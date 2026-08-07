"""Shared response-extraction and plotting functions for the contrast-response demo
(demos/7_contrast_response_demo.ipynb -- grating/spot/flash contrast-response analysis).

Functions here call `ra.get_ndf_blocks_for_protocol`, `ra.find_datafile_for_protocol`,
`ra.create_mea_pipeline`, and `ra.build_trial_response_table` (all defined elsewhere in the
retinanalysis package). `import retinanalysis as ra` is done lazily inside the two functions
that need it (not at module level), because this module is itself imported by
retinanalysis/__init__.py -- a module-level `import retinanalysis` here would be a circular
import at package-init time. Same lazy-import pattern used in correlation_utils.py,
datajoint_utils.py, and vision_utils.py.

The full change history for this module lives in changes/grating_and_contrast_demos_notes.md
and changes/claude_changes_2026-07-28.txt, not here.
"""

import contextlib
import html
import io

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Human-readable, unit-labeled y-axis text for each response column
# build_trial_response_table can produce. Used by plot_crf/plot_crf_across_ndfs so every
# panel's y-axis says what's actually being plotted, not just the raw column name.
_RESPONSE_AXIS_LABELS = {
    'f1': 'F1 amplitude (Hz)',
    'f1_noise_sub': 'F1 amplitude, noise-subtracted (Hz)',
    'f0': 'F0 / mean rate (Hz)',
    'mean_rate': 'Mean firing rate (Hz)',
    'mean_rate_noise_sub': 'Mean firing rate, noise-subtracted (Hz)',
}

# Human-readable x-axis text for each condition_key these plots are called with.
_CONDITION_AXIS_LABELS = {
    'contrast': 'Contrast',
    'intensity': 'Intensity',
}


def _response_axis_label(col):
    """Y-axis label for a response column name, e.g. 'f1' -> 'F1 amplitude (Hz)',
    'mean_rate_noise_sub_norm' -> 'Mean firing rate, noise-subtracted (normalized)'.
    Falls back to a capitalized, underscore-stripped version of the column name for
    anything not in _RESPONSE_AXIS_LABELS.
    """
    is_norm = col.endswith('_norm')
    base = col[:-len('_norm')] if is_norm else col
    label = _RESPONSE_AXIS_LABELS.get(base, base.replace('_', ' ').capitalize())
    if is_norm:
        # Per-cell-normalized values are unitless (each cell scaled to its own max = 1),
        # so drop any trailing "(Hz)"-style unit before appending "(normalized)".
        label = label.split(' (')[0] + ' (normalized)'
    return label


def _condition_axis_label(condition_key):
    """X-axis label for a condition_key, e.g. 'contrast' -> 'Contrast'. Falls back to a
    capitalized, underscore-stripped version of condition_key for anything not in
    _CONDITION_AXIS_LABELS.
    """
    return _CONDITION_AXIS_LABELS.get(condition_key, condition_key.replace('_', ' ').capitalize())


@contextlib.contextmanager
def scrollable_prints(max_height_px=220):
    """Collapse everything printed to stdout OR stderr inside a `with scrollable_prints():`
    block into one small, scrollable HTML box, instead of it taking up unlimited vertical
    space in the notebook.

    Captures both streams because a lot of what shows up in this kind of verbose output
    isn't plain print() -- warnings (warnings.warn(), UserWarning, etc.) and library logging
    (e.g. DataJoint's own connection/status messages) default to stderr, not stdout. Only
    redirecting stdout left that output rendering outside the scroll box, defeating the
    point -- confirmed directly (yas: "that made like 1/4 of the bottom scrollable not the
    entire output").

    Matplotlib figures (or anything else IPython displays directly, e.g. dataframe repr via
    display()) are still NOT captured -- those don't go through stdout/stderr at all. Code
    that creates figures should run after the `with` block exits (see plot_crf_across_ndfs
    below: the NDF-loading loop -- prints only, no figures -- is inside `with
    scrollable_prints():`; the figure-creation loop right after it is not), so figures still
    render normally, full-size, un-scrolled.

    Uses plain HTML/CSS (a max-height + overflow-y div) rather than Jupyter's built-in
    per-cell "scrolled output" toggle, since that toggle's behavior isn't consistently
    scriptable across notebook frontends (JupyterLab, classic Notebook, VS Code's Jupyter
    extension). This renders identically everywhere.
    """
    from IPython.display import display, HTML

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield
    text = buf.getvalue()
    if text:
        display(HTML(
            '<div style="max-height:{h}px; overflow-y:auto; white-space:pre-wrap; '
            'font-family:monospace; font-size:12px; border:1px solid #ddd; '
            'padding:6px 8px; background:#fafafa; margin-bottom:4px;">{t}</div>'.format(
                h=max_height_px, t=html.escape(text)
            )
        ))


