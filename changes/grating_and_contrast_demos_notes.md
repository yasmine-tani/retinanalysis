# Grating DS/OS + contrast-response demos (2026-07-28)

**Who made these changes:** Claude (Cowork), working from yas's instructions. New
functionality, not an edit to anything yas had already built -- see "Provenance" in
`mosaic_dedup_and_autotyping_notes.md` for how Claude's changes vs. yas's own prior
edits are tracked overall.

## Summary

Added support for two protocols that had zero support anywhere in `retinanalysis`
before this: drifting-grating direction/orientation selectivity (DS/OS), and
contrast-response (F1 vs. contrast). This adds one new module
(`src/retinanalysis/utils/tuning.py`) and two new demo notebooks
(`demos/6_grating_dsos_demo.ipynb`, `demos/7_contrast_response_demo.ipynb`).

**Important, please read before trusting the notebooks:** I do not have access to your
DataJoint database or `B:\Array-data` from this environment. The math in
`tuning.py` (F1/F0 extraction, DSI/OSI, Naka-Rushton fitting) was unit-tested against
synthetic data with known ground truth, and the notebook cells' *logic* was separately
verified by running the exact same code against synthetic `stim_block`/`response_block`
objects shaped like the real ones. But the notebooks themselves have never been run
against your live database -- I can't confirm the exact `protocol_name` string for the
DS/OS stimulus, or that `epoch_parameters` in your DB actually has the keys I assumed.
Both notebooks print the raw `epoch_parameters` keys for you to check early on, before
anything downstream depends on them.

## What's new

- `src/retinanalysis/utils/tuning.py` (new file, wired into `ra.` namespace via
  `__init__.py`):
  - `compute_f1_f0(rate, bin_rate, stim_freq)` -- FFT-based extraction of the mean
    (F0) and fundamental-frequency amplitude (F1) of a firing-rate trace, e.g. the
    response to a drifting grating at its temporal frequency.
  - `compute_dsi_osi(orientations_deg, responses)` -- standard vector-sum direction
    selectivity index (DSI, 360-degree periodic) and orientation selectivity index
    (OSI, 180-degree periodic, doubled-angle), plus preferred direction/orientation.
    This is the field-standard circular-statistics definition -- you said you didn't
    have an established convention already, so this was the default; flag it if you
    want something different.
  - `fit_naka_rushton(contrasts, responses)` -- fits `R(c) = baseline + Rmax *
    c^n / (c^n + c50^n)` via `scipy.optimize.curve_fit`, returns fitted params plus
    R-squared.
  - All three were tested against synthetic data with known ground truth (exact
    sinusoid for F1, a perfectly single-direction-tuned cell and an
    orientation-but-not-direction-tuned cell for DSI/OSI, and a clean + noisy
    Naka-Rushton curve for the fit) -- see Verification below.

- `demos/6_grating_dsos_demo.ipynb` (new): finds grating datasets via
  `get_datasets_from_protocol_names('grating')`, builds a pipeline for one
  experiment/datafile (defaults to `20260227A`/`data012`, the example data you
  copied), prints the raw `epoch_parameters` keys for verification, bins spikes with
  the protocol-agnostic `bin_spike_times_at_rate` (no stimulus regen needed -- F1/DSI/
  OSI only need spike timing + the stored stimulus parameters), extracts F1 per
  (cell, trial), averages across repeats per (cell, spatial frequency, temporal
  frequency, orientation), computes DSI/OSI per (cell, spatial frequency, temporal
  frequency), and plots an example cell's polar tuning curve plus a DSI-vs-OSI scatter
  across all cells for one stimulus condition.

- `demos/7_contrast_response_demo.ipynb` (new): same overall approach, for
  `ContrastResponseGrating` (defaults to `20260227A`/`data000`). Extracts F1 per
  (cell, trial), averages per contrast level, **normalizes each cell to its own max
  F1 = 1** (per your request), fits Naka-Rushton to each cell's normalized curve, and
  plots an example cell's fitted curve plus a population C50 histogram. Cells with
  zero measurable response at every contrast are dropped (reported as
  `n_cells_dropped`) rather than causing a divide-by-zero.

## Update: fixed after yas ran demo 6 against the real database

