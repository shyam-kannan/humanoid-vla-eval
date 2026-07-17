"""Automated scoring pipeline — implements docs/scoring_rubric.md against the raw
episode logs produced by notebooks/02_automated_scoring.ipynb.

Runs entirely locally (no GPU needed). Reads one JSON file per episode from a raw-log
directory (predicted action chunks, actual recorded actions, hand-closure segmentation,
Cosmos-Reason2's reasoning text), computes:

  1. Execution-stage scoring per body-part group per observed phase (Section 4)
  2. Reasoning-stage scoring via an LLM-as-judge call to Claude (Section 3)
  3. The core reasoning x execution 2x2 classification per phase (Section 5)
  4. Manual-review flags (Section 6)

and writes a scored CSV + JSON summary.

Usage:
    python scripts/score_trajectories.py --raw-log-dir /path/to/raw_logs --out-dir results/

Requires ANTHROPIC_API_KEY (or an `ant auth login` profile) for the reasoning-stage judge.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Model choice for the reasoning-stage LLM judge. This is a small, cheap
# classification call (match a handful of reasoning-trace steps against 3
# canonical phase labels) — if per-call cost matters at the scale you're
# running this, claude-haiku-4-5 is a reasonable, much cheaper substitute.
# Left as Opus by default rather than silently downgrading; change explicitly
# if you want the cheaper model.
# ---------------------------------------------------------------------------
JUDGE_MODEL = "claude-opus-4-8"

EXECUTION_ARM_WAIST_KEYS = {"left_arm", "right_arm", "waist", "left_leg", "right_leg"}
EXECUTION_HAND_KEYS = {"left_hand", "right_hand"}
EXECUTION_WRIST_EEF_KEYS = {"left_wrist_eef_9d", "right_wrist_eef_9d"}

CANONICAL_PHASES = ["reach", "transport", "retreat"]

REASONING_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "object": {"type": "string", "description": "The object being manipulated, as named in the task."},
        "target": {"type": "string", "description": "The destination/target, as named in the task."},
        "phases_found": {
            "type": "object",
            "properties": {
                "reach": {"type": "boolean"},
                "transport": {"type": "boolean"},
                "retreat": {"type": "boolean"},
            },
            "required": ["reach", "transport", "retreat"],
            "additionalProperties": False,
        },
        "order_correct": {"type": "boolean", "description": "True if the phases found appear in reach -> transport -> retreat order."},
        "object_target_correct": {"type": "boolean", "description": "True if every step referencing an object/target names the correct one from the task."},
        "hallucinated_step": {"type": "boolean", "description": "True if any step describes an action or object not grounded in the task."},
        "under_specified": {"type": "boolean", "description": "True if the plan is too vague to map onto any canonical phase confidently."},
        "manual_review_needed": {"type": "boolean", "description": "True if hallucinated_step or under_specified is true and you cannot confidently resolve it from the text alone."},
        "rationale": {"type": "string", "description": "One or two sentences explaining the judgment."},
    },
    "required": [
        "object", "target", "phases_found", "order_correct", "object_target_correct",
        "hallucinated_step", "under_specified", "manual_review_needed", "rationale",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Execution-stage scoring (scoring_rubric.md Section 4)
# ---------------------------------------------------------------------------

def rot6d_to_matrix(rot6d: list[float]) -> Any:
    import numpy as np

    a1 = np.asarray(rot6d[0:3], dtype=np.float64)
    a2 = np.asarray(rot6d[3:6], dtype=np.float64)
    b1 = a1 / np.linalg.norm(a1)
    b2 = a2 - np.dot(b1, a2) * b1
    b2 = b2 / np.linalg.norm(b2)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=1)


def geodesic_angle_deg(rot6d_a: list[float], rot6d_b: list[float]) -> float:
    import numpy as np

    R_a = rot6d_to_matrix(rot6d_a)
    R_b = rot6d_to_matrix(rot6d_b)
    R_rel = R_a.T @ R_b
    trace = float(np.clip((np.trace(R_rel) - 1.0) / 2.0, -1.0, 1.0))
    return float(np.degrees(np.arccos(trace)))


def tier(value: float, match_max: float, minor_max: float) -> str:
    if value < match_max:
        return "match"
    if value < minor_max:
        return "minor_deviation"
    return "failure"


def score_wrist_eef_key(predicted: list[list[float]], actual: list[list[float]]) -> dict:
    """Wrist position (cm) + rotation (deg) tiers, averaged over the compared steps."""
    import numpy as np

    n = min(len(predicted), len(actual))
    if n == 0:
        return {"n_steps": 0, "position_tier": "unscored", "rotation_tier": "unscored"}

    pos_dists_cm = []
    rot_angles_deg = []
    for t in range(n):
        pred = predicted[t]
        act = actual[t]
        pos_dist_m = float(np.linalg.norm(np.asarray(pred[:3]) - np.asarray(act[:3])))
        pos_dists_cm.append(pos_dist_m * 100.0)
        rot_angles_deg.append(geodesic_angle_deg(pred[3:9], act[3:9]))

    mean_pos_cm = sum(pos_dists_cm) / n
    mean_rot_deg = sum(rot_angles_deg) / n
    return {
        "n_steps": n,
        "mean_position_error_cm": round(mean_pos_cm, 3),
        "mean_rotation_error_deg": round(mean_rot_deg, 3),
        "position_tier": tier(mean_pos_cm, 3.0, 7.0),
        "rotation_tier": tier(mean_rot_deg, 10.0, 20.0),
    }


def score_joint_group(predicted: list[list[float]], actual: list[list[float]]) -> dict:
    """Per-joint degree diff, averaged over compared steps. Assumes raw joint values are
    in radians (standard for robot joint-state representations) and converts to degrees
    for the rubric's threshold comparison -- flagged here since it's an assumption, not
    something independently confirmed against the dataset's units documentation."""
    import numpy as np

    n = min(len(predicted), len(actual))
    if n == 0:
        return {"n_steps": 0, "group_tier": "unscored"}

    max_joint_diff_deg = 0.0
    mean_joint_diffs_deg = []
    for t in range(n):
        pred = np.asarray(predicted[t], dtype=np.float64)
        act = np.asarray(actual[t], dtype=np.float64)
        diff_deg = np.degrees(np.abs(pred - act))
        mean_joint_diffs_deg.append(diff_deg)
        max_joint_diff_deg = max(max_joint_diff_deg, float(diff_deg.max()))

    mean_per_joint = np.mean(np.stack(mean_joint_diffs_deg, axis=0), axis=0)
    if (mean_per_joint >= 15.0).any():
        group_tier = "failure"
    elif (mean_per_joint >= 5.0).any():
        group_tier = "minor_deviation"
    else:
        group_tier = "match"

    return {
        "n_steps": n,
        "mean_per_joint_deg": [round(float(v), 3) for v in mean_per_joint],
        "max_single_joint_diff_deg": round(max_joint_diff_deg, 3),
        "group_tier": group_tier,
    }


