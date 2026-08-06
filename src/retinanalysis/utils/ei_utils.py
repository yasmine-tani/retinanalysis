from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from visionloader import VisionCellDataTable

import numpy as np
import matplotlib.pyplot as plt


def sort_electrode_map(electrode_map: np.ndarray) -> np.ndarray:
    """
    Sort electrodes by their x, y locations.

    This uses lexsort to sort electrodes by their x, y locations
    First sort by rows, break ties by columns.
    As each row is jittered but within row the electrodes have exact same y location.

    Parameters:
    electrode_map (numpy.ndarray): The electrode locations of shape (512, 2).

    Returns:
    numpy.ndarray: Sorted indices of the electrodes (512,).
    """
    sorted_indices = np.lexsort((electrode_map[:, 0], electrode_map[:, 1]))
    return sorted_indices


def reshape_ei(
    ei: np.ndarray, sorted_electrodes: np.ndarray, n_rows: int = 16
) -> np.ndarray:
    """
    Reshape the EI matrix from 512 x 201 to 16 x 32 x 201 based on electrode locations.

    Parameters:
    ei (numpy.ndarray): The EI matrix of shape (electrode, frames).
    sorted_electrodes (numpy.ndarray): The sorted indices of the electrodes.
    n_rows (int): The number of rows to reshape the EI matrix into. Default is 16.

    Returns:
    numpy.ndarray: The reshaped EI matrix of shape (16, 32, 201).
    """
    if ei.shape[0] != 512:
        print(f"Warning: Expected EI shape (512, 201), got {ei.shape}")
    n_electrodes = ei.shape[0]
    n_frames = ei.shape[1]
    n_cols = n_electrodes // n_rows  # Assuming 512 electrodes and 16 rows

    if n_cols * n_rows != n_electrodes:
        raise ValueError(
            f"Number of electrodes {n_electrodes} is not compatible with {n_rows} rows and {n_cols} columns."
        )

    sorted_ei = ei[sorted_electrodes]

    # Reshape the sorted EI matrix
    reshaped_ei = sorted_ei.reshape(n_rows, n_cols, n_frames)

    return reshaped_ei


def get_top_electrodes(
    n_ID: int, vcd: VisionCellDataTable, n_interval=2, n_markers=5, b_sort=True
):
    # Reshape EI timeseries
    ei = vcd.get_ei_for_cell(n_ID).ei
    sorted_electrodes = sort_electrode_map(vcd.get_electrode_map())
    ei = reshape_ei(ei, sorted_electrodes)

    # Get EI map = abs max projection across timeframes
    ei_map = np.max(np.abs(ei), axis=2)
    ei_map = np.log10(ei_map + 1e-6)

    ## Label top n_markers pixels spaced by n_interval in the heatmap
    # Sorted index of pixels
    ei_map_sidx = np.argsort(ei_map.flatten())[::-1]
    top_idx = ei_map_sidx[::n_interval][:n_markers]

    # Sort top_idx by argmin of EI time series
    if b_sort:
        amin_ei_ts = np.zeros(n_markers)
        for i in range(n_markers):
            y, x = np.unravel_index(top_idx[i], ei_map.shape)
            # ei_ts = ei_grid[:, y, x]
            ei_ts = ei[y, x, :]
            amin_ei_ts[i] = np.argmin(ei_ts)
        top_idx = top_idx[np.argsort(amin_ei_ts)]

    return top_idx


def get_ei_and_map(n_ID: int, vcd: VisionCellDataTable):
    # Reshape EI timeseries
    ei = vcd.get_ei_for_cell(n_ID).ei
    sorted_electrodes = sort_electrode_map(vcd.get_electrode_map())
    ei = reshape_ei(ei, sorted_electrodes)
    ei_map = np.max(np.abs(ei), axis=2)
    return ei, ei_map


def plot_ei_map(
    n_ID: int, vcd: VisionCellDataTable, top_idx=None, axs=None, label=None
):
    sorted_electrodes = sort_electrode_map(vcd.get_electrode_map())
    if top_idx is None:
        # Get top electrodes if not provided
        top_idx = get_top_electrodes(n_ID, vcd)

    ei, ei_map = get_ei_and_map(n_ID, vcd)
    # Log is better for visualization
    ei_map = np.log10(ei_map + 1e-6)

    # top_idx is the top n_markers pixels to plot, returned by get_top_electrodes
    n_markers = len(top_idx)
    if axs is None:
        f, axs = plt.subplots(
            nrows=n_markers + 1,
            figsize=(6, 8),
            gridspec_kw={"height_ratios": [1] + [1 / n_markers] * n_markers},
        )

    sample_rate = 20000.0  # Hz
    sts = vcd.get_spike_times_for_cell(n_ID)
    num_sps = len(sts)
    max_st = sts.max() / sample_rate
    avg_rate = num_sps / max_st

    ax0 = axs[0]
    im = ax0.imshow(ei_map, cmap="hot", aspect="auto")
    plt.colorbar(im, ax=ax0, label="log10(abs(EI amplitude))")

    # Get index of peak
    peak_channel = np.argmax(ei_map)
    peak_idx = np.unravel_index(peak_channel, ei_map.shape)
    peak_channel_idx = sorted_electrodes[peak_channel]
    ax0.plot(peak_idx[1], peak_idx[0], "o", color="blue")
    ax0.axhline(peak_idx[0], color="blue")
    ax0.axvline(peak_idx[1], color="blue")

    for i in range(n_markers):
        top = top_idx[i]
        channel_idx = sorted_electrodes[top]
        y, x = np.unravel_index(top, ei_map.shape)
        ax0.plot(x, y, "o", color="C2", ms=5)
        ax0.text(x, y, str(i), color="k")

        ax = axs[i + 1]
        # ei_ts = ei_grid[:, y, x]
        ei_ts = ei[y, x, :]
        ax.plot(ei_ts, "C2")
        ax.axvline(np.argmin(ei_ts), color="k")
        ax.set_xticks([])
        ax.set_ylabel(f"{i} (e{channel_idx})")

    # Set xticks for last ax
    ax.set_xticks(np.arange(0, len(ei_ts), 50))
    ax.set_xlabel("Timeframe")

    str_title = ""
    if label is not None:
        str_title += f"{label} "
    str_title += f"ID {n_ID}\nPeak: {peak_idx}, e{peak_channel_idx}\n{num_sps} sps ({avg_rate:.1f} Hz)\n"
    ax0.set_title(str_title)
    plt.tight_layout()
    return ax0


