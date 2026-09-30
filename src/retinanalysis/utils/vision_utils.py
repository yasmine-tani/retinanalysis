from __future__ import annotations
from typing import Union, List, Dict, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from retinanalysis.classes.analysis_chunk import AnalysisChunk
    from retinanalysis.classes.response import MEAResponseBlock, MEAResponseGroup
    from visionloader import VisionCellDataTable

from retinanalysis.utils import DATA_DIR, ANALYSIS_DIR, get_exp_summary

import os
import numpy as np
from pandas import DataFrame

# from retinanalysis.utils.datajoint_utils import get_exp_summary
from visionloader import load_vision_data

from matplotlib.patches import Ellipse, Polygon
from matplotlib.colors import to_rgba
from matplotlib.path import Path as MplPath
from skimage.measure import find_contours
import xarray as xr
from collections import Counter


def patch_vision_double_array_bug() -> None:
    """
    Work around a bug found in a real installed visionloader build (2026-08-19, per
    yas -- timecourses showing as a flat line at 0 in the data quality demo, no error).

    visionloader's ParametersFileReader reads two kinds of '.params' fields: single
    values (x0, y0, SigmaX, SigmaY, Theta, ...) parsed directly in Python, and
    double-array values (RedTimeCourse, GreenTimeCourse, BlueTimeCourse, ...) filled in
    by a compiled extension, visionloader.cython_extensions.visionfile_cext
    .unpack_64bit_float_from_bytearray. Confirmed against a real chunk where every
    single-value field loaded correctly but every double-array field came back as
    uninitialized memory (denormalized floats around 1e-312, not real zeros) -- the
    array LENGTH was always right, only the VALUES were garbage, isolating the bug to
    that one compiled call.

    This replaces just that one call with an equivalent pure-Python implementation,
    using the same big-endian double format read correctly everywhere else in
    ParametersFileReader. Confirmed against the same real chunk to produce real,
    sane values afterward.

    Call this once, before building any AnalysisChunk/MEAPipeline (e.g. right after
    `import retinanalysis as ra`) -- anything already built before this runs will
    still have the old garbage values baked in and needs to be rebuilt. Safe to call
    more than once.
    """
    import visionloader.visionloader as _vl_mod

    def _pure_python_unpack_64bit_float(buffer_array, n_doubles, idx, out_array):
        raw = bytes(buffer_array[idx : idx + 8 * n_doubles])
        out_array[:] = np.frombuffer(raw, dtype=">f8", count=n_doubles)

    _vl_mod.vcext.unpack_64bit_float_from_bytearray = _pure_python_unpack_64bit_float
    print(
        "Patched visionloader's double-array '.params' field parsing (timecourses, "
        "etc.) to use a pure-Python fallback instead of the buggy compiled extension."
    )


def _resolve_vision_data_path(exp_name: str, chunk_name: str, ss_version: str) -> str:
    requested_versions = [version for version in [ss_version] if version]
    candidate_versions = list(dict.fromkeys(requested_versions + ["kilosort2.5", "kilosort25", "kilosort40", "kilosort4", "combined"]))

    candidate_dirs = []
    for version in candidate_versions:
        candidate_dirs.extend(
            [
                os.path.join(ANALYSIS_DIR, exp_name, chunk_name, version),
                os.path.join(DATA_DIR, exp_name, chunk_name, version),
                os.path.join(DATA_DIR, exp_name, version, chunk_name),
                os.path.join(ANALYSIS_DIR, exp_name, version, chunk_name),
                os.path.join(DATA_DIR, exp_name, version),
                os.path.join(ANALYSIS_DIR, exp_name, version),
            ]
        )

    candidate_dirs.extend(
        [
            os.path.join(DATA_DIR, exp_name, chunk_name),
            os.path.join(DATA_DIR, exp_name, chunk_name, "ksfiles"),
            os.path.join(DATA_DIR, exp_name, chunk_name, "kilosort2.5"),
            os.path.join(DATA_DIR, exp_name, chunk_name, "kilosort25"),
            os.path.join(DATA_DIR, exp_name, chunk_name, "kilosort40"),
            os.path.join(ANALYSIS_DIR, exp_name, chunk_name),
        ]
    )

    for candidate in candidate_dirs:
        if os.path.isdir(candidate):
            return candidate
    return candidate_dirs[0] if candidate_dirs else os.path.join(DATA_DIR, exp_name, chunk_name, ss_version)


def get_analysis_vcd(
    exp_name: str,
    chunk_name: str,
    ss_version: str,
    include_ei: bool = True,
    include_neurons: bool = True,
    verbose: bool = True,
) -> VisionCellDataTable:

    data_path = _resolve_vision_data_path(exp_name, chunk_name, ss_version)

    if verbose:
        print(f"Loading VCD from {data_path} ...")

    dataset_name = chunk_name
    if not os.path.isdir(data_path):
        dataset_name = ss_version
    elif not os.path.isfile(os.path.join(data_path, f"{dataset_name}.globals")):
        dataset_name = ss_version

    try:
        vcd = load_vision_data(
            data_path,
            dataset_name,
            include_ei=include_ei,
            include_noise=False,
            include_sta=False,
            include_params=True,
            include_runtimemovie_params=True,
            include_neurons=include_neurons,
        )
    except AssertionError as e:
        if "RTMP tag" not in str(e):
            raise
        # Globals file has no runtime movie parameters (RTMP tag). Load without them;
        # vcd.runtimemovie_params will be None. AnalysisChunk.get_noise_params() falls
        # back to assuming no STA cropping in this case.
        if verbose:
            print(
                "WARNING: Globals file has no RTMP tag, loading without runtime movie "
                "parameters. STA-crop correction will assume no cropping "
                "(see get_noise_params())."
            )
        vcd = load_vision_data(
            data_path,
            dataset_name,
            include_ei=include_ei,
            include_noise=False,
            include_sta=False,
            include_params=True,
            include_runtimemovie_params=False,
            include_neurons=include_neurons,
        )

    if verbose:
        print(f"VCD loaded with {len(vcd.get_cell_ids())} cells.\n")

    return vcd


def get_protocol_vcd(
    exp_name: str,
    datafile_name: str,
    ss_version: str,
    include_ei: bool = True,
    verbose: bool = True,
) -> VisionCellDataTable:

    resolved_ss_version = ss_version or "kilosort2.5"
    candidate_dirs = [
        os.path.join(DATA_DIR, exp_name, resolved_ss_version, datafile_name),
        os.path.join(DATA_DIR, exp_name, "kilosort25", datafile_name),
        os.path.join(DATA_DIR, exp_name, "kilosort40", datafile_name),
        os.path.join(DATA_DIR, exp_name, datafile_name, resolved_ss_version),
        os.path.join(DATA_DIR, exp_name, datafile_name),
        os.path.join(DATA_DIR, exp_name, resolved_ss_version),
        os.path.join(ANALYSIS_DIR, exp_name, resolved_ss_version, datafile_name),
        os.path.join(ANALYSIS_DIR, exp_name, "kilosort25", datafile_name),
        os.path.join(ANALYSIS_DIR, exp_name, datafile_name, resolved_ss_version),
        os.path.join(ANALYSIS_DIR, exp_name, resolved_ss_version),
    ]
    data_path = next((path for path in candidate_dirs if os.path.isdir(path)), candidate_dirs[0])

    if verbose:
        print(f"Loading VCD from {data_path} ...")

    vcd = load_vision_data(
        data_path, datafile_name, include_ei=include_ei, include_neurons=True
    )
    if verbose:
        print(f"VCD loaded with {len(vcd.get_cell_ids())} cells.\n")

    return vcd


