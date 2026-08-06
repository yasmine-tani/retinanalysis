"""
Spike-train cross-correlation analysis between pairs of cells, including across different
NDF/light-level recordings of the same retina. Ported from three MATLAB scripts (a pairwise
cross-correlation (CCF) script, an extended 3-cell "triplet" version with 3D
joint-correlation plots, and a population Synchrony-Index-vs-distance script).

The full change history for this module lives in changes/correlated_spiking_demo_notes.md
and changes/claude_changes_2026-07-28.txt, not here.

DESIGN CHOICES:

1. Cross-chunk/cross-NDF cell mapping reuses the existing cluster_match()/ei_corr()
   functions in vision_utils.py rather than a new EI-matching routine -- the same functions
   already used for this purpose (matching cells between a reference AnalysisChunk and a
   target MEAResponseBlock/AnalysisChunk) in classes/mea_pipeline.py.

2. Spike times used for the correlation are the FULL, un-epoch-split spike train for a
   given block/datafile (matching the MATLAB scripts' spikes{idx}, the whole chunk's spike
   train, not sliced into trials) -- see get_full_spike_times_sec().

3. Which recording represents each NDF is resolved dynamically from the DataJoint database
   (get_exp_summary + a user-specified protocol_name), not from a hardcoded chunk/NDF path
   list.

4. Micron conversion: AnalysisChunk computes self.microns_per_stixel dynamically
   per-experiment in get_noise_params() (microns_per_pixel * canvas_size[0] / numXChecks,
   pulled from real epoch parameters), used instead of a hardcoded conversion factor.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from retinanalysis.utils.datajoint_utils import (
    find_classified_noise_chunk,
    get_exp_summary,
)

if TYPE_CHECKING:
    from retinanalysis.classes.analysis_chunk import AnalysisChunk
    from retinanalysis.classes.response import MEAResponseBlock

# MEA DAQ sample rate in Hz. Matches the SAMPLE_RATE constant already defined identically
# in classes/response.py, classes/raw.py, and classes/mea_pipeline.py -- this is a fixed
# property of the recording hardware/Vision file format, not an experiment parameter, so
# (unlike stimulus parameters) it is intentionally kept as a constant here too, consistent
# with the rest of the package rather than newly hardcoded by this module.
SAMPLE_RATE = 20000


def get_full_spike_times_sec(obj, cell_id: int) -> np.ndarray:
    """
    Get the full (whole-recording, not epoch-split) spike train for one cell, in seconds.

    Works for both AnalysisChunk and MEAResponseBlock, since both expose a `.vcd`
    (VisionCellDataTable) with `get_spike_times_for_cell`, which returns raw sample
    indices. This intentionally bypasses each class's own `get_spike_times()` /
    epoch-splitting logic, matching the MATLAB scripts' use of `datarun.spikes{idx}`, which
    is likewise the entire chunk's spike train rather than trial-sliced data.

    Parameters:
    obj (AnalysisChunk | MEAResponseBlock): object with a `.vcd` attribute.

    cell_id (int): cell id to pull spike times for.

    Returns:
    spike_times_sec (np.ndarray): sorted spike times in seconds, relative to the start of
    that chunk/datafile's recording.
    """
    raw_samples = obj.vcd.get_spike_times_for_cell(cell_id)
    spike_times_sec = np.sort(np.asarray(raw_samples, dtype=float) / SAMPLE_RATE)
    return spike_times_sec


def compute_ccf(
    spikes_a: np.ndarray,
    spikes_b: np.ndarray,
    window_size: float = 0.05,
    bin_size: float = 0.002,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Cross-correlation function (CCF) between two spike trains, i.e. a histogram of
    (spike_b_time - spike_a_time) for every pair of spikes within +/- window_size of each
    other: for every spike_a, spikes_b within the window are collected relative to spike_a,
    then all of those relative times across every spike_a are pooled into one histogram.
    Output is raw coincidence COUNTS (not normalized to a rate or probability).

    Parameters:
    spikes_a (np.ndarray): spike times (seconds) for the reference cell.

    spikes_b (np.ndarray): spike times (seconds) for the comparison cell.

    window_size (float): +/- time window around each spike_a, in seconds. Default 0.05 (50
    ms).

    bin_size (float): histogram bin width, in seconds. Default 0.002 (2 ms).

    Returns:
    ccf (np.ndarray): coincidence counts per bin, length = number of bins.

    bin_centers (np.ndarray): center time (seconds) of each bin, same length as ccf.
    """
    spikes_a = np.sort(np.asarray(spikes_a, dtype=float))
    spikes_b = np.sort(np.asarray(spikes_b, dtype=float))

    edges = np.arange(-window_size, window_size + bin_size, bin_size)
    bin_centers = edges[:-1] + bin_size / 2
    ccf = np.zeros(len(edges) - 1)

    if len(spikes_a) == 0 or len(spikes_b) == 0:
        return ccf, bin_centers

    # For each spike in A, find the slice of (sorted) spikes_b within the window via
    # searchsorted rather than a full nested loop -- vectorized per reference spike for
    # reasonable performance on whole-recording spike trains.
    lo_idx = np.searchsorted(spikes_b, spikes_a - window_size, side="left")
    hi_idx = np.searchsorted(spikes_b, spikes_a + window_size, side="right")

    all_diffs: List[np.ndarray] = []
    for t_a, lo, hi in zip(spikes_a, lo_idx, hi_idx):
        if hi > lo:
            all_diffs.append(spikes_b[lo:hi] - t_a)

    if all_diffs:
        pooled = np.concatenate(all_diffs)
        ccf, _ = np.histogram(pooled, bins=edges)

    return ccf, bin_centers