def _significant_electrode_mask(
    ei: np.ndarray, electrode_threshold: float = 5.0, min_significant_electrodes: int = 10,
) -> Tuple[np.ndarray, bool]:
    """
    UPDATED 2026-08-05 (Claude, per yas): per-electrode boolean mask of which
    electrodes carry a significant signal for this EI, now matching yas's MATLAB
    map_ei_amr's "space_only" thresholding convention exactly, instead of the previous
    adaptive "abs(value) >= significance_std * ei.std()" rule. Was previously shared
    with ei_corr()/cluster_match()'s (vision_utils.py) own noise-zeroing threshold --
    that function is UNCHANGED and still uses its own convention; this only affects the
    footprint QC plots (plot_ei_footprint_across_ndfs, plot_ei_footprint_mosaic_for_cell_type)
    below, not the actual cross-NDF/cross-chunk cell matching used everywhere else in
    the package. See changes/ei_footprint_data_quality_notes.md for why: yas noticed
    the footprint plots' zoom window "picking up too much of the cell" -- the old
    adaptive threshold scales with each EI's own std, so a lower-variance EI got a
    looser absolute cutoff than a noisier one, letting more electrodes count as
    "significant" inconsistently across cells.

    Two changes from MATLAB's map_ei_amr, both per yas:
    - electrode_threshold (default 5.0) is now a FIXED absolute cutoff on peak
      amplitude, not scaled by that EI's own std -- matches map_ei_amr's
      'electrode_threshold' parameter (also 5 there) exactly. Verified (as much as
      possible without a live MATLAB session) that this is safe to compare directly:
      Python's EIReader (visionloader.py, vendored in
      lib/artificial-retina-software-pipeline/utilities/) reads the same .ei binary
      file Vision produces with zero scaling/unit conversion applied anywhere in the
      read path (confirmed by reading EIReader.get_ei_for_cell_id() and
      VisionCellDataTable.get_ei_for_cell(), both direct passthroughs of the raw
      unpacked file bytes) -- so whatever units the .ei file stores are exactly what
      this function sees, same as MATLAB's own loader would see reading the identical
      file.
    - min_significant_electrodes (default 10) is a NEW gate this package didn't have
      at all before -- matches map_ei_amr's 'significant_electrodes' parameter. Unlike
      MATLAB (which excludes the cell from matching entirely if this isn't met), the
      QC plots here still draw the cell -- excluding a QC visualization would defeat
      the point of a QC check -- but the caller is expected to check the returned
      `enough_electrodes` flag and warn/flag prominently rather than silently drawing
      a marginal cell as if it were fine.

    Deliberately did NOT copy map_ei_amr's use of raw max() instead of max(abs()) --
    per yas's own call: many real spike waveforms peak negative-going (near the soma),
    so dropping abs() risks scoring a real, large-amplitude electrode as
    "not significant" if its positive-going rebound happens to be small. Kept abs().

    Parameters:
        ei (np.ndarray): shape (n_electrodes, n_frames).

        electrode_threshold (float): fixed absolute cutoff on
        max(abs(ei), axis=1) for an electrode to count as significant. Default 5.0,
        matching map_ei_amr's default.

        min_significant_electrodes (int): minimum number of electrodes that must clear
        electrode_threshold for this EI to be considered well-localized/reliable.
        Default 10, matching map_ei_amr's default. Does NOT affect what mask is
        returned -- only the `enough_electrodes` flag, for the caller to warn on.

    Returns:
        (mask, enough_electrodes): mask is the per-electrode boolean array (same as
        before). enough_electrodes is True iff mask.sum() >= min_significant_electrodes.
    """
    amp = np.max(np.abs(ei), axis=1)
    mask = amp >= electrode_threshold
    enough_electrodes = bool(mask.sum() >= min_significant_electrodes)
    return mask, enough_electrodes


def _span_normalized_marker_scale(marker_scale, span, reference_span, min_ratio=1 / 3.0, max_ratio=1.0):
    """
    NEW 2026-08-05 (Claude, per yas): rescales a marker_scale (max scatter dot AREA, in
    matplotlib's points^2 `s` units) so dots represent a roughly consistent PHYSICAL
    size across panels with different zoom spans, instead of the same fixed
    screen-space size regardless of how much of the array a given panel's zoom window
    covers.

    Why this matters: matplotlib's `s` is a fixed screen-space (points^2) size, not
    tied to data coordinates. Two panels can be drawn at the same physical figure size
    but show very different amounts of physical space (e.g. a tightly-cropped
    significant-electrode region vs. the full electrode array, or -- in the EI mosaic
    -- one cell's tightly localized footprint vs. another cell's more spread-out one).
    If both use the same `s`, the panel with the WIDER span packs more physical
    distance into the same screen space, so the same-size dot ends up representing (and
    visually looking like) a bigger chunk of that panel -- yas: "the far away [wider
    zoom] one seems slightly too big" / mosaic rows "some are big and some are tiny".

    Since `s` is an AREA and a physical size scales linearly with span, the correct
    area-scale factor is (reference_span / span) ** 2 -- a panel showing 2x the
    physical distance needs 1/4 the marker area to represent the same physical dot
    size.

    UPDATED 2026-08-06 (Claude, per yas): `max_ratio` dropped from 3.0 to 1.0 --
    i.e. this now only ever SHRINKS wide-span panels, never BOOSTS narrow-span ones
    above the flat marker_scale baseline. Originally this clipped symmetrically
    ([1/3, 3] linear, up to 9x area), on the assumption that narrow-span rows were
    also somewhat undersized. But yas's own prior feedback was that narrow/zoomed-in
    rows already "look fine" at the flat baseline -- only the wide-span rows were
    reported oversized. The up-to-9x boost was invisible while every electrode was
    still being drawn (lots of small background dots blended together), but once the
    two-tier context/significant draw (2026-08-05) removed that clutter, the boosted
    significant-tier dots in narrow-span rows were left bare and became visibly huge,
    overlapping, near-solid circles -- yas: "the circles are like huge in some spots
    now, it made the zoomed in ones worse." Since narrow-span rows didn't need
    boosting in the first place, the fix is to cap the ratio at 1.0 (no boost, shrink
    only) rather than trying to re-tune the boost amount.

    Parameters:
        marker_scale (float): the base/reference marker_scale (points^2 `s` units, at
        100% relative amplitude).

        span (float): this panel's own zoom span (e.g. max(xlim span, ylim span)), in
        the same physical units as reference_span (electrode map coordinates).

        reference_span (float): the span this marker_scale was calibrated against
        (e.g. the shared zoomed-panel span in plot_ei_footprint_across_ndfs, or the
        median row span in plot_ei_footprint_mosaic_for_cell_type).

        min_ratio, max_ratio (float): clip bounds on the LINEAR (reference_span/span)
        ratio before squaring. Defaults 1/3 (shrink wide-span panels up to 9x area
        down) and 1.0 (never boost narrow-span panels above baseline).

    Returns:
        float: the adjusted marker_scale to use for this specific panel.
    """
    if span <= 0 or reference_span <= 0:
        return marker_scale
    ratio = np.clip(reference_span / span, min_ratio, max_ratio)
    return marker_scale * (ratio ** 2)


