# PROJECT_AIT3040-

Prototype for early detection and warning of maritime collision risk using AIS data and deep learning.

Status: Initial project setup. Residual-GRU M5a will be implemented and trained again in this repository.

The locked dataset `final_dataset_1.0` is kept locally in `DATASET_FINAL/` and is not committed to GitHub. Its existing Train/Validation/Test splits will be used without resplitting.

## Repository structure

- `configs/`, `contracts/`: shared configuration and interfaces.
- `src/`: data, models, training, evaluation, risk, and utilities.
- `backend/`, `frontend/`: application components.
- `artifacts/`: local checkpoints and scalers, plus shareable manifests.
- `scripts/`, `tests/`, `results/`: supporting scripts, tests, and results.

## Responsibilities

- Trung: model, risk and alerts, encounter and inference components, and model artifacts.
- Toàn: AIS ingestion and replay, track management, data/replay APIs, and map and replay controls.
- Shared components and integration are coordinated by both members.


## Environment setup

Use Python 3.12 (64-bit). From the repository root on Windows:

```powershell
py -3.12 -m venv .venv
# Choose one PyTorch build, then install the remaining dependencies:
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
# For a compatible NVIDIA GPU, use this command instead of the CPU command:
# .\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m pip check
```

Copy `.env.example` to `.env` if local configuration is needed. Set `DATASET_ROOT` to the local dataset directory; relative paths are resolved from the repository root. `.env` is ignored by Git. The smoke test uses synthetic data and reads the locked Train split only.


## Dataset loader

`configs/data_config.yaml` defines the locked contract. `DATASET_ROOT` can override the default `./DATASET_FINAL`; relative paths resolve from the repository root. An explicit `dataset_root` argument takes precedence.

```python
from src.data.dataset_loader import DatasetLoader
from src.data.vessel_dataset import VesselDataset
from src.data.encounter_dataset import EncounterDataset

train = DatasetLoader().load_split("train")
vessel_sample = VesselDataset(train)[0]       # unscaled history and anchor-relative target
encounter_sample = EncounterDataset(train)[0] # model_input, ground_truth, metadata kept separate
```

Run the read-only dataset smoke test and unit tests from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_test_dataset.py
.\.venv\Scripts\python.exe -m pytest tests/unit/test_dataset_loader.py -v
```

The smoke test checks Test structure and index metadata only. It writes a small report under `results/s1_t01/`, never into the dataset.

## Notebooks and tensor verification

Install notebook dependencies with `python -m pip install -r requirements-dev.txt` in the virtual environment. Start JupyterLab with `.\.venv\Scripts\python.exe -m jupyterlab` and choose the environment's Python kernel. Set `DATASET_ROOT` as described above when needed.

- `notebooks/01_dataset_overview.ipynb`: dataset structure and Train/Validation overview.
- `notebooks/02_feature_tensor_analysis.ipynb`: feature, tensor, reconstruction and input-isolation checks.

Run `.\.venv\Scripts\python.exe scripts/verify_tensor_contract.py` for the shared contract checks; run `.\.venv\Scripts\python.exe -m pytest tests/unit -v` for unit tests. Re-execute both notebooks with `.\.venv\Scripts\python.exe scripts/execute_notebooks.py`; it uses a temporary kernel bound to this environment.
