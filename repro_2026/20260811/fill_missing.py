"""Fill in any empty descriptions for a single model/scenario combination."""
import argparse
import json
import re
import time
from pathlib import Path

import openai


def chat(client, model, user, max_retries=5):
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content":
                     "You are an expert in autonomous driving safety. Generate concise, "
                     "diverse, and realistic safety-critical driving scenario descriptions."},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
            )
            content = (r.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception as e:
            print(f"  [retry {attempt+1}/{max_retries}] {type(e).__name__}: {e}", flush=True)
        time.sleep(5 * (attempt + 1))
    return None


def extract_description(text):
    text = text.strip()
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")
    numbered = re.findall(r"\d+\.\s+(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL)
    if numbered:
        return [s.strip().split("\n")[0] for s in numbered if s.strip()]
    bulleted = re.findall(r"[-*]\s+(.+?)(?=\n[-*]|\Z)", text, re.DOTALL)
    if bulleted:
        return [s.strip().split("\n")[0] for s in bulleted if s.strip()]
    lines = [ln.strip() for ln in text.split("\n") if ln.strip() and len(ln.strip()) > 30]
    if lines:
        return lines
    return [text] if text else [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--scenario", required=True,
                    help="scenario name e.g. RightTurn")
    ap.add_argument("--descriptions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    args = ap.parse_args()

    in_dir = Path(args.descriptions_dir) / args.model.replace(":", "_")
    fp = in_dir / f"{args.scenario}.json"
    data = json.load(open(fp))

    descs = data["descriptions"]
    user_prompt = data["prompt"]
    print(f"Filling missing slots for {args.scenario} ({sum(1 for d in descs if d.strip())}/{len(descs)} non-empty)")

    client = openai.OpenAI(base_url=args.ollama_url, api_key="ollama", timeout=600)

    for i in range(len(descs)):
        if descs[i].strip():
            continue
        seed = (
            f"{user_prompt}\n\n"
            f"Generate description #{i+1} only. Output just the description, no numbering, no preamble."
        )
        result = chat(client, args.model, seed)
        if result:
            cands = extract_description(result)
            cands = [c for c in cands if len(c) > 30]
            pick = cands[0] if cands else result
            descs[i] = pick
            print(f"  slot {i}: filled ({len(pick)} chars)")
        else:
            print(f"  slot {i}: still empty")

    data["descriptions"] = descs
    with open(fp, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Done. Final: {sum(1 for d in descs if d.strip())}/{len(descs)} non-empty")


if __name__ == "__main__":
    main()
