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

This file tells the package where your data actually lives on this machine — it doesn't exist yet, and every machine's paths are different, so you're creating it fresh. Create a new file at `src\retinanalysis\config\config.ini` and paste in the block below, then edit the `[WINDOWS_DEFAULT]` section with real paths for this machine:

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

[WINDOWS_SECONDARY]
analysis = C:\path\to\secondary\analysis
data = C:\path\to\secondary\sorted
raw = C:\path\to\secondary\raw
h5 = C:\path\to\secondary\h5
meta = C:\path\to\secondary\meta
tags = C:\path\to\secondary\tags
query = C:\path\to\secondary\query
user = your_username
```

`B:` is whatever drive letter your shared network drive is mapped to on this machine — check File Explorer → This PC. `user` is your own username. Both sections must be present in the file (the package reads both on startup), but you only need to fill in real paths under `[WINDOWS_DEFAULT]` — leave `[WINDOWS_SECONDARY]` as placeholder text unless you actually have a second data location; a path that doesn't exist is just skipped. `config.ini` itself is gitignored, so this file stays local to your machine and `git pull` will never touch or overwrite it.

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

**`FileNotFoundError: No config file found at ...`** on `import retinanalysis` — step 8 was skipped, or the file isn't named/placed exactly right. It must be at `src\retinanalysis\config\config.ini` (not `.txt`, not `config.ini.txt` — make sure File Explorer isn't hiding the real extension). Create it as described in step 8, then restart the kernel and re-run.

**`No NAS or SSD paths found, check that one of them is connected`** printed but no crash — `config.ini` exists but still has placeholder paths (e.g. `B:\Array-data\sorted`) that don't actually exist on this machine. Open the file and confirm the `[WINDOWS_DEFAULT]` paths point to a drive/folder that's really there — check File Explorer → This PC for the right drive letter.

**`pip install .\lib\...\utilities\` fails with a compiler error** — the C++ Build Tools from step 3 aren't installed, or you need to open a brand new PowerShell window after installing them.

**Database calls fail / connection refused** — Docker Desktop isn't open, or the container isn't running. Open Docker Desktop and check the `retinanalysis-database` container shows a stop icon (running), not a play icon.

**You cloned without `--recursive`** — run `git submodule update --init --recursive`, then redo step 6.
