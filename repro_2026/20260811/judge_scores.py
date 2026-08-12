"""Have an LLM judge (gemma4:12b) rate each description on safety-criticality.

We use gemma4:12b as a 'judge' model to score descriptions from all 4 LLMs.
This is similar to using GPT-4 as judge in LLM evaluation.
"""
import argparse
import json
import re
import time
from pathlib import Path

import openai

JUDGE_PROMPT = """You are evaluating the quality of a safety-critical driving scenario description.

Score the following description on three criteria (each 0-5):
1. **Safety-criticality** (0-5): Does it describe a genuinely dangerous situation that could lead to a collision?
2. **Specificity** (0-5): Are the agents, behaviors, and locations clearly described?
3. **Realism** (0-5): Is the scenario plausible in real-world driving?

Description: "{description}"

Respond with exactly three lines in this format:
Safety-criticality: <score>
Specificity: <score>
Realism: <score>"""


def chat(client, model, user, max_retries=3):
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content":
                     "You are an expert judge of autonomous-driving safety scenarios."},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
            content = (r.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception as e:
            print(f"  [retry {attempt+1}] {type(e).__name__}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None


def parse_scores(text):
    text = text.strip()
    out = {"safety_criticality": None, "specificity": None, "realism": None}
    for key, label in [
        ("safety_criticality", r"Safety[-\s]*criticality"),
        ("specificity", r"Specificity"),
        ("realism", r"Realism"),
    ]:
        m = re.search(label + r"\s*[:\-]\s*(\d)", text, re.IGNORECASE)
        if m:
            out[key] = int(m.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge_model", default="gemma4:12b")
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--descriptions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    ap.add_argument("--out_path",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/judge_scores.json")
    ap.add_argument("--include_baseline", action="store_true")
    ap.add_argument("--baseline_file",
                    default="/home/hokuto/chatScene/ChatScene/retrieve/scenario_descriptions.txt")
    args = ap.parse_args()

    client = openai.OpenAI(base_url=args.ollama_url, api_key="ollama", timeout=120)

    all_descs = {}  # model -> [(scenario, idx, desc)]
    base_dir = Path(args.descriptions_dir)
    for model_dir in sorted(base_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        all_descs[model_name] = []
        for jf in sorted(model_dir.glob("*.json")):
            data = json.load(open(jf))
            for i, d in enumerate(data["descriptions"]):
                if d.strip():
                    all_descs[model_name].append((data["base_scenario"], i, d))

    if args.include_baseline:
        bp = Path(args.baseline_file)
        if bp.exists():
            lines = [l.strip() for l in bp.read_text().split("\n") if l.strip()]
            base_scenarios = ["StraightObstacle", "TurningObstacle", "LaneChanging",
                              "VehiclePassing", "RedLightRunning", "UnprotectedLeftTurn",
                              "RightTurn", "CrossingNegotiation"]
            all_descs["GPT4_baseline"] = []
            for i, name in enumerate(base_scenarios):
                chunk = lines[i*5:(i+1)*5]
                for j, d in enumerate(chunk):
                    all_descs["GPT4_baseline"].append((name, j, d))

    out = {}
    total = 0
    success = 0
    for model_name, items in all_descs.items():
        out[model_name] = []
        for scenario, idx, desc in items:
            total += 1
            prompt = JUDGE_PROMPT.format(description=desc)
            resp = chat(client, args.judge_model, prompt)
            if not resp:
                continue
            scores = parse_scores(resp)
            success += 1
            out[model_name].append({
                "scenario": scenario, "idx": idx, "description": desc,
                "scores": scores, "raw": resp,
            })
        print(f"{model_name}: scored {len(out[model_name])}/{len(items)}", flush=True)

    Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {args.out_path}")
    print(f"Total: {success}/{total} successful")


if __name__ == "__main__":
    main()
