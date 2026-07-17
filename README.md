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

Research and dataset/model selection in progress. See project issues and commit history
for current phase.
