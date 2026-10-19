from __future__ import annotations
import os
import openai

STRATA_DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
STRATA_DEFAULT_MODEL = "qwen3.8-flash-next-iq3_s"


def _resolve_api_key(explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    for k in ("STRATA_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(k)
        if v:
            return v
    return "none"


def _resolve_base_url(explicit: str | None, provider: str) -> str | None:
    if explicit is not None:
        return explicit
    if provider in ("strata", "auto"):
        return os.environ.get("STRATA_BASE_URL", STRATA_DEFAULT_BASE_URL)
    if provider == "openai":
        return os.environ.get("OPENAI_BASE_URL")
    return None


class LLMChat():
    """
    Unified LLM wrapper for ChatScene scenario generation.

    Providers:
      - strata : OpenAI-compatible endpoint (qwen3.8-flash-next via Strata). Default.
      - openai : Official OpenAI API (gpt-4o etc.)
      - auto   : strata if STRATA_BASE_URL set or model contains qwen/strata, else openai-like
      - local  : HuggingFace transformers pipeline
    """
    def __init__(
        self,
        model_name: str = STRATA_DEFAULT_MODEL,
        provider: str = "auto",
        base_url: str | None = None,
        api_key: str | None = None,
        enable_thinking: bool = False,
        fallback_models: list[str] | None = None,
    ):
        super(LLMChat, self).__init__()
        self.model_name = model_name
        self.provider = provider
        self.enable_thinking = enable_thinking
        self.fallback_models = fallback_models or []

        p = provider.lower() if isinstance(provider, str) else "auto"
        if p == "auto":
            low = model_name.lower()
            if "qwen" in low or "strata" in low or "flash" in low:
                p = "strata"
            elif low.startswith("gpt") or "openai" in low:
                p = "openai"
            else:
                p = "strata"
        self.provider = p

        if self.provider in ("strata", "openai", "auto"):
            resolved_base = _resolve_base_url(base_url, self.provider)
            resolved_key = _resolve_api_key(api_key)
            kwargs: dict = {"api_key": resolved_key}
            if resolved_base:
                kwargs["base_url"] = resolved_base
            self.client = openai.OpenAI(**kwargs)
            self.pipeline = None
        elif self.provider == "local":
            import torch
            import transformers
            self.client = None
            self.pipeline = transformers.pipeline(
                "text-generation",
                model=model_name,
                model_kwargs={"torch_dtype": torch.bfloat16},
                device="cuda",
            )
        else:
            raise ValueError(f"Unknown provider {provider!r}, expected strata|openai|local|auto")

    def _extra_body(self) -> dict | None:
        if self.provider in ("strata", "auto") and not self.enable_thinking:
            return {"chat_template_kwargs": {"enable_thinking": False}}
        if self.provider == "strata" and self.enable_thinking:
            return {"chat_template_kwargs": {"enable_thinking": True}}
        return None

    def generate(self, messages, max_new_tokens: int = 500, **kwargs):
        if self.client is not None:
            create_kwargs: dict = {
                "model": self.model_name,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0),
            }
            if max_new_tokens is not None:
                create_kwargs["max_tokens"] = max_new_tokens
            eb = self._extra_body()
            if eb is not None and "extra_body" not in kwargs:
                create_kwargs["extra_body"] = eb
            elif "extra_body" in kwargs:
                create_kwargs["extra_body"] = kwargs["extra_body"]
            for k in ("top_p", "top_k", "seed", "stop"):
                if k in kwargs:
                    create_kwargs[k] = kwargs[k]

            response = self.client.chat.completions.create(**create_kwargs)
            msg = response.choices[0].message
            content = getattr(msg, "content", None)
            if content is None:
                content = getattr(msg, "reasoning_content", None) or ""
            return content
        else:
            outputs = self.pipeline(
                messages,
                max_new_tokens=max_new_tokens,
                do_sample=False
            )
            try:
                return outputs[0]["generated_text"][-1]
            except Exception:
                return str(outputs[0]) if outputs else ""
