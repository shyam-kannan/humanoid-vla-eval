# [Draft title] Where Does Intent Get Lost? An Offline Trajectory-Matching Analysis of Reasoning-to-Action Handoff Failures in a Humanoid VLA

**Status: first full draft, 2026-07-20. Numbers below are from a 50-episode run on one
task (`g1-pick-apple`). Placeholders are marked `[TODO]`. Not yet in IEEE LaTeX format —
see note at the end.**

## Abstract

Vision-Language-Action (VLA) models for humanoid manipulation typically decompose into a
high-level reasoning stage that plans a sequence of sub-goals and a low-level action
stage that executes continuous joint-space trajectories. Failures in these systems are
often attributed vaguely to "the model," without distinguishing whether the plan itself
was wrong or whether a correct plan failed to survive the handoff into execution. We
present an offline evaluation methodology that scores these two stages independently
against real teleoperated demonstrations and cross-references them into a joint
classification, isolating the specific failure mode of **intent lost in handoff**: a
correct plan whose execution diverges from the demonstrated trajectory. Applied to GR00T
N1.7 (zero-shot on a real Unitree G1 teleop dataset) with Cosmos-Reason2-2B as a
reasoning-stage proxy, across 50 pick-and-place episodes (150 sub-goal-phase
observations) we find that 68.0% of phase observations show intent lost in handoff (a
correct plan whose execution diverges from the demonstrated trajectory) versus only 3.3%
where both stages fail together, with failure concentrated in continuous joint control
(arm, wrist, or torso deviates from the tightest tolerance in 100% of observations)
rather than discrete grasp-state prediction (deviates in only 18.7%), and rising
monotonically through the task
from 58.0% at the initial reach to 74.0% by the final retreat. We discuss the
methodological limits of trajectory-matching against a single demonstration as a proxy
for task success, and release the scoring pipeline as an open, auditable tool for
pre-deployment diagnosis of VLA planning-execution failures.

## I. Introduction

[TODO: expand with citations] Vision-language-action models increasingly follow a
two-stage architecture inspired by dual-process theories of cognition: a "System 2"
component performs deliberate, language-mediated reasoning to decompose a task
instruction into sub-goals, while a "System 1" component maps the current observation
and sub-goal onto continuous low-level actions. This decomposition is attractive for
interpretability and modularity, but it introduces a specific failure surface that
single-stage, end-to-end policies do not have: the reasoning stage can produce a
completely correct plan that the action stage nonetheless fails to execute faithfully.
We call this failure mode **intent lost in handoff**.

Existing evaluation practice for VLA models typically reports aggregate task success
rate, which conflates planning failures with execution failures and gives no diagnostic
signal about *where* in the reasoning-to-action pipeline a given failure originates. This
is a meaningful gap for humanoid platforms specifically, where whole-body coordination
(balance, torso posture, bimanual coordination) adds execution-stage failure modes beyond
what tabletop single-arm manipulation exposes, and where physical trial-and-error
evaluation is expensive and slow compared to software iteration.

We contribute:

1. An offline evaluation methodology that scores reasoning-stage and execution-stage
   fidelity independently, against ground truth derived directly from real teleoperated
   demonstrations (no simulation, no physical execution required), and cross-references
   them into a 2x2 classification that isolates intent-lost-in-handoff from cases where
   both stages fail together or where an incorrect plan is accidentally executed
   correctly.
2. A concrete instantiation of this methodology on GR00T N1.7 (NVIDIA's whole-body
   humanoid VLA policy) evaluated zero-shot against real Unitree G1 teleoperated
   demonstrations, using Cosmos-Reason2-2B as an explicit, labeled proxy for the
   reasoning stage GR00T does not expose in human-readable form.
3. An empirical failure taxonomy across 50 episodes (150 sub-goal-phase observations)
   showing that execution
   failures concentrate in continuous joint-space control rather than discrete
   grasp-state prediction, and that failure rate increases through the course of a
   pick-and-place task rather than being uniform.
4. [TODO if time permits] Release of the full scoring pipeline as open, auditable
   tooling, including the specific numeric thresholds used and the reasoning behind
   design decisions made after inspecting real per-episode data (e.g., scoring against
   an early prediction window rather than a full open-loop rollout, to isolate immediate
   plan-following from accumulated open-loop drift).

## II. Related Work

[TODO -- needs real citations, this is placeholder scaffolding only]