def scrollable_figure(fig, max_height_px=600, dpi=100):
    """
    NEW 2026-08-05 (Claude, per yas): displays a matplotlib figure inside a fixed-height,
    scrollable HTML box -- the figure equivalent of scrollable_prints() above, for
    mosaic-style figures (many small subplots) that can end up taller than the screen.

    scrollable_prints()'s own docstring already notes matplotlib figures aren't
    captured by stdout/stderr redirection at all, so they need a different mechanism.
    Earlier in this project, `cell.metadata['scrolled'] = True` (Jupyter's built-in
    per-cell "scrolled output" toggle) was tried for exactly this, then reverted: it
    scroll-boxes the WHOLE cell's output (including things that shouldn't be boxed) and
    isn't reliably honored across notebook frontends (JupyterLab/classic/VS Code) -- see
    scrollable_prints()'s docstring and changes/ for that history. This avoids both
    problems the same way scrollable_prints() does: plain HTML/CSS (a max-height +
    overflow-y div), scoped to just this one image, works identically everywhere.

    Renders fig to an in-memory PNG (fig.savefig into an io.BytesIO buffer),
    base64-encodes it, and displays it as an <img> inside the scrollable div via
    IPython.display. Closes fig afterward (plt.close(fig)) so Jupyter's normal
    end-of-cell auto-display doesn't ALSO render a second, un-scrolled copy of the same
    figure.

    Parameters:
        fig: the matplotlib Figure to display.

        max_height_px (int): max height of the scrollable box, in pixels. Default 600.

        dpi (int): resolution the figure is rendered at. Default 100.

    Returns:
        None -- displays directly, like IPython.display.display().
    """
    import base64
    from IPython.display import display, HTML

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode('ascii')
    display(HTML(
        '<div style="max-height:{h}px; overflow-y:auto; border:1px solid #ddd; '
        'margin-bottom:4px;"><img src="data:image/png;base64,{b64}" '
        'style="display:block;"/></div>'.format(h=max_height_px, b64=encoded)
    ))


def load_contrast_section(exp_name, contrast_search, protocol_name, condition_keys,
                           analysis_chunk_name, corr_cutoff=0.8, stim_freq_key='temporalFrequency',
                           manual_datafile_name=None, typing_chunk=None, default_ndf=0):
    """Finds the datafile for `protocol_name`, builds the pipeline, builds the tidy trial
    response table, and tags each row with its cell_type.

    Datafile selection: prefers whichever datafile actually ran this protocol at
    `default_ndf` (looked up via the real 'NDF' column from get_ndf_blocks_for_protocol, not
    a hardcoded mapping). Falls back to the earliest datafile by block_id
    (find_datafile_for_protocol) only if no datafile at default_ndf exists for this
    protocol, and prints which path was taken either way. Pass manual_datafile_name to skip
    auto-detection entirely.

    Returns (df_trials, spike_times_by_cell, df_epochs, datafile_name, ndf_used).
    """
    import retinanalysis as ra

    ndf_used = None
    if manual_datafile_name is not None:
        datafile_name = manual_datafile_name
    else:
        df_ndf_blocks = ra.get_ndf_blocks_for_protocol(exp_name, protocol_name, verbose=False)
        ndf_match = df_ndf_blocks[df_ndf_blocks['NDF'] == default_ndf]
        if len(ndf_match) > 0:
            datafile_name = ndf_match.iloc[0]['datafile_name']
            ndf_used = default_ndf
            print(f'Using NDF {default_ndf} datafile for {protocol_name}: {datafile_name}')
        else:
            datafile_name = ra.find_datafile_for_protocol(
                contrast_search, exp_name, protocol_name=protocol_name
            )
            available_ndfs = list(df_ndf_blocks['NDF']) if len(df_ndf_blocks) else []
            print(
                f'No NDF {default_ndf} datafile found for {protocol_name} -- available NDFs: '
                f'{available_ndfs}. Falling back to the earliest datafile by block_id instead: '
                f'{datafile_name}. Set MANUAL_DATAFILE_NAME_* or default_ndf to override.'
            )

    if datafile_name is None:
        raise ValueError(
            f'No {protocol_name} datafile found for {exp_name} -- '
            'pick a different exp_name, or set this section\'s MANUAL_DATAFILE_NAME.'
        )

    pipeline = ra.create_mea_pipeline(
        exp_name, datafile_name, analysis_chunk_name=analysis_chunk_name, corr_cutoff=corr_cutoff,
    )
    stim_block = pipeline.stim
    response_block = pipeline.resp
    df_epochs = stim_block.df_epochs

    print(f'{len(df_epochs)} epochs found for {exp_name} {datafile_name}')
    print('protocol_name(s) present:', df_epochs['protocol_name'].unique())
    matching = df_epochs[df_epochs['protocol_name'] == protocol_name]
    if len(matching) == 0:
        raise ValueError(f'No epochs with protocol_name == {protocol_name!r} found in {datafile_name}.')
    print(f'epoch_parameters keys for the first {protocol_name} epoch '
          '(VERIFY these match condition_keys/stim_freq_key below):')
    print(sorted(matching.iloc[0]['epoch_parameters'].keys()))

    df_trials = ra.build_trial_response_table(
        df_epochs, response_block, protocol_name, condition_keys, stim_freq_key=stim_freq_key
    )

    # cell_type comes from pipeline.resp.df_spike_times, which MEAPipeline computes via its
    # own EI-based cross-chunk cell mapping (match_dict, built by cluster_match) in
    # add_types_to_protocol() -- not a manual join against a separately-built cell_type_map,
    # since df_trials['cell_id'] are this protocol's own cell_ids from a different sorting
    # run than the reference/classification chunk, so a direct ID-based join wouldn't line
    # up. Cells that never EI-matched the reference chunk come through as 'Unmatched';
    # 'Unknown' means a cell DID match a reference cell, but that reference cell's
    # classification label was blank/unrecognized.
    cell_type_by_id = response_block.df_spike_times.set_index('cell_id')['cell_type']
    df_trials['cell_type'] = df_trials['cell_id'].map(cell_type_by_id).fillna('Unmatched')

    spike_times_by_cell = response_block.df_spike_times.set_index('cell_id')['spike_times']

    print(f'{len(df_trials)} (cell, trial) rows, {df_trials["cell_id"].nunique()} cells, '
          f'cell types present: {sorted(df_trials["cell_type"].unique())}')
    n_unmatched_rows = (df_trials['cell_type'] == 'Unmatched').sum()
    if n_unmatched_rows > 0:
        print(f'  ({n_unmatched_rows} / {len(df_trials)} rows are cells that did not EI-match '
              f'the reference chunk at corr_cutoff={corr_cutoff} -- try a lower corr_cutoff '
              'if this seems like too many, e.g. 0.7.)')

    # Cells can be lost at two separate points before ever showing up in a raster:
    #   1. The reference/classification chunk AnalysisChunk that create_mea_pipeline builds
    #      internally (pipeline.analysis_chunk) tries to load an EI for every cell and drops
    #      any cell whose EI computation fails -- before typing or cross-chunk matching even
    #      starts. This is a DIFFERENT AnalysisChunk instance than `typing_chunk` (built with
    #      include_ei=False to preview cell types without this drop), so counting from
    #      typing_chunk alone overcounts vs. what a section can actually use.
    #   2. cluster_match (cross-chunk EI matching, corr_cutoff above) can fail to map a cell
    #      that DID survive step 1, if its EI correlation to the target datafile doesn't
    #      clear corr_cutoff.
    # Printed per real (non-Unknown/Unmatched) type found in typing_chunk, if provided, so
    # it's not a guessing game which step lost a given cell.
    if typing_chunk is not None and hasattr(pipeline, 'analysis_chunk'):
        classification_files = [f for f in typing_chunk.typing_files if 'classification' in f.lower()]
        if classification_files:
            file_idx = typing_chunk.typing_files.index(classification_files[0])
            type_col = typing_chunk.df_cell_params[f'typing_file_{file_idx}'].values
            real_types = sorted(set(type_col) - {'Unknown', 'Unmatched'})
            print('  Cell-count funnel per type (raw classification file -> survived reference-chunk '
                  'EI computation -> survived cross-chunk EI match into this datafile):')
            for ct in real_types:
                raw_ids = set(typing_chunk.cell_ids[type_col == ct].tolist())
                ref_survived_ids = raw_ids & set(pipeline.analysis_chunk.cell_ids.tolist())
                matched_ids = {cid for cid in ref_survived_ids if cid in pipeline.match_dict}
                print(f'    {ct!r}: {len(raw_ids)} in file -> {len(ref_survived_ids)} survived '
                      f'reference-chunk EI -> {len(matched_ids)} matched into {datafile_name} '
                      f'at corr_cutoff={corr_cutoff}')

    return df_trials, spike_times_by_cell, df_epochs, datafile_name, ndf_used