def hand_state_bucket(mean_abs_value: float, threshold: float, signal_min: float, signal_max: float) -> str:
    """3-state discrete bucket (open/transitioning/closed) per Section 4.4, using the
    same threshold already fit for ground-truth segmentation. 'Transitioning' is a band
    of +/-15% of the signal's observed range around the threshold."""
    band = 0.15 * (signal_max - signal_min)
    if mean_abs_value < threshold - band:
        return "open"
    if mean_abs_value > threshold + band:
        return "closed"
    return "transitioning"


def score_hand_group(predicted: list[list[float]], actual: list[list[float]],
                      threshold: float, signal_min: float, signal_max: float) -> dict:
    import numpy as np

    n = min(len(predicted), len(actual))
    if n == 0:
        return {"n_steps": 0, "group_tier": "unscored"}

    matches = 0
    for t in range(n):
        pred_mag = float(np.mean(np.abs(predicted[t])))
        act_mag = float(np.mean(np.abs(actual[t])))
        pred_bucket = hand_state_bucket(pred_mag, threshold, signal_min, signal_max)
        act_bucket = hand_state_bucket(act_mag, threshold, signal_min, signal_max)
        if pred_bucket == act_bucket:
            matches += 1

    match_frac = matches / n
    group_tier = "match" if match_frac == 1.0 else ("minor_deviation" if match_frac >= 0.5 else "failure")
    return {"n_steps": n, "match_fraction": round(match_frac, 3), "group_tier": group_tier}