def plot_ei_footprint_across_ndfs(
    ref_vcd: "VisionCellDataTable",
    ref_cell_id: int,
    ref_label: str,
    ndf_labels: List[str],
    ndf_vcds: List[Optional["VisionCellDataTable"]],
    ndf_cell_ids: List[Optional[int]],
    ndf_corrs: List[Optional[float]],
    electrode_threshold: float = 5.0,
    min_significant_electrodes: int = 10,
    zoom_padding_frac: float = 0.3,
    marker_scale: float = 250.0,
    n_cols: int = 3,
):
    """
    NEW 2026-08-04 (Claude, per yas): EI footprint comparison across light levels, for
    one reference cell -- a data-quality/QC check that a cell's electrical footprint
    (and therefore its identity) is being tracked consistently across NDFs, not just
    that some correlation number cleared a threshold.

    Each electrode is drawn as a dot at its real physical (x, y) position (from
    vcd.get_electrode_map()), sized by that electrode's peak |EI amplitude|
    (max(abs(ei), axis=1)) for the matched cell in that panel -- NOT the reshaped-grid
    heatmap style of plot_ei_map() above, this matches a footprint-scatter convention
    instead. One panel per NDF (using whatever cell that NDF's own EI-matching already
    found -- this function does no matching itself, it only plots cell IDs/correlations
    handed to it), plus one additional panel showing the reference cell's own footprint
    in the context of the FULL electrode array (all electrodes in light gray, the
    "significant" electrodes -- UPDATED 2026-08-05: now matching yas's MATLAB
    map_ei_amr's thresholding convention, abs(ei) >= electrode_threshold (a fixed
    value, default 5.0, not scaled by that EI's own std like before) -- highlighted in
    red), for scale.

    This function does NOT do any EI matching or correlation computation -- it only
    draws whatever (cell_id, corr) pairs you hand it. That's deliberate: matching stays
    on the existing, unmodified cluster_match()/ei_corr() (vision_utils.py), same
    convention used everywhere else in this package (cell typing, cross-NDF CRF
    matching, etc.) -- this just visualizes the result. See
    changes/ei_footprint_data_quality_notes.md for the reasoning (yas's MATLAB
    map_ei_amr/compare_map_ei_amr use a different matching convention -- stricter
    corr_threshold, a minimum-significant-electrode gate, and un-abs'd max instead of
    max(abs()) -- none of that has been reconciled with cluster_match(), so the
    correlation values shown here reflect OUR existing matching convention, not
    yas's MATLAB one).

    Marker sizes are normalized against the REFERENCE cell's own peak amplitude (not
    each panel's own max) and reused identically for every panel, so a real drop in
    spike amplitude at a given NDF shows up as visibly smaller dots there, rather than
    every panel being independently rescaled to look the same size regardless of
    amplitude. UPDATED 2026-08-05 (Claude, per yas): the reference/full-array panel is
    an exception -- it's zoomed OUT to the whole array rather than cropped like the NDF
    panels, so its marker_scale is separately rescaled (_span_normalized_marker_scale,
    below) to represent the same PHYSICAL dot size as the zoomed panels rather than the
    same screen-space size, which otherwise looks oversized there.

    Different NDF chunks can legitimately have different electrode counts (e.g. 512 vs.
    519 -- seen in yas's data from inconsistent per-sort bad-channel exclusion, see
    changes/ for the investigation). This function never assumes electrode arrays line
    up by index between chunks -- every panel uses its OWN vcd's electrode map and EI
    array, and the shared zoom window is just a physical (x, y) bounding box (in
    microns), which is safe to reuse across chunks with different electrode counts.

    Parameters:
        ref_vcd: VisionCellDataTable for the reference/parent chunk (e.g. the NDF 0
        white-noise/typing chunk).

        ref_cell_id (int): cell ID, in ref_vcd, to check.

        ref_label (str): label for the reference panel, e.g. 'NDF 0'.

        ndf_labels (List[str]): one label per NDF panel, e.g. ['NDF 5', 'NDF 4', ...].

        ndf_vcds (List[VisionCellDataTable or None]): one VisionCellDataTable per NDF
        (the target/child chunk for that NDF). None if that NDF had no usable data.

        ndf_cell_ids (List[int or None]): the cell ID, in the corresponding ndf_vcds
        entry, that ref_cell_id was matched to. None if no match was found.

        ndf_corrs (List[float or None]): the EI correlation for that match (from
        cluster_match()/ei_corr()'s corr_dict). None if no match was found.

        electrode_threshold (float): fixed absolute cutoff on max(abs(ei)) for an
        electrode to count as "significant" -- only used to pick the zoom window and to
        decide which electrodes get highlighted red in the full-array panel. Default
        5.0, matching yas's MATLAB map_ei_amr's 'electrode_threshold' default (see
        _significant_electrode_mask's docstring for the units-matching verification).

        min_significant_electrodes (int): if ref_cell_id has fewer than this many
        electrodes clearing electrode_threshold, a warning prints and the figure title
        is flagged -- the zoom window still gets drawn (falling back to the top-20 by
        amplitude if literally zero electrodes qualify), but this is a signal the cell
        may be weak/marginal. Default 10, matching map_ei_amr's
        'significant_electrodes' default.

        zoom_padding_frac (float): fraction of the significant-electrode bounding box's
        width/height to pad on each side when setting the zoom window. Default 0.3.

        marker_scale (float): max scatter marker size (matplotlib's area-like `s`
        units), applied to the reference cell's own peak-amplitude electrode. Default
        250.

        n_cols (int): panels per row (NDF panels + the reference/full-array panel are
        laid out in one grid). Default 3 (matches a 2x3 grid for 5 NDFs + 1 reference
        panel).

    Returns:
        fig: the matplotlib Figure.
    """
    n_ndf_panels = len(ndf_labels)
    n_panels = n_ndf_panels + 1  # + the reference/full-array panel
    n_rows = int(np.ceil(n_panels / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.2 * n_cols, 4.2 * n_rows))
    axes = np.atleast_1d(axes).flatten()

    ref_ei = ref_vcd.get_ei_for_cell(ref_cell_id).ei
    ref_electrode_map = ref_vcd.get_electrode_map()
    ref_amp = np.max(np.abs(ref_ei), axis=1)
    ref_max_amp = ref_amp.max() if ref_amp.max() > 0 else 1.0
    sig_mask, enough_electrodes = _significant_electrode_mask(
        ref_ei, electrode_threshold, min_significant_electrodes,
    )
    # Tracks what actually happened for the marginal_note shown on the reference panel
    # title below -- computed here (not re-derived from sig_mask/enough_electrodes
    # after the fallback reassignment) so a zero-electrode fallback to the top 20 by
    # amplitude doesn't get mislabeled as "only 20/10" (enough_electrodes reflects the
    # ORIGINAL, pre-fallback mask, which is what should be reported).
    marginal_note = ""

    if not sig_mask.any():
        print(
            f"WARNING: no electrodes for reference cell {ref_cell_id} cleared the "
            f"electrode_threshold={electrode_threshold} threshold -- falling back to "
            "the top 20 electrodes by amplitude for the zoom window instead."
        )
        top_n = min(20, len(ref_amp))
        fallback_idx = np.argsort(ref_amp)[::-1][:top_n]
        sig_mask = np.zeros_like(sig_mask)
        sig_mask[fallback_idx] = True
        marginal_note = "\n(0 electrodes cleared threshold -- showing top 20 by amplitude)"
    elif not enough_electrodes:
        print(
            f"WARNING: reference cell {ref_cell_id} only has {int(sig_mask.sum())} "
            f"electrode(s) clearing electrode_threshold={electrode_threshold} "
            f"(< min_significant_electrodes={min_significant_electrodes}) -- this "
            "cell may be weak/marginal. Peak amplitude range across all electrodes: "
            f"[{ref_amp.min():.1f}, {ref_amp.max():.1f}]."
        )
        marginal_note = f"\n(only {int(sig_mask.sum())}/{min_significant_electrodes} min sig. electrodes)"

    sig_coords = ref_electrode_map[sig_mask]
    x_min, y_min = sig_coords.min(axis=0)
    x_max, y_max = sig_coords.max(axis=0)
    x_pad = max((x_max - x_min) * zoom_padding_frac, 1.0)
    y_pad = max((y_max - y_min) * zoom_padding_frac, 1.0)
    xlim = (x_min - x_pad, x_max + x_pad)
    ylim = (y_min - y_pad, y_max + y_pad)

    def _draw_footprint(ax, vcd, cell_id, title):
        # UPDATED 2026-08-05 (Claude, per yas): two-tier draw, same convention the
        # dedicated full-array reference panel below already uses (small fixed-size
        # gray context dots for EVERY electrode + amplitude-scaled dots only for
        # electrodes clearing electrode_threshold) -- was previously ALL electrodes at
        # an amplitude-scaled size (floored at 0.5, but still multiplied by
        # marker_scale), which packed hundreds of near-invisible dots into the crop and
        # made wider crops look like one solid blob rather than a real footprint shape.
        # Context dots stay a small FIXED size regardless of zoom/marker_scale, so they
        # can't balloon -- yas wants them kept ("i still want to see the surrounding
        # electrodes... so i know where it is on the array and what it spans").
        electrode_map = vcd.get_electrode_map()
        ei = vcd.get_ei_for_cell(cell_id).ei
        amp = np.max(np.abs(ei), axis=1)
        panel_sig_mask, _ = _significant_electrode_mask(ei, electrode_threshold, min_significant_electrodes)

        ax.scatter(electrode_map[:, 0], electrode_map[:, 1], s=4, color="0.75")

        sizes = np.clip(
            marker_scale * (amp[panel_sig_mask] / ref_max_amp), 0.5, marker_scale
        )
        ax.scatter(
            electrode_map[panel_sig_mask, 0], electrode_map[panel_sig_mask, 1],
            s=sizes, color="k", alpha=0.85,
        )
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=11)

    for i, (label, vcd, cell_id, corr) in enumerate(
        zip(ndf_labels, ndf_vcds, ndf_cell_ids, ndf_corrs)
    ):
        ax = axes[i]
        if vcd is None or cell_id is None:
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{label}\nno match", fontsize=11, color="gray")
            continue
        corr_str = f"cor = {corr:.3f}" if corr is not None else "cor = ?"
        _draw_footprint(ax, vcd, cell_id, f"{label}={cell_id}\n{corr_str}")

    # Reference panel: full array in light gray, significant electrodes in red.
    # UPDATED 2026-08-05 (Claude, per yas): "the far away one seems slightly too big"
    # -- this panel isn't zoomed to xlim/ylim like the NDF panels are (it shows the
    # WHOLE array, for context), so the same marker_scale used there would draw
    # visually oversized dots here (see _span_normalized_marker_scale's docstring for
    # why). Rescaled so red dots represent roughly the same PHYSICAL size here as they
    # do in the zoomed panels, not the same screen-space size.
    zoomed_span = max(xlim[1] - xlim[0], ylim[1] - ylim[0])
    full_array_span = max(
        ref_electrode_map[:, 0].max() - ref_electrode_map[:, 0].min(),
        ref_electrode_map[:, 1].max() - ref_electrode_map[:, 1].min(),
    )
    ref_panel_marker_scale = _span_normalized_marker_scale(marker_scale, full_array_span, zoomed_span)

    ref_ax = axes[n_ndf_panels]
    ref_ax.scatter(
        ref_electrode_map[:, 0], ref_electrode_map[:, 1], s=4, color="0.75",
    )
    sig_sizes = np.clip(
        ref_panel_marker_scale * (ref_amp[sig_mask] / ref_max_amp), 0.5, ref_panel_marker_scale
    )
    ref_ax.scatter(
        ref_electrode_map[sig_mask, 0], ref_electrode_map[sig_mask, 1],
        s=sig_sizes, color="darkred",
    )
    ref_ax.set_xticks([])
    ref_ax.set_yticks([])
    ref_ax.set_aspect("equal")
    ref_ax.set_title(f"{ref_label}={ref_cell_id}\nparent data{marginal_note}", fontsize=11, color="darkred")

    for j in range(n_panels, len(axes)):
        axes[j].axis("off")

    fig.tight_layout()
    return fig


