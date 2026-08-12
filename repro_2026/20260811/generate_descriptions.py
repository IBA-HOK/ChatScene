"""Generate scenario descriptions for each base scenario using Ollama LLMs.

Reproduction of the description generation step from ChatScene (2405.14062),
replacing GPT-4 with local Ollama models:
  - gemma4:e4b, gemma4:e2b, gemma4:12b, qwen3.5:4b
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import openai

BASE_SCENARIOS = [
    ("StraightObstacle",
     "Provide a description of a safety-critical scenario where the ego vehicle is driving on a straight road. "
     "The adversarial agent (pedestrian, car, cyclist, or motorcycle) should perform an unexpected behavior "
     "that may lead to a collision. Keep it to one or two short sentences."),
    ("TurningObstacle",
     "Provide a description of a safety-critical scenario where the ego vehicle is turning at an intersection. "
     "The adversarial agent (pedestrian, car, cyclist, or motorcycle) should perform an unexpected behavior "
     "that may lead to a collision. Keep it to one or two short sentences."),
    ("LaneChanging",
     "Provide a description of a safety-critical scenario where the ego vehicle is changing lanes. "
     "The adversarial agent (pedestrian, car, cyclist, or motorcycle) should perform an unexpected behavior "
     "that may lead to a collision. Keep it to one or two short sentences."),
    ("VehiclePassing",
     "Provide a description of a safety-critical scenario where the ego vehicle is passing a parked vehicle "
     "using the opposite lane. The adversarial agent (pedestrian, car, cyclist, or motorcycle) should perform "
     "an unexpected behavior that may lead to a collision. Keep it to one or two short sentences."),
    ("RedLightRunning",
     "Provide a description of a safety-critical scenario where a vehicle runs a red light at an intersection "
     "while the ego vehicle is proceeding through. The adversarial agent should perform an unexpected behavior "
     "that may lead to a collision. Keep it to one or two short sentences."),
    ("UnprotectedLeftTurn",
     "Provide a description of a safety-critical scenario where the ego vehicle is making an unprotected left "
     "turn at an intersection. The adversarial agent (pedestrian, car, cyclist, or motorcycle) should perform "
     "an unexpected behavior that may lead to a collision. Keep it to one or two short sentences."),
    ("RightTurn",
     "Provide a description of a safety-critical scenario where the ego vehicle is making a right turn at "
     "an intersection. The adversarial agent (pedestrian, car, cyclist, or motorcycle) should perform an "
     "unexpected behavior that may lead to a collision. Keep it to one or two short sentences."),
    ("CrossingNegotiation",
     "Provide a description of a safety-critical scenario where the ego vehicle is negotiating crossing "
     "traffic at an intersection. The adversarial agent (pedestrian, car, cyclist, or motorcycle) should "
     "perform an unexpected behavior that may lead to a collision. Keep it to one or two short sentences."),
]


def chat(client, model, system, user, temperature=0.7, max_retries=3):
    """Call Ollama OpenAI-compatible API with retry."""
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
            content = r.choices[0].message.content or ""
            content = content.strip()
            if content:
                return content
            print(f"  [retry {attempt+1}/{max_retries}] empty response", flush=True)
        except Exception as e:
            print(f"  [retry {attempt+1}/{max_retries}] {type(e).__name__}: {e}", flush=True)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"All retries failed for {model}")


def extract_description(text):
    """Try to extract the actual scenario description from the LLM output."""
    text = text.strip()

    # remove code fences
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")

    # try numbered list (1. ... 2. ...)
    numbered = re.findall(r"\d+\.\s+(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL)
    if numbered:
        return [s.strip().split("\n")[0] for s in numbered if s.strip()]

    # try bulleted list (- ... or * ...)
    bulleted = re.findall(r"[-*]\s+(.+?)(?=\n[-*]|\Z)", text, re.DOTALL)
    if bulleted:
        return [s.strip().split("\n")[0] for s in bulleted if s.strip()]

    # try paragraph - one sentence per line (must have substantial content)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip() and len(ln.strip()) > 30]
    if lines:
        return lines

    # last resort - return entire text
    return [text] if text else [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Ollama model name, e.g. gemma4:12b")
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--n_per_scenario", type=int, default=5)
    ap.add_argument("--out_dir", default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--seed_offset", type=int, default=0,
                    help="offset added to each scenario index when calling; useful for varying temperature")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) / args.model.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "generation.log"
    log_f = open(log_path, "w", buffering=1)

    client = openai.OpenAI(base_url=args.ollama_url, api_key="ollama", timeout=600)

    system_prompt = (
        "You are an expert in autonomous driving safety. Generate concise, "
        "diverse, and realistic safety-critical driving scenario descriptions."
    )

    summary = {}
    for sidx, (name, user_prompt) in enumerate(BASE_SCENARIOS):
        out_file = out_dir / f"{name}.json"
        if out_file.exists():
            with open(out_file) as f:
                existing = json.load(f)
            non_empty = sum(1 for d in existing.get("descriptions", []) if d and d.strip())
            if non_empty >= args.n_per_scenario:
                print(f"[skip] {name} already has {non_empty} non-empty descriptions", flush=True)
                summary[name] = non_empty
                continue

        descriptions = []
        attempts = 0
        for i in range(args.n_per_scenario):
            seed_prompt = (
                f"{user_prompt}\n\n"
                f"Generate description #{i+1} only. Output just the description, no numbering, no preamble."
            )
            try:
                txt = chat(
                    client, args.model, system_prompt, seed_prompt,
                    temperature=args.temperature + (args.seed_offset + i) * 0.05,
                )
                log_f.write(f"\n[{name} #{i+1}]\n{txt}\n---\n")
                # take the longest paragraph if multiple
                cand = extract_description(txt)
                # pick the longest non-trivial one
                cand = [c for c in cand if len(c) > 30]
                if not cand:
                    cand = [txt]
                # de-duplicate vs. existing
                pick = None
                for c in cand:
                    if c not in descriptions and not any(c[:80] in d or d[:80] in c for d in descriptions):
                        pick = c
                        break
                if pick is None:
                    pick = cand[0]
                descriptions.append(pick)
                print(f"  [{name} #{i+1}] ok ({len(pick)} chars)", flush=True)
            except Exception as e:
                print(f"  [{name} #{i+1}] FAIL: {e}", flush=True)
                log_f.write(f"[{name} #{i+1}] FAIL: {e}\n")
            attempts += 1

        with open(out_file, "w") as f:
            json.dump({
                "model": args.model,
                "base_scenario": name,
                "prompt": user_prompt,
                "descriptions": descriptions,
            }, f, indent=2)
        summary[name] = len(descriptions)
        print(f"[done] {name}: {len(descriptions)} descriptions", flush=True)

    log_f.close()
    print("\nSummary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
