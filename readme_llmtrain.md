# ChatScene LLM ベースシナリオ生成・訓練手順書

このドキュメントでは、ChatScene プロジェクトで ChatGPT（OpenAI API）または **Ollama OpenAI 互換 API** を使った動的シナリオ生成から、エージェント訓練・評価までの一連の流れをまとめています。

特に、**RTX 5080 のような最新 GPU + CARLA 0.9.13（Python 3.8 前提）+ 最新 PyTorch** の組み合わせで発生する互換性問題（デッドロック）についても、その回避方法を記載しています。

---

## 1. プロジェクト構成と責務分離

本プロジェクトでは、シナリオ生成とエージェント訓練を分離して実行します。

```
┌─────────────────────────────────────────────────────────────────┐
│  chatscene-retrieval（Python 3.10 + PyTorch 2.x + CUDA 13）    │
│  └─ ChatGPT による Scenic シナリオコード生成                   │
│  └─ sentence-transformers による RAG 検索                     │
│  └─ 生成物：safebench/scenario/scenario_data/scenic_data/dynamic_scenario/
└─────────────────────────────────────────────────────────────────┘
                              ↓ 生成ファイルを共有
┌─────────────────────────────────────────────────────────────────┐
│  chatscene（Python 3.8 + CARLA 0.9.13 + PyTorch 1.13 + CUDA 11.7）│
│  └─ Scenic ファイルのコンパイル検証                              │
│  └─ エージェント訓練（run_train_dynamic.py）                    │
│  └─ エージェント評価（run_eval_dynamic.py）                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 環境構築

### 2.1 メイン環境（chatscene）

README.md の手順に従って構築します。CARLA 0.9.13 は Python 3.8 が前提です。

```bash
conda create -n chatscene python=3.8
conda activate chatscene
pip install -r requirements.txt
pip install decorator==5.1.1
pip install -e .
cd Scenic
python -m pip install -e .
```

### 2.2 検索・生成専用環境（chatscene-retrieval）

RTX 50 系 GPU など、最新 GPU を使用する場合は専用環境を構築します。

```bash
conda create -n chatscene-retrieval python=3.10 -y
conda activate chatscene-retrieval
pip install -r requirements-retrieval.txt
```

`requirements-retrieval.txt` には以下が含まれます：

- PyTorch 2.x（CUDA 12.4 / 13.0 対応）
- `sentence_transformers`
- `openai`
- `python-dotenv`
- `transformers`
- `tqdm`
- `numpy`

---

## 3. API キーの設定

`retrieve/architecture.py` は `.env` ファイルから API 設定を読み込みます。

### 3.1 OpenAI API を使う場合

```bash
# .env ファイルを編集
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 3.2 Ollama OpenAI 互換 API を使う場合

ローカルの Ollama サーバーを使う場合は、`.env` に以下を追加します。

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_API_KEY=ollama  # Ollama では実際には使用されませんが、OpenAI クライアント用に空でない値が必要です
```

Ollama 側で事前に利用するモデルを pull しておいてください（例：`ollama pull llama3.2`）。

`.env` は `.gitignore` に登録されており、Git にコミットされません。

---

## 4. シナリオ記述の作成

自然言語でシナリオを `retrieve/scenario_descriptions.txt` に記述します。

```text
The ego vehicle is driving on a straight road; the adversarial pedestrian suddenly crosses the road from the right front and suddenly stops in front of the ego.
The ego vehicle attempts a right turn at a four-way intersection, and an adversarial pedestrian crosses the road and suddenly stops.
```

1 行 1 シナリオです。

---

## 5. 動的シナリオの生成

`chatscene-retrieval` 環境で実行します。

```bash
conda activate chatscene-retrieval
python retrieve/retrieve.py --model gpt-4o --use_llm --no_verify
```

#### Ollama を使う場合

```bash
conda activate chatscene-retrieval
python retrieve/retrieve.py --model llama3.2 --ollama_url http://localhost:11434/v1 --use_llm --no_verify
```

`--ollama_url` は `.env` の `OLLAMA_BASE_URL` よりも優先されます。省略した場合は `OLLAMA_BASE_URL` が使用されます。

| 引数 | 説明 |
|---|---|
| `--model gpt-4o` / `--model llama3.2` | 使用する LLM（デフォルト: gpt-4o） |
| `--ollama_url` | Ollama の OpenAI 互換 API エンドポイント（例: `http://localhost:11434/v1`） |
| `--use_llm` | LLM で Scenic コードを生成します（指定しないと純粋な検索のみ） |
| `--no_verify` | Scenic のコンパイル検証をスキップします。retrieval 環境には CARLA が入っていないため必須です |
| `--topk 3` | RAG 検索で上位何件を使うか（デフォルト: 3） |
| `--port_ip 2000` | CARLA ポート指定（検証しない場合は不要） |