def get_roi_dict(location: List[float], distance_x: float, distance_y: float):

    roi = dict()
    roi["x_min"] = location[0] - distance_x
    roi["x_max"] = location[0] + distance_x
    roi["y_min"] = location[1] - distance_y
    roi["y_max"] = location[1] + distance_y

    return roi


def cluster_match(
    ref_object: AnalysisChunk | MEAResponseBlock | MEAResponseGroup,
    test_object: AnalysisChunk | MEAResponseBlock | MEAResponseGroup,
    corr_cutoff: float = 0.8,
    method: str = "all",
    use_isi: bool = False,
    use_timecourse: bool = False,
    n_removed_channels: int = 1,
    verbose: bool = True,
):

    ref_ids = ref_object.cell_ids
    test_ids = test_object.cell_ids

    if "all" in method:
        arr_full_corr: np.ndarray = ei_corr(
            ref_object,
            test_object,
            method="full",
            n_removed_channels=n_removed_channels,
        )
        arr_space_corr: np.ndarray = ei_corr(
            ref_object,
            test_object,
            method="space",
            n_removed_channels=n_removed_channels,
        )
        arr_power_corr: np.ndarray = ei_corr(
            ref_object,
            test_object,
            method="power",
            n_removed_channels=n_removed_channels,
        )
    elif "full" in method:
        arr_full_corr: np.ndarray = ei_corr(
            ref_object,
            test_object,
            method=method,
            n_removed_channels=n_removed_channels,
        )
        arr_space_corr: np.ndarray = np.zeros(arr_full_corr.shape)
        arr_power_corr: np.ndarray = np.zeros(arr_full_corr.shape)
    elif "space" in method:
        arr_space_corr: np.ndarray = ei_corr(
            ref_object,
            test_object,
            method=method,
            n_removed_channels=n_removed_channels,
        )
        arr_full_corr: np.ndarray = np.zeros(arr_space_corr.shape)
        arr_power_corr: np.ndarray = np.zeros(arr_space_corr.shape)
    elif "power" in method:
        arr_power_corr: np.ndarray = ei_corr(
            ref_object,
            test_object,
            method=method,
            n_removed_channels=n_removed_channels,
        )
        arr_space_corr: np.ndarray = np.zeros(arr_power_corr.shape)
        arr_full_corr: np.ndarray = np.zeros(arr_power_corr.shape)
    else:
        raise NameError("Method property must be 'all', 'full', 'space', or 'power'")

    match_dict = dict()
    corr_dict = dict()
    match_count = 0
    bad_match_count = 0
    isi_corr = 1
    rgb_corr = 1

    if verbose:
        # to avoid circular imports, we're only importing classes inside the utils when needed for checking. Annoying but
        # this is just an issue with python
        from retinanalysis.classes.analysis_chunk import AnalysisChunk

        if isinstance(ref_object, AnalysisChunk):
            if isinstance(test_object, AnalysisChunk):
                ref_name = ref_object.chunk_name
                test_name = test_object.chunk_name
                print(
                    f"Cluster matching {ref_object.exp_name} {ref_name} with {test_name} ..."
                )
            else:
                ref_name = ref_object.chunk_name
                test_name = os.path.splitext(test_object.protocol_name)[1][1:]
                print(
                    f"Cluster matching {ref_object.exp_name} {ref_name} with {test_name} ..."
                )
        else:
            if isinstance(test_object, AnalysisChunk):
                ref_name = os.path.splitext(ref_object.protocol_name)[1][1:]
                test_name = test_object.chunk_name
                print(
                    f"Cluster matching {ref_object.exp_name} {ref_name} with {test_name} ..."
                )

            else:
                ref_name = os.path.splitext(ref_object.protocol_name)[1][1:]
                test_name = os.path.splitext(test_object.protocol_name)[1][1:]
                print(
                    f"Cluster matching {ref_object.exp_name} {ref_name} with {test_name} ..."
                )

    # Loop through all of the reference cells, comparing correlations against the test cells to find the best one
    for idx, ref_cell in enumerate(ref_ids):
        # Sort this cell's correlations for all three methods
        sorted_full_corr = np.sort(arr_full_corr[idx, :])
        sorted_full_corr = np.flip(sorted_full_corr)

        sorted_space_corr = np.sort(arr_space_corr[idx, :])
        sorted_space_corr = np.flip(sorted_space_corr)

        sorted_power_corr = np.sort(arr_power_corr[idx, :])
        sorted_power_corr = np.flip(sorted_power_corr)

        # Pull the max and next max correlations from the sorted correlation vectors
        max_corrs = np.array(
            [sorted_full_corr[0], sorted_space_corr[0], sorted_power_corr[0]]
        )
        next_max_corrs = np.array(
            [sorted_full_corr[1], sorted_space_corr[1], sorted_power_corr[1]]
        )
        corr_filter = next_max_corrs < max_corrs * 0.9

        # Pull the indices corresponding of the maximum values (the three values in max_corrs above) in each vector
        max_inds = np.array(
            [
                np.argmax(arr_full_corr[idx, :]),
                np.argmax(arr_space_corr[idx, :]),
                np.argmax(arr_power_corr[idx, :]),
            ]
        )

        # Eliminate correlations where the next best correlation is within 90% (currently hard-coded...)
        if any(corr_filter):
            max_corrs = max_corrs[corr_filter]
            max_inds = max_inds[corr_filter]
        else:
            # If all correlations have been eliminated using this technique, the call cannot be matched
            bad_match_count += 1
            continue

        # Pull the index of the highest remaing correlation
        best_match = np.argmax(max_corrs)

        # Pull that correlation value
        max_corr = max_corrs[best_match]

        # Pull the index of that correlation value
        max_ind = max_inds[best_match]

        # Using the index of the best correlation value, pull the vector corresponding to
        # all of the correlations for the current reference cell's "best match" test cell.
        # Then do the same process as above, but for the vector of correlations belonging to the
        # best matched test cell. This ensures that if reference_cell 1's best match is test_cell 2,
        # test_cell 2's best match is ALSO reference_cell 1... otherwise it's a bad match.
        sorted_rev_full_corr = np.sort(arr_full_corr[:, max_ind])
        sorted_rev_full_corr = np.flip(sorted_rev_full_corr)

        sorted_rev_space_corr = np.sort(arr_space_corr[:, max_ind])
        sorted_rev_space_corr = np.flip(sorted_rev_space_corr)

        sorted_rev_power_corr = np.sort(arr_power_corr[:, max_ind])
        sorted_rev_power_corr = np.flip(sorted_rev_power_corr)

        max_rev_corrs = np.array(
            [
                sorted_rev_full_corr[0],
                sorted_rev_space_corr[0],
                sorted_rev_power_corr[0],
            ]
        )
        next_max_rev_corrs = np.array(
            [
                sorted_rev_full_corr[1],
                sorted_rev_space_corr[1],
                sorted_rev_power_corr[1],
            ]
        )
        rev_corr_filter = next_max_rev_corrs < max_rev_corrs * 0.9

        max_rev_inds = np.array(
            [
                np.argmax(arr_full_corr[:, max_ind]),
                np.argmax(arr_space_corr[:, max_ind]),
                np.argmax(arr_power_corr[:, max_ind]),
            ]
        )

        if any(rev_corr_filter):
            max_rev_corrs = max_rev_corrs[rev_corr_filter]
            max_rev_inds = max_rev_inds[rev_corr_filter]
        else:
            bad_match_count += 1
            continue

        best_rev_match = np.argmax(max_rev_corrs)
        max_rev_ind = max_rev_inds[best_rev_match]
        max_rev_corr = max_rev_corrs[best_rev_match]

        # Kick out the cell if the best reverse correlation is higher
        if max_rev_corr > max_corr:
            bad_match_count += 1
            continue

        # If maximum correlation is above the cutoff set in the function, proceed
        if max_corr > corr_cutoff:
            # if use timecourses is true, pull timecourses for the ref and test cell, and
            # calculate the correlation.
            if use_timecourse:
                from retinanalysis.classes.analysis_chunk import AnalysisChunk

                if isinstance(ref_object, AnalysisChunk) and isinstance(
                    test_object, AnalysisChunk
                ):
                    ref_r = ref_object.d_timecourses[ref_cell]["red"]
                    ref_g = ref_object.d_timecourses[ref_cell]["green"]
                    ref_b = ref_object.d_timecourses[ref_cell]["blue"]

                    test_r = test_object.d_timecourses[test_ids[max_ind]]["red"]
                    test_g = test_object.d_timecourses[test_ids[max_ind]]["green"]
                    test_b = test_object.d_timecourses[test_ids[max_ind]]["blue"]

                    ref_rgb = np.concatenate([ref_r, ref_g, ref_b])
                    test_rgb = np.concatenate([test_r, ref_g, test_b])
                    np.nan_to_num(
                        ref_rgb, copy=False, nan=0.001, neginf=0.001, posinf=0.001
                    )
                    np.nan_to_num(
                        test_rgb, copy=False, nan=0.001, neginf=0.001, posinf=0.001
                    )

                    rgb_corr = np.corrcoef(ref_rgb, test_rgb)[0, 1]
                else:
                    raise ValueError(
                        "To use timecourses, ref and test object must both be AnalysisChunks"
                    )

            # If use_isi is true, pull isi's for the ref and test cells, and calculate the
            # correlation
            if use_isi:
                from retinanalysis.classes.analysis_chunk import AnalysisChunk

                if isinstance(ref_object, AnalysisChunk) and isinstance(
                    test_object, AnalysisChunk
                ):
                    ref_isi = ref_object.d_ISIs[ref_cell]
                    match_isi = test_object.d_ISIs[test_ids[max_ind]]

                    # ref_isi = ref_vcd.get_acf_numpairs_for_cell(ref_cell)
                    # match_isi = test_vcd.get_acf_numpairs_for_cell(test_ids[max_ind])
                    # np.nan_to_num(ref_isi, copy=False, nan=0.001, neginf=0.001, posinf=0.001)
                    # np.nan_to_num(match_isi, copy = False, nan=0.001, neginf=0.001, posinf=0.001)

                    isi_corr = np.corrcoef(ref_isi, match_isi)[0, 1]
                else:
                    raise ValueError(
                        "To use ISIs, ref and test objects must both be AnalysisChunks"
                    )

            # If the isi_correlation or the rgb_correlation is below 0.3, throw out the cell
            if isi_corr < 0.3 or rgb_corr < 0.3:
                bad_match_count += 1

            # Kick out the cell if the best reverse correlation cell isn't the reference cell
            # This isn't redundant with the max_rev_corr > max_corr check above... it's possible
            # that the max_rev_corr is actually lower, because the reverse correlation was kicked
            # out by the 90% rule only when that rule was applied backwards (i.e. The second best
            # correlation for the test cell was within 90% of the best correlation (with our reference
            # cell), and so that correlation was kicked out when we ran the process in reverse).
            elif ref_ids[max_rev_ind] != ref_cell:
                bad_match_count += 1
            else:
                match_dict[ref_cell] = test_ids[max_ind]
                match_count += 1
                corr_dict[ref_cell] = max_corr

        else:
            bad_match_count += 1

    if verbose:
        percent_good = match_count / len(ref_ids)
        percent_bad = bad_match_count / len(ref_ids)
        print(
            f"{np.round(percent_good * 100, 2)}% matched, {np.round(percent_bad * 100, 2)}% unmatched.\n"
        )

    match_dict = dict(sorted(match_dict.items()))
    corr_dict = dict(sorted(corr_dict.items()))

    # Check for duplicate matches
    counts = Counter(match_dict.values())
    duplicate_dict = {
        k: (v, corr_dict[k]) for k, v in match_dict.items() if counts[v] > 1
    }

    if not duplicate_dict:
        pass
    else:
        print(
            f"WARNING: Duplicate matches detected. Keys {[key for key, value in duplicate_dict.items()]} have duplicate values"
        )

    return match_dict, corr_dict


