#!/bin/bash
# Run all 4 LLMs sequentially for description generation.
set -e
cd /home/hokuto/chatScene/ChatScene/repro_2026
PY=/home/hokuto/miniforge3/envs/chatscene/bin/python

LOG_DIR=/home/hokuto/chatScene/ChatScene/repro_2026/logs
mkdir -p $LOG_DIR

for MODEL in gemma4:e4b gemma4:e2b gemma4:12b qwen3.5:4b; do
  MODEL_TAG=$(echo $MODEL | tr ':' '_')
  echo "============================================================"
  echo "Starting $MODEL at $(date)"
  echo "============================================================"
  $PY generate_descriptions.py --model $MODEL --n_per_scenario 5 \
    > $LOG_DIR/$MODEL_TAG.log 2>&1
  echo "Done $MODEL at $(date)"
done

echo "ALL MODELS DONE"
