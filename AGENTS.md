# 前提
本実験はchatscene.htmlにある論文の追実験であるため、実行前に必ずその論文及びその他参考文献(./papers/*)を確認すること

# スキル
可能な限りスキルgenshijinを使用すること

# 環境
実行用環境は./carlaにある

# 指示
スクリプトの乱立は控え、実装のさいには類似する役割のスクリプトがないかを評価してから作業すること
Agent自身が参照するための文書などは./AgentDocsに配置すること
この環境は論文付属のGithubレポジトリのフォークである よって論文記載の実験などを行う場合、新たなスクリプトを作る前に利用可能なものがないか十分精査すること

# 現在の目標（DSF選抜の改善）
- baseline（collision-based selection）は先行研究再現のため変更しない。比較用にrawのまま保持する。
- DSF側は衝突sceneを許可する。`require_no_collision: true` で衝突を全除外しない。
- side/rearは許容する。side/rear除去は目的ではない。
- 回避不能sceneを選抜から除外または下位化する。
- 目標指標: CRは低下してよい（PDF p-11）。OSは上昇させない。ADEは維持/改善。衝突不可避率I45は低下。side/rear率は参考指標で制約しない。
- 公式I45定義: 衝突相手がego中心から5m以内かつ正面±45°（全角90°）以内に入った最初の時刻を検出開始とする。0.3s反応遅れ後、最大減速8m/s²＋最大操舵proxy（横加速度5m/s²、yaw rate 1rad/s cap）で回避不能なら不可避。`not_front`は不可避に算入する。分母はL1通過衝突、L1 rejectのみ除外。
- 選抜方針: L1 hard reject → 5m+45°検出 → avoidable gate → hard-avoidable margin昇順 → directional DSF/OS ranking → eval検証とrefill。side/rear contactは許容。
- 評価はactual eval recordsを優先する。capture metricsは予備検証に留める。
- SACは`obs_type=0`で周囲actorを検出しない。5m/±45°は前方センサ仮定であり、SACの検出範囲とは呼ばない。
- avoidability-firstは易しい衝突を拾い、CRを落とす（trial: CR .565, I45 .607）。Aは1.0に飽和するためhardnessに使わない。
- hard-avoidable margin: brake/left/right各候補の最小中心距離から衝突半径2mを引いた値の最大。`0 < margin < 0.5m`を「難しいが回避可能」の候補とする。
- 実装前に関連スクリプト（`safebench/scenic_runner.py`, `safebench/util/dsf.py`, `tools/dsf_select.py`, `tools/avoidability_audit.py`, `tools/compute_table1.py`）を精査し、新規スクリプト乱立を避ける。
- 実験結果・比較表は`results/`、引継ぎ・設計は`AgentDocs/`に置く。

# 評価プロトコルと注意（必読）
- I45でsceneを選び、同じscene集合でI45を評価してはいけない。それは評価リークで、改善は定義上当然。I45は「選抜の道具」と「評価の物差し」を同時に使わない。
- I45を使った選抜結果は「benchmark construction」または「oracle」として分離する。手法の改善主張には使わない。
- 手法評価では、選抜と最終評価を分離する。
  - 校正: routes 0-7（またはscenario 1/3）
  - 最終テスト: routes 8-9（またはscenario 5）
  - 閾値・選抜ルールは校正側で固定し、テスト側では変更しない。
- 選抜proxyの例: future-path DSF、near-miss margin、OS/ADE diversity。I45は最終評価だけに使う。
- eval-dispose（eval結果を見てsceneを選び直す）をtest setで行わない。validation内のrefillに限定する。
- baselineはrawのまま保持する。I45を比較する場合は、baselineにも同じI45フィルタを適用した参考値を出し、rawとfilteredを混同しない。DSF側だけフィルタしてbaseline rawと比較しない。
- `pinned`は必須。選抜した全data_idに`pinned`を保存し、evalは`replay_scenes(pinned)`で固定再生成する。pinnedなしのevalはdata_id driftで無効。
- `not_front`（5m+45°に一度も入らない）はI45で不可避に算入する。side/rear contact自体は許容だが、front検出できないside/rear接近はnot_frontとして扱う。
- 評価指標はCR/OS/ADE/I45に加え、avoidable collision yield、eval衝突数、L1 reject数、insufficient group数を報告する。
- full `dsf_avoidable`の実績: I45 .464、side+rear 4、ADE 7.338、CR .533、OS .663。I45は改善したがOSがbaseline .517から悪化しており、成功ではない。
- 実行中の`run_paper_repro.sh`などは編集しない。bashが読み取り位置をずらして末尾で構文エラーになる。
- 実験結果は`results/`、設計・評価プロトコルは`AgentDocs/`、AGENTS.mdは方針のみを保つ。
