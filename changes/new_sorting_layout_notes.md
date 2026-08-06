# New sorting-layout compatibility notes

## Summary
These changes were made to keep notebook-based analysis working when the sorted data layout no longer matches the older chunk-directory convention.

## What changed
- The importer now discovers sorting chunks from both legacy chunk folders and newer data-directory layouts such as `data000`, `data001`, and algorithm folders like `kilosort25`.
- Existing experiments can now be refreshed explicitly instead of being skipped as already present.
- Notebook-facing helpers now tolerate missing or relocated typing files and missing SortingChunk rows so the analysis workflow can still produce a summary and cell-typing table.

## Verification
The compatibility behavior is covered by the regression test file at `tests/test_database_pop_structure.py`.

## Reproduction notes
If you need to reproduce the newer layout locally, create a directory like:

```text
<experiment_root>/kilosort25/data000/ksfiles/
```

and ensure the expected sorting outputs (for example `cluster_KSLabel.tsv` or similar files) are present there.
