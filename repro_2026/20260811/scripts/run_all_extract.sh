#!/bin/bash
# Run extraction for all 4 LLMs.
set -e
cd /home/hokuto/chatScene/ChatScene/repro_2026
PY=/home/hokuto/miniforge3/envs/chatscene/bin/python

LOG_DIR=/home/hokuto/chatScene/ChatScene/repro_2026/logs
mkdir -p $LOG_DIR

for MODEL in gemma4:e4b gemma4:e2b gemma4:12b qwen3.5:4b; do
  MODEL_TAG=$(echo $MODEL | tr ':' '_')
  echo "============================================================"
  echo "Extracting for $MODEL at $(date)"
  echo "============================================================"
  $PY extract_components.py --model $MODEL \
    > $LOG_DIR/${MODEL_TAG}_extract.log 2>&1
  tail -2 $LOG_DIR/${MODEL_TAG}_extract.log
done

echo "ALL EXTRACTIONS DONE"
