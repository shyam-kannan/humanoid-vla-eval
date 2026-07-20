# Manual spot-check: how to sanity-check the automated scoring

Before trusting the automated pipeline's verdicts at scale (running across many more
episodes), spot-check a handful of already-scored episodes by hand. The goal is a simple
question per phase: **does what actually happened in the video roughly match the
`success` / `minor_deviation` / `intent_lost_in_handoff` / `compounding_failure` label
the pipeline gave it?**

This is a sanity check on the *pipeline*, not a way to move the numbers. If a spot-check
disagrees with the label, that's a signal to look for a bug or a miscalibrated threshold
(see `docs/scoring_rubric.md`'s revision history — several real bugs were found exactly
this way). It is never a reason to change a label by hand or loosen a threshold just to
make the disagreement go away — see the note at the bottom of this document.

## What you need

From a completed run of `notebooks/02_automated_scoring.ipynb`, on Drive:

- `results/scored_phases.csv` and `results/scored_episodes.json` — the scored output
- `raw_logs/episode_XXXXXX.json` — one file per episode, has the predicted/actual
  numbers, the derived grasp/release frame indices, and Cosmos-Reason2's reasoning text
- The episode videos, already downloaded under
  `data/g1_teleop_subset/g1-pick-apple/videos/chunk-000/observation.images.ego_view/`

## Step 1 — Pick episodes to check

Open `scored_phases.csv` and pick a small, deliberately mixed sample — not just the
worst-looking ones. A reasonable first batch:

- 1-2 phases classified `intent_lost_in_handoff` (the primary finding — check this most)
- 1 phase classified `success`
- 1 phase classified `minor_deviation`
- Any phase with `needs_manual_review = True` (these were already flagged by the
  pipeline itself — Section 6 of `docs/scoring_rubric.md`)

Note the `episode_index` and `phase` (`reach` / `transport` / `retreat`) for each one.

## Step 2 — Extract the exact frames

Run Section 17 of `notebooks/02_automated_scoring.ipynb` (`extract_phase_frames`) for
each episode/phase you picked:

```python
extract_phase_frames(episode_index=0, phase_name='transport')
```

This does three things at once:
- Saves PNGs of the exact frame range that was actually scored (the phase's
  `early_step_count`-step window, plus a few frames of padding on each side) to
  `spot_check_frames/` on Drive — decoded sequentially, so it's frame-exact, not a
  browser-scrubbed approximation.
- Prints the task instruction.
- Prints Cosmos-Reason2's full reasoning trace for that episode.

Only Section 0 (Drive mount) needs to have run first — no GPU, no model loading.

## Step 3 — Look at the frames

Download `spot_check_frames/` (or view it directly if you're in Colab) and look at the
sequence of images for the phase you're checking. Ask, in order:

1. **Does the scene match the task?** Is there a red apple, a plate, roughly where the
   task instruction says?
2. **Does the reasoning trace make sense** given what's in the frames? Does it name the
   right object/target, in a sensible order?
3. **Does the robot's arm/hand look like it's doing what the phase name says** — reaching
   toward the object, carrying it, or releasing and withdrawing?

## Step 4 — Cross-reference the numbers

Open `scored_episodes.json`, find that episode's `phase_classifications.<phase_name>`,
and look at `execution_groups`. Find whichever group(s) drove the `failure` or
`minor_deviation` verdict (check `active_side` first — only that side's `arm`, `hand`,
`wrist_eef_9d`, and `waist` drive the verdict; see Section 4.5 of the rubric) and read
off which specific number tripped it, e.g.:

```
"waist": {"mean_per_joint_deg": [16.87, 5.46, 1.85], "group_tier": "failure"}
```

Then ask: **does that specific joint/dimension look visibly wrong in the frames**, or
does the arm/waist look basically fine to the eye and the number seems to be flagging
something too subtle to see? Both are useful outcomes — a visible mismatch corroborates
the label; a subtle number with no visible problem is worth flagging as a possible
threshold-calibration issue (not a correctness bug) for later review, since the rubric's
own thresholds are explicitly marked as provisional pending exactly this kind of check.

## Step 5 — Record the result

Keep a running note (a markdown table works fine) of every phase you check:

| Episode | Phase | Label | Agree? | Notes |
|---|---|---|---|---|
| 0 | transport | intent_lost_in_handoff | yes | waist visibly drifts off-plane in frames 50-57 |
| 3 | reach | minor_deviation | yes | close call, arm looks slightly early |

A handful of episodes (5-10 phases) checked this way is normally enough to decide
whether the pipeline is trustworthy at the current scale, before scaling up to more
episodes (`docs/scoring_rubric.md` Section 7 and the project's later "run at scale"
step).

## What to do if a spot-check disagrees with the label

Treat it as a bug report against the pipeline, the same way the earlier scoring bugs
were found and fixed (see the git history and `docs/scoring_rubric.md`'s revision notes
for examples: an idle-arm aggregation bug, a video-frame seek precision issue, a
full-horizon-averaging methodology issue, and a manual-review display bug were all found
this way). Concretely:

1. Write down exactly what disagreed and why (which frames, which number, which
   threshold).
2. Look for a root cause in the code — a wrong assumption, a unit mismatch, an
   aggregation rule that doesn't fit this case.
3. Fix the actual cause, verify the fix against real data (not just synthetic examples),
   and re-run scoring.

**Do not** hand-edit a classification in the output, and do not adjust a threshold with
the specific goal of making a disagreement disappear rather than because the check
revealed the threshold was measuring the wrong thing. The whole point of this pipeline is
an honest measurement of where reasoning-to-action intent gets lost -- a threshold tuned
to produce a predetermined answer isn't a more accurate pipeline, it's a broken one.
