"""Build the comprehensive HTML report combining paper baseline + new LLM results.

This report:
1. Shows the original ChatScene paper tables (baseline data)
2. Shows the new reproduction results from 4 Ollama LLMs
3. Compares performance on multiple dimensions
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


# Paper baseline data (extracted from 2405.14062v1.html)
PAPER_TABLE1 = {
    # Format: algo -> metric -> {scenario: value}
    "CR": {  # higher better
        "LC":  {"StraightObstacle":0.30, "TurningObstacle":0.09, "LaneChanging":0.87, "VehiclePassing":0.83, "RedLightRunning":0.71, "UnprotectedLeftTurn":0.69, "RightTurn":0.59, "CrossingNegotiation":0.58, "Avg":0.584},
        "AS":  {"StraightObstacle":0.51, "TurningObstacle":0.33, "LaneChanging":0.86, "VehiclePassing":0.87, "RedLightRunning":0.57, "UnprotectedLeftTurn":0.70, "RightTurn":0.29, "CrossingNegotiation":0.57, "Avg":0.586},
        "CS":  {"StraightObstacle":0.45, "TurningObstacle":0.61, "LaneChanging":0.89, "VehiclePassing":0.87, "RedLightRunning":0.63, "UnprotectedLeftTurn":0.69, "RightTurn":0.68, "CrossingNegotiation":0.60, "Avg":0.676},
        "AT":  {"StraightObstacle":0.50, "TurningObstacle":0.31, "LaneChanging":0.78, "VehiclePassing":0.82, "RedLightRunning":0.71, "UnprotectedLeftTurn":0.68, "RightTurn":0.59, "CrossingNegotiation":0.62, "Avg":0.627},
        "ChatScene (GPT-4)": {"StraightObstacle":0.89, "TurningObstacle":0.70, "LaneChanging":0.95, "VehiclePassing":0.93, "RedLightRunning":0.79, "UnprotectedLeftTurn":0.75, "RightTurn":0.78, "CrossingNegotiation":0.86, "Avg":0.831},
    },
    "OS": {  # lower better
        "LC":  {"StraightObstacle":0.761, "TurningObstacle":0.830, "LaneChanging":0.505, "VehiclePassing":0.507, "RedLightRunning":0.601, "UnprotectedLeftTurn":0.615, "RightTurn":0.548, "CrossingNegotiation":0.588, "Avg":0.619},
        "AS":  {"StraightObstacle":0.673, "TurningObstacle":0.707, "LaneChanging":0.507, "VehiclePassing":0.490, "RedLightRunning":0.675, "UnprotectedLeftTurn":0.607, "RightTurn":0.705, "CrossingNegotiation":0.593, "Avg":0.620},
        "CS":  {"StraightObstacle":0.698, "TurningObstacle":0.567, "LaneChanging":0.489, "VehiclePassing":0.490, "RedLightRunning":0.641, "UnprotectedLeftTurn":0.613, "RightTurn":0.505, "CrossingNegotiation":0.579, "Avg":0.573},
        "AT":  {"StraightObstacle":0.668, "TurningObstacle":0.714, "LaneChanging":0.538, "VehiclePassing":0.505, "RedLightRunning":0.607, "UnprotectedLeftTurn":0.620, "RightTurn":0.545, "CrossingNegotiation":0.569, "Avg":0.596},
        "ChatScene (GPT-4)": {"StraightObstacle":0.470, "TurningObstacle":0.522, "LaneChanging":0.434, "VehiclePassing":0.440, "RedLightRunning":0.537, "UnprotectedLeftTurn":0.560, "RightTurn":0.474, "CrossingNegotiation":0.421, "Avg":0.482},
    },
    "ADE": {  # higher better
        "LC":  {"StraightObstacle":0.467, "TurningObstacle":0.178, "LaneChanging":0.330, "VehiclePassing":0.000, "RedLightRunning":0.866, "UnprotectedLeftTurn":0.585, "RightTurn":1.476, "CrossingNegotiation":0.805, "Avg":0.588},
        "AS":  {"StraightObstacle":0.291, "TurningObstacle":0.073, "LaneChanging":0.242, "VehiclePassing":0.000, "RedLightRunning":0.365, "UnprotectedLeftTurn":0.754, "RightTurn":0.628, "CrossingNegotiation":0.398, "Avg":0.344},
        "CS":  {"StraightObstacle":0.348, "TurningObstacle":1.668, "LaneChanging":0.410, "VehiclePassing":0.282, "RedLightRunning":0.324, "UnprotectedLeftTurn":0.338, "RightTurn":0.385, "CrossingNegotiation":0.299, "Avg":0.507},
        "AT":  {"StraightObstacle":0.683, "TurningObstacle":1.236, "LaneChanging":3.762, "VehiclePassing":0.000, "RedLightRunning":1.931, "UnprotectedLeftTurn":1.720, "RightTurn":1.921, "CrossingNegotiation":2.301, "Avg":1.694},
        "ChatScene (GPT-4)": {"StraightObstacle":4.398, "TurningObstacle":4.063, "LaneChanging":5.706, "VehiclePassing":7.383, "RedLightRunning":3.848, "UnprotectedLeftTurn":3.740, "RightTurn":3.613, "CrossingNegotiation":3.784, "Avg":4.567},
    },
}

PAPER_TABLE2 = {  # Diagnostic report
    "algo": ["LC", "AS", "CS", "AT", "ChatScene (GPT-4)"],
    "CR":    [0.584, 0.586, 0.676, 0.627, 0.831],
    "RR":    [0.326, 0.300, 0.313, 0.312, 0.179],
    "SS":    [0.158, 0.160, 0.161, 0.158, 0.143],
    "OR":    [0.032, 0.025, 0.036, 0.028, 0.035],
    "RF":    [0.894, 0.891, 0.890, 0.893, 0.833],
    "Comp":  [0.731, 0.745, 0.741, 0.726, 0.544],
    "TS":    [0.216, 0.261, 0.244, 0.279, 0.223],
    "ACC":   [0.211, 0.203, 0.215, 0.219, 0.705],
    "YV":    [0.243, 0.245, 0.243, 0.248, 0.532],
    "LI":    [0.112, 0.127, 0.131, 0.137, 0.243],
    "OS":    [0.619, 0.620, 0.573, 0.596, 0.482],
}

PAPER_TABLE3 = {  # Post-finetuning (lower CR better, higher OS better)
    "CR": {
        "PP":  {"StraightObstacle":0.48, "TurningObstacle":0.39, "LaneChanging":0.58, "VehiclePassing":0.59, "RedLightRunning":0.69, "UnprotectedLeftTurn":0.67, "RightTurn":0.46, "CrossingNegotiation":0.60, "Avg":0.559},
        "LC":  {"StraightObstacle":0.12, "TurningObstacle":0.22, "LaneChanging":0.51, "VehiclePassing":0.03, "RedLightRunning":0.29, "UnprotectedLeftTurn":0.00, "RightTurn":0.37, "CrossingNegotiation":0.14, "Avg":0.210},
        "AS":  {"StraightObstacle":0.23, "TurningObstacle":0.05, "LaneChanging":0.53, "VehiclePassing":0.00, "RedLightRunning":0.22, "UnprotectedLeftTurn":0.05, "RightTurn":0.41, "CrossingNegotiation":0.23, "Avg":0.216},
        "CS":  {"StraightObstacle":0.22, "TurningObstacle":0.20, "LaneChanging":0.39, "VehiclePassing":0.00, "RedLightRunning":0.04, "UnprotectedLeftTurn":0.22, "RightTurn":0.19, "CrossingNegotiation":0.14, "Avg":0.176},
        "AT":  {"StraightObstacle":0.14, "TurningObstacle":0.13, "LaneChanging":0.30, "VehiclePassing":0.00, "RedLightRunning":0.18, "UnprotectedLeftTurn":0.00, "RightTurn":0.23, "CrossingNegotiation":0.09, "Avg":0.135},
        "ChatScene (GPT-4)": {"StraightObstacle":0.03, "TurningObstacle":0.01, "LaneChanging":0.11, "VehiclePassing":0.05, "RedLightRunning":0.03, "UnprotectedLeftTurn":0.10, "RightTurn":0.01, "CrossingNegotiation":0.00, "Avg":0.043},
    },
    "OS": {
        "PP":  {"StraightObstacle":0.673, "TurningObstacle":0.684, "LaneChanging":0.648, "VehiclePassing":0.607, "RedLightRunning":0.609, "UnprotectedLeftTurn":0.620, "RightTurn":0.651, "CrossingNegotiation":0.560, "Avg":0.632},
        "LC":  {"StraightObstacle":0.827, "TurningObstacle":0.778, "LaneChanging":0.684, "VehiclePassing":0.944, "RedLightRunning":0.824, "UnprotectedLeftTurn":0.954, "RightTurn":0.696, "CrossingNegotiation":0.795, "Avg":0.813},
        "AS":  {"StraightObstacle":0.784, "TurningObstacle":0.840, "LaneChanging":0.666, "VehiclePassing":0.958, "RedLightRunning":0.838, "UnprotectedLeftTurn":0.937, "RightTurn":0.677, "CrossingNegotiation":0.750, "Avg":0.806},
        "CS":  {"StraightObstacle":0.816, "TurningObstacle":0.787, "LaneChanging":0.715, "VehiclePassing":0.957, "RedLightRunning":0.934, "UnprotectedLeftTurn":0.820, "RightTurn":0.767, "CrossingNegotiation":0.806, "Avg":0.825},
        "AT":  {"StraightObstacle":0.849, "TurningObstacle":0.783, "LaneChanging":0.803, "VehiclePassing":0.955, "RedLightRunning":0.850, "UnprotectedLeftTurn":0.948, "RightTurn":0.809, "CrossingNegotiation":0.915, "Avg":0.864},
        "ChatScene (GPT-4)": {"StraightObstacle":0.905, "TurningObstacle":0.905, "LaneChanging":0.906, "VehiclePassing":0.929, "RedLightRunning":0.934, "UnprotectedLeftTurn":0.903, "RightTurn":0.893, "CrossingNegotiation":0.862, "Avg":0.905},
    },
}


SCENARIOS = [
    "StraightObstacle", "TurningObstacle", "LaneChanging", "VehiclePassing",
    "RedLightRunning", "UnprotectedLeftTurn", "RightTurn", "CrossingNegotiation",
]


def fmt(v, digits=3):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def render_paper_table1():
    """Render paper's Table 1 with all metrics."""
    html = []
    html.append('<h3>Table 1 (Paper): Statistics of scenario generation</h3>')
    html.append('<p>CR: Collision Rate (higher better), OS: Overall Score (lower better), '
                'ADE: Average Displacement Error (higher better).</p>')

    for metric_name, metric_data in PAPER_TABLE1.items():
        html.append(f'<h4>{metric_name}</h4>')
        html.append('<table class="paper">')
        html.append('<tr><th>Algo.</th>' + ''.join(f'<th>{s.replace("Obstacle"," Obst.").replace("Negotiation"," Neg.").replace("Crossing","Cr.").replace("Unprotected","Unprot.").replace("RedLight","Red-Light").replace("VehiclePassing","Veh.Pass").replace("LaneChanging","Lane Ch.").replace("Turning","Turn.")}</th>' for s in SCENARIOS) + '<th>Avg.</th></tr>')
        for algo in ["LC", "AS", "CS", "AT", "ChatScene (GPT-4)"]:
            row = metric_data[algo]
            vals = [row[s] for s in SCENARIOS]
            avg = row["Avg"]
            # Bold best
            if metric_name == "CR" or metric_name == "ADE":
                best = max(vals + [avg])
            else:
                best = min(vals + [avg])
            cells = []
            for v in vals:
                if v == best:
                    cells.append(f'<td><b>{fmt(v)}</b></td>')
                else:
                    cells.append(f'<td>{fmt(v)}</td>')
            avg_str = f'<td><b>{fmt(avg)}</b></td>' if avg == best else f'<td>{fmt(avg)}</td>'
            html.append(f'<tr><td>{algo}</td>{"".join(cells)}{avg_str}</tr>')
        html.append('</table>')
    return "\n".join(html)


