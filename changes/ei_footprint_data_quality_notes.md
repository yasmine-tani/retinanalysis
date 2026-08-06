# EI footprint across light levels -- data quality section (2026-08-04)

**Who made these changes:** Claude (Cowork), working from yas's instructions. New
functionality, not an edit to anything yas had already built.

## Summary

New "Data Quality: EI Footprint Across Light Levels" section at the end of
`demos/1_retinanalysis_intro.ipynb`, plus three new functions in
`src/retinanalysis/utils/ei_utils.py`. For one example cell in a reference chunk
(picked automatically, or set manually), shows its EI footprint -- a scatter of dots at
each electrode's real physical position, sized by that electrode's peak amplitude --
alongside its EI-matched counterpart at every other NDF the same protocol was run at,
one panel per NDF, plus a full-array context panel showing where the zoomed region
sits within the whole electrode array. Matches the style of a reference figure yas
shared (2x3 grid, `NDF X=<matched cell id>` / `cor = 0.XXX` titles per panel, red
full-array context panel for the reference).

## Why

Requested as a QC check: does a cell's electrical identity actually look consistent
across light levels, not just "did the correlation clear a threshold." A high
correlation number alone doesn't rule out an ambiguous or ill-conditioned match --
seeing the actual footprint shape side by side is a more direct sanity check.

## What's new

- `src/retinanalysis/utils/ei_utils.py`:
  - `_significant_electrode_mask(ei, significance_std=1.5)` (private): per-electrode
    boolean mask, reusing the exact "abs(value) >= significance_std * ei.std()"
    convention `ei_corr()`/`cluster_match()` (`vision_utils.py`) already uses to zero
    out noise electrodes before correlating -- only used here to decide the zoom
    window and which electrodes get highlighted red, not to change matching itself.
  - `plot_ei_footprint_across_ndfs(ref_vcd, ref_cell_id, ref_label, ndf_labels,
    ndf_vcds, ndf_cell_ids, ndf_corrs, ...)`: pure plotting, does no matching. One
    panel per NDF (electrode-position scatter, dot size = per-electrode peak |EI
    amplitude|, zoomed to a shared physical (x, y) bounding box computed from the
    reference cell's significant electrodes) plus one reference/full-array panel
    (all electrodes in light gray, significant electrodes in red). A missing match at
    a given NDF (`cell_id=None`) renders as a labeled "no match" panel instead of
    crashing. Marker sizes are normalized against the REFERENCE cell's own peak
    amplitude (not each panel's own max), so a real amplitude drop at a given NDF is
    visible as smaller dots there, not silently rescaled away.

    Different chunks can have different electrode counts (512 vs. 519 -- confirmed
    earlier this session as a real thing in yas's data, from inconsistent per-sort
    bad-channel exclusion). This function never assumes electrode arrays line up by
    index between chunks: every panel uses its OWN vcd's electrode map and EI array,
    and the shared zoom window is a physical (x, y) bounding box in microns, which
    stays valid regardless of electrode count differences.

  - `get_ei_matches_across_ndfs(ref_analysis_chunk, exp_name, protocol_name,
    ss_version='kilosort2.5', corr_cutoff=0.85, verbose=True)`: finds one datafile per
    NDF for `protocol_name` (via `get_ndf_blocks_for_protocol` -- real NDF values, not
    a hardcoded list), loads each as an `MEAResponseBlock`, and EI-matches every cell
    in `ref_analysis_chunk` against it using the EXISTING, UNMODIFIED
    `cluster_match()`/`ei_corr()` -- same convention already used for cell typing and
    cross-NDF CRF matching elsewhere in this package. Automatically skips the
    reference chunk's own NDF/datafile if it's among the blocks found (matching a
    chunk against itself is trivial, corr ~1.0, not useful to plot). Returns a tidy
    `(ref_cell_id, NDF, matched_cell_id, corr)` DataFrame plus a `{NDF: vcd}` dict for
    reuse by the plotting function (avoids reloading).
  - `pick_example_cell_for_footprint(df_matches)`: auto-picks whichever ref cell was
    matched at the most NDFs, tie-broken by highest mean correlation across those NDFs
    -- a cell that's cleanly trackable everywhere, not just lucky at one NDF.

- `demos/1_retinanalysis_intro.ipynb`: new markdown + code cell at the end (the two
  previously-empty trailing cells), using `analysis_chunk` (already built earlier in
  the notebook, has EIs loaded) as the reference and `analysis_chunk.noise_protocol`
  as the protocol to find other NDFs for. `CELL_ID_TO_CHECK` variable lets you check a
  specific cell instead of the auto-picked one.

## Open question -- matching convention doesn't match yas's MATLAB scripts

Yas shared her MATLAB `compare_map_ei_amr`/`map_ei_amr` scripts (a cross-validation
check: does restricting the EI-match candidate pool to a specific test-cell list give
the same answer as matching against the full population -- disagreement flags an
ambiguous match). Comparing `map_ei_amr` to our `ei_corr()`/`cluster_match()` found
real differences:
  - `corr_threshold` is 0.95 in `map_ei_amr` (and `compare_map_ei_amr` defaults to the
    same); ours defaults to 0.8 in `cluster_match()`, 0.85 in demo 7's grating section
    -- a meaningfully looser bar.
  - `map_ei_amr` requires >= `significant_electrodes` (default 10) electrodes above
    threshold or excludes the cell entirely before attempting a match. `ei_corr()` has
    no equivalent minimum-electrode-count gate.
  - The per-electrode "significance" summary differs: `map_ei_amr`'s `space_only` mode
    takes `max(ei, [], 2)` (raw signed max over time, NOT absolute value) then zeros
    anything below a fixed `electrode_threshold` of 5 (native EI units). `ei_corr()`
    (method='space') takes `max(abs(ei), axis=1)` (absolute value first) then zeros
    anything below 1.5x that cell's OWN EI standard deviation -- a per-cell relative
    threshold, not MATLAB's fixed absolute one. Whether this matters depends on
    whether yas's stored EI traces are spike-negative or already sign-flipped --
    unconfirmed, flagged to her, not assumed either way.

None of this has been changed -- `cluster_match()`/`ei_corr()` is used unmodified
everywhere in this package (cell typing, cross-NDF CRF matching, and now this new EI
footprint feature too), per yas's explicit direction ("idc how", i.e. proceed with the
existing convention rather than gate the new feature on reconciling this first). The
correlation numbers this new section shows reflect OUR existing convention, not
MATLAB's -- documented in both the function docstrings and the new notebook cell so
it's visible wherever this comes up again.

## Verification

- `python -m py_compile` on `ei_utils.py` -- passes.
- Synthetic render test against the REAL `plot_ei_footprint_across_ndfs` (loaded via
  `importlib`, fake electrode map + EI data with a localized "soma" hot spot and
  per-NDF amplitude/position jitter to simulate real cross-NDF variation, one NDF
  deliberately given no match to test that code path): rendered the figure, saved as
  PNG, and actually looked at it -- matches the reference image's style (2x3 grid,
  `NDF X=<id>` / `cor = 0.XXX` titles, dot size visibly shrinking for lower-amplitude
  panels, "no match" panel rendered in gray instead of crashing, red full-array
  context panel with the zoomed region highlighted).
