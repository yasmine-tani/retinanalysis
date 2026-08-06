# NEW 2026-07-28 (Claude, per yas): tuning-curve analysis for grating-based protocols
# (contrast response, direction/orientation selectivity). Nothing in this package
# supported these before -- D_REGEN_FXNS in classes/stim.py only has regen functions
# for SpatialNoise, PresentImages, and DovesMovie, and there was no F1/DSI/OSI code
# anywhere. This module doesn't need stimulus regen at all: F1/DSI/OSI only need spike
# timing (via ResponseBlock.bin_spike_times_at_rate) and the stimulus parameters
# already stored in df_epochs['epoch_parameters'] (orientation, contrast,
# temporalFrequency, etc.), which are protocol-agnostic.
#
# All three functions below were unit-tested against synthetic data with known ground
# truth before being wired into any notebook -- see
# changes/grating_and_contrast_demos_notes.md for what was checked.

import numpy as np
import pandas as pd
from typing import Optional, Dict, Tuple, List
from scipy.optimize import curve_fit


def compute_f1_f0(
    rate: np.ndarray,
    bin_rate: float,
    stim_freq: float,
) -> Tuple[float, float]:
    """
    Compute the F0 (mean/DC) and F1 (fundamental Fourier amplitude at stim_freq)
    components of a firing-rate trace, e.g. the response to a drifting grating.

    Parameters:
        rate (np.ndarray): 1D firing-rate (or spike-count) trace over the stimulus
        period only -- exclude preTime/tailTime before calling this (e.g. slice
        binned_spikes to the stimTime window first).

        bin_rate (float): sampling rate of `rate`, in Hz (bins per second). This
        should match whatever bin_rate you passed to bin_spike_times_at_rate().

        stim_freq (float): the drifting grating's temporal frequency, in Hz -- this
        is the frequency F1 is extracted at (usually epoch_parameters['temporalFrequency']).

    Returns:
        f0 (float): mean of the rate trace (DC component), same units as `rate`.
        f1 (float): amplitude of the Fourier component nearest stim_freq, same
        units as `rate` (e.g. Hz, if `rate` was in Hz / b_count=False).
    """
    rate = np.asarray(rate, dtype=float)
    n = len(rate)
    if n == 0:
        return 0.0, 0.0

    f0 = float(np.mean(rate))

    fft_vals = np.fft.rfft(rate - f0)
    freqs = np.fft.rfftfreq(n, d=1.0 / bin_rate)

    idx = int(np.argmin(np.abs(freqs - stim_freq)))
    # Amplitude normalization for a real signal's one-sided FFT: 2/n * |X[k]|
    f1 = float(2.0 / n * np.abs(fft_vals[idx]))

    return f0, f1


def compute_f1_f0_from_spikes(
    spike_times: np.ndarray,
    stim_freq: float,
    duration_s: float,
) -> Tuple[float, float]:
    """
    Compute F0 (mean rate) and F1 (fundamental Fourier amplitude at stim_freq)
    directly from raw spike times, with no binning. This is the direct
    spike-time vector-sum method (matches yas's lab's existing MATLAB convention:
    phases = 2*pi*stim_freq*spike_time; f1 = 2*|sum(exp(i*phases))|/duration).

    This is mathematically the continuous-time version of what compute_f1_f0 does
    on a binned rate trace -- both estimate the same underlying quantity, this one
    without discretization error, at the cost of needing raw spike times rather
    than a pre-binned rate array. Verified against compute_f1_f0 on the same
    synthetic spike trains (see changes/ notes for the exact comparison) -- the two
    agree closely and are both unbiased across repeated trials.

    Parameters:
        spike_times (np.ndarray): spike times (in seconds) relative to the start
        of the analysis window (e.g. relative to stimulus onset, already excluding
        preTime/tailTime -- so 0 = start of the stimulus period).

        stim_freq (float): the drifting grating's temporal frequency, in Hz.

        duration_s (float): duration of the analysis window, in seconds (e.g. the
        trial's stimTime, in seconds).

    Returns:
        f0 (float): mean firing rate over the window, in Hz (spike count / duration).
        f1 (float): amplitude of the Fourier component at stim_freq, in Hz.
    """
    spike_times = np.asarray(spike_times, dtype=float)
    n = len(spike_times)
    f0 = float(n / duration_s) if duration_s > 0 else 0.0
    if n == 0:
        return f0, 0.0

    phases = 2 * np.pi * stim_freq * spike_times
    vector_sum = np.sum(np.exp(1j * phases))
    f1 = float(2.0 * np.abs(vector_sum) / duration_s)

    return f0, f1


