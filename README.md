# RetinAnalysis
MEA and Single Cell Ephys Analysis Package

## Setup

Click your operating system below and follow the steps in order. Skip any step where you already have that tool installed.

<details>
<summary><strong>Windows</strong></summary>

Everything below runs in **Anaconda PowerShell Prompt**, not Command Prompt and not Git Bash. Windows usually installs two similar-looking shortcuts — **Anaconda Prompt** (Command Prompt) and **Anaconda Powershell Prompt** (actual PowerShell) — you want the second one. If you have Miniconda instead of full Anaconda, look for **Anaconda Powershell Prompt (miniconda3)**. You can tell you're in the right one because the prompt starts with `PS`, e.g. `(retinanalysis) PS C:\...>`.

**1. Install Git.** Download and run: https://git-scm.com/download/win — accept the defaults. (This also installs Git Bash — you won't need it; `git` itself works fine from Anaconda PowerShell Prompt after this.)

**2. Install Docker Desktop.** Download and run: https://docs.docker.com/desktop/ — launch it once after installing, then leave it running whenever you need database access (queries, `ra.populate_database()`). Just `import retinanalysis` doesn't need it running.

**3. Install a C++ compiler.** Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/ — in the installer, check **"Desktop development with C++"**, then install. (Needed to build one submodule, `vision-utils`.)

**4. Confirm you have conda.** Open Anaconda PowerShell Prompt and run:
```powershell
conda --version
```
If that fails, install Miniconda first: https://docs.conda.io/en/latest/miniconda.html

**5. Clone the repo:**
```powershell
git clone https://github.com/yasmine-tani/retinanalysis.git --recursive
cd retinanalysis
```

**6. Create the environment and install:**
```powershell
conda create -y -n retinanalysis python=3.11.13
conda activate retinanalysis
pip install -e .
pip install .\lib\artificial-retina-software-pipeline\utilities\
```

**7. Fix a known Windows bug.** The first time this package loads `matplotlib`, Windows can raise a DLL load error. If you hit that:
```powershell
pip uninstall Pillow
pip install -U Pillow
```
If you don't hit the error, skip this.

**8. Set up config.ini.** This file tells the package where your data lives on this machine — it doesn't exist yet, and every machine's paths are different, so you're creating it fresh. From the same PowerShell window (already `cd`'d into the `retinanalysis` folder from step 5):
```powershell
notepad src\retinanalysis\config\config.ini
```
Windows will ask "Cannot find config.ini. Do you want to create a new file?" — click **Yes**. Paste in the block below, edit the `[WINDOWS_DEFAULT]` paths for this machine, then save (Ctrl+S) and close.

> If that doesn't open a blank file to edit, create `config.ini` manually: open Notepad, paste in the block below, then File → Save As, navigate to `src\retinanalysis\config`, set "Save as type" to **All Files** (not "Text Documents" — this avoids accidentally saving it as `config.ini.txt`), and set the file name to exactly `config.ini`.

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

`B:` is whatever drive letter your shared network drive is mapped to on this machine — check File Explorer → This PC. `user` is your own username. Both sections must be present in the file, but you only need real paths under `[WINDOWS_DEFAULT]` — leave `[WINDOWS_SECONDARY]` as placeholder text unless you actually have a second data location; a path that doesn't exist is just skipped. `query` is used by mosaic-plotting across many datasets — it's useful to point it at the NAS analysis dir even when your other paths point at a local SSD, so mosaics can load cell typing from everything on the NAS, not just what's on your SSD. `config.ini` itself is gitignored, so this file stays local to your machine and `git pull` will never touch or overwrite it.

**9. Start the local database.** Docker Desktop must be open for this.
```powershell
mkdir ..\retinanalysis-database
copy docker-compose.yaml ..\retinanalysis-database\
cd ..\retinanalysis-database
docker compose up -d
cd ..\retinanalysis
```

**10. Install Jupyter and launch it:**
```powershell
pip install jupyterlab
jupyter lab
```

**11. Populate the database.** Open any notebook in `demos/` and run in a cell:
```python
import retinanalysis as ra
ra.populate_database()
```

#### Windows troubleshooting

**Can't find "Anaconda PowerShell Prompt", or `'x' is not recognized as an internal or external command, operable program or batch file`** — you're likely in the cmd-based Anaconda Prompt instead of the PowerShell one; see the note at the top of this section. If no PowerShell-flavored shortcut exists at all, open regular Windows PowerShell, run `conda init powershell` once, then close and reopen PowerShell — `conda` will work there directly from then on.