def plot_crf_across_ndfs(exp_name, contrast_search, protocol_name, condition_key,
                          analysis_chunk_name, corr_cutoff, response_col, title_prefix,
                          typing_chunk=None, log_x=None, cell_types=None, show_sem=True):
    """Loops every NDF found for `protocol_name` (via `ra.get_ndf_blocks_for_protocol`, real
    database NDF values, not a hardcoded list) and calls load_contrast_section once per NDF
    -- the same function used by the single-NDF CRF cell and the NDF explorer cells.

    Produces one figure per real cell type: default (cell_types=None) auto-detects every
    real type present across the loaded NDFs, excluding 'Unknown'/'Unmatched' (same
    convention as plot_raster_overview_by_cell_type), and each figure's title names the cell
    type. Data is loaded once per NDF, not once per NDF per type -- per-type filtering
    happens after loading, since df_trials_ndf already carries a 'cell_type' column. Within
    each type's figure, every NDF is one line/color on shared axes.

    show_sem (default True): whether to draw SEM error bars on each NDF's line. With many
    NDFs overlaid on the same axes the error bars can make the plot busy -- set to False for
    just the mean lines/markers.

    Returns a dict of {cell_type: fig}.

    Reloads and re-matches cells at every NDF found (same per-NDF cost as running the NDF
    explorer once per NDF), so this can take a while with several NDFs -- progress prints
    collapse into one scrollable box via scrollable_prints().
    """
    import retinanalysis as ra

    if log_x is None:
        log_x = (condition_key == 'contrast')

    df_ndf_blocks = ra.get_ndf_blocks_for_protocol(exp_name, protocol_name)
    if len(df_ndf_blocks) == 0:
        print(f'No {protocol_name} blocks found for {exp_name} at any NDF.')
        return {}

    # Load each NDF ONCE (the expensive step -- rebuilds the pipeline and EI-matches cells),
    # not once per cell type. This loop is pure loading (prints only, no figures -- the
    # figure-creation loop is below, outside this `with` block), so it's wrapped in
    # scrollable_prints() to collapse the per-NDF progress output into one small scroll box.
    df_trials_by_ndf = {}
    with scrollable_prints():
        for _, row in df_ndf_blocks.iterrows():
            ndf_val = row['NDF']
            datafile_name = row['datafile_name']
            print(f'--- NDF {ndf_val} ({datafile_name}) ---')
            try:
                df_trials_ndf, _, _, _, _ = load_contrast_section(
                    exp_name, contrast_search, protocol_name, condition_keys=[condition_key],
                    analysis_chunk_name=analysis_chunk_name, corr_cutoff=corr_cutoff,
                    manual_datafile_name=datafile_name, typing_chunk=typing_chunk,
                )
                df_trials_by_ndf[ndf_val] = df_trials_ndf
            except Exception as e:
                print(f'  Skipping NDF {ndf_val}: {e}')

    if not df_trials_by_ndf:
        print('No NDF had usable data -- nothing plotted.')
        return {}

    if cell_types is None:
        all_types = set()
        for df in df_trials_by_ndf.values():
            all_types |= set(df['cell_type'].unique())
        cell_types = sorted(t for t in all_types if t not in ('Unknown', 'Unmatched'))

    ndf_vals = sorted(df_trials_by_ndf.keys())
    cmap = plt.get_cmap('viridis')
    colors = {ndf: cmap(i / max(1, len(ndf_vals) - 1)) for i, ndf in enumerate(ndf_vals)}

    figs = {}
    for ct in cell_types:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        fig.suptitle(f'{title_prefix} -- {ct}', fontsize=14)
        any_plotted = False
        # UPDATED 2026-08-06 (Claude, per yas): collected across every NDF plotted on
        # these shared axes, so the tick-setting below (non-log_x case) reflects every
        # real tested condition value seen, not just whichever NDF happened to be
        # plotted last.
        all_x_values = set()

        for ndf_val in ndf_vals:
            ct_trials = df_trials_by_ndf[ndf_val]
            ct_trials = ct_trials[ct_trials['cell_type'] == ct]
            if len(ct_trials) == 0:
                continue

            curves = ct_trials.groupby(['cell_id', condition_key])[response_col].mean().reset_index()
            if len(curves) == 0:
                continue

            pop = curves.groupby(condition_key)[response_col].agg(['mean', 'sem']).reset_index()
            x = pop[condition_key].values.astype(float)
            all_x_values.update(x.tolist())
            x_plot = (
                np.where(x == 0, x[x > 0].min() / 2 if (x > 0).any() else 0.005, x)
                if log_x else x
            )
            color = colors[ndf_val]
            axes[0].errorbar(x_plot, pop['mean'], yerr=(pop['sem'] if show_sem else None),
                              marker='o', capsize=3, color=color, label=f'NDF {ndf_val:g}')

            norm_rows = []
            for cell_id, grp in curves.groupby('cell_id'):
                m = grp[response_col].max()
                if m is None or not np.isfinite(m) or m == 0:
                    continue
                g2 = grp.copy()
                g2[response_col + '_norm'] = g2[response_col] / m
                norm_rows.append(g2)
            if norm_rows:
                norm_curves = pd.concat(norm_rows, ignore_index=True)
                pop_norm = norm_curves.groupby(condition_key)[response_col + '_norm'].agg(['mean', 'sem']).reset_index()
                axes[1].errorbar(x_plot, pop_norm['mean'], yerr=(pop_norm['sem'] if show_sem else None),
                                  marker='o', capsize=3, color=color, label=f'NDF {ndf_val:g}')

            any_plotted = True

        if not any_plotted:
            plt.close(fig)
            print(f'{ct}: no data at any NDF, skipping.')
            continue

        sem_suffix = ' +/- SEM' if show_sem else ''
        panel_titles = [f'{response_col} (raw, population mean{sem_suffix})',
                        f'{response_col} (per-cell normalized{sem_suffix})']
        panel_cols = [response_col, response_col + '_norm']
        for ax, panel_title, col in zip(axes, panel_titles, panel_cols):
            ax.set_xlabel(_condition_axis_label(condition_key))
            ax.set_ylabel(_response_axis_label(col))
            ax.set_title(panel_title)
            ax.grid(True, alpha=0.3)
            if log_x:
                ax.set_xscale('log')
            else:
                # Same "clear 0-1 contrast ticks" convention as plot_crf: tick every
                # real tested value, fix the axis to the full [0, 1] span specifically
                # for condition_key == 'contrast' (a value that's conceptually bounded
                # there), rather than trusting matplotlib's default linear locator.
                if all_x_values:
                    ax.set_xticks(sorted(all_x_values))
                if condition_key == 'contrast':
                    ax.set_xlim(0, 1)
            ax.legend(fontsize=8)
        fig.tight_layout()
        figs[ct] = fig

    return figs


