# Lazy proxy for the DataJoint schema. This preserves ``ra.schema`` while
# avoiding a database connection during ``import retinanalysis``.
from retinanalysis._database import schema

# Import various data and analysis directories directly.
# Settings doesn't reference any of the utils or classes so it should be
# safe to import first without circular import issues
from . import config
from .config import settings
from .config.settings import (ANALYSIS_DIR,
                              DATA_DIR,
                              RAW_DIR,
                              H5_DIR,
                              META_DIR,
                              TAGS_DIR,
                              QUERY_DIR,
                              USER)

# Utilities imported first. They should NEVER reference the classes for anything
# other than type hints, which should be done using the TYPE_CHECKING and 
# __future__ annotations imports (see vision_utils). This avoids problems with
# circular imports
from . import utils
from .utils import database_pop
from .utils.database_pop import *

from .utils import database_utils
from .utils.database_utils import *

from .utils import datajoint_utils
from .utils.datajoint_utils import *

from .utils import ei_utils
from .utils.ei_utils import *

# NEW 2026-07-28 (Claude, per yas): F1/F0, DSI/OSI, and Naka-Rushton fitting for
# grating-based protocols (direction/orientation selectivity, contrast response).
# Doesn't reference any classes, so safe to import here alongside the other utils.
from .utils import tuning
from .utils.tuning import *

# NEW 2026-07-29 (Claude, per yas): spike-train cross-correlation analysis (compute_ccf,
# build_master_mapping_table) for correlated-spiking analysis across NDF light levels.
# Only imports datajoint_utils at module level; AnalysisChunk/MEAResponseBlock/cluster_match
# are imported lazily inside functions to avoid circular imports (same pattern already used
# in vision_utils.py and datajoint_utils.py's plot_mosaics_for_datasets).
from .utils import correlation_utils
from .utils.correlation_utils import *

# NEW 2026-08-03 (Claude, per yas -- "why cant we just save a file with just my defitions
# thats ouside the notebook"): the contrast-response demo's shared load/plot functions
# (load_contrast_section, plot_crf_across_ndfs, plot_crf, plot_raster_overview_by_cell_type,
# plot_rasters_for_cell_type, _raster_for_cell), moved here from a single large notebook cell
# in demos/7_contrast_response_demo.ipynb. Only imports numpy/pandas/matplotlib at module
# level; `import retinanalysis as ra` is done lazily inside the two functions that need it
# (load_contrast_section, plot_crf_across_ndfs), same circular-import-avoidance pattern as
# correlation_utils.py/datajoint_utils.py.
from .utils import contrast_response_utils
from .utils.contrast_response_utils import *

from .utils import spike_detector

from .utils import regen
from .utils.regen import *

from .utils import vision_utils
from .utils.vision_utils import *

from .utils import parse_data

# Import preprocessing
from . import preprocessing
from .preprocessing import sta
from .preprocessing import rfs
from .preprocessing import ks_to_vision


# Import classes last
from . import classes
from .classes import analysis_chunk
from .classes.analysis_chunk import AnalysisChunk

from .classes import stim
from .classes.stim import (StimBlock,
                           MEAStimBlock,
                           MEAStimGroup,
                           create_mea_stim_group,
                           D_REGEN_FXNS)

from .classes import response
from .classes.response import (ResponseBlock,
                               MEAResponseBlock,
                               SCResponseBlock,
                               MEAResponseGroup,
                               check_frame_times,
                               create_mea_response_group)

from .classes import qc
from .classes.qc import MEAQC

from .classes import raw
from .classes.raw import RawTraces

# Pipeline must be imported last as it references the above pieces.
from .classes import mea_pipeline
from .classes.mea_pipeline import (MEAPipeline,
                                   create_mea_pipeline)
from .classes import sc_pipeline
from .classes import dedup
from .classes.dedup import DedupBlock

# datajoint installs a sys.excepthook (see datajoint/logging.py) whose formatter
# drops exc_info, silently swallowing tracebacks for anything not caught by
# .populate(). Restore the default hook so uncaught exceptions print normally.
import sys as _sys
_sys.excepthook = _sys.__excepthook__
del _sys
