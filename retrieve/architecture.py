import os
import openai
import torch
import transformers
from dotenv import load_dotenv

load_dotenv()

def _truncate_text(text, max_len=800):
    """Truncate long text for debug output."""
    text = str(text)
    if len(text) <= max_len:
        return text
    head = max_len // 2
    tail = max_len - head
    return text[:head] + f"\n... ({len(text) - max_len} characters omitted) ...\n" + text[-tail:]

class LLMChat():
    def __init__(self, model_name='meta-llama/Meta-Llama-3-8B-Instruct', ollama_base_url=None, timeout=600):
        super(LLMChat, self).__init__()
        self.model_name = model_name
        self.use_openai_client = False
        if ollama_base_url:
            # Ollama OpenAI-compatible API endpoint
            print(f"[LLMChat] Using Ollama OpenAI-compatible API: {ollama_base_url} (model: {model_name})")
            self.client = openai.OpenAI(
                base_url=ollama_base_url,
                api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
                timeout=timeout,
            )
            self.use_openai_client = True
        elif model_name.startswith('gpt'):
            if not os.environ.get("OPENAI_API_KEY"):
                raise ValueError("OPENAI_API_KEY is not set. Please configure it in the .env file.")
            print(f"[LLMChat] Using OpenAI API (model: {model_name})")
            self.client = openai.OpenAI(timeout=timeout)
            self.use_openai_client = True
        else:
            print(f"[LLMChat] Using local transformers pipeline (model: {model_name})")
            self.pipeline = transformers.pipeline(
                "text-generation",
                model=model_name,
                model_kwargs={"torch_dtype": torch.bfloat16},
                device="cuda",
            )

    def generate(self, messages, max_new_tokens = 500):
        if self.use_openai_client:
            try:
                print(f"\n[LLMChat] ===== Sending request to {self.model_name} =====")
                for i, msg in enumerate(messages):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    print(f"\n[LLMChat] Message {i} (role: {role}):")
                    print(_truncate_text(content))
                print(f"\n[LLMChat] Waiting for response...")
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0,
                )
                response_text = response.choices[0].message.content
                print(f"\n[LLMChat] ===== Received response from {self.model_name} =====")
                print(_truncate_text(response_text))
                print(f"\n[LLMChat] ===== End of response =====\n")
                return response_text
            except openai.APIConnectionError as e:
                raise ConnectionError(
                    f"Failed to connect to the API endpoint. "
                    f"If you are using Ollama, make sure the server is running with 'ollama serve' "
                    f"and the model '{self.model_name}' is pulled. Original error: {e}"
                ) from e
        else:
            outputs = self.pipeline(
                messages,
                max_new_tokens=max_new_tokens,
                do_sample=False
            )
            return outputs[0]["generated_text"][-1]