- VLA models and dual-system architectures: GR00T [TODO cite], OpenVLA [TODO cite],
  RT-2 [TODO cite], pi0 [TODO cite]. Note where each does/doesn't expose an inspectable
  reasoning trace.
- Chain-of-thought / explicit reasoning in embodied models: ECoT [TODO cite], Cosmos-
  Reason [TODO cite].
- Offline evaluation of robot policies against demonstration datasets: [TODO cite --
  imitation learning evaluation literature, action-chunking policy evaluation].
- Humanoid whole-body manipulation benchmarks: [TODO cite].
- Failure taxonomies / error analysis for learned robot policies: [TODO cite].

## III. Method

### III.A. Dataset

We use `nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1`, a public dataset of real (not
simulated) teleoperated Unitree G1 humanoid trajectories in LeRobot format, sampled at
20fps. We evaluate on the `g1-pick-apple` task (pick up a red apple, place it on a
plate) [TODO: note if additional task folders from this dataset -- pear/grapes/
starfruit -- are added before submission for cross-task generalization]. State and
action are 43-dimensional whole-body vectors (legs, waist, both arms, both hands).

### III.B. Models

**Action stage (System 1):** GR00T N1.7 (3B parameters), NVIDIA's whole-body humanoid VLA
policy, loaded zero-shot with `EmbodimentTag.REAL_G1` -- a pretrain tag matched by
construction to this dataset's embodiment, requiring no fine-tuning.

**Reasoning stage (System 2) proxy:** GR00T's own internal reasoning representation is
latent (hidden-state activations), not human-readable. We use Cosmos-Reason2-2B, a
vision-language model sharing backbone lineage with GR00T's internal VLM but released
standalone with natural-language chain-of-thought output, run independently on the same
task instruction and initial frame. **This is an explicit proxy, not GR00T's literal
internal state**, and all results involving the reasoning stage must be read with this
caveat.

### III.C. Ground-truth sub-goal segmentation

The dataset provides one flat task instruction per episode, not labeled sub-goal
boundaries. We derive reach / transport / retreat sub-goal boundaries from the recorded
hand-joint trajectory: a scalar "hand closure" signal (mean absolute value of the 7
hand-joint state dimensions per frame, per hand) is computed for both hands; the hand
with the larger observed range is taken as the grasping hand for that episode (this is
computed from ground-truth recorded data, independent of any model prediction). A grasp
event is the first sustained (>=3-frame) crossing of a per-episode-fit threshold from
below to above; a release event is the following sustained reverse crossing. This splits
each episode into reach (start -> grasp), transport (grasp -> release), and retreat
(release -> end).

### III.D. Execution-stage scoring

For each of the three sub-goal phases, GR00T is queried once at that phase's start frame,
producing a predicted action chunk. This is compared against the actual recorded
teleoperated action for the same window, per body-part group: wrist position (Euclidean
distance, cm), wrist rotation (geodesic angle between predicted and actual rotation
matrices, reconstructed from the 6D continuity representation of Zhou et al.), arm/torso
joint angles (per-joint degree difference), and hand grasp state (discrete
open/transitioning/closed bucket match). [TODO: table of match/minor-deviation/failure
thresholds per dimension, from `docs/scoring_rubric.md` Sections 4.1-4.4]

Only the arm, hand, wrist, and torso of the *grasping* side (plus the shared torso/waist)
drive the phase-level verdict; the idle arm's motion is not commanded by the task and its
prediction error is not evidence of a failed handoff.

Scoring uses only the first 10 predicted steps (~0.5s at this dataset's frame rate), not
the full ~40-step predicted chunk. Inspecting signed per-joint error on real data showed
two distinct phenomena conflated by full-chunk averaging: some joints show error that
grows steadily from near-zero over the open-loop horizon (expected behavior for any
policy evaluated this way, since deployment normally re-plans every few steps rather than
executing a long open-loop rollout), while others show a near-constant offset present
even at the first predicted step (a more direct signal about whether the immediate action
reflects the plan). We report both windows; the early window drives classification.

### III.E. Reasoning-stage scoring

Cosmos-Reason2's step-by-step plan for the task is evaluated once per episode (it
produces one plan up front, not a new plan per phase) via LLM-as-judge (Claude): does the
plan cover all three canonical sub-goal phases, in the correct order, naming the correct
object and target, without hallucinated content or being too vague to map onto the
phases. [TODO: note LLM-judge noise observed in practice -- see Discussion.]

### III.F. Joint classification

Per phase, we cross-reference reasoning-stage match against execution-stage tier:

