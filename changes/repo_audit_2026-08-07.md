# RetinAnalysis Repo Audit (2026-08-07)

Answers to yas's post-meeting questions (items 1, 4, 5, 7, 9, 10 from her batch of 10).
Items 2/3/6/8 are implementation work, tracked separately and starting once the
remaining clarifications come back.

## 1. Known issues / what could go wrong running these notebooks

**RTMP tag missing from `.globals` files** -- status: handled, not a blocker.
`get_analysis_vcd()` (`vision_utils.py`) catches the specific
`AssertionError: Globals file does not have RTMP tag` and retries the load without
runtime-movie params instead of crashing. `AnalysisChunk.get_noise_params()`
(`analysis_chunk.py`) then assumes no STA cropping happened when RTMP is missing, and
prints a warning every time this fallback is used -- so it's silent-but-flagged, not
silently wrong. RTMP is a white-noise-only tag by design (confirmed by scanning real
`.globals` files: present on genuine white-noise chunks, absent on grating/contrast
chunks, 1:1 correlation, nothing corrupted) -- it turned out to be *consistently*
missing across yas's real experiments, not a rare dead-recording edge case, which is
why this got a real fix instead of just an error message.

**Missing/absent classification files.** `find_classified_noise_chunk()` implements
yas's lab convention automatically: prefers a classified NDF0 chunk, falls back to
NDF1, picks the earliest-recorded if multiple candidates are classified, and prints
every candidate it considered plus which one it picked (so a wrong pick is easy to
spot and override). `plot_mosaics_for_datasets()` skips chunks without a
classification file rather than erroring, and reports once per experiment if *none* of
its chunks are classified.

**Missing `.params` file for a specific sorting version/datafile.** Not really a code
bug -- this happens when a chosen `datafile_name` doesn't actually have valid
`kilosort2.5` (or whichever `ss_version`) output for that experiment, i.e. picking a
datafile that wasn't actually spike-sorted with that algorithm. Comes up as a plain
`FileNotFoundError`-style crash; the fix is picking a real datafile, not a code change.
Worth knowing about since it looks alarming the first time.

**Stale kernel state (not a code bug, but the single most common "why doesn't this
work" this session).** Every demo notebook does `from retinanalysis... import *` (or
similar) near the top. When package code changes underneath an already-running kernel
(e.g. after a `git pull`), the kernel keeps using whatever was imported at its last
start -- new function signatures/behavior won't show up until you **restart the
kernel** and rerun from the top, not just rerun the affected cell. This has caused
several `TypeError: got an unexpected keyword argument` -style errors this session that
looked like real bugs but weren't.

**DataJoint 0.14 -> 2.2.2 migration.** Retinanalysis now requires `datajoint==2.2.2`.
An old DataJoint 0.14 database cannot be upgraded in place -- needs a fresh Docker
container + `ra.populate_database()` after updating the package, not before. Documented
in the README's migration note.

**Windows-specific: matplotlib/Pillow DLL load error** on first `import retinanalysis`.
Fixed by `pip uninstall Pillow && pip install -U Pillow`. Documented in the setup guide
and README.

**Compiler requirement for the `vision-utils` submodule.** It compiles Cython +
pybind11 C++ extensions at install time -- needs Xcode Command Line Tools (Mac) or
Visual Studio Build Tools with the C++ workload (Windows) actually installed, or the
install fails with a compiler error that doesn't obviously say "install a compiler."

**`noise_f1`/`f1_noise_sub` statistical bias (grating F1 noise-subtraction).**
Documented in `tuning.py`'s docstring: short pre-stimulus noise windows make the F1
vector-sum estimator's noise floor scale up (~4.7x inflated over a 0.25s window vs. a
4.0s window in a synthetic all-noise test), making `f1_noise_sub` come out spuriously
negative for essentially every cell. The grating CRF/Naka-Rushton cells default to raw
`f1` instead, matching what yas's own MATLAB scripts always did (none of them subtract
a baseline from F1). This is exactly what item 3a below is aiming to fix properly
(0%-contrast-run baseline instead of the pre-stimulus window).