def get_ei_matches_across_ndfs(
    ref_analysis_chunk,
    exp_name: str,
    protocol_name: str,
    ss_version: str = "kilosort2.5",
    corr_cutoff: float = 0.85,
    verbose: bool = True,
):
    """
    NEW 2026-08-04 (Claude, per yas): find one datafile per NDF for protocol_name (via
    get_ndf_blocks_for_protocol, real database NDF values -- not a hardcoded NDF list),
    load each as an MEAResponseBlock, and EI-match every cell in ref_analysis_chunk
    against it using the existing, unmodified cluster_match()/ei_corr()
    (vision_utils.py) -- the same matching convention already used everywhere else in
    this package. This function does no plotting -- see
    plot_ei_footprint_across_ndfs() above for that, and pick_example_cell_for_footprint()
    below to auto-select a well-matched cell from the result.

    The reference chunk's own NDF/datafile (ref_analysis_chunk.chunk_name) is skipped
    automatically if it's among the NDF blocks found for protocol_name -- matching a
    chunk's cells against themselves is trivial (corr ~1.0 for everything) and not
    useful to plot alongside the real cross-NDF matches.

    Parameters:
        ref_analysis_chunk: an AnalysisChunk with EIs loaded (include_ei not set to
        False), used as the reference/parent side of the match at every NDF.

        exp_name (str): experiment name.

        protocol_name (str): exact protocol name to find NDF blocks for (e.g.
        'manookinlab.protocols.SpatialNoise' for a white-noise-based check, or any
        other protocol that was run at multiple NDFs).

        ss_version (str): spike-sorting version for locating each NDF's datafile.
        Default 'kilosort2.5'.

        corr_cutoff (float): EI correlation cutoff passed to cluster_match(). Default
        0.85, matching this package's other cross-NDF matching (e.g.
        contrast_response_utils.py's CORR_THRESHOLD_* defaults).

        verbose (bool): print progress per NDF. Default True.

    Returns:
        df_matches (pandas DataFrame): columns ['ref_cell_id', 'NDF', 'matched_cell_id',
        'corr'] -- one row per (ref_cell_id, NDF) pair that had a valid match at that
        NDF (corr_cutoff and cluster_match's own forward/reverse-consistency checks
        both have to pass). No row at all for a given (ref_cell_id, NDF) combination
        means that cell had no acceptable match at that NDF.

        ndf_vcds (dict): {NDF value: VisionCellDataTable}, for every NDF that loaded
        successfully -- hand this straight to plot_ei_footprint_across_ndfs() so it
        doesn't need to reload anything. Does NOT include the reference chunk's own
        NDF/datafile (see note above) -- so plot_ei_footprint_across_ndfs's "reference"
        panel and its "NDF" panels are never the same recording.

        ref_ndf (float or None): NEW 2026-08-05 (Claude, per yas) -- the NDF value of
        ref_analysis_chunk's own datafile (found by matching ref_datafile_name against
        df_ndf_blocks, the same lookup that decides which block to skip above), so
        callers can print/label which NDF the reference actually is instead of assuming
        it's NDF 0. None if ref_analysis_chunk.chunk_name wasn't found among this
        protocol's NDF blocks at all (e.g. the reference chunk used a different
        protocol name than protocol_name).
    """
    import pandas as pd
    from retinanalysis.utils.correlation_utils import get_ndf_blocks_for_protocol
    from retinanalysis.classes.response import MEAResponseBlock
    from retinanalysis.utils.vision_utils import cluster_match

    df_ndf_blocks = get_ndf_blocks_for_protocol(exp_name, protocol_name, verbose=verbose)
    if len(df_ndf_blocks) == 0:
        print(f"No {protocol_name} blocks found for {exp_name} at any NDF.")
        return pd.DataFrame(columns=["ref_cell_id", "NDF", "matched_cell_id", "corr"]), {}, None

    ref_datafile_name = getattr(ref_analysis_chunk, "chunk_name", None)

    rows = []
    ndf_vcds = {}
    ref_ndf = None
    for _, row in df_ndf_blocks.iterrows():
        ndf_val = row["NDF"]
        datafile_name = row["datafile_name"]

        if ref_datafile_name is not None and datafile_name == ref_datafile_name:
            ref_ndf = ndf_val
            if verbose:
                print(
                    f"--- NDF {ndf_val} ({datafile_name}) is the reference chunk's "
                    "own datafile, skipping (matching it against itself is trivial) ---"
                )
            continue

        if verbose:
            print(f"--- NDF {ndf_val} ({datafile_name}) ---")
        try:
            response_block = MEAResponseBlock(
                exp_name, datafile_name, ss_version, include_ei=True,
                b_load_fd=False, verbose=verbose,
            )
        except Exception as e:
            print(f"  Skipping NDF {ndf_val}: {e}")
            continue

        ndf_vcds[ndf_val] = response_block.vcd
        match_dict, corr_dict = cluster_match(
            ref_analysis_chunk, response_block, corr_cutoff=corr_cutoff, verbose=verbose,
        )
        for ref_id, matched_id in match_dict.items():
            rows.append(
                {
                    "ref_cell_id": ref_id,
                    "NDF": ndf_val,
                    "matched_cell_id": matched_id,
                    "corr": corr_dict.get(ref_id),
                }
            )

    df_matches = pd.DataFrame(rows, columns=["ref_cell_id", "NDF", "matched_cell_id", "corr"])
    return df_matches, ndf_vcds, ref_ndf


