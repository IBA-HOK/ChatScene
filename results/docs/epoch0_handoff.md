# epoch 0（SAC pretrain）Table1取得 引継ぎ手順

最終更新: 2026-10-23 / 対象: SAC のみ（PPO・TD3は未実施）
リポジトリ: `/home/hokuto/chatScene_Strata/ChatScene`

---

## 1. 目的

論文 ChatScene（`papers/chatScene.html`）Table 1 のうち **SAC ego 列**を、
pinned replay で再現する。

論文の Table1 は「SAC surrogate で最も困難な scene を選抜 → 選抜 scene を
SAC / PPO / TD3 の 3 ego で評価 → 3 ego の平均」という定義。
本手順は **SAC のみ**（指示により PPO/TD3 は対象外）。

残作業は **scenario 2, 4, 6, 7, 8** の capture + eval。
scenario 1, 3, 5 は取得済み。

---

## 2. 環境（必ず守る）

- Python: `/home/hokuto/miniforge3/envs/chatscene/bin/python`（base に torch なし）
- CARLA: `./carla`、port 2002 / TM port 8002
- `import scenic` は旧ツリーを指すが内容同一で無害
- `python scripts/*.py` は旧 checkout を shadow するため、**PYTHONPATH 先頭に
  ROOT_DIR** を置く（batch が自動処理。手動実行時は要注意）
- 実行前に必ず `pgrep -f run_paper_repro.sh` と
  `ss -tlnp | grep -E ':2002|:8002'` を確認（多重起動は flock で拒否される）

---

## 3. 現在の状態（2026-10-23 時点）

| scenario | pinned | capture records | eval records (epoch0) |
|---|---|---|---|
| 1 StraightObstacle | 50 | 50 | 50 |
| 2 TurningObstacle | 0 | 1（stale） | 0 |
| 3 LaneChanging | 50 | 50 | 50 |
| 4 VehiclePassing | 0 | 0 | 0 |
| 5 RedLightRunning | 50 | 50 | 50 |
| 6 UnprotectedLeft | 0 | 0 | 0 |
| 7 RightTurn | 0 | 0 | 0 |
| 8 CrossingNegotiation | 0 | 0 | 0 |

s1 / s3 / s5 の確定値（回帰確認用ベースライン）:

| scenario | CR↑ | OS↓ | ADE↑（論文準拠 tail10） | 論文ADE |
|---|---|---|---|---|
| 1 | 0.990 | 0.441 | 2.826 | 4.398 |
| 3 | 0.720 | 0.565 | 5.744 | 5.706 |
| 5 | 0.810 | 0.545 | 3.816 | 3.848 |

- 全 300 scene が移動（静止 0）。s3・s5 の ADE は論文と 1% 以内で一致。

routes 8–9 のみ（DSF pilot の比較用ベースライン）:

| scenario | n | CR↑ | OS↓ | ADE↑ (eval proxy) | ADE↑ (tail10) |
|---|---:|---:|---:|---:|---:|
| 1 | 20 | 1.000 | 0.436 | 2.628 | 2.392 |
| 3 | 20 | 0.700 | 0.584 | 12.687 | 6.687 |
| 5 | 20 | 0.850 | 0.531 | 4.456 | 3.876 |
| avg | | 0.850 | 0.517 | | |

- `eval proxy` は `--ade-root` なし（eval 母集団の選択 scene 間 ADE）。
- `tail10` は capture records の末尾10 step を使う論文寄り集計。

算出コマンド:

```bash
# eval proxy
python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic \
  --ego sac-pretrain --scenarios 1,3,5 --routes 8,9

# paper-like tail10
python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic \
  --ego sac-pretrain --scenarios 1,3,5 --routes 8,9 \
  --ade-root log/adv_train/train_scenario/sac/adv_scenic --ade-tail 10
```

---

## 4. 確定済みの根本原因と修正（再調査不要）

