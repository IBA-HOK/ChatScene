"""Run Scenic code generation for a small subset of descriptions.

This uses the existing retrieval database and a small subset of descriptions
to demonstrate the full ChatScene pipeline.
"""
import argparse
import json
import os
import pickle
import re
import sys
import time
from pathlib import Path

# Add parent dir to path for retrieval modules
sys.path.insert(0, "/home/hokuto/chatScene/ChatScene/retrieve")

# We re-implement minimal helpers since architecture.py uses openai
import openai


SYSTEM_PROMPT = '''Your goal is to assist me in writing snippets using Scenic 2.1 for CARLA simulation. Scenic is a domain-specific probabilistic programming language designed for modeling environments in cyber-physical systems like robots and autonomous vehicles. Please adhere strictly to the Scenic 2.1 API, avoiding the use of any non-existent APIs or the Python random package.'''

BEHAVIOR_PROMPT = """Now, your task is to help write part of the Scenic code for defining the adversarial behavior of an agent given the corresponding description. Here are some related description-snippet pairs:
{content}
Now, provide the snippet for the following description. Note that if there is already one in the example that matches the description, directly return snippet. Otherwise, please construct the snippet following the same format as above. Note that the name of the behavior function should always be AdvBehavior, and any hyperparameter should be defined as param OPT_xxx, and use it inside the behavior function with globalParameters.OPT_xxx. Please strictly follow the syntax as those used in the examples.

Description: {current_description}"""


def chat(client, model, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model, messages=messages, temperature=0,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"  [retry {attempt+1}] {type(e).__name__}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None


def extract_scenic(text):
    pattern = r"```scenic(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[0].strip()
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--n_subsample", type=int, default=2,
                    help="number of descriptions to sample for code generation")
    ap.add_argument("--descriptions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    ap.add_argument("--extractions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/extractions")
    ap.add_argument("--out_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/scenic_code")
    ap.add_argument("--scenario_filter", default="StraightObstacle",
                    help="only generate code for this base scenario")
    args = ap.parse_args()

    # Load database
    db_path = "/home/hokuto/chatScene/ChatScene/retrieve/database_v1.pkl"
    with open(db_path, "rb") as f:
        db = pickle.load(f)
    behavior_descs = db["behavior"]["description"]
    behavior_snips = db["behavior"]["snippet"]

    # We use simple keyword overlap as retrieval (skip sentence-transformer)
    def simple_retrieve(query, descs, snips, k=3):
        qwords = set(query.lower().split())
        scored = []
        for i, d in enumerate(descs):
            dwords = set(d.lower().split())
            j = len(qwords & dwords) / max(1, len(qwords | dwords))
            scored.append((j, i))
        scored.sort(reverse=True)
        idxs = [i for _, i in scored[:k]]
        return [descs[i] for i in idxs], [snips[i] for i in idxs]

    in_dir = Path(args.descriptions_dir) / args.model.replace(":", "_")
    out_dir = Path(args.out_dir) / args.model.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    desc_file = in_dir / f"{args.scenario_filter}.json"
    data = json.load(open(desc_file))
    descriptions = data["descriptions"][:args.n_subsample]

    client = openai.OpenAI(base_url=args.ollama_url, api_key="ollama", timeout=600)

    for i, desc in enumerate(descriptions):
        print(f"\n=== [{args.scenario_filter} #{i+1}] ===")
        print(f"Description: {desc[:120]}...")

        # Retrieve top-k behavior examples
        top_descs, top_snips = simple_retrieve(desc, behavior_descs, behavior_snips, k=args.topk)
        print(f"Retrieved: {top_descs}")

        content = ""
        for j in range(args.topk):
            content += f"Description: {top_descs[j]}\nSnippet:\n```scenic\n{top_snips[j]}```\n"

        user_prompt = BEHAVIOR_PROMPT.format(content=content, current_description=desc)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        resp = chat(client, args.model, messages)
        if not resp:
            print(f"  FAIL")
            continue
        code = extract_scenic(resp)
        print(f"\nGenerated code (first 400 chars):\n{code[:400]}...")

        # Save
        out_file = out_dir / f"{args.scenario_filter}_{i+1}.scenic"
        with open(out_file, "w") as f:
            f.write(f"'''{desc}'''\n")
            f.write(code)
        # Also save the raw response
        with open(out_file.with_suffix(".raw.txt"), "w") as f:
            f.write(resp)


if __name__ == "__main__":
    main()
