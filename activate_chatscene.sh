#!/usr/bin/env bash
# ChatScene 実行環境をまとめて有効化するスクリプト
# README.md / readme_llmtrain.md の手順に基づき、
# conda 環境（chatscene）のアクティベートと CARLA 用 PYTHONPATH の設定を行います。
#
# 使用方法:
#   source activate_chatscene.sh
#
# 注意:
#   このスクリプトは source 実行してください。
#   ./activate_chatscene.sh として実行しても、サブシェルでのみ有効になり、
#   カレントシェルには反映されません。

# --- 1. source 実行かどうかの確認 ---
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "[Error] このスクリプトは source 実行してください。"
    echo "        source $(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    exit 1
fi

# --- 2. conda の検出と初期化 ---
# まずは現在の PATH から conda を探す
CONDA_BASE=""
if command -v conda >/dev/null 2>&1; then
    CONDA_BASE=$(conda info --base 2>/dev/null)
fi

# 見つからない場合は一般的なインストール先を順に試す
if [ -z "$CONDA_BASE" ]; then
    for conda_path in \
        "${HOME}/miniforge3" \
        "${HOME}/miniconda3" \
        "${HOME}/anaconda3" \
        "/opt/conda" \
        "/opt/miniconda3" \
        "/opt/anaconda3"
    do
        if [ -f "${conda_path}/bin/conda" ]; then
            CONDA_BASE="${conda_path}"
            break
        fi
    done
fi

if [ -z "$CONDA_BASE" ]; then
    echo "[Error] conda が見つかりませんでした。"
    echo "        conda をインストールするか、PATH を通してから再実行してください。"
    return 1
fi

# conda activate を正しく動作させるため、必ず shell hook を読み込む
# （PATH に conda 実行ファイルがあっても、シェル関数として初期化されていない場合がある）
# shellcheck source=/dev/null
eval "$("${CONDA_BASE}/bin/conda" shell.bash hook)"

# --- 3. chatscene 環境のアクティベート ---
echo "[Info] conda 環境 'chatscene' をアクティベートします..."
if ! conda activate chatscene; then
    echo "[Error] 'chatscene' 環境のアクティベートに失敗しました。"
    return 1
fi

# --- 4. CARLA_ROOT の設定 ---
# 既に設定済みならそれを優先
if [ -z "$CARLA_ROOT" ]; then
    for carla_path in \
        "${HOME}/CARLA_0.9.13" \
        "${HOME}/carla/CARLA_0.9.13" \
        "${HOME}/carla" \
        "/opt/carla-simulator" \
        "/opt/CARLA_0.9.13"
    do
        if [ -f "${carla_path}/CarlaUE4.sh" ]; then
            export CARLA_ROOT="${carla_path}"
            break
        fi
    done
fi

if [ -z "$CARLA_ROOT" ]; then
    echo "[Warning] CARLA_ROOT が設定されておらず、CARLA 0.9.13 の自動検出もできませんでした。"
    echo "          CARLA を実行する前に手動で設定してください:"
    echo "          export CARLA_ROOT=/path/to/CARLA_0.9.13"
else
    # README.md Step 7 に記載の PYTHONPATH を設定
    export PYTHONPATH=${PYTHONPATH}:${CARLA_ROOT}/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg
    export PYTHONPATH=${PYTHONPATH}:${CARLA_ROOT}/PythonAPI/carla/agents
    export PYTHONPATH=${PYTHONPATH}:${CARLA_ROOT}/PythonAPI/carla
    export PYTHONPATH=${PYTHONPATH}:${CARLA_ROOT}/PythonAPI
    echo "[Info] CARLA_ROOT=${CARLA_ROOT} を設定しました。"
fi

# --- 5. 設定内容の表示 ---
echo "[Info] 現在の conda 環境: ${CONDA_DEFAULT_ENV}"
echo "[Info] 準備完了。以下のように CARLA サーバーや訓練スクリプトを実行できます。"
echo ""
echo "  # CARLA サーバー起動例（リモート/ヘッドレス環境）"
echo "  cd \"\${CARLA_ROOT}\""
echo "  ./CarlaUE4.sh -prefernvidia -RenderOffScreen -carla-port=2000"
echo ""
echo "  # 動的シナリオの検証・訓練・評価例"
echo "  python scripts/verify_dynamic_scenarios.py --port_ip 2000"
echo "  python scripts/run_train_dynamic.py --agent_cfg=adv_scenic.yaml --scenario_cfg=dynamic_scenic.yaml --mode train_scenario"
echo "  python scripts/run_train_dynamic.py --agent_cfg=adv_scenic.yaml --scenario_cfg=dynamic_scenic.yaml --mode train_agent"
echo "  python scripts/run_eval_dynamic.py --agent_cfg=adv_scenic.yaml --scenario_cfg=dynamic_scenic.yaml --mode eval"
