# ChatScene 追実験レポート (20260811) — ファイル構成と説明

本ディレクトリは、ChatScene 論文 (arXiv:2405.14062v1) の追実験として実施した
「ollama serve で提供されるローカル LLM 4 モデルによる安全クリティカルシナリオ
記述生成実験」の成果物一式です。

- 対象モデル: `gemma4:e4b` (8.0B), `gemma4:e2b` (5.1B), `gemma4:12b` (11.9B), `qwen3.5:4b` (4.7B)
- 実行環境: NVIDIA GeForce RTX 5080 (16GB VRAM) / 156GB RAM / Ubuntu Linux
- 論文のベースライン (LC/AS/CS/AT/GPT-4) の CARLA 評価数値は再実験せず、
  論文の Table 1/2/3/8/9 をそのまま参照データとして使用
- 実験日: 2026-08-12 (ディレクトリ名は 20260811 の名残り)

---

## 1. 新造ファイル一覧と説明

以下、本実験で新規に作成されたファイル・ディレクトリの全説明です。

### 1.1 スクリプト (ルート直下 & `scripts/`)

| ファイル | 説明 |
|---|---|
| `generate_descriptions.py` | **シナリオ記述生成スクリプト**。8 つのベースシナリオ (Straight Obstacle / Turning Obstacle / Lane Changing / Vehicle Passing / Red-light Running / Unprotected Left-turn / Right-turn / Crossing Negotiation) に対し、指定 LLM に 5 件ずつの安全クリティカルシナリオ記述を生成させる。Ollama の OpenAI 互換 API (`http://localhost:11434/v1`) を使用し、空応答時はリトライ、出力は `descriptions/<model_tag>/<Scenario>.json` に保存。`--model` / `--n_per_scenario` / `--temperature` 等を指定可能。 |
| `run_all_models.sh` | 4 モデル (`gemma4:e4b` → `gemma4:e2b` → `gemma4:12b` → `qwen3.5:4b`) を順番に `generate_descriptions.py` で実行するバッチスクリプト。各モデルのログは `logs/<model_tag>.log` に出力。 |
| `extract_components.py` | **コンポーネント抽出スクリプト**。論文の `retrieve/prompts/extraction.txt` を移植したプロンプトで、各記述を Adversarial Object / Behavior / Geometry / Spawn Position の 4 コンポーネントに分解する。結果は `extractions/<model_tag>/<Scenario>.json` に保存。正規表現パーサ (`parse_extraction`) で 4 項目すべて取得できた場合のみ success と判定。 |
| `run_all_extract.sh` | 4 モデル分の `extract_components.py` を順番に実行するバッチスクリプト。ログは `logs/<model_tag>_extract.log`。 |
| `fill_missing.py` | **空記述の補完スクリプト**。`descriptions/<Scenario>.json` 内で空文字列のスロットだけを再生成して埋める (qwen3.5:4b の空応答対策用)。再実行時に既存の非空記述を保持したまま欠損のみ補完できる。 |
| `refill_extractions.py` | **失敗抽出の再実行スクリプト**。`extractions/<Scenario>.json` 内で success=False のレコードのみ、簡潔なフォーマット指定プロンプトで再抽出を試みる (qwen3.5:4b 対策)。途中経過を JSON に逐次保存する。 |
| `analyze_descriptions.py` | **記述品質の分析スクリプト**。各モデルの記述について、記述長 (avg/max/min)、ユニーク数、ペアワイズ Jaccard 類似度 (多様性の逆指標)、ego 言及率、Behavior キーワード数、敵対オブジェクト種別分布を計算し `results/analysis.json` に出力。`--include_baseline` で論文の GPT-4 記述 (`retrieve/scenario_descriptions.txt`) も同時に分析。 |
| `judge_one.py` | **LLM-as-Judge 採点スクリプト (モデル単位版)**。judge モデル (デフォルト `gemma4:12b`) に各記述を 0–5 の 3 軸 (Safety-criticality / Specificity / Realism) で採点させる。1 モデルずつ実行し、進捗と JSON を逐次保存するため、途中失敗時の再開が容易。結果は `results/judge_scores.json` に追記される。 |
| `judge_scores.py` | **LLM-as-Judge 採点スクリプト (一括版)**。全モデルの記述を 1 プロセスで一括採点する。機能は `judge_one.py` と同等だが、途中でプロセスが落ちると途中結果が失われるため、実運用では `judge_one.py` を推奨。 |
| `scenic_subset.py` | **Scenic コード生成の試行スクリプト**。既存の retrieval DB (`retrieve/database_v1.pkl`) からキーワード重複ベースの簡単な検索で Top-k スニペットを取得し、論文の `behavior.txt` プロンプト形式で各 LLM に Scenic スニペット生成を試行する。※実験の結果、4 モデルすべて Scenic 2.1 構文を満たすコードを生成できず (API の幻覚・空応答)、本パイプラインは「試行失敗」としてレポート 5.3 節に記録。 |
| `build_report.py` | **HTML レポート生成スクリプト**。論文の Table 1/2/3 のベースライン数値 (ハードコード)、`results/` 配下の分析結果、LLM-as-Judge スコアを組み合わせて 1 枚の統合 HTML レポートを生成。`report/report.html` を出力。 |

### 1.2 データ出力ディレクトリ