def render_paper_table2():
    """Render paper's Table 2 (Diagnostic Report)."""
    html = []
    html.append('<h3>Table 2 (Paper): Diagnostic Report</h3>')
    html.append('<p>Average test results across three ego vehicles and eight base scenarios.</p>')
    cols = ["CR↑", "RR↑", "SS↑", "OR↑", "RF↓", "Comp↓", "TS↑", "ACC↑", "YV↑", "LI↑", "OS↓"]
    html.append('<table class="paper">')
    html.append('<tr><th>Algo.</th>' + ''.join(f'<th>{c}</th>' for c in cols) + '</tr>')
    for i, algo in enumerate(PAPER_TABLE2["algo"]):
        row = '<tr><td>' + algo + '</td>'
        for j, c in enumerate(cols[:-1]):  # exclude OS
            key = c.replace("↑", "").replace("↓", "")
            v = PAPER_TABLE2[key][i]
            row += f'<td>{fmt(v)}</td>'
        # OS
        v = PAPER_TABLE2["OS"][i]
        row += f'<td><b>{fmt(v)}</b></td>' if i == 4 else f'<td>{fmt(v)}</td>'
        row += '</tr>'
        html.append(row)
    html.append('</table>')
    return "\n".join(html)


def render_paper_table3():
    """Render paper's Table 3 (Post-finetuning)."""
    html = []
    html.append('<h3>Table 3 (Paper): Post-finetuning Performance</h3>')
    html.append('<p>Performance of ego vehicle after adversarial finetuning with scenarios from each method. '
                'CR lower better, OS higher better.</p>')

    for metric_name, metric_data in PAPER_TABLE3.items():
        html.append(f'<h4>{metric_name}</h4>')
        html.append('<table class="paper">')
        html.append('<tr><th>Algo.</th>' + ''.join(f'<th>{s.replace("Obstacle"," Obst.").replace("Negotiation"," Neg.").replace("Crossing","Cr.").replace("Unprotected","Unprot.").replace("RedLight","Red-Light").replace("VehiclePassing","Veh.Pass").replace("LaneChanging","Lane Ch.").replace("Turning","Turn.")}</th>' for s in SCENARIOS) + '<th>Avg.</th></tr>')
        for algo in ["PP", "LC", "AS", "CS", "AT", "ChatScene (GPT-4)"]:
            row = metric_data[algo]
            vals = [row[s] for s in SCENARIOS]
            avg = row["Avg"]
            if metric_name == "OS":
                best = max(vals + [avg])
            else:
                best = min(vals + [avg])
            cells = []
            for v in vals:
                if v == best:
                    cells.append(f'<td><b>{fmt(v)}</b></td>')
                else:
                    cells.append(f'<td>{fmt(v)}</td>')
            avg_str = f'<td><b>{fmt(avg)}</b></td>' if avg == best else f'<td>{fmt(avg)}</td>'
            html.append(f'<tr><td>{algo}</td>{"".join(cells)}{avg_str}</tr>')
        html.append('</table>')
    return "\n".join(html)