def get_protocol_from_datafile(exp_name: str, datafile_name: str) -> str:
    exp_summary = get_exp_summary(exp_name)

    assert exp_summary is not None, (
        f"Experiment summary failed to generate for {exp_name}, {datafile_name}"
    )
    protocol_name = exp_summary.query("datafile_name == @datafile_name").reset_index(
        drop=True
    )

    return protocol_name.loc[0, "protocol_name"]


def get_classification_file_path(
    classification_file_name: str,
    exp_name: str,
    chunk_name: str,
    ss_version: str = "kilosort2.5",
) -> str:

    classification_file_path = os.path.join(
        ANALYSIS_DIR, exp_name, chunk_name, ss_version, classification_file_name
    )

    return classification_file_path


def get_ells(
    analysis_chunk: AnalysisChunk,
    d_cells_by_type: Dict[str, List[int]],
    std_scaling: float = 1.6,
    units: str = "pixels",
) -> Tuple[Dict[str, dict], int]:

    if "microns" in units.lower():
        scale_factor = analysis_chunk.microns_per_stixel
    elif "pixels" in units.lower():
        scale_factor = analysis_chunk.pixels_per_stixel
    elif "stixels" in units.lower():
        scale_factor = 1
    else:
        raise NameError("Units string must be 'microns', 'pixels' or 'stixels'.")

    rf_params = analysis_chunk.rf_params

    d_ells_by_type = dict()
    for idx, ct in enumerate(d_cells_by_type.keys()):
        d_ells_by_id = dict()
        for id in d_cells_by_type[ct]:
            d_ells_by_id[id] = Ellipse(
                xy=(
                    rf_params[id]["center_x"] * scale_factor,
                    rf_params[id]["center_y"] * scale_factor,
                ),
                width=rf_params[id]["std_x"] * std_scaling * scale_factor,
                height=rf_params[id]["std_y"] * std_scaling * scale_factor,
                angle=rf_params[id]["rot"],
                facecolor=f"C{idx}",
                edgecolor=f"C{idx}",
                alpha=0.7,
            )

        d_ells_by_type[ct] = d_ells_by_id

    return d_ells_by_type, scale_factor