def summarize_ei_matches(df_matches):
    """
    NEW 2026-08-05 (Claude, per yas): ranked summary table over the output of
    get_ei_matches_across_ndfs() -- one row per ref_cell_id, so you can browse which
    cells are well-tracked across NDFs and pick one to look at with
    plot_ei_footprint_across_ndfs(), instead of only ever seeing whichever cell
    pick_example_cell_for_footprint() would have auto-picked.

    Sort order (n_ndfs_matched desc, then mean_corr desc) is the same ordering
    pick_example_cell_for_footprint() uses to choose its top pick -- so that function's
    result is always summary.iloc[0]['ref_cell_id'] (see its refactored body below,
    which now just calls this).

    Parameters:
        df_matches (pandas DataFrame): output of get_ei_matches_across_ndfs().

    Returns:
        pandas DataFrame with columns ['ref_cell_id', 'n_ndfs_matched', 'mean_corr',
        'min_corr'], sorted best-to-worst.
    """
    import pandas as pd

    if len(df_matches) == 0:
        return pd.DataFrame(columns=["ref_cell_id", "n_ndfs_matched", "mean_corr", "min_corr"])

    summary = (
        df_matches.groupby("ref_cell_id")["corr"]
        .agg(n_ndfs_matched="count", mean_corr="mean", min_corr="min")
        .reset_index()
    )
    summary = summary.sort_values(
        ["n_ndfs_matched", "mean_corr"], ascending=False
    ).reset_index(drop=True)
    return summary


