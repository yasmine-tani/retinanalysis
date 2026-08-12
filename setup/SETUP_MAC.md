# RetinAnalysis setup — Mac

Everything below runs in **Terminal**.

Skip a step if you already have that tool installed.

## 1. Install Git + a C compiler

```bash
xcode-select --install
```

This installs both Git and `clang` (the C/C++ compiler needed later) in one step.

## 2. Install Docker Desktop

Download the build that matches your chip (Apple Silicon or Intel): https://docs.docker.com/desktop/

Launch it once after installing, then leave it running whenever you need database access.

## 3. Confirm you have conda

```bash
conda --version
```

If that fails, install Miniconda first: https://docs.conda.io/en/latest/miniconda.html

## 4. Clone the repo

```bash
git clone https://github.com/yasmine-tani/retinanalysis.git --recursive
cd retinanalysis
```

## 5. Create the environment and install

```bash
conda create -y -n retinanalysis python=3.11.13
conda activate retinanalysis
pip install -e .
pip install lib/artificial-retina-software-pipeline/utilities/
```

## 6. Set up config.ini

```bash
cp src/retinanalysis/config/config.ini.example src/retinanalysis/config/config.ini
```

Open `src/retinanalysis/config/config.ini` and edit the `[DEFAULT]` section with real paths for this machine, e.g.:

```ini
[DEFAULT]
analysis = /Volumes/Array-data/sorted
data = /Volumes/Array-data/sorted
raw = /Volumes/Array-data/raw
h5 = /Volumes/Array-data/h5
meta = /Volumes/Array-data/dj_meta
tags = /Volumes/Array-data/tags
query = /Volumes/Array-data/sorted
user = your_username
```

`/Volumes/Array-data` is wherever your shared network drive is mounted on this Mac — check Finder → Go → Network (the exact name may differ). `user` is your own username. You only need to fill in `[DEFAULT]` (and `[SECONDARY]` if you actually have a second data location) — leave the other sections alone. `config.ini` itself is gitignored, so this is a one-time edit that `git pull` will never touch or overwrite.

## 7. Start the local database

```bash
mkdir -p ../retinanalysis-database
cp docker-compose.yaml ../retinanalysis-database/
cd ../retinanalysis-database
docker compose up -d
cd ../retinanalysis
```

Docker Desktop must be open for this to work.

## 8. Install Jupyter and launch it

```bash
pip install jupyterlab
jupyter lab
```

## 9. Populate the database

In a notebook cell (any notebook in `demos/`):

```python
import retinanalysis as ra
ra.populate_database()
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'cv2'`** on the very first `import retinanalysis` cell — this is NOT a missing OpenCV install. `opencv-python` is already a listed dependency and gets installed automatically by step 5's `pip install -e .`. This error means Jupyter is running a different Python than the `retinanalysis` environment you just built. Fix:
1. Close Jupyter.
2. In Terminal: `conda activate retinanalysis`
3. `jupyter lab` — launch it from that same activated terminal, not a separate one.
4. Once the notebook is open, check the kernel name in the top-right corner. If it doesn't say `retinanalysis`, click it and switch. If `retinanalysis` isn't in the list at all, run `pip install ipykernel` then `python -m ipykernel install --user --name retinanalysis` inside the activated environment, then refresh the Jupyter tab.

**`pip install lib/.../utilities/` fails with a compiler error** — `xcode-select --install` from step 1 didn't finish. Run it again and wait for it to complete before retrying.

**Database calls fail / connection refused** — Docker Desktop isn't open, or the container isn't running. Open Docker Desktop and check the `retinanalysis-database` container shows a stop icon (running), not a play icon.

**You cloned without `--recursive`** — run `git submodule update --init --recursive`, then redo step 5.