AUTO_CONTOUR_LEVELS = np.round(np.arange(0.10, 0.91, 0.05), 2)
AUTO_CONTOUR_FALLBACK = 0.5


def _peak_normalized_map(sta: np.ndarray):
    """Peak spatial frame of a (T, H, W, C) STA, divided by its signed peak value, so the RF
    center is +1 at the peak for ON and OFF cells alike and the opposite-sign surround is
    negative. Returns (map, (peak_row, peak_col)), or (None, None) if the STA is flat."""
    peak_idx = np.unravel_index(np.argmax(np.abs(sta)), sta.shape)
    t_idx, peak_y, peak_x, c_idx = peak_idx
    spat_map = sta[t_idx, :, :, c_idx].astype(float)
    peak_val = spat_map[peak_y, peak_x]
    if peak_val == 0:
        return None, None
    return spat_map / peak_val, (peak_y, peak_x)


def _smoothed_peak_map(sta: np.ndarray, sigma: float = 0.7):
    """Like _peak_normalized_map, but less noisy, for contouring: averages the peak frame
    with the frames just before and after it, blurs lightly (Gaussian, `sigma` stixels),
    then divides by the signed peak of that smoothed map. Returns (map, (peak_row,
    peak_col)) on the stixel grid, or (None, None) if the STA is flat.

    ADDED 2026-09-30 (Claude, per yas -- contours "look so bad"): tracing the single raw
    peak frame at stixel resolution turns every noisy edge stixel into a dent or spike,
    because these RFs are only ~6-8 stixels across."""
    from scipy.ndimage import gaussian_filter
    t_idx, _, _, c_idx = np.unravel_index(np.argmax(np.abs(sta)), sta.shape)
    frame = sta[max(t_idx - 1, 0): t_idx + 2, :, :, c_idx].astype(float).mean(axis=0)
    if sigma and sigma > 0:
        frame = gaussian_filter(frame, sigma)
    peak_y, peak_x = np.unravel_index(np.argmax(np.abs(frame)), frame.shape)
    peak_val = frame[peak_y, peak_x]
    if peak_val == 0:
        return None, None
    return frame / peak_val, (peak_y, peak_x)