| | Execution match | Execution failure |
|---|---|---|
| **Reasoning match** | Success | **Intent lost in handoff** |
| **Reasoning failure** | Accidentally correct | Compounding failure |

"Minor deviation" execution results are tracked as a separate category rather than folded
into match or failure.

## IV. Results

Across 50 episodes (150 sub-goal-phase observations, all with valid grasp/release
segmentation):

**Table 1 -- overall classification**

| Classification | Count | % |
|---|---|---|
| Intent lost in handoff | 102 | 68.0% |
| Minor deviation | 43 | 28.7% |
| Compounding failure | 5 | 3.3% |
| Success | 0 | 0.0% |
| Accidentally correct | 0 | 0.0% |

**Table 2 -- classification by sub-goal phase**

| Phase | Intent lost | Minor deviation | Compounding failure |
|---|---|---|---|
| Reach | 58.0% | 42.0% | 0.0% |
| Transport | 72.0% | 26.0% | 2.0% |
| Retreat | 74.0% | 18.0% | 8.0% |

Failure rate rises monotonically through the task: the model's execution is closest to
the demonstrated trajectory immediately after the observation (reach), and diverges
further as the task progresses through transport into retreat.

**Table 3 -- which measured dimension drives failure/minor-deviation** (a phase can
implicate more than one dimension)

| Dimension | Count (of 150) |
|---|---|
| Waist (torso) rotation | 148 |
| Arm joint angles | 145 |
| Wrist position | 145 |
| Wrist rotation | 100 |
| Hand grasp state | 28 |

Discrete grasp-state prediction (hand open/closed) is reliable; continuous joint-space
and pose control (arm, wrist, torso) is where deviation concentrates. This suggests the
model's difficulty is specifically in precise continuous control fidelity, not in
higher-level object-interaction state tracking.

**Table 4 -- reasoning-stage failure categories** (episode-level, n=50)

| Category | Episodes |
|---|---|
| Hallucinated step | 10 (20%) |
| Wrong object/target | 9 (18%) |
| Missing sub-goal | 5 (10%) |

The dominant failure pattern is a correct plan with a failed execution
(`intent_lost_in_handoff`, 68% of observations), not a failure of both stages together
(`compounding_failure`, 3.3%) -- consistent with the reasoning stage (or its proxy) being
comparatively reliable relative to execution-stage trajectory fidelity in this setting. We
manually verified all 3 `compounding_failure` episodes against their raw reasoning
traces and execution numbers (Section [TODO: cross-ref] / `docs/manual_spot_check.md`):
in two, the plan never described a retreat/withdraw step at all; in the third, the plan
described the *plate* moving to meet the apple rather than the reverse -- a clear
reversal of actor and object, not a borderline judge call.

**Table 5 -- how many of the 5 scored dimensions land in the strictest tier
simultaneously, per phase** (arm, hand, wrist position, wrist rotation, waist)

| Dimensions matching | Count | % |
|---|---|---|
| 0 of 5 | 23 | 15.3% |
| 1 of 5 | 75 | 50.0% |
| 2 of 5 | 48 | 32.0% |
| 3 of 5 | 3 | 2.0% |
| 4 of 5 | 1 | 0.7% |
| 5 of 5 | 0 | 0.0% |

No phase in our sample achieves the strictest tier on all 5 dimensions simultaneously,
which explains the 0% strict-success rate in Table 1 -- but the shape of this
distribution is itself informative. If a single overly strict threshold were responsible
(e.g., the torso-rotation tolerance being unreasonably tight relative to what a
well-performing model could achieve), we would expect phases to cluster near 4/5, with
one holdout dimension. Instead the distribution is centered at 1-2/5 (82% of phases), with
only 4 of 150 phases (2.7%) reaching 3 or more. This is consistent with genuinely
independent, non-trivial deviation across multiple continuous-control dimensions at once,
not an artifact of one miscalibrated cutoff.

[TODO: figures -- bar chart of Table 1, stacked bar of Table 2 by phase, bar chart of
Table 5, example frame sequence for a representative intent-lost-in-handoff case with
predicted-vs-actual overlay if time permits]

## V. Discussion and Limitations