def compute_triplet_map(
    spikes_a: np.ndarray,
    spikes_b: np.ndarray,
    spikes_c: np.ndarray,
    window_size: float = 0.05,
    bin_size: float = 0.002,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Direct port of the inner loop of `triplecellcorrelatedspiking.m` (identical logic in
    `triplecorrelatedspikingwithvideos.m`, minus the video-export section -- static 3D plot
    only, no video export).

    For every spike in the reference train (spikes_a), finds spikes_b and spikes_c within
    +/- window_size of that reference spike, then accumulates the FULL cross product of every
    (b_relative_time, c_relative_time) pair into a 2D histogram -- i.e. this is a joint
    co-occurrence map, not just two independent 1D CCFs stacked together. Equivalent to:
        for i = 1:length(spikes_A)
            t_ref = spikes_A(i);
            B_rel = spikes_B(within window) - t_ref;
            C_rel = spikes_C(within window) - t_ref;
            if ~isempty(B_rel) && ~isempty(C_rel)
                [p, q] = meshgrid(B_rel, C_rel);
                triplet_map = triplet_map + histcounts2(p(:), q(:), edges, edges);
            end
        end
    (only spike_a's that have AT LEAST ONE nearby spike in BOTH b and c contribute anything
    -- an A-spike with a nearby B but no nearby C contributes nothing to the map.)

    Parameters:
    spikes_a/b/c (np.ndarray): spike times (seconds) for the reference cell (A) and the two
    comparison cells (B, C).

    window_size (float): +/- time window around each spikes_a spike, in seconds. Default 0.05
    (50 ms).

    bin_size (float): histogram bin width, in seconds, applied to BOTH axes (B and C). Default
    0.002 (2 ms) -- same defaults as compute_ccf, since the source script uses the same
    edges/bin_size for both the plain pairwise CCF and the triplet map.

    Returns:
    triplet_map (np.ndarray): 2D array, shape (n_bins, n_bins). triplet_map[i, j] = count of
    (B-relative-time in bin i, C-relative-time in bin j) pairs, pooled across every
    contributing A-spike. Row axis (dim 0) is B's relative time, column axis (dim 1) is C's
    relative time -- matches MATLAB's histcounts2(B_values, C_values, edges, edges) N(i,j)
    convention (B indexes rows, C indexes columns) exactly, so if you build a plotting grid via
    `np.meshgrid(bin_centers, bin_centers, indexing='ij')` the first output varies along axis 0
    (B) and the second along axis 1 (C), keeping the same B=rows/C=columns meaning all the way
    through to the plot.

    bin_centers (np.ndarray): center time (seconds) of each bin, same for both axes (shared
    edges), length = n_bins.
    """
    spikes_a = np.sort(np.asarray(spikes_a, dtype=float))
    spikes_b = np.sort(np.asarray(spikes_b, dtype=float))
    spikes_c = np.sort(np.asarray(spikes_c, dtype=float))

    edges = np.arange(-window_size, window_size + bin_size, bin_size)
    bin_centers = edges[:-1] + bin_size / 2
    n_bins = len(edges) - 1
    triplet_map = np.zeros((n_bins, n_bins))

    if len(spikes_a) == 0 or len(spikes_b) == 0 or len(spikes_c) == 0:
        return triplet_map, bin_centers

    lo_b = np.searchsorted(spikes_b, spikes_a - window_size, side="left")
    hi_b = np.searchsorted(spikes_b, spikes_a + window_size, side="right")
    lo_c = np.searchsorted(spikes_c, spikes_a - window_size, side="left")
    hi_c = np.searchsorted(spikes_c, spikes_a + window_size, side="right")

    # For each A-spike with at least one nearby B and at least one nearby C, accumulate the
    # full cross product of (b_rel, c_rel) pairs -- matches MATLAB's
    # meshgrid(B_rel, C_rel) + histcounts2(p(:), q(:), edges, edges) inside the loop over A.
    for t_a, lb, hb, lc, hc in zip(spikes_a, lo_b, hi_b, lo_c, hi_c):
        if hb > lb and hc > lc:
            b_rel = spikes_b[lb:hb] - t_a
            c_rel = spikes_c[lc:hc] - t_a
            # Full cross product of every (b_rel, c_rel) pair, matching MATLAB's
            # meshgrid(B_rel, C_rel) + histcounts2(p(:), q(:), edges, edges).
            bb, cc = np.meshgrid(b_rel, c_rel, indexing="xy")
            h, _, _ = np.histogram2d(bb.ravel(), cc.ravel(), bins=[edges, edges])
            triplet_map += h

    return triplet_map, bin_centers


def compute_synchrony_index(
    spike_trains: Dict[int, np.ndarray],
    bin_size: float = 0.01,
    duration: Optional[float] = None,
) -> pd.DataFrame:
    """
    Direct port of `compute_population_si` from `SI_vs_RF_microns.m`: Synchrony Index
    SI = log2(P_joint / P_chance) for every pair of cells in spike_trains.

    ONE SIMPLIFICATION vs. the source script: it bins spikes in two steps -- 1ms bins, then
    OR-downsamples groups of `bin_factor` 1ms bins into a 10ms "any spike in this window"
    boolean via `sum(reshape(vec_1ms, bin_factor, [])) > 0`. Directly histogramming at the
    final 10ms resolution and checking `> 0` produces an IDENTICAL boolean-per-10ms-bin result
    (the 1ms intermediate step isn't used for anything else), so that's what this does -- same
    output, without the two-stage reshape.

    ANOTHER SIMPLIFICATION: the source script bins each cell's spikes relative to per-epoch
    trigger times (`epoch_edges = -pre_time_sec : bin_size_plot : stimulus_duration_sec +
    tail_time_sec`, stitched across triggers). This module's spike trains
    (get_full_spike_times_sec) are already the WHOLE, un-epoch-split recording -- the same
    convention already established for compute_ccf/compute_triplet_map in this module. For a
    single continuous recording (a single stimulus_duration_sec value, not a per-trial one),
    trigger-stitching is mathematically identical to just binning the whole spike train
    directly, which is what this does. If a real correlation protocol block actually has
    MULTIPLE separate triggers/repeats per block (not a single continuous stimulus), this
    would need per-epoch stitching instead, which isn't implemented here.

    Parameters:
    spike_trains (Dict[int, np.ndarray]): {cell_id: spike_times_sec} for every cell to
    include -- e.g. one entry per Ref_ID mapped to its target-recording spike train at a given
    NDF (or the reference chunk's own spike train for the "NDF 0" / reference panel).

    bin_size (float): bin width in seconds for the binary "any spike in this window"
    representation. Default 0.01 (10ms), matching the source script's `bin_size_stats`.

    duration (Optional[float]): total time span (seconds) used to build bins [0, duration).
    Default None uses the latest spike time across every cell in spike_trains -- a reasonable
    stand-in for "the whole recording" when an explicit recording duration isn't available,
    but pass one explicitly (e.g. from a known stimulus length) if you want bins to extend
    past the last spike.

    Returns:
    df_si (pd.DataFrame): columns cell_a, cell_b, si -- one row per pair (cell_a < cell_b)
    with a DEFINED synchrony index. Pairs are dropped (not included with NaN) if
    P_joint == 0 (no observed coincidences) or P_chance == 0 (one or both cells never
    fired), since log2 of those is undefined/infinite. Empty (correctly-columned) dataframe if
    fewer than 2 cells have any spikes, or duration ends up 0.
    """
    cell_ids = sorted(spike_trains.keys())

    if duration is None:
        spike_maxes = [
            float(np.max(v)) for v in spike_trains.values() if len(v) > 0
        ]
        duration = max(spike_maxes) if spike_maxes else 0.0

    empty = pd.DataFrame(columns=["cell_a", "cell_b", "si"])
    if duration <= 0 or len(cell_ids) < 2:
        return empty

    edges = np.arange(0, duration + bin_size, bin_size)

    binary_by_cell = {}
    for cid in cell_ids:
        counts, _ = np.histogram(np.asarray(spike_trains[cid], dtype=float), bins=edges)
        binary_by_cell[cid] = counts > 0

    p_single = {cid: float(np.mean(binary_by_cell[cid])) for cid in cell_ids}

    rows = []
    for cell_a, cell_b in itertools.combinations(cell_ids, 2):
        joint = np.logical_and(binary_by_cell[cell_a], binary_by_cell[cell_b])
        p_joint = float(np.mean(joint))
        p_chance = p_single[cell_a] * p_single[cell_b]
        if p_joint > 0 and p_chance > 0:
            si = float(np.log2(p_joint / p_chance))
            if np.isfinite(si):
                rows.append({"cell_a": cell_a, "cell_b": cell_b, "si": si})

    if not rows:
        return empty

    return pd.DataFrame(rows, columns=["cell_a", "cell_b", "si"])


def get_ndf_blocks_for_protocol(
    exp_name: str,
    protocol_name: str,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Find one datafile (block) per NDF light level for a given protocol, using the real
    DataJoint experiment summary rather than a hardcoded NDF -> path list.

    Parameters:
    exp_name (str): experiment name, e.g. '20251016A'.

    protocol_name (str): exact protocol name to filter to (e.g.
    'manookinlab.protocols.SpatialNoise'). NDF is not unique per block in this schema --
    multiple protocols can share an NDF -- so this filter is required to get one
    correlation-source block per NDF rather than an arbitrary one.

    verbose (bool): print what was found. Default True.

    Returns:
    df_ndf_blocks (pd.DataFrame): one row per NDF actually present for this protocol, with
    at least 'NDF', 'datafile_name', 'block_id' columns, sorted by NDF ascending. If a given
    NDF has more than one matching block (protocol re-run), the earliest by block_id is
    kept and this is printed. Empty dataframe (not None) if nothing is found, so callers can
    check len(df) == 0 without a None-check.
    """
    df_exp_summary = get_exp_summary(exp_name)
    if df_exp_summary is None or len(df_exp_summary) == 0:
        if verbose:
            print(f"No experiment summary found for {exp_name}.")
        return pd.DataFrame(columns=["NDF", "datafile_name", "block_id"])

    df_proto = df_exp_summary.query("protocol_name == @protocol_name").copy()
    if len(df_proto) == 0:
        if verbose:
            print(f'No "{protocol_name}" blocks found for {exp_name}.')
        return pd.DataFrame(columns=["NDF", "datafile_name", "block_id"])

    df_proto = df_proto.dropna(subset=["NDF"]).sort_values("block_id")

    rows = []
    for ndf_val, df_ndf in df_proto.groupby("NDF"):
        chosen = df_ndf.iloc[0]
        if len(df_ndf) > 1 and verbose:
            print(
                f"{exp_name}: {len(df_ndf)} '{protocol_name}' blocks found at NDF "
                f"{ndf_val}: {list(df_ndf['datafile_name'])}. Using the earliest, "
                f"{chosen['datafile_name']}."
            )
        rows.append(
            {
                "NDF": ndf_val,
                "datafile_name": chosen["datafile_name"],
                "block_id": chosen["block_id"],
            }
        )

    df_ndf_blocks = pd.DataFrame(rows).sort_values("NDF").reset_index(drop=True)

    if verbose:
        print(
            f"{exp_name}: found {len(df_ndf_blocks)} NDF level(s) for '{protocol_name}': "
            f"{list(df_ndf_blocks['NDF'])}"
        )

    return df_ndf_blocks


def _normalize_cell_type_label(s: str) -> str:
    """
    AnalysisChunk.get_df()'s pick_type_from_parts (analysis_chunk.py) always stores a
    matched on/off type as "<prefix>/<base>" -- e.g. "off/brisk transient", WITH a slash.
    Cell-type strings elsewhere are sometimes written with a plain space instead ("off
    brisk transient"), which would fail an exact-match comparison against the real stored
    value even though the cells genuinely exist. This normalizes '/', '-', and '_' to a
    single space (and lowercases), so 'off brisk transient', 'off-brisk-transient',
    'off_brisk_transient', and the real stored 'off/brisk transient' all compare equal.
    """
    return " ".join(s.replace("/", " ").replace("-", " ").replace("_", " ").split()).lower()


def get_cell_ids_of_type(
    analysis_chunk: "AnalysisChunk",
    cell_type: str,
    typing_file: Optional[str] = None,
    verbose: bool = True,
) -> np.ndarray:
    """
    Get the cell_ids in an AnalysisChunk classified as a given cell_type, matching the
    filtering pattern already used in demos/7_contrast_response_demo.ipynb (typing_file_N
    columns of df_cell_params) rather than a new helper class.

    Parameters:
    analysis_chunk (AnalysisChunk): must have .typing_files and .df_cell_params populated
    (i.e. constructed without b_load_spatial_maps=False being combined with skipping
    get_df() -- this is the default AnalysisChunk behavior).

    cell_type (str): cell-type string to match, e.g. 'off/brisk transient' (the real stored
    format -- on/off-typed cells are stored as "<prefix>/<base>"). Not a strict exact
    match -- '/', '-', '_', extra whitespace, and case are all normalized before comparing
    (see _normalize_cell_type_label), so 'off brisk transient' or 'off-brisk-transient'
    also match the real 'off/brisk transient' value. Distinct labels that only differ in
    real words (e.g. 'on/off brisk sustained' vs. 'brisk sustained') still never collide --
    only separator punctuation/whitespace is treated as equivalent.

    typing_file (Optional[str]): which typing file to use. Default None picks the first
    file with "classification" in its name (case-insensitive), same rule used elsewhere in
    this package (plot_mosaics_for_datasets, demo 7).

    verbose (bool): print which typing file and how many cells were found. Default True.

    Returns:
    cell_ids (np.ndarray): cell_ids of that type, sorted ascending. Empty array if the type
    isn't found or no classification file exists. If empty because cell_type didn't match
    anything (not because there's no classification file at all), the real available type
    strings in this file are printed unconditionally (not gated behind verbose) -- so the
    actual strings are visible to copy instead of guessing at separator formatting.
    """
    if typing_file is None:
        classification_files = [
            f for f in analysis_chunk.typing_files if "classification" in f.lower()
        ]
        if not classification_files:
            if verbose:
                print(
                    f"No classification file found for {analysis_chunk.exp_name} "
                    f"{analysis_chunk.chunk_name}."
                )
            return np.array([], dtype=int)
        typing_file = classification_files[0]

    if typing_file not in analysis_chunk.typing_files:
        if verbose:
            print(f"Typing file {typing_file} not found in this AnalysisChunk's typing_files.")
        return np.array([], dtype=int)

    file_idx = analysis_chunk.typing_files.index(typing_file)
    col = f"typing_file_{file_idx}"
    available = analysis_chunk.df_cell_params[col].values
    target_norm = _normalize_cell_type_label(str(cell_type))
    mask = np.array([_normalize_cell_type_label(str(v)) == target_norm for v in available])
    cell_ids = np.sort(np.asarray(analysis_chunk.cell_ids)[mask])

    if verbose:
        print(
            f"{analysis_chunk.exp_name} {analysis_chunk.chunk_name} ({typing_file}): "
            f"{len(cell_ids)} cell(s) of type '{cell_type}'."
        )

    if len(cell_ids) == 0:
        available_types = sorted(set(str(v) for v in available))
        print(
            f"No cells matched {cell_type!r} in {typing_file} (checked case/separator- "
            f"insensitively -- '/', '-', '_', and extra whitespace are all treated the "
            f"same). Real type strings present in this file: {available_types}"
        )

    return cell_ids


def get_cell_pairwise_distances(
    analysis_chunk: "AnalysisChunk",
    cell_ids,
    units: str = "microns",
) -> pd.DataFrame:
    """
    Computes ordinary Euclidean distance between RF centers for every pair of the given
    cell_ids, in whichever unit you ask for -- same unit convention (microns/pixels/stixels)
    already used by plot_rfs()/get_ells(), so a distance printed here matches what you'd
    measure directly off a plot_rfs(units='microns') mosaic of the same cells. Uses
    AnalysisChunk's RF center (self.rf_params[cell_id]['center_x'/'center_y'], in stixel
    units, set in get_rf_params()) and its stixel->micron conversion factor
    (self.microns_per_stixel, computed dynamically per-experiment in get_noise_params()
    from real epoch parameters).

    Parameters:
    analysis_chunk (AnalysisChunk): must have .rf_params populated (default AnalysisChunk
    behavior -- get_rf_params() runs in __init__).

    cell_ids: cell_ids to compute pairwise distances between. Typically a meaningful subset
    (e.g. the "matched at every NDF" cells from a master_table -- see
    build_master_mapping_table), not necessarily every cell of a type, since cells outside
    that subset can't contribute a full cross-NDF CCF panel set anyway.

    units (str): 'microns', 'pixels', or 'stixels'. Default 'microns'.

    Returns:
    df_pairs (pd.DataFrame): one row per UNORDERED pair (cell_a < cell_b), columns
    'cell_a', 'cell_b', 'distance' -- sorted by distance ascending (closest/most likely
    "neighbor" pairs first). Empty dataframe (with these columns, not None) if fewer than 2
    cell_ids are given, so callers can check len(df) == 0 without a None-check.
    """
    if "microns" in units.lower():
        scale_factor = analysis_chunk.microns_per_stixel
    elif "pixels" in units.lower():
        scale_factor = analysis_chunk.pixels_per_stixel
    elif "stixels" in units.lower():
        scale_factor = 1
    else:
        raise NameError("units must be 'microns', 'pixels', or 'stixels'.")

    cell_ids = [int(c) for c in cell_ids]
    empty = pd.DataFrame(columns=["cell_a", "cell_b", "distance"])
    if len(cell_ids) < 2:
        return empty

    rows = []
    for cell_a, cell_b in itertools.combinations(sorted(cell_ids), 2):
        if cell_a not in analysis_chunk.rf_params or cell_b not in analysis_chunk.rf_params:
            continue
        xa = analysis_chunk.rf_params[cell_a]["center_x"] * scale_factor
        ya = analysis_chunk.rf_params[cell_a]["center_y"] * scale_factor
        xb = analysis_chunk.rf_params[cell_b]["center_x"] * scale_factor
        yb = analysis_chunk.rf_params[cell_b]["center_y"] * scale_factor
        dist = float(np.hypot(xa - xb, ya - yb))
        rows.append({"cell_a": cell_a, "cell_b": cell_b, "distance": dist})

    if not rows:
        return empty

    df_pairs = pd.DataFrame(rows).sort_values("distance", ascending=True).reset_index(drop=True)
    return df_pairs


def build_master_mapping_table(
    exp_name: str,
    cell_type: str,
    protocol_name: str,
    reference_chunk_name: Optional[str] = None,
    ss_version: str = "kilosort2.5",
    corr_threshold: float = 0.85,
    typing_file: Optional[str] = None,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, "AnalysisChunk", Dict[float, "MEAResponseBlock"]]:
    """
    Build a master cell-mapping table across NDF light levels -- the Python equivalent of
    the "Create Master Mapping Table" step in the MATLAB correlation scripts (which uses
    map_ei chunk-by-chunk). Reuses the existing cluster_match()/ei_corr() EI-matching
    functions (vision_utils.py) -- the same ones already used for cross-chunk matching in
    classes/mea_pipeline.py -- rather than a new matching routine.

    Reference (classification) cells come from the noise/classification chunk found by
    find_classified_noise_chunk() (or reference_chunk_name if you already know it). Target
    cells for each NDF come from whichever block ran `protocol_name` at that NDF, resolved
    dynamically via get_ndf_blocks_for_protocol() -- nothing here is a hardcoded
    chunk/NDF -> path list.

    Parameters:
    exp_name (str): experiment name, e.g. '20251016A'.

    cell_type (str): exact cell-type string to restrict the mapping to (e.g.
    'off brisk transient'). Only reference cells of this type are looked up in the master
    table; this keeps the table (and any downstream CCF loop) scoped to cells you actually
    care about instead of every cell in the chunk.

    protocol_name (str): exact protocol name whose per-NDF blocks provide the spike data
    to be mapped/correlated (e.g. the protocol you want cross-correlations computed during).

    reference_chunk_name (Optional[str]): chunk_name (or datafile_name, for newer
    chunk-less experiments) to use as the classification/EI reference. Default None calls
    find_classified_noise_chunk(exp_name) to auto-pick it, same convention used in demos 6
    and 7.

    ss_version (str): spike-sorting version subfolder. Default 'kilosort2.5'.

    corr_threshold (float): EI-correlation cutoff passed to cluster_match() as corr_cutoff.
    Default 0.85.

    typing_file (Optional[str]): which classification file to use for cell_type filtering.
    Default None auto-picks the first file with "classification" in its name.

    verbose (bool): print progress (which chunks/blocks are loaded, matching results).
    Default True.

    Returns:
    master_table (pd.DataFrame): one row per reference cell of cell_type, with columns
    'Ref_ID' and 'NDF{n}_ID' for each NDF found for protocol_name (float NaN where a cell
    could not be mapped at that NDF).

    ref_chunk (AnalysisChunk): the reference/classification AnalysisChunk, kept around so
    callers can pull the reference cell's own spike times
    (get_full_spike_times_sec(ref_chunk, ref_id)) for an "NDF 0" / reference-level
    correlation, treating the classification chunk's own spikes as the top light level.

    d_ndf_blocks (Dict[float, MEAResponseBlock]): the loaded MEAResponseBlock for each NDF,
    keyed by NDF value, so callers can pull mapped cells' spike times without reloading.
    """
    from retinanalysis.classes.analysis_chunk import AnalysisChunk
    from retinanalysis.classes.response import MEAResponseBlock
    from retinanalysis.utils.vision_utils import cluster_match

    if reference_chunk_name is None:
        reference_chunk_name = find_classified_noise_chunk(
            exp_name, ss_version=ss_version, verbose=verbose
        )
        if reference_chunk_name is None:
            raise ValueError(
                f"Could not auto-find a classified noise chunk for {exp_name}. Pass "
                "reference_chunk_name explicitly."
            )

    if verbose:
        print(f"Loading reference chunk {reference_chunk_name} for {exp_name} ...")
    ref_chunk = AnalysisChunk(
        exp_name,
        reference_chunk_name,
        ss_version=ss_version,
        verbose=verbose,
    )

    ref_ids = get_cell_ids_of_type(
        ref_chunk, cell_type, typing_file=typing_file, verbose=verbose
    )
    if len(ref_ids) == 0:
        # get_cell_ids_of_type already printed the real available type strings above
        # (unconditionally, not gated behind verbose) right before returning empty --
        # pointing back at that instead of repeating the list here.
        raise ValueError(
            f"No cells of type '{cell_type}' found in reference chunk "
            f"{reference_chunk_name} -- see the real available type strings printed just "
            "above (cell_type is matched case/separator-insensitively, but the actual "
            "words still have to match)."
        )

    master_table = pd.DataFrame({"Ref_ID": ref_ids})

    df_ndf_blocks = get_ndf_blocks_for_protocol(exp_name, protocol_name, verbose=verbose)
    if len(df_ndf_blocks) == 0:
        raise ValueError(
            f"No '{protocol_name}' blocks found for {exp_name} at any NDF."
        )

    d_ndf_blocks: Dict[float, "MEAResponseBlock"] = {}

    for _, row in df_ndf_blocks.iterrows():
        ndf_val = row["NDF"]
        datafile_name = row["datafile_name"]
        if verbose:
            print(f"Mapping NDF {ndf_val} ({datafile_name}) ...")

        resp_block = MEAResponseBlock(
            exp_name=exp_name,
            datafile_name=datafile_name,
            ss_version=ss_version,
            include_ei=True,
            verbose=verbose,
        )
        d_ndf_blocks[ndf_val] = resp_block

        match_dict, _corr_dict = cluster_match(
            ref_chunk, resp_block, corr_cutoff=corr_threshold, verbose=verbose
        )

        mapped_ids = [match_dict.get(ref_id, np.nan) for ref_id in ref_ids]
        n_mapped = int(np.sum(~pd.isna(mapped_ids)))
        if verbose:
            print(f"  -> mapped {n_mapped} / {len(ref_ids)} cells at NDF {ndf_val}.")

        master_table[f"NDF{ndf_val:g}_ID"] = mapped_ids

    return master_table, ref_chunk, d_ndf_blocks