def uniformity_index_curve(
    d_maps: Dict[int, tuple], levels=AUTO_CONTOUR_LEVELS, upsample: int = 4
) -> Optional[np.ndarray]:
    """
    Uniformity index (Gauthier et al. 2009, PLoS Biol, doi:10.1371/journal.pbio.1000063;
    MATLAB calc_uniformity_index.m) of one cell type's mosaic at each contour level:
    the fraction of the mosaic's interior covered by exactly one cell's RF. Too low a
    level -> RFs pile on top of each other (overlap); too high -> holes between them
    (gaps). A real mosaic tiles, so the level that maximizes UI is the one where the
    contours tile best.

    The interior (ROI) is the Delaunay triangulation of the cells' peak pixels, same as
    the MATLAB version, so the empty space outside the mosaic's edge isn't counted as gaps.
    Each cell's RF at a level = the connected region of its peak-normalized map >= level
    that contains its peak pixel. Computed on the stixel grid upsampled `upsample`x
    (bilinear) rather than by polygon clipping.

    Parameters:
        d_maps: {cell_id: (peak_normalized_map, (peak_row, peak_col))}, one entry per cell
        of ONE type (see _peak_normalized_map).
        levels: contour levels to evaluate.
        upsample: upsampling factor for the coverage grid. Default 4.

    Returns:
        array of shape (len(levels), 3): columns = (UI, fraction of ROI with no RF,
        fraction of ROI covered by 2+ RFs). None if there are fewer than 4 cells or the
        peaks are collinear (no triangulation).
    """
    from scipy.ndimage import zoom, label
    from scipy.spatial import Delaunay

    if len(d_maps) < 4:
        return None
    up_maps, peaks = [], []
    for m, (py, px) in d_maps.values():
        up_maps.append(zoom(m, upsample, order=1))
        peaks.append((py * upsample + upsample // 2, px * upsample + upsample // 2))
    shape = up_maps[0].shape
    peaks = np.array(peaks)
    try:
        tri = Delaunay(peaks)
    except Exception:
        return None
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    roi = (tri.find_simplex(np.column_stack([yy.ravel(), xx.ravel()])) >= 0).reshape(shape)
    if not roi.any():
        return None

    out = []
    for lv in levels:
        cov = np.zeros(shape, dtype=int)
        for m, (py, px) in zip(up_maps, peaks):
            lab, _ = label(m >= lv)
            k = lab[min(py, shape[0] - 1), min(px, shape[1] - 1)]
            if k > 0:
                cov += lab == k
        r = cov[roi]
        out.append(((r == 1).mean(), (r == 0).mean(), (r >= 2).mean()))
    return np.array(out)


def get_rf_contours(
    analysis_chunk: AnalysisChunk,
    d_cells_by_type: Dict[str, List[int]],
    contour_level: Union[float, str] = "auto",
    units: str = "pixels",
    typing_file: Optional[str] = None,
    verbose: bool = True,
    smooth: bool = True,
    smooth_sigma: float = 0.7,
    upsample: int = 4,
) -> Tuple[Dict[str, dict], int]:
    """
    Non-parametric alternative to get_ells(): traces each cell's actual RF boundary
    directly from its raw STA pixels via marching-squares contouring, the same approach
    as the lab's MATLAB rf_contours.m / get_rf_contours.m, rather than drawing a fitted
    Gaussian ellipse.

    For each cell: take the STA frame containing that cell's own peak |deviation|, divide
    it by the signed peak value (center -> +1 for ON and OFF cells alike; the opposite-sign
    surround goes negative and is excluded, as in MATLAB rf_contours.m), and contour at the
    level. Of the contour bands, keeps the smallest one enclosing the cell's own peak pixel.

    Choosing the level: contour_level="auto" (default) picks, separately for each cell type,
    the level in AUTO_CONTOUR_LEVELS (0.10-0.90) that maximizes that type's uniformity index
    (see uniformity_index_curve; Gauthier et al. 2009, MATLAB calc_best_ui_thresh.m) -- i.e.
    the level at which the type's contours tile space best, with the least overlap and the
    fewest gaps. There's no single right fixed level: on 20251016A the best level ranged
    0.40-0.65 across types, and at a fixed 0.25 the ON brisk sustained contours overlapped
    over 99% of the mosaic. Types with fewer than 4 cells can't be scored and fall back to
    AUTO_CONTOUR_FALLBACK (0.5). Pass a float to force one level for every type.

    Parameters:
        analysis_chunk (AnalysisChunk): the chunk to pull raw STAs from.

        d_cells_by_type (Dict[str, List[int]]): cell ids to contour, grouped by type
        (same shape as get_ells()'s d_cells_by_type).

        contour_level (float or "auto"): see above. Default "auto".

        units (str): 'pixels', 'microns', or 'stixels'. Default 'pixels'.

        typing_file (str): typing file to pass through to get_stas(); if None, get_stas()
        uses its own default (chunk's 0th typing file).

        verbose (bool): print the level (and UI, when auto) used for each type. Default True.

        smooth (bool): ADDED 2026-09-30. Default True: contour a smoothed map (peak frame
        averaged with its neighbouring frames, Gaussian blur of `smooth_sigma` stixels; see
        _smoothed_peak_map), traced on a cubic `upsample`x-interpolated grid, so outlines
        are smooth curves instead of stixel staircases. False = the old behaviour (raw
        peak frame, stixel grid). The auto level is scored on whichever map is contoured.

        smooth_sigma (float): blur width in stixels when smooth=True. Default 0.7.

        upsample (int): interpolation factor for tracing when smooth=True. Default 4.

    Returns:
        (d_contours_by_type, scale_factor): d_contours_by_type is
        {cell_type: {cell_id: matplotlib.patches.Polygon}}, same dict shape as get_ells()'s
        ellipses, so plot_rfs() can drop either dict into the same axes.add_patch() loop.
        Drawn with a light fill (f'C{idx}' at 30% opacity) and a solid outline in the same
        color, so each RF is highlighted but overlap between cells is still visible. scale_factor is the stixels-to-units conversion actually used (matches
        get_ells()'s). The level/UI used per type is also stored on
        analysis_chunk.last_contour_levels as {cell_type: (level, ui_or_None)}.
    """
    if "microns" in units.lower():
        scale_factor = analysis_chunk.microns_per_stixel
    elif "pixels" in units.lower():
        scale_factor = analysis_chunk.pixels_per_stixel
    elif "stixels" in units.lower():
        scale_factor = 1
    else:
        raise NameError("Units string must be 'microns', 'pixels' or 'stixels'.")

    auto = isinstance(contour_level, str)
    if auto and contour_level.lower() != "auto":
        raise ValueError("contour_level must be a float or 'auto'.")

    all_ids = [cid for ids in d_cells_by_type.values() for cid in ids]
    d_stas = analysis_chunk.get_stas(
        noise_ids=all_ids,
        cell_types=list(d_cells_by_type.keys()),
        typing_file=typing_file,
        padded=True,
        units="stixels",
    )
    # get_stas() groups its output by cell_type -- flatten to a single cell_id lookup,
    # since d_cells_by_type may group the same ids differently than get_stas() would on
    # its own (e.g. when the caller passed noise_ids explicitly).
    sta_by_id: Dict[int, np.ndarray] = {}
    for ct_stas in d_stas.values():
        sta_by_id.update(ct_stas)

    d_contours_by_type = dict()
    levels_used = dict()
    for idx, ct in enumerate(d_cells_by_type.keys()):
        d_maps = {}
        for cell_id in d_cells_by_type[ct]:
            sta = sta_by_id.get(cell_id)
            if sta is None:
                continue
            m, pk = _smoothed_peak_map(sta, smooth_sigma) if smooth else _peak_normalized_map(sta)
            if m is not None:
                d_maps[cell_id] = (m, pk)

        ui = None
        if auto:
            curve = uniformity_index_curve(d_maps)
            if curve is None:
                level = AUTO_CONTOUR_FALLBACK
            else:
                best = int(np.argmax(curve[:, 0]))
                level = float(AUTO_CONTOUR_LEVELS[best])
                ui = float(curve[best, 0])
        else:
            level = float(contour_level)
        levels_used[ct] = (level, ui)
        if verbose:
            if ui is not None:
                print(f"{ct}: contour level {level:.2f} (uniformity index {ui:.2f})")
            elif auto:
                print(f"{ct}: contour level {level:.2f} (fewer than 4 cells, UI not computable -- fallback)")
            else:
                print(f"{ct}: contour level {level:.2f}")

        d_contours_by_id = dict()
        for cell_id, (norm_map, (peak_y, peak_x)) in d_maps.items():
            if smooth and upsample > 1:
                # Trace on a cubic-interpolated grid, then map points back to stixel
                # coordinates. scipy's zoom (grid_mode=False) puts output index o at input
                # coordinate o * (n - 1) / (n_up - 1) along each axis.
                from scipy.ndimage import zoom as _zoom
                fine = _zoom(norm_map, upsample, order=3)
                ry = (norm_map.shape[0] - 1) / (fine.shape[0] - 1)
                rx = (norm_map.shape[1] - 1) / (fine.shape[1] - 1)
                contours = [np.column_stack([c[:, 0] * ry, c[:, 1] * rx])
                            for c in find_contours(fine, level=level)]
            else:
                contours = find_contours(norm_map, level=level)
            if not contours:
                continue

            # Each contour is an array of (row, col) points. Keep only bands that
            # actually enclose the cell's own peak pixel, then take the smallest-area
            # one among those (the tightest boundary directly around the RF center).
            best_xy = None
            best_area = None
            for c in contours:
                path = MplPath(np.column_stack([c[:, 1], c[:, 0]]))  # (x, y) = (col, row)
                if not path.contains_point((peak_x, peak_y)):
                    continue
                x, y = c[:, 1], c[:, 0]
                area = 0.5 * abs(
                    np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))
                )
                if best_area is None or area < best_area:
                    best_area = area
                    best_xy = np.column_stack([x, y])

            if best_xy is None:
                continue

            d_contours_by_id[cell_id] = Polygon(
                best_xy * scale_factor,
                closed=True,
                facecolor=to_rgba(f"C{idx}", 0.3),  # light fill = highlight
                edgecolor=to_rgba(f"C{idx}", 1.0),  # solid outline so overlaps stay visible
                linewidth=1.2,
            )

        d_contours_by_type[ct] = d_contours_by_id

    analysis_chunk.last_contour_levels = levels_used
    return d_contours_by_type, scale_factor