**Trajectory-matching is not task-success measurement.** This is the central
methodological caveat of the entire approach and must not be elided: every classification
here measures divergence from *one recorded human demonstration*, not whether the
predicted trajectory would have physically succeeded at the task. A pick-and-place task
generally admits multiple valid solution paths; GR00T predicting a different-but-valid
grasp approach would be scored identically to a genuinely failed grasp under this rubric.
The zero success rate we observe (Table 1) should be read as "GR00T's zero-shot
predictions on this embodiment do not closely track this specific demonstrated
trajectory," not as "GR00T fails to complete this task." Table 5's distribution supports
this being a real measurement of partial trajectory fidelity rather than a rubric
artifact -- most phases achieve 1-2 of 5 dimensions within the strictest tolerance, not
zero, and the shape of the distribution is inconsistent with one miscalibrated threshold
being solely responsible. Grounding the trajectory-fidelity-vs-task-success distinction --
ideally via the physical-consequence proxy layer described below -- is the most important
piece of future work this result motivates.

**Reasoning-stage proxy.** Cosmos-Reason2-2B is used as an explicit, labeled stand-in for
GR00T's internal reasoning, which is otherwise a latent, non-human-readable
representation. Results describing "reasoning-stage" behavior describe this proxy, not a
literal decoding of GR00T's internals.

**Forward-kinematics approximation.** GR00T's `REAL_G1` embodiment expects wrist
end-effector pose (`wrist_eef_9d`) state/action fields that no public G1 dataset,
including this one, records directly. We compute these via forward kinematics from the
official Unitree G1 URDF. This is an approximation not independently verified against
NVIDIA's internal training convention for this field; any bias in that convention should
largely cancel out of the *relative* predicted-vs-actual comparisons this rubric performs
(both sides are computed the same way), but this has not been independently confirmed.

**LLM-as-judge noise.** The reasoning-stage judge showed some inconsistency across calls
in borderline cases -- e.g. an unspecified color descriptor ("teal plate") was judged
harmless elaboration in one episode and flagged as hallucination in others. This is a
known limitation of LLM-as-judge approaches generally rather than specific to this
pipeline, and a source of noise in the reasoning-failure-category counts (Table 4)
specifically, though it does not affect the execution-stage numbers (computed
deterministically from numeric thresholds). We manually re-verified all 3
`compounding_failure` episodes -- the cases most sensitive to judge reliability, since
both stages must be independently correct for that label to be trustworthy -- against the
raw reasoning trace and execution numbers directly; all 3 held up as genuine double-
failures rather than judge noise (`docs/manual_spot_check.md`).

**Single task, single object.** Results here are from one task type
(`g1-pick-apple`) [TODO: update if additional task folders are added before
submission]. The dataset includes three other object types (pear, grapes, starfruit)
under the same task structure; whether the phase-wise failure gradient and the
discrete/continuous split generalize across object geometry is untested.

**Sample size.** 50 episodes / 150 phase observations is a modest sample for a strong
generalization claim; error bars and statistical testing [TODO if time permits] would
strengthen Table 1-4's claims.

**Physical-consequence proxy layer (explicitly out of scope here).** A natural extension
is a kinematic-plausibility layer estimating whether a flagged execution failure
plausibly causes a physical consequence (e.g., a balance-relevant torso deviation, an
unreachable target) -- applied on top of, not in place of, the match/failure
classification above. We deliberately scoped this out of the current submission to
prioritize evaluating at a larger episode count within the available time; it remains
the most direct way to address the trajectory-matching-vs-task-success gap above and is
future work.

## VI. Conclusion

[TODO: 1 paragraph restating the contribution and the headline empirical finding once
final numbers are locked in.]

---

## Notes for finishing this draft

- **Not yet in IEEE LaTeX format.** This is content-first markdown so we could iterate
  fast under time pressure. Once the content above is reviewed/edited, say the word and
  I'll port it into IEEEtran two-column LaTeX (or if there's an existing Overleaf
  project/template, tell me and I'll match it).
- **Double-anonymous**: no author names/affiliations/acknowledgments anywhere in this
  draft yet, on purpose -- add those only in the final camera-ready version, not before
  submission.
- **Figures**: none yet. The strongest candidates given what we have: (1) a bar chart of
  Table 1, (2) the phase-wise gradient from Table 2 as a stacked bar, (3) one annotated
  example frame sequence (we already have `extract_phase_frames` output for episode 0's
  transport phase) showing a representative intent-lost-in-handoff case.
- **Page budget**: IEEE Humanoids main track is 8 pages. This draft, once References and
  figures are added, is roughly Introduction (0.75p) + Related Work (0.75p) + Method
  (1.5p) + Results (1.5p) + Discussion (1.5p) + Conclusion (0.25p) ≈ 6.25p of text before
  figures/tables/references -- should fit with room for 1-2 figures.