**Windows filesystem lock quirks (git operations).** Ran into `.git/index.lock` /
`ORIG_HEAD.lock` files that couldn't be deleted, both from this session's sandbox and
independently on yas's own Windows machine. Likely cause: OneDrive (or another
program with the repo folder open) holding a file handle during a git operation. Not a
retinanalysis-specific issue, but worth flagging for any Windows lab member whose
`Users` folder is OneDrive-synced.

## 4. What's actually in `changes/`, and how corrections get handled

`changes/*.md` files are pure documentation -- plain Markdown, never imported or
executed by anything. They have zero effect on notebook/package behavior; they exist
so a human (you, or anyone else who inherits this code) can understand *why* something
looks the way it does without reverse-engineering it from the diff alone.

**Convention:** one file per topic area (e.g. `ei_footprint_data_quality_notes.md`,
`grating_and_contrast_demos_notes.md`), each containing dated `## Update YYYY-MM-DD`
sections, appended to over time -- never edited or deleted. Each section has: **why**
(quoting your actual feedback where relevant), **what changed** (files/functions,
specific enough to diff against), and a **Verification** subsection (what was actually
tested, and what's explicitly NOT yet verified, e.g. "not run against your live
database").

**When you correct me:** a NEW dated entry gets added describing the correction --
existing entries are never rewritten or deleted, even when they turn out to be wrong.
You saw this happen live today: the Naka-Rushton axis went through three states
(0-1 linear ticks -> log-scale with real labels -> reverted to plain original) and all
three are separate, timestamped entries in `grating_and_contrast_demos_notes.md`, each
explaining what was tried and why it got reverted. This means the file is a real audit
trail of the iteration itself, not just a snapshot of the current state -- if something
looks weird months from now, the "we tried X, it didn't work because Y" reasoning is
still there, not silently erased.

**The two odd-looking files** (`claude_changes_2026-07-28.txt`,
`yas_pre_existing_changes_vs_upstream_2026-07-28.diff`) are historical, from before the
per-topic `.md` convention started: the `.txt` is a raw changelog of one day's edits
(superseded by the topic files for anything after), and the `.diff` is a one-time git
diff generated to separate your own pre-existing edits from the original upstream repo
(mostly full of noisy notebook-output diffs, not very readable -- not something to
maintain going forward).

**Where the actual backend functions live:** `src/retinanalysis/` -- specifically
`src/retinanalysis/utils/*.py` (most of the analysis/plotting functions demos call),
`src/retinanalysis/classes/*.py` (`AnalysisChunk`, `MEAPipeline`, `Response`, etc.),
`src/retinanalysis/config/` (DataJoint schema + settings), and
`lib/artificial-retina-software-pipeline/` (the vendored `vision-utils` submodule that
reads Vision's binary files). Every function gets `import`ed into the top-level `ra.`
namespace via `src/retinanalysis/__init__.py`'s `from .utils.X import *` lines -- that's
why notebooks call e.g. `ra.populate_database()` without knowing which file it's
actually defined in.

## 5. What's already in DataJoint, and where

**Schema (`src/retinanalysis/config/schema.py`):** 14 tables --
`Protocol`, `Experiment`, `Animal`, `Preparation`, `Cell`, `EpochGroup`,
`SortingChunk`, `SortedCell`, `CellTypeFile`, `SortedCellType`, `EpochBlock`, `Epoch`,
`Response`, `Stimulus`, plus a peripheral `Tags` table for free-form tagging. Roughly:
`Experiment` -> `Animal` -> `Preparation` -> `Cell` -> `EpochGroup` -> `EpochBlock` ->
`Epoch` -> `Response`/`Stimulus`, with a parallel `SortingChunk` -> `SortedCell` ->
`SortedCellType` branch for spike-sorting/typing output. Most tables carry a generic
`properties`/`attributes` JSON blob alongside their named columns, so h5-metadata
fields that don't have a dedicated column still get preserved.

**Ingestion (`src/retinanalysis/utils/database_pop.py`):** the actual h5/meta/tags
parsing and table-population logic -- `discover_sorting_chunks`,
`append_experiment`/`append_animal`/`append_preparation`/`append_cell`/
`append_epoch_group`/`append_epoch_block`/`append_epoch`/`append_response`/
`append_stimulus`/`append_tags`/`append_sorting_chunk`/`append_celltypefiles`, plus
`gen_tags`/`gen_meta_list`/`parse_data` for finding/reading the source files.

**Top-level entry points (`src/retinanalysis/utils/database_utils.py`):**
`populate_database()` (what you actually call), `reload_experiment_data()` (delete +
repopulate one experiment), `delete_experiments()`, `purge_database()` (wipes
everything).

**Query/search/plotting helpers built on top of the schema
(`src/retinanalysis/utils/datajoint_utils.py`, ~24 functions):** the ones you'll
actually touch from a notebook -- `get_exp_summary`, `search_protocol`,
`get_datasets_from_protocol_names`, `get_noise_chunks_sorted_by_distance`,
`find_datafile_for_protocol`, `find_classified_noise_chunk`, `get_noise_name_by_exp`,
`get_typing_files_for_datasets`, `plot_mosaics_for_datasets`/
`plot_mosaics_for_all_datasets`, `get_epoch_data_from_exp`,
`get_epochblock_query`/`get_epochblock_timing`/`get_epochblock_response_query`/
`get_epochblock_frame_data`/`get_epochblock_amp_data`, plus a handful of smaller
utilities (`populate_ndf_column`, `get_block_id_from_datafile`,
`get_n_cells_of_interest`, `get_stage_frame_rate_by_exp`, `get_display_params_by_exp`,
`find_varying_epoch_parameters`, `add_parameters_col`).

## 7. How easy is this for someone new to get running?

Honest assessment, current state:

**Reasonably good, once you know the steps -- the steps just aren't trivial.**
`install.sh` handles the Python side cleanly (creates the env, installs
`retinanalysis` + the `vision-utils` submodule, creates a `config.ini` placeholder) for
both `uv` and conda. The `RetinAnalysis_Setup_Guide.pdf` now walks through every
prerequisite end to end for both Windows and Mac. That said, there's real friction a
brand-new person will hit that isn't a one-command fix:

- Needs a C/C++ compiler installed *before* running `install.sh` (Xcode CLT / VS Build
  Tools) -- not auto-installed, and the failure mode if it's missing isn't obviously
  "install a compiler."
- Needs Docker Desktop running for anything database-backed, plus a manual step to copy
  `docker-compose.yaml` into its own directory and start it -- not part of
  `install.sh` at all, by design (the installer explicitly doesn't touch Docker/the
  database).
- `config.ini` (real data paths) is 100% manual and per-machine, gitignored on purpose
  -- there's no way to automate this since it depends on how each person's machine
  actually mounts your shared data.
- On Windows specifically: needs Git Bash to run `install.sh` at all (plain
  PowerShell/CMD won't run a bash script), plus the Pillow DLL fix is a real, somewhat
  obscure gotcha.
- Getting an actual visualization on screen requires a *second* setup step beyond
  package install: installing Jupyter into the same environment and launching it --
  not bundled as a dependency (see below).

**Packages needed beyond what `install.sh` already installs, to get a notebook +
visualization running:** just `jupyterlab` (or `notebook`) -- not currently in
`pyproject.toml`'s dependencies, so it's a one-line manual `pip install jupyterlab`
into the same environment after `install.sh` finishes. Everything else a demo notebook
needs (matplotlib, numpy, pandas, scipy, ipywidgets/ipympl for interactive plots,
torch, etc.) is already a hard dependency and gets installed automatically.

**Bottom line:** a new person following the PDF guide start to finish, with no
deviations, should get a working environment -- but it's roughly 15-20 real steps
across multiple tools (git, a compiler, Docker, Python env, Jupyter, config file
editing), not a single "run this and you're done" script. That's mostly inherent to
what this package actually needs (compiled extensions + a local database + real data
paths), not something a smarter installer alone fixes.

## 9. Who can push, and how to add checks and balances

**Right now: only you.** `yasmine-tani/retinanalysis` is your personal GitHub fork --
nobody else has push access unless you explicitly add them as a collaborator (GitHub
repo -> Settings -> Collaborators). Anyone else can still contribute via the standard
GitHub flow without you granting them anything: they fork *your* fork, make changes on
their own copy, and open a pull request against yours, which you then review and merge
(or not) -- this works today with zero setup on your end.

**If you want lab members to have more direct access, options in increasing order of
"formal":**

1. **Stay fork-and-PR only (recommended default).** No collaborators added at all --
   everyone works from their own fork, PRs come to you for review. Simplest, and
   nobody can push anything without you seeing it first.
2. **Add trusted collaborators + branch protection on `main`.** Give specific people
   direct push access, but turn on a branch protection rule (GitHub repo -> Settings ->
   Branches) requiring pull requests into `main` with at least one approval, and
   disallowing direct pushes/force-pushes to `main` -- so even collaborators can't
   silently overwrite `main`, they still go through a reviewed PR.
3. **Add a CI check that has to pass before merging.** A GitHub Actions workflow
   (`.github/workflows/`) that runs on every PR -- at minimum `python -m py_compile` on
   changed `.py` files and `nbformat.validate()` + `compile()` on changed notebooks,
   which catches "this notebook doesn't even parse" before it ever reaches `main`.
   Combine with option 2's branch protection ("require status checks to pass") to make
   it a hard gate, not just a suggestion.

**Should you add tests?** Given most of this codebase is DataJoint-backed (can't
easily unit-test without a live database, and you can't run a real DB in CI without
real experiment data), I'd suggest a pragmatic split rather than trying to
test everything:

- **Pure-logic functions with no DB/file dependency** -- `tuning.py`'s math
  (F0/F1, DSI/OSI, Naka-Rushton fitting), `ei_utils.py`'s significance
  masking/marker-scaling, `contrast_response_utils.py`'s axis-tick logic -- these are
  exactly what's been getting synthetic-tested throughout this session already (fake
  data with known ground truth, `importlib`-loaded so it's testing the real code, not a
  reimplementation). Worth formalizing into real `tests/test_*.py` files that
  `pytest` picks up automatically (there's already a `tests/` dir and a `--dev` install
  flag on `install.sh` that installs `pytest`) -- cheap, fast, no DB needed, and this is
  the kind of test that would have caught the mosaic function's old
  `significance_std` API break immediately if it existed then.
- **Notebook structural checks** -- `nbformat.validate()` + `compile()` on every demo
  notebook, cheap and DB-free, catches "this doesn't even parse" regressions.
- **Don't force true end-to-end DB-backed tests** -- not practical without hosting a
  real DataJoint database + real experiment data in CI, which isn't worth the
  infrastructure cost for a lab-internal tool. Manual verification against the live
  database (which is already how every change this session has been sanity-checked
  before you run it for real) stays the right tool for that layer.

## 10. Does this survive changed stimulus parameters?

**Contrast conditions (count or values):** yes, no code change needed.
`build_trial_response_table` takes `condition_keys` as an argument and pulls whatever
values actually exist in `epoch_parameters` for whatever epochs match `protocol_name`
-- it doesn't assume a specific count or specific values anywhere. `plot_crf`/
`plot_crf_across_ndfs` build their x-axis (ticks, evenly-spaced positions, `[0,1]`
range) from `pop[condition_key].values` -- i.e. from whatever's actually in the data --
so fewer or more contrast levels, or different specific values, just show up correctly
next run.

**White noise square size / grid size:** yes, and more robustly than I expected.
`AnalysisChunk.get_noise_params()` pulls `numXChecks`/`numYChecks`/`gridSize` per epoch
from DataJoint (not hardcoded), and explicitly detects if grid size *changes mid­
recording* -- prints a warning, and (when the RTMP tag is present) uses Vision's own
`micronsPerStixelX` to figure out which epoch block's grid size is the "real" one
rather than guessing. If RTMP is *also* missing in that specific mixed-grid-size
scenario, it raises a clear `ValueError` instead of silently picking one arbitrarily --
so it fails loudly rather than producing a misleadingly-sized STA.

**One real caveat:** a few notebook-level variables assume a specific
`epoch_parameters` KEY NAME, not a specific value -- e.g. `FLASH_CONDITION_KEYS =
['contrast']` is a plain notebook variable, not auto-detected, so if a given protocol's
condition were renamed (e.g. to `'intensity'`) that line would need manual editing.
This is intentional/by design (the notebook cell already has a comment telling you to
verify it against the printed `epoch_parameters` keys), not a limitation of the
underlying extraction code -- but worth knowing it's a manual check, not automatic, if
a protocol's parameter *naming* changes rather than its values.