def build_trial_response_table(
    df_epochs: "pd.DataFrame",
    response_block,
    protocol_name: str,
    condition_keys: List[str],
    stim_freq_key: str = "temporalFrequency",
) -> "pd.DataFrame":
    """
    NEW 2026-07-29 (Claude, per yas): tidy per-(cell, trial) response table for a
    single stimulus protocol, working for BOTH periodic stimuli (e.g. drifting
    gratings, where F1 is meaningful) and non-periodic stimuli (e.g. flash,
    static spots, where only mean firing rate is meaningful). Built for
    demos/7_contrast_response_demo.ipynb's grating/spot/flash sections to share
    one extraction+verification path instead of three separate copies.

    For every epoch matching protocol_name, and every cell in response_block:
      - mean_rate (Hz): spike count in the stimulus window (stimTime) / stimTime.
      - baseline_rate (Hz): spike count in a window taken from the END of the
        pre-stimulus period (immediately before stimulus onset), of length
        min(preTime, stimTime), divided by that window's duration -- this is
        yas's chosen noise-subtraction convention (spontaneous rate from the
        pre-stimulus window), applied per-trial, per-cell. If preTime is 0, this
        (and everything derived from it) is 0.
      - mean_rate_noise_sub (Hz): mean_rate - baseline_rate. Can be negative (a
        trial with less activity than its own baseline estimate) -- left
        un-clipped so it stays usable for averaging/statistics downstream.
      - f0, f1, noise_f1, f1_noise_sub (Hz): only computed when epoch_parameters
        has a stim_freq_key entry that isn't None/0 for that epoch, i.e. only for
        periodic stimuli. f1 is computed via compute_f1_f0_from_spikes on the
        stimulus-window spikes; noise_f1 the same way on the same pre-stimulus
        baseline window used for baseline_rate, at the same frequency; f1_noise_sub
        = f1 - noise_f1. For non-periodic epochs, all four of these columns are
        NaN for that row (mean_rate-based columns are always computed regardless).

        CAVEAT added 2026-07-30 (Claude, per yas -- grating CRF/rasters "looked
        off"): noise_f1/f1_noise_sub have a real statistical bias and should NOT
        be treated as the default/primary CRF measure. compute_f1_f0_from_spikes's
        vector-sum F1 estimate has a noise floor that scales like ~1/sqrt(window
        duration) -- confirmed numerically (synthetic pure-Poisson, non-modulated
        spiking at a fixed rate: mean apparent F1 over a 0.25s window came out
        ~4.7x higher than the SAME rate's F1 over a 4.0s window, purely from
        short-window sampling noise, no real periodicity). Since noise_window_s =
        min(preTime, stimTime) is very short whenever preTime is short (e.g. 250ms
        pre-stimulus, common for a 4s grating trial), noise_f1 comes out inflated
        relative to the real stimulus-window f1, making f1_noise_sub come out
        strongly (and spuriously) NEGATIVE for essentially every cell/condition --
        this is exactly what happened in yas's real grating data (f1 ~2-4.5 Hz,
        noise_f1 ~11-12 Hz, f1_noise_sub ~ -7 to -11 Hz for every contrast).
        f1_noise_sub was never something yas's own MATLAB CRF scripts computed --
        none of the three versions she shared subtract any baseline from F1, they
        all plot raw F1 directly -- so this was a gap-filling addition on my part,
        not something she asked for or confirmed, and it turns out to be
        mis-behaved for short preTime windows. mean_rate_noise_sub does NOT have
        this problem (a plain spike-count/duration rate estimate isn't biased by
        short windows the way a short-window Fourier vector-sum is), so that
        stays fine to use for spot/flash. The f0/f1/noise_f1/f1_noise_sub columns
        are still computed and left in the output (useful for inspection / a
        future debiased version), but demos/7_contrast_response_demo.ipynb's
        grating section now defaults to plotting raw 'f1', not 'f1_noise_sub',
        matching yas's own scripts. Revisit noise_f1's estimator (e.g. only
        computing it when the noise window spans enough stim_freq cycles to be
        meaningful) if a baseline-subtracted F1 measure turns out to be needed.
      - condition_keys columns: whatever epoch_parameters keys you ask for (e.g.
        ['contrast']), pulled directly with no assumption about which keys exist
        for which protocol -- this is why protocol_name/condition_keys/
        stim_freq_key are all arguments here rather than hardcoded, so the same
        function works for gratings, spots, and flashes without needing to know
        their exact parameter sets in advance.

    Uses raw spike times (response_block.df_spike_times) directly, not a
    pre-binned rate trace -- the direct spike-time method (see
    compute_f1_f0_from_spikes) is used here rather than the binned-FFT
    compute_f1_f0, because the noise-window duration doesn't necessarily land on
    a clean bin boundary. response_block.bin_spike_times_at_rate() does NOT need
    to have been called before this.

    Parameters:
    df_epochs (pandas DataFrame): from stim_block.df_epochs.

    response_block: an MEAResponseBlock/ResponseBlock, providing cell_ids,
    n_epochs, and df_spike_times.

    protocol_name (str): exact protocol_name to filter df_epochs to.

    condition_keys (List[str]): epoch_parameters keys to pull into their own
    columns (e.g. ['contrast']).

    stim_freq_key (str): epoch_parameters key giving the stimulus's temporal
    frequency in Hz, used to decide whether a given epoch is periodic. Default
    'temporalFrequency'. If this key is absent, None, or 0 for an epoch, that
    epoch's f0/f1/noise_f1/f1_noise_sub come out as NaN.

    Returns:
    df_trials (pandas DataFrame): one row per (cell, epoch) matching
    protocol_name, with the columns described above.
    """
    spike_times_by_cell = response_block.df_spike_times.set_index("cell_id")["spike_times"]
    cell_ids = response_block.cell_ids

    rows = []
    for j_epoch in range(response_block.n_epochs):
        row = df_epochs.iloc[j_epoch]
        if row["protocol_name"] != protocol_name:
            continue

        params = row["epoch_parameters"]
        pre_time_s = row["preTime"] / 1000.0
        stim_time_s = row["stimTime"] / 1000.0
        stim_freq = params.get(stim_freq_key)
        is_periodic = stim_freq is not None and stim_freq > 0

        noise_window_s = min(pre_time_s, stim_time_s)
        noise_start_s = pre_time_s - noise_window_s  # relative to trial start

        for cell_id in cell_ids:
            trial_spikes_ms = spike_times_by_cell.loc[cell_id][j_epoch]
            trial_spikes_s = (
                np.asarray(trial_spikes_ms, dtype=float) / 1000.0
                if trial_spikes_ms is not None and len(trial_spikes_ms) > 0
                else np.array([])
            )

            # --- stimulus-window response ---
            in_stim = (trial_spikes_s >= pre_time_s) & (
                trial_spikes_s < pre_time_s + stim_time_s
            )
            stim_spikes_s = trial_spikes_s[in_stim] - pre_time_s
            mean_rate = len(stim_spikes_s) / stim_time_s if stim_time_s > 0 else 0.0

            # --- pre-stimulus baseline/noise window (tail end of preTime) ---
            in_noise = (trial_spikes_s >= noise_start_s) & (trial_spikes_s < pre_time_s)
            noise_spikes_s = trial_spikes_s[in_noise] - noise_start_s
            baseline_rate = (
                len(noise_spikes_s) / noise_window_s if noise_window_s > 0 else 0.0
            )

            mean_rate_noise_sub = mean_rate - baseline_rate

            if is_periodic:
                f0, f1 = compute_f1_f0_from_spikes(stim_spikes_s, stim_freq, stim_time_s)
                if noise_window_s > 0:
                    _, noise_f1 = compute_f1_f0_from_spikes(
                        noise_spikes_s, stim_freq, noise_window_s
                    )
                else:
                    noise_f1 = 0.0
                f1_noise_sub = f1 - noise_f1
            else:
                f0 = f1 = noise_f1 = f1_noise_sub = np.nan

            row_dict = {
                "cell_id": cell_id,
                "epoch_index": j_epoch,
                "mean_rate": mean_rate,
                "baseline_rate": baseline_rate,
                "mean_rate_noise_sub": mean_rate_noise_sub,
                "f0": f0,
                "f1": f1,
                "noise_f1": noise_f1,
                "f1_noise_sub": f1_noise_sub,
            }
            for key in condition_keys:
                row_dict[key] = params.get(key)
            rows.append(row_dict)

    return pd.DataFrame(rows)


