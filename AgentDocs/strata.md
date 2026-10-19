# Strata qwen3.8-flash-next 連携

## 概要
ChatScene シナリオ生成を GPT-4o (OpenAI) から Strata 上の `qwen3.8-flash-next-iq3_s` へ移行。OpenAI 互換 API `http://127.0.0.1:8080/v1` 経由。

## 変更点
- `retrieve/architecture.py`: provider 分岐 (`strata|openai|local|auto`)、 `STRATA_BASE_URL`/`STRATA_API_KEY` env 対応、 `enable_thinking` 制御、 hardcoded OpenAI key 削除、 `qwen` 推論時の `reasoning_content` fallback
- `retrieve/utils.py`: `extract_scenic_code` fence 耐性 (scenic/python/bare)・`pdb` 削除、 `generate_code_snippet` retry + fallback、 `retrieve_topk` CPU fallback (RTX 5080 sm_120 互換)、 `save_scenic_code` verify モード `parse|scenic|none`
- `retrieve/retrieve.py`: CLI 拡張 `--provider/--fallback-models/--verify/--ban-towns/--enable-thinking/--base-url/--api-key`、 `main()` 分離、 `RETRIEVE_DEVICE=cpu` CPU fallback
- `retrieve/retrieve_dynamic.py`: AGENTS.md 準拠 wrapper (`--model qwen3.8-flash-next-iq3_s --provider strata ...`)
- `.env.example` + `.gitignore` (.env 無視)

## 起動
```
export PATH=/home/hokuto/miniforge3/envs/chatscene/bin:$PATH
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy RETRIEVE_DEVICE=cpu HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python retrieve/retrieve_dynamic.py --model qwen3.8-flash-next-iq3_s --provider strata --fallback-models "" --verify parse --ban-towns "" --topk 3 --use_llm
bash scripts/paper_method_regen.sh
```

## 検証
- `curl http://127.0.0.1:8080/v1/models | grep qwen`
- `python -c "from retrieve.architecture import LLMChat; c=LLMChat('qwen3.8-flash-next-iq3_s', provider='strata'); print(c.generate([...]))"`
