# Correlated spiking demo -- notes

## 2026-07-29: new demo 8 (pairwise cross-correlation across NDF light levels)

### What was asked for

Three MATLAB scripts, pasted together in one message:

1. A pairwise cross-correlation (CCF) analysis between two named cells
   (`cell_id_A`, `cell_id_B`), tracked across NDF light levels via EI-based cell
   mapping (`map_ei`) from a "high light" reference/classification chunk, with a
   saved "master mapping table" (`writetable(..., 'master_cell_mapping.xlsx')`).
2. The same, extended to 3 cells ("triplets"): adds a 2D joint-correlation
   histogram (cell B and cell C spike times relative to cell A) rendered as a
   rotating 3D surface, plus HD `.mp4` + `.gif` export of the rotation.
3. A population "Synchrony Index (SI) vs. distance" analysis: pairwise SI
   (`log2(P_joint / P_chance)`) between every pair of cells of a given type,
   plotted against physical (micron) distance, using STA-fit centers converted
   from stixels via a `microns_per_stixel` factor yas flagged as possibly wrong
   ("idk if the microns conversion is right it should be somewhere in the
   date[data]").

### Scope decided (asked via AskUserQuestion, since this is a large, genuinely new
piece of functionality -- nothing like it existed in the package before)

- Cross-chunk/NDF cell mapping: **reuse the existing `cluster_match()`/`ei_corr()`**
  in `vision_utils.py` rather than port a new EI-matching routine. (Yas's first
  answer to this question was "idk im confused" -- rather than re-ask a
  confusing technical question, I went with the recommended/default option,
  since it's the lower-risk choice: reusing already-tested code that's already
  used for this exact purpose in `mea_pipeline.py`, instead of writing new
  matching logic. Flag this back to me if that's not what you wanted.)
- v1 scope: **pairwise CCF only** (script 1). The 3-cell triplet/3D/video-export
  piece (script 2) and the population SI-vs-distance piece (script 3) are **not
  built yet** -- yas picked "Pairwise CCF" when given the choice of all three.
- Data source: whole, un-epoch-split spike trains per block/datafile (matching
  the MATLAB scripts' `datarun.spikes{idx}`), for a protocol you specify
  dynamically rather than a hardcoded stimulus.

### The micron-conversion question, answered directly

Checked `AnalysisChunk.get_noise_params()` (`classes/analysis_chunk.py`, ~line
284): `self.microns_per_stixel = self.microns_per_pixel * self.pixels_per_stixel`,
where `pixels_per_stixel = canvas_size[0] / numXChecks`, and
`microns_per_pixel`/`canvas_size`/`numXChecks` are all pulled from real DataJoint
epoch `parameters` -- **this is already computed per-experiment from real data,
not hardcoded**. It should directly replace the hardcoded `56.40888888888889` in
script 3, whenever that piece gets built. Not used by v1 (no distances computed
in the CCF-only version), but flagging this now since it directly answers what
you asked.

### New code

`src/retinanalysis/utils/correlation_utils.py` (new file):

- `SAMPLE_RATE = 20000`: matches the identical hardcoded constant already in
  `response.py`/`raw.py`/`mea_pipeline.py`. This is a DAQ hardware constant (not
  a stimulus/experiment parameter), so -- unlike stimulus parameters elsewhere in
  this project -- it's intentionally kept as a constant here too, for consistency
  with the rest of the package, rather than something new that got hardcoded by
  this change.
- `get_full_spike_times_sec(obj, cell_id)`: full (non-epoch-split) spike times in
  seconds for one cell, works on both `AnalysisChunk` and `MEAResponseBlock`
  (both have `.vcd`). Bypasses each class's own epoch-splitting `get_spike_times()`.
- `compute_ccf(spikes_a, spikes_b, window_size=0.05, bin_size=0.002)`: raw
  coincidence-count cross-correlogram, matching the MATLAB triplet script's
  window/bin defaults (its simpler pairwise script didn't specify bin size, so
  the triplet script's numbers -- the only concrete ones given -- are used for
  both). Vectorized via `np.searchsorted` rather than a literal nested loop.
- `get_ndf_blocks_for_protocol(exp_name, protocol_name)`: one datafile per NDF
  for a given protocol, read from `get_exp_summary()` -- replaces the MATLAB
  scripts' hardcoded `ndf_paths`/`ndf_list` cell arrays with a live database
  lookup. NDF is not unique per block in this schema (multiple protocols can
  share an NDF), so `protocol_name` is required, not optional.
- `get_cell_ids_of_type(analysis_chunk, cell_type, typing_file=None)`: same
  typing-file-column filtering pattern already used in demo 7, factored out so
  it isn't copy-pasted a third time.
- `build_master_mapping_table(exp_name, cell_type, protocol_name, ...)`: the
  Python equivalent of the MATLAB "Create Master Mapping Table" step. Loads the
  reference/classification chunk once (via `find_classified_noise_chunk`, same
  picker demos 6/7 already use), gets its cells of `cell_type`, then for every
  NDF found for `protocol_name` loads that block (`MEAResponseBlock`) and calls
  `cluster_match(ref_chunk, resp_block, corr_cutoff=corr_threshold)`. Returns the
  mapping table, the reference `AnalysisChunk`, and a `{NDF: MEAResponseBlock}`
  dict so the notebook doesn't reload anything to get spike times afterward.

Registered in `src/retinanalysis/__init__.py` right after `tuning`, using the
same lazy-import-inside-function pattern already used in `vision_utils.py` for
`AnalysisChunk`/`MEAResponseBlock`/`cluster_match`, to avoid circular imports
(this module needs classes that are themselves imported after utils).

`demos/8_correlated_spiking_demo.ipynb` (new, 6 code cells + 6 markdown cells):
choose `exp_name` -> print every block found (datafile/protocol/NDF) so
`CORRELATION_PROTOCOL_NAME` and `CELL_TYPE` are picked from real data, not
guessed -> build the master mapping table -> pick `cell_id_A`/`cell_id_B` from
`Ref_ID` -> plot CCF panels: one for the reference/classification chunk's own
spike train (matching the MATLAB script's "NDF 0" plot from
`datarun_classify.spikes`), plus one per NDF row of the mapping table where both
cells were successfully mapped (unmapped NDFs are skipped and printed, matching
the MATLAB scripts' `continue` behavior).

**Deliberate design point:** the reference/classification chunk (used for cell
typing + as the EI-matching source) is kept separate from the NDF-0 row of
`CORRELATION_PROTOCOL_NAME`'s own mapping table -- they are not assumed to be
the same recording, even though yas's MATLAB script effectively treats them as
one (it uses `datarun_classify.spikes` directly for its "NDF 0" plot). Both are
plotted in this notebook so this can be checked against real data rather than
silently assumed.

### Verification

- `compute_ccf` unit-tested against synthetic ground truth: known 10ms lag
  between two spike trains recovers a peak at the correct bin with the correct
  count; zero-overlap spike trains give an all-zero CCF; empty input handled
  without error; bin_centers always matches ccf length across several
  window/bin-size combinations.
- `get_ndf_blocks_for_protocol` and `get_cell_ids_of_type` unit-tested against
  synthetic stub dataframes/objects (module-stubbed via `sys.modules`, no real
  DataJoint/visionloader available in this sandbox): correct NDF grouping,
  correct earliest-block_id tie-break on a duplicated NDF, correct exclusion of
  a same-NDF row from a different protocol, correct cell-type filtering, correct
  "no classification file" fallback.
- `build_master_mapping_table` orchestration tested end-to-end against fully
  stubbed `AnalysisChunk`/`MEAResponseBlock`/`cluster_match` (3 synthetic NDFs
  with different, controlled mapping outcomes per NDF -- full match, partial
  match, no match): confirmed the returned table has the right shape/values,
  `NaN` for cells that didn't map, and the right `{NDF: block}` dict keys.
- Full end-to-end integration test: extracted the LITERAL cell source from the
  saved `.ipynb` and `exec()`'d all 6 code cells in order against synthetic spike
  data with a real, planted 10ms cross-correlation lag between two cells at 3
  different (fake) NDF blocks plus the reference chunk, one NDF deliberately left
  unmapped for one cell: all 4 valid panels were built (reference + 2 mapped
  NDFs; 1 NDF correctly skipped and printed), and the recovered CCF peak lag was
  within 1ms of the true 10ms lag in every panel.
- `nbformat.validate()` (normalized, no warnings) and `python -m py_compile` on
  the new utils file both pass.
- **Not yet verified against the live database.** `CORRELATION_PROTOCOL_NAME`,
  `CELL_TYPE`, `cell_id_A`/`cell_id_B` in the notebook are placeholders you'll
  set from your own experiment's printed block list.

### Not built yet (future work, same as flagged in Pending)

- 3-cell triplet joint-correlation maps + 3D surface plots + `.mp4`/`.gif` export
  (MATLAB script 2).
- Population Synchrony-Index-vs-distance (MATLAB script 3) -- the
  `microns_per_stixel` answer above is ready for this whenever it's built.

## Update 2026-07-30: cell-type mosaic, all-NDF-passed mosaic, auto neighbor-pair pick

yas: "can you also print a mosaic of the cell type too and then the mosaic of
those that passed the threshold in all the light levels and then can it not
automatically pick nearby cells to each other like neighbors and then have an
additional cell for inputting cell ids if so deem fit or is that not possible
to calculate the distance between the cells."

Answer to the last part first: yes, distance between cells is directly
computable. `AnalysisChunk` already has each cell's RF center
(`rf_params[cell_id]['center_x'/'center_y']`, stixel units) and a
per-experiment stixel->micron conversion (`microns_per_stixel`, computed
dynamically from real epoch parameters in `get_noise_params()` -- not the
hardcoded conversion factor yas's own MATLAB script used and had already
flagged as possibly wrong for other experiments). Nothing new needed to be
measured or estimated -- this was just never wired up into the notebook.

**New function**, `src/retinanalysis/utils/correlation_utils.py`,
`get_cell_pairwise_distances(analysis_chunk, cell_ids, units='microns')`:
ordinary Euclidean distance between RF centers for every unordered pair of
the given cell_ids, using the same unit convention (`'microns'`/`'pixels'`/
`'stixels'`) already used by `plot_rfs()`/`get_ells()`, so a distance printed
here matches what you'd measure directly off a `plot_rfs(units='microns')`
mosaic of the same cells. Returns a dataframe (`cell_a`, `cell_b`,
`distance`) sorted ascending -- closest pairs first. Auto-exported as
`ra.get_cell_pairwise_distances` (no `__all__` in this module, same as its
other functions).

**demos/8_correlated_spiking_demo.ipynb**, 4 new cells + 1 rewritten section
(12 -> 16 cells total):

1. New markdown+code pair right after the master-mapping-table build:
   "Mosaic: every reference cell of `CELL_TYPE`" ->
   `ref_chunk.plot_rfs(cell_types=[CELL_TYPE], label_cells=True, b_zoom=True,
   units='microns')`. Reuses the existing `plot_rfs` method directly (the
   same one the intro demo and demo 7 already use) -- no new plotting code,
   per the "logic is the same" principle already established for this repo.

2. New markdown+code pair after that: "Mosaic: cells that matched at every
   NDF". Computes `passed_all_ndf_ids` = the `Ref_ID`s where every
   `NDF{n}_ID` column in `master_table` is non-NaN (i.e. survived
   `CORR_THRESHOLD` EI-matching at every light level tested, not just some),
   prints the count and list, then plots the same `plot_rfs` mosaic
   restricted to `noise_ids=passed_all_ndf_ids`. This is also the candidate
   pool the neighbor auto-pick below draws from, since only these cells can
   contribute a full cross-NDF CCF panel set in the final plotting cell.

3. Rewrote "Pick two reference cells to correlate": now calls
   `ra.get_cell_pairwise_distances(ref_chunk, passed_all_ndf_ids,
   units='microns')`, prints/displays the full sorted pair-distance table,
   and auto-sets `cell_id_A`/`cell_id_B` to the CLOSEST pair by default
   (yas's "automatically pick nearby cells to each other like neighbors").
   Kept the original manual-override capability yas explicitly asked to keep
   ("an additional cell for inputting cell ids if so deem fit") -- the same
   `cell_id_A`/`cell_id_B` variables are still just plain assignments you can
   edit directly in that cell (commented-out override lines added as an
   explicit prompt), and the existing validation (`raise ValueError` if a
   cell_id isn't a real `Ref_ID`) is unchanged. Fallback: if fewer than 2
   cells matched every NDF, falls back to the original "first two rows of
   master_table" behavior with a printed explanation, rather than crashing
   with no valid pair to pick from.

### Verification

- `python -m py_compile src/retinanalysis/utils/correlation_utils.py` --
  passes.
- `nbformat.validate()` + all code cells re-compiled on the 16-cell notebook
  -- passes.
- `get_cell_pairwise_distances` unit-tested standalone (module loaded
  directly via `importlib`, with `retinanalysis.utils.datajoint_utils`
  stubbed out since it's an unrelated top-level import in the same file, not
  a reimplementation) against a synthetic 4-cell layout with known geometry:
  correctly identified the closest pair (verified against the exact expected
  Euclidean distance, `8.0 * sqrt(2)` microns for a 1-stixel-diagonal
  separation with `microns_per_stixel=8.0`), correctly computed a plain
  5.0-stixel distance in `'stixels'` units, and correctly returned an empty
  (but correctly-columned) dataframe for a single-cell input.
- Full integration test: extracted the LITERAL updated notebook cells and
  `exec()`'d them against a fake `ref_chunk` (records `plot_rfs` calls
  instead of actually rendering, so this runs headless) and a synthetic
  5-cell `master_table` (3 cells matched every NDF, 2 didn't, one closest
  pair planted among the 3): confirmed the cell-type mosaic cell calls
  `plot_rfs(cell_types=[CELL_TYPE], ...)` correctly; confirmed
  `passed_all_ndf_ids` correctly excluded the 2 partially-matched cells and
  the mosaic cell called `plot_rfs(noise_ids=[1, 2, 3], ...)`; confirmed the
  auto-pick cell correctly selected the planted closest pair
  (`cell_id_A=1, cell_id_B=2`, 11.3 um apart) over the third, farther cell.
  Separately tested the fallback path (only 1 cell matched every NDF):
  confirmed it correctly falls back to the first two `Ref_ID` rows with the
  explanatory print, instead of crashing on an empty distance table.
- **Not yet verified against the live database** -- same caveat as every
  other piece of this demo; I have no DataJoint/data access from here.

## Update 2026-07-30 (later): "No cells of type 'off brisk transient' found" -- real bug, not empty data

yas ran `build_master_mapping_table` for real and hit `ValueError: No cells
of type 'off brisk transient' found in reference chunk data019`, and pushed
back correctly: "does it not allow there to not be all types lol also i
think there are some off brisk transient but."

Root cause: `AnalysisChunk.get_df()`'s `pick_type_from_parts` (the function
fixed for demo 7's hyphen/underscore bug two rounds ago) always stores a
matched on/off cell type as `"<prefix>/<base>"` -- WITH a slash, e.g.
`"off/brisk transient"`. But `get_cell_ids_of_type` (this demo's own
type-filtering function) compared against `CELL_TYPE` with plain `==`, and
demo 8's own `CELL_TYPE` default was written with a space instead of a slash
(`'off brisk transient'`) -- a mismatch I introduced myself when writing the
demo, same mistake, different location, as the bug fixed for demo 7 earlier
today. The cells genuinely existed; the query string just couldn't match the
real stored format.

**Fix**, `src/retinanalysis/utils/correlation_utils.py`:
- New `_normalize_cell_type_label(s)` helper: treats `/`, `-`, `_`, and
  extra whitespace as equivalent (and lowercases), same idea as the
  `_normalize_type_token` fix in `analysis_chunk.py`, extended to also cover
  `/` since that's the separator this module's comparisons actually deal
  with. `get_cell_ids_of_type` now compares normalized strings on both
  sides, so `'off brisk transient'`, `'off-brisk-transient'`, and the real
  `'off/brisk transient'` all match identically. Distinct real types (e.g.
  `'on/brisk sustained'` vs. `'off/brisk sustained'`) still never collide --
  only separator punctuation is treated as interchangeable, not the words.
- When nothing matches, `get_cell_ids_of_type` now unconditionally (not
  gated behind `verbose`) prints the real type strings present in the file,
  so the fix is copy-pasteable instead of another guess. `build_master_mapping_table`'s
  raised `ValueError` now points back at that printed list instead of just
  repeating the not-found string.
- Fixed demo 8's own `CELL_TYPE` default/example (cell 5) and its markdown
  description to use the real slash format, with a note that space/hyphen
  also work now.

### Verification
- `python -m py_compile` on `correlation_utils.py` -- passes.
- `nbformat.validate()` + all cells re-compiled on the notebook -- passes.
- Reproduced yas's exact scenario with a fake `AnalysisChunk` (2 real
  `'off/brisk transient'` cells stored with a slash, queried with a plain
  space like the old demo default): confirmed the fix finds both cells
  (previously would have found zero). Also confirmed a hyphenated query and
  the canonical slash query both find the same 2 cells, a genuinely
  nonexistent type still correctly returns empty and prints the real
  available types, and `'on/brisk sustained'` vs. `'off/brisk sustained'`
  remain correctly distinct (no false collision from the normalization).

## Update 2026-07-30 (latest): triplet joint-correlation + Synchrony-Index-vs-distance added

yas: "can we add the triple cell and si to the correlation 8 notebook" -- the two pieces
explicitly deferred back on 2026-07-29 when she picked "Pairwise CCF" as the v1 scope. She
uploaded the three original MATLAB scripts (`SI_vs_RF_microns.m`,
`triplecellcorrelatedspiking.m`, `triplecorrelatedspikingwithvideos.m`) since I no longer had
the literal source, only my own earlier summary.

**Scope confirmed via AskUserQuestion before building:**
- Triplet output: **static 3D plot only** (no `.mp4`/`.gif` video export) -- so
  `triplecorrelatedspikingwithvideos.m`'s section 4 (VideoWriter + rgb2ind/imwrite GIF loop)
  is intentionally NOT ported. Everything else in that script is identical to
  `triplecellcorrelatedspiking.m` (confirmed by diffing the two files), so one port covers
  both.
- SI-vs-distance scope: cells that matched at **every** NDF (same `passed_all_ndf_ids` pool
  already built for the neighbor auto-pick), **one plot per NDF** (not a single pooled plot),
  reusing her script's "fixed map strategy" (NDF0/reference RF coordinates for the x-axis
  distance on every panel, so a given cell pair's plotted distance is physically constant
  across light levels even though the SI itself is computed from that NDF's own spikes).

### New functions, `src/retinanalysis/utils/correlation_utils.py`

**`compute_triplet_map(spikes_a, spikes_b, spikes_c, window_size=0.05, bin_size=0.002)`** --
direct port of the inner loop of `triplecellcorrelatedspiking.m`. For every spike of
`spikes_a`, finds `spikes_b`/`spikes_c` within `+/- window_size`, and if BOTH have at least
one nearby spike, accumulates the FULL cross product of every `(b_relative_time,
c_relative_time)` pair into a shared 2D histogram (`edges x edges`) -- i.e. a genuine joint
co-occurrence map, not two independent 1D CCFs. Same `window_size`/`bin_size` defaults as
`compute_ccf`, matching her script's shared `edges` variable for both. Returns
`(triplet_map, bin_centers)`; `triplet_map[i, j]` = count with B-relative-time in bin `i`,
C-relative-time in bin `j` (B = rows/axis 0, C = columns/axis 1 -- matches MATLAB's
`histcounts2(B_values, C_values, ...)` convention exactly).

**`compute_synchrony_index(spike_trains, bin_size=0.01, duration=None)`** -- direct port of
`compute_population_si` from `SI_vs_RF_microns.m`. `SI = log2(P_joint / P_chance)` for every
pair of cells in `spike_trains` (a `{cell_id: spike_times_sec}` dict), where `P_single` = 
fraction of `bin_size`-wide bins containing >=1 spike, `P_joint` = fraction of bins where BOTH
cells fired, `P_chance = P_single_a * P_single_b`. Pairs with `P_joint == 0` or `P_chance ==
0` are dropped (matching her `if ~isnan(val) && ~isinf(val)` filter), not kept as NaN/-inf
rows.

TWO DELIBERATE SIMPLIFICATIONS vs. her MATLAB script, documented in the function's own
docstring rather than silently changed:
1. Her script bins at 1ms then OR-downsamples groups of `bin_factor` bins to 10ms
   (`sum(reshape(vec_1ms, bin_factor, [])) > 0`). Directly histogramming at the final 10ms
   resolution and checking `> 0` gives an IDENTICAL boolean-per-bin result (the 1ms
   intermediate step isn't used for anything else) -- same output, fewer steps.
2. Her script bins spikes relative to per-epoch TRIGGER times, stitched across triggers
   (`epoch_edges`/`cell2mat`/`arrayfun`). This function uses the WHOLE, un-epoch-split spike
   train instead -- the convention already established for `compute_ccf`/`compute_triplet_map`
   in this module, per yas's own earlier confirmation that this analysis should work "same as
   it's computed in the matlab script." Her own config value (`stimulus_duration_sec = 180.0`,
   a single number, not per-trial) describes ONE continuous recording, in which case her
   trigger-stitching reduces to exactly this. Flagged explicitly in the docstring in case her
   real correlation-protocol block actually has multiple separate triggers/repeats, which
   would need different handling (not implemented).

### `demos/8_correlated_spiking_demo.ipynb` (16 -> 22 cells)

1. Added `GENOTYPE = 'C57 WT'` to the config cell -- free-text label for plot titles only
   (matches her scripts' `genotype` variable), not used in any analysis logic.
2. New "Triplet: pick a third cell (C)" section -- auto-picks `cell_id_C` by walking
   `df_neighbor_pairs` (already computed for the A/B auto-pick) and taking the first pair that
   introduces exactly one cell not already in `{cell_id_A, cell_id_B}` -- i.e. the closest
   additional cell to the existing pair. Manual override preserved (same pattern as
   `cell_id_A`/`cell_id_B`).
3. New "Triplet joint-correlation (3D)" section -- one static `matplotlib` 3D surface (jet
   colormap, no edges, `view_init(elev=30, azim=-45)` matching her script's `view(-45, 30)`,
   no x/y axis labels + a descriptive title, matching her "CLEAN LABELS" comment) per light
   level: reference chunk (her "NDF 0") using its own spikes directly, then one per NDF where
   all 3 cells are mapped (skipped + printed otherwise, same pattern as the pairwise CCF loop).
4. New "Synchrony Index vs. distance" section -- one scatter plot (distance vs. SI, `y=0`
   reference line, matching her `plot_si`'s axis/style choices) per light level: reference
   panel using `passed_all_ndf_ids`' own reference-chunk spikes, then one per NDF using that
   NDF's mapped target spike trains, always plotted against the REFERENCE chunk's RF-center
   distances (`df_neighbor_pairs`, reused directly -- no recomputation needed since it's
   already exactly the right table).

### Verification
- `python -m py_compile src/retinanalysis/utils/correlation_utils.py` -- passes.
- `nbformat.validate()` + all code cells re-compiled on the 22-cell notebook -- passes.
- `compute_triplet_map` unit-tested: (a) a planted deterministic triplet (every A-spike
  followed by a B-spike at exactly +5ms and a C-spike at exactly +8ms, plus a noise-only
  A-spike with no nearby B/C) -- confirmed the total count matches exactly (3, one per real
  triplet, the noise spike contributes nothing) and the peak lands in the correct
  `(B~5ms, C~8ms)` bin; (b) explicit cross-product check (1 A-spike, 2 nearby B's, 3 nearby
  C's) -- confirmed exactly `2*3=6` counts, not `2` or `3`, confirming the full meshgrid cross
  product (not a paired zip) is being computed; (c) empty `spikes_a` correctly returns an
  all-zero map.
- `compute_synchrony_index` unit-tested against a hand-computable case (10 one-second bins;
  cell 1 and cell 2 fire in the exact same 5 bins -- perfectly synchronized; cell 3 fires in
  the complementary 5 bins -- zero overlap with cell 1): confirmed `SI(1,2)` equals the
  hand-computed value exactly (`log2(0.5/0.25) = 1.0`), and confirmed the zero-overlap pair
  `(1,3)` is DROPPED entirely (not present as a NaN/-inf row), matching her script's filter.
  Also confirmed `duration=None` auto-inference matches an explicit `duration` given by hand,
  and that a single-cell input returns an empty, correctly-columned dataframe.
- Full integration test: extracted the LITERAL updated notebook cells and `exec()`'d them in
  order against synthetic data (4 reference cells with a shared correlated spike source
  planted into cells 1/2/3 -- cell 3 spatially far but still correlated, cell 4 spatially
  close but independent -- plus a matching NDF1 recording with the same planted structure):
  confirmed the pairwise auto-pick correctly chose the physically closest pair (1, 2);
  confirmed the triplet auto-pick correctly chose cell 4 (closest remaining cell, even though
  it's UNcorrelated -- the auto-pick is purely spatial, matching how it's described to yas, not
  a "pick the most correlated triplet" heuristic); confirmed the triplet 3D-plot cell and the
  SI-vs-distance cell both ran without error end to end, producing panels for the reference
  chunk and NDF1. Separately sanity-checked `compute_synchrony_index`'s output on this same
  planted data outside the notebook context: the 3 genuinely-correlated pairs (1,2), (1,3),
  (2,3) all came out strongly positive (SI ~2.0-3.4), while every pair involving the
  independent cell 4 came out negative -- confirming the function recovers the right sign of
  a real, planted correlation structure, not just running without crashing.
- **Not yet verified against the live database** -- same caveat as every other piece of this
  demo.


## Update 2026-08-03: stripped change-history narrative out of the notebook

Same request as demo 7 (see changes/grating_and_contrast_demos_notes.md's
2026-08-03 (3) entry): every markdown section header and inline code comment
in `demos/8_correlated_spiking_demo.ipynb` and
`src/retinanalysis/utils/correlation_utils.py` that read like a changelog
entry -- `"NEW 2026-07-30 (Claude, per yas -- '...')"`, "yas's MATLAB
script", "her script", etc. -- was rewritten to plain, current-state
documentation. No dates, no attribution, no "here's what I changed and why"
narrative anywhere in either file. Full history stays in this file and
`changes/claude_changes_2026-07-28.txt`.

No logic changed anywhere -- only markdown text and comments/docstrings
(module docstring, and every function's docstring in correlation_utils.py:
compute_ccf, compute_triplet_map, compute_synchrony_index,
get_ndf_blocks_for_protocol, _normalize_cell_type_label, get_cell_ids_of_type,
get_cell_pairwise_distances, build_master_mapping_table).

### Verification
- `nbformat.validate()` + all 23 notebook cells re-compiled -- passes.
- `python -m py_compile` on `correlation_utils.py` -- passes.
- Grepped both files for `"per yas"`, `"Claude"`, `"CHANGED 20"`, `"FIXED 20"`,
  `"NEW 20"`, `"yas's"` -- zero matches left.
- Synthetic regression check against the cleaned-up `correlation_utils.py`
  (loaded directly, `datajoint_utils` stubbed to avoid a live DB import):
  `compute_ccf` and `compute_triplet_map` recover a planted 3-way coincidence
  exactly; `compute_synchrony_index` on two perfectly-correlated spike trains
  vs. one independent train still gives the correlated pair a strictly higher
  SI than the independent pair; `_normalize_cell_type_label` still treats
  `'off/brisk transient'` / `'off-brisk-transient'` / `'off brisk transient'`
  as equal; `get_cell_pairwise_distances` on 3 planted RF centers still
  returns the closest pair first with the exact expected distance. All
  confirm the docstring/comment rewrite didn't touch any logic.

## 2026-08-11: neighbor distance cutoff for Synchrony Index vs. distance (item 3c)

### Why

Item 3c of yas's post-meeting list (full list in `changes/repo_audit_2026-08-07.md`):
"Add an upper distance cutoff to correlated-spiking analysis -- compute each cell's
nearest-neighbor distance, use the median of that distribution, cap inclusion at
~1.5-2x that median." The "Synchrony Index vs. distance" section plots SI for every
pairwise combination among the cells that matched every NDF, with no distance limit --
including same-cell-type pairs on opposite sides of the array, which dilutes/biases
the real distance relationship with pairs that were never going to show meaningful
correlation regardless of distance.

### What changed

`src/retinanalysis/utils/correlation_utils.py` -- two new functions, both exported via
the existing `from .utils.correlation_utils import *` wildcard in `__init__.py` (no
`__all__` in this module, so both are automatically available as `ra.<name>`):

- `compute_nearest_neighbor_distances(df_pairs, cell_ids=None)`: for every cell, the
  minimum distance to any other cell in the set (from `get_cell_pairwise_distances`'s
  output). Returns a `pd.Series` indexed by cell_id.
- `get_neighbor_distance_cutoff(df_pairs, cell_ids=None, multiplier=1.75)`: median of
  those per-cell nearest-neighbor distances, times `multiplier`, as the cutoff. Median
  (not mean) so one cell with an unusually close or unusually isolated nearest
  neighbor doesn't skew the result. Default `multiplier=1.75` splits yas's stated
  "~1.5-2x" range -- pass 1.5 or 2.0 explicitly for either end. Returns a dict with
  `cutoff`, `median_nn_distance`, and the full `nn_distances` Series (for inspecting
  which cell has the most isolated nearest neighbor, which usually flags a sparse/
  incomplete mosaic rather than a real spacing outlier). NaN cutoff if fewer than 2
  cells have a defined nearest-neighbor distance.

`demos/7_correlated_spiking_demo.ipynb`:
- New cell (`NEIGHBOR_DISTANCE_MULTIPLIER = 1.75`) right after `df_neighbor_pairs` is
  built, computing and printing the median nearest-neighbor distance, the resulting
  cutoff, and how many of the pairs among `passed_all_ndf_ids` fall within it.
- `si_vs_distance_panel` (inside the "Synchrony Index vs. distance" cell) now drops
  any pair beyond that cutoff before plotting, prints how many pairs were dropped per
  panel, and notes the cutoff value in each panel's title.
- Does NOT affect the "Pick two reference cells to correlate" cell (already
  auto-picks the single closest pair, a cutoff doesn't change that) or the CCF/
  triplet sections (both work on one specific chosen pair, not a population).

### Verification

Unit-tested both new functions against a synthetic 1D mosaic (5 cells at
x = 0/100/200/310/900 microns -- 4 realistically-spaced cells plus one far outlier),
loaded directly with `retinanalysis.utils.datajoint_utils` stubbed (same technique
used for this module's other synthetic tests, avoids a live DB import):
- `compute_nearest_neighbor_distances` matched hand-computed expected values exactly
  (each of the 4 close cells' nearest neighbor is another close cell at 100-110um;
  the outlier's nearest neighbor is 590um away).
- `get_neighbor_distance_cutoff` computed median_nn_distance=100, cutoff=175
  (multiplier=1.75) -- confirmed all 3 immediately-adjacent pairs (100-110um) pass
  the cutoff, the outlier cell has zero pairs within the cutoff, and 2nd-order pairs
  (200-210um, farther than typical adjacent spacing allows) are correctly excluded
  too -- not just the obvious outlier.
- Edge cases: fewer than 2 cells, and an empty `df_pairs`, both return NaN
  cutoff/median as documented rather than raising.
- Notebook re-validated with `nbformat.validate()` + per-cell `compile()` after the
  edits (25 cells, 0 syntax errors).

**I do not have access to your DataJoint database from this environment, so this has
not been run against real correlated-spiking data.** The synthetic test confirms the
arithmetic given known cell positions; please run the notebook and check whether
`NEIGHBOR_DISTANCE_MULTIPLIER=1.75` feels right for your actual mosaic spacing, or
whether 1.5/2.0 (or something else) fits your data better.
