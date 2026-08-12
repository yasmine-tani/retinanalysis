# RetinAnalysis setup — Windows

Everything below runs in **Anaconda PowerShell Prompt**. You don't need Git Bash for any of this.

Skip a step if you already have that tool installed.

## 1. Install Git

Download and run: https://git-scm.com/download/win — accept the defaults.

(This also installs Git Bash. You won't use it — `git` itself works fine from Anaconda PowerShell Prompt after this.)

## 2. Install Docker Desktop

Download and run: https://docs.docker.com/desktop/

Launch it once after installing, then leave it running whenever you need database access.

## 3. Install a C++ compiler

Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/

In the installer, check **"Desktop development with C++"**, then install. (Needed to build one submodule — `vision-utils`.)

## 4. Confirm you have conda

Open **Anaconda PowerShell Prompt** and run:

```powershell
conda --version
```

If that fails, install Miniconda first: https://docs.conda.io/en/latest/miniconda.html

## 5. Clone the repo

```powershell
git clone https://github.com/yasmine-tani/retinanalysis.git --recursive
cd retinanalysis
```

## 6. Create the environment and install

```powershell
conda create -y -n retinanalysis python=3.11.13
conda activate retinanalysis
pip install -e .
pip install .\lib\artificial-retina-software-pipeline\utilities\
```

## 7. Fix a known Windows bug

```powershell
pip uninstall Pillow
pip install -U Pillow
```

(Only actually matters the first time you `import retinanalysis` — if you don't hit a DLL error, you can skip this.)

## 8. Set up config.ini

```powershell
cp src\retinanalysis\config\config.ini.example src\retinanalysis\config\config.ini
```

Open `src\retinanalysis\config\config.ini` and edit the `[WINDOWS_DEFAULT]` section with real paths for this machine, e.g.:

```ini
[WINDOWS_DEFAULT]
analysis = B:\Array-data\sorted
data = B:\Array-data\sorted
raw = B:\Array-data\raw
h5 = B:\Array-data\h5
meta = B:\Array-data\dj_meta
tags = B:\Array-data\tags
query = B:\Array-data\sorted
user = your_username
```

`B:` is whatever drive letter your shared network drive is mapped to on this machine — check File Explorer → This PC. `user` is your own username. You only need to fill in `[WINDOWS_DEFAULT]` (and `[WINDOWS_SECONDARY]` if you actually have a second data location) — leave the other sections alone. `config.ini` itself is gitignored, so this is a one-time edit that `git pull` will never touch or overwrite.

## 9. Start the local database

```powershell
mkdir ..\retinanalysis-database
cp docker-compose.yaml ..\retinanalysis-database\
cd ..\retinanalysis-database
docker compose up -d
cd ..\retinanalysis
```

Docker Desktop must be open for this to work.

## 10. Install Jupyter and launch it

```powershell
pip install jupyterlab
jupyter lab
```

## 11. Populate the database

In a notebook cell (any notebook in `demos/`):

```python
import retinanalysis as ra
ra.populate_database()
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'cv2'`** on the very first `import retinanalysis` cell — this is NOT a missing OpenCV/C++ install. `opencv-python` is already a listed dependency and gets installed automatically by step 6's `pip install -e .`. This error means Jupyter is running a different Python than the `retinanalysis` environment you just built. Fix:
1. Close Jupyter.
2. In Anaconda PowerShell Prompt: `conda activate retinanalysis`
3. `jupyter lab` — launch it from that same activated terminal, not a separate one.
4. Once the notebook is open, check the kernel name in the top-right corner. If it doesn't say `retinanalysis` (or Python 3.11.13 from that env), click it and switch. If `retinanalysis` isn't in the list at all, run `pip install ipykernel` then `python -m ipykernel install --user --name retinanalysis` inside the activated environment, then refresh the Jupyter tab.

**`DLL load failed` on `import matplotlib`** — see step 7.

**`pip install .\lib\...\utilities\` fails with a compiler error** — the C++ Build Tools from step 3 aren't installed, or you need to open a brand new PowerShell window after installing them.

**Database calls fail / connection refused** — Docker Desktop isn't open, or the container isn't running. Open Docker Desktop and check the `retinanalysis-database` container shows a stop icon (running), not a play icon.

**You cloned without `--recursive`** — run `git submodule update --init --recursive`, then redo step 6.
