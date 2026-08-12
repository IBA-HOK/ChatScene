"""Extract Adversarial Object / Behavior / Geometry / Spawn Position from descriptions.

This is the second step of the ChatScene pipeline. We use the extraction prompt from
the original repo, but adapted to work with any Ollama-served LLM.
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

import openai

# This is the extraction prompt from the original ChatScene repo.
EXTRACTION_PROMPT = """Your task is to decompose full descriptions of safety-critical scenarios into sub-descriptions for the following distinct components:

Adversarial Object: Indicate the type of the adversarial agent, restricted to Car, Pedestrian, Bicycle, or Motorcycle.
Behavior: Describe the behavior of the adversarial agent.
Geometry: Specify the road condition where the scenario occurs (e.g., straight road, four-way intersection), including traffic light conditions.
Spawn Position: Indicate the initial relative position of the adversarial object to the ego vehicle, including any potential obstructions like a vending machine.

Here are some examples:
Scenario: The ego vehicle is driving on a straight road, and the car in front brakes suddenly as the ego approaches.
Adversarial Object: Car
Behavior: The adversarial car suddenly brakes as the ego approaches.
Geometry: A straight road.
Spawn Position: The adversarial agent is directly in front of the ego vehicle on the same straight road, heading in the same direction.

Scenario: The ego vehicle attempts a right turn at a four-way intersection, and an adversarial pedestrian crosses the road and suddenly stops.
Adversarial Object: Pedestrian
Behavior: The adversarial pedestrian deliberately steps onto the road in front of the ego vehicle.
Geometry: The ego vehicle drives across a four-way intersection.
Spawn Position: The adversarial agent is on the right front of the ego vehicle at the end of the ego's initial lane for crossing.

Scenario: The ego vehicle navigates around a parked car, and an oncoming car suddenly turns into its path.
Adversarial Object: Car
Behavior: The adversarial car suddenly turns into the ego's path.
Geometry: The ego vehicle is positioned on a two-lane road with traffic flowing in opposite directions.
Spawn Position: The adversarial agent comes from the near opposite oncoming lane, with a parked car blocking the ego vehicle's lane.

Scenario: The ego vehicle is traveling along a straight road when a pedestrian, initially hidden behind a bus stop on the sidewalk to the right, unexpectedly dashes onto the road directly in front of the ego vehicle and comes to an abrupt stop.
Adversarial Object: Pedestrian
Behavior: The adversarial pedestrian suddenly sprints from the right, stopping abruptly in front of the ego vehicle.
Geometry: A straight road.
Spawn Position: The adversarial agent spawns from behind a bus stop on the right front of the ego vehicle on the same straight road for crossing.

Scenario: The ego vehicle is changing to the right lane when an adversarial vehicle approaches rapidly from the right.
Adversarial Object: Car
Behavior: The adversarial car approaches rapidly.
Geometry: The ego vehicle is placed in a straight lane that includes a right lane.
Spawn Position: The adversarial car drives straight from the rear right of the ego.

Scenario: The ego vehicle is turning right at an intersection, and a crossing car from the left violates the red light and suddenly brakes.
Adversarial Object: Car
Behavior: The adversarial car suddenly brakes near the ego vehicle.
Geometry: The ego vehicle drives straight across a four-way signalized intersection; the light is red for the adversarial agent.
Spawn Position: The adversarial car is crossing the intersection from the left.

Now, extract the adversarial behavior, geometry and spawn position in the same format from the following scenario, notice Adversarial Object is restricted to Car, Pedestrian, Bicycle, or Motorcycle.
Scenario: {scenario}"""


def chat(client, model, user, max_retries=3):
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content":
                     "You are an expert at decomposing driving scenarios into structured components."},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [retry {attempt+1}/{max_retries}] {type(e).__name__}: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"All retries failed for {model}")


def parse_extraction(text):
    """Try to extract Adversarial Object / Behavior / Geometry / Spawn Position from output."""
    text = text.strip()
    # Strip code fences if any
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")
    # Strip leading markdown bold markers
    text = re.sub(r"\*\*", "", text)

    out = {
        "Adversarial Object": "",
        "Behavior": "",
        "Geometry": "",
        "Spawn Position": "",
    }
    pat = re.compile(
        r"Adversarial\s*Object\s*:\s*(.+?)(?=Behavior\s*:|Geometry\s*:|Spawn\s*Position\s*:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    pat_b = re.compile(
        r"Behavior\s*:\s*(.+?)(?=Geometry\s*:|Spawn\s*Position\s*:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    pat_g = re.compile(
        r"Geometry\s*:\s*(.+?)(?=Spawn\s*Position\s*:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    pat_s = re.compile(
        r"Spawn\s*Position\s*:\s*(.+?)$",
        re.DOTALL | re.IGNORECASE,
    )
    m = pat.search(text)
    if m: out["Adversarial Object"] = m.group(1).strip().strip("*- ")
    m = pat_b.search(text)
    if m: out["Behavior"] = m.group(1).strip().strip("*- ")
    m = pat_g.search(text)
    if m: out["Geometry"] = m.group(1).strip().strip("*- ")
    m = pat_s.search(text)
    if m: out["Spawn Position"] = m.group(1).strip().strip("*- ")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--in_dir", default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    ap.add_argument("--out_dir", default="/home/hokuto/chatScene/ChatScene/repro_2026/extractions")
    args = ap.parse_args()

    in_dir = Path(args.in_dir) / args.model.replace(":", "_")
    out_dir = Path(args.out_dir) / args.model.replace(":", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    client = openai.OpenAI(base_url=args.ollama_url, api_key="ollama", timeout=600)

    total = 0
    success = 0
    for jf in sorted(in_dir.glob("*.json")):
        if jf.name == "generation.log":
            continue
        data = json.load(open(jf))
        scenario_name = data["base_scenario"]
        descriptions = data["descriptions"]

        out_records = []
        for i, desc in enumerate(descriptions):
            total += 1
            user_prompt = EXTRACTION_PROMPT.format(scenario=desc)
            try:
                resp = chat(client, args.model, user_prompt)
                parsed = parse_extraction(resp)
                ok = bool(parsed["Adversarial Object"] and parsed["Behavior"] and
                         parsed["Geometry"] and parsed["Spawn Position"])
                if ok:
                    success += 1
                out_records.append({
                    "idx": i,
                    "description": desc,
                    "extraction_raw": resp,
                    "extraction": parsed,
                    "success": ok,
                })
                print(f"  [{scenario_name} #{i+1}] {'ok' if ok else 'partial'}", flush=True)
            except Exception as e:
                print(f"  [{scenario_name} #{i+1}] FAIL: {e}", flush=True)
                out_records.append({
                    "idx": i,
                    "description": desc,
                    "extraction_raw": "",
                    "extraction": {},
                    "success": False,
                    "error": str(e),
                })

        out_file = out_dir / f"{scenario_name}.json"
        with open(out_file, "w") as f:
            json.dump({
                "model": args.model,
                "base_scenario": scenario_name,
                "extractions": out_records,
            }, f, indent=2)
        print(f"[done] {scenario_name}: {sum(r['success'] for r in out_records)}/{len(out_records)} ok", flush=True)

    print(f"\nTotal: {success}/{total} successful extractions", flush=True)


if __name__ == "__main__":
    main()
