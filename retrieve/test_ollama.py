"""Quick connectivity test for Ollama's OpenAI-compatible API."""
import os
import argparse
from dotenv import load_dotenv
import openai

load_dotenv()

parser = argparse.ArgumentParser(description="Test Ollama OpenAI-compatible API.")
parser.add_argument('--model', type=str, default='llama3.2', help='Ollama model name')
parser.add_argument('--ollama_url', type=str, default=None, help="Ollama base URL (default: OLLAMA_BASE_URL env var or http://localhost:11434/v1)")
args = parser.parse_args()

ollama_url = args.ollama_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
api_key = os.environ.get("OLLAMA_API_KEY", "ollama")

print(f"Connecting to Ollama at: {ollama_url}")
print(f"Model: {args.model}")

client = openai.OpenAI(base_url=ollama_url, api_key=api_key, timeout=120)

try:
    response = client.chat.completions.create(
        model=args.model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in one word."},
        ],
        temperature=0,
    )
    print("\nResponse:")
    print(response.choices[0].message.content)
    print("\nOllama API is working correctly.")
except Exception as e:
    print(f"\nError: {type(e).__name__}: {e}")
    print("\nTroubleshooting:")
    print("- Ensure 'ollama serve' is running")
    print("- Ensure the model is pulled: ollama pull " + args.model)
    print("- Verify the URL ends with /v1")