def plot_crf(df_trials, condition_key, response_col, raw_response_col, title, log_x=None, show_noise_sub=True):
    """Raw response (row 1) vs. noise-subtracted response (row 2, only if
    show_noise_sub=True) x non-normalized vs. per-cell-normalized (each cell's own max
    set to 1) columns. Population mean +/- SEM across cells at each condition level.

    show_noise_sub (bool): set False when response_col's noise-subtracted version isn't
    reliable (e.g. grating F1 -- see the CAVEAT in build_trial_response_table's docstring
    about noise_f1's short-window statistical bias). Default True."""
    if log_x is None:
        log_x = (condition_key == 'contrast')

    nrows = 2 if show_noise_sub else 1
    fig, axes = plt.subplots(nrows, 2, figsize=(11, 4.5 * nrows), squeeze=False)
    fig.suptitle(title, fontsize=14)

    def summarize(col):
        return df_trials.groupby(['cell_id', condition_key])[col].mean().reset_index()

    def normalize(curves, col):
        out = []
        for cell_id, grp in curves.groupby('cell_id'):
            m = grp[col].max()
            if m is None or not np.isfinite(m) or m == 0:
                continue
            g2 = grp.copy()
            g2[col + '_norm'] = g2[col] / m
            out.append(g2)
        if not out:
            return pd.DataFrame(columns=list(curves.columns) + [col + '_norm'])
        return pd.concat(out, ignore_index=True)

    raw_curves = summarize(raw_response_col)
    raw_norm = normalize(raw_curves, raw_response_col)

    panels = [
        (axes[0, 0], raw_curves, raw_response_col, f'{raw_response_col} (raw)'),
        (axes[0, 1], raw_norm, raw_response_col + '_norm', f'{raw_response_col} (normalized)'),
    ]

    if show_noise_sub:
        sub_curves = summarize(response_col)
        sub_norm = normalize(sub_curves, response_col)
        panels += [
            (axes[1, 0], sub_curves, response_col, f'{response_col} (noise-subtracted)'),
            (axes[1, 1], sub_norm, response_col + '_norm', f'{response_col} (noise-subtracted, normalized)'),
        ]

    for ax, curves, col, panel_title in panels:
        if len(curves) == 0 or col not in curves.columns:
            ax.set_title(panel_title + ' -- no data')
            continue
        pop = curves.groupby(condition_key)[col].agg(['mean', 'sem']).reset_index()
        x = pop[condition_key].values.astype(float)
        if log_x:
            x_plot = np.where(x == 0, x[x > 0].min() / 2 if (x > 0).any() else 0.005, x)
            ax.set_xscale('log')
        else:
            x_plot = x
            # UPDATED 2026-08-06 (Claude, per yas): "clear 0-1 contrast ticks instead"
            # -- log_x=False previously just fell back to matplotlib's default linear
            # tick placement, which is fine but doesn't guarantee a tick at every real
            # tested contrast level. Explicitly tick every actual value present in the
            # data instead, so the axis reads the real tested contrasts rather than an
            # arbitrary round-number grid. For condition_key == 'contrast' specifically
            # (a value that's conceptually bounded in [0, 1]), also fix the axis range
            # to the full [0, 1] span rather than autoscaling tightly to whatever the
            # max tested contrast happened to be.
            ax.set_xticks(sorted(set(x)))
            if condition_key == 'contrast':
                ax.set_xlim(0, 1)
        ax.errorbar(x_plot, pop['mean'], yerr=pop['sem'], marker='o', capsize=3)
        ax.set_xlabel(_condition_axis_label(condition_key))
        ax.set_ylabel(_response_axis_label(col))
        ax.set_title(panel_title)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def _raster_for_cell(ax, cell_id, df_trials_cell, spike_times_by_cell, df_epochs, condition_key, gap_size=2, markersize=1.5):
    """Draws one cell's raster: dot markers per spike (not eventplot tick lines), with an
    explicit blank-row gap (gap_size rows, default 2) between condition blocks, a y-tick
    label centered on each condition block's row range, and the x-axis cropped to
    [0, stimTime] with spikes shifted to be relative to stimulus onset (0 = start of
    stimTime) -- spikes outside the stimulus window aren't plotted. Vertical dotted
    gridlines every 0.5s give a rhythm reference for periodic stimuli.
    """
    if len(df_trials_cell) == 0:
        ax.set_title(f'Cell {cell_id}: no trials')
        return

    example_row = df_epochs.iloc[df_trials_cell.iloc[0]['epoch_index']]
    pre_time_s = example_row['preTime'] / 1000.0
    stim_time_s = example_row['stimTime'] / 1000.0

    condition_values = sorted(df_trials_cell[condition_key].unique())

    current_row = 0
    y_ticks = []
    y_labels = []

    for cond_val in condition_values:
        cond_trials = df_trials_cell[df_trials_cell[condition_key] == cond_val]
        start_row = current_row
        for _, row in cond_trials.iterrows():
            j_epoch = row['epoch_index']
            trial_spikes_ms = spike_times_by_cell.loc[cell_id][j_epoch]
            ts = (
                np.asarray(trial_spikes_ms, dtype=float) / 1000.0
                if trial_spikes_ms is not None and len(trial_spikes_ms) > 0
                else np.array([])
            )
            in_stim = (ts >= pre_time_s) & (ts < pre_time_s + stim_time_s)
            aligned = ts[in_stim] - pre_time_s
            if len(aligned) > 0:
                ax.plot(aligned, np.full(len(aligned), current_row), '.', color='k', markersize=markersize, markeredgewidth=0)
            current_row += 1
        if current_row > start_row:
            y_ticks.append((start_row + current_row - 1) / 2)
            y_labels.append(f'{condition_key}={cond_val}')
        current_row += gap_size

    if stim_time_s > 0:
        ax.set_xlim(0, stim_time_s)
        sec = 0.0
        while sec <= stim_time_s:
            ax.axvline(sec, linestyle=':', color=(0.8, 0.8, 0.8), linewidth=0.7)
            sec += 0.5
    ax.set_ylim(-1, max(current_row - gap_size, 1))
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels, fontsize=7)
    ax.set_title(f'Cell {cell_id}')
    ax.set_xlabel('Time (s)')