1. **eval の `pretrain_dir` 上書き（最重要）**
   `scripts/run_eval.py` で `args.pretrain_dir=None` が
   `agent_config.update(args_dict)` により YAML 値を破壊し、
   **未学習のランダム SAC** で評価していた（全車静止 → CR 0.0）。
   修正: `pretrain_dir is None` のとき dict から key を落とす。
   確認方法: eval ログに `>> Initilizing sac model from ...` が出ること。

2. **`record_params` の None 参照**
   `endSimulation` 後の `self.scene=None` 参照で衝突時にクラッシュ。
   修正: `record_params` は `self.scene or self._last_scene` を参照。

3. **sampler の dict 未対応**
   `replay_scenes` は `{select_id: scene}` を返すのに list 前提の
   `idx >= len()` 判定で全滅（`SCENIC_GEN_FAILED: out of range` 160件）。
   修正: dict のときは `idx not in self.scene` で判定。

4. **ADE の集計誤り**
   全 route をプールしてペア比較していたため 177〜302 の異常値。
   論文定義（同一 scenario 内のペア）に修正。

### 4.1 意図的に「書き戻した」もの（復活させない）

- 縮退ガード `_check_adv_degenerate` / `[GUARD]`（真因ではなく誤爆源。1438回誤発火）
- `_geo` 非OPT形状ピン（旧 pins で問題なく動作するため不要）
- stale simulation のクリア（`record_params` クラッシュを誘発）
- `get_ego_vehicles` / `get_hero_actor` の検証（ego ハンドル起因の証拠なし）

残している対策: フェンス網（SIGALRM / exit 42・43）、watchdog、preflight、
TM warmup、logger の化石検知、sampler 修正、pool key 修正、例外安全な remove。

---

## 5. 実行手順（残り 5 scenario）

### 5.1 事前確認

```bash
cd /home/hokuto/chatScene_Strata/ChatScene
pgrep -af "run_paper_repro.sh|run_train.py|run_eval.py" | grep -v "bash -c"   # 空であること
ss -tlnp | grep -E ':2002|:8002'                                              # 空 or CARLA のみ
```

### 5.2 本実行（capture → eval → 集計を一括）

```bash
SCENARIOS="2 4 6 7 8" \
EVAL_ROUTES="0 1 2 3 4 5 6 7 8 9" \
STEP_TIMEOUT=1800 STEP_TIMEOUT_TRAIN=21600 \
setsid nohup bash scripts/run_paper_repro.sh \
  --skip-train-agent --test-epoch 0 --restart-carla --aggregate \
  > /tmp/epoch0_rest.log 2>&1 < /dev/null &
```

- `--skip-train-agent`: SAC は pretrain 重みを使うため adv 学習は不要
- capture は 1 scenario = 50 config（10 route × 5 behavior）。
  実測 s1≒7h / s3≒5h（hang 復旧込み）→ **5 scenario で 25〜35h 想定**
- `--aggregate` は終了時に `scripts/summarize_table1.sh` を実行
  （既定 ADE は eval 母集団。論文準拠 ADE は 5.4 で別途算出）

### 5.3 監視（15分間隔が最適）

```bash
tail -n 3 /tmp/epoch0_rest.log
grep -c "OK: eval" /tmp/epoch0_rest.log
find log/adv_train/eval/sac/adv_scenic_epoch0 -name "*records.pkl" | wc -l
python3 -c "import json,glob; fs=sorted(glob.glob('safebench/scenario/scenario_data/scenic_data/scenario_*/scenario_*.json')); print([(f.split('/')[-2], sum(1 for v in json.load(open(f)).values() if v.get('pinned'))) for f in fs])"
```

正常時: `pinned` が増加、ログサイズ増加、worker の CPU 時間が増加。

### 5.4 論文準拠 ADE の算出（重要）

ADE は「生成アルゴリズムの多様性」指標で **ego 非依存**。
選抜済み 2 scene ではなく、**capture の収束ラウンド（最終10件）**から測る。