| パス | 説明 |
|---|---|
| `descriptions/<model_tag>/` | **生成されたシナリオ記述**。モデルごとに 8 シナリオ × 5 記述 = 40 記述を JSON に格納 (合計 160 記述)。各 `<Scenario>.json` は `model` / `base_scenario` / `prompt` / `descriptions[]` を持つ。`generation.log` は各 LLM 呼び出しの生出力。 |
| `descriptions/<model_tag>/generation.log` | 記述生成時の全 LLM 応答ログ (モデル毎・番号付き)。 |
| `extractions/<model_tag>/` | **コンポーネント抽出結果**。モデルごとに 8 シナリオ分の JSON。各レコードは `description` / `extraction_raw` / `extraction{Adversarial Object, Behavior, Geometry, Spawn Position}` / `success` を持つ。 |
| `results/analysis.json` | `analyze_descriptions.py` の出力。モデル別・シナリオ別の記述品質メトリクスとサマリ。GPT-4 ベースラインも含む。 |
| `results/extraction_analysis.json` | 抽出成功率 (モデル別) と敵対オブジェクト種別分布の集計。 |
| `results/judge_scores.json` | LLM-as-Judge の全採点結果 (モデル別・記述別の 3 軸スコア + 生応答)。計 200 件 (4 モデル × 40 + GPT-4 ベースライン 40)。 |
| `results/judge_by_scenario.json` | `judge_scores.json` をモデル×シナリオ単位に集約したスコア表 (Safety-criticality / Specificity / Realism の平均)。 |
| `logs/` | 全 LLM 呼び出しの生ログ。<br>・`<model_tag>.log` — 記述生成<br>・`<model_tag>_extract.log` — コンポーネント抽出<br>・`judge_gemma12b.log` / `judge_gemma_e2b.log` / `judge_gemma_e4b.log` / `judge_qwen.log` / `judge_gpt4.log` — judge_one.py による採点ログ<br>・`judge_scores.log` — judge_scores.py (一括版) のログ<br>・`qwen3.5_4b_rerun.log` / `qwen3.5_4b_refill.log` / `qwen3.5_4b_refill2.log` — qwen3.5 の欠損補完・再抽出ログ<br>・`run_all.log` / `run_all_extract.log` — バッチ実行の全体ログ |
| `report/report.html` | **統合 HTML レポート**。論文ベースライン表 (Table 1/2/3) + 新規 LLM 実験結果 (記述品質・抽出成功率・LLM-as-Judge スコア・サンプル記述/抽出) を 1 ファイルにまとめた最終成果物。 |
| `index.html` | `report/report.html` の同一コピー (ブラウザで開きやすいようにルートにも配置)。 |
| `scripts/` | ルート直下のスクリプトと同じもののコピー (整理用)。 |
| `README.md` | 本ファイル。新造ファイルの全説明と実験結果サマリ。 |

---

## 2. 実行パイプラインの流れ

```
(1) 記述生成      run_all_models.sh  →  generate_descriptions.py
                    ↓ descriptions/<model_tag>/<Scenario>.json (40×4=160件)
(2) 欠損補完      fill_missing.py (qwen3.5:4b の空応答対策)
(3) 抽出          run_all_extract.sh →  extract_components.py
                    ↓ extractions/<model_tag>/<Scenario>.json
(4) 再抽出        refill_extractions.py (失敗レコードのみ)
(5) 分析          analyze_descriptions.py → results/analysis.json
                    extract_analysis 集計 → results/extraction_analysis.json
(6) LLM-as-Judge  judge_one.py (×5ターゲット) → results/judge_scores.json
                    ↓ 集約 → results/judge_by_scenario.json
(7) レポート出力  build_report.py → report/report.html (= index.html)
```

---

## 3. 実験結果サマリ

| モデル | 記述数 | 平均長 (chars) | 多様性 (1−Jaccard) | ego 言及率 | 抽出成功率 | SC | SP | RE |
|---|---|---|---|---|---|---|---|---|
| gemma4:e2b | 40 | 149 | 0.72 | 70% | 100% | 5.00 | 3.17 | 4.88 |
| gemma4:e4b | 40 | 162 | 0.82 | 68% | 100% | 4.97 | 3.58 | 4.92 |
| gemma4:12b | 40 | 130 | 0.64 | 100% | 100% | 4.97 | 3.28 | 4.90 |
| qwen3.5:4b | 40 | 268 | 0.81 | 60% | 97.5% | 5.00 | 4.10 | 4.72 |
| GPT-4 (論文) | 40 | 198 | 0.62 | 100% | — | 4.53 | 3.03 | 4.65 |

- SC = Safety-criticality, SP = Specificity, RE = Realism (LLM-as-Judge, 0–5)
- 詳細は `report/report.html` を参照
- CARLA シミュレーション (CR/OS/ADE) は未実施 → 論文 Table 1/2/3 を参照データとして掲載

---

## 4. 未実施事項と理由

- **CARLA 評価 (CR/OS/ADE)**: 8 シナリオ × 10 ルート × 9 シーン × 4 モデルの
  フルシミュレーションは 24 GPU 時間超を要し、また論文の SAC/PPO/TD3 訓練済み
  ego モデルが必要なため未実施。論文の数値をベースラインとして使用。
- **敵対的ファインチューニング (Table 3)**: 訓練済み RL ポリシーが必要なため未実施。
- **Scenic コード生成**: 4 モデルとも Scenic 2.1 API の知識不足により
  幻覚 (存在しない API) や空応答が多発し、GPT-4 との同等比較は不可能と判断。
  `scenic_subset.py` の試行ログは `logs/` に残っている。