def plot_raster_overview_by_cell_type(df_trials, spike_times_by_cell, df_epochs, condition_key, response_col,
                                       cell_types=None, max_cells_per_page=4, sort_by_response=True,
                                       markersize=1.5):
    """One figure per page per cell type (each a separate output, since Jupyter's inline
    backend displays every figure created during a cell's execution -- scrolling through the
    notebook naturally pages through them), max_cells_per_page cells per figure (default 4,
    2x2). Every cell of every type is shown, paginated the same way
    plot_rasters_for_cell_type paginates a single type -- a type with, say, 14 cells produces
    4 separate figures (2x2, 2x2, 2x2, 2x1) rather than being truncated.

    Returns a dict of {cell_type: [fig_page_1, fig_page_2, ...]}.
    """
    if cell_types is None:
        # 'Unknown' and 'Unmatched' are bookkeeping labels, not real cell types (see the
        # cell_type-join comment in load_contrast_section) -- excluding them is equivalent
        # to "only plot types that matched cell_types.csv". Pass cell_types=[...] explicitly
        # to widen this (e.g. to also see 'Unmatched' cells).
        cell_types = sorted(
            ct for ct in df_trials['cell_type'].unique() if ct not in ('Unknown', 'Unmatched')
        )

    figs = {}
    for ct in cell_types:
        ct_trials = df_trials[df_trials['cell_type'] == ct]
        if len(ct_trials) == 0:
            print(f'{ct}: no trials, skipping.')
            continue

        if sort_by_response:
            cells = list(
                ct_trials.groupby('cell_id')[response_col].mean().sort_values(ascending=False).index
            )
        else:
            cells = sorted(ct_trials['cell_id'].unique())
        n_total = len(cells)

        type_figs = []
        n_pages = int(np.ceil(n_total / max_cells_per_page))
        for page in range(n_pages):
            page_cells = cells[page * max_cells_per_page:(page + 1) * max_cells_per_page]
            ncols = min(2, len(page_cells))
            nrows = int(np.ceil(len(page_cells) / ncols))
            fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows), squeeze=False)
            for i, cell_id in enumerate(page_cells):
                ax = axes[i // ncols, i % ncols]
                cell_trials = df_trials[df_trials['cell_id'] == cell_id]
                _raster_for_cell(ax, cell_id, cell_trials, spike_times_by_cell, df_epochs, condition_key,
                                 markersize=markersize)
            for j in range(len(page_cells), nrows * ncols):
                axes[j // ncols, j % ncols].axis('off')
            page_label = f' (page {page + 1}/{n_pages})' if n_pages > 1 else ''
            fig.suptitle(f'{ct} (n={n_total} cell(s)){page_label}')
            fig.tight_layout()
            type_figs.append(fig)

        figs[ct] = type_figs

    return figs


def plot_rasters_for_cell_type(df_trials, spike_times_by_cell, df_epochs, condition_key, selected_cell_type,
                                max_cells_per_page=4, markersize=1.5):
    """Paginated -- max_cells_per_page cells per figure, default 4 (2x2) -- instead of
    putting every cell of the type into one grid. Returns a list of figures, one per page."""
    cells = sorted(df_trials[df_trials['cell_type'] == selected_cell_type]['cell_id'].unique())
    if len(cells) == 0:
        print(f'No cells of type {selected_cell_type!r} found.')
        return []

    figs = []
    n_pages = int(np.ceil(len(cells) / max_cells_per_page))
    for page in range(n_pages):
        page_cells = cells[page * max_cells_per_page:(page + 1) * max_cells_per_page]
        ncols = min(2, len(page_cells))
        nrows = int(np.ceil(len(page_cells) / ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows), squeeze=False)
        for i, cell_id in enumerate(page_cells):
            ax = axes[i // ncols, i % ncols]
            cell_trials = df_trials[df_trials['cell_id'] == cell_id]
            _raster_for_cell(ax, cell_id, cell_trials, spike_times_by_cell, df_epochs, condition_key,
                             markersize=markersize)
        for j in range(len(page_cells), nrows * ncols):
            axes[j // ncols, j % ncols].axis('off')
        page_label = f' (page {page + 1}/{n_pages})' if n_pages > 1 else ''
        fig.suptitle(f'All cells of type {selected_cell_type!r} (n={len(cells)}){page_label}')
        fig.tight_layout()
        figs.append(fig)

    return figs


def compute_cell_psth(cell_id, cell_trials, spike_times_by_cell, df_epochs, bin_size_ms=10.0):
    """
    NEW 2026-08-05 (Claude, per yas): one cell's own trial-averaged PSTH (Hz curve over
    time), for a sanity check on a CRF's response shape -- separate from
    compute_f1_f0_from_spikes()'s (tuning.py) unbinned spike-phase F1 method, which
    isn't touched by this. Binning here is only for the plot.

    Pools every trial in cell_trials' spikes (already expected to be filtered to one
    cell_id and one condition value by the caller) into bin_size_ms bins across
    [0, stimTime), then divides by (n_trials * bin_width_s) to get a rate in Hz. Spike
    time alignment (relative to stim onset, cropped to the stimulus window) matches
    _raster_for_cell()'s convention exactly, so a PSTH bin lines up with that same
    cell's raster above/below it.

    Parameters:
        cell_id: the cell's ID (used to index into spike_times_by_cell).

        cell_trials (DataFrame): rows of df_trials already filtered to this cell_id (and
        typically one condition value -- the caller loops over condition values).

        spike_times_by_cell, df_epochs: same objects load_contrast_section() returns.

        bin_size_ms (float): PSTH bin width in ms. Default 10.0.

    Returns:
        (bin_centers_s, rate_hz): both numpy arrays, or (None, None) if cell_trials is
        empty or stimTime can't be determined / is <= 0.
    """
    if len(cell_trials) == 0:
        return None, None

    example_row = df_epochs.iloc[cell_trials.iloc[0]['epoch_index']]
    pre_time_s = example_row['preTime'] / 1000.0
    stim_time_s = example_row['stimTime'] / 1000.0
    if stim_time_s <= 0:
        return None, None

    bin_width_s = bin_size_ms / 1000.0
    bin_edges = np.arange(0, stim_time_s + bin_width_s, bin_width_s)

    counts = np.zeros(len(bin_edges) - 1)
    n_trials = 0
    for _, row in cell_trials.iterrows():
        j_epoch = row['epoch_index']
        trial_spikes_ms = spike_times_by_cell.loc[cell_id][j_epoch]
        ts = (
            np.asarray(trial_spikes_ms, dtype=float) / 1000.0
            if trial_spikes_ms is not None and len(trial_spikes_ms) > 0
            else np.array([])
        )
        in_stim = (ts >= pre_time_s) & (ts < pre_time_s + stim_time_s)
        aligned = ts[in_stim] - pre_time_s
        c, _ = np.histogram(aligned, bins=bin_edges)
        counts += c
        n_trials += 1

    if n_trials == 0:
        return None, None

    rate_hz = counts / (n_trials * bin_width_s)
    bin_centers_s = (bin_edges[:-1] + bin_edges[1:]) / 2
    return bin_centers_s, rate_hz


def plot_psth_for_cell_type(df_trials, spike_times_by_cell, df_epochs, condition_key,
                             selected_cell_type, bin_size_ms=10.0, title=None, ax=None,
                             cmap_name='viridis'):
    """
    NEW 2026-08-05 (Claude, per yas): population PSTH for one cell type -- one line per
    condition_key value (e.g. one line per contrast level), so a CRF's shape (plot_crf(),
    above) can be sanity-checked against the actual response time-course it was computed
    from, not just trusted as a summary number. Meant to sit in a cell placed BEFORE the
    CRF cell in the notebook, per yas's request.

    Same per-cell-first-then-population-average convention plot_crf() already uses
    (df_trials.groupby(['cell_id', condition_key])... then averaged across cells): each
    cell's own trial-pooled PSTH is computed first (compute_cell_psth, above), THEN
    averaged across the cells of selected_cell_type -- so one unusually high-firing cell
    can't dominate the type's average shape.

    Lines are colored by condition_key value on a cmap_name colormap (default
    'viridis', low value = dark end) with a colorbar rather than a legend -- avoids a
    cluttered legend when there are many contrast levels.

    Parameters:
        df_trials, spike_times_by_cell, df_epochs, condition_key: same objects/shapes
        load_contrast_section() and the raster functions already use.

        selected_cell_type (str): which cell_type in df_trials to average PSTHs over.

        bin_size_ms (float): PSTH bin width in ms, passed through to compute_cell_psth.
        Default 10.0 (matches yas's MATLAB PSTH convention).

        title (str or None): panel title.

        ax (matplotlib Axes or None): draws into this axes if given (caller owns the
        figure then, this returns fig=None); otherwise makes and returns a new
        single-panel figure.

        cmap_name (str): matplotlib colormap name for the per-condition lines.

    Returns:
        (fig, ax): fig is None if an existing ax was passed in.
    """
    type_trials = df_trials[df_trials['cell_type'] == selected_cell_type]
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 4))
    else:
        fig = None

    if len(type_trials) == 0:
        ax.set_title((title or selected_cell_type) + '\nno trials')
        return fig, ax

    cond_values = sorted(type_trials[condition_key].unique())
    cmap = plt.get_cmap(cmap_name)
    norm = (
        plt.Normalize(vmin=min(cond_values), vmax=max(cond_values))
        if len(cond_values) > 1 else None
    )

    n_cells_plotted = 0
    for cond_val in cond_values:
        cond_trials = type_trials[type_trials[condition_key] == cond_val]
        cell_curves = []
        t_common = None
        for cell_id, cell_trials in cond_trials.groupby('cell_id'):
            t, rate = compute_cell_psth(cell_id, cell_trials, spike_times_by_cell, df_epochs, bin_size_ms)
            if t is None:
                continue
            if t_common is None:
                t_common = t
            cell_curves.append(rate)
        if not cell_curves:
            continue
        n_cells_plotted = max(n_cells_plotted, len(cell_curves))
        mean_rate = np.mean(np.vstack(cell_curves), axis=0)
        color = cmap(norm(cond_val)) if norm is not None else cmap(0.5)
        ax.plot(t_common, mean_rate, color=color, label=f'{condition_key}={cond_val:g}')

    ax.set_xlabel('Time from stim onset (s)')
    ax.set_ylabel(f'Firing rate (Hz), n={n_cells_plotted} cells')
    if title:
        ax.set_title(title)
    if norm is not None:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax)
        cbar.set_label(_condition_axis_label(condition_key))
    else:
        ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    return fig, ax


def plot_psth_mosaic_for_cell_type(df_trials, spike_times_by_cell, df_epochs, condition_key,
                                    selected_cell_type, bin_size_ms=10.0, n_cols=4,
                                    cmap_name='viridis', title=None):
    """
    NEW 2026-08-05 (Claude, per yas): PSTH mosaic -- one small subplot per INDIVIDUAL
    cell of selected_cell_type (not averaged across cells, unlike plot_psth_for_cell_type
    above), one line per condition_key value (e.g. one per contrast) within each
    subplot. Replaces the single population-average panel per yas's feedback ("the
    psths look terrible") -- averaging across only a handful of cells was hiding
    exactly the cell-to-cell shape differences a QC check should surface. Meant for a
    notebook cell with metadata scrolled=True, so a mosaic taller than the screen gets
    a fixed-height scrollable output box instead of pushing the rest of the notebook
    down. plot_psth_for_cell_type (the population-average version) is left in this
    module, just no longer called from the notebook -- still useful if a single-line
    summary is ever wanted again.

    Cells sorted by cell_id, laid out n_cols per row (default 4). One shared colorbar
    for the whole mosaic (not a per-subplot legend) -- would be unreadable repeated
    across dozens of tiny subplots.

    Parameters:
        df_trials, spike_times_by_cell, df_epochs, condition_key: same objects/shapes
        load_contrast_section() and the raster functions already use.

        selected_cell_type (str): which cell_type in df_trials to make a mosaic of.

        bin_size_ms (float): PSTH bin width in ms, passed through to compute_cell_psth.
        Default 10.0.

        n_cols (int): subplots per row. Default 4.

        cmap_name (str): matplotlib colormap name for the per-condition lines.

        title (str or None): figure suptitle. Defaults to
        f'{selected_cell_type} (n={len(cells)} cells)'.

    Returns:
        fig: one figure containing every cell of selected_cell_type.
    """
    cells = sorted(df_trials[df_trials['cell_type'] == selected_cell_type]['cell_id'].unique())
    if len(cells) == 0:
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.set_title(f'{selected_cell_type!r}\nno cells found')
        ax.axis('off')
        return fig

    n_rows = int(np.ceil(len(cells) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.4 * n_cols, 2.6 * n_rows), squeeze=False)

    cond_values = sorted(df_trials[condition_key].unique())
    cmap = plt.get_cmap(cmap_name)
    norm = (
        plt.Normalize(vmin=min(cond_values), vmax=max(cond_values))
        if len(cond_values) > 1 else None
    )

    for i, cell_id in enumerate(cells):
        ax = axes[i // n_cols, i % n_cols]
        cell_all_trials = df_trials[df_trials['cell_id'] == cell_id]
        for cond_val in cond_values:
            cond_trials = cell_all_trials[cell_all_trials[condition_key] == cond_val]
            t, rate = compute_cell_psth(cell_id, cond_trials, spike_times_by_cell, df_epochs, bin_size_ms)
            if t is None:
                continue
            color = cmap(norm(cond_val)) if norm is not None else cmap(0.5)
            ax.plot(t, rate, color=color, linewidth=1)
        ax.set_title(f'Cell {cell_id}', fontsize=9)
        ax.tick_params(labelsize=7)

    for j in range(len(cells), n_rows * n_cols):
        axes[j // n_cols, j % n_cols].axis('off')

    if norm is not None:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=axes, shrink=0.6, pad=0.01)
        cbar.set_label(_condition_axis_label(condition_key))

    fig.supxlabel('Time from stim onset (s)')
    fig.supylabel('Firing rate (Hz)')
    fig.suptitle(title or f'{selected_cell_type} (n={len(cells)} cells)', fontsize=13)
    return fig


def plot_raster_and_psth_for_cell_type(df_trials, spike_times_by_cell, df_epochs, condition_key,
                                        selected_cell_type, bin_size_ms=10.0, max_cells_per_page=4,
                                        cmap_name='viridis', markersize=1.5):
    """
    NEW 2026-08-05 (Claude, per yas): the standard raster-above-PSTH-below QC pairing,
    for sanity-checking a CRF against the actual spikes it's summarizing -- not just a
    PSTH curve on its own (plot_psth_mosaic_for_cell_type, above -- yas's feedback: a
    PSTH-only mosaic is fine for scanning many cells for outliers, but doesn't let you
    check the curve against the raw spikes it came from). Per cell: raster on top (the
    exact same block-by-condition layout _raster_for_cell() already draws, reused
    unchanged), its derived PSTH (compute_cell_psth(), one line per condition_key value
    e.g. contrast, colored on the same colormap/legend for every cell) directly below
    it, sharing the same x-axis (time from stim onset) -- so the two rows are visually
    aligned and you can eyeball whether the PSTH curve is a fair summary of the dots
    above it.

    Paginated exactly like plot_rasters_for_cell_type -- max_cells_per_page cells per
    figure (default 4), so pages stay a normal notebook-cell-output size instead of one
    giant scrollable mosaic.

    Parameters:
        df_trials, spike_times_by_cell, df_epochs, condition_key: same objects/shapes
        load_contrast_section() and the raster functions already use.

        selected_cell_type (str): which cell_type in df_trials to plot.

        bin_size_ms (float): PSTH bin width in ms, passed through to compute_cell_psth.
        Default 10.0.

        max_cells_per_page (int): cells per figure/page. Default 4.

        cmap_name (str): matplotlib colormap name for the per-condition PSTH lines.

        markersize (float): raster dot size, passed through to _raster_for_cell.

    Returns:
        list of figures, one per page.
    """
    cells = sorted(df_trials[df_trials['cell_type'] == selected_cell_type]['cell_id'].unique())
    if len(cells) == 0:
        print(f'No cells of type {selected_cell_type!r} found.')
        return []

    cond_values = sorted(df_trials[condition_key].unique())
    cmap = plt.get_cmap(cmap_name)
    norm = (
        plt.Normalize(vmin=min(cond_values), vmax=max(cond_values))
        if len(cond_values) > 1 else None
    )
    legend_handles = [
        Line2D([0], [0], color=(cmap(norm(cv)) if norm is not None else cmap(0.5)),
               label=f'{condition_key}={cv:g}')
        for cv in cond_values
    ]

    figs = []
    n_pages = int(np.ceil(len(cells) / max_cells_per_page))
    for page in range(n_pages):
        page_cells = cells[page * max_cells_per_page:(page + 1) * max_cells_per_page]
        ncols = len(page_cells)
        fig, axes = plt.subplots(
            2, ncols, figsize=(4 * ncols, 6.5), squeeze=False,
            gridspec_kw={'height_ratios': [2, 1]},
        )
        for i, cell_id in enumerate(page_cells):
            ax_raster = axes[0, i]
            ax_psth = axes[1, i]
            cell_trials = df_trials[df_trials['cell_id'] == cell_id]
            _raster_for_cell(ax_raster, cell_id, cell_trials, spike_times_by_cell, df_epochs, condition_key,
                              markersize=markersize)
            for cond_val in cond_values:
                cond_trials = cell_trials[cell_trials[condition_key] == cond_val]
                t, rate = compute_cell_psth(cell_id, cond_trials, spike_times_by_cell, df_epochs, bin_size_ms)
                if t is None:
                    continue
                color = cmap(norm(cond_val)) if norm is not None else cmap(0.5)
                ax_psth.plot(t, rate, color=color, linewidth=1)
            ax_psth.set_xlim(ax_raster.get_xlim())  # keep the two rows visually aligned
            ax_psth.set_xlabel('Time from stim onset (s)')
            if i == 0:
                ax_psth.set_ylabel('Rate (Hz)')
            ax_psth.grid(True, alpha=0.3)

        fig.legend(handles=legend_handles, loc='lower center', ncol=min(len(cond_values), 6),
                   fontsize=8, bbox_to_anchor=(0.5, -0.02))
        page_label = f' (page {page + 1}/{n_pages})' if n_pages > 1 else ''
        fig.suptitle(f'{selected_cell_type!r}: raster + PSTH (n={len(cells)}){page_label}', fontsize=13)
        fig.tight_layout(rect=[0, 0.04, 1, 0.96])
        figs.append(fig)

    return figs