**`ModuleNotFoundError: No module named 'cv2'`** on the very first `import retinanalysis` cell — not a missing install; `opencv-python-headless` is a listed dependency and installs automatically with step 6. This means Jupyter is running a different Python than the `retinanalysis` environment. Close Jupyter, run `conda activate retinanalysis`, then launch `jupyter lab` from that same terminal. Once the notebook is open, check the kernel name in the top-right corner — if it's not `retinanalysis`, switch it (or if it's missing from the list, run `pip install ipykernel` then `python -m ipykernel install --user --name retinanalysis` and refresh).

**`ImportError: DLL load failed while importing cv2`** — rare now that this package uses `opencv-python-headless`, but if it still happens: confirm only one opencv package is installed (`pip list | Select-String opencv` should show exactly one), try a clean reinstall (`pip uninstall opencv-python-headless -y`, `pip cache purge`, `pip install opencv-python-headless --no-cache-dir`), and check whether this is a Windows "N" edition (run `winver`) — N editions ship without the Media Feature Pack, which video-reading code needs; get it here: https://support.microsoft.com/en-us/topic/media-feature-pack-list-for-windows-n-editions-c1c6fffa-d052-8338-7a79-a4bb980a700a

**`DLL load failed` on `import matplotlib`** — see step 7.

**`FileNotFoundError: No config file found at ...`** on `import retinanalysis` — step 8 was skipped, or the file isn't named/placed exactly right. It must be at `src\retinanalysis\config\config.ini` (not `.txt` — make sure File Explorer isn't hiding the real extension). Redo step 8, then restart the kernel.

**`No NAS or SSD paths found, check that one of them is connected`** printed but no crash — `config.ini` exists but still has placeholder paths that don't actually exist on this machine. Open the file and confirm the `[WINDOWS_DEFAULT]` paths point to a drive/folder that's really there.

**`pip install .\lib\...\utilities\` fails with a compiler error** — the C++ Build Tools from step 3 aren't installed, or you need a brand-new PowerShell window opened after installing them.

**Database calls fail / connection refused** — Docker Desktop isn't open, or the container isn't running. Open Docker Desktop and confirm the `retinanalysis-database` container shows a stop icon (running), not a play icon — see the screenshot below.

**Cloned without `--recursive`** — run `git submodule update --init --recursive`, then redo step 6.

</details>

<details>
<summary><strong>Mac</strong></summary>

Everything below runs in **Terminal**.

**1. Install Git and a C compiler:**
```bash
xcode-select --install
```
This installs both Git and `clang` (the C/C++ compiler needed later) in one step.

**2. Install Docker Desktop.** Download the build that matches your chip (Apple Silicon or Intel): https://docs.docker.com/desktop/ — launch it once, then leave it running whenever you need database access.

**3. Confirm you have conda:**
```bash
conda --version
```
If that fails, install Miniconda first: https://docs.conda.io/en/latest/miniconda.html

**4. Clone the repo:**
```bash
git clone https://github.com/yasmine-tani/retinanalysis.git --recursive
cd retinanalysis
```

**5. Create the environment and install:**
```bash
conda create -y -n retinanalysis python=3.11.13
conda activate retinanalysis
pip install -e .
pip install lib/artificial-retina-software-pipeline/utilities/
```

**6. Set up config.ini.** This file tells the package where your data lives on this machine — it doesn't exist yet, so you're creating it fresh. From the same Terminal window (already `cd`'d into `retinanalysis` from step 4):
```bash
nano src/retinanalysis/config/config.ini
```
Paste in the block below, edit the `[DEFAULT]` paths for this machine, then save and exit (Ctrl+O, Enter, Ctrl+X).

> If `nano` isn't available or that doesn't work, create `config.ini` manually: open TextEdit, switch to plain text first (Format menu → Make Plain Text — this matters, since saving from Rich Text mode can corrupt the file), paste in the block below, then save it as exactly `src/retinanalysis/config/config.ini`.

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

[SECONDARY]
analysis = /path/to/secondary/analysis
data = /path/to/secondary/sorted
raw = /path/to/secondary/raw
h5 = /path/to/secondary/h5
meta = /path/to/secondary/meta
tags = /path/to/secondary/tags
query = /path/to/secondary/query
user = your_username
```

`/Volumes/Array-data` is wherever your shared network drive is mounted on this Mac — check Finder → Go → Network (the exact name may differ). `user` is your own username. Both sections must be present, but you only need real paths under `[DEFAULT]` — leave `[SECONDARY]` as placeholder text unless you actually have a second data location. `query` is used by mosaic-plotting across many datasets — point it at the NAS analysis dir even when your other paths point at a local SSD, so mosaics can load cell typing from everything on the NAS. `config.ini` itself is gitignored, so `git pull` will never touch or overwrite it.

**7. Start the local database.** Docker Desktop must be open for this.
```bash
mkdir -p ../retinanalysis-database
cp docker-compose.yaml ../retinanalysis-database/
cd ../retinanalysis-database
docker compose up -d
cd ../retinanalysis
```