def plot_rf_sizes(df_rf_sizes: DataFrame, title: str = "RF size by cell type"):
    """
    Plot the output of AnalysisChunk.get_rf_sizes_from_sta().

    Left: RF diameter per cell type, half-max (blue) next to the Gaussian fit (grey), one
    dot per cell over a box, to compare types and see the spread within each type (outlying
    dots are worth a look in the portraits). Right: half-max vs Gaussian diameter per cell,
    colored by type; the dashed line is what a perfectly Gaussian RF would give
    (half-max = 1.18 x the 1-SD-radius Gaussian diameter), so cells far off it have RFs
    that the Gaussian fit describes poorly (or a failed fit).

    Returns the figure.
    """
    import matplotlib.pyplot as plt

    d = df_rf_sizes.dropna(subset=["rf_diameter_halfmax_um"])
    types = sorted(d["cell_type"].unique())
    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(max(6, 1.6 * len(types)) + 4.5, 4.5),
        gridspec_kw={"width_ratios": [max(1.5, 0.45 * len(types)), 1]},
    )
    rng = np.random.default_rng(0)
    for i, ct in enumerate(types):
        g = d[d["cell_type"] == ct]
        for off, col, color in [(-0.18, "rf_diameter_halfmax_um", "#1f5fd6"), (0.18, "rf_diameter_gauss_um", "0.45")]:
            vals = g[col].dropna().values
            if len(vals) == 0:
                continue
            ax.boxplot(vals, positions=[i + off], widths=0.3, showfliers=False,
                       medianprops=dict(color=color, lw=2), boxprops=dict(color=color),
                       whiskerprops=dict(color=color), capprops=dict(color=color))
            ax.scatter(i + off + rng.uniform(-0.08, 0.08, len(vals)), vals, s=10, color=color, alpha=0.6, zorder=3)
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels([f"{ct}\n(n={int((d['cell_type'] == ct).sum())})" for ct in types], rotation=30, ha="right")
    ax.set_ylabel("RF diameter (\u00b5m)")
    ax.scatter([], [], color="#1f5fd6", label="half-max (raw STA)")
    ax.scatter([], [], color="0.45", label="Gaussian fit (1-SD radius)")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title(title)

    for i, ct in enumerate(types):
        g = d[d["cell_type"] == ct]
        ax2.scatter(g["rf_diameter_gauss_um"], g["rf_diameter_halfmax_um"], s=12, color=f"C{i}", label=ct, alpha=0.8)
    lim = np.nanmax(d[["rf_diameter_halfmax_um", "rf_diameter_gauss_um"]].values) * 1.05
    ax2.plot([0, lim], [0, 1.1774 * lim], ls="--", color="0.5", lw=1, label="perfect Gaussian")
    ax2.set_xlim(0, lim); ax2.set_ylim(0, lim * 1.2)
    ax2.set_xlabel("Gaussian-fit diameter (\u00b5m)"); ax2.set_ylabel("half-max diameter (\u00b5m)")
    ax2.set_title("Per cell: half-max vs fit")
    ax2.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    return fig


def get_timecourses(
    analysis_chunk: AnalysisChunk, d_cells_by_type: dict
) -> Dict[str, dict]:

    d_timecourses_by_type = dict()

    for ct in d_cells_by_type.keys():
        r_timecourses = [
            analysis_chunk.d_timecourses[cell]["red"] for cell in d_cells_by_type[ct]
        ]
        g_timecourses = [
            analysis_chunk.d_timecourses[cell]["green"] for cell in d_cells_by_type[ct]
        ]
        b_timecourses = [
            analysis_chunk.d_timecourses[cell]["blue"] for cell in d_cells_by_type[ct]
        ]

        r_timecourses = np.array(r_timecourses)
        g_timecourses = np.array(g_timecourses)
        b_timecourses = np.array(b_timecourses)

        if r_timecourses.shape[0] > 1:
            r_mean = np.mean(r_timecourses, axis=0)
            r_std = np.std(r_timecourses, axis=0)
        else:
            r_mean = r_timecourses.squeeze()
            r_std = 0

        if g_timecourses.shape[0] > 1:
            g_mean = np.mean(g_timecourses, axis=0)
            g_std = np.std(g_timecourses, axis=0)
        else:
            g_mean = g_timecourses.squeeze()
            g_std = 0

        if b_timecourses.shape[0] > 1:
            b_mean = np.mean(b_timecourses, axis=0)
            b_std = np.std(b_timecourses, axis=0)
        else:
            b_mean = b_timecourses.squeeze()
            b_std = 0

        d_timecourses_by_type[ct] = {
            "r_timecourses": r_timecourses,
            "r_mean": r_mean,
            "r_std": r_std,
            "g_timecourses": g_timecourses,
            "g_mean": g_mean,
            "g_std": g_std,
            "b_timecourses": b_timecourses,
            "b_mean": b_mean,
            "b_std": b_std,
        }

    return d_timecourses_by_type


def get_spike_xarr(
    response_block: MEAResponseBlock | MEAResponseGroup,
    protocol_ids: Optional[List[int] | int] = None,
    cell_types: Optional[List[str] | str] = None,
    minimum_n: int = 1,
) -> xr.DataArray:

    if isinstance(cell_types, str):
        cell_types = [cell_types]

    if isinstance(protocol_ids, int):
        protocol_ids = [protocol_ids]

    # Check that cell_type data included in spike times dataframe, if not, add it
    if "cell_type" not in response_block.df_spike_times.columns:
        response_block.add_cell_types()
        spike_time_df = response_block.df_spike_times
    else:
        spike_time_df = response_block.df_spike_times

    if protocol_ids is None and cell_types is None:
        filtered_df = spike_time_df
        cell_types = sorted(filtered_df["cell_type"].unique())

    elif protocol_ids is None:
        filtered_df = spike_time_df.query("cell_type in @cell_types").reset_index(
            drop=True
        )
        cell_types = sorted(filtered_df["cell_type"].unique())

    elif cell_types is None:
        filtered_df = spike_time_df.query("cell_id in @protocol_ids").reset_index(
            drop=True
        )
        cell_types = sorted(filtered_df["cell_type"].unique())

    else:
        filtered_df = spike_time_df.query(
            "cell_id in @protocol_ids and cell_type in @cell_types"
        ).reset_index(drop=True)
        cell_types = sorted(filtered_df["cell_type"].unique())

    for ct in cell_types:
        if len(filtered_df.query("cell_type == @ct").values) < minimum_n:
            print(
                f"Removing {ct} from spike time array, too few cells (n = {len(filtered_df.query('cell_type==@ct').values)})..."
            )
            indices = filtered_df.query("cell_type == @ct").index
            filtered_df = filtered_df.drop(index=indices).reset_index(drop=True)  # type: ignore

    spike_time_arr = [
        filtered_df.loc[cell_idx, "spike_times"] for cell_idx in filtered_df.index
    ]

    spike_time_arr = np.array(spike_time_arr, dtype=object)
    dims = ["cell_id", "epoch"]

    coords = {
        "epoch": np.arange(response_block.n_epochs),
        "cell_id": filtered_df["cell_id"].values,
        "cell_type": (
            "cell_id",
            np.asarray(filtered_df["cell_type"].values, dtype="U"),
        ),
        "noise_id": ("cell_id", filtered_df["noise_id"].values),
    }

    spike_time_xarr = xr.DataArray(spike_time_arr, dims=dims, coords=coords)

    return spike_time_xarr