- Synthetic tests against the REAL `get_ei_matches_across_ndfs` and
  `pick_example_cell_for_footprint` (loaded via `importlib`,
  `get_ndf_blocks_for_protocol`/`MEAResponseBlock`/`cluster_match` stubbed): confirmed
  a failed NDF load is skipped gracefully (not a crash), the resulting DataFrame
  aggregates matches correctly across NDFs, `pick_example_cell_for_footprint` picks
  the cell matched at the most NDFs (tie-broken by mean correlation) over a cell with
  a single higher-correlation match, and an empty result returns `None` instead of
  erroring. Separately confirmed the reference-chunk self-exclusion: when one of the
  found NDF blocks' `datafile_name` equals the reference chunk's own `chunk_name`,
  that NDF is skipped and does not appear in the output.
- `nbformat.validate()` and `compile()` on every code cell in
  `demos/1_retinanalysis_intro.ipynb` after the edit -- passes.
- Not yet re-verified against yas's live database -- **needs a kernel restart**
  (package-level change) the next time this notebook is run.

(A separate, unrelated cleanup in this same notebook -- two pre-existing hardcoded
values in the "Choose an Experiment"/"Initialize Analysis Pipeline" cells -- is
documented in `changes/demo1_intro_notes.md` instead, since it's not part of this EI
footprint feature.)

## Update 2026-08-05: ranked summary table + split into two cells

Per yas: browsing the ranked-by-trackability table should happen once (cheap to look
at), and picking a different cell to actually plot shouldn't require re-running the
whole cross-NDF EI-matching pass again.

**New in `ei_utils.py`:** `summarize_ei_matches(df_matches)` -- groups
`get_ei_matches_across_ndfs()`'s output by `ref_cell_id`, returns a DataFrame
(`ref_cell_id`, `n_ndfs_matched`, `mean_corr`, `min_corr`) sorted best-to-worst
(`n_ndfs_matched` desc, then `mean_corr` desc). `pick_example_cell_for_footprint()`
refactored to just take `summarize_ei_matches(...).iloc[0]` instead of re-deriving its
own aggregation -- same ordering, kept in one place so the ranked table and the
auto-pick can never disagree.

**Notebook (`demos/1_retinanalysis_intro.ipynb`):** the old single cell
(`8f3fbad9-11ab-43ff-9615-bc33d97c65f8`) is now two:

