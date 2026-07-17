# Notebooks

Colab-only notebooks. Open each directly in Google Colab (colab.google.com), select a
GPU runtime (A100 preferred, L4 as fallback), and run top to bottom. Each notebook
checkpoints its progress to Google Drive so a disconnected session can resume by
re-running from the top — completed steps are skipped automatically.

- `01_environment_setup.ipynb` — Phase 2: installs dependencies, loads GR00T N1.7 and
  Cosmos-Reason2-2B, pulls a small subset of `nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1`
  (real Unitree G1 teleop data), verifies the data format end-to-end.