def score_execution_phase(phase_result: dict, segmentation: dict) -> dict:
    predicted = phase_result["predicted_action"]
    actual = phase_result["actual_action"]

    groups: dict[str, dict] = {}
    for key in predicted:
        if key in EXECUTION_WRIST_EEF_KEYS:
            groups[key] = score_wrist_eef_key(predicted[key], actual.get(key, []))
        elif key in EXECUTION_HAND_KEYS:
            groups[key] = score_hand_group(
                predicted[key], actual.get(key, []),
                segmentation["threshold"], segmentation["signal_min"], segmentation["signal_max"],
            )
        elif key in EXECUTION_ARM_WAIST_KEYS:
            groups[key] = score_joint_group(predicted[key], actual.get(key, []))
        # legs (left_leg/right_leg) fall under EXECUTION_ARM_WAIST_KEYS already

    tiers = []
    for key, g in groups.items():
        if key in EXECUTION_WRIST_EEF_KEYS:
            tiers.append(g.get("position_tier", "unscored"))
            tiers.append(g.get("rotation_tier", "unscored"))
        else:
            tiers.append(g.get("group_tier", "unscored"))
    tiers = [t for t in tiers if t != "unscored"]

    if not tiers:
        overall = "unscored"
    elif all(t == "match" for t in tiers):
        overall = "match"
    elif any(t == "failure" for t in tiers):
        overall = "failure"
    else:
        overall = "minor_deviation"

    minor_count = sum(1 for t in tiers if t == "minor_deviation")
    manual_review = len(tiers) > 0 and minor_count >= max(1, int(0.75 * len(tiers)))

    return {
        "groups": groups,
        "overall_tier": overall,
        "manual_review_ambiguous_minor": manual_review,
    }


# ---------------------------------------------------------------------------
# Reasoning-stage scoring (scoring_rubric.md Section 3) -- LLM-as-judge
# ---------------------------------------------------------------------------

