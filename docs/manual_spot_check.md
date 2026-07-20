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

**Pass 1 (2026-07-20, video-based, 15-episode run).** Episode 0's `transport` phase --
see below, inconclusive (waist-driven, not in frame).

**Pass 2 (2026-07-20, numeric-based against raw predicted/actual data, 50-episode run).**
5 episodes / 15 phases, chosen for coverage: 2 "typical" episodes (0, 4) and all 3 of the
`compounding_failure` cases with the most reasoning-judge scrutiny value (22, 26, 35),
since those are where the reasoning judge and execution scorer both have to be right for
the label to be trustworthy. Method: read the reasoning trace in full, recompute
`score_execution_phase` directly from the raw `predicted_action`/`actual_action` arrays
(not the pre-aggregated summary), and check whether the numbers driving each verdict are
internally consistent (varying, physically plausible magnitudes -- not suspiciously
identical or degenerate, which would suggest a pipeline bug rather than real model error).

| Episode | Phase | Label | Driving group(s) | Assessment |
|---|---|---|---|---|
| 0 | transport | intent_lost_in_handoff | `waist` (joint 0, 16.87° vs 15° cutoff) | Inconclusive (video pass) -- torso not in frame, see note below |
| 0 | reach | minor_deviation | arm, wrist position, waist all minor | Numbers internally consistent, no bug |
| 0 | retreat | intent_lost_in_handoff | arm (31.7°), wrist pos (8.4cm), wrist rot (20.1°) all failure | Numbers internally consistent, no bug |
| 4 | reach | intent_lost_in_handoff | wrist position (8.0cm, failure); arm/waist only minor | Numbers internally consistent, no bug |
| 4 | transport | minor_deviation | arm, wrist position, waist all minor | Numbers internally consistent, no bug |
| 4 | retreat | minor_deviation | arm, wrist pos, wrist rot, waist all minor | Numbers internally consistent, no bug |
| 22 | reach | minor_deviation | arm, wrist position, waist all minor | Numbers internally consistent, no bug |
| 22 | transport | compounding_failure | arm (24.7°), hand (failure), wrist pos (7.8cm) all failure | **Reasoning check: legitimate.** Plan never describes a retreat/withdraw step (ends at "release the apple onto the plate") -- genuine missing_sub_goal, not judge noise. Execution independently failure-tier. Double-failure confirmed real. |
| 22 | retreat | intent_lost_in_handoff | arm (36.1°), wrist pos (12.5cm) failure | Numbers internally consistent, no bug |
| 26 | reach | intent_lost_in_handoff | arm (33.8°), wrist pos (9.5cm) failure | Numbers internally consistent, no bug |
| 26 | transport | compounding_failure | arm minor, hand (failure), wrist pos (10.5cm), wrist rot (23.6°), waist (16.2°) all failure | **Reasoning check: legitimate**, same pattern as episode 22 -- plan ends at "ensure the apple is stable and properly placed," no withdraw step described. Execution independently and severely failure-tier (4 of 5 groups failing, not just barely over threshold like episode 0). Double-failure confirmed real. |
| 26 | retreat | intent_lost_in_handoff | arm, wrist pos, wrist rot all failure | Numbers internally consistent, no bug |
| 35 | reach | minor_deviation | arm, wrist position, waist all minor | Numbers internally consistent, no bug |
| 35 | transport | compounding_failure | arm minor, hand (failure), wrist pos (10.1cm), waist (18.4°) failure | **Reasoning check: legitimate, and the most striking finding of this pass.** The plan has the apple lifted by the *left* arm, then describes the **plate** moving to meet the apple ("align the plate with the apple's new location... lower the plate to receive the apple") instead of the apple moving to the plate -- a genuine object/actor reversal, not a borderline judge call. Separately (not currently scored, just observed): the plan's claimed grasping arm (left) doesn't match the ground-truth active hand (right) for this episode -- a real reasoning-stage handedness error on top of the object-reversal one. Execution independently failure-tier. Double-failure confirmed real. |
| 35 | retreat | intent_lost_in_handoff | arm (24.8°), wrist pos (8.3cm), wrist rot (22.6°) failure | Numbers internally consistent, no bug |

**Conclusion after 16 phases across 6 episodes: no new bugs found, and the 3
`compounding_failure` cases specifically checked all hold up as genuine double-failures
under scrutiny, not reasoning-judge noise.** The "teal plate" inconsistency noted
earlier remains the one known source of reasoning-judge noise, and it did not affect any
of the 3 compounding_failure cases checked here.

## Still to check / revisit

- [ ] At least one phase classified `success`, to confirm the pipeline isn't just
      over-eager to flag failures -- check that a `success` phase's video also looks
      genuinely clean, not just "not obviously bad." **Currently blocked: 0 of 150
      phases in the 50-episode run landed as `success` -- see `docs/paper_draft.md`
      Discussion for why this is expected given the strict aggregation rule, not
      necessarily a pipeline problem, but it means this check can't be done until/unless
      a `success` case exists in a future run.**
- [ ] Any phase where `full_horizon_tier` and `execution_tier` (early-window) disagree
      sharply -- e.g. early window is `match` but full horizon is `failure`. Useful for
      sanity-checking that the horizon split (Section 4 of the rubric) is capturing a real
      phenomenon (drift) and not hiding something that matters within the early window
      too.
- [ ] Revisit whether the `waist` joint ordering assumption (joint 0 = `waist_yaw`, per
      the URDF) is right -- still unconfirmed. Pass 2 was numeric, not visual, so it
      didn't add evidence either way on this specific question; would need a video check
      with the torso actually in frame (a different camera crop/task) to resolve.
- [ ] Episode 0's `transport` phase (the original waist-driven, camera-inconclusive case)
      remains formally unresolved -- not urgent given Pass 2 found no supporting evidence
      of a pipeline bug elsewhere, but flagged here so it isn't forgotten if the
      waist-joint-ordering question above ever gets resolved.

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
