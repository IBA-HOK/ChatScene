"""Quality / diversity analysis of generated scenario descriptions."""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np


# Heuristic keyword lists to classify content
ADVERSARIAL_TYPES = ["car", "pedestrian", "cyclist", "bicycle", "motorcycle",
                     "motorcyclist", "vehicle", "truck", "bus"]
BEHAVIOR_KEYWORDS = ["suddenly", "abruptly", "unexpected", "brake", "accelerate",
                     "swerve", "stop", "stop", "dash", "sprint", "dart", "drift",
                     "weave", "merge", "cross", "block", "yield", "swerves"]
GEOMETRY_KEYWORDS = ["straight road", "intersection", "lane", "sidewalk",
                     "driveway", "highway", "crosswalk", "four-way", "three-way",
                     "roundabout", "traffic light", "red light", "signal"]


def has_any(text, keywords):
    text = text.lower()
    return [kw for kw in keywords if kw in text]


def jaccard(a, b):
    """Jaccard similarity on word sets."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def detect_adv_object(text):
    text = text.lower()
    if "motorcyclist" in text or "motorcycle" in text or "bike" in text.split():
        return "Motorcycle"
    if "cyclist" in text or "bicycle" in text or "bike " in text:
        return "Bicycle"
    if "pedestrian" in text or "child" in text or "person" in text or "jaywalking" in text:
        return "Pedestrian"
    if "car" in text or "vehicle" in text or "truck" in text or "bus" in text or "taxi" in text:
        return "Car"
    return "Unknown"


def analyze_descriptions(records):
    descs = records["descriptions"]
    n = len(descs)
    lengths = [len(d) for d in descs]
    adv_objs = [detect_adv_object(d) for d in descs]

    # Pairwise Jaccard
    sims = []
    for i in range(n):
        for j in range(i + 1, n):
            sims.append(jaccard(descs[i], descs[j]))

    # Number of unique descriptions
    unique = len({d.lower() for d in descs})

    # Behavior keyword counts (avg per desc)
    bk = [len(has_any(d, BEHAVIOR_KEYWORDS)) for d in descs]

    # Geometry keyword counts
    gk = [len(has_any(d, GEOMETRY_KEYWORDS)) for d in descs]

    # Mentions of "ego" (should be in all)
    ego_count = sum(1 for d in descs if "ego" in d.lower())

    return {
        "n": n,
        "unique": unique,
        "avg_length": float(np.mean(lengths)),
        "max_length": int(np.max(lengths)),
        "min_length": int(np.min(lengths)),
        "adv_object_counts": dict(Counter(adv_objs)),
        "avg_behavior_keywords": float(np.mean(bk)),
        "avg_geometry_keywords": float(np.mean(gk)),
        "ego_mentioned_ratio": ego_count / n if n else 0.0,
        "avg_pairwise_jaccard": float(np.mean(sims)) if sims else 0.0,
        "max_pairwise_jaccard": float(np.max(sims)) if sims else 0.0,
        "min_pairwise_jaccard": float(np.min(sims)) if sims else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--descriptions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    ap.add_argument("--extractions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/extractions")
    ap.add_argument("--out_path",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/analysis.json")
    ap.add_argument("--include_baseline", action="store_true",
                    help="also include the original GPT-4 descriptions from retrieve/scenario_descriptions.txt")
    args = ap.parse_args()

    out = {"models": {}}

    base_dir = Path(args.descriptions_dir)
    for model_dir in sorted(base_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        out["models"][model_name] = {"scenarios": {}, "summary": {}}
        all_analyzed = []
        for jf in sorted(model_dir.glob("*.json")):
            if jf.name == "generation.log":
                continue
            data = json.load(open(jf))
            scenario = data["base_scenario"]
            r = analyze_descriptions(data)
            out["models"][model_name]["scenarios"][scenario] = r
            all_analyzed.append(r)

        if all_analyzed:
            # Aggregate per-model summary
            summary = {
                "total_scenarios": len(all_analyzed),
                "total_descriptions": sum(r["n"] for r in all_analyzed),
                "total_unique": sum(r["unique"] for r in all_analyzed),
                "avg_length": float(np.mean([r["avg_length"] for r in all_analyzed])),
                "avg_pairwise_jaccard": float(np.mean([r["avg_pairwise_jaccard"] for r in all_analyzed])),
                "ego_mentioned_ratio": float(np.mean([r["ego_mentioned_ratio"] for r in all_analyzed])),
                "avg_behavior_keywords": float(np.mean([r["avg_behavior_keywords"] for r in all_analyzed])),
                "adv_object_diversity": len(set(k for r in all_analyzed
                                                 for k in r["adv_object_counts"].keys())),
            }
            out["models"][model_name]["summary"] = summary

    # Baseline: GPT-4 from paper
    if args.include_baseline:
        baseline_file = Path("/home/hokuto/chatScene/ChatScene/retrieve/scenario_descriptions.txt")
        if baseline_file.exists():
            lines = [l.strip() for l in baseline_file.read_text().split("\n") if l.strip()]
            # split into 5 per scenario (8 scenarios)
            base_scenarios = ["StraightObstacle", "TurningObstacle", "LaneChanging",
                              "VehiclePassing", "RedLightRunning", "UnprotectedLeftTurn",
                              "RightTurn", "CrossingNegotiation"]
            out["models"]["GPT4_baseline"] = {"scenarios": {}, "summary": {}}
            all_analyzed = []
            for i, name in enumerate(base_scenarios):
                chunk = lines[i*5:(i+1)*5]
                data = {"descriptions": chunk, "base_scenario": name}
                r = analyze_descriptions(data)
                out["models"]["GPT4_baseline"]["scenarios"][name] = r
                all_analyzed.append(r)
            if all_analyzed:
                out["models"]["GPT4_baseline"]["summary"] = {
                    "total_scenarios": len(all_analyzed),
                    "total_descriptions": sum(r["n"] for r in all_analyzed),
                    "total_unique": sum(r["unique"] for r in all_analyzed),
                    "avg_length": float(np.mean([r["avg_length"] for r in all_analyzed])),
                    "avg_pairwise_jaccard": float(np.mean([r["avg_pairwise_jaccard"] for r in all_analyzed])),
                    "ego_mentioned_ratio": float(np.mean([r["ego_mentioned_ratio"] for r in all_analyzed])),
                    "avg_behavior_keywords": float(np.mean([r["avg_behavior_keywords"] for r in all_analyzed])),
                    "adv_object_diversity": len(set(k for r in all_analyzed
                                                     for k in r["adv_object_counts"].keys())),
                }

    Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote analysis to {args.out_path}")
    print(json.dumps({k: v.get("summary", {}) for k, v in out["models"].items()}, indent=2))


if __name__ == "__main__":
    main()
