# humanoid-vla-eval

Offline evaluation of Vision-Language-Action (VLA) models for humanoid whole-body tasks
(balance, bipedal locomotion, dual-arm manipulation). This project investigates where a
VLA's high-level reasoning/planning stage ("System 2") loses intent when handing off to
its low-level action head ("System 1"), measured via offline trajectory matching against
existing labeled robot trajectory datasets — no simulation, no physical execution. The
goal is a failure-mode taxonomy and error breakdown across models and datasets, framed as
a diagnostic tool for catching planning errors before expensive hardware trials.

Target venue: IEEE Humanoids 2026.

## Status

Phase 2 (environment setup) in progress. Selected stack: GR00T N1.7 (action/System1,
`EmbodimentTag.REAL_G1`), Cosmos-Reason2-2B (reasoning proxy/System2), and
`nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1` (real Unitree G1 teleop trajectories) as the
primary dataset. See `notebooks/01_environment_setup.ipynb` and commit history for
details, including why AgiBot World was dropped in favor of this dataset.