def compute_dsi_osi(
    orientations_deg: np.ndarray,
    responses: np.ndarray,
) -> Dict[str, float]:
    """
    Vector-sum direction and orientation selectivity indices for a tuning curve.
    Standard circular-statistics definition -- flag if your lab uses a different
    convention and this should be swapped out.

    Direction selectivity (DSI) treats the response as 360-degree periodic (a cell
    responding equally to opposite directions has DSI near 0). Orientation
    selectivity (OSI) treats the response as 180-degree periodic (uses doubled
    angles), so a cell that responds equally to two opposite directions along one
    axis (but not the perpendicular axis) still gets a high OSI even though its
    DSI is ~0.

    Parameters:
        orientations_deg (np.ndarray): stimulus direction/orientation for each
        condition, in degrees.

        responses (np.ndarray): non-negative response magnitude (e.g. F1
        amplitude, or mean firing rate above baseline) for each condition, same
        length/order as orientations_deg.

    Returns:
        dict with keys:
            dsi (float): direction selectivity index, in [0, 1].
            preferred_direction_deg (float): vector-sum preferred direction, in
            [0, 360). NaN if all responses are 0.
            osi (float): orientation selectivity index, in [0, 1].
            preferred_orientation_deg (float): vector-sum preferred orientation,
            in [0, 180). NaN if all responses are 0.
    """
    orientations_deg = np.asarray(orientations_deg, dtype=float)
    responses = np.asarray(responses, dtype=float)

    if np.any(responses < 0):
        raise ValueError("responses must be non-negative for vector-sum DSI/OSI.")

    total = responses.sum()
    if total == 0:
        return {
            "dsi": 0.0,
            "preferred_direction_deg": float("nan"),
            "osi": 0.0,
            "preferred_orientation_deg": float("nan"),
        }

    theta = np.deg2rad(orientations_deg)

    # Direction selectivity: 360-degree periodic
    vec_dir = np.sum(responses * np.exp(1j * theta)) / total
    dsi = float(np.abs(vec_dir))
    pref_dir = float(np.rad2deg(np.angle(vec_dir)) % 360)

    # Orientation selectivity: 180-degree periodic (doubled angle)
    vec_ori = np.sum(responses * np.exp(1j * 2 * theta)) / total
    osi = float(np.abs(vec_ori))
    pref_ori = float((np.rad2deg(np.angle(vec_ori)) / 2) % 180)

    return {
        "dsi": dsi,
        "preferred_direction_deg": pref_dir,
        "osi": osi,
        "preferred_orientation_deg": pref_ori,
    }