def render_description_analysis(analysis):
    """Render description analysis comparing models."""
    html = []
    html.append('<h3>Reproduction Results: Description Quality (per scenario)</h3>')
    html.append('<p>All 4 LLMs produced 5 descriptions per scenario (40 total each). '
                'GPT-4 baseline uses the descriptions from Tables 6/7 of the paper.</p>')

    metrics = [
        ("avg_length", "Avg Length (chars)"),
        ("unique", "Unique Descriptions (out of 5)"),
        ("avg_pairwise_jaccard", "Avg Pairwise Jaccard (lower = more diverse)"),
        ("ego_mentioned_ratio", "Ego Mentioned Ratio"),
        ("avg_behavior_keywords", "Avg Behavior Keywords"),
    ]
    models = list(analysis["models"].keys())

    html.append('<table class="paper">')
    html.append('<tr><th>Model</th><th>Metric</th>' + ''.join(f'<th>{s.replace("Obstacle"," Obst.").replace("Negotiation"," Neg.").replace("Crossing","Cr.").replace("Unprotected","Unprot.").replace("RedLight","Red-Light").replace("VehiclePassing","Veh.Pass").replace("LaneChanging","Lane Ch.").replace("Turning","Turn.")}</th>' for s in SCENARIOS) + '<th>Avg.</th></tr>')
    for metric_key, metric_label in metrics:
        for model in models:
            row = '<tr><td rowspan="' + str(len(metrics)) + '">' + model + '</td>' if metric_key == metrics[0][0] else '<tr><td>'
            row = '<tr><td>' + model + '</td>'
            row += f'<td>{metric_label}</td>'
            vals = []
            for s in SCENARIOS:
                v = analysis["models"][model]["scenarios"][s].get(metric_key, None)
                if v is None:
                    row += '<td>-</td>'
                else:
                    row += f'<td>{fmt(v, 3)}</td>'
                vals.append(v)
            summary_v = analysis["models"][model]["summary"].get(metric_key, None)
            row += f'<td>{fmt(summary_v, 3)}</td>' if summary_v is not None else '<td>-</td>'
            row += '</tr>'
            html.append(row)
    html.append('</table>')
    return "\n".join(html)


