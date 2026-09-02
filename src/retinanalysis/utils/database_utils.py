from retinanalysis.utils import USER, H5_DIR, META_DIR, TAGS_DIR, database_pop
from retinanalysis._database import get_schema_module, schema
from typing import List


def populate_database(
    username=USER,
    h5_dir=H5_DIR,
    meta_dir=META_DIR,
    tags_dir=TAGS_DIR,
    refresh_existing: bool = False,
    verbose: bool = True,
):
    # Wraps the actual ingestion in scrollable_prints() here, inside the function
    # itself, instead of requiring every notebook to remember
    # `with ra.scrollable_prints():` around this call -- so the per-file ingestion
    # output is always collapsed into a small scrollable box, no matter where/how
    # populate_database() gets called. Set verbose=False to suppress that output
    # entirely instead of just collapsing it (e.g. the "Already in database" /
    # "Refreshing existing experiment" / cell-type-file deletion counts that print
    # per experiment during a refresh). Imported lazily (not at module level) for
    # the same circular-import reason contrast_response_utils.py's own lazy
    # `import retinanalysis` calls exist -- database_utils.py loads early during
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
            verbose=verbose,
        )


def reload_experiment_data(
    exp_name,
    username=USER,
    h5_dir=H5_DIR,
    meta_dir=META_DIR,
    tags_dir=TAGS_DIR,
    verbose: bool = True,
):

    existing = schema.Experiment() & {"exp_name": exp_name}
    if verbose:
        existing.delete(prompt=False)
    else:
        database_pop._delete_quiet(existing)

    populate_database(username, h5_dir, meta_dir, tags_dir, verbose=verbose)


def delete_experiments(exp_names: List[str]):

    for exp in exp_names:
        (schema.Experiment() & {"exp_name": exp}).delete(prompt=False)


def purge_database():
    all_experiments = schema.Experiment()
    all_exp_names = all_experiments.to_arrays("exp_name")

    for exp in all_exp_names:
        (schema.Experiment() & {"exp_name": exp}).delete(prompt=False)
