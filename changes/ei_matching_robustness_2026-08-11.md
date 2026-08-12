# EI-matching robustness: clear errors instead of a cryptic IndexError (2026-08-11)

**Who made these changes:** Claude (Cowork), per yas, in response to a real crash she
hit running `3_contrast_grating_demo.ipynb` against a dataset other than the ones
this had been tested against before.

## The crash

```
IndexError: tuple index out of range
```
at `vision_utils.py:942`, `num_pts = fixed_ref_eis.shape[1]`, inside `ei_corr()`,
called from `cluster_match()`, called from `MEAPipeline.__init__()`, called from
`create_mea_pipeline()`, called from `load_contrast_section()`.

## Root cause

`ei_corr()` builds `fixed_ref_eis` by flattening every reference cell's EI array and
stacking the results with `np.array([...])`. If the list being stacked is EMPTY (zero
cells), `np.array([])` produces a 1D array of shape `(0,)`, not a 2D array -- so
`.shape[1]` on the next line has no second axis to read, hence `IndexError: tuple
index out of range`.

The list ends up empty because `ref_ids = ref_object.cell_ids`, and both
`AnalysisChunk` and `MEAResponseBlock` already drop any cell whose
`get_ei_for_cell()` call fails (a per-cell `try`/`except` loop, printing `"WARNING:
No ei for ref cell id {id}, removing from..."` and filtering that id out of
`cell_ids`) -- for this dataset, EVERY cell in the reference chunk (or the target
block -- both sides can trigger the same symptom) apparently failed EI loading,
leaving `cell_ids` empty.

**Why this was so hard to diagnose from the traceback alone:** the per-cell
`WARNING: No ei...` lines that would have explained this are only printed one at a
time, easy to miss when there are dozens/hundreds of them -- and every notebook that
builds an `AnalysisChunk`/`MEAResponseBlock` (via `create_mea_pipeline`,
`load_contrast_section`, `build_master_mapping_table`, etc.) does so inside a `with
scrollable_prints():` block, which collapses exactly these warnings into a small
scrolled-away box. So the actual cause (zero cells with usable EIs) was real and
would have been visible if you scrolled that box open, but the crash itself gave no
hint to look there.

## What changed

Three files, same fix pattern in each -- turn a silent/easy-to-miss failure into an
unmissable one, as close to its real cause as possible:

- **`src/retinanalysis/classes/analysis_chunk.py`** (`AnalysisChunk.__init__`): after
  the existing per-cell EI-drop loop, added an unconditional summary print if any
  cells were dropped (`"EI loading summary for {chunk_name}: N / M cell(s) had no
  usable EI..."`), and a loud `"ERROR: 0 cells in {chunk_name} have a usable EI..."`
  line specifically when EVERY cell failed -- explaining directly that this will
  cause the cryptic `ei_corr` `IndexError` downstream if not addressed.
- **`src/retinanalysis/classes/response.py`** (`MEAResponseBlock.__init__`): same
  fix, same reasoning, for the target/response side (the other object that can
  trigger this).
- **`src/retinanalysis/utils/vision_utils.py`** (`ei_corr`): a real safety net,
  independent of the two changes above -- checks `fixed_ref_eis`/`fixed_test_eis`
  for `ndim < 2` or zero rows right before the line that used to crash, and raises a
  clear `ValueError` naming which side (ref or test) had the problem, how many
  ids were involved, and where to look for the underlying cause -- instead of the
  unexplained `IndexError`.

None of this changes what happens for a normal, working dataset -- the checks only
trigger in the exact "zero usable EIs" condition that used to crash uninformatively.
This does NOT fix why THIS dataset has zero usable EIs in the first place (that's a
data/environment question -- most likely either that chunk's `.ei` file doesn't
exist or was never computed for it, or there's some other systematic per-cell EI
load failure) -- it makes that root cause visible and diagnosable instead of buried
in a stack trace.

## Verification

Directly unit-tested `ei_corr()` (module loaded standalone, `visionloader` and the
`retinanalysis` package stubbed out since neither is available in this environment --
same technique used elsewhere in this repo for testing `vision_utils.py`/
`correlation_utils.py` without a live database):
- A normal case (3 reference cells, 2 test cells, consistent EI shapes) still
  produces the correct `(3, 2)` correlation matrix -- confirms the fix doesn't
  change behavior for working data.