**8. Install Jupyter and launch it:**
```bash
pip install jupyterlab
jupyter lab
```

**9. Populate the database.** Open any notebook in `demos/` and run in a cell:
```python
import retinanalysis as ra
ra.populate_database()
```

#### Mac troubleshooting

**`ModuleNotFoundError: No module named 'cv2'`** on the very first `import retinanalysis` cell — not a missing install; `opencv-python-headless` installs automatically with step 5. This means Jupyter is running a different Python than the `retinanalysis` environment. Close Jupyter, run `conda activate retinanalysis`, then launch `jupyter lab` from that same terminal. Check the kernel name in the top-right corner — if it's not `retinanalysis`, switch it (or if it's missing, run `pip install ipykernel` then `python -m ipykernel install --user --name retinanalysis` and refresh).

**`pip install lib/.../utilities/` fails with a compiler error** — `xcode-select --install` from step 1 didn't finish. Run it again and wait for it to complete.

**`FileNotFoundError: No config file found at ...`** on `import retinanalysis` — step 6 was skipped, or the file isn't at exactly `src/retinanalysis/config/config.ini`. Redo step 6, then restart the kernel.

**`No NAS or SSD paths found, check that one of them is connected`** printed but no crash — `config.ini` exists but still has placeholder paths that don't exist on this machine. Confirm the `[DEFAULT]` paths point to something really mounted — check Finder → Go → Network.

**Database calls fail / connection refused** — Docker Desktop isn't open, or the container isn't running. See the screenshot below.

**Cloned without `--recursive`** — run `git submodule update --init --recursive`, then redo step 5.

</details>

<details>
<summary><strong>Linux</strong></summary>

Everything below runs in a Terminal. Commands assume a Debian/Ubuntu system (`apt`) — swap in `dnf`/`pacman`/etc. for other distros.

**1. Install Git and build tools:**
```bash
sudo apt update && sudo apt install -y git build-essential
```

**2. Install Docker Engine.** Follow: https://docs.docker.com/engine/install/ — then let your user run Docker without `sudo`:
```bash
sudo usermod -aG docker $USER
```
Log out and back in for that to take effect.

**3. Confirm you have conda:**
```bash
conda --version
```
If that fails, install Miniconda first: https://docs.conda.io/en/latest/miniconda.html

**4. Clone the repo:**
```bash
git clone https://github.com/yasmine-tani/retinanalysis.git --recursive
cd retinanalysis
```

**5. Create the environment and install:**
```bash
conda create -y -n retinanalysis python=3.11.13
conda activate retinanalysis
pip install -e .
pip install lib/artificial-retina-software-pipeline/utilities/
```