```bash
export PYTHONPATH=/home/hokuto/chatScene_Strata/ChatScene:$PYTHONPATH
for sub in PythonAPI/carla/agents PythonAPI/carla PythonAPI; do
  [ -e carla/$sub ] && PYTHONPATH=$PYTHONPATH:carla/$sub; done
for egg in carla/PythonAPI/carla/dist/carla-*.egg; do
  [ -e "$egg" ] && PYTHONPATH=$PYTHONPATH:$egg && break; done

/home/hokuto/miniforge3/envs/chatscene/bin/python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic \
  --ade-root  log/adv_train/train_scenario/sac/adv_scenic \
  --ade-tail 10 --ego sac-pretrain --scenarios "1,2,3,4,5,6,7,8"
```

参考: `--ade-tail 0`（全50件）は 5.444 / 8.677 / 4.427 と過大、
`--ade-tail 10`（収束）が論文一致（s3 5.744 vs 5.706、s5 3.816 vs 3.848）。

---

## 6. 既知の障害と復旧

| 症状 | 原因 | 対処 |
|---|---|---|
| `SCENIC_GEN_FAILED: out of range` | sampler の dict 未対応（修正済） | 修正が入っているか確認 |
| `traffic manager ... bind error` | 孤児 worker が 8002 占有 | batch の preflight が自動掃除。手動なら `ss -tlnp` で PID 特定 → `kill -9` |
| worker が無出力＋CPU 停止 | CARLA RPC 固着 | フェンスが 15 分で exit 43 → 温存 retry。eval は watchdog 対象外なので `STEP_TIMEOUT=1800` で 30 分打ち切り |
| eval が `This scenario and route have been done.` で全 skip | 過去の（誤った）出力が残存 | `log/adv_train/eval/sac/adv_scenic_epoch0` を削除して再実行 |
| CR が 0.0 / 全車静止 | pretrain 未ロード | ログに `Initilizing sac model` があるか確認。無ければ `run_eval.py` の修正が消えている |
| 衝突時に `AttributeError: 'NoneType' ... params` | `record_params` の scene 参照 | 修正済み。再発時は `_last_scene` を確認 |

- 固着 worker は SIGTERM を無視する → **`kill -9` のみ有効**
- **batch 実行中に `scripts/run_paper_repro.sh` を編集しない**（逐次読み破壊）。
  Python ファイルはプロセス起動時に読まれるため編集可

---

## 7. 完了条件（検証ゲート）

1. pinned が **8 scenario × 50 = 400 件**
2. epoch0 eval が **8 scenario × 50 records = 400 件**
3. 集計で `All green`、`FAILED` なし
4. 全 scene が移動（静止 0 を確認）:

```bash
export PYTHONPATH=/home/hokuto/chatScene_Strata/ChatScene:$PYTHONPATH
# 先頭の PythonAPI 追加は 5.4 と同じ
/home/hokuto/miniforge3/envs/chatscene/bin/python - <<'PY'
import joblib, glob, numpy as np
fs=glob.glob('log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic/scenario_*/*/eval_results/*_records.pkl')
stat=mov=col=0
for f in fs:
    for k,s in joblib.load(f).items():
        ex=np.array([t['ego_x'] for t in s]); ey=np.array([t['ego_y'] for t in s])
        d=float(np.hypot(ex[-1]-ex[0], ey[-1]-ey[0]))
        mov += d>=5; stat += d<5
        col += str(s[-1].get('collision'))=='Status.FAILURE'
print('files=%d scenes=%d moving=%d static=%d collided=%d' % (len(fs), stat+mov, mov, stat, col))
PY
```

5. ADE（tail10）が論文オーダー（約 3〜8）に入る

---

## 8. 追加取得（必要になった場合のみ）

PPO / TD3 列（論文 Table1 は 3 ego 平均）。チェックポイントは既存:

- `safebench/agent/model_ckpt/safe_rl/ppo_0/model_save/model.pt`
- `safebench/agent/model_ckpt/safe_rl/td3_0/model_save/model.pt`

`scripts/run_eval.py` は `--test_policy ppo|td3` と `--pretrain_dir` を受け付ける。
現行 batch は SAC 固定なので、PPO/TD3 は個別に eval を回すことになる。