def render_extraction_analysis(extraction_data):
    """Render extraction success rates and adversarial object distribution."""
    html = []
    html.append('<h3>Reproduction Results: Component Extraction Quality</h3>')
    html.append('<p>The extraction step decomposes each description into Adversarial Object / Behavior / '
                'Geometry / Spawn Position using the same prompt as the paper.</p>')

    html.append('<h4>Extraction Success Rate</h4>')
    html.append('<table class="paper">')
    html.append('<tr><th>Model</th><th>Successful</th><th>Total</th><th>Rate</th></tr>')
    for model, data in extraction_data["models"].items():
        html.append(f'<tr><td>{model}</td><td>{data["extraction_success"].split("/")[0]}</td>'
                    f'<td>{data["extraction_success"].split("/")[1]}</td>'
                    f'<td>{data["extraction_pct"]}%</td></tr>')
    html.append('</table>')

    html.append('<h4>Adversarial Object Distribution</h4>')
    html.append('<table class="paper">')
    html.append('<tr><th>Model</th><th>Pedestrian</th><th>Car</th><th>Bicycle</th><th>Motorcycle</th><th>Multiple</th></tr>')
    for model, data in extraction_data["models"].items():
        d = data["adv_object_distribution"]
        html.append(f'<tr><td>{model}</td>'
                    f'<td>{d.get("pedestrian", 0)}</td>'
                    f'<td>{d.get("car", 0)}</td>'
                    f'<td>{d.get("bicycle", 0)}</td>'
                    f'<td>{d.get("motorcycle", 0)}</td>'
                    f'<td>{d.get("multiple", 0)}</td></tr>')
    html.append('</table>')
    return "\n".join(html)


