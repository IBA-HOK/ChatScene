"""Score descriptions per model (run individually for reliability)."""
import argparse
import json
import os
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


def chat(client, model, user, max_retries=3, timeout=90):
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
                timeout=timeout,
            )
            content = (r.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception as e:
            print(f"  [retry {attempt+1}] {type(e).__name__}: {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    return None


def parse_scores(text):
    out = {"safety_criticality": None, "specificity": None, "realism": None}
    if not text:
        return out
    for key, label in [
        ("safety_criticality", r"Safety[-\s]*criticality"),
        ("specificity", r"Specificity"),
        ("realism", r"Realism"),
    ]:
        m = re.search(label + r"\s*[:\-]\s*(\d)", text, re.IGNORECASE)
        if m:
            out[key] = int(m.group(1))
    return out


def score_one_model(target_model, judge_model, ollama_url, descriptions_dir, out_path, include_baseline=False, baseline_file=None):
    client = openai.OpenAI(base_url=ollama_url, api_key="ollama", timeout=90)
    all_descs = {}
    base_dir = Path(descriptions_dir)
    model_dir = base_dir / target_model.replace(":", "_")
    if model_dir.exists():
        all_descs[target_model] = []
        for jf in sorted(model_dir.glob("*.json")):
            data = json.load(open(jf))
            for i, d in enumerate(data["descriptions"]):
                if d.strip():
                    all_descs[target_model].append((data["base_scenario"], i, d))

    if include_baseline and baseline_file and Path(baseline_file).exists():
        lines = [l.strip() for l in Path(baseline_file).read_text().split("\n") if l.strip()]
        base_scenarios = ["StraightObstacle", "TurningObstacle", "LaneChanging",
                          "VehiclePassing", "RedLightRunning", "UnprotectedLeftTurn",
                          "RightTurn", "CrossingNegotiation"]
        all_descs["GPT4_baseline"] = []
        for i, name in enumerate(base_scenarios):
            chunk = lines[i*5:(i+1)*5]
            for j, d in enumerate(chunk):
                all_descs["GPT4_baseline"].append((name, j, d))

    # Load existing scores if any
    if Path(out_path).exists():
        existing = json.load(open(out_path))
    else:
        existing = {}

    for model_name, items in all_descs.items():
        if model_name not in existing:
            existing[model_name] = []
        out_records = list(existing[model_name])
        for scenario, idx, desc in items:
            if any(x["scenario"] == scenario and x["idx"] == idx for x in out_records):
                continue
            prompt = JUDGE_PROMPT.format(description=desc)
            resp = chat(client, judge_model, prompt)
            if not resp:
                print(f"  [{model_name} {scenario} #{idx+1}] still empty", flush=True)
                continue
            scores = parse_scores(resp)
            out_records.append({
                "scenario": scenario, "idx": idx, "description": desc,
                "scores": scores, "raw": resp,
            })
            existing[model_name] = out_records
            # save incrementally
            with open(out_path, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"  [{model_name} {scenario} #{idx+1}] sc={scores['safety_criticality']} sp={scores['specificity']} re={scores['realism']}", flush=True)

    return existing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="judge model (e.g. gemma4:12b)")
    ap.add_argument("--target_model", required=True,
                    help="model whose descriptions are being scored")
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--descriptions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    ap.add_argument("--out_path",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/judge_scores.json")
    ap.add_argument("--include_baseline", action="store_true")
    ap.add_argument("--baseline_file",
                    default="/home/hokuto/chatScene/ChatScene/retrieve/scenario_descriptions.txt")
    args = ap.parse_args()

    result = score_one_model(args.target_model, args.model, args.ollama_url,
                             args.descriptions_dir,
                             args.out_path, args.include_baseline, args.baseline_file)

    # summary
    summary = {}
    for model_name, items in result.items():
        sc = [x["scores"]["safety_criticality"] for x in items if x["scores"]["safety_criticality"] is not None]
        sp = [x["scores"]["specificity"] for x in items if x["scores"]["specificity"] is not None]
        re_ = [x["scores"]["realism"] for x in items if x["scores"]["realism"] is not None]
        summary[model_name] = {
            "n_scored": len(items),
            "avg_safety_criticality": round(sum(sc)/len(sc), 2) if sc else None,
            "avg_specificity": round(sum(sp)/len(sp), 2) if sp else None,
            "avg_realism": round(sum(re_)/len(re_), 2) if re_ else None,
        }
    print("\nSummary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