def pick_example_cell_for_footprint(df_matches) -> Optional[int]:
    """
    NEW 2026-08-04 (Claude, per yas): auto-pick a reference cell to use as the example
    in plot_ei_footprint_across_ndfs(), from the output of get_ei_matches_across_ndfs().
    Picks whichever ref_cell_id was matched at the most NDFs, breaking ties by highest
    mean correlation across those NDFs -- a cell that's cleanly trackable everywhere,
    not just a lucky high correlation at one NDF.

    UPDATED 2026-08-05 (Claude, per yas): now just takes the top row of
    summarize_ei_matches() instead of re-deriving its own aggregation -- same ordering,
    kept in one place so the ranked table and the auto-pick can never disagree.

    Parameters:
        df_matches (pandas DataFrame): output of get_ei_matches_across_ndfs().

    Returns:
        ref_cell_id (int or None): the picked cell ID, or None if df_matches is empty.
    """
    summary = summarize_ei_matches(df_matches)
    if len(summary) == 0:
        return None
    return int(summary.iloc[0]["ref_cell_id"])


def plot_ei_footprint_mosaic_for_cell_type(
    analysis_chunk,
    df_matches,
    ndf_vcds,
    cell_type: str,
    ndf_values: Optional[List] = None,
    ref_ndf=None,
    typing_file: Optional[str] = None,
    electrode_threshold: float = 5.0,
    min_significant_electrodes: int = 10,
    zoom_padding_frac: float = 0.3,
    marker_scale: float = 120.0,
    panel_size: float = 1.7,
    verbose: bool = True,
):
    """
    NEW 2026-08-05 (Claude, per yas): EI footprint mosaic -- ROW = one cell of
    cell_type, COLUMN = one NDF, small "mosaic vibes" square panels. Same layout idea
    as plot_ei_footprint_across_ndfs() above (one cell's footprint side by side across
    NDFs), just repeated as one row per cell instead of picking a single cell at a
    time -- so a whole cell type can be scanned for outliers/bad matches, cell by cell,
    NDF by NDF, in one scrollable mosaic.

    REPLACES an earlier version of this same function (2026-08-05, same day) that put
    ONE NDF per whole mosaic and a different cell in every panel -- yas's feedback: "no
    but i dont feel like its producing side by side plots of the sme cell it just has
    which cell ids it mapped to with an arrow as the title but then no other plots also
    have that id". That version answered a different question (scan many cells at one
    NDF) than what was actually wanted (scan one cell type across NDFs, cell by cell).

    Reuses df_matches/ndf_vcds from get_ei_matches_across_ndfs() -- already computed
    once in the cell above this one in the notebook -- so this does no new EI matching
    or NDF loading itself, same "compute once, cheaply re-view many ways" pattern as
    summarize_ei_matches()/pick_example_cell_for_footprint().

    Zoom window and amplitude-normalization scale are shared PER ROW (computed from
    that row's own reference cell's EI in analysis_chunk.vcd, same convention
    plot_ei_footprint_across_ndfs() uses for its one cell) -- every column in a row is
    the SAME physical cell at a different light level, so a real amplitude drop should
    show up as a visibly smaller dot within that row. Each row's window/scale is
    independent of every other row (different cells, different amplitudes/positions).

    UPDATED 2026-08-05 (Claude, per yas): "make the squares all the same size some are
    big and some are tiny" -- different cells have differently-sized zoom windows (a
    widely-spread footprint needs a wider crop than a tightly localized one), and
    marker_scale used to be one flat value regardless, so rows with a wider zoom window
    showed oversized dots relative to rows with a tighter one (same root cause as the
    reference-panel fix in plot_ei_footprint_across_ndfs() -- see
    _span_normalized_marker_scale's docstring). Now marker_scale is rescaled PER ROW
    against the median zoom span across all rows in this mosaic, so dots represent a
    roughly consistent physical size everywhere, not a consistent screen-space size.

    UPDATED 2026-08-05 (Claude, per yas): "having the reference cell is crucial" -- if
    ref_ndf is given, an extra column is added for the reference chunk's own NDF
    (e.g. NDF 0), drawn in RED using analysis_chunk.vcd directly (no lookup in
    ndf_vcds/df_matches needed -- it's the row's own ref_cell_id, already loaded to
    compute that row's zoom window/scale anyway). Matches
    plot_ei_footprint_across_ndfs()'s existing red-reference-panel convention. Column
    position follows normal NDF sort order (descending, same as every other column),
    so it lands wherever ref_ndf's actual value falls -- not hardcoded to be first or
    last.

    UPDATED 2026-08-05 (Claude, per yas): "picking up like way too much of the cell" --
    _significant_electrode_mask() (shared with plot_ei_footprint_across_ndfs()) now
    uses a fixed electrode_threshold (default 5.0) matching yas's MATLAB map_ei_amr,
    instead of an adaptive std-based one -- see that function's docstring for the full
    reasoning and the units-matching verification. Rows whose reference cell doesn't
    clear min_significant_electrodes get their y-axis row label suffixed with '*' and
    are counted in the verbose summary print, rather than being silently drawn as if
    they were as reliable as any other row.

    UPDATED 2026-08-05 (Claude, per yas): two-tier draw in every panel (reference and
    matched alike) -- every electrode gets a small, fixed-size (s=2) gray context dot
    first, so the whole array's position/extent is always visible ("i still want to see
    the surrounding electrodes... so i know where it is on the array and what it
    spans"), THEN only the electrodes that clear electrode_threshold for that specific
    panel's own EI get a second, amplitude-scaled dot drawn on top (red for the
    reference column, black otherwise). Previously every electrode was drawn at an
    amplitude-scaled size floored at 0.5, so hundreds of below-threshold electrodes
    still showed a small-but-visible dot each -- fine for tightly-localized cells, but
    for wide-span rows (span-normalized marker_scale can multiply sizes up to ~9x) this
    carpeted the whole panel and made the footprint look like one solid blob rather
    than a shape with a real gradient. Significance is recomputed per-panel from that
    panel's own EI (not inherited from the reference row), matching
    plot_ei_footprint_across_ndfs()'s _draw_footprint helper.

    Cell type membership comes from get_cell_ids_of_type() (correlation_utils.py,
    unchanged) -- same case/separator-insensitive matching used everywhere else a
    cell_type string gets matched in this package.

    Parameters:
        analysis_chunk: the reference/parent AnalysisChunk that df_matches was computed
        from (i.e. the same one passed as ref_analysis_chunk to
        get_ei_matches_across_ndfs()). Must have .vcd (used as the per-row reference EI
        source, same as plot_ei_footprint_across_ndfs()'s ref_vcd).

        df_matches, ndf_vcds: outputs of get_ei_matches_across_ndfs().

        cell_type (str): which cell type to make a mosaic of, e.g. 'off/brisk transient'.

        ndf_values (list or None): which NDFs to show as columns -- must be keys
        already present in ndf_vcds. Default None uses every NDF in ndf_vcds, sorted
        highest-first (dimmest first, matching plot_ei_footprint_across_ndfs'
        reference-figure ordering).

        ref_ndf (float or None): the reference chunk's own NDF value (the third return
        value of get_ei_matches_across_ndfs()) -- if given, adds one more column
        showing each row's reference-chunk footprint in red. None (default) omits it.

        typing_file (str or None): passed through to get_cell_ids_of_type(). Default
        None auto-picks the first classification file.

        electrode_threshold, min_significant_electrodes, zoom_padding_frac,
        marker_scale: same meaning as plot_ei_footprint_across_ndfs(), just computed
        per-row instead of once overall. marker_scale defaults smaller here (120 vs.
        250) since panels are small.

        panel_size (float): width/height of each square panel, in inches. Default 1.7
        (small, for a dense "mosaic" look across many rows).

        verbose (bool): print how many cells of this type / matched panels were found,
        and how many rows didn't meet min_significant_electrodes. Default True.

    Returns:
        fig: one figure, len(cell_ids) rows x len(ndf_values) columns.
    """
    from retinanalysis.utils.correlation_utils import get_cell_ids_of_type

    cell_ids = get_cell_ids_of_type(analysis_chunk, cell_type, typing_file=typing_file, verbose=verbose)
    if len(cell_ids) == 0:
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.set_title(f'{cell_type!r}\nno cells found')
        ax.axis('off')
        return fig

    if ndf_values is None:
        ndf_values = sorted(ndf_vcds.keys(), reverse=True)
    else:
        missing = [v for v in ndf_values if v not in ndf_vcds]
        if missing:
            print(f'NDF value(s) {missing} not in ndf_vcds (available: {sorted(ndf_vcds.keys())}) -- skipping those.')
        ndf_values = [v for v in ndf_values if v in ndf_vcds]
    if not ndf_values and ref_ndf is None:
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.set_title('No valid NDF values found in ndf_vcds')
        ax.axis('off')
        return fig

    # Reference column (if requested) is just another column value, sorted into place
    # like any other NDF -- not hardcoded first or last.
    col_values = sorted(set(ndf_values) | ({ref_ndf} if ref_ndf is not None else set()), reverse=True)

    n_rows = len(cell_ids)
    n_cols = len(col_values)

    # PASS 1: compute each row's own zoom window (xlim/ylim) and span BEFORE drawing
    # anything, so a shared median span is available to normalize marker sizes against
    # (_span_normalized_marker_scale) -- otherwise a cell with a widely-spread
    # footprint and a cell with a tightly localized one would each use the same flat
    # marker_scale and end up looking wildly different in dot size. Per yas: "make the
    # squares all the same size some are big and some are tiny."
    row_data = []
    n_marginal_rows = 0
    for ref_cell_id in cell_ids:
        ref_ei = analysis_chunk.vcd.get_ei_for_cell(ref_cell_id).ei
        ref_electrode_map = analysis_chunk.vcd.get_electrode_map()
        ref_amp = np.max(np.abs(ref_ei), axis=1)
        ref_max_amp = ref_amp.max() if ref_amp.max() > 0 else 1.0
        sig_mask, enough_electrodes = _significant_electrode_mask(
            ref_ei, electrode_threshold, min_significant_electrodes,
        )
        if not sig_mask.any():
            top_n = min(20, len(ref_amp))
            sig_mask = np.zeros_like(sig_mask)
            sig_mask[np.argsort(ref_amp)[::-1][:top_n]] = True
        if not enough_electrodes:
            n_marginal_rows += 1
        sig_coords = ref_electrode_map[sig_mask]
        x_min, y_min = sig_coords.min(axis=0)
        x_max, y_max = sig_coords.max(axis=0)
        x_pad = max((x_max - x_min) * zoom_padding_frac, 1.0)
        y_pad = max((y_max - y_min) * zoom_padding_frac, 1.0)
        xlim = (x_min - x_pad, x_max + x_pad)
        ylim = (y_min - y_pad, y_max + y_pad)
        span = max(xlim[1] - xlim[0], ylim[1] - ylim[0])
        row_data.append(dict(
            ref_cell_id=ref_cell_id, ref_ei=ref_ei, ref_electrode_map=ref_electrode_map,
            ref_amp=ref_amp, ref_max_amp=ref_max_amp, xlim=xlim, ylim=ylim, span=span,
            enough_electrodes=enough_electrodes,
        ))

    median_span = float(np.median([r['span'] for r in row_data]))

    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(panel_size * n_cols, panel_size * n_rows), squeeze=False,
    )

    n_matched_total = 0
    for i, r in enumerate(row_data):
        ref_cell_id = r['ref_cell_id']
        ref_electrode_map = r['ref_electrode_map']
        ref_amp = r['ref_amp']
        ref_max_amp = r['ref_max_amp']
        xlim, ylim = r['xlim'], r['ylim']
        row_marker_scale = _span_normalized_marker_scale(marker_scale, r['span'], median_span)
        cell_matches = df_matches[df_matches['ref_cell_id'] == ref_cell_id].set_index('NDF')
        # Row's own significant-electrode mask (recomputed from ref_ei, already loaded
        # in pass 1) -- reused for the reference column below.
        ref_sig_mask, _ = _significant_electrode_mask(r['ref_ei'], electrode_threshold, min_significant_electrodes)

        for j, col_ndf in enumerate(col_values):
            ax = axes[i, j]
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_aspect('equal')

            if ref_ndf is not None and col_ndf == ref_ndf:
                # The reference chunk's own footprint for this row's cell -- already
                # loaded above (ref_amp/ref_electrode_map), no lookup needed.
                # UPDATED 2026-08-05 (Claude, per yas): two-tier draw -- small fixed
                # gray context dots for every electrode ("i still want to see the
                # surrounding electrodes... so i know where it is on the array and
                # what it spans"), amplitude-scaled red dots only for electrodes
                # clearing electrode_threshold. Was previously ALL electrodes at an
                # amplitude-scaled size, which packed hundreds of near-invisible dots
                # into wide-span rows and made them look like one solid blob.
                ax.scatter(ref_electrode_map[:, 0], ref_electrode_map[:, 1], s=2, color='0.75')
                sizes = np.clip(
                    row_marker_scale * (ref_amp[ref_sig_mask] / ref_max_amp), 0.5, row_marker_scale
                )
                ax.scatter(
                    ref_electrode_map[ref_sig_mask, 0], ref_electrode_map[ref_sig_mask, 1],
                    s=sizes, color='darkred', alpha=0.85,
                )
                ax.set_title(f'NDF {col_ndf:g}\n{ref_cell_id} (ref)', fontsize=6, color='darkred')
            elif col_ndf not in cell_matches.index:
                ax.set_title(f'NDF {col_ndf:g}\nno match', fontsize=6, color='gray')
            else:
                matched_cell_id = int(cell_matches.loc[col_ndf, 'matched_cell_id'])
                corr = cell_matches.loc[col_ndf, 'corr']
                vcd = ndf_vcds[col_ndf]
                ei = vcd.get_ei_for_cell(matched_cell_id).ei
                electrode_map = vcd.get_electrode_map()
                amp = np.max(np.abs(ei), axis=1)
                panel_sig_mask, _ = _significant_electrode_mask(ei, electrode_threshold, min_significant_electrodes)
                ax.scatter(electrode_map[:, 0], electrode_map[:, 1], s=2, color='0.75')
                sizes = np.clip(
                    row_marker_scale * (amp[panel_sig_mask] / ref_max_amp), 0.5, row_marker_scale
                )
                ax.scatter(
                    electrode_map[panel_sig_mask, 0], electrode_map[panel_sig_mask, 1],
                    s=sizes, color='k', alpha=0.85,
                )
                corr_str = f'{corr:.2f}' if corr is not None else '?'
                ax.set_title(f'NDF {col_ndf:g}\n{matched_cell_id} (r={corr_str})', fontsize=6)
                n_matched_total += 1

            if j == 0:
                # '*' flags rows whose reference cell didn't clear
                # min_significant_electrodes -- a marginal/weak cell, not necessarily a
                # bad match, but worth a second look rather than trusting it the same
                # as every other row.
                marginal_flag = '' if r['enough_electrodes'] else ' *'
                ax.set_ylabel(f'cell {ref_cell_id}{marginal_flag}', fontsize=7, rotation=0, ha='right', va='center')

    if verbose:
        n_data_cols = len(ndf_values)  # excludes the reference column from the "matched" denominator
        ref_note = ' + 1 reference column' if ref_ndf is not None else ''
        marginal_note = f' ({n_marginal_rows} row(s) marked * -- < {min_significant_electrodes} sig. electrodes)' if n_marginal_rows else ''
        print(
            f'{cell_type!r}: {len(cell_ids)} cell(s) x {n_data_cols} NDF(s){ref_note}{marginal_note}, '
            f'{n_matched_total} of {len(cell_ids) * n_data_cols} panel(s) matched.'
        )

    fig.suptitle(f'{cell_type} EI footprints (rows=cells, cols=NDFs, red=reference)', fontsize=12)
    fig.tight_layout(rect=[0.03, 0, 1, 0.97])
    return fig
