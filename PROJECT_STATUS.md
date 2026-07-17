# Handoff Notes — 2026-07-17 session

**TL;DR:** Phase 2 (environment setup) is done — the full pipeline runs end-to-end on
Colab Pro. Phase 3 (manual smoke test) is in progress. Pick up by running the notebook
from the top (or resuming mid-way via checkpoint) and continuing the manual comparison
in Section 9.

## What changed this session

Started from nothing (no repo) and got to a working GR00T + Cosmos-Reason2 + real G1
data pipeline. Notable technical decisions/fixes, in order:

1. **Dataset pivot:** originally planned around AgiBot World, but discovered GR00T has
   no zero-shot embodiment tag for it (would've needed fine-tuning, which we're not
   doing). Switched to `nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1` — real Unitree G1
   teleop data, matches GR00T's actual `REAL_G1` zero-shot tag.
2. **`REAL_G1` needs a `wrist_eef_9d` state field the raw dataset doesn't have** (only
   raw joint angles are recorded — no public G1 dataset provides this, including
   NVIDIA's own). Added a forward-kinematics step using the official Unitree G1 URDF
   (`unitreerobotics/unitree_ros`) + `pytorch_kinematics` to compute it. Sanity-checked
   (plausible ~0.3m arm reach, finite values) but flagged everywhere as an
   **approximation**, not verified against NVIDIA's internal convention.
3. **Fixed a handful of wrong API assumptions** against the real GR00T/Cosmos-Reason2
   source (import paths, constructor signatures, the Cosmos-Reason2 model class,
   chat-template input format, and a hardcoded language observation key that turned out
   to be dataset-specific, not a fixed literal).
4. **Fixed a nasty numpy install issue on Colab**: gr00t pins `numpy==1.26.4`, Colab
   ships numpy 2.x by default. An in-place downgrade leaves a corrupted mixed install
   (numpy 2.0 renamed an internal directory). Worse, once numpy's compiled extension is
   loaded once in a running kernel, it can't be safely reloaded in-process — a genuine
   restart is sometimes unavoidable. The install cell now detects this specific failure
   mode and tells you plainly when a restart is needed, instead of pretending to fix it
   live.
5. Built Section 9 (Phase 3): compares GR00T's predicted first action step against what
   the human teleoperator actually did next in the same recorded episode.

## Current state

- Notebook: `notebooks/01_environment_setup.ipynb`
- Confirmed working end-to-end: GR00T N1.7 load → Cosmos-Reason2 load → dataset
  download/parse → FK sanity check → full observation build → `get_action()` →
  Cosmos-Reason2 reasoning trace. All produced sensible output on episode 0 of
  `g1-pick-apple` ("Pick up the red apple and place it on the plate").
- Section 9 (predicted-vs-actual comparison) was just added — **not yet run**. That's
  the next thing to execute.
- Checkpointing to Drive works (`checkpoints/phase2_status.json`) — re-running the
  notebook from the top skips anything already done.

## How to pick up

1. Open the notebook fresh in Colab (GPU runtime, ideally High-RAM/80GB A100 — Cosmos-
   Reason2 alone needs ~24GB minimum, GR00T ~16GB, and they're loaded simultaneously).
2. Run top to bottom. Everything through Section 8 (status summary) is confirmed
   working. Section 9 is new — run it and manually check: does the reasoning trace make
   sense for the task, and is the predicted action in a plausible direction relative to
   the actual recorded action?
3. If you hit the numpy restart message: just restart the runtime once and re-run — the
   on-disk fix is already correct by that point, it's a one-time thing.
4. After Section 9 looks reasonable, Phase 3 is done → move to Phase 4 (formal
   match/failure scoring definitions, written before running at scale).

## Known approximations to keep flagged in any output/writeup

- Cosmos-Reason2's reasoning output is a **proxy** for GR00T's actual (inaccessible,
  latent) internal reasoning — not the literal internal state.
- `wrist_eef_9d` values are **forward-kinematics approximations**, not recorded ground
  truth or verified against NVIDIA's internal convention.
