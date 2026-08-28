import retinanalysis
from retinanalysis._database import schema
import os
from retinanalysis.config.settings import ANALYSIS_DIR, DATA_DIR
from retinanalysis.utils.vision_utils import _resolve_vision_data_path
import pandas as pd
from retinanalysis.utils.vision_utils import get_analysis_vcd, get_ells, get_timecourses
from hdf5storage import loadmat
import pickle
import numpy as np
from typing import cast, List, Dict, Optional, Any

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import visionloader as vl
from scipy.ndimage import zoom

try:
    import importlib.resources as ir
except:
    import importlib_resources as ir  # type: ignore

from retinanalysis.utils.datajoint_utils import get_noise_name_by_exp


class AnalysisChunk:
    """
    Class that contains data from an MEA sorting chunk created primarily from spatial noise.

    This is unique to spatial noise chunks because these chunks contain '.sta'. and '.params'
    files while regular sorting chunks and data files do not.

    Parameters:
        exp_name (str): The name of the experiment as seen in the 'exp_name' entry of the datajoint database

        chunk_name (str): The name of the sorting chunk (e.g. 'chunk2'). This chunk must be findable in the
        analysis directory defined by the config.ini file in the retinanalysis_root/config folder.

        ss_version (str): spike sorting version, default is 'kilosort2.5'. This is mostly used to find the
        right folder. Relevant files should be located at: 'analysis_directory/chunk_name/ss_version/'

        b_load_spatial_maps (bool): Whether or not to load the spatial maps for the cells in this chunk,
        default value is True.

        pkl_file (dict | str): Optional. If you have exported an analysis chunk to a pickle file using
        the export_to_pkl() method, you can give only this input to reload the object from the pickle file.

    Returns:
        AnalysisChunk object for experiment name, chunk, and ss_version given in the initializer.

    Properties:
        Use the print command on a AnalysisChunk instance to get a list of all properties contained in
        the object
    """

    def __init__(
        self,
        exp_name: Optional[str] = None,
        chunk_name: Optional[str] = None,
        ss_version: str = "kilosort2.5",
        pkl_file: Optional[dict | str] = None,
        b_load_spatial_maps: bool = True,
        verbose: bool = True,
        **vu_kwargs,
    ):

        self.verbose = verbose

        if pkl_file is None:
            if exp_name is None or chunk_name is None:
                raise ValueError(
                    "Either exp_name and chunk_name or pkl_file must be provided."
                )
        else:
            # Load from pickle file if string, otherwise must be a dict
            if isinstance(pkl_file, str):
                with open(pkl_file, "rb") as f:
                    d_out = pickle.load(f)
            else:
                d_out = pkl_file
                pkl_file = "input dict."
            self.__dict__.update(d_out)
            self.vcd = get_analysis_vcd(
                self.exp_name,
                self.chunk_name,
                self.ss_version,
                verbose=self.verbose,
                **vu_kwargs,
            )
            if self.verbose:
                print(f"AnalysisChunk loaded from {pkl_file}")
            return

        self.exp_name = exp_name
        self.chunk_name = chunk_name
        self.ss_version = self._resolve_ss_version(chunk_name, ss_version)

        # Pull Experiment ID
        exp_id = schema.Experiment() & {"exp_name": self.exp_name}
        self.exp_id = exp_id.to_arrays("id")[0]

        # Pull chunk id
        chunk_id = schema.SortingChunk() & {
            "experiment_id": self.exp_id,
            "chunk_name": self.chunk_name,
        }
        self.chunk_id = chunk_id.to_arrays("id")[0]

        self.noise_protocol = get_noise_name_by_exp(exp_name)

        # Pull protocol id
        protocol_id = schema.Protocol() & {"name": self.noise_protocol}
        self.protocol_id = protocol_id.to_arrays("protocol_id")[0]

        self.vcd = get_analysis_vcd(
            self.exp_name,
            self.chunk_name,
            self.ss_version,
            verbose=self.verbose,
            **vu_kwargs,
        )
        self.cell_ids = np.sort(self.vcd.get_cell_ids())

        # Pull EIs into an EI dictionary (if include_ei param is true)
        loaded_eis = False
        if "include_ei" in vu_kwargs:
            if vu_kwargs["include_ei"] == False:
                pass
            else:
                self.d_EIs = dict()
                bad_ids = []
                for id in self.cell_ids:
                    try:
                        self.d_EIs[id] = self.vcd.get_ei_for_cell(id).ei
                    except:
                        print(
                            f"WARNING: No ei for ref cell id {id}, removing from {self.chunk_name} AnalysisChunk"
                        )
                        bad_ids.append(id)

                mask = ~np.isin(self.cell_ids, bad_ids)
                self.cell_ids = self.cell_ids[mask]
                loaded_eis = True
        else:
            self.d_EIs = dict()
            bad_ids = []
            for id in self.cell_ids:
                try:
                    self.d_EIs[id] = self.vcd.get_ei_for_cell(id).ei
                except:
                    print(
                        f"WARNING: No ei for ref cell id {id}, removing from {self.chunk_name} AnalysisChunk"
                    )
                    bad_ids.append(id)

            mask = ~np.isin(self.cell_ids, bad_ids)
            self.cell_ids = self.cell_ids[mask]
            loaded_eis = True

        # UPDATED 2026-08-11 (Claude, per yas -- a different dataset crashed deep inside
        # ei_corr() with a cryptic "IndexError: tuple index out of range", traced back to
        # this chunk having ZERO cells with a usable EI after the per-cell drop loop
        # above). The per-cell "WARNING: No ei..." lines above are easy to miss when
        # there are many of them -- especially since every notebook that builds an
        # AnalysisChunk does so inside a `with scrollable_prints():` block, which
        # collapses exactly these prints into a small scrolled box. A single unmissable
        # summary line (and a hard error-level line if EVERY cell failed) makes this
        # failure mode diagnosable from the printed output alone, instead of requiring a
        # trip into ei_corr()'s internals to figure out why fixed_ref_eis had the wrong
        # shape.
        if loaded_eis and len(bad_ids) > 0:
            print(
                f"EI loading summary for {self.chunk_name}: {len(bad_ids)} / "
                f"{len(bad_ids) + len(self.cell_ids)} cell(s) had no usable EI and were "
                f"dropped. {len(self.cell_ids)} cell(s) remain."
            )
        if loaded_eis and len(self.cell_ids) == 0:
            print(
                f"ERROR: 0 cells in {self.chunk_name} have a usable EI. EI-based cell "
                "matching (cluster_match/ei_corr, used by create_mea_pipeline and "
                "build_master_mapping_table) will fail for this chunk with a cryptic "
                "'IndexError: tuple index out of range' if you proceed -- that error is "
                "actually this. This usually means either this chunk's .ei file doesn't "
                "exist / EI computation was never run for it (check the analysis "
                "directory), or something is systematically wrong with EI loading here "
                "(see the per-cell WARNING lines above, if any printed) -- not just a "
                "normal handful of broken cells."
            )

        # Pull timecourses into an timecourse dictionary
        self.d_timecourses = dict()
        for id in self.cell_ids:
            timecourse_r = self.vcd.main_datatable[id]["RedTimeCourse"]
            timecourse_g = self.vcd.main_datatable[id]["GreenTimeCourse"]
            timecourse_b = self.vcd.main_datatable[id]["BlueTimeCourse"]
            self.d_timecourses[id] = {
                "red": timecourse_r,
                "green": timecourse_g,
                "blue": timecourse_b,
            }

        # Pull ISIs into an ISI  dictionary
        self.d_ISIs = dict()
        for id in self.cell_ids:
            isi = self.vcd.get_acf_numpairs_for_cell(id)
            np.nan_to_num(isi, copy=False, nan=0.001, neginf=0.001, posinf=0.001)
            self.d_ISIs[id] = isi
        self.isi_bin_edges = np.linspace(0, 300, 601)

        self.get_noise_params()
        self.get_rf_params()
        self.get_df()

        if b_load_spatial_maps:
            self.get_spatial_maps()

    def _resolve_ss_version(self, chunk_name: str, requested_ss_version: str) -> str:
        # Adapted to choose a real spike-sorting folder automatically when the notebook uses the old default version.
        if requested_ss_version and os.path.isdir(
            os.path.join(DATA_DIR, self.exp_name, requested_ss_version, chunk_name)
        ):
            return requested_ss_version

        candidate_versions = ["kilosort2.5", "kilosort25", "kilosort40", "kilosort4", "combined"]
        for version in candidate_versions:
            if os.path.isdir(os.path.join(DATA_DIR, self.exp_name, version, chunk_name)):
                return version
            if os.path.isdir(os.path.join(ANALYSIS_DIR, self.exp_name, chunk_name, version)):
                return version
        return requested_ss_version or "kilosort2.5"

    def get_noise_params(self):
        """
        Method for accessing spatial noise and STA parameters, and correcting for any
        discrepancy due to cropping.

        If the chunk's globals file has no RTMP (runtime movie parameters) tag,
        self.vcd.runtimemovie_params is None (see get_analysis_vcd() in vision_utils.py).
        In that case we assume the STA grid was never cropped relative to the full noise
        grid: staXChecks/staYChecks default to numXChecks/numYChecks, so
        deltaXChecks/deltaYChecks come out to 0. A warning is printed whenever this
        fallback is used.
        """
        has_rtmp = self.vcd.runtimemovie_params is not None

        if has_rtmp:
            self.staXChecks = int(self.vcd.runtimemovie_params.width)
            self.staYChecks = int(self.vcd.runtimemovie_params.height)

        # Pull epoch block and epoch to get num X and num Y checks used in noise
        epoch_blocks = schema.EpochBlock() & {
            "experiment_id": self.exp_id,
            "chunk_id": self.chunk_id,
            "protocol_id": self.protocol_id,
        }
        epoch_block_ids = epoch_blocks.to_arrays("id")
        epochs = [
            schema.Epoch() & {"experiment_id": self.exp_id, "parent_id": block_id}
            for block_id in epoch_block_ids
        ]

        numXChecks = np.array(
            [epoch.to_arrays("parameters")[0]["numXChecks"] for epoch in epochs]
        )
        numYChecks = np.array(
            [epoch.to_arrays("parameters")[0]["numYChecks"] for epoch in epochs]
        )

        if not all(element == numXChecks[0] for element in numXChecks) and not all(
            element == numYChecks[0] for element in numYChecks
        ):
            print(
                "WARNING: Not all epoch blocks used the same number of X and Y checks\n"
            )

            gridSizes = np.array(
                [epoch.to_arrays("parameters")[0]["gridSize"] for epoch in epochs]
            )

            if has_rtmp:
                vision_micronsPerStixel = self.vcd.runtimemovie_params.micronsPerStixelX
                self.numXChecks = int(numXChecks[gridSizes == vision_micronsPerStixel])
                self.numYChecks = int(numYChecks[gridSizes == vision_micronsPerStixel])
            else:
                print(
                    "WARNING: No RTMP tag available to disambiguate which grid size "
                    "was used; defaulting to the first epoch block's numXChecks/"
                    "numYChecks.\n"
                )
                self.numXChecks = int(numXChecks[0])
                self.numYChecks = int(numYChecks[0])

        else:
            self.numXChecks = int(numXChecks[0])
            self.numYChecks = int(numYChecks[0])

        if not has_rtmp:
            print(
                "WARNING: Globals file has no RTMP tag; assuming the STA grid was NOT "
                "cropped relative to the full noise grid (staXChecks = numXChecks, "
                "staYChecks = numYChecks, so deltaXChecks = deltaYChecks = 0).\n"
            )
            self.staXChecks = self.numXChecks
            self.staYChecks = self.numYChecks

        self.deltaXChecks = int((self.numXChecks - self.staXChecks) / 2)
        self.deltaYChecks = int((self.numYChecks - self.staYChecks) / 2)

        self.microns_per_pixel = epochs[0].to_arrays("parameters")[0]["micronsPerPixel"]
        self.canvas_size = epochs[0].to_arrays("parameters")[0]["canvasSize"]

        # Pull noise data file names
        noise_data_dirs = epoch_blocks.to_arrays("data_dir")
        self.data_files = [os.path.basename(path) for path in noise_data_dirs]

        # Pull typing files directly from available analysis directories... avoids issues with datajoint
        # not updating typing files on existing experiments
        candidate_typedirs = [
            os.path.join(ANALYSIS_DIR, self.exp_name, self.chunk_name, self.ss_version),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name, self.ss_version),
            os.path.join(DATA_DIR, self.exp_name, self.ss_version, self.chunk_name),
            os.path.join(ANALYSIS_DIR, self.exp_name, self.chunk_name),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name),
            os.path.join(ANALYSIS_DIR, self.exp_name, self.ss_version),
            os.path.join(DATA_DIR, self.exp_name, self.ss_version),
        ]
        typing_files = []
        seen_files = set()
        for typing_dir in candidate_typedirs:
            if not os.path.isdir(typing_dir):
                continue
            for file in os.listdir(typing_dir):
                if not file.endswith(".txt"):
                    continue
                if file in seen_files:
                    continue
                seen_files.add(file)
                typing_files.append(file)

        self.typing_files = typing_files

        # typing_files = schema.CellTypeFile() & {'chunk_id' : self.chunk_id, 'algorithm': self.ss_version}
        # self.typing_files = [file_name for file_name in typing_files.fetch('file_name')]

        self.pixels_per_stixel = self.canvas_size[0] / self.numXChecks
        self.microns_per_stixel = self.microns_per_pixel * self.pixels_per_stixel

    def get_rf_params(self):
        """
        Method for pulling the receptive field parameters stored in the vision cell data table (VCD).

        This method also corrects for Y-flipping and any crop discrepancies between the size of the
        spatial noise and the size of the STA.
        """
        self.rf_params = dict()
        broken_ids = []
        for id in self.cell_ids:
            try:
                center_x = self.vcd.main_datatable[id]["x0"]
                center_y = self.vcd.main_datatable[id]["y0"]
                self.rf_params[id] = {
                    "center_x": center_x + self.deltaXChecks,
                    "center_y": (self.staYChecks - center_y) + self.deltaYChecks,
                    "std_x": self.vcd.main_datatable[id]["SigmaX"],
                    "std_y": self.vcd.main_datatable[id]["SigmaY"],
                    "rot": self.vcd.main_datatable[id]["Theta"],
                }
            except:
                print(f"Issue with id {id}...\nWill remove from cell_ids list.")
                broken_ids.append(id)

        for id in broken_ids:
            self.cell_ids = self.cell_ids[self.cell_ids != id]

    def get_cells_by_region(self, roi: Dict[str, float], units: str = "pixels"):
        """
        Method for pulling cell_ids by region of interest.

        Parameters:
            roi (dict): roi definition as a dictionary with 4 values. 'x_min','x_max', 'y_min', 'y_max'.
            These define the vertical and horizontal lines that define the region of interest. Units of ROI
            definition must match the units parameter!

        units (str): units to use when defining the roi. Must be either 'pixels', 'microns', or 'stixels'. Default 'pixels'.

        Returns:
            arr_ids (ndarray): returns a 1D array of cell ids whose center_x and center_y fall within the defined roi.
        """

        if "pixels" in units.lower():
            unit_scaling = self.pixels_per_stixel
        elif "microns" in units.lower():
            unit_scaling = self.microns_per_stixel
        elif "stixels" in units.lower():
            unit_scaling = 1
        else:
            raise Exception("Units must be 'pixels', 'microns' or 'stixels'")

        bounding_box = dict()
        for key, val in roi.items():
            bounding_box[key] = val / unit_scaling

        x_min = bounding_box["x_min"]
        x_max = bounding_box["x_max"]
        y_min = bounding_box["y_min"]
        y_max = bounding_box["y_max"]

        df_cell_params_filtered = self.df_cell_params.query(
            "center_x > @x_min and center_x < @x_max and center_y > @y_min and center_y < @y_max"
        )
        arr_ids = df_cell_params_filtered["cell_id"].values

        return arr_ids

    def get_df(self):
        # Adapted to keep cell typing working when typing files are relocated under newer layouts.
        """Build the cell-parameter dataframe while tolerating newer analysis layouts.

        This change keeps the notebook workflow working when typing files live under a
        data-directory-based path rather than the older chunk-root layout.
        """
        center_x = [self.rf_params[id]["center_x"] for id in self.cell_ids]
        center_y = [self.rf_params[id]["center_y"] for id in self.cell_ids]
        std_x = [self.rf_params[id]["std_x"] for id in self.cell_ids]
        std_y = [self.rf_params[id]["std_y"] for id in self.cell_ids]
        rot = [self.rf_params[id]["rot"] for id in self.cell_ids]

        df_dict = {
            "cell_id": self.cell_ids,
            "center_x": center_x,
            "center_y": center_y,
            "std_x": std_x,
            "std_y": std_y,
            "rot": rot,
        }

        cell_types_list_path = str(ir.files(retinanalysis) / "assets/cell_types.csv")
        cell_types_list = pd.read_csv(cell_types_list_path)
        cell_types = cell_types_list["cell_types"].values

        for idx, typing_file in enumerate(self.typing_files):
            file_path = self._resolve_typing_file_path(typing_file)
            d_result = dict()

            if file_path is None or not os.path.isfile(file_path):
                classification = ["Unknown"] * len(self.cell_ids)
                df_dict[f"typing_file_{idx}"] = classification
                continue

            with open(file_path, "r") as file:
                for line in file:
                    if not line.strip():
                        continue
                    parts = line.split(" ", 1)
                    if len(parts) != 2:
                        continue
                    key, value = map(str.strip, parts)
                    sub_values = [s.strip() for s in value.split("/") if s.strip()]
                    d_result[int(key)] = sub_values

            # Normalize cell type tokens for matching
            # CHANGED 2026-07-30 (Claude, per yas -- she noticed some cell types show up far
            # less often than expected and hypothesized the classification file isn't always
            # written the same way, e.g. "brisk sustained" vs. "brisk-sustained"): matching
            # used to be a literal `part in norm_cell_types_lower` check, so any hyphen,
            # underscore, or run of extra whitespace in the raw classification file (instead of
            # a single plain space, matching cell_types.csv exactly) silently fell through to
            # "Unknown" with no warning. _normalize_type_token() below makes hyphens/underscores
            # equivalent to spaces and collapses repeated whitespace before comparing, on BOTH
            # sides (raw file tokens and the CSV vocabulary), so "brisk-sustained",
            # "brisk_sustained", and "brisk  sustained" all now match the CSV's "brisk
            # sustained" the same as a literal space would. This only WIDENS matching (things
            # that used to match still match identically); it cannot cause two previously-
            # distinct types to collide, since it doesn't touch letters or the on/off prefix.
            def _normalize_type_token(s: str) -> str:
                return " ".join(s.replace("-", " ").replace("_", " ").split())

            norm_cell_types = [ct.strip() for ct in cell_types]
            norm_cell_types_lower = [
                _normalize_type_token(ct.lower()) for ct in norm_cell_types
            ]
            unmatched_raw_tokens: set = set()

            def pick_type_from_parts(parts_list: list[str]) -> str:
                parts_lower = [_normalize_type_token(p.lower()) for p in parts_list]
                # find base type and optional on/off prefix
                base = None
                for part in parts_lower:
                    if part in norm_cell_types_lower:
                        base = norm_cell_types[norm_cell_types_lower.index(part)]
                        break
                prefix = None
                for part in parts_lower:
                    if part in ("on", "off"):
                        prefix = part
                        break
                # prefer explicit combined labels like 'on/brisk sustained' if present in CSV
                if prefix and base:
                    combined = f"{prefix}/{base}"
                    for ct in norm_cell_types:
                        if _normalize_type_token(ct.lower()) == _normalize_type_token(
                            combined.lower()
                        ):
                            return ct
                    # if combined not in CSV, still return combined string so downstream can match
                    return combined
                # otherwise prefer base type if found
                if base:
                    return base
                # Nothing matched -- record the raw (non-on/off, non-structural) tokens that
                # failed, so a verbose run can tell yas exactly which raw strings need a
                # cell_types.csv entry or turn out to be a formatting variant like the hyphen
                # case above. "all" is skipped -- it's the fixed top-level bin every line is
                # written under (e.g. "All/on/brisk sustained"), not a candidate type name, so
                # it would otherwise show up as a false "unmatched" entry on every single line.
                for part, raw_part in zip(parts_lower, parts_list):
                    if part not in ("on", "off", "all") and part != "":
                        unmatched_raw_tokens.add(raw_part)
                return "Unknown"

            for cell in self.cell_ids:
                if cell in d_result.keys():
                    chosen = pick_type_from_parts(d_result[cell])
                    d_result[cell] = chosen
                else:
                    d_result[cell] = "Unknown"

            # UPDATED 2026-08-12 (Claude, per yas): used to always print regardless of
            # self.verbose. That's fine for one chunk, but plot_mosaics_for_datasets()
            # constructs an AnalysisChunk per chunk across a whole df_exp_search, so this
            # fired once per chunk with any mismatched labels -- a wall of near-identical
            # lines when scanning many datasets. Gated behind self.verbose (default True
            # for a standalone AnalysisChunk, False when called from
            # plot_mosaics_for_datasets) so mosaic-plotting stays quiet by default; set
            # verbose=True to get this diagnostic back.
            if unmatched_raw_tokens and self.verbose:
                print(
                    f"[{typing_file}] {len(unmatched_raw_tokens)} raw classification token(s) "
                    "did not match any cell_types.csv entry (even after normalizing "
                    "hyphens/underscores/extra spaces) and were classified 'Unknown': "
                    f"{sorted(unmatched_raw_tokens)}"
                )

            classification = [d_result.get(cell, "Unknown") for cell in self.cell_ids]
            df_dict[f"typing_file_{idx}"] = classification

        self.df_cell_params = pd.DataFrame(df_dict)

    def _resolve_typing_file_path(self, typing_file: str) -> Optional[str]:
        # Adapted to search both legacy and newer analysis-directory patterns.
        """Resolve typing-file locations across legacy and newer analysis layouts."""
        candidate_dirs = [
            os.path.join(ANALYSIS_DIR, self.exp_name, self.chunk_name, self.ss_version),
            os.path.join(ANALYSIS_DIR, self.exp_name, self.ss_version, self.chunk_name),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name, self.ss_version),
            os.path.join(DATA_DIR, self.exp_name, self.ss_version, self.chunk_name),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name, "ksfiles"),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name, "kilosort2.5"),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name, "kilosort25"),
            os.path.join(DATA_DIR, self.exp_name, self.chunk_name, "kilosort40"),
        ]
        for directory in candidate_dirs:
            candidate = os.path.join(directory, typing_file)
            if os.path.isfile(candidate):
                return candidate
        return None

    def get_spatial_maps(self, ls_channels=[0, 2]):
        # By default load red and blue channel spatial maps.
        mat_file = os.path.join(
            DATA_DIR,
            self.exp_name,
            self.chunk_name,
            self.ss_version,
            f"{self.ss_version}_params.mat",
        )

        # If _params.mat file doesn't exist in data dir, look in analysis dir instead
        if not os.path.exists(mat_file):
            mat_file = os.path.join(
                ANALYSIS_DIR,
                self.exp_name,
                self.chunk_name,
                self.ss_version,
                f"{self.ss_version}_params.mat",
            )

        # if no _params.mat file found at all, print a warning and return
        if not os.path.exists(mat_file):
            print(
                f"WARNING: _params.mat file not found in: {mat_file}\nSpatial maps were not loaded"
            )
            return

        d_params = loadmat(mat_file)
        d_spatial_maps = {}
        for idx_ID, n_ID in enumerate(self.cell_ids):
            # TODO pad spatial maps to match N_HEIGHT and N_WIDTH @roaksleaf pls help
            # Cell ID index in vcd should be same as in _params.mat
            spat_mat = d_params["spatial_maps"][idx_ID][:, :, ls_channels]
            left_pad = int(self.deltaXChecks)
            right_pad = int(self.numXChecks - self.staXChecks - self.deltaXChecks)
            top_pad = int(self.deltaYChecks)
            bottom_pad = int(self.numYChecks - self.staYChecks - self.deltaYChecks)

            padded = np.pad(
                spat_mat,
                ((top_pad, bottom_pad), (left_pad, right_pad), (0, 0)),
                mode="constant",
                constant_values=0,
            )
            d_spatial_maps[n_ID] = padded

        self.d_spatial_maps = d_spatial_maps
        if self.verbose:
            print(
                f"\nLoaded spatial maps for channels {ls_channels} and {len(self.cell_ids)} cells of shape {d_spatial_maps[self.cell_ids[0]].shape}"
            )  # from:\n{mat_file}')
            print(f"Spatial maps have been padded to align with RF parameters.\n")
        # TODO could also load convex hull fits too under 'hull_vertices'

    def plot_rfs(
        self,
        noise_ids: Optional[List[int]] = None,
        cell_types: Optional[List[str]] = None,
        typing_file: Optional[str] = None,
        units: str = "pixels",
        std_scaling: float = 1.6,
        b_zoom: bool = False,
        n_pad: int = 6,
        minimum_n: int = 1,
        roi: Optional[Dict[str, float]] = None,
        label_cells: bool = False,
        exclude_unknown: bool = True,
        title: str = "RFs by Cell Type",
    ) -> Optional[np.ndarray[Any, np.dtype[np.object_]]]:
        """
        Method for plotting the receptive fields for a given list of cell ids, cell types,
        or a union of both. If no cell_ids or cell types are given, all cells in the
        analysis chunk are plotted by type.

        Parameters:
            noise_ids (List[int]): A list of cell_ids to plot. Default None.

            cell_types (List[str]): A list of cell_type strings, (e.g. ['OnP', 'OffP']). Default None.

            typing_fyle (str): A typing file name which is used to determine the cell types for any given cell_ids.
            If None is given, the 0th typing file associated with the analysis chunk is used. Default None.

            units (str): Units to use when plotting the receptive fields. Must be either 'pixels', 'microns',
            or 'stixels'. Default 'pixels'.

            std_scaling (float): Factor used to scale the standard deviation of the plotted receptive fields. Default 1.6

            b_zoom (bool): Boolean value indicating whether or not to zoom the plots in on  the cell mosaic. Default False

            n_pad (int): Padding value (in stixels) used with b_zoom. B_zoom will zoom into the min and max center_x and
            center_y values in the mosaic, and n_pad will zoom back out by the given number of stixels. Default 6

            minimum_n (int): min number of cells required to actually plot the output

            roi (dict): roi definition as a dictionary with 4 values. 'x_min', 'x_max', 'y_min', 'y_max'. These
            define the vertical and horizontal lines that define the region of interest

            label_cells (bool): If True, put text label with cell id on each ellipse. Default False.

            exclude_unknown (bool): If True (default), drop the 'Unknown' cell type (cells whose
            classification string didn't match anything in cell_types.csv) from the auto-detected
            type list when cell_types=None. Has no effect if cell_types is given explicitly --
            an explicit request for 'Unknown' is still honored.

            title (str): Figure suptitle. Default 'RFs by Cell Type' -- override this when
            plotting the same chunk from two different sources side by side (e.g. protocol
            chunk vs. reference/typing chunk) so the two figures are distinguishable.

        Returns:
            axs (axes): Axes object that contains all of the axes used in the receptive field figure.
            There will be as many axes as there are cell_types represented in the plot.

            The function will also plot the results automatically if you're in a jupyter notebook, but it does not call
            plt.show() on the figure. You need to call plt.show() manually if running as part of a REPL or script.
        """
        # Convert individual cell type or cell id into list
        cell_types_was_none = cell_types is None

        if isinstance(cell_types, str):
            cell_types = [cell_types]

        if isinstance(noise_ids, int) or isinstance(noise_ids, float):
            noise_ids = [int(noise_ids)]

        # Parse typing file, use typing file 0 if none given
        if typing_file is None:
            try:
                typing_file = self.typing_files[0]
            except:
                print(f"No typing files for {self.exp_name} {self.chunk_name}")
                return

        if typing_file not in self.typing_files:
            print(f"{typing_file} Doesn't Exist in {self.exp_name} {self.chunk_name}")
            return

        typing_file_idx = self.typing_files.index(typing_file)

        # Pull appropriate union of noise cell ids and cell types using given params.
        if noise_ids is None and cell_types is None:
            filtered_df = self.df_cell_params
            noise_ids = list(filtered_df["cell_id"].values)
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        elif noise_ids is None:
            filtered_df = self.df_cell_params.query(
                f"typing_file_{typing_file_idx} in @cell_types"
            )
            noise_ids = list(filtered_df["cell_id"].values)
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        elif cell_types is None:
            filtered_df = self.df_cell_params.query(f"cell_id  in @noise_ids")
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        else:
            filtered_df = self.df_cell_params.query(
                f"typing_file_{typing_file_idx} in @cell_types and cell_id in @noise_ids"
            )
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())

        # Pull only those cells inside the given region of interest (roi) if one was specified.
        if roi is not None:
            roi_cell_ids = self.get_cells_by_region(roi=roi, units=units)
            filtered_df = filtered_df.query("cell_id in @roi_cell_ids")
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())

        # Cell types auto-detected (not explicitly requested) skip 'Unknown' by default --
        # cells whose classification string didn't match cell_types.csv, not a real type.
        # Placed after the roi filter above, since that block re-derives cell_types from
        # filtered_df and would otherwise silently reintroduce 'Unknown'.
        if exclude_unknown and cell_types_was_none:
            cell_types = [ct for ct in cell_types if str(ct).strip().lower() != "unknown"]

        # If no cells found after all the above filtering, return
        if len(filtered_df) == 0:
            print("No data found for the given noise_ids and cell_types.")
            return

        # Remove cells below minimum threshold set in params (minimum_n param)
        too_few_cells = [
            ct
            for ct in cell_types
            if len(
                filtered_df.query(f"typing_file_{typing_file_idx} == @ct")[
                    "cell_id"
                ].values
            )
            < minimum_n
        ]

        for ct in too_few_cells:
            cell_types.remove(ct)

        # Sort cell types alphabetically for plotting
        cell_types = sorted(cell_types)

        # Organize IDs and types into dictionary and pass to get_ells() function to pull ellipses
        d_noise_ids_by_type = {
            ct: list(
                filtered_df.query(f"typing_file_{typing_file_idx} == @ct")[
                    "cell_id"
                ].values
            )
            for ct in cell_types
        }
        d_ells_by_type, scale_factor = get_ells(
            self, d_noise_ids_by_type, std_scaling=std_scaling, units=units
        )

        # Plot ellipses, one axis per cell type
        rows = int(np.ceil(len(cell_types) / 4))
        cols = np.min([(len(cell_types) - 1 % 4) + 1, 4])
        size = (4 * cols, int(3 * rows))

        fig, axs = plt.subplots(
            nrows=rows, ncols=cols, figsize=size, layout="constrained"
        )

        if cols != 1:
            axs = np.array(axs).flatten()
        else:
            axs = np.array([axs])

        for idx, ct in enumerate(cell_types):
            ax = axs[idx]
            for id in d_ells_by_type[ct]:
                ax.add_patch(d_ells_by_type[ct][id])
                if label_cells:
                    ax.text(
                        d_ells_by_type[ct][id].center[0],
                        d_ells_by_type[ct][id].center[1],
                        str(id),
                        horizontalalignment="center",
                        verticalalignment="center",
                    )

            ax.set_xlim(0, self.numXChecks * scale_factor)
            ax.set_ylim(0, self.numYChecks * scale_factor)

            ax.set_ylabel(units.lower())
            ax.set_xlabel(units.lower())

            n_cells = len(d_ells_by_type[ct])
            ax.set_title(f"{ct}, (n = {n_cells})")

        # Remove any empty axes
        num_axes = rows * cols
        empty_axes = num_axes - len(cell_types)

        for i in range(empty_axes):
            fig.delaxes(cast(Axes, axs[num_axes - 1 - i]))

        # If b_zoom is true, crop each axis to zoom in on the array.
        # UPDATED 2026-08-12 (Claude, per yas -- "n=26 but only one is plotted"): this
        # used to compute ONE shared x/y window from `filtered_df`, which is the union
        # of every cell across EVERY type being plotted in this figure, and apply that
        # same window to every subplot regardless of which type it shows. If any single
        # cell anywhere in the figure (any type, even one bad RF fit) sits far from the
        # rest, that shared window balloons out to include it, and every OTHER
        # subplot's real cluster gets squeezed into a tiny corner -- cells were still
        # being plotted, just visually crushed to near-invisibility by an unrelated
        # outlier's zoom requirement. Now computes each subplot's zoom window from only
        # that subplot's own cell type.
        if b_zoom:
            for idx, ct in enumerate(cell_types):
                ax = axs[idx]
                ct_ids = list(d_ells_by_type[ct].keys())
                ct_df = filtered_df.query("cell_id in @ct_ids")
                if len(ct_df) == 0:
                    continue
                x_min, x_max = ct_df["center_x"].min(), ct_df["center_x"].max()
                y_min, y_max = ct_df["center_y"].min(), ct_df["center_y"].max()
                ax.set_xlim(
                    (x_min - n_pad) * scale_factor, (x_max + n_pad) * scale_factor
                )
                ax.set_ylim(
                    (y_min - n_pad) * scale_factor, (y_max + n_pad) * scale_factor
                )

        fig.suptitle(title, fontsize=15)

        return axs

    def plot_rf_portraits(
        self,
        noise_ids: Optional[List[int]] = None,
        cell_types: Optional[List[str]] = None,
        typing_file: Optional[str] = None,
        plot_radius: int = 10,
        scale_up: int = 4,
        cmap: str = "RdBu_r",
        minimum_n: int = 1,
        n_cols: Optional[int] = None,
        exclude_unknown: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Plot a grid of small per-cell receptive-field "portraits": each cell's own cropped,
        polarity-corrected raw spatial STA pixels centered on that cell's RF, rather than the
        fitted-ellipse mosaic that plot_rfs() draws. One figure is produced per cell type.

        Mirrors the lab's MATLAB plot_rf_portraits.m reference (crop raw RF pixels to a window
        around each cell's own center, polarity-correct, normalize, tile into a grid). Built on
        get_stas() (raw per-cell STAs read directly from the native .sta files via
        visionloader), the same source plot_stas() already uses -- NOT on d_spatial_maps /
        get_spatial_maps(), which depends on a separately-exported '<ss_version>_params.mat'
        file that most chunks don't actually have on disk (only a native Vision '.params' file).
        For each cell, the single time/color frame containing that cell's own peak STA
        deviation is used, then cropped to a small window around rf_params' center_x/center_y.

        Parameters:
            noise_ids (List[int]): A list of cell_ids to plot. Default None (all cells).

            cell_types (List[str]): A list of cell_type strings, (e.g. ['OnP', 'OffP']). Default None.

            typing_file (str): Typing file name used to determine cell types. If None, the 0th
            typing file associated with the analysis chunk is used. Default None.

            plot_radius (int): Half-width, in stixels, of the cropped window around each cell's
            RF center. Default 10.

            scale_up (int): Integer factor to upscale each cropped portrait for display
            (nearest-neighbor), matching the MATLAB reference's matrix_scaled_up. Default 4.

            cmap (str): Diverging colormap used to display polarity-corrected, normalized
            pixels (so a cell's peak deviation is always +1, its opposite pole -1). Default 'RdBu_r'.

            minimum_n (int): Minimum number of cells required for a cell type to be plotted.

            n_cols (int): Number of columns in the portrait grid. Defaults to ceil(sqrt(n_cells)).

            exclude_unknown (bool): If True (default), drop the 'Unknown' cell type from the
            auto-detected type list when cell_types=None. Has no effect if cell_types is given
            explicitly.

        Returns:
            dict of {cell_type: fig}, one figure per cell type plotted. Returns None if no cells
            match the given filters.

            The function will also plot the results automatically if you're in a jupyter
            notebook, but it does not call plt.show() on the figure.
        """
        # Convert individual cell type or cell id into list
        cell_types_was_none = cell_types is None

        if isinstance(cell_types, str):
            cell_types = [cell_types]
        if isinstance(noise_ids, int) or isinstance(noise_ids, float):
            noise_ids = [int(noise_ids)]

        # Parse typing file, use typing file 0 if none given
        if typing_file is None:
            try:
                typing_file = self.typing_files[0]
            except Exception:
                print(f"No typing files for {self.exp_name} {self.chunk_name}")
                return None

        if typing_file not in self.typing_files:
            print(f"{typing_file} Doesn't Exist in {self.exp_name} {self.chunk_name}")
            return None

        typing_file_idx = self.typing_files.index(typing_file)

        # Pull appropriate union of noise cell ids and cell types using given params.
        if noise_ids is None and cell_types is None:
            filtered_df = self.df_cell_params
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        elif noise_ids is None:
            filtered_df = self.df_cell_params.query(
                f"typing_file_{typing_file_idx} in @cell_types"
            )
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        elif cell_types is None:
            filtered_df = self.df_cell_params.query("cell_id in @noise_ids")
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        else:
            filtered_df = self.df_cell_params.query(
                f"typing_file_{typing_file_idx} in @cell_types and cell_id in @noise_ids"
            )
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())

        # Cell types auto-detected (not explicitly requested) skip 'Unknown' by default.
        if exclude_unknown and cell_types_was_none:
            cell_types = [ct for ct in cell_types if str(ct).strip().lower() != "unknown"]

        if len(filtered_df) == 0:
            print("No data found for the given noise_ids and cell_types.")
            return None

        # Remove cell types below minimum_n, same convention as plot_rfs
        too_few_cells = [
            ct
            for ct in cell_types
            if len(
                filtered_df.query(f"typing_file_{typing_file_idx} == @ct")[
                    "cell_id"
                ].values
            )
            < minimum_n
        ]
        for ct in too_few_cells:
            cell_types.remove(ct)

        cell_types = sorted(cell_types)

        # Pull raw STAs for exactly the cells being plotted, organized by cell type --
        # padded=True so the array's pixel grid lines up with rf_params' center_x/center_y
        # (both padded to numXChecks/numYChecks the same way; see get_rf_params()).
        plot_ids = list(
            filtered_df.query(f"typing_file_{typing_file_idx} in @cell_types")[
                "cell_id"
            ].values
        )
        d_stas = self.get_stas(
            noise_ids=plot_ids,
            cell_types=cell_types,
            typing_file=typing_file,
            padded=True,
            units="stixels",
        )

        def crop_portrait(cell_id, sta):
            # sta has shape (T, H, W, 3) -- find this cell's own peak deviation across
            # every time bin and color channel, same convention plot_stas() uses, then
            # take just that single spatial frame/channel for the portrait.
            peak_idx = np.unravel_index(np.argmax(np.abs(sta)), sta.shape)
            t_idx, c_idx = peak_idx[0], peak_idx[3]
            spat_map = sta[t_idx, :, :, c_idx]

            cy = int(round(self.rf_params[cell_id]["center_y"]))
            cx = int(round(self.rf_params[cell_id]["center_x"]))
            r = plot_radius
            window = np.zeros((2 * r + 1, 2 * r + 1))

            y0, y1 = cy - r, cy + r + 1
            x0, x1 = cx - r, cx + r + 1
            src_y0, src_y1 = max(y0, 0), min(y1, spat_map.shape[0])
            src_x0, src_x1 = max(x0, 0), min(x1, spat_map.shape[1])
            dst_y0, dst_x0 = src_y0 - y0, src_x0 - x0
            dst_y1 = dst_y0 + (src_y1 - src_y0)
            dst_x1 = dst_x0 + (src_x1 - src_x0)

            if src_y1 > src_y0 and src_x1 > src_x0:
                window[dst_y0:dst_y1, dst_x0:dst_x1] = spat_map[
                    src_y0:src_y1, src_x0:src_x1
                ]

            # Polarity-correct so the strongest deviation from zero is always positive,
            # then normalize to [-1, 1] for a shared, comparable color scale across cells.
            if np.any(window):
                peak = window.flat[np.argmax(np.abs(window))]
                if peak < 0:
                    window = -window
                max_abs = np.max(np.abs(window))
                if max_abs > 0:
                    window = window / max_abs

            if scale_up > 1:
                window = np.kron(window, np.ones((scale_up, scale_up)))

            return window

        d_figs = {}
        for ct in cell_types:
            ct_ids = list(d_stas.get(ct, {}).keys())
            if len(ct_ids) == 0:
                continue

            n_cells = len(ct_ids)
            cols = n_cols or int(np.ceil(np.sqrt(n_cells)))
            rows = int(np.ceil(n_cells / cols))

            fig, axs = plt.subplots(
                nrows=rows,
                ncols=cols,
                figsize=(1.6 * cols, 1.6 * rows),
                layout="constrained",
            )
            axs = np.array(axs).flatten() if n_cells > 1 else np.array([axs])

            for idx, cell_id in enumerate(ct_ids):
                ax = axs[idx]
                portrait = crop_portrait(cell_id, d_stas[ct][cell_id])
                # interpolation='nearest' -- these are raw stixel pixels (the whole point
                # of a portrait vs. the fitted-ellipse mosaic), so matplotlib's default
                # imshow interpolation ('antialiased', which blurs/smooths neighboring
                # pixels together) was defeating that and making everything look
                # over-smoothed. Nearest gives crisp per-stixel blocks instead.
                ax.imshow(portrait, cmap=cmap, vmin=-1, vmax=1, interpolation="nearest")
                ax.set_title(str(cell_id), fontsize=8)
                ax.set_xticks([])
                ax.set_yticks([])

            num_axes = rows * cols
            for i in range(n_cells, num_axes):
                fig.delaxes(cast(Axes, axs[i]))

            fig.suptitle(f"{ct} RF portraits, (n = {n_cells})", fontsize=13)
            d_figs[ct] = fig

        return d_figs

    def plot_timecourses(
        self,
        noise_ids: Optional[List[int]] = None,
        cell_types: Optional[List[str]] = None,
        typing_file: Optional[str] = None,
        units: str = "ms",
        std_scaling: float = 2,
        minimum_n: int = 1,
        roi: Optional[Dict[str, float]] = None,
        roi_units: str = "pixels",
        exclude_unknown: bool = True,
        xlim_left_ms: float = -250.0,
    ) -> Optional[np.ndarray[Any, np.dtype[np.object_]]]:
        """
        Method for plotting the timecourses for a given list of cell ids, cell types, or a union of both. If no cell_ids
        or cell types are given, the timecourses for all cells in the analysis chunk are plotted by type. The mean is
        plotted as a line with a shaded region defined by the standard deviation * std_scaling.

        Parameters:
            noise_ids (List[int]): A list of cell_ids to plot. Default None.

            cell_types (List[str]): A list of cell_type strings, (e.g. ['OnP', 'OffP']). Default None.

            typing_fyle (str): A typing file name which is used to determine the cell types for any given cell_ids.
            If none is given, the 0th typing file associated with the analysis chunk is used. Default None.

            units (str): Units to use when plotting the timecourse. Must be either 'ms', 'milliseconds', 's',
            or 'seconds'. Default 'mss'.

            std_scaling (float): Factor used to scale the standard deviation used for plotting the shaded
            region around each timecourse. Default 2

            roi (dict): roi definition as a dictionary with 4 values. 'x_min', 'x_max', 'y_min', 'y_max'.
            These define the vertical and horizontal lines that define the region of interest

            roi_units (str): Units to use when defining the region of interest. Must be 'pixels', 'microns',
            or 'stixels'. Default 'pixels'.

            exclude_unknown (bool): If True (default), drop the 'Unknown' cell type from the
            auto-detected type list when cell_types=None. Has no effect if cell_types is given
            explicitly.

            xlim_left_ms (float): Left edge of the plotted x-axis, in milliseconds (converted to
            the requested `units` automatically). The full timecourse is still computed/averaged
            over its entire window regardless of this value -- this only crops what's shown, so
            the actual (usually short, biphasic) response is easier to see instead of being
            squeezed into a sliver of a much longer window. Default -250.0.

        Returns:
            axs (axes): Axes object that contains all of the axes used in the timecourses figure. There
            will be as many axes as there are cell_types represented in the plot.

            The function will also plot the results automatically if you're in a jupyter notebook, but it does not call
            plt.show() on the figure. You need to call plt.show() manually if running as part of a REPL or script.

        """
        # Convert individual cell type or cell id into list
        cell_types_was_none = cell_types is None

        if isinstance(cell_types, str):
            cell_types = [cell_types]

        if isinstance(noise_ids, int) or isinstance(noise_ids, float):
            noise_ids = [int(noise_ids)]

        # Parse units input
        if "ms" in units.lower() or "milliseconds" in units.lower():
            scale_factor = 1
        elif "s" in units.lower() or "seconds" in units.lower():
            scale_factor = 1e-3
        else:
            raise NameError(
                "Units string must be 'ms', 'milliseconds', 's' or 'seconds'"
            )

        # Parse typing file, use typing file 0 if none given
        if typing_file is None:
            try:
                typing_file = self.typing_files[0]
            except:
                print(f"No typing files for {self.exp_name} {self.chunk_name}")
                return

        if typing_file not in self.typing_files:
            print(f"{typing_file} Doesn't Exist in {self.exp_name} {self.chunk_name}")
            return

        typing_file_idx = self.typing_files.index(typing_file)

        # Filter for union of cell ids and cell types provided by user
        if noise_ids is None and cell_types is None:
            filtered_df = self.df_cell_params
            noise_ids = list(filtered_df["cell_id"].values)
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        elif noise_ids is None:
            filtered_df = self.df_cell_params.query(
                f"typing_file_{typing_file_idx} in @cell_types"
            )
            noise_ids = list(filtered_df["cell_id"].values)
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        elif cell_types is None:
            filtered_df = self.df_cell_params.query(f"cell_id in @noise_ids")
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())
        else:
            filtered_df = self.df_cell_params.query(
                f"typing_file_{typing_file_idx} in @cell_types and cell_id in @noise_ids"
            )
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())

        # Filter for cells inside region of interest (roi) if one was provided
        if roi is not None:
            roi_cell_ids = self.get_cells_by_region(roi=roi, units=roi_units)
            filtered_df = filtered_df.query("cell_id in @roi_cell_ids")
            cell_types = sorted(filtered_df[f"typing_file_{typing_file_idx}"].unique())

        # Cell types auto-detected (not explicitly requested) skip 'Unknown' by default --
        # placed after the roi filter above, since that block re-derives cell_types from
        # filtered_df and would otherwise silently reintroduce 'Unknown'.
        if exclude_unknown and cell_types_was_none:
            cell_types = [ct for ct in cell_types if str(ct).strip().lower() != "unknown"]

        # Check that we actually have cells to plot
        if len(filtered_df) == 0:
            print("No data found for the given noise_ids and cell_types.")
            return

        # Remove cells below minimum threshold
        too_few_cells = [
            ct
            for ct in cell_types
            if len(
                filtered_df.query(f"typing_file_{typing_file_idx} == @ct")[
                    "cell_id"
                ].values
            )
            < minimum_n
        ]

        for ct in too_few_cells:
            cell_types.remove(ct)

        # Organize cells into dictionary and pass that dictionary to get_timecourses() function
        d_noise_ids_by_type = {
            ct: filtered_df.query(f"typing_file_{typing_file_idx} == @ct")[
                "cell_id"
            ].values
            for ct in cell_types
        }
        d_timecourses_by_type = get_timecourses(self, d_noise_ids_by_type)

        # Plot timecourses, one axis per cell type
        rows = np.ceil(len(cell_types) / 4).astype(int)
        cols = np.min([(len(cell_types) - 1 % 4) + 1, 4])
        size = (4 * cols, int(3 * rows))

        fig, axs = plt.subplots(
            nrows=rows, ncols=cols, figsize=size, layout="constrained"
        )

        if cols != 1:
            axs = np.array(axs).flatten()
        else:
            axs = np.array([axs])

        for idx, ct in enumerate(cell_types):
            ax = axs[idx]

            time_vals = (
                np.linspace(-491.66, 8.33, len(d_timecourses_by_type[ct]["g_mean"]))
                * scale_factor
            )

            if np.array_equal(
                d_timecourses_by_type[ct]["r_mean"], d_timecourses_by_type[ct]["g_mean"]
            ):
                g_err_top = (
                    d_timecourses_by_type[ct]["g_mean"]
                    + d_timecourses_by_type[ct]["g_std"] * std_scaling
                )
                g_err_bottom = (
                    d_timecourses_by_type[ct]["g_mean"]
                    - d_timecourses_by_type[ct]["g_std"] * std_scaling
                )
                ax.plot(time_vals, d_timecourses_by_type[ct]["g_mean"], "-g")
                ax.fill_between(
                    time_vals, g_err_bottom, g_err_top, alpha=0.4, color="g"
                )
            else:
                r_err_top = (
                    d_timecourses_by_type[ct]["r_mean"]
                    + d_timecourses_by_type[ct]["r_std"] * std_scaling
                )
                r_err_bottom = (
                    d_timecourses_by_type[ct]["r_mean"]
                    - d_timecourses_by_type[ct]["r_std"] * std_scaling
                )
                ax.plot(time_vals, d_timecourses_by_type[ct]["r_mean"], "-r")
                ax.fill_between(
                    time_vals, r_err_bottom, r_err_top, alpha=0.4, color="r"
                )

                g_err_top = (
                    d_timecourses_by_type[ct]["g_mean"]
                    + d_timecourses_by_type[ct]["g_std"] * std_scaling
                )
                g_err_bottom = (
                    d_timecourses_by_type[ct]["g_mean"]
                    - d_timecourses_by_type[ct]["g_std"] * std_scaling
                )
                ax.plot(time_vals, d_timecourses_by_type[ct]["g_mean"], "-g")
                ax.fill_between(
                    time_vals, g_err_bottom, g_err_top, alpha=0.4, color="g"
                )

            b_err_top = (
                d_timecourses_by_type[ct]["b_mean"]
                + d_timecourses_by_type[ct]["b_std"] * std_scaling
            )
            b_err_bottom = (
                d_timecourses_by_type[ct]["b_mean"]
                - d_timecourses_by_type[ct]["b_std"] * std_scaling
            )
            ax.plot(time_vals, d_timecourses_by_type[ct]["b_mean"], "-b")
            ax.fill_between(time_vals, b_err_bottom, b_err_top, alpha=0.4, color="b")

            ax.set_xlim([xlim_left_ms * scale_factor, time_vals[-1]])
            ax.axvline(0, color="k", linestyle="--", linewidth=1, alpha=0.6)
            ax.axhline(0, color="grey", linestyle="--", linewidth=1, alpha=0.4)

            ax.set_ylabel(f"STA (arb. units)")
            ax.set_xlabel(f"Time ({units})")

            ax.set_title(
                f"{ct}, (n = {d_timecourses_by_type[ct]['r_timecourses'].shape[0]})"
            )

        # Remove any empty axes
        num_axes = rows * cols
        empty_axes = num_axes - len(cell_types)

        for i in range(empty_axes):
            fig.delaxes(cast(Axes, axs[num_axes - 1 - i]))

        fig.suptitle("Timecourse by Cell Type", fontsize=15)

        return axs

    def get_stas(
        self,
        noise_ids: int | List[int] | np.ndarray | None = None,
        cell_types: str | List[str] | None = None,
        typing_file: str | None = None,
        padded: bool = True,
        units: str = "stixels",
    ) -> dict:
        """
        Function for loading the STAs of a given list of cell types and/or noise ids. If both are given, will only
        pull the union of the two.

        Parameters:
            noise_ids (int or List[int]): list of cell ids, optional, default is None

            cell_types (str or List[str]): list of cell types, optional, default is None

            typing_file (str): name of a typing file to use for cell type classification

            padded (bool): Boolean value to indicate if any crop should be removed relative to the actual size of the
            noise frame. Most STAs are cropped for the sake of memory, but it makes them inaccurate relative to the
            stimulus. Default is True.

            units (str): Either 'stixels', 'pixels', or 'microns'. This will scale the STAs to the appropriate units
            using nearest neighbor scaling.

        Returns:
            all_stas (numpy array or dict of numpy arrays): numpy array that contains all STAs. If a typing file is given and/or
            cell type info is available, the output will have cell type information. Otherwise it
            will not.
        """

        # Convert individual Cell ID or Cell Type into a list
        if isinstance(noise_ids, int) or isinstance(noise_ids, float):
            noise_ids = [int(noise_ids)]

        if isinstance(cell_types, str):
            cell_types = [cell_types]


        # Parse units to make sure they're valid
        if "pixels" in units.lower():
            unit_scaling = self.pixels_per_stixel
        elif "microns" in units.lower():
            unit_scaling = self.microns_per_stixel
        elif "stixels" in units.lower():
            unit_scaling = 1
        else:
            raise Exception("Units must be 'pixels', 'microns' or 'stixels'")

        # Combined parsing of noise_ids, cell_types, and typing_file... a bit hard to follow
        # may split this up like it is in plot_rfs() and plot_timecourses()
        if noise_ids is None:
            # Neither noise IDs nor cell types provided
            if cell_types is None:
                if not self.typing_files:
                    print(
                        "WARNING: No typing files exist for this chunk, will not organize cells by type"
                    )
                    filtered_df = self.df_cell_params
                    cell_ids = filtered_df["cell_id"].to_numpy()
                    available_types = None
                    typing_file_idx = None
                else:
                    print(
                        "WARNING: Loading all STAs... this will take up a huge amount of memory"
                    )
                    if typing_file is None:
                        typing_file = self.typing_files[0]

                    typing_file_idx = self.typing_files.index(typing_file)

                    filtered_df = self.df_cell_params
                    cell_ids = filtered_df["cell_id"].to_numpy()
                    available_types = sorted(
                        filtered_df[f"typing_file_{typing_file_idx}"].unique()
                    )

            # Cell types provided, no IDs provided
            else:
                if not self.typing_files:
                    raise ValueError(
                        "No typing files exist for this chunk, try again without cell type argument"
                    )
                else:
                    if typing_file is None:
                        typing_file = self.typing_files[0]

                    typing_file_idx = self.typing_files.index(typing_file)

                    filtered_df = self.df_cell_params.query(
                        f"typing_file_{typing_file_idx} in @cell_types"
                    )
                    cell_ids = filtered_df["cell_id"].to_numpy()
                    available_types = sorted(
                        filtered_df[f"typing_file_{typing_file_idx}"].unique()
                    )

        else:
            # Noise IDs provided but no cell types provided
            if cell_types is None:
                if not self.typing_files:
                    print(
                        "WARNING: No typing files exist for this chunk, will not organize cells by type"
                    )

                    filtered_df = self.df_cell_params.query("cell_id in @noise_ids")
                    cell_ids = filtered_df["cell_id"].to_numpy()
                    available_types = None
                    typing_file_idx = None
                else:
                    if typing_file is None:
                        typing_file = self.typing_files[0]

                    typing_file_idx = self.typing_files.index(typing_file)

                    filtered_df = self.df_cell_params.query("cell_id in @noise_ids")
                    cell_ids = filtered_df["cell_id"].to_numpy()
                    available_types = sorted(
                        filtered_df[f"typing_file_{typing_file_idx}"].unique()
                    )
            else:
                # Noise IDs and Cell Types provided
                if not self.typing_files:
                    raise ValueError(
                        "No typing files exist for this chunk, try again without the cell type"
                    )
                else:
                    if typing_file is None:
                        typing_file = self.typing_files[0]

                    typing_file_idx = self.typing_files.index(typing_file)

                    filtered_df = self.df_cell_params.query(
                        f"cell_id in @noise_ids and typing_file_{typing_file_idx} in @cell_types"
                    )
                    cell_ids = filtered_df["cell_id"].to_numpy()
                    available_types = sorted(
                        filtered_df[f"typing_file_{typing_file_idx}"].unique()
                    )

        # Pull STAs and organize by cell id alone, or nested inside a dictionary organized by cell id.
        # UPDATED (Claude, per yas -- AssertionError from vl.STAReader: "analysis_folder_path"
        # doesn't exist): this used to hardcode ANALYSIS_DIR/exp_name/chunk_name/ss_version as the
        # only place to look for the .sta file, unlike get_analysis_vcd() (used to build self.vcd,
        # which is where rf_params/timecourses come from), which tries many DATA_DIR/ANALYSIS_DIR
        # candidate layouts via _resolve_vision_data_path(). That's why rf_params could load fine
        # while get_stas()/plot_stas()/plot_rf_portraits() hit a hard AssertionError for the same
        # chunk -- the .sta file was never actually missing, just not where this one hardcoded path
        # was looking. Now uses the same resolver as everything else in this class.
        sta_dir = _resolve_vision_data_path(self.exp_name, self.chunk_name, self.ss_version)
        # The .sta file itself is sometimes named for the chunk (e.g. "data005.sta") and
        # sometimes for the spike-sorting version (e.g. "kilosort2.5.sta"), depending on
        # layout -- same ambiguity get_analysis_vcd() already resolves for self.vcd's
        # dataset_name. Prefer chunk_name, fall back to ss_version if that file isn't there.
        sta_dataset_name = self.chunk_name
        if not os.path.isfile(os.path.join(sta_dir, f"{sta_dataset_name}.sta")):
            sta_dataset_name = self.ss_version
        sta_reader = vl.STAReader(sta_dir, sta_dataset_name)

        if available_types is None:
            id_dict = dict()
            for cell_id in cell_ids:
                # Pull Raw STA
                data = sta_reader.get_sta_for_cell_id(cell_id)
                sta = np.stack([data.red, data.green, data.blue])
                sta = np.transpose(sta, (3, 1, 2, 0))
                if unit_scaling > 1:
                    sta = zoom(
                        sta, zoom=[1.0, unit_scaling, unit_scaling, 1.0], order=0
                    )
                id_dict[cell_id] = sta

            d_stas = id_dict
        else:
            ct_dict = dict()
            for ct in available_types:
                ct_ids = filtered_df.query(f"typing_file_{typing_file_idx} == @ct")[
                    "cell_id"
                ].to_numpy()
                id_dict = dict()
                for cell_id in ct_ids:
                    data = sta_reader.get_sta_for_cell_id(cell_id)
                    sta = np.stack([data.red, data.green, data.blue])
                    sta = np.transpose(sta, (3, 1, 2, 0))

                    if padded:
                        left_pad = int(self.deltaXChecks)
                        right_pad = int(
                            self.numXChecks - self.staXChecks - self.deltaXChecks
                        )
                        top_pad = int(self.deltaYChecks)
                        bottom_pad = int(
                            self.numYChecks - self.staYChecks - self.deltaYChecks
                        )

                        pad_width_config = [
                            (0, 0),
                            (bottom_pad, top_pad),
                            (left_pad, right_pad),
                            (0, 0),
                        ]
                        sta = np.pad(
                            sta, pad_width_config, mode="constant", constant_values=0
                        )

                    if unit_scaling > 1:
                        sta = zoom(
                            sta, zoom=[1.0, unit_scaling, unit_scaling, 1.0], order=0
                        )
                    id_dict[cell_id] = sta

                ct_dict[ct] = id_dict

            d_stas = ct_dict

        return d_stas

    def plot_stas(
        self,
        noise_ids: Optional[int | List[int]] = None,
        cell_types: Optional[str | List[str]] = None,
        typing_file: Optional[str] = None,
        cols: int = 4,
        padded: bool = False,
        units: str = "stixels",
    ) -> List[np.ndarray] | List[Axes]:
        """
        Method for plotting STAs for a list of cell ids, a list of cell types, or the union of the two. The
        user also has the option of providing a typing file to use. If there exists a typing file or one
        is provided, the function will plot STAs in separate figures organized by cell type. One figure per
        cell type, one STA per axis, number of axes = number of cells of that cell type.

        Parameters:
            noise_ids (int or List[int]) a single cell id or list of cell ids to be plotted. Optional, default None.

            cell_types (str or List[str]) a single cell type or list of cell types to be plotted. Optional, default None.

            typing_file (str): The name of a typing file to use for linking cell types to cell ids. If no typing file is given
            typing file [0] from the analysis chunk is used. If there are no typing files, only one figure is plotted, with no
            cell type information.

            cols (int): number of columns to use in the resulting figure(s).

            padded (bool): Boolean value to indicate if any crop should be removed relative to the actual size of the
            noise frame. Most STAs are cropped for the sake of memory, but it makes them inaccurate relative to the
            stimulus. Default value for plotting purposes is False.

            units (str): units to plot the STAs in. Must be stixels, pixels, or microns. Default is stixels. If other units
            are used, the STA is scaled using nearest neighbor interpolation.

        Returns:
            sta_axes: will return a list of Axes objects (multiple single cells of different types) or a list of numpy arrays
            of axes (multiple cells of multiple types).

            The function will also plot the results automatically if you're in a jupyter notebook, but it does not call
            plt.show() on the figure. You need to call plt.show() manually if running as part of a REPL or script.
        """

        # All unit parsing and checking of data types done in get_stas()
        d_stas = self.get_stas(
            noise_ids=noise_ids,
            cell_types=cell_types,
            typing_file=typing_file,
            padded=padded,
            units=units,
        )

        all_axes = []
        # Plot STAs organized by one figure per cell type
        if isinstance(list(d_stas.keys())[0], str):
            # This indicates that the dictionary is organized by cell type
            available_types: List[str] = sorted(list(d_stas.keys()))

            for ct_idx, ct in enumerate(available_types):
                cell_ids = list(d_stas[ct].keys())

                rows = np.ceil(len(cell_ids) / cols).astype(int)
                if len(cell_ids) > 1:
                    fig, ax = plt.subplots(
                        nrows=rows,
                        ncols=cols,
                        figsize=(5 * cols, 3.5 * rows),
                        layout="constrained",
                    )
                    ax = ax.flatten()
                else:
                    fig, ax = plt.subplots(figsize=(5, 3.5), layout="constrained")
                    ax = [ax]

                for c_idx, cell_id in enumerate(cell_ids):
                    sta = d_stas[ct][cell_id]
                    min_index = np.unravel_index(np.argmin(sta), sta.shape)
                    max_index = np.unravel_index(np.argmax(sta), sta.shape)

                    if np.abs(np.min(sta)) > np.abs(np.max(sta)):
                        timebin_to_plot = min_index[0]
                    else:
                        timebin_to_plot = max_index[0]

                    sta_img = (sta[timebin_to_plot, :, :, :] + 1) / 2
                    ax[c_idx].imshow(sta_img)
                    ax[c_idx].set_title(f"Cell ID #{cell_id}")
                    ax[c_idx].set_xlabel(f"{units}")
                    ax[c_idx].set_ylabel(f"{units}")

                if self.deltaXChecks > 0 and not padded:
                    fig.suptitle(f"Cropped {ct} STAs")
                else:
                    fig.suptitle(f"{ct} STAs")

                if len(cell_ids) > 1:
                    # Delete unused axes
                    num_axes = rows * cols
                    empty_axes = num_axes - len(cell_ids)

                    for i in range(empty_axes):
                        fig.delaxes(ax[num_axes - 1 - i])

                all_axes.append(ax)

        # No cell types, plot all STAs in a single figure
        else:
            assert isinstance(list(d_stas.keys())[0], int), (
                f"The keys in the sta dict should either be ints or strs, yours is a {type(list(d_stas.keys())[0])}"
            )
            # This indicates the sta dictionary is organized by cell id and has no types associated with it.
            cell_ids = list(d_stas.keys())

            rows = np.ceil(len(cell_ids) / cols).astype(int)
            fig, ax = plt.subplots(
                nrows=rows,
                ncols=cols,
                figsize=(5 * cols, 3.5 * rows),
                layout="constrained",
            )

            if rows * cols > 1:
                ax = ax.flatten()
            else:
                ax = [ax]

            for c_idx, cell_id in enumerate(cell_ids):
                sta = d_stas[cell_id]
                min_index = np.unravel_index(np.argmin(sta), sta.shape)
                max_index = np.unravel_index(np.argmax(sta), sta.shape)

                if np.abs(np.min(sta)) > np.abs(np.max(sta)):
                    timebin_to_plot = min_index[0]
                else:
                    timebin_to_plot = max_index[0]

                sta_img = (sta[timebin_to_plot, :, :, :] + 1) / 2
                ax[c_idx].imshow(sta_img)
                ax[c_idx].set_title(f"Cell ID #{cell_id}")
                ax[c_idx].set_xlabel("Stixels X")
                ax[c_idx].set_ylabel("Stixels Y")

            if self.deltaXChecks > 0 and not padded:
                fig.suptitle(f"Cropped STAs by Cell ID")
            else:
                fig.suptitle(f"STAs by Cell ID")

            if len(cell_ids) > 1:
                # Delete unused axes
                num_axes = rows * cols
                empty_axes = num_axes - len(cell_ids)

                for i in range(empty_axes):
                    fig.delaxes(ax[num_axes - 1 - i])

            all_axes.append(ax)

        return all_axes

    def export_to_pkl(self, file_path: str):
        d_out = self.__dict__.copy()
        # Pop out vcd
        d_out.pop("vcd")
        with open(file_path, "wb") as f:
            pickle.dump(d_out, f)

        if self.verbose:
            print(f"AnalysisChunk exported to {file_path}")

    def __repr__(self):
        str_self = f"{self.__class__.__name__} with properties:\n"
        str_self += f"  exp_name: {self.exp_name}\n"
        str_self += f"  chunk_name: {self.chunk_name}\n"
        str_self += f"  ss_version: {self.ss_version}\n"
        str_self += f"  noise_protocol: {self.noise_protocol}\n"
        str_self += f"  data_files: {self.data_files}\n"
        str_self += f"  typing_files: {self.typing_files}\n"
        str_self += f"  vcd: {self.vcd}\n"
        str_self += (
            f"  d_EIs dictionary containing EIs for {len(self.cell_ids)} cell IDs\n"
        )
        str_self += (
            f"  d_ISIs dictionary containing ISIs for {len(self.cell_ids)} cell IDs\n"
        )
        str_self += f"  d_timecourses dictionary containing dictionary with 'red' 'green' and 'blue' timecourses for {len(self.cell_ids)} cell IDs\n"
        str_self += f"  numXChecks: {self.numXChecks}\n"
        str_self += f"  numYChecks: {self.numYChecks}\n"
        str_self += f"  staXChecks: {self.staXChecks}\n"
        str_self += f"  staYChecks: {self.staYChecks}\n"
        str_self += f"  canvas_size: {self.canvas_size}\n"
        str_self += f"  microns_per_pixel: {self.microns_per_pixel}\n"
        str_self += f"  cell_ids of length: {len(self.cell_ids)}\n"
        str_self += f"  rf_params with fields: {list(self.rf_params[self.cell_ids[0]].keys())}\n"
        str_self += f"  df_cell_params of shape: {self.df_cell_params.shape}\n"

        if hasattr(self, "d_spatial_maps"):
            str_self += f"  d_spatial_maps with {len(self.d_spatial_maps)} cells\n"
        else:
            str_self += "  d_spatial_maps not loaded\n"
        return str_self
