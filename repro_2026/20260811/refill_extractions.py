"""Re-run extraction for partial extractions only (where success=False)."""
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
                     "You are an expert at decomposing driving scenarios into structured components. "
                     "Always respond with all four components: Adversarial Object, Behavior, Geometry, Spawn Position."},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
            content = (r.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception as e:
            print(f"  [retry {attempt+1}/{max_retries}] {type(e).__name__}: {e}", flush=True)
        time.sleep(2 * (attempt + 1))
    return None


def parse_extraction(text):
    text = text.strip()
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("```", "")
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


PROMPT_TEMPLATE = """Decompose this safety-critical driving scenario into exactly four lines:

Adversarial Object: <Car|Pedestrian|Bicycle|Motorcycle>
Behavior: <what the adversarial agent does>
Geometry: <road condition>
Spawn Position: <where the adversarial agent starts>

Scenario: {scenario}

Output exactly those four lines."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ollama_url", default="http://localhost:11434/v1")
    ap.add_argument("--extractions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/extractions")
    args = ap.parse_args()

    in_dir = Path(args.extractions_dir) / args.model.replace(":", "_")
    client = openai.OpenAI(base_url=args.ollama_url, api_key="ollama", timeout=600)

    for jf in sorted(in_dir.glob("*.json")):
        data = json.load(open(jf))
        changed = False
        for e in data["extractions"]:
            if e["success"]:
                continue
            prompt = PROMPT_TEMPLATE.format(scenario=e["description"])
            resp = chat(client, args.model, prompt)
            if not resp:
                print(f"  [{data['base_scenario']} #{e['idx']+1}] still empty")
                continue
            parsed = parse_extraction(resp)
            ok = bool(parsed["Adversarial Object"] and parsed["Behavior"] and
                     parsed["Geometry"] and parsed["Spawn Position"])
            if ok:
                e["extraction_raw"] = resp
                e["extraction"] = parsed
                e["success"] = True
                changed = True
                print(f"  [{data['base_scenario']} #{e['idx']+1}] now ok ({len(resp)} chars)")
            else:
                print(f"  [{data['base_scenario']} #{e['idx']+1}] partial: {parsed}")
        if changed:
            with open(jf, "w") as f:
                json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