- An empty reference-cell case raises `ValueError: ei_corr: no usable reference
  EIs (0 ref_ids, fixed_ref_eis shape (0,))...` instead of the old `IndexError`.
- An empty test-cell case raises the equivalent `ValueError` naming the test side.

**I do not have access to your DataJoint database from this environment, so I
cannot reproduce or diagnose the actual dataset that triggered this**, and I have
NOT verified `AnalysisChunk`'s/`MEAResponseBlock`'s new summary-print behavior
against a real EI-loading failure (only the downstream `ei_corr` check was directly
testable without real data). Please re-run the notebook against that dataset --
you should now see either the `"EI loading summary"` / `"ERROR: 0 cells..."` prints
(pointing at exactly which chunk/block has the problem) or the new `ValueError` from
`ei_corr` itself, instead of the unexplained `IndexError`. That won't make the
notebook run successfully on that dataset by itself, but it should tell you WHY it
can't, which is the actual blocker right now.

## Update 2026-08-11 (later same day): root cause found for the dataset that hit this

yas ran into exactly this crash for real (`exp_name='20260505A'`, `analysis_chunk_name='data017'`,
`ss_version='kilosort2.5'` default, actual data under `.../kilosort25/data017/`). Traced it
live, step by step, ruling out each layer before touching anything (per her explicit
"stop just changing stuff, ask me first"):

1. Path resolution was correct -- `_resolve_vision_data_path` landed on
   `B:\Array-data\sorted\20260505A\kilosort25\data017`, which does contain
   `data017.ei` (real file, ~212MB).
2. Reading `visionloader.load_vision_data`'s own source (pasted by yas from her
   installed package) showed EI loading uses
   `vcd.add_ei_from_loaded_ei_dict(eis_by_cell_id, restrict_to_existing_cells=include_params)`
   -- `get_analysis_vcd()` always passes `include_params=True`, so this looked like
   a plausible bug (EIs silently dropped for any cell without an RF-fit params
   entry). Checked directly: `data017`'s `.neurons`-derived cell_ids (394) and its
   `.params`-derived `main_datatable` keys (394) had **100% overlap** -- ruled this
   out, not the cause here.
3. Isolated the raw `.ei` file read with `visionloader.EIReader` directly, bypassing
   `load_vision_data`/`AnalysisChunk`/all of retinanalysis entirely:
   `EIReader(path, 'data017').get_all_eis_by_cell_id()` returned **0 EIs** -- an
   empty dict, straight from the library that's supposed to parse the file.
4. Ran the identical check against `data016` (a different chunk from the same
   experiment/sort) in the same environment: **260 EIs**, works fine. Since the
   exact same reader/code/environment succeeds on one chunk's `.ei` file and fails
   on another's, this rules out a `visionloader` version/environment issue and a
   retinanalysis code bug.

**Conclusion: this is specific to `data017.ei` itself** -- the file exists with a
plausible size but contains zero parseable EI entries, most likely because EI
computation for that chunk in Vision didn't actually finish/write correctly even
though it produced a file (or the file is otherwise corrupted). Not a retinanalysis
bug, not a `visionloader` bug, not "cells got weird IDs from a bad sort" -- a bad
`.ei` file for one specific chunk. Fix is to recompute EIs for `data017` in Vision
and re-run; the diagnostic error added earlier in this doc will now name this
condition clearly if it happens again for another chunk, rather than requiring this
whole trace again.

## On "so many notebooks only work with 1-2 datasets"

This specific crash is now diagnosable, not fixed at the data level -- the dataset
still needs a chunk/block with real, computed EI files to run EI-based matching at
all (that's a fundamental requirement of the matching approach `create_mea_pipeline`/
`build_master_mapping_table` use, not something code can route around). The broader
question -- how much of the notebook suite is genuinely dataset-agnostic vs.
implicitly tuned to the 1-2 datasets it's been run against so far -- hasn't been
audited systematically. If you want, a reasonable next step would be to go through
each demo notebook's assumptions one at a time (hardcoded protocol name guesses,
NDF-picking logic, cell-type vocabulary, required file types like `.ei`/`.sta`/
`.params`) and flag which are real requirements of the analysis vs. which are
untested guesses that happened to work for the datasets used so far.