1. Same cell ID, now only runs `get_ei_matches_across_ndfs()` (the expensive part --
   reloads every other NDF's datafile and does the matching) and displays
   `summarize_ei_matches(df_ei_matches).head(20)` as a ranked table.
2. New cell (`76067e3f-8927-4dda-9ba3-12827bee67f7`), right after -- reads
   `CELL_ID_TO_CHECK` (now moved into this cell), reuses `df_ei_matches`/`ndf_vcds`
   already in memory from cell 1 (no reload), and calls
   `plot_ei_footprint_across_ndfs()`. Meant to be re-run on its own after changing
   `CELL_ID_TO_CHECK` to a `ref_cell_id` from the table -- cell 1 only needs to be
   re-run if `analysis_chunk` itself changes.

### Verification
- `nbformat.validate()` + `compile()` on every code cell in the notebook -- passes.
- `python -m py_compile` on `ei_utils.py` -- passes.
- Synthetic test (real `summarize_ei_matches`/`pick_example_cell_for_footprint`, loaded
  via `importlib`, fake `df_matches`): confirmed sort order (most-NDFs-matched first,
  ties broken by mean corr), confirmed `pick_example_cell_for_footprint` picks
  `summary.iloc[0]`, confirmed both handle an empty `df_matches` (empty DataFrame with
  the right columns / `None`) without erroring.
- Not yet re-verified against yas's live database -- notebook-cell-only change plus one
  new pure-pandas function, no kernel restart needed for the `ei_utils.py` part beyond
  picking up the new function (restart needed either way since it's a package edit).

## Update 2026-08-05 (2): EI footprint mosaic -- pick NDF + cell type, scrollable

Yas asked "what happened to the section in the ei mapping where there is an ndf line
and a cell type line... prints the ei mapping of the cells in those type as a
scrollable element" -- checked the full session history first (not just this
conversation's carried-over summary) and confirmed nothing like that had ever existed
in this section before; it was a mix-up with the PSTH cell built the same day in demo
7 (`PSTH_NDF_VALUES`/`PSTH_CELL_TYPE_GRATING`), which has the same two-selector shape.
Confirmed with yas this is a genuinely new feature, not a restoration, then built it.

**New in `ei_utils.py`:** `plot_ei_footprint_mosaic_for_cell_type(analysis_chunk,
df_matches, ndf_vcds, cell_type, ndf_val, typing_file=None, significance_std=1.5,
zoom_padding_frac=0.3, marker_scale=250.0, n_cols=4, verbose=True)`. One small panel
per cell of `cell_type`, all at one requested `ndf_val` -- complements (doesn't
replace) `plot_ei_footprint_across_ndfs()` above it, which is "one cell across every
NDF"; this is "one NDF, every cell of a type". Cell type membership comes from
`get_cell_ids_of_type()` (`correlation_utils.py`, unchanged -- same
case/separator-insensitive matching used everywhere else). Reuses
`df_matches`/`ndf_vcds` from `get_ei_matches_across_ndfs()` (already computed in the
first cell of this section) -- no new matching or NDF loading.

Deliberately does NOT share one zoom window / one amplitude scale across panels the
way `plot_ei_footprint_across_ndfs()` does -- that function's panels are all the SAME
physical cell at different light levels (so a shared scale makes a real amplitude drop
visible), but this mosaic's panels are DIFFERENT cells at different physical positions
on the array, so each panel computes its own zoom window (from its own significant
electrodes) and normalizes to its own peak amplitude. Checks whether each footprint
individually looks like a sensible, localized signature -- not a cross-cell amplitude
comparison.

**New in `contrast_response_utils.py`:** `scrollable_figure(fig, max_height_px=600,
dpi=100)` -- the figure equivalent of the existing `scrollable_prints()` (that
function's own docstring already notes matplotlib figures aren't stdout/stderr, so
they need a different mechanism). Renders `fig` to an in-memory PNG, base64-encodes it,
displays it in a `max-height + overflow-y` HTML div, then `plt.close(fig)` so Jupyter's
normal end-of-cell auto-display doesn't ALSO render an un-scrolled second copy.
Deliberately NOT using `cell.metadata['scrolled'] = True` -- that was tried earlier
this same day for the PSTH mosaic (now removed) and is flagged in this project's own
history (see `scrollable_prints()`'s docstring) as scroll-boxing a whole cell's output
rather than just one figure, and not reliably honored across notebook frontends.
Exported to the `ra.` namespace the same way `scrollable_prints` already is (wildcard
import, no `__all__` restriction in that file).

**Notebook (`demos/1_retinanalysis_intro.ipynb`):** new markdown (`a59c5216...`) + code
(`2717ecfe...`) cells inserted right after the existing footprint-plot cell
(`76067e3f...`). `EI_MOSAIC_NDF` (defaults to the highest/dimmest NDF found) and
`EI_MOSAIC_CELL_TYPE` (None = auto-pick first real, non-Unknown/Unmatched type) are the
two override lines. Calls `plot_ei_footprint_mosaic_for_cell_type(...)` then
`scrollable_figure(...)`.

### Verification
- `python -m py_compile` on `ei_utils.py` and `contrast_response_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell in
  `demos/1_retinanalysis_intro.ipynb` -- passes. Confirmed cell order: EI-match cell
  (24) -> footprint-plot cell (25) -> new mosaic cell (26-27).
- Synthetic test for `scrollable_figure` (real function, loaded via `importlib`, real
  `IPython.display` with only `display`/`HTML` monkeypatched -- same established
  pattern as `scrollable_prints()`'s own tests): confirmed `display()` gets called,
  confirmed the HTML contains the requested `max-height` and a base64 PNG `<img>`,
  confirmed the source figure gets closed (`plt.get_fignums()` count drops) so it
  doesn't double-render.
- Synthetic test for `plot_ei_footprint_mosaic_for_cell_type` (real function, loaded
  via `importlib` with `retinanalysis.utils.correlation_utils` loaded the same way and
  `retinanalysis.utils.datajoint_utils` stubbed out -- that module needs a live
  DataJoint connection at import time and isn't needed for this function; a fake
  `AnalysisChunk`/`VisionCellDataTable`/`df_matches`/`ndf_vcds`): confirmed cell-type
  filtering picks the right 3 of 5 fake cells, confirmed matched cells get a real panel
  titled `{ref} -> {matched}\ncor=X.XXX` and unmatched cells get a gray "no match"
  panel, confirmed the empty-cell-type and NDF-not-in-ndf_vcds cases each return a
  single-panel placeholder figure instead of erroring.
- Not yet re-verified against yas's live database -- package-level change to both
  files, needs a kernel restart plus re-running demo 1 down through the EI section.

## Update 2026-08-05 (3): rebuilt as rows=cells, columns=NDFs (not one-NDF-many-cells)

The "(2)" mosaic above was the wrong shape. Yas's actual complaint after trying it:
"no but i dont feel like its producing side by side plots of the sme cell it just has
which cell ids it mapped to with an arrow as the title but then no other plots also
have that id so im confused." Root cause: that version put ONE NDF per mosaic and a
DIFFERENT cell in every panel, so naturally no ref_cell_id ever repeated within the
same figure. What was actually wanted (confirmed): "side by side plots of the same
cell" for a whole cell type -- i.e. the existing single-cell-across-NDFs layout
(`plot_ei_footprint_across_ndfs`), repeated as one row per cell instead of picking one
cell at a time, with smaller panels ("mosaic vibes").

**`ei_utils.py`:** `plot_ei_footprint_mosaic_for_cell_type` rewritten in place (same
name, replaces the "(2)" version entirely rather than keeping both -- that version
answered a question nobody actually had). New signature: `ndf_values` (list or None,
was `ndf_val` singular) replaces the single-NDF parameter; added `panel_size` (inches
per square panel, default 1.7, small on purpose) and dropped `n_cols` (columns are now
NDFs, not a manual wrap count). Layout: row = cell (from `get_cell_ids_of_type`),
column = NDF. Per-row zoom window + amplitude scale come from that row's own reference
cell in `analysis_chunk.vcd` (same convention as `plot_ei_footprint_across_ndfs`'s
single-cell version) -- shared across that row's NDF columns, independent per row.
`marker_scale` default lowered 250 -> 120 to suit the smaller panels.

**Notebook:** cell `2717ecfe-06aa-4ed3-b449-7a21474c32f8` updated: `EI_MOSAIC_NDF`
(single value) -> `EI_MOSAIC_NDF_VALUES` (list or None = all NDFs in `ndf_vcds`).
`EI_MOSAIC_CELL_TYPE` unchanged. Markdown cell `a59c5216...` rewritten to describe the
new layout.

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell in
  `demos/1_retinanalysis_intro.ipynb` -- passes.
- Synthetic test (real `plot_ei_footprint_mosaic_for_cell_type`, loaded via
  `importlib` with `correlation_utils` loaded the same way and `datajoint_utils`
  stubbed, same pattern as the "(2)" test): fake AnalysisChunk with a `.vcd`, 3 cells
  of the target type, matches present for some (cell, NDF) pairs and missing for
  others. Confirmed panel count = n_cells x n_ndfs (3x2=6 for the default full set,
  3x1=3 when `ndf_values=[5]`), confirmed row labels (`cell {id}`) appear only in the
  first column and are in `cell_ids` order, confirmed matched panels get a real
  scatter + `NDF X\\n{matched_id} (r=Y)` title and unmatched panels get a gray "no
  match" title, confirmed an out-of-range `ndf_values` entry is dropped with a warning
  rather than erroring, confirmed the empty-cell-type case still returns a single
  placeholder figure.
- Not yet re-verified against yas's live database -- package-level change, needs a
  kernel restart plus re-running demo 1 down through the EI section. Note: yas had
  already run the previous ("(2)") version once against real data
  (`20260506A`/`data006`, 'off/brisk sustained', NDF 4.0, 22/25 matched) before asking
  for this rebuild, so the underlying data-loading path is confirmed working -- only
  the layout changed.

## Update 2026-08-05 (4): reference NDF surfaced, reference column added to mosaic (red)

Yas: "can you have the reference one at ndf 0 printed and the ei for just that one
mapped in red not black i think having the reference cell is crucial." Following up on
the "why are only NDF 3/4 available" question -- NDF 0 (the reference chunk's own NDF)
was always being silently skipped inside `get_ei_matches_across_ndfs` (matching a chunk
against itself is trivial), but the actual NDF value was never returned, only used
internally to decide what to skip.

**`ei_utils.py`:**
- `get_ei_matches_across_ndfs` now returns a 3-tuple: `(df_matches, ndf_vcds, ref_ndf)`
  -- `ref_ndf` is the NDF value matched against `ref_analysis_chunk.chunk_name` in
  `df_ndf_blocks` (the same lookup that already decided which block to skip), or `None`
  if the reference chunk's datafile wasn't found among this protocol's NDF blocks at
  all. BREAKING for any other caller unpacking 2 values -- checked, the only call site
  in the whole repo is the notebook cell, already updated (see below).
- `plot_ei_footprint_mosaic_for_cell_type` gets a new `ref_ndf=None` parameter -- when
  given, adds one more column (sorted into place by NDF value like any other column,
  not hardcoded first/last) showing each row's OWN reference-chunk footprint
  (`analysis_chunk.vcd`, already loaded per-row for the zoom window/scale) in red,
  titled `NDF {ref_ndf}\n{cell_id} (ref)`. Matches
  `plot_ei_footprint_across_ndfs()`'s existing red-reference-panel convention. Verbose
  print's "N of M panels matched" denominator excludes the reference column (it isn't
  a "match", it's the reference itself).

**Notebook (`demos/1_retinanalysis_intro.ipynb`):**
- Cell `8f3fbad9...`: unpacks `df_ei_matches, ndf_vcds, ref_ndf = ra.get_ei_matches_across_ndfs(...)`,
  prints "Reference chunk (data006) is at NDF {ref_ndf}."
- Cell `76067e3f...` (single-cell-across-NDFs plot): reference panel's label now
  includes the NDF value (`f'Reference ({analysis_chunk.chunk_name}, NDF {ref_ndf:g})'`)
  instead of just the chunk name.
- Cell `2717ecfe...` (mosaic): passes `ref_ndf=ref_ndf` through to
  `plot_ei_footprint_mosaic_for_cell_type`, and the printed summary line now mentions
  the reference column.

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell in
  `demos/1_retinanalysis_intro.ipynb` -- passes.
- Grepped the whole repo for `get_ei_matches_across_ndfs` call sites -- only the one
  notebook cell (already updated); no other code silently broken by the 2-tuple ->
  3-tuple return change.
- Synthetic test, `plot_ei_footprint_mosaic_for_cell_type` with `ref_ndf=0` (same fake
  3-cell/2-NDF dataset as the "(3)" update): confirmed a 3rd column appears (3 cells x
  3 columns = 9 panels, was 6), confirmed every row gets exactly one panel titled
  `NDF 0\n{cell_id} (ref)`, confirmed those panels' title color and scatter facecolor
  are both red (`ax.title.get_color() == 'red'`, `ax.collections[0].get_facecolor()`
  red-dominant RGBA) while non-reference panels stay black.
- Synthetic test, `get_ei_matches_across_ndfs` return shape: stubbed
  `get_ndf_blocks_for_protocol`/`MEAResponseBlock`/`cluster_match` (no live DB/Vision
  files touched) with a 3-block fake dataset (NDF 0.0 = reference, matching
  `chunk_name`; NDF 3.0, 4.0 = others). Confirmed `ref_ndf == 0.0`, confirmed
  `ndf_vcds` excludes NDF 0.0 and includes 3.0/4.0, confirmed the empty-blocks-found
  early-return path now returns a 3-tuple `(empty_df, {}, None)` instead of erroring on
  the old 2-tuple unpack.
- Not yet re-verified against yas's live database -- package-level change (return-shape
  change to a function with a real call site), needs a kernel restart plus re-running
  demo 1 down through the EI section.

## Update 2026-08-05 (5): marker sizes normalized by physical span, not screen size

Yas: "the like circled of the ei seem slightly too big... the zoomed in ones look fine
but the far away it feels..." then, after an explanation of why (matplotlib's `s` is a
fixed screen-space size, not tied to data coordinates -- a panel showing more physical
distance in the same figure size makes same-`s` dots look proportionally bigger),
follow-up: "i trust you... do whatever so it looks more legible, and maybe make the
squares all the same size some are big and some are tiny."

**New in `ei_utils.py`:** `_span_normalized_marker_scale(marker_scale, span,
reference_span, min_ratio=1/3, max_ratio=3.0)` -- rescales a marker_scale so dots
represent a roughly consistent PHYSICAL size across panels with different zoom spans.
Since `s` is an area and physical size scales linearly with span, the correct area
scale factor is `(reference_span / span) ** 2`, clipped (linear ratio clipped to
[1/3, 3] before squaring, so one outlier span can't blow sizes up 9x+ or shrink them to
near-invisible) to keep it bounded.

Applied in two places:
- `plot_ei_footprint_across_ndfs()`: the full-array reference panel (previously used
  the flat `marker_scale` for its red significant-electrode dots, same as the cropped
  NDF panels) now computes its own `ref_panel_marker_scale` from
  `_span_normalized_marker_scale(marker_scale, full_array_span, zoomed_span)` --
  `full_array_span` from the electrode map's actual x/y extent, `zoomed_span` from the
  shared crop window the NDF panels already use. Only the red (amplitude-scaled) dots
  are affected; the light-gray full-array context dots keep their small fixed size
  (`s=4`) since those were never the complaint.
- `plot_ei_footprint_mosaic_for_cell_type()`: restructured into two passes -- pass 1
  computes every row's zoom window/span up front (was previously computed and used
  immediately per row in a single pass); a median span across all rows is then used as
  `reference_span` for pass 2's actual drawing, so `row_marker_scale =
  _span_normalized_marker_scale(marker_scale, row_span, median_span)` replaces the flat
  `marker_scale` for both the reference (red) and matched (black) dots in that row.
  Rows with a wider footprint (bigger crop) get proportionally smaller max dot size;
  rows with a tighter footprint get proportionally bigger max dot size -- both trying
  to represent the same physical dot size rather than the same screen-space size.

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- Unit tests on `_span_normalized_marker_scale` directly: same span -> unchanged;
  3x-wider span -> shrinks; 1/3 span -> grows; extreme spans clip at the documented
  1/3x-3x linear (1/9x-9x area) bounds; degenerate (zero) span falls back to the
  unscaled `marker_scale` instead of dividing by zero.
- `plot_ei_footprint_mosaic_for_cell_type`, realistic-ish synthetic test (one cell with
  significant electrodes spread wide, one with them tightly clustered, same
  `marker_scale`): confirmed the wide-footprint row's max dot size ends up smaller than
  the narrow-footprint row's, opposite of the un-normalized behavior.
- `plot_ei_footprint_across_ndfs`, synthetic test with a REALISTIC localized EI (6
  significant electrodes clustered in a small neighborhood of a 200-electrode, 1800x1000
  micron array -- matching real array scale/electrode-count order of magnitude seen in
  yas's data): confirmed the full-array reference panel's red dots shrink well below the
  default `marker_scale=250` (max ~28 in this test) while the zoomed NDF panel's dots
  still range up to 250 for the truly max-amplitude electrode -- i.e. the far-away panel
  no longer looks disproportionately larger. (An earlier, less realistic test attempt
  with significant electrodes chosen at the extreme opposite ends of the array produced
  a zoom-padding artifact where the "zoomed" window ended up wider than the full array
  itself -- not a bug, just an unrealistic edge case for real EI footprint data, which
  is always spatially localized.)
- Full mosaic regression suite (no-reference-column, `ref_ndf` column, empty-cell-type,
  invalid-NDF cases) re-run after this change -- all still pass unchanged.
- Not yet re-verified against yas's live database -- package-level change, needs a
  kernel restart plus re-running demo 1 down through the EI section.

## Update 2026-08-05 (6): switched to yas's MATLAB electrode-significance convention

Yas: "i think there was a filter for how much noise it picks up... i think its
pickign up like way too mch of the cell." Found the actual filter in `map_ei_amr`
(sent earlier this session, see the "compare_map_ei_amr" / "map_ei_amr" exchange):
`electrode_threshold=5` (fixed absolute cutoff), `significant_electrodes=10` (minimum
count, or the cell gets excluded from matching entirely), applied to raw (non-abs)
`max(ei, axis=1)`.

Before implementing, verified the units question yas asked about: whether a MATLAB
threshold of "5" means the same thing applied to our Python-loaded EI values. Traced
the read path -- `EIReader.get_ei_for_cell_id()` and
`VisionCellDataTable.get_ei_for_cell()` (both in
`lib/artificial-retina-software-pipeline/utilities/visionloader/visionloader.py`) --
and confirmed neither applies any scaling/unit conversion; both are direct
byte-unpacks of the same `.ei` binary file Vision produces, which is the same file
MATLAB's own loader reads. No live MATLAB session available to do a byte-for-byte
numeric comparison, so this isn't 100% certain, but there's no scaling anywhere on the
Python side to cause a mismatch, and it would be unusual for a file-format reader to
invent its own scale factor for a standardized format other tools also read raw.
Recommended a cheap real-world check (compare `max(datarun.ei.eis{idx})` in MATLAB
against `vcd.get_ei_for_cell(id).ei.max()` in Python for the same cell) if yas wants
full certainty later.

Discussed whether to copy MATLAB's convention exactly. Recommended: yes for the fixed
threshold and the minimum-electrode gate (directly explains/fixes the "too much noise"
symptom -- the old adaptive `1.5 * ei.std()` threshold scaled with each EI's own
variance, so lower-variance cells got a looser absolute cutoff inconsistently).
Recommended AGAINST copying MATLAB's raw (non-abs) max -- many real spike waveforms
peak negative-going near the soma, so dropping abs() risks scoring a real,
large-amplitude electrode as insignificant if its positive rebound happens to be
small. Yas agreed: keep abs(), copy the threshold + minimum-count gate.

**`ei_utils.py`:**
- `_significant_electrode_mask(ei, electrode_threshold=5.0,
  min_significant_electrodes=10)` -- signature and behavior both changed. Was
  `(ei, significance_std=1.5) -> mask`; now `(ei, electrode_threshold=5.0,
  min_significant_electrodes=10) -> (mask, enough_electrodes)`. `mask` still uses
  `max(abs(ei), axis=1) >= electrode_threshold` (abs() kept), just against a FIXED
  value instead of `ei.std() * significance_std`. `enough_electrodes` is new -- True
  iff `mask.sum() >= min_significant_electrodes`. BREAKING for any other caller of the
  old 1-value-return signature -- checked, only 2 call sites in the whole repo, both
  updated (below).
- `plot_ei_footprint_across_ndfs`: `significance_std=1.5` param replaced with
  `electrode_threshold=5.0, min_significant_electrodes=10`. Unpacks
  `(sig_mask, enough_electrodes)`. Three distinct cases, each with its own message:
  (1) zero electrodes clear the threshold -- same top-20-by-amplitude fallback as
  before, warning updated to reference `electrode_threshold`; (2) some electrodes
  clear it but fewer than the minimum -- NEW: prints a warning including the cell's
  peak amplitude range (a sanity-check number, in case the threshold does turn out to
  be miscalibrated for this data), and the reference panel's title gets a
  `(only N/10 min sig. electrodes)` suffix; (3) normal case -- unchanged.
- `plot_ei_footprint_mosaic_for_cell_type`: same parameter replacement. Rows whose
  reference cell doesn't meet `min_significant_electrodes` get their y-axis row label
  suffixed `" *"` (e.g. `"cell 1234 *"`) instead of being silently drawn identically to
  every other row, and the verbose summary print now includes a count of how many rows
  were flagged.

**Notebook:** no cell edits needed -- neither of the two call sites
(`76067e3f-8927-4dda-9ba3-12827bee67f7`, `2717ecfe-06aa-4ed3-b449-7a21474c32f8`) passed
`significance_std` explicitly, so both pick up the new
`electrode_threshold`/`min_significant_electrodes` defaults automatically.

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- `nbformat.validate()` + `compile()` on every code cell in
  `demos/1_retinanalysis_intro.ipynb` -- passes.
- Grepped the whole repo for `_significant_electrode_mask`/`significance_std` call
  sites -- confirmed only the two updated functions call it, and no notebook cell
  passes the old `significance_std` keyword that would now silently break.
- Unit tests on `_significant_electrode_mask` directly: a mostly-noise EI with 15
  boosted electrodes -> 15 significant, `enough_electrodes=True` at the default
  minimum of 10, `False` when the minimum is raised to 20 (same mask, correctly
  reflects the stricter bar); an all-noise EI -> 0 significant, `enough_electrodes=False`.
- `plot_ei_footprint_mosaic_for_cell_type` regression suite re-run with the new API
  (realistic clustered-footprint fake EIs, 200 electrodes across a
  1800x1000-micron array): confirmed normal rows (15 sig. electrodes each, above the
  default minimum of 10) get plain `"cell {id}"` labels; confirmed a synthetic
  weak/sparse cell (only 3 boosted electrodes) gets `"cell 1 *"`; confirmed the
  verbose print's marginal-row count; re-confirmed `ref_ndf` column, empty-cell-type,
  and invalid-NDF cases all still behave as before.
- `plot_ei_footprint_across_ndfs` smoke test re-run with the new API -- still produces
  a reference panel with 2 scatter collections (gray full-array + red significant) and
  the expected title text.
- Not yet re-verified against yas's live database, and the exact-units assumption is
  not independently confirmed against a live MATLAB session -- flagged above as a cheap
  follow-up check yas can run if she wants full certainty. Needs a kernel restart plus
  re-running demo 1 down through the EI section either way (package-level change).

## Update 2026-08-05 (later): two-tier context + significant electrode draw

**Why:** yas posted a screenshot of the real mosaic output (cells 194/200/221 x NDF
4/3/0) showing dots covering most of every panel in a "solid blobby" pattern, worse for
wider-spread cells. My first-pass diagnosis (units mismatch making the crop window too
big) was wrong -- yas pushed back: "but the thing im saying is it looks the same as
when you had the scale factor function should we change the scale factor," which led to
the real cause: the zoomed panels were drawing **every** electrode, not just
significant ones, each sized by amplitude and floored at 0.5, then multiplied by the
row's span-normalized `marker_scale` (up to ~9x for wide-span rows). Wider rows have
more electrodes physically inside their (proportionally wider) crop, so more
near-noise electrodes each got a small-but-visible dot -- carpeting the panel.

I first proposed dropping non-significant electrodes from the zoomed panels entirely.
Yas corrected this: "wait but i still want to see the surroundign leectrodes i need
them to have a small dot so i knwo where it is on the array and what it spans like."
Final agreed design, applied everywhere a zoomed EI footprint is drawn: **every**
electrode gets a small, FIXED-size (not amplitude- or scale-multiplied) gray context
dot first, so array position/extent is always visible; THEN only electrodes clearing
`electrode_threshold` (for that specific panel's own EI) get a second, amplitude-scaled
dot drawn on top -- matching the gray-context/red-significant convention the dedicated
full-array reference panel already used.

**`ei_utils.py`:**
- `plot_ei_footprint_across_ndfs`'s internal `_draw_footprint(ax, vcd, cell_id, title)`
  helper (used for every zoomed match panel): now draws all electrodes as fixed `s=4`
  gray dots (`color="0.75"`), then recomputes that panel's own significant mask via
  `_significant_electrode_mask(ei, electrode_threshold, min_significant_electrodes)`
  and draws only those electrodes with amplitude-scaled black dots on top. Was one
  scatter call, all electrodes, amplitude-scaled and floored at 0.5.
- `plot_ei_footprint_mosaic_for_cell_type`'s drawing loop (PASS 2): same two-tier
  change applied to both branches -- the `ref_ndf` reference column (fixed `s=2` gray
  context, then red significant dots using a per-row mask recomputed from
  `row_data`'s already-loaded `ref_ei`) and the matched-cell column (fixed `s=2` gray
  context, then black significant dots using a mask recomputed from that specific
  matched cell's own EI, not inherited from the reference row). Both branches still use
  `row_marker_scale` (the existing span-normalized scale) for the significant tier only
  -- the context tier is deliberately NOT scaled by it, since letting the context dots
  grow with span was the original source of the clutter.
- No parameter signatures changed in either function -- this is purely internal to how
  each panel is drawn, so no notebook cell edits are needed.

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- New synthetic test (`test_two_tier.py`, fake 300-electrode array, 300-600 micron
  spread, 30 boosted "significant" electrodes vs. 270 noise electrodes below
  `electrode_threshold=5.0`) run against both functions:
  - `plot_ei_footprint_across_ndfs`: confirmed each zoomed panel draws exactly 2
    scatter collections, the first covering all 300 electrodes at one uniform fixed
    size (<=5 pts^2, independent of row span), the second covering only the ~30
    significant electrodes with sizes that vary by amplitude and reach above the
    context floor.
  - `plot_ei_footprint_mosaic_for_cell_type`: same check, for both the red reference
    column and the black matched column -- confirmed the context tier is fixed-size
    and covers every electrode, the significant tier is amplitude-scaled and covers
    only electrodes clearing the threshold.
  - `_significant_electrode_mask` basic + marginal cases re-run directly (10/10 and
    3/10 significant-electrode counts) -- still correct after the surrounding code
    changes.
- Not yet re-verified against yas's live database/real mosaic output -- needs a kernel
  restart and re-running demo 1's EI section (package-level change, same as prior
  updates in this file).

## Update 2026-08-06: stop boosting narrow-span rows, only shrink wide-span ones

**Why:** yas ran the two-tier fix above against her live database and sent screenshots.
The wide-span rows (cells 194/200/221) now look right -- clear tapering shape, no more
solid blob. But the narrow/zoomed-in rows (e.g. cells 105/107/117/120/122) got WORSE:
"the circles are like huge un some spots now, it made the zoomed in ones worse."

Root cause: `_span_normalized_marker_scale` clipped its ratio symmetrically to [1/3,
3] linear (up to 9x area boost for narrow-span rows, up to 9x shrink for wide-span
ones). Before the two-tier draw, that up-to-9x boost on narrow rows was invisible --
every electrode was still drawn, so lots of small background dots blended everything
into one texture. Once the two-tier draw removed the background clutter, the boosted
significant-tier dots in narrow-span rows were left bare, and since significant
electrodes by definition have amplitude close to the row's own peak, most of them
landed near the (now 9x inflated) size cap -- a cluster of huge, overlapping,
near-solid circles. But per yas's own earlier feedback, the narrow-span rows already
"look fine" at the flat, unboosted marker_scale -- only the wide-span rows were ever
reported oversized. So the boost side of the clip was solving a problem that didn't
exist and just needed to be removed, not re-tuned.

**`ei_utils.py`:**
- `_span_normalized_marker_scale(marker_scale, span, reference_span, min_ratio=1/3.0,
  max_ratio=1.0)` -- `max_ratio` default changed from `3.0` to `1.0`. Ratio is still
  `clip(reference_span / span, min_ratio, max_ratio)`, so wide-span rows (span >
  reference_span, ratio < 1) still shrink exactly as before; narrow-span rows (span <
  reference_span, ratio would be > 1) now clip at `1.0`, i.e. stay at the flat
  `marker_scale` baseline instead of being boosted. Both call sites
  (`plot_ei_footprint_across_ndfs`'s reference panel, `plot_ei_footprint_mosaic_for_cell_type`'s
  per-row scale) call this with default `min_ratio`/`max_ratio`, so no other code
  changes needed.

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- Direct calls to `_span_normalized_marker_scale`: narrow span (20) vs. reference span
  (200) now returns the unboosted baseline (100.0, was previously boosted toward 900.0
  at the old 9x cap); wide span (600) vs. reference (200) still shrinks to ~11.1 (2/3
  of the flat 1/9 area factor), unchanged from before -- confirms the fix is
  one-sided as intended.
- Not yet re-verified against yas's live database -- needs a kernel restart and
  re-running demo 1's EI section.

## Update 2026-08-06 (later): darker reference red

**Why:** yas: "make the red a darker red so it doesnt look like a fluorescent blob of
red." Matplotlib's plain `"red"` is fully saturated; against the gray context dots it
read as neon/fluorescent, especially now that the significant-electrode dots are
visually isolated (two-tier draw) rather than blended into surrounding clutter.

**`ei_utils.py`:** all reference-panel/reference-column red -- both the significant-dot
scatter color and the matching title text color -- changed from `"red"` to `"darkred"`
in both `plot_ei_footprint_across_ndfs` (dedicated full-array reference panel) and
`plot_ei_footprint_mosaic_for_cell_type` (red reference column). Also added
`alpha=0.85` to `plot_ei_footprint_across_ndfs`'s reference-panel dots for consistency
with every other red/black dot scatter in both functions (previously fully opaque,
inconsistent with the rest).

### Verification
- `python -m py_compile` on `ei_utils.py` -- passes.
- Grepped for remaining `color="red"`/`color='red'` in `ei_utils.py` -- none left,
  only `"darkred"` at both reference-panel/column sites.
- Purely a color/alpha constant change, no signature or behavior change -- no notebook
  edits needed, no new synthetic test required beyond the compile check.
