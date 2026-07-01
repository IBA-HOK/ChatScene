# ChatScene LLM ベースシナリオ生成・訓練手順書

このドキュメントでは、ChatScene プロジェクトで ChatGPT（OpenAI API）を使った動的シナリオ生成から、エージェント訓練・評価までの一連の流れをまとめています。

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

## 3. OpenAI API キーの設定

`retrieve/architecture.py` は `.env` ファイルから `OPENAI_API_KEY` を読み込みます。

```bash
# .env ファイルを編集
OPENAI_API_KEY=sk-your-actual-api-key-here
```

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

| 引数 | 説明 |
|---|---|
| `--model gpt-4o` | 使用する LLM（デフォルト: gpt-4o） |
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

## 6. Scenic ファイルのコンパイル検証

生成された `.scenic` ファイルは、CARLA が利用可能な `chatscene` 環境で検証します。

```bash
conda activate chatscene
python scripts/verify_dynamic_scenarios.py --port_ip 2000
```

検証に失敗したファイルは `.scenic` から `.txt` にリネームされ、手動確認用に残ります。

---

## 7. エージェント訓練

検証済みの Scenic ファイルを使って、エージェントを訓練します。

### 7.1 シナリオ選定（train_scenario）

```bash
conda activate chatscene
python scripts/run_train_dynamic.py \
  --agent_cfg=adv_scenic.yaml \
  --scenario_cfg=dynamic_scenic.yaml \
  --mode train_scenario
```

### 7.2 エージェント訓練（train_agent）

```bash
conda activate chatscene
python scripts/run_train_dynamic.py \
  --agent_cfg=adv_scenic.yaml \
  --scenario_cfg=dynamic_scenic.yaml \
  --mode train_agent
```

### 7.3 評価（eval）

```bash
conda activate chatscene
python scripts/run_eval_dynamic.py \
  --agent_cfg=adv_scenic.yaml \
  --scenario_cfg=dynamic_scenic.yaml \
  --mode eval
```

---

## 8. トラブルシューティング

### 8.1 `ImportError: cannot import name 'cached_download' from 'huggingface_hub'`

`sentence_transformers==2.2.1` と新しい `huggingface_hub` の互換性問題です。

```bash
pip install --upgrade sentence_transformers
```

### 8.2 `CUDA error: no kernel image is available for execution on the device`

PyTorch が GPU の compute capability に対応していません。RTX 5080（sm_120）など最新 GPU では、chatscene-retrieval 環境を使用してください。

### 8.3 `openai.AuthenticationError: 401`

`.env` の `OPENAI_API_KEY` が未設定か、無効なキーです。有効な API キーに書き換えてください。

---

## 9. 注意事項

- `chatscene` 環境と `chatscene-retrieval` 環境は分離しています。retrieval 環境では CARLA は動きません。
- `.env` ファイルには実際の API キーを記入してくださいが、Git にはコミットしないでください。
- 生成された `dynamic_*.scenic` は訓練前に必ず `verify_dynamic_scenarios.py` で検証してください。
- `__pycache__/` や `log/`、`safebench.egg-info/` などは `.gitignore` に追加しておくことを推奨します。