**6. Set up config.ini.** This file tells the package where your data lives on this machine — it doesn't exist yet, so you're creating it fresh. From the same terminal (already `cd`'d into `retinanalysis` from step 4):
```bash
nano src/retinanalysis/config/config.ini
```
Paste in the block below, edit the `[LINUX_DEFAULT]` paths for this machine, then save and exit (Ctrl+O, Enter, Ctrl+X).

```ini
[LINUX_DEFAULT]
analysis = /mnt/Array-data/sorted
data = /mnt/Array-data/sorted
raw = /mnt/Array-data/raw
h5 = /mnt/Array-data/h5
meta = /mnt/Array-data/dj_meta
tags = /mnt/Array-data/tags
query = /mnt/Array-data/sorted
user = your_username

[LINUX_SECONDARY]
analysis = /path/to/secondary/analysis
data = /path/to/secondary/sorted
raw = /path/to/secondary/raw
h5 = /path/to/secondary/h5
meta = /path/to/secondary/meta
tags = /path/to/secondary/tags
query = /path/to/secondary/query
user = your_username
```

`/mnt/Array-data` is wherever your shared network drive is mounted on this machine. `user` is your own username. Both sections must be present, but you only need real paths under `[LINUX_DEFAULT]` — leave `[LINUX_SECONDARY]` as placeholder text unless you have a second data location. `query` is used by mosaic-plotting across many datasets — point it at the NAS analysis dir even when your other paths point at a local SSD. `config.ini` itself is gitignored, so `git pull` will never touch or overwrite it.

**7. Start the local database:**
```bash
mkdir -p ../retinanalysis-database
cp docker-compose.yaml ../retinanalysis-database/
cd ../retinanalysis-database
docker compose up -d
cd ../retinanalysis
```

**8. Install Jupyter and launch it:**
```bash
pip install jupyterlab
jupyter lab
```

**9. Populate the database.** Open any notebook in `demos/` and run in a cell:
```python
import retinanalysis as ra
ra.populate_database()
```

#### Linux troubleshooting

**`ModuleNotFoundError: No module named 'cv2'`** — Jupyter is running a different Python than the `retinanalysis` environment. Close Jupyter, `conda activate retinanalysis`, relaunch `jupyter lab` from that terminal, and check the kernel name in the notebook's top-right corner.

**`permission denied while trying to connect to the Docker daemon socket`** — your user isn't in the `docker` group yet, or you haven't logged out/in since step 2. Run `groups` to check if `docker` is listed; if not, redo step 2's `usermod` command and fully log out and back in (not just close the terminal).

**`FileNotFoundError: No config file found at ...`** — step 6 was skipped, or the file isn't at exactly `src/retinanalysis/config/config.ini`. Redo step 6, then restart the kernel.

**`No NAS or SSD paths found, check that one of them is connected`** — `config.ini` exists but still has placeholder paths. Confirm `[LINUX_DEFAULT]` points at something really mounted (`df -h` or `mount` can help confirm).

**Database calls fail / connection refused** — check the container is actually up: `docker compose ps` from the `retinanalysis-database` folder, or `docker ps` generally.

**Cloned without `--recursive`** — run `git submodule update --init --recursive`, then redo step 5.

</details>

### Checking that the database container is running

However you installed Docker, the local database needs its container running before any database-backed call (queries, `ra.populate_database()`) will work. `import retinanalysis as ra` on its own does not need it running.

In Docker Desktop (Windows/Mac), open the app and look at the `retinanalysis-database` container: a stop icon means it's running; a play icon means it's stopped and needs starting.

<img width="1382" height="832" alt="Docker Desktop showing the retinanalysis-database container running" src="https://github.com/user-attachments/assets/45ee0d03-6dd7-48c4-ad38-c75e558259ed" />

On Linux (Docker Engine, no GUI), run `docker compose ps` from inside the `retinanalysis-database` folder instead.

## Running RetinAnalysis day to day

Once setup is done, starting a normal session is just:

```bash
conda activate retinanalysis
cd retinanalysis
jupyter lab
```

**Getting updates:**
```bash
git pull
pip install -e .   # only needed if dependencies changed
```

## Advanced: using uv instead of conda

[uv](https://docs.astral.sh/uv/) is a fast, Rust-based alternative to conda for managing the Python environment. It works at the project level rather than system-wide — the environment lives in a `.venv` folder inside the repo itself. Use this instead of the conda steps above if you already know uv and prefer it; the rest of setup (Docker, config.ini, populating the database) is identical either way.

```bash
git clone https://github.com/yasmine-tani/retinanalysis.git --recursive
cd retinanalysis
uv venv --python 3.11.13
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e .
uv pip install lib/artificial-retina-software-pipeline/utilities/   # Windows: .\lib\artificial-retina-software-pipeline\utilities\
```

Then continue from the config.ini step for your OS above.

## Shortcut: install.sh

`install.sh`, included in this repo, bundles several of the manual steps above (create the environment, install retinanalysis and the submodule, create a placeholder `config.ini` if one doesn't exist) into a single command. It's a bash script, so it works out of the box on Mac and Linux Terminal; on Windows it needs Git Bash or WSL, which is why the Windows steps above don't use it. If you're on Mac/Linux and want the shorter path instead of the manual steps:

```bash
./install.sh conda            # or: ./install.sh uv
./install.sh conda --dev --env retinanalysis   # optional flags
./install.sh uv --python 3.11.13
```

It does not run `git submodule update`, and it does not create, populate, or migrate the database — you still need the `git clone --recursive` and Docker/populate steps above. If something fails partway through, the manual steps make it easier to see exactly which command broke, which is why they're the default recommendation above.

## Upgrading from an older version (DataJoint 2 migration)

Retinanalysis now uses `datajoint==2.2.2`. If you have an existing install from before this change: reinstall or update retinanalysis in your analysis environment, create a fresh local DataJoint/MySQL database (use the Docker steps above to initialize a new one), and repopulate it (`ra.populate_database()`) *after* retinanalysis has been updated. Do not try to update an old DataJoint 0.14 database in place.

We recommend doing this in a fresh conda or uv environment, and keeping the old database and retinanalysis installation around until you've confirmed the updated version isn't causing issues in your analysis code.

## Optional: datajoint.json

Retinanalysis provides fallback local DataJoint settings for the common lab workflow, but DataJoint 2 will warn you if it doesn't find a `datajoint.json` file in your project root. You can safely ignore this warning, but if you want to make the connection explicit and avoid it, create a `datajoint.json` file in the root of your analysis project:

```json
{
  "database.host": "127.0.0.1",
  "database.port": 3306,
  "database.user": "root",
  "database.password": "simple"
}
```

Project-level `datajoint.json`, environment variables, or explicit `datajoint.config` settings take precedence over retinanalysis' local fallback settings.