生成されたファイルは以下に保存されます：

```
safebench/scenario/scenario_data/scenic_data/dynamic_scenario/
├── dynamic_0.scenic
├── dynamic_1.scenic
├── ...
└── dynamic_log.csv
```

---

## 6. 生成したシナリオの実行（ステップバイステップ）

以降の手順はすべて `chatscene` 環境で、**CARLA サーバーが起動している状態** で実行します。

### Step 0: CARLA サーバーを起動する

```bash
conda activate chatscene
cd /path/to/CARLA_0.9.13
./CarlaUE4.sh -RenderOffScreen
```

`-RenderOffScreen` をつけると画面表示なしで起動できます。GPU メモリが不足する場合は、ヘッドレスモードを検討してください。

CARLA が起動し、ポート 2000 で待ち受けていることを確認します。

### Step 1: 生成された Scenic ファイルを検証する

`chatscene-retrieval` 環境では CARLA がないため、コンパイル検証は `chatscene` 環境で行います。

```bash
conda activate chatscene
python scripts/verify_dynamic_scenarios.py --port_ip 2000
```

このスクリプトは `safebench/scenario/scenario_data/scenic_data/dynamic_scenario/` 以下の `.scenic` ファイルを 1 つずつ CARLA に読み込ませ、コンパイルできるかチェックします。

- **成功したファイル**: そのまま `.scenic` として残ります。
- **失敗したファイル**: `.scenic` から `.txt` にリネームされ、手動確認用に残ります。

検証後、`.scenic` ファイルだけが残っていることを確認してください。

### Step 2: シナリオ設定ファイルを確認する

`safebench/scenario/config/dynamic_scenic.yaml` を開き、生成したシナリオに合わせて以下を確認・修正します。

主に確認する項目：

- `scenic_dir`: 生成した Scenic ファイルが置かれたディレクトリ（例：`safebench/scenario/scenario_data/scenic_data/dynamic_scenario/`）
- `scenario_id`: 実行するシナリオ番号（`null` で全シナリオ、または `[0, 1, 2]` のようにリストで指定）
- `sample_num`: 各シナリオでサンプリングする経路・パラメータ数
- `opt_step`: 最適化ステップ数
- `select_num`: 選定するシナリオ数

`map`（Town 名）は各 `.scenic` ファイル内で指定されているため、必要に応じて `.scenic` ファイル側を編集してください。

必要に応じて、`dynamic_scenic.yaml` を編集してください。

### Step 3: シナリオを選定する（train_scenario）

生成した Scenic シナリオから、訓練に使用するシナリオを選定します。

```bash
conda activate chatscene
python scripts/run_train_dynamic.py \
  --agent_cfg=adv_scenic.yaml \
  --scenario_cfg=dynamic_scenic.yaml \
  --mode train_scenario
```

実行後、選定されたシナリオの情報がログや設定ファイルに反映されます。

### Step 4: エージェントを訓練する（train_agent）

選定されたシナリオ上でエージェントを訓練します。

```bash
conda activate chatscene
python scripts/run_train_dynamic.py \
  --agent_cfg=adv_scenic.yaml \
  --scenario_cfg=dynamic_scenic.yaml \
  --mode train_agent
```

訓練には GPU の性能によりますが、数時間～数日かかることがあります。ログは `log/` ディレクトリに保存されます。

訓練が完了すると、モデルチェックポイントが `safebench/agent/model_ckpt/` 以下に保存されます。

### Step 5: 評価する（eval）

訓練済みエージェントを使って、生成したシナリオ上で評価を行います。

```bash
conda activate chatscene
python scripts/run_eval_dynamic.py \
  --agent_cfg=adv_scenic.yaml \
  --scenario_cfg=dynamic_scenic.yaml \
  --mode eval
```