def get_spike_dict(
    response_block: MEAResponseBlock | MEAResponseGroup,
    protocol_ids: Optional[List[int] | int] = None,
    cell_types: Optional[List[str] | str] = None,
    minimum_n: int = 1,
) -> dict:

    # Check that cell_type data included in spike times dataframe, if not, add it
    if "cell_type" not in response_block.df_spike_times.columns:
        response_block.add_cell_types()
        spike_time_df = response_block.df_spike_times
    else:
        spike_time_df = response_block.df_spike_times

    if protocol_ids is None and cell_types is None:
        filtered_df = spike_time_df
        cell_types = sorted(filtered_df["cell_type"].unique())

    elif protocol_ids is None:
        filtered_df = spike_time_df.query("cell_type in @cell_types")
        cell_types = sorted(filtered_df["cell_type"].unique())

    elif cell_types is None:
        filtered_df = spike_time_df.query("cell_id in @protocol_ids")
        cell_types = sorted(filtered_df["cell_type"].unique())

    else:
        filtered_df = spike_time_df.query(
            "cell_id in @protocol_ids and cell_type in @cell_types"
        )
        cell_types = sorted(filtered_df["cell_type"].unique())

    for ct in cell_types:
        if len(filtered_df.query("cell_type == @ct").values) < minimum_n:
            print(
                f"Removing {ct} from spike time array, too few cells (n = {len(filtered_df.query('cell_type==@ct').values)})..."
            )
            indices = filtered_df.query("cell_type == @ct").index
            filtered_df = filtered_df.drop(index=indices).reset_index(drop=True)  # type: ignore

    d_spike_times = dict()
    for ct in cell_types:
        d_times_and_ids = dict()
        df_type = filtered_df.query("cell_type == @ct").reset_index(drop=True)
        type_ids = df_type["cell_id"].values
        arr_spike_times = [
            df_type.loc[idx, "spike_times"] for idx, id in enumerate(type_ids)
        ]
        arr_spike_times = np.array(arr_spike_times, dtype=object)
        d_times_and_ids["spike_times"] = arr_spike_times
        d_times_and_ids["cell_ids"] = type_ids

        d_spike_times[ct] = d_times_and_ids

    return d_spike_times


def classification_transfer(
    analysis_chunk: AnalysisChunk,
    target_object: AnalysisChunk | MEAResponseBlock | MEAResponseGroup,
    ss_version: Optional[str] = None,
    input_typing_file: Optional[str] = None,
    output_typing_file: str = "RA_autoClassification.txt",
    verbose: bool = True,
    **kwargs,
):
    """Transfer classification between an analysis chunk and another analysis chunk or a response block
    Inputs:
        analysis_chunk: AnalysisChunk
        target_object: AnalysisChunk or ResponseBlock or ResponseGroup
        ss_version: str such as 'kilosort2.5', if None, uses same ss_version as analysis_chunk
        input_typing_file: str, filename of classification file to use, if None will use
                            the first typing file in analysis_chunk.typing_files
        output_typing_file: str, filename of classification file to export, default is
                            RA_autoClassification.txt

    Kwargs to pass to cluster_match:
        use_isi: bool, default = false
        use_timecourse: bool, default = false
        corr_cutoff: float, default = 0.8
        method: str, default = 'full'
        n_removed_channels: int, default = 1
    """

    if len(analysis_chunk.typing_files) == 0:
        raise FileNotFoundError("No typing files available for this analysis chunk")

    # To avoid circular imports, we're only importing classes inside the utils when needed for checking. Annoying but
    # this is just an issue with python
    from retinanalysis.classes.analysis_chunk import AnalysisChunk

    if isinstance(target_object, AnalysisChunk) and target_object == analysis_chunk:
        raise Exception(
            f"Target chunk ({target_object.chunk_name}) cannot be the same as analysis chunk {analysis_chunk.chunk_name}"
        )

    # If no input typing file is specified, use typing_file_0
    if input_typing_file is None:
        input_typing_file = analysis_chunk.typing_files[0]

    # Flag if input typing file is not actually part of the current analysis chunk
    if input_typing_file not in analysis_chunk.typing_files:
        raise FileNotFoundError("Input typing file not found in current chunk")

    # If no spike sorting version is given, use same ss_version as analysis chunk
    if ss_version is None:
        ss_version = analysis_chunk.ss_version

    if isinstance(target_object, AnalysisChunk):
        if verbose:
            print(
                f"Cluster matching {analysis_chunk.chunk_name} with {target_object.chunk_name}\n"
            )
        destination_file_path = os.path.join(
            ANALYSIS_DIR,
            analysis_chunk.exp_name,
            target_object.chunk_name,
            ss_version,
            output_typing_file,
        )

    else:
        if verbose:
            print(
                f"Cluster matching {analysis_chunk.chunk_name} with {target_object.protocol_name}\n"
            )
        destination_file_path = os.path.join(os.getcwd(), output_typing_file)
        if "use_timecourse" in kwargs:
            if kwargs["use_timecourse"]:
                raise FileNotFoundError(
                    "Response blocks don't have a .params file, can't use timecourse for cluster matching"
                )

    # Cluster Match
    target_ids = target_object.cell_ids

    match_dict, _ = cluster_match(analysis_chunk, target_object, **kwargs)

    # Create classification file and drop it in the destination path
    input_file_path = os.path.join(
        ANALYSIS_DIR,
        analysis_chunk.exp_name,
        analysis_chunk.chunk_name,
        analysis_chunk.ss_version,
        input_typing_file,
    )

    matched_count = 0
    unmatched_count = 0
    input_classification_dict = create_dictionary_from_file(
        input_file_path, delimiter=" "
    )

    with open(destination_file_path, mode="w") as output_file:
        for key in match_dict.keys():
            matched_count += 1
            print(match_dict[key], input_classification_dict[key], file=output_file)

    partial_output = create_dictionary_from_file(destination_file_path, delimiter=" ")

    with open(destination_file_path, mode="a") as output_file:
        for id in target_ids:
            if id in partial_output:
                pass
            else:
                print(id, "All/Unknown", file=output_file)
                unmatched_count += 1

    print(
        f"\nTarget clusters matched: {matched_count}\nTarget clusters unmatched: {unmatched_count}\n"
    )
    print(
        f"Classification file {output_typing_file} created at: {destination_file_path}"
    )

    return match_dict