Two things confirmed by actually running this against your DataJoint server (which I
don't have access to): the DS/OS protocol name is exactly
`manookinlab.protocols.GratingDSOS` (there's also a `manookinlab.protocols.GratingMTF`
protocol that showed up in the same search -- not covered by either demo). And
`20260227A` -- the experiment I inspected sorted files for -- **is not itself in the
DataJoint database**, only its sorted files were copied locally for me to look at, so
`create_mea_pipeline('20260227A', ...)` fails with `DataJointError: fetch1 should only
return one tuple. 0 tuples found`. Both notebooks' default `exp_name`/`datafile_name`
were updated to real datasets confirmed present in your `grating_search`/
`contrast_search` results: demo 6 now defaults to `20250910A`/`data003` (GratingDSOS,
NDF 4.0), demo 7 to `20260505A`/`data015` (ContrastResponseGrating, NDF 0.0). Both
notebooks' "Choose an experiment" cells now say this explicitly and list a couple of
alternative real datasets you can swap in instead.

## What I could NOT verify from here (please check)

- The exact DataJoint `protocol_name` string for the DS/OS grating stimulus --
  `data012_GratingDSOS.npy`'s pre-extracted `trial_parameters` never included a
  `protocol_name` field at all, unlike the contrast-response file (which had
  `'manookinlab.protocols.ContrastResponseGrating'` verbatim). Demo 6's dataset-search
  cell does a broad `'grating'` substring search and prints all matching
  `protocol_name` values -- **edit `ds_os_protocol_name` in the "Choose an experiment"
  cell to whatever the real one turns out to be.**
- Whether `ContrastResponseGrating`/the DS/OS protocol are actually populated in your
  DataJoint database at all, and with the parameter key names I assumed (`orientation`,
  `contrast`, `spatialFrequency`, `temporalFrequency`, `barWidth`) -- these came from
  the pre-extracted `_unified.npy`/`_GratingDSOS.npy` files in the `20260227A` folder
  you copied, which were produced by a separate script outside `retinanalysis`, not
  necessarily reflecting what `populate_database()` stores. Both notebooks print
  `epoch_parameters` keys early specifically so you can catch a mismatch immediately
  rather than deep into the analysis.
- Epoch-index alignment between `stim_block.df_epochs` and
  `response_block.binned_spikes`'s epoch axis -- I'm relying on the same
  row-order-matches-epoch-index assumption demo 1 already relies on (e.g. its
  space-constant plot indexed `spike_counts` by a boolean mask built from
  `stimulus_data`'s row order), not introducing a new assumption, but flagging it
  since it's still an assumption.

## Verification

- `python -m py_compile src/retinanalysis/utils/tuning.py` and
  `src/retinanalysis/__init__.py` both pass.
- `tuning.py`'s three functions were unit-tested standalone against synthetic data
  with known ground truth (clean + noisy sinusoid for F1/F0; a perfectly
  single-direction-tuned cell, an orientation-only-tuned cell, and a flat/untuned
  cell for DSI/OSI; clean + noisy Naka-Rushton curves for the fit) -- all recovered
  the true parameters within tight tolerances.
- Both notebooks' `ast.parse()`-checked for syntax errors -- clean.
- Both notebooks' actual cell logic (not a re-implementation -- the literal code from
  the notebook cells) was run end-to-end against synthetic `df_epochs`/
  `binned_spikes` objects shaped like the real `stim_block`/`response_block` (same
  columns, same array shapes, epochs shuffled out of order to catch any ordering
  bugs): demo 6's logic correctly identified a known direction-selective cell
  (DSI=0.79, preferred direction recovered to within 15 degrees of the true 90
  degrees) out of a population where the other cells were unstructured noise; demo
  7's logic correctly recovered the true C50 (within 0.03) and true exponent `n`
  (within 0.6) for four cells sharing the same underlying tuning curve but scaled to
  different absolute firing rates, confirming the per-cell normalization works as
  intended.
- **Not verified: an actual run against your live DataJoint database.** That's the
  one thing I can't do from here -- please run both notebooks and let me know what
  breaks, starting with the printed `epoch_parameters` keys.

## Update 2026-07-29: demo 6 rewritten to match Kai's `DS-OS.ipynb` convention; bug fix; `compute_f1_f0_from_spikes` added

**Bug found and fixed first:** cell 5 of demo 6 (the "choose an experiment" code
cell) still had the OLD `exp_name = '20260227A'` / `datafile_name = 'data012'`
values, even though the markdown cell right above it already said these had been
switched to `20250910A`/`data003` after your real-database run. This was a leftover
from an edit that didn't actually get applied to the code cell -- confirmed from
your own saved run output still sitting in the file: cell 5 raised
`DataJointError: fetch1 should only return one tuple. 0 tuples found` (expected,
since `20260227A` isn't in the DB), which cascaded into cell 8's
`NameError: name 'n_epochs' is not defined` (nothing downstream ever ran). Fixed:
cell 5 now actually contains `20250910A`/`data003`. Also fixed cells 2/3's
inconsistency (markdown said "broad substring search" but the code had narrowed to
`'gratingDSOS'` only) -- reverted the search term to `'grating'` so it still
surfaces `ContrastResponseGrating`/`GratingMTF` for reference, matching what the
markdown already described.

**New function, `src/retinanalysis/utils/tuning.py`:**
- `compute_f1_f0_from_spikes(spike_times, stim_freq, duration_s)` -- the direct
  spike-time vector-sum method for F0/F1 (no binning): `phases = 2*pi*f*t; f1 =
  2*|sum(exp(i*phases))|/duration`. This matches the convention in yas's lab's
  existing MATLAB code exactly. Added alongside the existing `compute_f1_f0`
  (binned-FFT method) per yas's request to keep both available for comparison,
  rather than picking one. Unit-tested against synthetic Poisson spike trains with
  a known ground-truth rate/F1 (300 trials, both methods unbiased, means within ~3%
  of true values, and closely agreeing with each other trial-by-trial).

**Demo 6 rewritten (cells 8 onward replaced)** to match the DS/OS convention in
`DS-OS.ipynb`, a reference notebook from your labmate Kai that you uploaded, instead
of the F1-based approach the first version used:

- **DSI/OSI now computed from mean firing rate, not F1.** New cell builds
  `mean_rate` (spike count in the stimulus window / `stimTime`, from raw spike
  times) for every (cell, trial) alongside both F1 methods (`f1_binned`/`f0_binned`
  via `compute_f1_f0`, `f1_spiketime`/`f0_spiketime` via the new
  `compute_f1_f0_from_spikes`) -- the F1 columns are kept for comparison/QC and
  later contrast-response work, but `mean_rate` is what feeds DSI/OSI, matching
  Kai's notebook.
- **One (spatialFrequency, temporalFrequency) condition per cell**, chosen as
  whichever condition gives that cell's highest peak mean rate across orientations
  -- ported from Kai's population-sweep loop. The first version instead computed a
  separate DSI/OSI per (cell, sf, tf) combination; this version picks one "best"
  condition per cell like Kai's does.
- **Thresholds, taken directly from Kai's notebook, not invented here:**
  `DSI_THRESHOLD = 0.3`, `OSI_THRESHOLD = 0.3`, `MIN_RESPONSE_HZ = 2.0`.
- **`ds_cells`/`os_cells` are mutually exclusive**, matching Kai's exact filter:
  `os_cells` requires `dsi <= DSI_THRESHOLD` in addition to `osi > OSI_THRESHOLD`,
  so a strongly direction-selective cell is never double-counted as
  orientation-selective.
- New "Total Cells / DS candidates / OS candidates" summary print (this was the
  original ask -- "counts + polar plots for all/many cells").
- New calibration-plot cell: DSI histogram + threshold line, DSI-vs-peak-rate
  scatter, OSI histogram + threshold line, DSI-vs-OSI scatter colored by
  classification -- ported from the equivalent cells in Kai's notebook.
- New "smart clock" plotting cell: ported and generalized Kai's `plot_smart_clock`
  (his cell 6) to loop over the top 3 DS cells and top 3 OS cells (not just one),
  and to read from the DataJoint-pipeline dataframes built above
  (`df_trials`/`df_metrics`/`spike_times_by_cell`) instead of his raw
  `_GratingDSOS.npy` file. Center polar plot of mean rate vs. orientation at the
  cell's best condition, with a red arrow (DS, pointing at preferred direction) or
  blue axis line (OS, along preferred orientation) depending on which index is
  stronger; satellite raster subplots around the edge, one per orientation,
  positioned at that orientation's angle, stimulus window shaded.

### Verification (2026-07-29 round)

- `compute_f1_f0_from_spikes` unit-tested against synthetic Poisson spike trains
  with known ground-truth rate (20 Hz) and F1 (12 Hz): recovered f0=20.07±1.38,
  f1=12.33±2.02 over 300 trials, matching `compute_f1_f0` on the same spike trains
  (binned) closely trial-by-trial.
- Notebook JSON re-validated with `nbformat.validate()` (not just `json.load` --
  catches nbformat-spec violations like the markdown-cell-with-outputs bug from the
  first round) -- passes. All 16 code cells compile cleanly (`compile(src, ...,
  "exec")`, no syntax errors).
- The DSI/OSI classification logic (best-condition selection, thresholds,
  mutual-exclusivity) was tested standalone against synthetic tuning curves with
  five planted cells: a strong DS cell, an OS-only cell (symmetric response at 0
  and 180 degrees from its axis), an untuned but active cell, a DS-shaped cell with
  too low a firing rate to pass `MIN_RESPONSE_HZ`, and a borderline-DSI cell.
  Correctly classified DS-only, OS-only, correctly excluded the untuned and
  low-rate cells, and confirmed `ds_cells`/`os_cells` never overlap.
- The **literal notebook cell source** (extracted from the saved `.ipynb`, not a
  reimplementation) was `exec()`'d against synthetic `df_epochs`/`response_block`
  objects shaped like the real ones (same columns/attributes: `protocol_name`,
  `epoch_parameters`, `preTime`, `stimTime`; `binned_spikes`, `cell_ids`,
  `n_epochs`, `df_spike_times`), with three planted cells (DS, OS-only, untuned)
  across 2 spatial/temporal-frequency conditions and 3 repeats each (216 total
  trial rows): the "build df_trials" cell, the DSI/OSI population-sweep cell, the
  calibration-plots cell, and the smart-clock plotting cell all ran without errors,
  and the classification cell correctly recovered the planted ground truth (DS cell
  -> `ds_cells`, OS cell -> `os_cells`, untuned cell -> neither).
- **Real-data check (2026-07-29, using the mounted `20260227A` folder):** yas
  pointed out I do have file access to that folder even without DataJoint, so I
  loaded `data012_GratingDSOS.npy` directly (671 clusters, 240 trials) and ran the
  exact same math (mean_rate extraction, `compute_f1_f0_from_spikes`,
  `compute_dsi_osi`, best-condition selection, Kai's thresholds/mutual-exclusivity)
  against the real `trial_parameters`/`spike_times_by_trial` in that file. This also
  independently confirmed my assumed `epoch_parameters` keys are exactly right:
  `orientation`, `spatialFrequency`, `temporalFrequency`, `barWidth`, `preTime`,
  `stimTime`, `tailTime` are all present verbatim in `trial_parameters[0]` (no
  `protocol_name` key, consistent with what I noted before). Result: 84 DS
  candidates and 35 OS candidates out of 671 clusters, correctly mutually
  exclusive, DSI range [0.001, 0.970] mean 0.151, OSI range [0.000, 0.901] mean
  0.148, peak rates [0.04, 75.76] Hz -- all physically reasonable distributions
  (not degenerate at 0 or all clustered at 1), for real spike data.

  **Caveat:** this bypasses DataJoint entirely -- it reads `spike_times_by_trial`/
  `trial_parameters` straight from the pre-extracted `.npy` file, not through
  `create_mea_pipeline`/`stim_block.df_epochs`/`response_block.bin_spike_times_at_rate`/
  `response_block.df_spike_times` the way the actual notebook does. So it validates
  the F1/DSI/OSI *math* and the classification *logic* against real data, and
  confirms the parameter key names, but it does NOT validate the DataJoint
  plumbing itself (whether `20250910A`/`data003` -- the notebook's actual default --
  is populated the same way, whether `bin_spike_times_at_rate` produces equivalent
  results, etc.). Still recommend actually running the notebook.

- **Still not verified: an actual run against your live DataJoint database** --
  same caveat as before. Please run it and let me know what (if anything) breaks.

## Update 2026-07-29 (later): RTMP crash root-caused; new `find_classified_noise_chunk()` picker added

You ran demo 6 for real and hit `AssertionError: Globals file does not have RTMP
tag, cannot load runtime movie parameters` inside `create_mea_pipeline`, even after
the exp_name/datafile_name bug fix above.

**Root cause:** `create_mea_pipeline` always builds an `AnalysisChunk` from
whatever it thinks is the "nearest" white-noise chunk (for RF/cell-typing data),
using a time-proximity heuristic. That auto-picked chunk's `.globals` file
happened to be missing the RTMP tag -- a tag Vision only writes for chunks it
successfully processed as spatial/white noise (it stores parameters for
regenerating that exact noise movie). I checked every `.globals` file in your
`20260227A` example folder directly (parsed the chunk-tag format used by
`visionloader.GlobalsFileReader`, which is vendored in this repo at
`lib/artificial-retina-software-pipeline/utilities/visionloader/visionloader.py`)
and found a clean, expected pattern: RTMP present on exactly the 6 chunks with
`.sta`/`.params` files (`data001,003,005,007,009,011` -- genuine white-noise runs),
absent on exactly the 7 grating/contrast chunks (`data000,002,004,006,008,010,012`
-- never white noise, so Vision never writes RTMP for them). Nothing in that
folder looked corrupted or unexpected.

So the crash on your real experiment means whatever chunk got auto-picked as
"nearest" either (a) wasn't really a completed/successful white-noise run (matches
what you described: NDF0 sometimes dies mid-recording, in which case NDF1 gets
classified instead, or multiple NDF0 attempts exist with different white-noise
parameters), or (b) the time-proximity heuristic just isn't the right way to pick
a chunk for your lab's actual convention.

**Fix, per your explicit instructions:** added `find_classified_noise_chunk()` to
`src/retinanalysis/utils/datajoint_utils.py` (auto-exported as
`ra.find_classified_noise_chunk`, no `__init__.py` change needed -- the module is
already wildcard-imported). It implements the convention you described: prefer the
white-noise chunk at NDF 0 that has a classification file; if NDF 0 was never
classified, fall back to NDF 1 (printing that it did so); if more than one chunk
at the chosen NDF has a classification file, use the earliest one by start time and
print every candidate found plus which one was picked; print the chosen chunk's
full stimulus parameters; return `None` (with a clear printed reason) if neither
NDF 0 nor NDF 1 has a classified chunk, rather than guessing further.

Deliberately does **not** instantiate `AnalysisChunk` to check for classification
files (unlike `plot_mosaics_for_datasets`, which does and just catches/skips
load failures) -- doing that here would incorrectly reject a genuinely classified
NDF0/NDF1 chunk that happens to lack the RTMP tag, before ever finding out it was
classified, since `AnalysisChunk.__init__` crashes on the RTMP load before
reaching typing-file logic. Instead it does a plain filesystem check (same
"filename contains 'classification', case-insensitive" rule as
`plot_mosaics_for_datasets`) via the existing `_resolve_vision_data_path()` helper
in `vision_utils.py`.

Demo 6's "choose an experiment" cell now calls this instead of relying on
`create_mea_pipeline`'s default chunk auto-detection, and passes the result in as
`analysis_chunk_name=...` (a parameter `create_mea_pipeline` already accepted, just
wasn't being used). Added `MANUAL_ANALYSIS_CHUNK = None` right above it, per your
request, so you can hardcode a specific chunk name instead if you ever want a
different one than what gets auto-picked.

**What this does NOT fix:** if your auto-picked NDF0/NDF1 classified chunk itself
still lacks the RTMP tag (i.e. it really was classified, but its `.globals` file
is still incomplete for some other reason), `create_mea_pipeline` will still crash
at the same `AssertionError` -- `find_classified_noise_chunk()` only makes the
*selection* deterministic and correct per your convention, it doesn't make
`AnalysisChunk` tolerate a missing RTMP tag once a chunk is chosen. I did NOT
implement that separately (making `get_analysis_vcd`/`AnalysisChunk.get_noise_params()`
degrade gracefully) yet, since it would require guessing a fallback for the STA
grid size (`staXChecks`/`staYChecks`, normally read from the RTMP data) that could
silently misalign spatial maps for a chunk that legitimately has RTMP-independent
issues -- flagged this as a decision point for you rather than assuming an answer.
If you hit the RTMP crash again on a chunk that `find_classified_noise_chunk()`
picked (i.e. one that DOES have a classification file), let me know and I'll
revisit this.

### Verification

- `find_classified_noise_chunk()` was tested against 4 synthetic scenarios (not
  live data, since I have no DB access): a single classified NDF0 chunk (picked
  correctly), multiple classified NDF0 chunks (earliest picked, all candidates
  printed), NDF0 present but unclassified with NDF1 classified (correctly falls
  back and prints why), and neither NDF0 nor NDF1 classified (correctly returns
  `None` with a clear message). Ran the actual function code (loaded the real
  `datajoint_utils.py` file, not a reimplementation) with `get_exp_summary`/
  `get_noise_name_by_exp`/`schema.Epoch`/`_resolve_vision_data_path`/`os.listdir`
  swapped for synthetic stand-ins shaped like the real ones.
- `python -m py_compile src/retinanalysis/utils/datajoint_utils.py` passes.
- Notebook re-validated with `nbformat.validate()` and all cells re-compiled after
  the edit -- passes.
- **Not verified: an actual run against your live DataJoint database**, same
  caveat as always -- I don't have access to it. This should get you further than
  before, but I can't promise it clears the RTMP error entirely if your NDF0/NDF1
  classified chunk itself has an incomplete `.globals` file.

## Update 2026-07-29 (later still): datafile_name auto-detected too, search narrowed to GratingDSOS only

Per yas: "even for this like i shouldnt need to put the data file name it should
find the gratingdsos run and the cell before it shoud only search for the dss
gratings." Two more manual inputs removed:

- **Cell 2/3 (dataset search)**: no longer a broad `'grating'` substring search
  (which also pulled in `ContrastResponseGrating` and `GratingMTF`). Now searches
  exact-match for `manookinlab.protocols.GratingDSOS` only, via
  `ra.get_datasets_from_protocol_names('manookinlab.protocols.GratingDSOS',
  b_exact_match=True)`. `grating_search` now only ever contains GratingDSOS rows.
- **New function, `find_datafile_for_protocol(df_exp_search, exp_name,
  protocol_name=None, verbose=True)`** in `datajoint_utils.py` (same
  auto-export mechanism as `find_classified_noise_chunk`, no `__init__.py`
  change): given a dataset-search dataframe and an experiment name, returns the
  matching `datafile_name`. If an experiment has more than one matching run
  (e.g. GratingDSOS was run twice that day), picks the earliest by `block_id` and
  prints every candidate found, mirroring the same "auto-pick + print + let you
  override" pattern as `find_classified_noise_chunk`.
- **Cell 4/5 (choose an experiment)**: now only `exp_name` needs to be set.
  `datafile_name` comes from `ra.find_datafile_for_protocol(grating_search,
  exp_name, protocol_name=ds_os_protocol_name)`. Added `MANUAL_DATAFILE_NAME =
  None` alongside the existing `MANUAL_ANALYSIS_CHUNK = None`, so either can be
  hardcoded independently if auto-detection doesn't pick what you want. Default
  `exp_name` updated to `'20260505A'` (matching what yas was actually testing
  with) -- no more hardcoded `datafile_name` default at all, since it's no longer
  needed.

### Verification

- `find_datafile_for_protocol()` is pure pandas logic (no schema/DB dependency),
  tested against 3 scenarios by pasting the exact function body against synthetic
  dataframes: a single match (picked correctly), two matches for the same
  experiment with different `block_id`s (earliest picked, both candidates
  printed), and no match (returns `None`, prints why).
- `python -m py_compile src/retinanalysis/utils/datajoint_utils.py` -- passes.
- Notebook re-validated with `nbformat.validate()` and all 16 cells re-compiled
  after the cell 2/3/4/5 edits -- passes.
- Still not verified against the live database.

## Update 2026-07-29 (later still): the RTMP crash is happening on every real experiment yas has tried -- implemented the graceful-degradation fix

yas: "you said you checked and a lot had the rmptg tag or hwatver yet so far th
eones i have tried all give that same error also i still don tgt what the tag is
lol." Two things to address.

**What the RTMP tag actually is, in plain terms:** it's a small piece of metadata
that Vision (the spike-sorting/analysis software) writes into a `.globals` file
when it finishes processing a white-noise ("spatial noise") recording. It records
the exact parameters of the randomized checkerboard movie that was shown to the
retina during that recording -- its size in stixels (the checkerboard squares),
refresh timing, and the random seed used to generate it -- so that later, Vision
(or this package) can regenerate the exact same movie frame-by-frame to compute
spike-triggered averages (receptive fields). It only ever gets written for
white-noise chunks, and only if Vision fully finished that step for that chunk.

**Reconciling with the earlier check:** the `20260227A` example folder scan (see
above) genuinely did find RTMP present on all 6 white-noise chunks there -- that
wasn't wrong. But that's one local example folder, and apparently not
representative of what's actually stored for the experiments in the real
DataJoint-tracked pipeline: yas has now tried this on multiple real experiments
and hit the same "no RTMP tag" error every time, meaning something about how her
lab's current (automated, kilosort-based) pipeline processes white-noise chunks
differs from whatever produced `20260227A`'s files, and consistently doesn't
result in Vision writing this tag. Since this is clearly not a rare/one-off
data-integrity problem for her actual workflow, but the *normal* case, I revisited
my earlier decision to hold off on making the loader tolerate a missing tag.

**Fix implemented (previously deferred, now done):**

- `get_analysis_vcd()` in `vision_utils.py`: the `load_vision_data(...)` call is
  now wrapped in try/except. If it fails specifically with the RTMP
  `AssertionError`, it prints a clear warning and retries with
  `include_runtimemovie_params=False` instead of crashing. Any other
  `AssertionError` (i.e. not about RTMP) still propagates normally -- this only
  catches the one specific failure mode.
- `AnalysisChunk.get_noise_params()` in `analysis_chunk.py`: reordered so
  `numXChecks`/`numYChecks` (from datajoint's stimulus parameters) are computed
  before `staXChecks`/`staYChecks` (normally from Vision's RTMP data). If
  `vcd.runtimemovie_params` is `None` (RTMP was missing), it now falls back to
  **assuming no cropping occurred** -- `staXChecks = numXChecks`, `staYChecks =
  numYChecks`, so `deltaXChecks`/`deltaYChecks` come out to 0 -- rather than
  crashing. This is the "risky assumption" I flagged earlier as needing your
  sign-off before I made it; given the tag is now confirmed missing across
  multiple real experiments (not one bad chunk), and there's no other source for
  this information without it, this is the only usable fallback. **If a spatial
  map or RF for a chunk that hit this fallback looks misaligned or an odd size,
  this assumption is the reason** -- it means the STA was actually computed on a
  cropped grid relative to the stimulus, and this can't know that without the
  RTMP data.
- One case still refuses to guess rather than silently picking a possibly-wrong
  answer: if a chunk's epoch blocks *disagree* on grid size (a separate, rarer
  situation) AND RTMP is missing, there's no way to know which grid size is the
  real one (normally Vision's `micronsPerStixelX` disambiguates this). This now
  raises a clear `ValueError` explaining exactly that, instead of guessing.

None of this affects the DS/OS demo's actual F1/DSI/OSI analysis, which never
touches spatial maps or STA grid size at all -- this only matters if/when you use
`plot_mosaics_for_datasets` or anything else that draws RF/spatial maps for a
chunk that hit this fallback.

### Verification

- `get_analysis_vcd()`'s retry logic: extracted the literal function source (via
  `ast`, not retyped) and ran it with `load_vision_data` mocked to raise the RTMP
  `AssertionError` on the first call (matching the real crash message) and
  succeed on a retry with `include_runtimemovie_params=False`. Confirmed: exactly
  2 calls happen (fail, then retry), the correct warning prints, and the returned
  vcd is usable. Separately confirmed a *different* `AssertionError` (not
  RTMP-related) is NOT swallowed -- it still propagates, so this fix doesn't mask
  unrelated bugs.
- `AnalysisChunk.get_noise_params()`'s fallback logic: same technique (literal
  function source via `ast`), tested against 4 scenarios: RTMP present + single
  grid size (regression check -- confirmed unchanged from before this fix), RTMP
  missing + single grid size (confirmed falls back to `staXChecks=numXChecks`,
  `deltaXChecks=0`), RTMP missing + disagreeing grid sizes across epoch blocks
  (confirmed raises a clear `ValueError` mentioning RTMP and "no safe fallback"),
  RTMP present + disagreeing grid sizes (regression check -- confirmed still uses
  `micronsPerStixelX` to disambiguate, unchanged from before).
- `python -m py_compile` on both changed files -- passes.
- Still not verified against the live database -- please try again and let me
  know if the RTMP error is actually gone now, and separately whether any
  mosaics/spatial maps you generate look right (given the "assume no cropping"
  fallback, this is the thing most worth double-checking).

## Update 2026-07-29 (later still): REVERTED the RTMP graceful-degradation fix

yas: "wait what lol dont change it i just wanted to know how may are missin i can
copy and paste a few json fies or somethi." She was asking an informational
question (how many `.globals` files are missing RTMP), not asking me to change the
shared package -- I misread the momentum of the conversation and implemented the
fix without her explicit go-ahead. She confirmed via a direct question that she
wants it reverted (over leaving it in as a safety net), reasoning: she'd rather a
missing-RTMP chunk fail loudly so she notices and fixes the underlying data,
rather than have it silently proceed on an assumption.

**Reverted, both files back to exactly their pre-2026-07-29-RTMP-fix state:**
- `src/retinanalysis/utils/vision_utils.py`: `get_analysis_vcd()` back to a single
  unguarded `load_vision_data(..., include_runtimemovie_params=True)` call, no
  try/except.
- `src/retinanalysis/classes/analysis_chunk.py`: `get_noise_params()` back to
  computing `staXChecks`/`staYChecks` from `self.vcd.runtimemovie_params.width/
  height` unconditionally, first, before `numXChecks`/`numYChecks` -- crashes
  again (as before) if `runtimemovie_params` is `None`.

Also clarified for yas: the RTMP tag lives in `.globals` files (a binary format
Vision writes), not JSON -- if her plan is to "copy and paste a few json files" to
fix this, that's likely a different mechanism than what would actually restore
the RTMP tag, and I flagged that mismatch rather than assuming which files she
meant. I also don't have access to her real server's experiments to count how
many are actually missing RTMP there -- only the local `20260227A` example
folder (which had 0 unexpectedly-missing files, only the expected non-white-noise
ones).

### Verification
- `python -m py_compile` on both files after the revert -- passes.
- `grep -n "RTMP"` on both files after the revert -- zero matches, confirming no
  trace of the added code remains.

## Update 2026-07-29 (later still): found the real bug -- find_classified_noise_chunk assumed the old chunk-naming convention

Same "why did 0227 give me this error" crash, still on `find_classified_noise_chunk`-picked chunks. yas: "we don't have chunks anymore tho remember i changed the datajoint structure last time to align with our new one" -- and then, when I asked her to paste `get_exp_summary` output rather than checking myself: "you should know, read the files on the changes we made... i thought we had already changed every area that assumes chunks."

She was right to push back -- I should have checked her own diff first. Read
`changes/yas_pre_existing_changes_vs_upstream_2026-07-28.diff` (her pre-existing
edits vs the upstream/Dragos repo, captured at the start of this session) and
found the actual mechanism, in her own change to `get_exp_summary()` in
`datajoint_utils.py`:

> "The newer sorted-data layout may not populate SortingChunk rows in the old
> form... fall back to empty chunk metadata rather than failing" -- when an
> experiment has no `SortingChunk` rows (the new, chunk-less layout), every row's
> `chunk_name` comes back as `""` (empty string), not something like `"chunk13"`.

`find_classified_noise_chunk()` (the function I wrote) filtered on
`chunk_name.str.contains("chunk")` -- a filter I copied from the EXISTING
`get_nearest_noise()` in `stim.py` without checking whether it still applied. I
confirmed `stim.py` is NOT in yas's pre-existing diff at all -- meaning that
substring filter is original, untouched upstream (Dragos's) code that was never
updated for the new schema, either by yas or by me. Copying it into my new
function carried the same stale assumption forward. Since `""` never contains
`"chunk"`, this filter silently excluded every white-noise row for any experiment
using the new layout -- exactly why it kept failing.

**Fixed:** `find_classified_noise_chunk()` no longer filters on chunk_name
content at all -- only on `protocol_name`. It resolves which identifier to use
per row: `chunk_name` if it's actually a non-empty string (older experiments that
still have real `SortingChunk` rows), otherwise `datafile_name` (newer
experiments, where each datafile is its own analysis unit -- matches both your
description and the actual `20260227A` folder structure, where files live at
`kilosort25/data001/data001.globals` etc.). That resolved identifier is what gets
deduped on, checked for classification files, printed, and returned -- so the
function now works for both the old and new structures without needing to know
in advance which one a given experiment uses.

### Verification
- Re-ran all 4 original synthetic scenarios (single/multiple/NDF1-fallback/none
  classified, all using populated `chunk_name` values) -- all still pass
  unchanged, confirming this is not a regression for older-structure experiments.
- Added a 5th scenario: `chunk_name=""` for all rows (matching `get_exp_summary`'s
  documented new-layout fallback), `datafile_name="data001"` used instead --
  confirmed the function correctly falls back to `datafile_name` and returns
  `'data001'`.
- `python -m py_compile src/retinanalysis/utils/datajoint_utils.py` -- passes.

## Update 2026-07-29 (major): demo 7 rebuilt -- separate grating/spot/flash sections, cell-type rasters, noise-subtracted CRFs

yas: the contrast demo hit the same RTMP error as the DS/OS demo (fixed the same
way, see below), and separately: "i want different cells for grating, spots and
flash and then people can choose what analyses they need but i need all them for
the responses and the rasters we talked about and all that." Also answered
follow-up questions on scope: search for spot/flash protocol names rather than
guess them; flash (and non-periodic spots) use mean firing rate, not F1, since a
flash isn't a periodic stimulus; rasters should come in two forms -- one overview
with a representative cell per cell type, and one where you pick a cell type and
see every cell of that type; noise subtraction should use the spontaneous
pre-stimulus rate (her recommended default).

**Quick fix first (same as DS/OS demo):** cells 4/5 ("choose an experiment") now
use `ra.find_datafile_for_protocol` + `ra.find_classified_noise_chunk` instead of
letting `create_mea_pipeline` auto-detect its own (unreliable, chunk-naming-
convention-dependent) analysis chunk.

**Checked yas's MATLAB CRF script for a noise-subtraction convention before
adding my own:** it doesn't have one -- it plots raw F1 per NDF/contrast
(including a contrast=0 condition, offset for log-scale visibility) with no
subtraction step anywhere. So the pre-stimulus-window subtraction implemented
here isn't overriding anything from that script -- it's filling in something the
script didn't specify, per yas's explicit choice when asked.

**New shared function, `build_trial_response_table()`** in
`src/retinanalysis/utils/tuning.py` -- the core piece that makes "different cells
for grating/spot/flash, but not three separate copies of the extraction logic"
possible:
- Always computes `mean_rate` (stim-window spike count / stimTime) and
  `baseline_rate` (spike count in a window of length `min(preTime, stimTime)`
  taken from the END of the pre-stimulus period, i.e. immediately before
  stimulus onset, divided by that window's own duration) and
  `mean_rate_noise_sub = mean_rate - baseline_rate` (not clipped at 0 -- a trial
  can come out negative if it happened to have less activity than its own
  baseline estimate, which is expected and left as-is for downstream averaging).
- Only computes `f0`/`f1`/`noise_f1`/`f1_noise_sub` (F1 the same way, on the
  matching pre-stimulus noise window, at the same frequency -- a standard
  "noise-floor" harmonic estimate) when a given epoch actually has a nonzero
  `temporalFrequency` (or whatever `stim_freq_key` is set to) -- i.e. only for
  periodic stimuli. Non-periodic epochs (flash, static spots) get NaN in those
  four columns; `mean_rate`-based columns are always populated regardless of
  periodicity.
- `protocol_name`/`condition_keys`/`stim_freq_key` are all arguments, not
  hardcoded -- this is what lets the same function serve gratings (`contrast`,
  periodic), spots (unknown condition key/periodicity), and flash (possibly
  `intensity` rather than `contrast`, non-periodic) without knowing their exact
  parameter conventions in advance.

**Rebuilt `demos/7_contrast_response_demo.ipynb`** (15 cells -> 31 cells), new
structure:
- Shared setup (once): broad `'contrast'` protocol search (not exact-match
  anymore, since spot/flash names aren't confirmed), `exp_name` +
  `ra.find_classified_noise_chunk` (shared chunk for cell typing across all
  three sections, since typing doesn't depend on which contrast stimulus is
  being analyzed), a cell that loads that chunk's classification file into a
  `cell_id -> cell_type` mapping (via `AnalysisChunk(..., b_load_spatial_maps=
  False, include_ei=False)`, same lightweight-load pattern as
  `plot_mosaics_for_datasets`), and one cell defining 5 shared, reusable,
  notebook-local functions: `load_contrast_section` (find datafile, build
  pipeline, build response table, tag cell types, print params for
  verification), `plot_crf` (2x2 grid: raw/noise-subtracted x
  non-normalized/per-cell-normalized, population mean +/- SEM vs. condition,
  log-x with a small offset for contrast=0 when the condition is literally
  `'contrast'`, matching yas's MATLAB script's plotting convention), and the
  raster trio (`_raster_for_cell`, `plot_raster_overview_by_cell_type`,
  `plot_rasters_for_cell_type` -- the two raster views yas asked for). These
  plotting/orchestration functions are notebook-local, not added to the shared
  package, matching the precedent set by demo 6's `plot_smart_clock`.
- **Grating section** (protocol name confirmed:
  `manookinlab.protocols.ContrastResponseGrating`): fully built out --
  F1-based CRF (`plot_crf` with `response_col='f1_noise_sub'`), a Naka-Rushton
  fit cell (ported from the original version of this demo, now fit to the
  noise-subtracted, per-cell-normalized F1), and both raster views.
- **Spot and Flash sections**: same structure, but `SPOT_PROTOCOL_NAME`/
  `FLASH_PROTOCOL_NAME` are placeholders (e.g.
  `'manookinlab.protocols.ContrastResponseSpot'`) since I have no example data to
  confirm the real strings from -- each section's loader cell checks whether its
  placeholder name is actually present in `contrast_search` and, if not, prints
  which real protocol names WERE found and sets `df_trials_spot`/`df_trials_flash`
  (etc.) to `None` rather than crashing. Every downstream cell in that section
  checks for that `None` sentinel and prints a short "not runnable yet" message
  instead of raising `NameError` -- this was caught by the integration test
  below (my first draft just skipped the assignment on a not-found protocol,
  which crashed every cell after it with `NameError: name 'df_trials_spot' is
  not defined the moment you ran the section without first fixing the protocol
  name). Both sections use mean rate, not F1 (`response_col='mean_rate_noise_sub'`),
  per yas's answer -- `CONDITION_KEYS` also need verification once you know the
  real parameter names (flash in particular may use something other than
  `'contrast'`, e.g. `'intensity'`).

### Verification

- `build_trial_response_table()` unit-tested against synthetic (cell, trial) data
  with 2 cells, 4 known baseline rates, a planted contrast-dependent rate boost
  (`baseline + 10*contrast` Hz), 25 repetitions per condition, and alternating
  periodic/non-periodic epochs: confirmed `mean_rate` matches
  `baseline + 10*contrast` within 1.5 Hz, `baseline_rate` matches the true
  baseline within 1.5 Hz, `mean_rate_noise_sub` matches the pure contrast-driven
  component (`10*contrast`) within 2 Hz -- all averaged over repetitions to beat
  down the sampling noise inherent in a short (0.5s) baseline window. Confirmed
  F1 columns are populated only for periodic epochs and NaN for non-periodic ones
  in every row. Confirmed a `preTime=0` edge case produces `baseline_rate=0`,
  `noise_f1=0`, and `mean_rate_noise_sub == mean_rate` with no division-by-zero.
- The 5 shared notebook-local functions (before being embedded in the notebook)
  were written and tested standalone first, against synthetic data with 4 planted
  cells across 2 cell types and 5 contrast levels x 6 repetitions: confirmed
  `load_contrast_section` correctly builds and tags `cell_type`, `plot_crf` and
  both raster functions run without exceptions, and
  `plot_rasters_for_cell_type` on a cell type with zero matching cells correctly
  returns `None` and prints a message rather than crashing or plotting an empty
  figure.
- Full end-to-end integration test: extracted the LITERAL cell source from the
  saved `.ipynb` (not a reimplementation) and `exec()`'d cells 3, 5, 7, 9, 11, 13,
  15, 17, 18, 20, 22, 23, 24, 26, 28, 29, 30 in order (matching real notebook
  execution order) against synthetic data with 5 cells / 2 cell types / 5
  contrast levels / 6 repetitions, where the synthetic search results only
  contain the grating protocol (simulating the realistic case where spot/flash
  haven't been confirmed yet): the grating section ran fully (150 trial rows
  built, CRF plotted, 2/5 cells got a successful Naka-Rushton fit, both raster
  views rendered without exceptions), and the spot/flash sections correctly
  detected their placeholder protocol names weren't in the search results,
  printed which real names WERE found, and every downstream cell in each section
  printed a "not runnable yet" message and returned cleanly instead of crashing
  -- this is what caught and fixed the `NameError` bug described above.
- `python -m py_compile src/retinanalysis/utils/tuning.py` -- passes.
- `nbformat.validate()` and `compile()` on all 31 cells of the rebuilt notebook
  -- passes.
- **Still not verified against the live database**, and additionally: **spot and
  flash protocol names/condition keys are placeholders, not confirmed** -- you'll
  need to fill those in from your own search results before those two sections
  will do anything.

## Update 2026-07-30: real-data bug fixes (cell typing, giant rasters, EI threshold, F1 noise bias)

Yas ran demo 7 against her real database (`20260227A`) and reported: rasters
"looked really off," the raster cell printed "selected cell type: Unknown" which
was confusing, she wants rasters separated into one block per cell type with an
optional cell to look at a different NDF/cell type, and asked whether the EI
mapping threshold can be set the way `corr_threshold` is set in her MATLAB
scripts.

I pulled the actual saved output images out of her committed notebook (they're
embedded as base64 PNG in the `.ipynb` JSON) to see exactly what she saw, instead
of guessing from the code alone.

**Bug 1 -- every cell classified as "Unknown" (root cause of the raster mess).**
`load_contrast_section` built `cell_type_map`, a `pandas.Series` indexed by the
REFERENCE/classification chunk's (`data009`) cell_ids, then did
`df_trials['cell_id'].map(cell_type_map)` -- but `df_trials['cell_id']` are
`data000`'s (the grating datafile's) own cell_ids, from an independent sorting
run. Cell 5 in `data000` and cell 5 in `data009` are unrelated physical cells;
the direct `.map()` by raw ID essentially never lines up. Her real output
confirmed this: "Loaded cell types for 628 cells... Unknown 628" printed at the
classification step is a separate, second bug (see below), and then "424
cells... cell types present: ['Unknown']" for the grating table is exactly what
this join bug predicts.

The correct mapping already exists and is already used elsewhere:
`MEAPipeline.add_types_to_protocol()` (`classes/mea_pipeline.py`) builds
`resp.df_spike_times['cell_type']` using `self.match_dict` -- the actual
EI-based cross-chunk cell mapping from `cluster_match()` -- so it's indexed
correctly by the PROTOCOL's own cell_ids. Fixed `load_contrast_section` to read
`cell_type` from `response_block.df_spike_times` instead of reinventing the
join. Cells that never EI-matched the reference chunk at all now show as
`'Unmatched'` (kept distinct from `'Unknown'`, which now only means "matched a
reference cell whose own classification label was blank/unrecognized").

**Bug 2 -- ~37,000-pixel-tall raster image.** With every cell lumped into one
`'Unknown'` type, `plot_rasters_for_cell_type` put all 424 grating cells into a
4-column grid (106 rows). Extracted the actual PNG from her notebook: 1589 x
37057 pixels, 10MB. That's what "looked really off." Fixed: both raster
functions are now capped/paginated (12 cells per figure by default), and
`plot_raster_overview_by_cell_type` produces ONE SEPARATE FIGURE PER CELL TYPE
(satisfies "separated into cells for each cell type when they are printed" --
Jupyter's inline backend displays every figure created during a cell's
execution, so a loop that calls `plt.subplots()` once per type naturally
produces one distinct output image per type) instead of cramming every type
into a single combined grid.

**Bug 3 -- `f1_noise_sub` spuriously negative for every grating cell/condition.**
Also pulled the actual grating CRF PNG: raw `f1` showed a clean rising CRF curve
(~2.2 to 4.4 Hz), but `f1_noise_sub` was uniformly NEGATIVE (~-11 to -6.5 Hz) and
its "normalized" panel was noisy/non-monotonic. Root cause: `noise_f1` is
computed via the vector-sum F1 estimator
(`compute_f1_f0_from_spikes`) over `noise_window_s = min(preTime, stimTime)`,
which is very short (250ms in her data) relative to the stimulus window (4s).
Confirmed on synthetic data: for the SAME non-modulated (pure Poisson) firing
rate, the vector-sum F1 estimate over a 0.25s window came out ~4.7x higher than
over a 4.0s window -- a real statistical bias (the estimator's noise floor
scales like ~1/sqrt(window duration)), not a sign of real periodicity. Since
`noise_f1` >> `f1`, `f1_noise_sub = f1 - noise_f1` goes strongly negative for
essentially every trial. This was never something yas's own MATLAB CRF scripts
computed -- none of the three versions she shared subtract a baseline from F1,
they all plot raw F1 directly -- so this was my own gap-filling addition (a
noise-subtraction convention she'd approved for `mean_rate`, which I extended to
F1 without it being asked for specifically), and it turns out to be
mis-behaved for short `preTime` windows. Fixed: `f0`/`f1`/`noise_f1`/
`f1_noise_sub` are still computed and left in `build_trial_response_table`'s
output (useful for inspection), but `plot_crf` gained a `show_noise_sub` flag
(default `True`, unchanged behavior for `mean_rate`-based spot/flash sections,
which don't have this bias) and the grating CRF/Naka-Rushton cells now default
to raw `f1`, matching yas's own scripts. Full caveat documented in
`build_trial_response_table`'s docstring in `tuning.py`.

**New feature -- EI-matching threshold, per yas ("the ei mapping threshold
should be set just like it is in my matlab notebook").** `MEAPipeline`/
`create_mea_pipeline` used to call `cluster_match()` with no `corr_cutoff`
argument at all, silently locked to `cluster_match`'s own default (0.8) with
**no way to override it** from a notebook. Added a `corr_cutoff: float = 0.8`
parameter to both, threaded through both `cluster_match()` call sites in
`MEAPipeline.__init__`. Default unchanged (0.8) so nothing else that doesn't
pass it explicitly is affected. Demo 7 now has a `CORR_THRESHOLD_*` variable per
section (grating/spot/flash), defaulting to 0.85 to match yas's MATLAB
`corr_threshold`, plumbed through `load_contrast_section(..., corr_cutoff=...)`.
`load_contrast_section` also now prints how many (cell, trial) rows are
`'Unmatched'` at the chosen threshold, so it's visible whether the threshold is
too strict.

**New feature -- optional NDF/light-level explorer, per yas.** Added an
"Optional: look at a different NDF" markdown+code cell pair at the end of each
section (grating/spot/flash). Set `EXPLORE_NDF_<SECTION>` to an NDF value and
(optionally) `EXPLORE_CELL_TYPE_<SECTION>`, and it re-runs `load_contrast_section`
against whichever datafile actually ran that protocol at that NDF -- found
dynamically via `ra.get_ndf_blocks_for_protocol` (the same helper written for
demo 8's correlation analysis, reused here), not a hardcoded NDF -> datafile
table.

**Still open -- needs yas's input, not fixed here (see the typing cell's new
diagnostics in the notebook):** the SEPARATE "every cell 100% Unknown" result at
the classification-loading step itself (before the join bug even applies) is
likely because `src/retinanalysis/assets/cell_types.csv` is mostly a primate
cell-type vocabulary inherited from the fork this package started from, with
only 3 mouse-style entries patched in (`on/brisk sustained`, `on/brisk
transient`, `brisk sustained` -- note the `/` and the missing `off` variants,
and no plain `off brisk sustained`/`off brisk transient` despite those being the
exact strings yas's own MATLAB scripts use as `cell_type`). If the real
classification file's raw labels don't exactly match an entry in that CSV,
`AnalysisChunk.get_df()`'s matching (in yas's own pre-existing code, not
touched here) falls back to "Unknown" for everything. Not changed here because
I don't know yas's full/real mouse cell-type vocabulary and don't want to guess
at rewriting a reference vocabulary used package-wide. The typing cell (cell 7)
now prints the raw classification-file lines plus the current `cell_types.csv`
vocabulary automatically whenever more than half of cells come out "Unknown," so
the actual mismatch is visible next time this runs against real data.

### Verification
- `python -m py_compile` on `mea_pipeline.py`, `tuning.py`, `correlation_utils.py`
  -- all pass.
- `nbformat.validate()` (normalized) on the rebuilt 37-cell notebook -- passes.
- Synthetic numerical check confirming the F1 short-window bias: pure Poisson
  spiking at a fixed rate gives a mean vector-sum F1 estimate ~4.7x higher over a
  0.25s window than over a 4.0s window at the same rate -- matches the
  qualitative pattern in yas's real data (noise_f1 ~11-12 Hz vs. real-window f1
  ~2-4.5 Hz).
- Full end-to-end integration test against a synthetic 3-cell (2 matched + 1
  deliberately unmatched) grating dataset, extracting and exec()'ing the LITERAL
  notebook cell source in order: confirmed `cell_type` in `df_trials_grating`
  correctly reflects `off brisk sustained`/`off brisk transient`/`'Unmatched'`
  (not lumped into a single `'Unknown'` bucket); confirmed `corr_cutoff=0.85` is
  correctly threaded all the way through `load_contrast_section` ->
  `create_mea_pipeline` (asserted inside the fake pipeline constructor); confirmed
  `plot_raster_overview_by_cell_type` returns one figure per type; confirmed
  `plot_crf(show_noise_sub=False)` produces a 2-axes (not 4-axes) figure and
  `show_noise_sub=True` still produces the original 4; confirmed the NDF
  explorer cell, when `EXPLORE_NDF_GRATING` is set to `1.0`, correctly calls
  `create_mea_pipeline` a second time with NDF 1's real datafile (`data002`,
  resolved via `get_ndf_blocks_for_protocol`, not a hardcoded value) and
  produces raster output for it.
- **Not yet re-verified against the live database** -- these are all fixes to
  real bugs found in yas's actual saved output, but haven't been run against her
  live data again yet.

## Update 2026-07-30 (later): raster marker size + classification-file hyphen/underscore matching bug

**Raster markers.** yas: "the raster feels like thick blobs I think the point
thickness should change." `_raster_for_cell`'s spike marker changed from
`'k.', markersize=3` to `'.', color='k', markersize=1.5, markeredgewidth=0`
(smaller dot, no edge stroke). Nothing else in the raster logic touched.
Verified by rendering the literal updated function against dense synthetic
spike data (3 conditions x 8 trials x 40-90 spikes/trial) and viewing the PNG:
dots stay visually distinct instead of merging into bars.

**Missing cell types.** yas: only `'Unknown'`, `'Unmatched'`, and
`'off/transient'` were showing up, when she expected her other confirmed types
too. Her hypothesis: "sometimes we do brisk sustained and other times
brisk-sustained... maybe the space translates as a `-` in the txt file."

Confirmed directly in code (`AnalysisChunk.get_df`, `pick_type_from_parts`):
matching against `cell_types.csv` was a literal `part in norm_cell_types_lower`
set-membership check with no normalization beyond lowercasing. Any hyphen,
underscore, or run of extra whitespace in the raw classification file line
(instead of a single plain space, exactly matching the CSV) would silently
fail to match and fall through to `"Unknown"` -- with no warning that this had
happened. This exactly matches her hypothesis and explains why only one type
(`off/transient`, presumably always written the same way) was surviving while
the others (presumably written inconsistently across sessions/people) weren't.

**Fix**, `src/retinanalysis/classes/analysis_chunk.py`, `get_df()`:
1. New `_normalize_type_token(s)` helper: replaces `-` and `_` with a space
   and collapses repeated whitespace, applied to BOTH the raw classification
   file tokens and the `cell_types.csv` vocabulary before comparing (and
   before re-checking the combined `"<prefix>/<base>"` string against the CSV).
   `"brisk-sustained"`, `"brisk_sustained"`, and `"brisk  sustained"` (double
   space) now all match the CSV's `"brisk sustained"` identically to a normal
   single space. This only WIDENS matching -- it cannot cause two previously-
   distinct types to collide, since only whitespace-equivalent characters are
   touched, not letters.
2. New unconditional (not verbose-gated -- same policy as the RTMP-missing
   warning) print: any raw token that still fails to match anything after
   normalization (excluding the structural `"on"`/`"off"`/`"all"` tokens) is
   collected and printed once per typing file, e.g.:
   `[chunk13.classification.txt] 2 raw classification token(s) did not match
   any cell_types.csv entry ... and were classified 'Unknown': ['bigmas',
   'ex-brisk-sus']`. This surfaces *remaining* real vocabulary gaps directly,
   instead of yas having to notice a type is missing and ask why.

No changes to `cell_types.csv` itself in this round -- the fix is in how
tokens are compared, not the vocabulary list. The existing entries
(`brisk sustained`, `brisk transient`, `transient`, etc.) now also match their
hyphen/underscore-written variants.

### Verification
- `python -m py_compile src/retinanalysis/classes/analysis_chunk.py` -- passes.
- `nbformat.validate()` + all 37 cells re-compiled on
  `demos/7_contrast_response_demo.ipynb` after the raster-marker edit -- passes.
- Standalone test of the extracted normalization + `pick_type_from_parts`
  logic (literal copy of the new code, not a reimplementation) against 6 cases:
  `"brisk sustained"` (already worked), `"brisk-sustained"`,
  `"brisk_sustained"`, `"brisk  transient"` (double space), plain
  `"transient"`, and a deliberately-unmatchable `"totally-made-up-type"`. All 5
  real variants correctly resolved to their expected `on/off`-prefixed label;
  the made-up type correctly stayed `"Unknown"` and was the only entry in
  `unmatched_raw_tokens` (confirmed `"All"` is excluded from that set, since
  it's the fixed structural top-level bin present in every line, not a
  candidate type -- an early version of this test caught `"All"` incorrectly
  appearing as a false "unmatched" entry on every line, fixed by adding it to
  the skip list alongside `"on"`/`"off"`).
- **Not yet re-verified against the live database / her real classification
  file** -- I don't have access to the actual raw file to confirm hyphens are
  really what's in there for the missing types; the fix is scoped to exactly
  the mechanism she hypothesized and verified to work correctly on that
  mechanism in isolation. If other types are still missing after this, the new
  unconditional print should show their exact raw (still-unmatched) token
  text, which would tell us the real cause directly instead of guessing again.

## Update 2026-07-30 (small): flash raster points a little thicker

yas, ahead of a larger flash-mosaic rework she flagged for later: "make point
thickness for raster plots for flash a little thicker (we will make bigger
edits later)."

Added a `markersize` parameter (default `1.5`, unchanged) threaded through
`_raster_for_cell` -> `plot_raster_overview_by_cell_type` /
`plot_rasters_for_cell_type`, and set only the 3 Flash-section call sites
(overview mosaic, single-type explorer, NDF explorer) to `markersize=2.2`.
Grating and spot rasters are untouched (still `1.5`, the shared default) --
scoped to flash only, matching her literal ask, since demo 7's raster
functions are shared across all three sections and I didn't want to change
grating/spot without being asked.

### Verification
`nbformat.validate()` + all cells re-compiled -- passes. Rendered the
literal `_raster_for_cell` function side-by-side at both marker sizes against
the same synthetic dense spike data used for the earlier thickness fix, and
viewed the output: `2.2` is visibly thicker than `1.5` without collapsing
back into the earlier "thick blobs" look.

## Update 2026-07-30 (small): grating CRF overlaid across all NDFs

yas: "for gratings i want a cell that plots the crfs of all ndfs on one
curve."

**New function**, shared functions cell, `plot_crf_across_ndfs(exp_name,
contrast_search, protocol_name, condition_key, analysis_chunk_name,
corr_cutoff, response_col, title, typing_chunk=None, log_x=None)`. Loops
`ra.get_ndf_blocks_for_protocol` (real database NDF values, same helper
already used by the NDF-explorer cells) and calls `load_contrast_section`
once per NDF -- the exact same function already used for the single-NDF CRF
cell and the NDF explorer, no new data-loading path -- then plots each NDF's
population CRF (raw + per-cell-normalized, same 2-panel layout as `plot_crf`)
as one colored/labeled line on **shared** axes instead of a separate figure
per NDF. Deliberately mirrors the existing single-NDF grating CRF cell's
population composition (every cell in `df_trials` at that NDF, not restricted
to `SELECTED_CELL_TYPE_GRATING`) rather than introducing a new, different
scope -- flagged in the docstring in case a type-restricted version is wanted
later.

New markdown+code cell pair inserted right after the existing single-NDF
grating CRF cell, calling `plot_crf_across_ndfs(..., response_col='f1', ...)`
(raw F1, same reasoning as the single-NDF cell -- noise-subtracted F1 has the
documented short-window bias). Only wired up for gratings, since that's what
was asked -- not added to spot/flash.

### Verification
`nbformat.validate()` + all 39 cells re-compiled -- passes. Extracted the
literal `plot_crf_across_ndfs` function (via the shared functions cell) and
ran it against synthetic data shaped like 3 NDFs x 5 cells x 4 contrast
levels, with F1 magnitude deliberately scaled down at higher NDF (dimmer
light -> lower response, planted ground truth): confirmed the figure has
exactly 2 axes, each with exactly 3 legend-labeled lines ("NDF 0", "NDF 1",
"NDF 2"), and visually confirmed via the rendered PNG that the raw panel
shows 3 separate curves ordered by response magnitude (NDF 0 highest) while
the normalized panel collapses them onto nearly the same shape (as expected
for a pure gain scaling with no shape change) -- both matching the planted
structure.

## Update 2026-07-30 (same day, later): CRF-across-NDFs split by cell type

yas: "but for all cell types too like the ones with all ndfs should have
which cell type at top and plot all ndfs (in that one cell you dded)."

`plot_crf_across_ndfs` (added earlier the same day) mixed every cell in
`df_trials` into one population curve per NDF regardless of type -- matching
the existing single-NDF CRF cell's behavior, which hadn't been flagged as a
problem until now. Changed to produce **one figure per real cell type**
(auto-detected across the loaded NDFs, excluding `'Unknown'`/`'Unmatched'`,
same convention as `plot_raster_overview_by_cell_type`), each titled with its
cell type, each still overlaying all NDFs as separate lines.

Restructured internally to avoid a real cost trap: rather than reloading
`load_contrast_section` once per (NDF, type) pair, each NDF is now loaded
exactly ONCE (`df_trials_by_ndf`, a dict keyed by NDF) and then filtered by
`cell_type` in-memory per figure -- `load_contrast_section` already returns
a `cell_type` column per cell, so no extra pipeline rebuilds are needed to
get per-type data. Return value changed from a single `Figure` to
`{cell_type: fig}`; the notebook variable was renamed
`fig_crf_all_ndfs_grating` -> `figs_crf_all_ndfs_grating` accordingly, and the
`title` parameter was renamed to `title_prefix` (the cell type is now
appended automatically per figure, e.g. `"... -- off/brisk transient"`).

**Bug caught during this edit, before testing**: the first attempt at
rewriting the function via string-slice concatenation duplicated the
`def plot_crf(` line into `def plot_crf(def plot_crf(...)`, since the
replacement text I built also ended with that same anchor string used to
find the insertion point. Caught by `nbformat`/`compile()` validation
(`SyntaxError: invalid syntax` pointing at the exact duplicated line) before
any testing was attempted -- fixed by removing the duplicate.

### Verification
`nbformat.validate()` + all cells re-compiled -- passes (after fixing the
duplicate-line bug above). Extracted the literal rewritten function and ran
it against synthetic data with 2 NDFs and 5 cells split across 3 labels (2
real cell types + one `'Unmatched'` cell): confirmed the returned dict has
exactly the 2 real types as keys (`'Unmatched'` correctly excluded);
confirmed each figure's title contains its cell type; confirmed each figure
has exactly 2 NDF-labeled lines per axis. Confirmed via the printed per-NDF
progress lines that `load_contrast_section` was called exactly twice total
(once per NDF), not four times (once per NDF per type), verifying the
no-redundant-reload design goal. Rendered one type's figure to PNG and
visually confirmed the title reads "Gratings: F1 vs. contrast across NDFs
(expX) -- off/brisk transient" with two correctly-separated NDF curves.

## Update 2026-07-30 (later still): overview rasters now show ALL cells per type, paginated

yas, once all 3 real cell types were finally showing up: "i dont want it to
just show the top 4 tho ideally it would show all maybe as separate
scrollable elements or somethign idk how its possible."

`plot_raster_overview_by_cell_type` previously capped each type's figure at
`max_cells_per_type` (default 4), showing only the top 4 cells by
`response_col` and silently dropping the rest -- the only way to see a type's
remaining cells was to separately re-run the single-type explorer cell
(`plot_rasters_for_cell_type`) at the bottom, which already did full
pagination but only for one manually-chosen type at a time.

Merged the two behaviors: `plot_raster_overview_by_cell_type` now paginates
EVERY type the same way `plot_rasters_for_cell_type` already paginates a
single type -- `max_cells_per_page` cells per figure (default 4, unchanged
2x2 layout), one figure per page, no cells dropped. Since Jupyter's inline
backend displays every figure a cell produces as a separate output block,
this is what actually behaves like "separate scrollable elements": a type
with 14 cells now produces 4 distinct figures in a row (titled "off/transient
(n=14 cell(s)) (page 1/4)" etc.) instead of one figure silently showing only
the best 4.

Return type changed accordingly: `{cell_type: fig}` -> `{cell_type: [fig_page_1,
fig_page_2, ...]}`. Checked all 3 call sites (grating/spot/flash overview
cells) -- none of them index into the returned dict's values, so this is a
safe, non-breaking change for this notebook. Added a `sort_by_response=True`
parameter (kept the existing highest-response-first ordering by default,
since that's still useful to see the best-responding cells on page 1 first --
pass `False` to sort by cell_id instead).

### Verification
- `python -m py_compile` -- n/a (pure notebook-cell code, no package file
  touched this round). `nbformat.validate()` + all 37 cells re-compiled --
  passes.
- Extracted the LITERAL updated function from the saved notebook and ran it
  against synthetic data shaped like yas's real "off/transient: 14 cells"
  case (14 synthetic cells of one type, 2 of another, 2 conditions x 3 trials
  each): confirmed the 14-cell type produced exactly 4 pages/figures (4+4+4+2
  cells) with correct page-number titles, and the 2-cell type produced
  exactly 1 page -- no cells silently dropped from either type, matching what
  she asked for.

## Update 2026-07-30 (later still): Flash section moved above Spots; NDF-explorer crash fixed

yas: "we rarely use spots so can you put the flash section above the spots
section also i tred the optional cell and put ndf2 and it found it but then
said too many values so."

**Reorder.** Each section (Gratings/Spots/Flash) turns out to be a
self-contained block: a markdown "intro" cell that carries its own leading
`---` plus `# Section: X` header, followed by that section's content cells.
Swapped the Spots and Flash blocks wholesale (each moved as a unit, intro
cell included), so the notebook now reads Gratings -> Flash -> Spots. Checked
first that neither section reads the other's variables (each builds its own
`df_trials_*`/`spike_times_by_cell_*`/etc. from scratch) -- this is a pure
cell reorder, no logic touched.

**The "too many values" crash.** Root cause: `load_contrast_section` was
changed earlier today (the NDF0-default fix) to return 5 values instead of 4
(`df_trials, spike_times_by_cell, df_epochs, datafile_name, ndf_used`), but
the 3 "explore a different NDF" cells were never updated to match and still
tried to unpack only 4 -- exactly a `ValueError: too many values to unpack
(expected 4)` the moment the cell actually finds a real NDF block and calls
`load_contrast_section`, which is exactly what yas hit setting
`EXPLORE_NDF_GRATING = 2.0`. Fixed all 3 explorer cells (grating, spot,
flash) to unpack 5 values (discarding the last two, since the datafile is
already known from the block match and `ndf_used` isn't populated in the
`manual_datafile_name` path anyway).

### Verification
- `nbformat.validate()` + all 37 cells re-compiled after both changes --
  passes.
- Reorder confirmed by re-printing the full cell list: Gratings, then Flash,
  then Spots, each still starting with its own intro cell.
- Directly reproduced the crash and the fix side-by-side against a stand-in
  function returning the real 5-tuple shape: the old 4-value unpack raises
  the exact error yas saw; the new 5-value unpack succeeds and preserves the
  same 3 values the rest of the cell actually uses.
- Caught my own script bug mid-edit: the first reorder attempt misidentified
  a section's own leading `---` (embedded inside its intro markdown cell) as
  a separate shared divider cell, so it targeted the wrong cell ranges -- the
  assertion guarding cell boundaries failed before anything was written to
  disk, re-diagnosed by printing full cell contents instead of just first
  lines, then redone correctly.
- Not yet re-verified against yas's live database/notebook run.

## Update 2026-08-03: moved shared functions out of the notebook into a package file

Yas: *"i dont want super super long function definitons in the notebook so why
cant we just save a file with just my defitions thats ouside the notebook,
like some lines of code should be there and to generate plots or whatevr but
like not pages of definitions."*

**What changed.** The ~500-line "shared response-extraction and plotting
functions" cell (`load_contrast_section`, `plot_crf_across_ndfs`, `plot_crf`,
`_raster_for_cell`, `plot_raster_overview_by_cell_type`,
`plot_rasters_for_cell_type`) is no longer defined inline in the notebook.
All six functions moved verbatim (same code, same docstrings, same CHANGED-
comment history) to a new file:

- `src/retinanalysis/utils/contrast_response_utils.py`

registered in `src/retinanalysis/__init__.py` the same way `correlation_utils.py`
already is (demo 8's pattern) -- `from .utils.contrast_response_utils import *`.
That cell in the notebook now just imports them:

```python
from retinanalysis.utils.contrast_response_utils import *
```

**Why this is safe / no other cells changed.** Every other cell in the
notebook already called these functions by their bare names (e.g.
`load_contrast_section(...)`, `plot_crf(...)`, not `ra.load_contrast_section(...)`).
Using a wildcard import (rather than switching everything to `ra.`-prefixed
calls) means every one of those ~20 call sites across the grating/flash/spot
sections needed zero edits -- confirmed by grepping the whole notebook for
all 6 function names after the change and checking every call site still
matches exactly what it was before.

**Circular-import note.** `load_contrast_section` and `plot_crf_across_ndfs`
call other `retinanalysis` functions (`get_ndf_blocks_for_protocol`,
`find_datafile_for_protocol`, `create_mea_pipeline`, `build_trial_response_table`)
via `ra.xxx(...)`. Since this new file is itself imported by
`retinanalysis/__init__.py`, a module-level `import retinanalysis as ra` in
it would be circular. Fixed the same way `correlation_utils.py` and
`datajoint_utils.py` already handle this: `import retinanalysis as ra` is
done *inside* those two function bodies (lazy import), not at the top of the
file. By the time a notebook actually calls these functions, `retinanalysis`
has already finished importing, so this is free and behaves identically to
before.

### Verification
- `python -m py_compile` on the new file -- passes.
- `nbformat.validate()` + all 39 notebook cells re-compiled -- passes.
- Grepped every code cell in the notebook for all 6 function names: only the
  (now-short) import cell and the original ~20 real call sites remain, and
  none of those call sites needed to change.
- Synthetic integration test: stubbed `retinanalysis` (fake
  `get_ndf_blocks_for_protocol`, `find_datafile_for_protocol`,
  `create_mea_pipeline`, `build_trial_response_table` returning planted
  NDF-dependent data) in `sys.modules`, loaded the ACTUAL new
  `contrast_response_utils.py` file (not a reimplementation), and called
  `load_contrast_section`, `plot_crf_across_ndfs`, `plot_crf`,
  `plot_raster_overview_by_cell_type`, and `plot_rasters_for_cell_type`
  directly -- all five ran correctly, including the lazy `ra` import
  resolving inside the function bodies and `plot_crf_across_ndfs` correctly
  calling the co-located `load_contrast_section` with no prefix.
- Not yet re-verified against yas's live database/notebook run -- next step
  is to restart the kernel (package-level staleness, not just cell-level)
  and re-run the notebook top to bottom.

## Update 2026-08-03 (2): scrollable loading-print output

Yas: *"and i wnat the ones that print a huge list of stimulus parameters to
be scrollable elements and question, some print a bunnnccchhh of loading
functino print statements as they go can those be removed after it works or
no ... or maybe those becomes scrollable and output is separate"* -- then,
after being asked whether to keep/remove/toggle these prints: *"idk what to
do i want just that to be scrollable oridk but not the actual figures
output but rn we scroll through just pages of print staements."*

**What changed.** `load_contrast_section`'s progress/diagnostic prints ("N
epochs found", `epoch_parameters` keys list, the cell-count funnel per type)
no longer print directly into the notebook's normal output. A new context
manager, `scrollable_prints()`, wraps just the loading calls so that
everything they print collapses into one small, scrollable box -- while any
figures created by the SAME cell (raster mosaics, CRF plots) still render
normally, full size, not scrolled.

**Why not just use Jupyter's "scrolled output" toggle?** I tried that first
(`cell.metadata.scrolled = True`), but it applies to a cell's ENTIRE output
-- prints AND figures together -- and its actual behavior varies across
notebook frontends (JupyterLab vs. classic Notebook vs. VS Code's Jupyter
extension don't all honor it the same way). Reverted that approach.
`scrollable_prints()` instead renders a plain HTML/CSS scroll box via
`IPython.display`, which looks the same everywhere, and -- because it's a
`with` block placed around just the loading code -- never touches whatever
figures get created outside (or after) that block.

**Where it's used:**
- Inside `plot_crf_across_ndfs` itself: the whole per-NDF loading loop
  (progress line + nested `load_contrast_section` prints, for every NDF) is
  now one `with scrollable_prints():` block -- the CRF figures, built in a
  separate loop right after, are unaffected. No notebook cell needed to
  change for this one.
- In the notebook: every cell that calls `load_contrast_section` directly
  (grating/flash/spot load cells, and all three "explore a different NDF"
  cells) now wraps just that call in `with scrollable_prints():`. The
  explorer cells' raster-plotting calls stay outside the block, so their
  figures render normally.

**On the "remove the prints once it works" question:** left as-is for now
(not removed) -- these are the same diagnostic prints (the cell-count
funnel especially) that helped find the Unknown/Unmatched cell-type bugs
earlier. Since they're now collapsed into a small scroll box instead of
dominating the page, there wasn't a strong reason to also delete them. Say
the word if you'd rather they were gone entirely once a section is trusted.

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + all 39 notebook cells re-compiled -- passes.
- Synthetic tests directly against the real `scrollable_prints()`
  implementation (mocked `IPython.display.display`, real matplotlib on the
  Agg backend): confirmed (1) captured print text lands in exactly one
  `display()` call with the expected scroll CSS, (2) nothing leaks to real
  stdout, (3) a figure created either inside or immediately after the
  `with` block still constructs normally, (4) running the real
  `plot_crf_across_ndfs` against stubbed data produces exactly ONE combined
  scroll box for both NDFs' loading output (not one per NDF) and still
  returns the expected `{cell_type: fig}` dict.
- Not yet re-verified against yas's live notebook run -- needs a kernel
  restart (package-level change) before the new `scrollable_prints` name is
  available.

## Update 2026-08-03 (3): stripped change-history narrative out of the notebook

Yas: *"why are there notes in all the demo title section im confused just say
what the notebook does at the top ... why are you sayign everythign you did,
that is saved to the file of our chages i dont want that in everyons notebook
files."*

**What changed.** Every markdown section header and inline code comment in
`demos/7_contrast_response_demo.ipynb` and `src/retinanalysis/utils/contrast_response_utils.py`
that read like a changelog entry -- `"NEW/CHANGED/FIXED 2026-07-30 (Claude, per
yas -- '...')"`, references to "your real data", "yas's MATLAB script", etc. --
was rewritten to plain, current-state documentation: what a section/function
does, what its parameters mean, what to watch out for. No dates, no
attribution, no "here's what I changed and why" narrative anywhere in either
file. That history already lives here and in
`changes/claude_changes_2026-07-28.txt` -- this was pure duplication, and
confusing for anyone else opening the notebook.

No logic changed anywhere -- only markdown text and comments/docstrings.

### Verification
- `nbformat.validate()` + all 39 notebook cells re-compiled -- passes.
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- Grepped both files for `"per yas"`, `"Claude"`, `"CHANGED 20"`, `"FIXED 20"`,
  `"NEW 20"`, `"yas's"` -- zero matches left.
- Re-ran the exact synthetic integration test from the earlier
  contrast_response_utils.py extraction (stubbed `retinanalysis`, loaded the
  real file, called `load_contrast_section`, `plot_crf_across_ndfs`,
  `plot_crf`, `plot_raster_overview_by_cell_type`,
  `plot_rasters_for_cell_type`) against the cleaned-up file -- all five still
  behave identically, confirming the comment/docstring rewrite didn't touch
  any logic.

## Update 2026-08-03 (4): real axis labels on the CRF plots

Yas asked whether the all-NDF CRFs were log-x (yes -- `log_x` defaults True
whenever `condition_key == 'contrast'`), whether her original MATLAB script
was log-x too (yes -- confirmed against the earlier port notes: it displayed
contrast=0 at 0.005 since 0 can't sit on a log axis, which is exactly what
`plot_crf`'s `x_plot = np.where(x == 0, x[x>0].min()/2, x)` replicates), and
why so many plots don't have proper axis labels.

That last one was a real gap: `plot_crf` and `plot_crf_across_ndfs` only ever
called `ax.set_xlabel(condition_key)` (the raw column name, e.g. "contrast",
un-capitalized) and never called `ax.set_ylabel(...)` at all, regardless of
whether `f1`, `mean_rate`, or a normalized version of either was being
plotted.

**What changed.** Added two small label helpers to
`contrast_response_utils.py`:
- `_response_axis_label(col)`: maps a response column name to a real y-axis
  label with units, e.g. `'f1'` -> `'F1 amplitude (Hz)'`, `'mean_rate_noise_sub'`
  -> `'Mean firing rate, noise-subtracted (Hz)'`. `_norm` columns get the same
  base label with the unit dropped and `'(normalized)'` appended instead
  (normalized values are unitless -- each cell scaled to its own max = 1).
  Falls back to a capitalized, underscore-stripped version of the column name
  for anything not in the lookup table.
- `_condition_axis_label(condition_key)`: `'contrast'` -> `'Contrast'`,
  `'intensity'` -> `'Intensity'`, same capitalize-fallback for anything else
  (e.g. if a flash/spot section's `condition_keys` ever needs to be something
  other than contrast).

Both `plot_crf` and `plot_crf_across_ndfs` now call `ax.set_ylabel(...)` with
the right label for whichever column that specific panel is actually
plotting, and `ax.set_xlabel(...)` with the capitalized condition name
instead of the raw column string.

Going forward, every new plot gets real x/y axis labels (with units where
there's a natural one) by default -- this isn't a one-off fix.

### Verification
- `python -m py_compile` -- passes.
- Unit tests on both label helpers directly (`f1` -> `'F1 amplitude (Hz)'`,
  `f1_norm` -> `'F1 amplitude (normalized)'`, `mean_rate_noise_sub_norm` ->
  `'Mean firing rate, noise-subtracted (normalized)'`, unknown column
  fallback, unknown condition_key fallback).
- Rendered both `plot_crf` and `plot_crf_across_ndfs` against synthetic data
  and read the actual `ax.get_xlabel()`/`ax.get_ylabel()` off the resulting
  figure (not just checked the code) -- all 4 panels of `plot_crf` and both
  panels of `plot_crf_across_ndfs` show the correct label. Also rendered to
  PNG and visually confirmed the labels display correctly, not just that the
  strings were set.

## Update 2026-08-03 (5): temporary fallback for "Globals file does not have RTMP tag" crashes

Yas: "im still getting so many of the stmp tag errors and idk why only some
give me that" (RTMP tags). Traced the actual crash mechanism (not from
memory -- read the vendored loader code and yas's own saved notebook
outputs, where this exact traceback already appears twice in demo 7 and
once in demo 1):

`get_analysis_vcd()` (`vision_utils.py`, used by `AnalysisChunk` -- your
reference/classification/white-noise chunk, and the `typing_chunk` cell)
hardcoded `include_runtimemovie_params=True` on every call. That flag makes
Vision's loader read the RTMP (runtime movie params) tag out of the chunk's
`.globals` file, and hard-crash with `AssertionError: Globals file does not
have RTMP tag, cannot load runtime movie parameters` if a chunk's `.globals`
file never had that tag written. Nothing downstream of AnalysisChunk in
either demo (cell typing, RF params, EI matching, spike times) actually
reads runtime movie params -- the only place this package uses them for
real is `preprocessing/sta.py` (stimulus regeneration), not used in demo 7
or 8. Separately, `MEAResponseBlock` (each NDF's grating/flash/spot target
datafile) goes through a different loader, `get_protocol_vcd()`, which
never requests this flag -- so only AnalysisChunk construction was ever
exposed, and only because of this one unconditional flag, not because
typing/EI genuinely needs it.

**This is a temporary fix, not the permanent one** -- per yas's request to
look back into it later rather than change the default behavior right now.
`get_analysis_vcd` now tries `include_runtimemovie_params=True` first (same
as before, preserving existing behavior/intent), and ONLY on that specific
RTMP-tag-missing AssertionError, retries the same load with
`include_runtimemovie_params=False` instead of crashing, printing a message
explaining what happened. Any other AssertionError (unrelated to RTMP)
still propagates normally, not silently swallowed.

The real fix under discussion (not done): stop requesting
`include_runtimemovie_params=True` by default at all, since nothing in
either demo needs it -- revisit once it's confirmed nothing else (e.g. demo
1's STA/RF work) needs it either.

### Verification
- `python -m py_compile` on `vision_utils.py` -- passes.
- Synthetic tests against the REAL function (`get_analysis_vcd`, loaded
  directly, `visionloader`/`retinanalysis.utils` stubbed to avoid needing
  real Vision data or a DB connection): (1) a chunk whose fake loader raises
  the exact RTMP AssertionError on the first call retries with
  `include_runtimemovie_params=False` and succeeds, returning a usable VCD;
  (2) a chunk that succeeds on the first try is NOT retried at all (fallback
  only engages for the RTMP-missing case, not on every call); (3) a
  different, unrelated AssertionError still propagates up instead of being
  silently caught.
- Not yet re-verified against your live database/notebook run.

## Update 2026-08-03 (6): reverted the RTMP fallback -- it didn't actually work

The temporary `get_analysis_vcd` fallback added just above (2026-08-03 (5))
was wrong and has been reverted. `vision_utils.py` is back to its exact
original form -- no try/except.

What I got wrong: I claimed "nothing downstream of AnalysisChunk reads
`vcd.runtimemovie_params`," based only on grepping for calls to the
RTMP-reading *functions*. I didn't check for code reading the resulting
*attribute* afterward. `AnalysisChunk.get_noise_params()` -- called
unconditionally in `__init__`, regardless of `b_load_spatial_maps` -- does
exactly that as its first two lines: `self.staXChecks =
int(self.vcd.runtimemovie_params.width)`. With the fallback in place,
`get_analysis_vcd` stopped crashing, but returned a `vcd` with
`runtimemovie_params = None`, which just moved the crash one step later
into a much less clear `AttributeError: 'NoneType' object has no attribute
'width'` inside `get_noise_params()`.

Worse: this isn't an isolated calculation. `get_noise_params()` computes
`staXChecks`/`staYChecks`/`deltaXChecks`/`deltaYChecks` from RTMP, then
`get_rf_params()` (also called unconditionally, not gated by
`b_load_spatial_maps`) uses those deltas to compute every cell's RF center,
then `get_df()` (which builds the cell-type dataframe that even
typing-only use -- `b_load_spatial_maps=False, include_ei=False` -- needs)
reads those RF centers. So RTMP is load-bearing for the classification path
too, in the current code, not just for RF/spatial-map work.

Two real fix options exist, but both have real tradeoffs (one risks
silently wrong RF coordinates if the fallback assumption doesn't hold,
the other means the chunk can't be used at all) -- flagged to yas rather
than guessed at, and reverted to the honest, original crash in the
meantime rather than leaving a fix in place that quietly does the wrong
thing.

### Verification
- `python -m py_compile` -- passes.
- Read back the reverted function and confirmed it matches the original
  (no try/except, no added comment) line for line.

## Update 2026-08-03 (7): RTMP fallback, done properly this time

Based on your observation that your old MATLAB pipeline never even needed
the globals file and never hit this problem, we agreed the STA-vs-noise-grid
crop correction (`deltaXChecks`/`deltaYChecks`) is very likely a no-op for
your data -- your white-noise protocol probably never crops the STA
relative to the full noise grid. This time the fix addresses the FULL
dependency chain identified in the revert above (2026-08-03 (6)), not just
`get_analysis_vcd`.

**Two files changed together:**

1. `src/retinanalysis/utils/vision_utils.py`, `get_analysis_vcd()`: re-added
   the try/except around `load_vision_data(...)`. If it raises an
   `AssertionError` containing "RTMP tag", it retries once with
   `include_runtimemovie_params=False` (prints a warning if `verbose=True`)
   and returns a VCD whose `runtimemovie_params` is `None`. Any other
   `AssertionError` still propagates normally.

2. `src/retinanalysis/classes/analysis_chunk.py`, `get_noise_params()`:
   now checks `has_rtmp = self.vcd.runtimemovie_params is not None` before
   touching it.
   - If RTMP is present: unchanged behavior exactly as before.
   - If RTMP is missing: `staXChecks`/`staYChecks` default to
     `numXChecks`/`numYChecks` (computed from DataJoint epoch parameters,
     unaffected by RTMP), so `deltaXChecks`/`deltaYChecks` come out to 0 --
     i.e. "assume no cropping." Prints a clear warning whenever this kicks
     in.
   - The rare "not all epoch blocks used the same number of X/Y checks"
     branch also had a second RTMP dependency (`vision_micronsPerStixel`,
     used to disambiguate which grid size was actually used). When RTMP is
     present this is unchanged. When RTMP is missing, it now falls back to
     the first epoch block's values instead of crashing, with its own
     warning -- this branch is rare enough that a wrong guess here is very
     unlikely to matter, but it's flagged loudly if it happens.

This time `get_rf_params()` and `get_df()` are safe because their inputs
(`deltaXChecks`, `deltaYChecks`, `staYChecks`) are always real numbers
(0 in the fallback case) rather than an attribute lookup on `None` -- the
crash can no longer propagate downstream the way it did in the reverted
attempt.

Also added a comment directly in the `typing_chunk = ra.AnalysisChunk(...)`
cell in `demos/7_contrast_response_demo.ipynb` (the cell where you actually
hit this error) explaining the fallback and the reasoning behind it, so
it's visible right where the error used to appear.

### Verification
- `python -m py_compile` on both `vision_utils.py` and `analysis_chunk.py`
  -- passes.
- Synthetic tests against the REAL functions (loaded directly via
  `importlib`, with `retinanalysis._database`/`visionloader`/etc. stubbed
  to avoid needing a live DB or real Vision data):
  - `get_analysis_vcd`: RTMP-missing chunk retries once and succeeds,
    returning `runtimemovie_params = None`; an unrelated `AssertionError`
    is NOT swallowed and still propagates.
  - `get_noise_params`: (1) RTMP present, consistent epoch blocks --
    unchanged, matches the original math exactly; (2) RTMP missing,
    consistent epoch blocks -- `staXChecks`/`staYChecks` fall back to
    `numXChecks`/`numYChecks`, `deltaXChecks`/`deltaYChecks` are 0, warning
    printed; (3) RTMP missing AND inconsistent epoch blocks (the rare
    double-dependency case that wasn't checked before) -- no crash, falls
    back gracefully to the first block's values; (4) RTMP present with
    inconsistent epoch blocks -- unchanged, still disambiguates via
    `micronsPerStixelX`.
- Notebook cell edit validated with `nbformat.validate()` and `compile()`
  on every code cell.
- Not yet re-verified against your live database -- if RF center positions
  ever look wrong for a chunk that prints the "no RTMP tag" warning, that's
  the first thing to check.

**You'll need to restart your kernel** for this to take effect, since it's
a change to the installed package, not the notebook itself.

## Update 2026-08-04 (1): on/off toggle for the "CRF across all NDFs" plots
-- SUPERSEDED, see (2) below

First read of the request implemented a whole-cell on/off toggle
(`SHOW_CRF_ACROSS_NDFS`) that skipped the entire "CRF across all NDFs" cell.
Yas clarified she actually meant just the SEM error bars, not the whole cell
("wait im stupid lol i meant the se bars for those plots lol i dont want to
toggle the entire cell off i just wouldnt run it my bad") -- see (2) below
for what actually shipped. Keeping this entry for the record since it was a
real (if short-lived) change.

## Update 2026-08-04 (2): on/off toggle for SEM error bars on the "CRF
across all NDFs" plots (replaces (1) above)

Request (yas): a quick on/off toggle for the SEM error bars specifically on
the grating section's "CRF across all NDFs" plots (`plot_crf_across_ndfs`)
-- with several NDFs overlaid on the same axes, the error bars can make the
plot busy. NOT a toggle for the whole cell/section (that was my
misreading, reverted).

**`src/retinanalysis/utils/contrast_response_utils.py`, `plot_crf_across_ndfs`:**
added a `show_sem: bool = True` parameter. When `False`, both `errorbar(...)`
calls (raw panel and per-cell-normalized panel) pass `yerr=None` instead of
`yerr=pop['sem']`/`yerr=pop_norm['sem']` -- lines/markers only, no error
bars. Panel titles also drop the `"+/- SEM"` suffix when `show_sem=False`, so
the figure itself reflects which mode it's in.

**`demos/7_contrast_response_demo.ipynb`, cell `crfallndf2`:** reverted the
whole-cell toggle from (1), back to calling `plot_crf_across_ndfs`
unconditionally -- and added `SHOW_SEM_ACROSS_NDFS = True` as the first line
of the cell, passed through as `show_sem=SHOW_SEM_ACROSS_NDFS`. Set it to
`False` and re-run the cell for clean mean-only lines.

Markdown header cell (`crfallndf1`) updated to point at the new
`SHOW_SEM_ACROSS_NDFS` toggle instead of the old (removed)
`SHOW_CRF_ACROSS_NDFS` one.

This is the only cell in the notebook that produces this particular "across
NDFs" plot -- spot/flash sections don't have an equivalent (single-NDF CRFs
only, no error-bar toggle requested for those).

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- Synthetic render test against the REAL `plot_crf_across_ndfs` (loaded via
  `importlib`, `ra.get_ndf_blocks_for_protocol`/`load_contrast_section`
  stubbed with synthetic per-cell trial data across 2 fake NDFs): rendered
  the figure with `show_sem=True` and `show_sem=False`, actually looked at
  both PNGs. `show_sem=True` shows error-bar caps/whiskers on every point
  and `"+/- SEM"` in the panel titles; `show_sem=False` shows clean
  lines/markers with no error bars and no `"+/- SEM"` in the titles.
  Confirmed programmatically too (checked `ax.collections` for error-bar
  line segments) as well as by eye.
- `nbformat.validate()` and `compile()` on every code cell in the notebook
  -- passes.

## Update 2026-08-05: grating PSTHs before the CRF (sanity check)

Per yas: wants to see the actual response time-course before trusting a CRF's shape --
"when you see the CRFs you can decide if it makes sense." Clarified a point of
confusion first: the earlier "not binned" comment was about
`compute_f1_f0_from_spikes()` (tuning.py, direct spike-phase vector-sum method for F1,
no binning) -- a completely separate thing from PSTH plotting, which necessarily bins
spikes into a rate-over-time curve. 10ms bins for the PSTH doesn't touch how F1 itself
gets computed anywhere.

**New in `contrast_response_utils.py`:**
- `compute_cell_psth(cell_id, cell_trials, spike_times_by_cell, df_epochs,
  bin_size_ms=10.0)`: one cell's own trial-pooled PSTH (Hz), across [0, stimTime),
  using the exact same spike-time alignment convention `_raster_for_cell()` already
  uses (relative to stim onset, cropped to the stim window) -- so a PSTH bin lines up
  with that cell's own raster.
- `plot_psth_for_cell_type(df_trials, spike_times_by_cell, df_epochs, condition_key,
  selected_cell_type, bin_size_ms=10.0, title=None, ax=None, cmap_name='viridis')`:
  one line per condition value (e.g. one per contrast), colored on a colormap (not a
  legend -- avoids clutter with many contrast levels) with a colorbar. Per-cell PSTH
  computed first, THEN averaged across cells of `selected_cell_type` -- same
  per-cell-first-then-population-average convention `plot_crf()` already uses, so a
  single high-firing cell can't dominate the shape.

**Notebook (`demos/7_contrast_response_demo.ipynb`):** new markdown + code cell
inserted between the grating load cell (`303d0214`) and the existing "Grating CRF"
section (`b5e472a7`/`3853ba05`) -- new cell IDs `f22dc663-f986-4087-9bbd-cd1ec8d861b5`
(markdown) and `cadf81b4-bd1e-44e3-ab94-20910f19664a` (code). Takes a list of NDF
values (`PSTH_NDF_VALUES = [ndf_grating]` by default -- can be `[1, 2, 3]` etc.), one
subplot per requested NDF. Reuses the already-loaded `df_trials_grating` etc. for
whichever NDF matches the section's primary `ndf_grating` (no reload); any other
requested NDF is loaded via `load_contrast_section(..., manual_datafile_name=...)`,
the same pattern the existing `EXPLORE_NDF_GRATING` cell (`44f4986d`) already uses.
Cell type is picked independently (`PSTH_CELL_TYPE_GRATING`, same "first real,
non-Unknown/Unmatched type" default logic as `SELECTED_CELL_TYPE_GRATING`) rather than
depending on that later cell, since this one now runs earlier in the notebook.

Only added to the Grating section for now (the only one of the three sections that's
fully wired up and runnable end to end -- Flash/Spot are still stubbed pending real
data). Same two functions are reusable there once those sections are runnable.

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell in
  `demos/7_contrast_response_demo.ipynb` -- passes. New PSTH cell confirmed at index
  13, directly between the grating load cell (11) and the CRF markdown (14).
- Synthetic test (real `compute_cell_psth`/`plot_psth_for_cell_type`, loaded via
  `importlib`, fake 2-cell/3-contrast/3-trial dataset with contrast-scaled spike
  counts): confirmed bin count matches `stimTime/bin_size` (100 bins for a 1s window,
  10ms bins); confirmed rate normalization (pooled spike count / (n_trials *
  bin_width_s)) against a hand-computed expected value; confirmed empty-trials case
  returns `(None, None)`; confirmed `plot_psth_for_cell_type` draws one line per
  contrast level and that mean rate increases with contrast (matching the synthetic
  data's construction); confirmed the "no trials for this cell type" and
  ax-passed-in-so-fig-is-None cases.
- Not yet re-verified against yas's live database -- package-level change to
  `contrast_response_utils.py`, needs a kernel restart plus re-running the notebook
  from the grating load cell down.

## Update 2026-08-05 (2): PSTHs replaced with a scrollable per-cell mosaic

Feedback: "the psths look terrible... maybe we should have a mosaic of all the cells
psth's in a scrollable element... we can pick ndf and cell type." The single
population-average-per-NDF panel (previous update, same day) was hiding cell-to-cell
shape differences -- exactly what this sanity check needs to surface.

**New in `contrast_response_utils.py`:** `plot_psth_mosaic_for_cell_type(df_trials,
spike_times_by_cell, df_epochs, condition_key, selected_cell_type, bin_size_ms=10.0,
n_cols=4, cmap_name='viridis', title=None)` -- one small subplot per INDIVIDUAL cell of
`selected_cell_type` (not averaged), `n_cols` per row (default 4), one line per
condition value (contrast) colored on a shared colorbar (a per-subplot legend would be
unreadable at that size). Reuses `compute_cell_psth` unchanged, just called once per
cell instead of averaged across cells first. `plot_psth_for_cell_type` (the
population-average version) is left in the module, just no longer called from the
notebook.

**Notebook:** same two cells (`f22dc663...` markdown, `cadf81b4...` code) rewritten in
place rather than adding new ones. Still takes `PSTH_NDF_VALUES` (list, e.g.
`[ndf_grating]` or `[1, 2, 3]`) and `PSTH_CELL_TYPE_GRATING` (None = auto-pick first
real type) -- same "pick NDF and cell type" override pattern as before, just now
driving a mosaic per NDF instead of one averaged panel per NDF. The code cell's
metadata now has `"scrolled": true`, so Jupyter renders its output in a fixed-height
box with its own scrollbar instead of pushing the rest of the notebook down when the
mosaic is tall (many cells).

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell -- passes. Confirmed
  `cadf81b4-bd1e-44e3-ab94-20910f19664a`'s metadata has `scrolled: True`.
- Synthetic test (real `plot_psth_mosaic_for_cell_type`, loaded via `importlib`, fake
  6-cell/3-contrast dataset with per-cell-scaled spike counts): confirmed one subplot
  titled `Cell {id}` per cell (6 titles for 6 cells, 2x4 grid with 2 unused axes turned
  off), confirmed the empty-cell-type case ("no cells found") doesn't error.
- Not yet re-verified against yas's live database -- needs a kernel restart (package
  change) plus re-running the notebook from the grating load cell down.

## Update 2026-08-05 (3): switched to raster+PSTH pairing, moved next to the rasters

Yas was confused about what the PSTH plots were actually showing (x-axis = time in
seconds since stim onset, 10ms bins; contrast is color, not an x-axis, because each
contrast is itself a whole time-course, not a single point in time) and separately
wasn't sure what format was actually meant by "look at their PSTHs" as a CRF sanity
check. Explained: the standard version is a raster stacked directly above its own
derived PSTH, same time axis, per cell -- so the smoothed curve can be checked against
the real spikes it came from, not just trusted alone. Confirmed and requested: "right
before the raster cells there is one for the psth... remove this one that looks for
outliers."

**New in `contrast_response_utils.py`:** `plot_raster_and_psth_for_cell_type(df_trials,
spike_times_by_cell, df_epochs, condition_key, selected_cell_type, bin_size_ms=10.0,
max_cells_per_page=4, cmap_name='viridis', markersize=1.5)`. Per cell: raster on top
(`_raster_for_cell()`, reused unchanged) with its derived PSTH directly below on the
same x-axis (`ax_psth.set_xlim(ax_raster.get_xlim())` keeps the two rows aligned), one
line per condition value colored on a shared colormap, one shared legend per page
(`Line2D` proxies, not a colorbar -- exact contrast values labeled instead of a
gradient). Paginated like `plot_rasters_for_cell_type` (`max_cells_per_page=4`) instead
of one big scrollable mosaic. `plot_psth_mosaic_for_cell_type` (previous update, same
day) is left in the module, unused in the notebook now -- still a reasonable "scan many
cells for outliers" tool, just not the right one for this sanity check.

**Notebook:** removed the two PSTH-mosaic cells that sat before the CRF cell
(`f22dc663...` / `cadf81b4...`). Added new markdown (`6bc0f7c8...`) + code
(`4c378466...`) cells right before the existing "## Grating rasters" markdown
(`e65c4455`) -- same `PSTH_NDF_VALUES` (list) / `PSTH_CELL_TYPE_GRATING` (None =
auto-pick) override pattern as before, now calling `plot_raster_and_psth_for_cell_type`
per requested NDF instead of the mosaic function. No `scrolled` metadata needed this
time -- pagination keeps each page a normal size.

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell -- passes. Confirmed cell
  order: grating load (11) -> CRF (12-17) -> new raster+PSTH cell (18-19) -> existing
  "Grating rasters" (20-22).
- Synthetic test (real `plot_raster_and_psth_for_cell_type`, loaded via `importlib`,
  fake 6-cell/3-contrast dataset): confirmed pagination (2 pages for 6 cells at
  max_cells_per_page=4), confirmed each page has 2 rows x n_cols axes (raster row +
  PSTH row), confirmed each PSTH axis has one line per contrast (3), confirmed raster
  and PSTH x-limits match for the same cell (visual alignment), confirmed the shared
  legend exists with the right per-contrast labels, confirmed the empty-cell-type case
  returns `[]` without erroring.
- Not yet re-verified against yas's live database -- package-level change, needs a
  kernel restart plus re-running the notebook from the grating load cell down.

## Update 2026-08-06: linear 0-1 contrast ticks, dropped the C50 histogram

**Why:** yas asked what the Naka-Rushton fit plot actually adds over the raw F1 curves
(answer: it's a fitted 4-parameter model summarizing the F1-vs-contrast data, not
another view of the same measurement), then said she didn't want the population C50
histogram next to it ("i dont want that bar plot... idk what purpose it serves"), and
separately asked why the contrast axis on the CRF plots showed scientific notation
("is it because its log scale"). It is: `plot_crf`/`plot_crf_across_ndfs` both default
to `log_x = (condition_key == 'contrast')`, so every contrast plot in this demo was
log-scaled by default, which is where the power-of-ten tick labels came from. She asked
for plain linear 0-1 axes with real contrast values ticked, for every contrast plot in
this demo, plus removal of the C50 histogram.

Separately worth noting (from the earlier "what's the point of the histogram"
conversation): the C50 histogram wasn't just uninteresting, it was actively misleading.
`fit_naka_rushton`'s `c50` upper bound is unconstrained (`np.inf`) -- any cell whose F1
doesn't clearly saturate within the tested contrast range is mathematically ambiguous
for this model and can fit to an arbitrarily large c50, which stretches the
histogram's x-axis and squashes every well-behaved cell into a single low bin (the
"always just one huge bar" yas described). Not fixed here since she asked to just
remove the plot rather than fix the fit's bounds -- `df_fits_grating` (every cell's
fitted c50/r_squared, printed as a table) is still available if anyone wants to look
at the population numbers directly, that underlying issue just isn't visualized as a
histogram anymore.

**`contrast_response_utils.py`:**
- `plot_crf`: in the `else` branch (non-log_x case), now sets `ax.set_xticks(sorted(set(x)))`
  -- every actual tested condition value gets a tick, not just whatever matplotlib's
  default linear locator would have chosen. Additionally, when `condition_key ==
  'contrast'` specifically, `ax.set_xlim(0, 1)` fixes the axis to the full conceptual
  [0, 1] range rather than autoscaling tightly to the max tested contrast. No change to
  the `log_x=True` branch -- log-scale plots (still available via an explicit
  `log_x=True` call) behave exactly as before.
- `plot_crf_across_ndfs`: same tick/xlim convention, applied once (after the per-NDF
  loop) using the union of every real value seen across all NDFs plotted on those
  shared axes (`all_x_values`), so ticks reflect every NDF's tested contrasts, not just
  whichever NDF happened to be plotted last.
- Neither function's `log_x` *default* changed (`log_x=None` still means "log-scale iff
  condition_key == 'contrast'") -- this only changes what happens when `log_x=False` is
  passed explicitly, so other notebooks/callers relying on the log default are
  unaffected. Demo 7's own cells now pass `log_x=False` explicitly (see below) rather
  than the shared default being flipped for everyone.

**`demos/7_contrast_response_demo.ipynb`:**
- Cell `3853ba05` (grating CRF), `crfallndf2` (grating CRF across NDFs), `763f6870`
  (flash CRF), `549ff346` (spot CRF) -- added `log_x=False` to each `plot_crf`/
  `plot_crf_across_ndfs` call.
- Cell `4851bf19` (Naka-Rushton fit) -- dropped the `axes[1].hist(df_fits_grating['c50'], ...)`
  population histogram and the `plt.subplots(1, 2, ...)` layout it needed; now a single
  axis with just the example cell's data + fitted curve, with `ax.set_xticks(...)` at
  the real tested contrasts and `ax.set_xlim(0, 1)`, same convention as the CRF cells.
  `df_fits_grating` (the full per-cell fit table) is still computed and displayed above
  the plot exactly as before -- only the histogram figure itself was removed.
- Cell `e8f8f82b` (markdown, section intro) -- rewritten to describe the single-plot
  output and explain why the histogram was dropped.

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every one of the notebook's 23 code cells --
  passes.
- Synthetic test against the real `plot_crf` (loaded via `importlib`, not
  reimplemented): 5 synthetic cells x 5 non-round tested contrasts (0.0, 0.12, 0.35,
  0.6, 0.96) x 3 trials. With `log_x=False`: confirmed `ax.get_xscale() == 'linear'`,
  confirmed `ax.get_xlim()` covers `[0, 1]`, confirmed every one of the 5 real tested
  contrast values is an actual tick (not just round numbers). With `log_x=True`:
  confirmed `ax.get_xscale() == 'log'` still works unchanged, confirming the log-scale
  path wasn't broken by this change.
- Not yet re-verified against yas's live database -- needs a kernel restart and
  re-running the notebook.

## Update 2026-08-06 (later, later): revert Naka-Rushton plot to linear

**Why:** yas ran the log-scale-with-real-labels version of the Naka-Rushton cell from
the update below and said it "looks weird... make that one go back to what it was."
Reverted cell `4851bf19` back to the plain linear axis (real tested contrasts ticked,
`ax.set_xlim(0, 1)`, `c_smooth = np.linspace(0, max, 200)`) -- i.e. undid only the
log-scale/`geomspace` change from the entry below, keeping the earlier C50-histogram
removal (that part was never in question). The parallel log-scale CRF cells
(`plot_crf`/`plot_crf_across_ndfs` calls with `log_x=True`) added in the same update
are untouched -- this revert is scoped to the Naka-Rushton fit cell only.

### Verification
- `nbformat.validate()` + `compile()` on all 27 code cells -- passes.
- Not yet re-verified against yas's live database.

## Update 2026-08-06 (later x2): revert Naka-Rushton plot all the way to original

**Why:** the previous revert (plain linear axis, but still forcing an explicit tick at
every real tested contrast value) still wasn't right -- yas: "now the naka rushton has
contrast conditions on top of each other go back to the very first naka rushton curve
ou made." On this plot's narrow single-axis width (5.5in figure), forcing 6-8 explicit
ticks (several closely-spaced low contrasts among them) crowded/overlapped the tick
labels themselves. Reverted cell `4851bf19`'s axis all the way to the very original
style from before any of today's axis changes: no `ax.set_xticks(...)`, no
`ax.set_xlim(...)` at all -- just matplotlib's own default linear tick locator, which
picks a small number of well-spaced round-number ticks rather than one per real value.
The C50-histogram removal is NOT reversed (that was a separate, standing request from
earlier in the day, unrelated to this axis back-and-forth). The CRF plots'
`even_spacing`/log-scale-pair changes from the entry below are untouched -- this is
scoped to the Naka-Rushton cell only, which never got `even_spacing` treatment in the
first place (continuous fitted curve, no natural categorical-axis position).

### Verification
- `nbformat.validate()` + `compile()` on all 27 code cells -- passes.
- Not yet re-verified against yas's live database.

## Update 2026-08-06 (later): even-spaced linear axis + parallel log-scale cells

**Why:** immediately after the previous update, yas ran the notebook and reported "all
the lower level contrasts are on top of each other" -- the [0, 1] linear axis from the
update above is accurate, but tested contrasts are typically geometrically/log-spaced
in practice (e.g. 0.02, 0.05, 0.1, 0.2, 0.4, 0.8), so on a true linear scale the low
values end up numerically close together and visually overlap. This is exactly the
problem log-scale originally existed to solve. After some back-and-forth, yas's final
ask: keep BOTH a log-scale cell (scientific notation is fine there, per her) and a
linear-scale cell for every contrast plot, but make the linear one actually usable by
spacing points out rather than plotting them at their true (clustering) positions.

**`contrast_response_utils.py`:**
- `plot_crf(..., even_spacing=False)` and `plot_crf_across_ndfs(..., even_spacing=False)`
  -- new parameter on both, only relevant when `log_x` is False. When True, every
  tested condition value is placed at an evenly-spaced integer rank position instead
  of its true numeric position (`value_to_rank = {value: i for i, value in
  enumerate(sorted(unique_values))}`), with the real value as that tick's label
  (`f'{v:g}'`). The axis still looks/behaves like a plain linear axis (no log scale,
  no scientific notation) -- only the spacing between tested values is equalized, not
  their displayed labels. `plot_crf` builds this mapping from every value in the input
  `df_trials`; `plot_crf_across_ndfs` builds it once from the union of every NDF's
  values (before the per-cell-type plotting loop), so every figure/NDF/panel places a
  given value at the same position. Default `False` preserves the prior "clear 0-1
  contrast ticks" behavior (true-to-scale spacing, fixed [0,1] xlim for
  `condition_key == 'contrast'`) added in the update above -- unaffected unless
  `even_spacing=True` is explicitly passed.

**`demos/7_contrast_response_demo.ipynb`:** every contrast-plotting cell now has TWO
versions back to back -- unchanged from the previous update, then a new duplicate cell
right after it:
- Cell `3853ba05` (grating CRF, linear/even-spaced) + new cell after it (log-scale,
  `log_x=True`, unchanged scientific-notation default).
- Cell `crfallndf2` (grating CRF across NDFs, linear/even-spaced) + new cell after it
  (log-scale).
- Cell `763f6870` (flash CRF, linear/even-spaced) + new cell after it (log-scale).
- Cell `549ff346` (spot CRF, linear/even-spaced) + new cell after it (log-scale).
- The four linear-version cells above also gained `even_spacing=True` (previously just
  `log_x=False`).
- Cell `4851bf19` (Naka-Rushton fit) -- NOT given an even-spaced linear version. This
  plot draws a continuous fitted curve alongside the data points, and an evenly-spaced
  categorical axis has no natural position for a continuous curve between ticks (the
  curve would have to be broken into disconnected data-point-to-data-point segments,
  losing the actual fitted shape). Kept log-scale instead (already the literature
  convention for these curves), but with explicit real-value tick labels
  (`ax.set_xticklabels([f'{c:g}' for c in tested_contrasts])`) instead of matplotlib's
  default scientific/power-of-ten log formatting, so the numbers are still directly
  readable -- this was yas's original ask ("i just want to be able to actually see the
  numbers in the log scale"). `contrast=0` is plotted at half the smallest nonzero
  tested contrast (log(0) is undefined, same floor-value convention `plot_crf`'s
  `log_x=True` branch already used) but its tick is still LABELED `'0'`, its real
  value. The smooth fitted curve (`c_smooth`) switched from `np.linspace(0, max, 200)`
  to `np.geomspace(c_floor, max, 200)` so every point on the curve has a strictly
  positive x value (a curve including x=0 or evenly-spaced-through-zero values would
  break/distort on a log axis).

### Verification
- `python -m py_compile` on `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on all 27 code cells (45 total cells, up from 41
  before the 4 new log-scale cells) -- passes.
- Synthetic test against the real `plot_crf` (loaded via `importlib`): 5 cells x 8
  geometrically-spaced contrasts (0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 0.96) x 3
  trials. With `even_spacing=True`: confirmed linear xscale, confirmed tick positions
  are evenly spaced (diff of exactly 1.0 between consecutive ticks) despite the real
  values not being evenly spaced, confirmed every real tested value appears as a tick
  label, confirmed the actually-plotted line data itself uses the evenly-spaced rank
  positions (not the true, clustering values). With `even_spacing=False`: confirmed
  the prior true-linear/[0,1]-xlim behavior is unchanged. Confirmed
  `plot_crf_across_ndfs` has the new `even_spacing` parameter with the right default.
- Naka-Rushton cell verified by extracting the LITERAL cell source from the saved
  `.ipynb` (via `json.load`, not reimplemented) and `exec()`-ing it against 8 synthetic
  cells with known ground-truth C50/n shapes plus noise, with `retinanalysis.utils.tuning`
  stubbed in `sys.modules` to point at the real `tuning.py` module (avoids needing the
  full config/DB-backed package init). Confirmed: log xscale; every real tested
  contrast (0.0 through 0.96) appears as a tick label; contrast=0 is plotted at a
  strictly positive x position (log-safe) while still labeled `'0'`; the smooth fitted
  curve's 200 points are all strictly positive (won't break/distort on the log axis).
- Not yet re-verified against yas's live database -- needs a kernel restart and
  re-running the notebook.
