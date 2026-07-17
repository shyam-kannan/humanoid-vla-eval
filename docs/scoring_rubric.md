# Scoring rubric

Written before running at scale, so failure categories aren't redefined after seeing
results. Thresholds below are calibrated against the one real example inspected by hand
(`g1-pick-apple`, episode 0) and against physically-motivated reference scales (object
size, teleoperation noise) — not tuned on a larger sample yet. Revisit after the manual
spot-check step, but the *categories* themselves should not change post-hoc, only the
numeric cutoffs if the spot-check shows they're miscalibrated.

## 1. Terminology

- **Reasoning output**: Cosmos-Reason2's numbered sub-goal list for a given task +
  frame. A *proxy* for GR00T's actual (inaccessible) internal reasoning — see main
  README caveat.
- **Action output**: GR00T's predicted action chunk (40 steps × per-body-part deltas) for
  a given observation.
- **Ground-truth sub-goals**: since the dataset only has one flat task string per
  episode (not pre-segmented sub-goals like the originally-considered AgiBot dataset),
  we derive them ourselves — see Section 2.
- **Ground-truth action**: the actually-recorded `action` field in the dataset at each
  frame (what the human teleoperator commanded next).

## 2. Deriving ground-truth sub-goals

The dataset has no labeled sub-goal segments, only a flat instruction ("pick up the red
apple and place it on the plate"). We derive segment boundaries from the recorded hand
joint trajectory, since grasp/release are the clearest, most reliable signal of a
sub-goal transition in a pick-and-place task:

1. Compute a scalar "hand closure" signal per timestep: mean absolute value of the 7
   hand joint dimensions (per hand).
2. A **grasp event** = the closure signal crosses from below to above a threshold (to
   be fit from the data's own distribution — e.g. a fraction of the observed max
   closure — not hardcoded blind) and stays above it for a minimum dwell time (avoids
   single-frame noise triggering a false segment).
3. A **release event** = the reverse crossing.
4. This splits each episode into three canonical sub-goals for a pick-and-place task:
   **reach** (start → grasp event), **transport** (grasp event → release event),
   **retreat** (release event → end).
5. Each derived sub-goal's ground-truth label is a short fixed phrase depending on the
   task's named object/target (parsed from the flat task string, e.g. "reach the red
   apple", "transport red apple to the plate", "retreat from the plate").

This is a coarser 3-way decomposition than Cosmos-Reason2's typical 6-7 step output —
reasoning-stage scoring (Section 3) maps the model's steps onto these 3 canonical phases
rather than requiring an exact step-count match.

## 3. Reasoning-stage (System 2) scoring

For each derived sub-goal phase, check whether Cosmos-Reason2's step list contains at
least one step whose described action+target semantically matches that phase (matching
done by an LLM-as-judge call or keyword/embedding match — implementation detail for
Phase 5, not fixed here).

**Match**: all three canonical phases (reach, transport, retreat) are represented, in
the correct relative order, referencing the correct named object and target.

**Failure categories** (a reasoning output can have more than one):
- **Missing sub-goal**: a canonical phase has no corresponding step at all.
- **Wrong order**: all phases present but in the wrong sequence.
- **Wrong object/target**: correct phase structure, but names an object or destination
  not present in the task (e.g. task says "apple" and "plate", plan mentions "bowl").
- **Hallucinated step**: a step describing an action/object not grounded in the
  task or visible scene (flagged for manual review if we can't verify from the frame
  alone — see Section 6).
- **Under-specified**: plan is too vague to map onto any canonical phase confidently
  (e.g. a single step like "complete the task") — flagged for manual review, not
  auto-scored either way.

## 4. Execution-stage (System 1) scoring

Compared per body-part group, since different joints have different natural precision.
The **comparison unit** is GR00T's full predicted action chunk against the actual
recorded frames following the same observation (not just the first predicted step,
which Section 3 only used for the one-off manual check).

### 4.1 Wrist position (from `wrist_eef_9d`, first 3 dims)

Distance in meters between predicted and actual wrist position.

| Tier | Threshold | Rationale |
|---|---|---|
| Match | < 3cm | Smaller than half a typical graspable object's radius (~7-8cm apple) |
| Minor deviation | 3–7cm | Plausibly still graspable, not exact |
| Failure | > 7cm | Likely to miss the target physically |

Note: both predicted and ground-truth wrist positions are computed via the same
forward-kinematics approximation (Section on FK in the main notebook), so any constant
bias in our FK convention should largely cancel out of this *relative* comparison, even
though neither absolute value is independently verified.

### 4.2 Wrist rotation (from `wrist_eef_9d`, last 6 dims)

Convert both predicted and actual 6D rotation representations back to rotation
matrices, compute the geodesic angular difference in degrees (not a raw vector
distance, which isn't physically interpretable).

| Tier | Threshold |
|---|---|
| Match | < 10° |
| Minor deviation | 10–20° |
| Failure | > 20° |

### 4.3 Arm / waist joint angles

Per-joint angular difference in degrees.

| Tier | Threshold |
|---|---|
| Match | < 5° |
| Minor deviation | 5–15° |
| Failure | > 15° |

A body-part group (e.g. "left arm", 7 joints) is scored **match** if all joints are
match-tier, **failure** if any single joint is failure-tier, **minor deviation**
otherwise. (Calibration note: in the one example reviewed by hand, the single largest
individual-joint miss was ~8.6° on the waist — minor-deviation tier under this scale,
consistent with the overall prediction reading as "good but not exact.")

### 4.4 Hands (grasp state)

Hands are scored as a **discrete state match**, not a continuous threshold — gripper
behavior is closer to binary (open / closing / closed) than continuously meaningful at
the single-joint level.

Derive a grasp state (open / transitioning / closed) from the mean hand-joint magnitude
using the same threshold-fitting approach as Section 2. Match if predicted and actual
fall in the same state bucket at each compared frame.

### 4.5 Combining body-part groups into one phase-level verdict

**Revised after the first automated pass** (see project notes) — the original rule was
"the phase fails if any single body-part group fails." Run against real data, that rule
produced a near-uniform failure verdict across every episode and phase: this task is
single-handed, so the arm/hand *not* doing the grasping isn't commanded to go anywhere in
particular, and its natural noisy drift was consistently failure-tier — which then
poisoned the verdict for phases where the actually task-relevant arm/hand tracked well.

The phase-level verdict is now driven only by the **active side** (the arm, hand, and
wrist_eef of whichever hand `active_hand` — Section 2 — identifies as the grasping hand)
plus the **waist** (shared by both arms' reach). The idle side's per-group scores are
still computed and logged in full, just excluded from the match/minor-deviation/failure
roll-up. If a future task genuinely requires both hands, this assumption needs revisiting
before running this rubric on it.

## 5. The core classification (the actual research output)

Cross-reference Section 3 (reasoning) and Section 4 (execution) per sub-goal phase, per
trajectory:

| | Execution match | Execution failure |
|---|---|---|
| **Reasoning match** | Success | **Intent lost in handoff** — the primary failure mode this project is built to find |
| **Reasoning failure** | Accidentally correct — action compensated for a bad plan | Compounding failure — can't attribute specifically to the handoff, both stages wrong |

"Minor deviation" execution results are tracked separately (not folded into match or
failure) so we can report a graded picture, not just a binary pass rate.

**"Unscored"** is a fifth, distinct outcome — not a fifth cell in the table above. It
means there wasn't enough comparable data to judge the phase at all (e.g. zero
overlapping frames between the predicted chunk and the actual recording), and must never
be silently treated as a failure. An earlier version of the classification code did not
check for this and would fold "not measured" into "compounding failure" or "intent lost
in handoff" — fixed; see the manual-spot-check note in Section 6.

## 6. Manual-review triggers (not auto-scored)

Flag for human review rather than auto-tagging when:
- A reasoning step is "under-specified" (Section 3) or "hallucinated" and we can't
  verify grounding from the frame without a person looking at it.
- Any body-part group's execution score is "minor deviation" for most of the groups that
  drive the phase-level verdict (Section 4.5's active-side groups: arm, hand, wrist
  position, wrist rotation, waist) — ambiguous overall trajectory, not clearly a clean
  match or failure. Implemented as 75% of those groups being minor-deviation-tier, which
  for the standard 4-way conceptual grouping this rubric originally described (wrist
  position, wrist rotation, joint angles, hands) works out to the same "3 of 4" the text
  above once said — the code's actual group breakdown is more granular (arm and waist
  scored separately, wrist position/rotation scored separately), so the percentage is the
  more accurate description now.
- A phase is compared against fewer than 3 overlapping predicted/actual timesteps
  (typically `retreat`, near the very end of a short episode) — too little data for a
  match/minor-deviation/failure verdict to mean anything. Distinct from the segmentation
  trigger below: this is about too few *frames*, not a bad grasp/release split.
- The derived ground-truth sub-goal segmentation (Section 2) produces phases that don't
  sum to a plausible fraction of the episode length (signals a bad grasp/release
  detection, not a real model failure).

**Video/state frame alignment.** The reach observation point is always frame 0 (no
seek needed); transport and retreat start mid-episode, where a naive video-frame seek
(`cv2`'s `CAP_PROP_POS_FRAMES`) can land on the nearest keyframe rather than the exact
requested frame for H.264-encoded video, desyncing the video GR00T sees from the state
row pulled at the same index. Fixed by reading and discarding frames sequentially up to
the start frame instead of seeking directly — guaranteed frame-exact, and cheap given how
short these episodes are (~100 frames).

## 7. Explicitly out of scope here

The physical-consequence proxy layer (does a flagged execution failure plausibly cause
a balance loss or unreachable target) is a separate, later addition — kinematic/stability
heuristics applied *on top of* whatever this rubric flags as a failure, not part of the
match/failure definitions above. Must stay labeled as an estimate everywhere it appears,
never presented as a measured physical outcome.