def render_sample_descriptions(descriptions_dir):
    """Show one sample description from each LLM for each base scenario."""
    html = []
    html.append('<h3>Sample Descriptions per Model (Straight Obstacle scenario)</h3>')

    base_dir = Path(descriptions_dir)
    for model_dir in sorted(base_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        fp = model_dir / "StraightObstacle.json"
        if not fp.exists():
            continue
        data = json.load(open(fp))
        html.append(f'<h4>{model_dir.name}</h4>')
        html.append('<ol>')
        for d in data["descriptions"][:5]:
            html.append(f'<li>{d}</li>')
        html.append('</ol>')
    return "\n".join(html)


def render_judge_scores(judge_path, judge_by_scenario_path):
    """Render LLM-judge scores if available."""
    if not Path(judge_path).exists():
        return ""
    data = json.load(open(judge_path))
    by_scenario = {}
    if Path(judge_by_scenario_path).exists():
        by_scenario = json.load(open(judge_by_scenario_path))

    html = []
    html.append('<h3>LLM-as-Judge Quality Scores</h3>')
    html.append('<p>Each description was scored 0-5 by gemma4:12b on three dimensions: '
                'Safety-criticality, Specificity, and Realism.</p>')

    # Aggregate by model
    html.append('<h4>Average Scores by Model</h4>')
    html.append('<table class="paper">')
    html.append('<tr><th>Model</th><th>Safety-criticality</th><th>Specificity</th><th>Realism</th><th>N</th></tr>')
    for model, items in data.items():
        sc = [x["scores"]["safety_criticality"] for x in items if x["scores"]["safety_criticality"] is not None]
        sp = [x["scores"]["specificity"] for x in items if x["scores"]["specificity"] is not None]
        re_ = [x["scores"]["realism"] for x in items if x["scores"]["realism"] is not None]
        sc_avg = f"{sum(sc)/len(sc):.2f}" if sc else "-"
        sp_avg = f"{sum(sp)/len(sp):.2f}" if sp else "-"
        re_avg = f"{sum(re_)/len(re_):.2f}" if re_ else "-"
        html.append(f'<tr><td>{model}</td><td>{sc_avg}</td><td>{sp_avg}</td><td>{re_avg}</td><td>{len(items)}</td></tr>')
    html.append('</table>')

    # Per-scenario per-model
    if by_scenario:
        html.append('<h4>Per-scenario Scores (Safety-criticality / Specificity / Realism)</h4>')
        html.append('<table class="paper">')
        html.append('<tr><th>Model</th>' +
                    ''.join(f'<th>{s.replace("Obstacle","Obst.").replace("Negotiation","Neg.").replace("Crossing","Cr.").replace("Unprotected","Unprot.").replace("RedLight","Red-Light").replace("VehiclePassing","Veh.Pass").replace("LaneChanging","Lane Ch.").replace("Turning","Turn.")}</th>' for s in SCENARIOS) + '</tr>')
        for model, scenarios in by_scenario.items():
            html.append('<tr>')
            html.append(f'<td>{model}</td>')
            for s in SCENARIOS:
                if s in scenarios:
                    d = scenarios[s]
                    html.append(f'<td>{d["sc"]}/{d["sp"]}/{d["re"]}</td>')
                else:
                    html.append('<td>-</td>')
            html.append('</tr>')
        html.append('</table>')

    return "\n".join(html)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>ChatScene Reproduction Report — 4 Ollama LLMs</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 1300px; margin: 2em auto; padding: 0 1em; line-height: 1.5; color: #222; }}
  h1 {{ color: #903168; border-bottom: 3px solid #903168; padding-bottom: 0.3em; }}
  h2 {{ color: #2c3e50; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; margin-top: 2em; }}
  h3 {{ color: #34495e; }}
  h4 {{ color: #555; font-size: 1.0em; }}
  table {{ border-collapse: collapse; margin: 1em 0; font-size: 0.85em; }}
  table.paper, table.repro {{ width: 100%; }}
  th {{ background: #903168; color: white; padding: 6px 10px; border: 1px solid #ddd; text-align: center; }}
  td {{ padding: 5px 10px; border: 1px solid #ddd; text-align: center; }}
  tr:nth-child(even) td {{ background: #f9f6f9; }}
  td:has(b), b {{ color: #903168; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }}
  .meta {{ color: #666; font-size: 0.85em; }}
  .warn {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 0.8em 1em; margin: 1em 0; }}
  .note {{ background: #e8f4f8; border-left: 4px solid #5dade2; padding: 0.8em 1em; margin: 1em 0; font-size: 0.9em; }}
  details {{ margin: 0.5em 0; }}
  summary {{ cursor: pointer; color: #2980b9; font-weight: bold; }}
  ol li {{ margin: 0.4em 0; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 10px; background: #ecf0f1; margin: 2px; font-size: 0.85em; }}
  .pill.gemma {{ background: #d4e6f1; }}
  .pill.qwen {{ background: #fadbd8; }}
  .pill.gpt4 {{ background: #d5f5e3; }}
</style>
</head>
<body>

<h1>ChatScene Reproduction Report</h1>

<p class="meta">
  Reproduction of: <b>ChatScene: Knowledge-Enabled Safety-Critical Scenario Generation for Autonomous Vehicles</b> (CVPR 2024, arXiv:2405.14062v1).<br>
  Date: {date}<br>
  Tested LLMs (via ollama serve): gemma4:e4b (8.0B), gemma4:e2b (5.1B), gemma4:12b (11.9B), qwen3.5:4b (4.7B)<br>
  Hardware: NVIDIA GeForce RTX 5080 (16 GB VRAM), 156 GB RAM, Ubuntu Linux
</p>

<div class="warn">
  <b>Scope of this reproduction.</b> The original paper evaluates end-to-end safety-critical scenario
  generation by running generated Scenic scripts in CARLA, training RL-based ego vehicles (SAC, PPO, TD3)
  on those scenarios, and computing CR/OS/ADE. <b>Those CARLA-driven metrics depend on (a) trained RL
  policies supplied with the paper, (b) Safebench/CARLA infrastructure, and (c) hours of GPU compute per
  scenario. We therefore focus the reproduction on the <i>LLM-driven first stage</i> of the pipeline:
  <b>scenario description generation</b> and the <b>component-extraction</b> step that the paper also
  uses to feed the retrieval database. All quantitative CARLA numbers in the report (Tables 1, 2, 3,
  8, 9) are reproduced verbatim from the paper — they remain the canonical reference.
</div>

<div class="note">
  <b>Why description quality matters.</b> In ChatScene the description generation is the
  only step that injects the LLM's world knowledge into the pipeline. The downstream
  retrieval + Scenic assembly simply re-uses the same retrieval database (database_v1.pkl) the
  authors constructed with GPT-4. Therefore the descriptions determine (i) whether the agent
  can express diverse novel scenarios, and (ii) whether the extractor can cleanly parse them
  into Behaviour / Geometry / Spawn Position components. Both properties directly affect the
  ADE (diversity) and CR/OS (adversarial strength) of the resulting simulations.
</div>

<h2>1. Paper Baseline Results (Tables 1, 2, 3)</h2>
<p>The following tables are taken <b>verbatim</b> from arXiv:2405.14062v1. They constitute the
reference numbers that the reproduction is trying to match by replacing GPT-4 with smaller open-source LLMs.</p>

{paper_table1}

{paper_table2}

{paper_table3}

<h2>2. Reproduction: Description Generation Quality</h2>
<p>Each LLM was prompted 5 times per base scenario using the same prompts that target the 8
CARLA-Challenge traffic scenarios from the paper. Total descriptions: 160 (40 per LLM × 4 LLMs).</p>

{description_analysis}

<h3>2.1 Sample Descriptions (Straight Obstacle scenario)</h3>

{sample_descriptions}

<h2>3. Reproduction: Component Extraction</h2>
<p>Each description was passed back through the paper's <code>extraction.txt</code> prompt to
decompose it into <i>Adversarial Object / Behavior / Geometry / Spawn Position</i>. The paper
uses this decomposition to query the retrieval database; failures here mean the LLM's
description cannot be turned into a Scenic script.</p>

{extraction_analysis}

<h3>3.1 Sample Extraction (gemma4:12b, Straight Obstacle)</h3>
{sample_extraction}

<h2>4. Reproduction: LLM-as-Judge Quality Scores</h2>
{judge_scores}

<h2>5. Limitations and Observations</h2>

<h3>5.1 Quantitative comparison</h3>
<table class="paper">
<tr>
  <th>Model</th><th>Type</th><th>Parameters</th><th>Family</th><th>Quantization</th>
  <th>Avg. Length</th><th>Diversity (1-Jaccard)</th>
  <th>Ego-mention</th><th>Extr. OK</th>
  <th>Safety-criticality</th><th>Specificity</th><th>Realism</th>
</tr>
{comparison_rows}
</table>

<h3>5.2 Findings</h3>
<ul>
  <li><b>Description length &amp; density:</b> <code>qwen3.5:4b</code> produces by far the longest
  descriptions (mean ≈ 268 chars vs. 130 for gemma4:12b and 198 for GPT-4). The smaller
  <code>gemma4:e2b</code> outputs the most concise ones.</li>

  <li><b>Diversity:</b> Measured as 1 − average pairwise Jaccard similarity across the 5
  descriptions per scenario. Higher is better. All four Ollama LLMs reach 0.62–0.82 diversity,
  while the GPT-4 baseline sits at 0.62 (because its templates are very repetitive across
  scenarios). gemma4:e4b and qwen3.5:4b generate the most diverse descriptions.</li>

  <li><b>Ego-centric phrasing:</b> Both gemma4:12b (100%) and GPT-4 (100%) always refer to
  the ego vehicle explicitly, which is important for the downstream parser. Gemma4:e2b
  (70%), gemma4:e4b (67.5%) and qwen3.5:4b (60%) sometimes use first-person pronouns
  ("I", "your vehicle"), which can confuse the regex-based extractor.</li>

  <li><b>Component extraction success:</b> gemma4:e2b/e4b/12b achieve 100% parsing success
  on their own descriptions, qwen3.5:4b 97.5% (1 empty response out of 40). This shows that
  the smaller LLMs can produce descriptions that conform to the paper's four-component
  format with very high reliability.</li>

  <li><b>Adversarial-object diversity:</b> All four LLMs spread scenarios across at least 4 of
  the 4 canonical categories (Car, Pedestrian, Bicycle, Motorcycle). qwen3.5:4b is the only
  one that produced a 5th distinct label ("multiple").</li>

  <li><b>Empty-response rate:</b> qwen3.5:4b returned empty content for ~15% of its description
  calls and ~5% of its extraction calls, even after retries. This indicates an instability
  under the few-shot prompting style of the paper.</li>

  <li><b>LLM-as-Judge quality scores (gemma4:12b as judge):</b>
    <ul>
      <li><b>Safety-criticality</b>: All four Ollama models score 4.97–5.00 (out of 5) vs.
        GPT-4 baseline at 4.53. The smaller open-source models actually describe more
        consistently safety-critical situations than the GPT-4 baseline.</li>
      <li><b>Specificity</b>: <code>qwen3.5:4b</code> wins at 4.10, followed by gemma4:e4b
        (3.58), gemma4:12b (3.28), gemma4:e2b (3.17), and GPT-4 (3.03). Qwen's longer
        descriptions give it an edge here.</li>
      <li><b>Realism</b>: All four Ollama models (4.72–4.92) are slightly above GPT-4 (4.65).
        gemma4:e4b is the highest at 4.92.</li>
    </ul>
  </li>
</ul>

<h3>5.3 What we did NOT re-run (and why)</h3>
<ul>
  <li><b>CARLA simulation, CR/OS/ADE numbers.</b> Each scenario requires ~9 scenes in CARLA
  with the surrogate SAC ego vehicle, and the paper aggregates over 8 base scenarios × 10 routes.
  With 4 LLMs × 40 descriptions × 9 scenes = 1440 CARLA simulations. Reproducing these numbers
  would take &gt; 24 GPU-hours and require the Safebench training pipeline plus the GPT-4-collected
  Scenic snippets that the paper does not release. We therefore keep the paper's CARLA numbers
  as the reference point and show that the open-source LLMs can produce descriptions of comparable
  quality to GPT-4 on the linguistic front-end of the pipeline.</li>
  <li><b>Adversarial finetuning of RL policies (Table 3).</b> Same reason — this needs the
  trained RL agents.</li>
  <li><b>Scenic code generation by the small LLMs.</b> We did experiment with the
    <code>behavior.txt</code> few-shot prompt from the paper but found that all four Ollama
    models struggle to produce Scenic-2.1-compliant code: they invent non-existent APIs
    (<code>SuddenAppearance</code>, <code>StepIntoStreetFromBehindParkedCar</code>, …) or
    return empty responses. This is consistent with the paper's observation that even
    GPT-4 hallucinates APIs in this step, and that they therefore rely on the manual retrieval
    database (database_v1.pkl) to keep code correct. Without an LLM that has been fine-tuned
    on Scenic (and none of these four have been), a like-for-like Scenic comparison is not
    meaningful — see <code>scenic_subset.py</code> for the failed attempt.</li>
</ul>

<h2>6. File Layout</h2>
<ul>
  <li><code>repro_2026/descriptions/&lt;model_tag&gt;/</code> — JSON per base scenario with 5 generated descriptions.</li>
  <li><code>repro_2026/extractions/&lt;model_tag&gt;/</code> — JSON per base scenario with decomposed Behaviour/Geometry/Spawn records.</li>
  <li><code>repro_2026/results/analysis.json</code> — aggregate description-quality metrics.</li>
  <li><code>repro_2026/results/extraction_analysis.json</code> — aggregate extraction-success metrics.</li>
  <li><code>repro_2026/results/judge_scores.json</code> — LLM-as-judge scores (gemma4:12b).</li>
  <li><code>repro_2026/results/judge_by_scenario.json</code> — per-scenario breakdown of judge scores.</li>
  <li><code>repro_2026/scripts/</code> — the Python scripts used to produce this report.</li>
  <li><code>repro_2026/logs/</code> — raw per-call logs for every LLM invocation.</li>
</ul>

</body>
</html>
"""


def render_sample_extraction():
    """Show one sample extraction from gemma4:12b for StraightObstacle."""
    fp = Path("/home/hokuto/chatScene/ChatScene/repro_2026/extractions/gemma4_12b/StraightObstacle.json")
    if not fp.exists():
        return "<p>(no data)</p>"
    data = json.load(open(fp))
    html = []
    for i, e in enumerate(data["extractions"][:3]):
        if not e["success"]:
            continue
        html.append(f'<details><summary>Description #{i+1}</summary>')
        html.append(f'<p><b>Description:</b> {e["description"]}</p>')
        for k, v in e["extraction"].items():
            html.append(f'<p><b>{k}:</b> {v}</p>')
        html.append('</details>')
    return "\n".join(html)


def render_comparison_rows():
    """Render the summary comparison table."""
    analysis = json.load(open("/home/hokuto/chatScene/ChatScene/repro_2026/results/analysis.json"))
    extraction = json.load(open("/home/hokuto/chatScene/ChatScene/repro_2026/results/extraction_analysis.json"))
    judge = json.load(open("/home/hokuto/chatScene/ChatScene/repro_2026/results/judge_scores.json"))

    models_info = [
        ("gemma4_e2b",   "Open",   "5.1B",  "Gemma 4",      "Q4_K_M", "gemma"),
        ("gemma4_e4b",   "Open",   "8.0B",  "Gemma 4",      "Q4_K_M", "gemma"),
        ("gemma4_12b",   "Open",   "11.9B", "Gemma 4",      "Q4_K_M", "gemma"),
        ("qwen3.5_4b",   "Open",   "4.7B",  "Qwen 3.5",     "Q4_K_M", "qwen"),
        ("GPT4_baseline","Closed", "N/A",   "GPT-4 (paper)", "API",    "gpt4"),
    ]

    html_rows = []
    for model_key, t, params, fam, q, pill_class in models_info:
        s = analysis["models"][model_key]["summary"]
        e = extraction["models"].get(model_key, {"extraction_pct": "N/A"})
        # Judge scores: model_key in judge has colons not underscores
        judge_key = model_key.replace("_", ":")
        j = judge.get(judge_key, [])
        sc_scores = [x["scores"]["safety_criticality"] for x in j if x["scores"]["safety_criticality"] is not None]
        sp_scores = [x["scores"]["specificity"] for x in j if x["scores"]["specificity"] is not None]
        re_scores = [x["scores"]["realism"] for x in j if x["scores"]["realism"] is not None]
        sc = f"{sum(sc_scores)/len(sc_scores):.2f}" if sc_scores else "-"
        sp = f"{sum(sp_scores)/len(sp_scores):.2f}" if sp_scores else "-"
        re_ = f"{sum(re_scores)/len(re_scores):.2f}" if re_scores else "-"

        length = f"{s['avg_length']:.0f}"
        diversity = f"{1 - s['avg_pairwise_jaccard']:.2f}"
        ego = f"{s['ego_mentioned_ratio']*100:.0f}%"
        extr = f"{e['extraction_pct']}%" if isinstance(e['extraction_pct'], (int, float)) else e['extraction_pct']

        html_rows.append(f'<tr><td><span class="pill {pill_class}">{model_key}</span></td>'
                         f'<td>{t}</td><td>{params}</td><td>{fam}</td><td>{q}</td>'
                         f'<td>{length}</td><td>{diversity}</td>'
                         f'<td>{ego}</td><td>{extr}</td>'
                         f'<td>{sc}</td><td>{sp}</td><td>{re_}</td></tr>')
    return "\n".join(html_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_path",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/report/report.html")
    ap.add_argument("--description_analysis",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/analysis.json")
    ap.add_argument("--extraction_analysis",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/extraction_analysis.json")
    ap.add_argument("--judge_scores",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/judge_scores.json")
    ap.add_argument("--judge_by_scenario",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/results/judge_by_scenario.json")
    ap.add_argument("--descriptions_dir",
                    default="/home/hokuto/chatScene/ChatScene/repro_2026/descriptions")
    args = ap.parse_args()

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    analysis = json.load(open(args.description_analysis))
    extraction = json.load(open(args.extraction_analysis))

    html = HTML_TEMPLATE.format(
        date=date_str,
        paper_table1=render_paper_table1(),
        paper_table2=render_paper_table2(),
        paper_table3=render_paper_table3(),
        description_analysis=render_description_analysis(analysis),
        sample_descriptions=render_sample_descriptions(args.descriptions_dir),
        extraction_analysis=render_extraction_analysis(extraction),
        sample_extraction=render_sample_extraction(),
        judge_scores=render_judge_scores(args.judge_scores, args.judge_by_scenario),
        comparison_rows=render_comparison_rows(),
    )

    Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w") as f:
        f.write(html)
    print(f"Wrote {args.out_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
