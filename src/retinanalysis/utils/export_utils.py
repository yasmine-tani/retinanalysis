"""
Saving figures for Illustrator and exporting the numbers behind them.

    ra.save_figure(fig, "figs/on_bs_crf")          # -> .svg + .pdf + .png, text editable
    ra.export_figure_data(fig, "figs/on_bs_crf")   # -> .csv, one column per plotted series

save_figure keeps every text label as real, editable text (not outlined paths) in both
SVG and PDF, and flattens only very dense artists (e.g. raster ticks, big scatter clouds)
to an embedded image so the file stays small enough for Illustrator to open. Axes, labels,
lines and patches stay vector.

export_figure_data reads the plotted data straight off a finished matplotlib figure
(lines, scatter points, bars, error/SD bands) and writes it as a wide CSV: one column per
unique series, named "<panel title> | <series label> | x" (and "| y"). Works on any
retinanalysis plot without changing the plotting function -- the source-data format
journals ask for, and loads directly in Igor or MATLAB (readtable).
"""
import os
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.collections import PathCollection, PolyCollection, LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle


def _n_points(artist) -> int:
    if isinstance(artist, Line2D):
        return len(artist.get_xdata())
    if isinstance(artist, PathCollection):
        return len(artist.get_offsets())
    if isinstance(artist, LineCollection):
        return sum(len(s) for s in artist.get_segments())
    return 0


def save_figure(
    fig=None,
    path: str = "figure",
    formats: Iterable[str] = ("svg", "pdf", "png"),
    dpi: int = 300,
    rasterize_dense: bool = True,
    dense_threshold: int = 5000,
    transparent: bool = False,
) -> List[str]:
    """
    Save a figure as editable vector graphics (plus a PNG preview).

    Parameters:
        fig: matplotlib Figure. Default None = current figure (plt.gcf()).
        path (str): output path WITHOUT extension, e.g. 'figs/20251016A_on_bs_crf'.
            Folders are created if needed. One file is written per format.
        formats: any of 'svg', 'pdf', 'png', 'eps'. Default ('svg', 'pdf', 'png').
        dpi (int): resolution for the PNG and for any flattened dense artists. Default 300.
        rasterize_dense (bool): flatten artists with more than dense_threshold points
            (raster plots, dense scatters) to an embedded image inside the vector file;
            everything else stays vector. Default True.
        dense_threshold (int): point count above which an artist is flattened. Default 5000.
        transparent (bool): transparent background. Default False.

    Returns:
        list of file paths written.

    Text stays editable because svg.fonttype='none' (SVG keeps <text> elements) and
    pdf.fonttype=42 (TrueType fonts embedded, not converted to outlines). If the font
    isn't installed on the machine opening the file, Illustrator substitutes one.
    """
    fig = fig if fig is not None else plt.gcf()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    flattened = []
    if rasterize_dense:
        for ax in fig.axes:
            for artist in list(ax.lines) + list(ax.collections):
                if _n_points(artist) > dense_threshold and not artist.get_rasterized():
                    artist.set_rasterized(True)
                    flattened.append(artist)

    paths = []
    with mpl.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42}):
        for fmt in formats:
            out = f"{path}.{fmt.lstrip('.')}"
            fig.savefig(out, dpi=dpi, bbox_inches="tight", transparent=transparent)
            paths.append(out)

    for artist in flattened:  # leave the figure as it was
        artist.set_rasterized(False)

    print(f"Saved {', '.join(os.path.basename(p) for p in paths)}"
          + (f" ({len(flattened)} dense artist(s) flattened)" if flattened else ""))
    return paths


def _label(artist, idx: int) -> str:
    lab = artist.get_label() if hasattr(artist, "get_label") else ""
    if not lab or lab.startswith("_"):
        return f"series{idx}"
    return lab


def figure_data_to_frame(fig=None) -> pd.DataFrame:
    """
    Pull the plotted numbers off a figure into a wide DataFrame (see export_figure_data).
    Series of different lengths are padded with NaN at the bottom.
    """
    fig = fig if fig is not None else plt.gcf()
    columns = {}

    def add(name, values):
        base, k = name, 2
        while name in columns:  # keep every series, even with duplicate names
            name = f"{base} ({k})"
            k += 1
        columns[name] = np.asarray(values, dtype=float).ravel()

    for a_idx, ax in enumerate(fig.axes):
        panel = ax.get_title() or ax.get_ylabel() or f"panel{a_idx + 1}"
        n = 0
        for line in ax.lines:
            x, y = np.asarray(line.get_xdata(), float), np.asarray(line.get_ydata(), float)
            if len(x) < 2 or (np.allclose(y, y[0]) and len(np.unique(x)) <= 2):
                continue  # skip axhline/axvline-style reference lines
            n += 1
            name = f"{panel} | {_label(line, n)}"
            add(f"{name} | x", x)
            add(f"{name} | y", y)
        for coll in ax.collections:
            if isinstance(coll, PathCollection) and len(coll.get_offsets()):
                n += 1
                off = np.asarray(coll.get_offsets(), float)
                name = f"{panel} | {_label(coll, n)}"
                add(f"{name} | x", off[:, 0])
                add(f"{name} | y", off[:, 1])
            elif isinstance(coll, PolyCollection) and len(coll.get_paths()):
                # fill_between band (e.g. mean +/- SD): export its lower/upper edges
                verts = coll.get_paths()[0].vertices
                if len(verts) >= 4:
                    n += 1
                    half = (len(verts) - 1) // 2
                    upper = verts[1 : half + 1]
                    lower = verts[half + 1 : -1][::-1]
                    m = min(len(upper), len(lower))
                    name = f"{panel} | {_label(coll, n)} band"
                    add(f"{name} | x", upper[:m, 0])
                    add(f"{name} | upper", upper[:m, 1])
                    add(f"{name} | lower", lower[:m, 1])
        bars = [p for p in ax.patches if isinstance(p, Rectangle) and p.get_width() > 0 and p.get_height() != 0]
        if bars:
            n += 1
            labels = [t.get_text() for t in ax.get_xticklabels()]
            add(f"{panel} | bars | x", [b.get_x() + b.get_width() / 2 for b in bars])
            add(f"{panel} | bars | height", [b.get_height() for b in bars])
            if labels and len(labels) == len(bars) and any(labels):
                columns[f"{panel} | bars | label"] = np.array(labels, dtype=object)

    if not columns:
        return pd.DataFrame()
    longest = max(len(v) for v in columns.values())
    padded = {}
    for k, v in columns.items():
        if v.dtype == object:
            padded[k] = list(v) + [""] * (longest - len(v))
        else:
            padded[k] = np.concatenate([v, np.full(longest - len(v), np.nan)])
    return pd.DataFrame(padded)


def export_figure_data(fig=None, path: str = "figure_data") -> Optional[str]:
    """
    Write the numbers plotted in a figure to '<path>.csv', one column per unique series
    (Maya's convention: e.g. 'on/brisk sustained | mean | y'). Each series gets its own
    x column so panels with different x values stay aligned. Pass the same `path` as
    save_figure to keep the figure and its data side by side.

    Returns the CSV path, or None if nothing plottable was found.
    """
    df = figure_data_to_frame(fig)
    if df.empty:
        print("No plotted data found in this figure.")
        return None
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    out = path if path.endswith(".csv") else f"{path}.csv"
    df.to_csv(out, index=False)
    print(f"Saved {os.path.basename(out)} ({df.shape[1]} columns)")
    return out
