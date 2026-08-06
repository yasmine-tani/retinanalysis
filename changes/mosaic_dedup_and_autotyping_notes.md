# Mosaic dedup + auto cell-typing notes (2026-07-28)

**Who made these changes:** Claude (Cowork), working from yas's instructions in a chat
session on 2026-07-28 (two rounds -- an initial pass, then a follow-up after yas reviewed
the first round's output live in the notebook). These are separate from yas's own earlier
edits to this repo -- see "Provenance" below for how to tell the two apart.

## Summary
`plot_mosaics_for_datasets` (used in `demos/1_retinanalysis_intro.ipynb` to browse RF
mosaics across many experiments at once) had two problems: it could plot the exact same
mosaic more than once, and it defaulted to a hardcoded cell-type list and required typing
out a classification filename by hand. Both are fixed. A small notebook cell-ordering bug
(`stimulus_data` used before it was defined) was also fixed.

After yas tried round 1 against real data, two more things came up: auto-detecting "every
cell type present" surfaced a lot of catch-all/low-confidence labels (Unknown, nc17, big,
large, etc.) that aren't real cell types, and the console output between "Plot Mosaics for
all the Options" and the actual figures was long enough that you had to scroll past it.
Round 2 (this same file) addresses both.

## What changed

- `src/retinanalysis/utils/datajoint_utils.py` -- `plot_mosaics_for_datasets()` was
  rewritten:
  - It used to loop over every row of the input dataframe (one row per epoch block) and,
    for each row, search for the *nearest* noise chunk by time and silently substitute a
    different chunk if the intended one failed to load (e.g. a missing RTMP tag). Several
    rows in the same experiment often fell back to the same substitute chunk, so that
    mosaic got plotted two or three times.
  - It now processes each unique `(experiment, chunk)` pair in the input dataframe exactly
    once. If a chunk fails to load it is skipped (printed, not substituted) and the next
    chunk in that same experiment is tried -- no more silent substitution, no more
    duplicate plots.
  - A chunk is only plotted if it has at least one classification/typing file (matched by
    `"classification"` appearing in the filename, case-insensitive -- this matches the
    naming convention yas described: some variation of `classification.txt`, sometimes
    with a classifier's initials before `.txt`). Chunks with no classification file are
    skipped; if an entire experiment has none, that's reported once for the experiment
    instead of silently doing nothing.
  - If a chunk has more than one classification file (i.e. more than one person typed it),
    a separate mosaic is plotted for each one.
  - Every plotted mosaic's title now shows the NDF (light level) and which classification
    file was used, so you can tell mosaics apart at a glance.
  - `cell_types` now defaults to `None` instead of the hardcoded `['OnP','OffP','OnM','OffM']`.
    When `None`, round 1 auto-detected *every* type present in the classification file; round
    2 (current behavior) auto-detects and then drops catch-all/low-confidence labels using a
    new `exclude_cell_type_keywords` parameter (see below). Pass your own `cell_types=[...]`
    list to skip auto-detection entirely and plot exactly those types.
  - **New `exclude_cell_type_keywords` parameter** (round 2): default
    `DEFAULT_EXCLUDED_CELL_TYPE_KEYWORDS = ['unknown', 'nc', 'large', 'big', 'huge', 'weak']`.
    Only applies when `cell_types=None` (auto-detect mode) -- if you pass your own list, this
    filter is not applied, since you've already said exactly what you want. `'nc'` is matched
    as a whole token (so `nc17`/`NC5` match, but it won't match inside an unrelated word like
    "Concentric"); the rest match as substrings (so `'large'` also drops `OnLarge`, `'big'`
    also drops `BigMas`). Define your own list and pass it in if this lab's junk-bin
    vocabulary changes -- there's a `_should_exclude_cell_type()` helper next to the function
    if you want to see/tweak the matching logic directly.
  - **Quieter output** (round 2): chunk loading now uses a single `tqdm` progress bar
    (`"Checking noise chunks for classification files"`) instead of printing "Loading VCD..."
    / "VCD loaded with N cells" for every chunk -- that was the wall of text you had to
    scroll past to reach the mosaics. Skip/no-classification messages still print (via
    `tqdm.write`, so they don't corrupt the progress bar), but there are far fewer of them
    now. Pass `verbose=True` to get the old per-chunk detail back if you need it for
    debugging.
  - On mosaic sizing ("it seems random"): the figure grid size is computed elsewhere (inside
    `AnalysisChunk.plot_rfs`, shared by other call sites, left untouched per the "scope to
    just the mosaic browser" instruction) from however many cell types are being plotted.
    Round 1's "auto-detect everything" could pull in 10-30+ raw labels per chunk, so the grid
    size varied wildly chunk to chunk. Round 2's exclusion filter should bring that back down
    to a small, consistent handful of real types (similar to what you had before with the
    hardcoded 2-type list) -- **please check after rerunning whether sizing now looks right;
    if it's still inconsistent we can look at pinning the grid layout explicitly.**
  - This redesign is scoped to `plot_mosaics_for_datasets` only, per yas's answer. Chunk
    selection elsewhere (e.g. `create_mea_pipeline`, single-experiment setup) is untouched.

- `demos/1_retinanalysis_intro.ipynb`:
  - The "Plot Mosaics for all the Options" cell no longer passes a hardcoded `cell_types`
    list into `plot_mosaics_for_datasets` (it now auto-detects + excludes). The `cell_types`
    variable itself is still defined in that cell because it's reused later in the notebook
    for the single-experiment analysis (`pipeline.plot_rfs`, `get_spike_xarr`) -- that part
    was left alone. Round 2 added an `EXCLUDE_CELL_TYPES` list defined right in that same
    cell (so it's easy to find and edit) and passes it as `exclude_cell_type_keywords`.
  - Swapped the order of the two cells under "Show Stim Information": the cell that reads
    `stimulus_data['epoch_parameters'].iloc[0]` used to run *before* the cell that defines
    `stimulus_data = stim_block.df_epochs`, which raised a `NameError`. Now the definition
    runs first. Stale outputs on both cells were cleared -- **you'll need to rerun them.**
  - **Round 3:** replaced the "Plot Some Results" cell (`dd15cd6f`, spike count vs. space
    constant). You'd already flagged that space constant/stixel size isn't varied within a
    SpatialNoise block for this setup (the noise seed changes every 2 epochs instead, which
    isn't summarized here). Per your choice, this is now a simple per-cell-type spike count
    summary (baseline-subtracted, mean +/- SEM across cells) for the single block already
    loaded -- a quick QC check that cells are responding, no swept parameter needed. Reuses
    `spike_times`/`spike_counts`/`baseline_spike_counts` from the cell above; no new data
    pulled. Outputs/execution_count cleared -- rerun to see it.

## What was intentionally NOT changed

Per yas's explicit answer, these known rough edges were left alone (out of scope for this
pass): the "Globals file does not have RTMP tag" retry behavior and "_params.mat file not
found" warnings that show up elsewhere (e.g. inside `create_mea_pipeline` / `stim.py`).
Those live in a different chunk-resolution code path that yas asked to leave untouched.

## Provenance / how to see exactly what changed

- `changes/yas_pre_existing_changes_vs_upstream_2026-07-28.diff` -- a snapshot of yas's
  own local edits, captured *before* Claude touched anything, as a diff against
  `origin/main` (upstream `DRezeanu/retinanalysis`). This is entirely yas's own prior work.
- `changes/claude_changes_2026-07-28.txt` -- a diff of only Claude's edits from this
  session, i.e. yas's version (above) vs. the current state. This is entirely Claude's work.
- These two files together should let you reconstruct: upstream -> yas's edits -> Claude's
  edits, as three distinguishable layers.

## Verification

- `python -m py_compile src/retinanalysis/utils/datajoint_utils.py` passes.
- The notebook JSON was re-validated (`json.load` succeeds, 23 cells, cell order and
  content spot-checked).
- No test suite covers `plot_mosaics_for_datasets` directly (it depends on a live
  DataJoint DB + real sorted data on the `B:\Array-data` drive, which isn't reachable from
  this environment), so this could not be run end-to-end here. Instead, the core logic
  (dedup, exclude-keyword matching, and the auto-detect-then-filter pipeline) was extracted
  into standalone scripts with stubbed-out `AnalysisChunk`/`plot_rfs` and run directly --
  all scenarios passed, including reproducing the exact `20250910A` triple-duplicate
  scenario from your original log (confirmed the chunk now loads once, not three times) and
  a mixed-label case (`on/brisk sustained`, `on/brisk transient`, `Unknown`, `nc17`,
  `OnLarge`, `BigMas`, `weak` -> only the two brisk types kept). The round 3 spike-count
  summary cell's xarray logic was also run against a synthetic `spike_times`/`spike_counts`
  array shaped like `get_spike_xarr()`'s real output (same dims/coords) and produced finite,
  sensible mean/SEM values. **Please rerun the mosaic cell and the spike-count summary cell
  in the notebook against your real data to confirm it looks right end to end** -- flag
  anything unexpected and we'll fix it.

## Reproduction / re-review notes

To re-check the fix against the exact failure you saw before: re-run the "Plot Mosaics for
all the Options" cell and confirm that `20250910A` (which previously produced 3 duplicate
plots of the same `data004` chunk) now either shows each of its real, distinctly-loadable
noise chunks at most once, or prints a single "No classification files found for any noise
chunk in 20250910A" line if none of them are classified.
