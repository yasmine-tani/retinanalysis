from retinanalysis.utils import USER, H5_DIR, META_DIR, TAGS_DIR, database_pop
from retinanalysis._database import get_schema_module, schema
from typing import List


def populate_database(
    username=USER,
    h5_dir=H5_DIR,
    meta_dir=META_DIR,
    tags_dir=TAGS_DIR,
    refresh_existing: bool = False,
):
    # UPDATED 2026-08-12 (Claude, per yas): wraps the actual ingestion in
    # scrollable_prints() here, inside the function itself, instead of requiring every
    # notebook to remember `with ra.scrollable_prints():` around this call -- so the
    # per-file ingestion output is always collapsed into a small scrollable box, no
    # matter where/how populate_database() gets called. Imported lazily (not at module
    # level) for the same circular-import reason contrast_response_utils.py's own
    # lazy `import retinanalysis` calls exist -- database_utils.py loads early during
    # package init.
    from retinanalysis.utils.contrast_response_utils import scrollable_prints

    schema_module = get_schema_module()

    with scrollable_prints():
        return database_pop.append_data(
            h5_dir,
            meta_dir,
            tags_dir,
            username,
            schema_module,
            refresh_existing=refresh_existing,
        )


def reload_experiment_data(
    exp_name, username=USER, h5_dir=H5_DIR, meta_dir=META_DIR, tags_dir=TAGS_DIR
):

    (schema.Experiment() & {"exp_name": exp_name}).delete(prompt=False)

    populate_database(username, h5_dir, meta_dir, tags_dir)


def delete_experiments(exp_names: List[str]):

    for exp in exp_names:
        (schema.Experiment() & {"exp_name": exp}).delete(prompt=False)


def purge_database():
    all_experiments = schema.Experiment()
    all_exp_names = all_experiments.to_arrays("exp_name")

    for exp in all_exp_names:
        (schema.Experiment() & {"exp_name": exp}).delete(prompt=False)