def ei_corr(
    ref_object: AnalysisChunk | MEAResponseBlock | MEAResponseGroup,
    target_object: AnalysisChunk | MEAResponseBlock | MEAResponseGroup,
    method: str = "full",
    n_removed_channels: int = 1,
) -> np.ndarray:

    # Pull reference eis
    ref_ids = ref_object.cell_ids

    # New code ensures cells with no or broken EIs don't break cluster matching
    ref_eis = [ref_object.d_EIs[id] for id in ref_ids]

    if n_removed_channels > 0:
        max_ref_vals = [np.array(np.max(np.abs(ei), axis=1)) for ei in ref_eis]
        ref_to_remove = [np.argsort(val)[-n_removed_channels:] for val in max_ref_vals]

        # New ei channel removal implementation, replace removed channel with mean value
        fixed_ref_eis = []
        for ei, channels in zip(ref_eis, ref_to_remove):
            ei_fixed = ei.copy()
            keep = np.ones(ei.shape[0], dtype=bool)
            keep[channels] = False
            fill_value = ei_fixed[keep, :].mean()
            ei_fixed[channels, :] = fill_value
            fixed_ref_eis.append(ei_fixed)

    else:
        fixed_ref_eis = [ei.copy() for ei in ref_eis]

    # Set any EI value where the ei is less than 1.5* its standard deviation to 0
    for idx, ei in enumerate(fixed_ref_eis):
        fixed_ref_eis[idx][abs(ei) < (ei.std() * 1.5)] = 0

    # For 'full' method: flatten each 512 x 201 ei array into a vector
    # and stack flattened eis into a numpy array
    if "full" in method:
        ref_eis_flat = [ei.flatten() for ei in fixed_ref_eis]
        fixed_ref_eis = np.array(ref_eis_flat)
    # For 'time' method, take max of absolute value over time and
    # stack the resulting 512 x 1 vectors into a numpy array
    elif "space" in method:
        ref_eis_mean = [np.max(np.abs(ei), axis=1) for ei in fixed_ref_eis]
        fixed_ref_eis = np.array(ref_eis_mean)
    # For 'power' method, square each 512 x 201 ei array, take the mean over time,
    # and stack the resulting 512 x 1 vectors into a numpy array
    elif "power" in method:
        ref_eis_mean = [np.mean(ei**2, axis=1) for ei in fixed_ref_eis]
        fixed_ref_eis = np.array(ref_eis_mean)
    else:
        raise NameError("Method poperty must be 'full', 'space', or 'power'.")

    # Pull test eis
    test_ids = target_object.cell_ids

    # New code makes sure that cells with broken or no EIs don't break cluster matching
    test_eis = [target_object.d_EIs[id] for id in test_ids]

    if n_removed_channels > 0:
        max_test_vals = [np.array(np.max(np.abs(ei), axis=1)) for ei in test_eis]
        test_to_remove = [
            np.argsort(val)[-n_removed_channels:] for val in max_test_vals
        ]

        # New ei channel removal implementation, replace removed channel with mean value
        fixed_test_eis = []
        for ei, channels in zip(test_eis, test_to_remove):
            ei_fixed = ei.copy()
            keep = np.ones(ei.shape[0], dtype=bool)
            keep[channels] = False
            fill_value = ei_fixed[keep, :].mean()
            ei_fixed[channels, :] = fill_value
            fixed_test_eis.append(ei_fixed)

    else:
        fixed_test_eis = [ei.copy() for ei in test_eis]

    # Set the EI value where the EI is less than 1.5* its standard deviation to 0
    for idx, ei in enumerate(fixed_test_eis):
        fixed_test_eis[idx][abs(ei) < (ei.std() * 1.5)] = 0

    # For 'full' method: flatten each 512 x 201 ei array into a vector
    # and stack flattened eis into a numpy array
    if "full" in method:
        test_eis_flat = [ei.flatten() for ei in fixed_test_eis]
        fixed_test_eis = np.array(test_eis_flat)
    # For 'time' method, take max of absolute value over time and
    # stack the resulting 512 x 1 vectors into a numpy array
    elif "space" in method:
        test_eis_mean = [np.max(np.abs(ei), axis=1) for ei in fixed_test_eis]
        fixed_test_eis = np.array(test_eis_mean)
    # For 'power' method, square each 512 x 201 ei array, take the mean over time,
    # and stack the resulting 512 x 1 vectors into a numpy array
    elif "power" in method:
        test_eis_mean = [np.mean(ei**2, axis=1) for ei in fixed_test_eis]
        fixed_test_eis = np.array(test_eis_mean)
    else:
        raise NameError("Method poperty must be 'full', 'space', or 'power'.")

    # UPDATED 2026-08-11 (Claude, per yas -- this crashed as a cryptic "IndexError:
    # tuple index out of range" on a different dataset than the ones this had been run
    # against before, with no indication of what actually went wrong). Root cause:
    # ref_ids/test_ids ends up empty (every cell in that chunk/block had no usable EI --
    # see the "EI loading summary"/"ERROR: 0 cells..." prints added to
    # AnalysisChunk.__init__ and MEAResponseBlock.__init__), so np.array([]) on an empty
    # list of flattened EIs produces a 1D array with no second axis, and
    # fixed_ref_eis.shape[1] below raised IndexError with no explanation. This turns
    # that into an actionable error instead.
    if fixed_ref_eis.ndim < 2 or fixed_ref_eis.shape[0] == 0:
        raise ValueError(
            f"ei_corr: no usable reference EIs ({len(ref_ids)} ref_ids, "
            f"fixed_ref_eis shape {fixed_ref_eis.shape}). This almost always means "
            "every cell in the reference object had no usable EI -- check for "
            "'EI loading summary' / 'ERROR: 0 cells...' printed when that "
            "AnalysisChunk/MEAResponseBlock was constructed (may be hidden inside a "
            "`with scrollable_prints():` block above)."
        )
    if fixed_test_eis.ndim < 2 or fixed_test_eis.shape[0] == 0:
        raise ValueError(
            f"ei_corr: no usable test EIs ({len(test_ids)} test_ids, "
            f"fixed_test_eis shape {fixed_test_eis.shape}). This almost always means "
            "every cell in the test object had no usable EI -- check for "
            "'EI loading summary' / 'ERROR: 0 cells...' printed when that "
            "AnalysisChunk/MEAResponseBlock was constructed (may be hidden inside a "
            "`with scrollable_prints():` block above)."
        )

    num_pts = fixed_ref_eis.shape[1]

    # Calculate covariance and correlation
    # TEMP FIX FOR NUMPY BUG that shows erroneous warnings Macs running
    # M4 and M5 chips. See Numpy bug 29820:
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        c = fixed_test_eis @ fixed_ref_eis.T / num_pts

    d = np.mean(fixed_test_eis, axis=1)[:, None] * np.mean(fixed_ref_eis, axis=1)[:, None].T
    covs = c - d

    std_calc = np.std(fixed_test_eis, axis=1)[:, None] * np.std(fixed_ref_eis, axis=1)[:, None].T
    corr = covs / std_calc

    # Set nan values and infinite values to 0
    np.nan_to_num(corr, copy=False, nan=0, posinf=0, neginf=0)

    return corr.T


def create_dictionary_from_file(file_path, delimiter=" "):
    result_dict = {}

    with open(file_path, "r") as file:
        for line in file:
            # Split each line into key and value using the specified delimiter
            key, value = map(str.strip, line.split(delimiter, 1))

            # Add key-value pair to the dictionary
            result_dict[int(key)] = value

    return result_dict


def get_presentation_times(
    frame_times: np.ndarray,
    preFrames: int,
    flashFrames: int,
    gapFrames: int,
    images_per_epoch: int,
):

    # Ensure frame times are in integers
    preFrames = int(preFrames)
    flashFrames = int(flashFrames)
    gapFrames = int(gapFrames)
    images_per_epoch = int(images_per_epoch)

    flash_times = []
    gap_times = []

    for epoch in range(frame_times.shape[0]):
        flash_times.append(
            [
                frame_times[epoch, preFrames + flashFrames * idx + gapFrames * idx]
                for idx in range(images_per_epoch)
            ]
        )
        gap_times.append(
            [
                frame_times[
                    epoch, preFrames + flashFrames * (idx + 1) + gapFrames * idx
                ]
                for idx in range(images_per_epoch)
            ]
        )

    pre_times = [frame_times[epoch, preFrames] for epoch in range(frame_times.shape[0])]
    pre_times = np.array(pre_times)
    flash_times = np.array(flash_times)
    gap_times = np.array(gap_times)

    return flash_times, gap_times, pre_times
