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

## Checked so far

| Episode | Phase | Label | Driving group(s) | Visually confirmed? | Notes |
|---|---|---|---|---|---|
| 0 | transport | intent_lost_in_handoff | `waist` (joint 0, 16.87° vs 15° cutoff) | Inconclusive | Everything else in the group (both wrists, both hands, both arms) was match/minor_deviation. The waist/torso isn't in frame in this camera's crop (only hands + apple + plate are visible), so the one thing driving the verdict can't be visually confirmed or denied from video alone -- see the write-up in conversation history around 2026-07-20 for the full reasoning. Not a bug: `score_joint_group`'s "any single joint fails the group" rule is `docs/scoring_rubric.md` Section 4.3's own explicit design, and the phase-level "any group fails the phase" rule was a deliberate choice kept as-is (see "Aggregation rule" note below). |

## Still to check / revisit

Pick up here for the next spot-check pass -- aiming for the 5-10 phase sample size
Step 5 recommends, mixed across labels:

- [ ] **Episode 4, `reach`** (`intent_lost_in_handoff`, driven by `left_wrist_eef_9d`
      position at 7.13cm / rotation 11.1°) -- good next candidate specifically *because*
      wrist position is visible in this camera's framing (unlike episode 0's waist-driven
      case), so this one can actually get a real visual confirm/deny rather than another
      inconclusive result.
- [ ] At least one phase classified `success`, to confirm the pipeline isn't just
      over-eager to flag failures -- check that a `success` phase's video also looks
      genuinely clean, not just "not obviously bad."
- [ ] At least one `minor_deviation` phase, to see whether "close but not quite" verdicts
      look like reasonable close calls by eye.
- [ ] Any phase where `full_horizon_tier` and `execution_tier` (early-window) disagree
      sharply -- e.g. early window is `match` but full horizon is `failure`. Useful for
      sanity-checking that the horizon split (Section 4 of the rubric) is capturing a real
      phenomenon (drift) and not hiding something that matters within the early window
      too.
- [ ] Once a few more phases are checked: revisit whether the `waist` joint ordering
      assumption (joint 0 = `waist_yaw`, per the URDF) is actually right -- if a future
      spot-check on a *visible* waist rotation confirms or contradicts a `waist`-driven
      verdict, that's indirect evidence for or against trusting the joint-0-is-yaw
      assumption on the episode-0 case above too.

## Aggregation rule -- decided, not to be revisited per-outcome

`score_execution_phase`'s "any active-side group failing fails the phase" rule was
deliberately kept as-is after episode 0's transport case (2026-07-20), rather than
loosened to something like "2 of N groups must fail." Reasoning: it's the direct,
consistent extension of the rubric's own explicit within-group rule (any single joint
fails the group -- Section 4.3), and changing it specifically because it produced an
inconvenient result on one case examined during spot-checking would be exactly the kind
of outcome-driven tuning this document argues against above. If this rule gets revisited
later, it should be for a reason independent of any specific phase's result -- e.g. a
pattern across many spot-checked phases showing the strict rule is systematically
miscalibrated, not a reaction to one case.