評価結果はログに出力され、衝突率や成功率などのメトリクスが確認できます。

### 実行の流れまとめ

```bash
# ターミナル 1: CARLA サーバー
conda activate chatscene
./CarlaUE4.sh -RenderOffScreen

# ターミナル 2: 検証・訓練・評価
conda activate chatscene
python scripts/verify_dynamic_scenarios.py --port_ip 2000
python scripts/run_train_dynamic.py --agent_cfg=adv_scenic.yaml --scenario_cfg=dynamic_scenic.yaml --mode train_scenario
python scripts/run_train_dynamic.py --agent_cfg=adv_scenic.yaml --scenario_cfg=dynamic_scenic.yaml --mode train_agent
python scripts/run_eval_dynamic.py --agent_cfg=adv_scenic.yaml --scenario_cfg=dynamic_scenic.yaml --mode eval
```

---

## 7. トラブルシューティング

### 7.1 `ImportError: cannot import name 'cached_download' from 'huggingface_hub'`

`sentence_transformers==2.2.1` と新しい `huggingface_hub` の互換性問題です。

```bash
pip install --upgrade sentence_transformers
```

### 7.2 `CUDA error: no kernel image is available for execution on the device`

PyTorch が GPU の compute capability に対応していません。RTX 5080（sm_120）など最新 GPU では、chatscene-retrieval 環境を使用してください。

### 7.3 `openai.AuthenticationError: 401`

`.env` の `OPENAI_API_KEY` が未設定か、無効な API キーです。有効な API キーに書き換えてください。Ollama を使う場合は `OPENAI_API_KEY` は不要です。

### 7.4 Ollama 接続エラー

まず、簡易接続テストを実行してください：

```bash
conda activate chatscene-retrieval
python retrieve/test_ollama.py --model gemma4:26b --ollama_url http://localhost:11434/v1
```

テストが成功したら、`retrieve/retrieve.py` でも同じ設定で実行できます。失敗する場合は以下を確認してください：

- Ollama サービスが起動しているか確認してください: `ollama serve` または `ollama run <model>`
- `--ollama_url` / `OLLAMA_BASE_URL` が正しいか確認してください（末尾に `/v1` が必要です）
- 指定したモデルが `ollama list` に存在し、事前に pull されているか確認してください

#### 最初の生成で止まる場合

大きなモデル（例：`gemma4:26b`）では、Ollama への最初のリクエスト時にモデルをメモリに読み込むため、数分～十分以上かかることがあります。ターミナルで `ollama run gemma4:26b` としてモデルを事前にメモリに載せておくか、しばらく待ってみてください。`retrieve/retrieve.py` 実行時に `[LLMChat] Using Ollama OpenAI-compatible API: ...` と表示されていれば、Ollama 経由で動作しています。

また、Ollama がモデルをアンロードしてしまうのを防ぐため、以下のように起動すると応答が速くなります：

```bash
OLLAMA_KEEP_ALIVE=-1 ollama serve
```

`OLLAMA_KEEP_ALIVE=-1` は、Ollama プロセスが終了するまでモデルをメモリに保持します。

### 7.5 Scenic コンパイル検証で失敗する

- 生成された `.scenic` ファイル内の `Town` と、実行する CARLA のマップが一致しているか確認してください。
- 失敗したファイルは `.txt` になっているため、内容を確認して修正するか、再生成してください。

### 7.6 訓練・評価で CARLA 接続エラー

- CARLA サーバーが起動しているか確認してください。
- `--port_ip` と CARLA の待受ポートが一致しているか確認してください（デフォルトは 2000）。
- `--port_ip` と CARLA の待受ポートが一致しているか確認してください（デフォルトは 2000）。

---

## 8. 注意事項

- `chatscene` 環境と `chatscene-retrieval` 環境は分離しています。retrieval 環境では CARLA は動きません。
- `.env` ファイルには実際の API キーを記入してくださいが、Git にはコミットしないでください。
- 生成された `dynamic_*.scenic` は訓練前に必ず `verify_dynamic_scenarios.py` で検証してください。
- `__pycache__/` や `log/`、`safebench.egg-info/` などは `.gitignore` に追加しておくことを推奨します。