def judge_reasoning(client: anthropic.Anthropic, task_instruction: str, reasoning_text: str) -> dict:
    prompt = (
        f"Task given to the robot: \"{task_instruction}\"\n\n"
        f"A model's step-by-step plan for this task:\n{reasoning_text}\n\n"
        "This is a pick-and-place task with exactly three canonical sub-goal phases: "
        "reach (approach and grasp the object), transport (carry the object toward the "
        "target/destination), and retreat (release the object and withdraw). Evaluate "
        "the plan above against these three phases."
    )
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        output_config={"format": {"type": "json_schema", "schema": REASONING_JUDGE_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    result = json.loads(text)

    all_phases_present = all(result["phases_found"].values())
    result["match"] = (
        all_phases_present
        and result["order_correct"]
        and result["object_target_correct"]
        and not result["hallucinated_step"]
        and not result["under_specified"]
    )
    failure_categories = []
    if not all_phases_present:
        failure_categories.append("missing_sub_goal")
    if all_phases_present and not result["order_correct"]:
        failure_categories.append("wrong_order")
    if not result["object_target_correct"]:
        failure_categories.append("wrong_object_target")
    if result["hallucinated_step"]:
        failure_categories.append("hallucinated_step")
    if result["under_specified"]:
        failure_categories.append("under_specified")
    result["failure_categories"] = failure_categories
    return result


# ---------------------------------------------------------------------------
# Core 2x2 classification (scoring_rubric.md Section 5)
# ---------------------------------------------------------------------------

def classify_2x2(reasoning_match_for_phase: bool, execution_tier: str) -> str:
    if execution_tier == "minor_deviation":
        return "minor_deviation"  # tracked separately, not folded into match/failure
    execution_match = execution_tier == "match"
    if reasoning_match_for_phase and execution_match:
        return "success"
    if reasoning_match_for_phase and not execution_match:
        return "intent_lost_in_handoff"
    if not reasoning_match_for_phase and execution_match:
        return "accidentally_correct"
    return "compounding_failure"


# ---------------------------------------------------------------------------
# Main per-episode scoring
# ---------------------------------------------------------------------------

def score_episode(client: anthropic.Anthropic, episode_log: dict) -> dict:
    segmentation = episode_log["segmentation"]
    task_instruction = episode_log["task_instruction"]
    reasoning_text = episode_log["cosmos_reasoning_proxy_text"]

    manual_review_reasons = []
    if not segmentation["segmentation_valid"]:
        manual_review_reasons.append("segmentation_invalid")

    reasoning_result = judge_reasoning(client, task_instruction, reasoning_text)
    if reasoning_result["manual_review_needed"]:
        manual_review_reasons.append("reasoning_hallucinated_or_underspecified")

    phase_classifications = {}
    for phase_name, phase_result in episode_log["phase_results"].items():
        execution_result = score_execution_phase(phase_result, segmentation)
        if execution_result["manual_review_ambiguous_minor"]:
            manual_review_reasons.append(f"{phase_name}_ambiguous_execution")

        reasoning_match_for_phase = bool(reasoning_result["phases_found"].get(phase_name, False))
        classification = classify_2x2(reasoning_match_for_phase, execution_result["overall_tier"])

        phase_classifications[phase_name] = {
            "reasoning_match": reasoning_match_for_phase,
            "execution_tier": execution_result["overall_tier"],
            "execution_groups": execution_result["groups"],
            "classification": classification,
        }

    return {
        "task_folder": episode_log["task_folder"],
        "episode_index": episode_log["episode_index"],
        "task_instruction": task_instruction,
        "segmentation_valid": segmentation["segmentation_valid"],
        "reasoning": reasoning_result,
        "phase_classifications": phase_classifications,
        "manual_review_reasons": sorted(set(manual_review_reasons)),
    }


def write_outputs(scored_episodes: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "scored_episodes.json", "w") as f:
        json.dump(scored_episodes, f, indent=2)

    csv_path = out_dir / "scored_phases.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "task_folder", "episode_index", "phase", "reasoning_match",
            "execution_tier", "classification", "needs_manual_review",
        ])
        for ep in scored_episodes:
            needs_review = len(ep["manual_review_reasons"]) > 0
            for phase_name, pc in ep["phase_classifications"].items():
                writer.writerow([
                    ep["task_folder"], ep["episode_index"], phase_name,
                    pc["reasoning_match"], pc["execution_tier"], pc["classification"],
                    needs_review,
                ])

    counts: dict[str, int] = {}
    total_phases = 0
    for ep in scored_episodes:
        for pc in ep["phase_classifications"].values():
            counts[pc["classification"]] = counts.get(pc["classification"], 0) + 1
            total_phases += 1
    n_manual_review = sum(1 for ep in scored_episodes if ep["manual_review_reasons"])

    print(f"\nScored {len(scored_episodes)} episodes, {total_phases} phase observations.")
    print(f"{n_manual_review} episodes flagged for manual review.")
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        pct = 100.0 * count / total_phases if total_phases else 0.0
        print(f"  {label:28s} {count:4d}  ({pct:.1f}%)")
    print(f"\nWrote {out_dir / 'scored_episodes.json'} and {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-log-dir", required=True, type=Path,
                         help="Directory of per-episode JSON logs from notebooks/02_automated_scoring.ipynb")
    parser.add_argument("--out-dir", default=Path("results"), type=Path,
                         help="Where to write scored_episodes.json and scored_phases.csv")
    args = parser.parse_args()

    log_files = sorted(args.raw_log_dir.glob("episode_*.json"))
    if not log_files:
        raise SystemExit(f"No episode_*.json files found in {args.raw_log_dir}")

    client = anthropic.Anthropic()

    scored_episodes = []
    for log_path in log_files:
        with open(log_path) as f:
            episode_log = json.load(f)
        print(f"Scoring {log_path.name}...")
        scored_episodes.append(score_episode(client, episode_log))

    write_outputs(scored_episodes, args.out_dir)


if __name__ == "__main__":
    main()