def _naka_rushton(c, rmax, c50, n, baseline):
    c = np.asarray(c, dtype=float)
    c_safe = np.clip(c, 0, None)
    return baseline + rmax * (c_safe**n) / (c_safe**n + c50**n + 1e-12)


def fit_naka_rushton(
    contrasts: np.ndarray,
    responses: np.ndarray,
    p0: Optional[List[float]] = None,
) -> Dict[str, float]:
    """
    Fit a Naka-Rushton (hyperbolic ratio) function to a contrast-response curve:
        R(c) = baseline + Rmax * c^n / (c^n + c50^n)

    Parameters:
        contrasts (np.ndarray): contrast values (whatever units your responses
        vector matches -- e.g. Michelson contrast 0-1, matching this dataset's
        epoch_parameters['contrast'] values of 0.0-0.96).

        responses (np.ndarray): response magnitude (e.g. F1, normalized to the
        cell's own max) at each contrast value, same length/order as contrasts.

        p0 (Optional[List[float]]): initial guess [rmax, c50, n, baseline]. If
        None, a reasonable guess is derived from the data.

    Returns:
        dict with keys: rmax, c50, n, baseline (fitted parameters), and
        r_squared (goodness of fit).

    Raises:
        RuntimeError (from scipy.optimize.curve_fit) if the fit doesn't converge --
        this can happen with very noisy or non-saturating data, so check
        r_squared / the fitted curve visually rather than trusting params blindly.
    """
    contrasts = np.asarray(contrasts, dtype=float)
    responses = np.asarray(responses, dtype=float)

    if p0 is None:
        rmax0 = float(np.max(responses) - np.min(responses)) or 1.0
        c50_0 = (
            float(np.median(contrasts[contrasts > 0]))
            if np.any(contrasts > 0)
            else 0.1
        )
        p0 = [rmax0, c50_0, 2.0, float(np.min(responses))]

    bounds = ([0, 1e-6, 0.1, -np.inf], [np.inf, np.inf, 10, np.inf])

    popt, _ = curve_fit(
        _naka_rushton, contrasts, responses, p0=p0, bounds=bounds, maxfev=10000
    )
    rmax, c50, n, baseline = popt

    preds = _naka_rushton(contrasts, *popt)
    ss_res = np.sum((responses - preds) ** 2)
    ss_tot = np.sum((responses - np.mean(responses)) ** 2)
    r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    return {
        "rmax": float(rmax),
        "c50": float(c50),
        "n": float(n),
        "baseline": float(baseline),
        "r_squared": r_squared,
    }
