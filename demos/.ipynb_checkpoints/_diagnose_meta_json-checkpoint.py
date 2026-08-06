# Read-only diagnostic: scans every meta JSON file in META_DIR and reports which
# ones are missing the keys append_experiment/append_animal/append_preparation/
# append_cell require via direct dict indexing (experiment["rig_type"], etc.) --
# any of these being absent is exactly what crashes populate_database() with a
# KeyError partway through, silently blocking every experiment queued after it.
#
# This does NOT touch the database or modify any files -- safe to run any time.
#
# Usage: paste into a notebook cell (after `import retinanalysis as ra`) or run
# as a script from an environment where `retinanalysis` is importable.

import json
import os
import retinanalysis as ra
from retinanalysis.config.settings import META_DIR

REQUIRED_EXPERIMENT_KEYS = ["rig_type", "animals"]
REQUIRED_ANIMAL_KEYS = ["uuid", "preparations"]
REQUIRED_PREPARATION_KEYS = ["uuid", "cells"]
REQUIRED_CELL_KEYS = ["uuid", "epoch_groups"]


def check_meta_file(path):
    """Returns a list of problem strings for this file (empty list = looks OK)."""
    problems = []

    try:
        with open(path, "r") as f:
            meta = json.load(f)
    except Exception as e:
        return [f"could not parse JSON: {e}"]

    for key in REQUIRED_EXPERIMENT_KEYS:
        if key not in meta:
            problems.append(f"missing top-level '{key}'")

    if "animals" in meta:
        for i, animal in enumerate(meta["animals"]):
            for key in REQUIRED_ANIMAL_KEYS:
                if key not in animal:
                    problems.append(f"animals[{i}] missing '{key}'")
            for j, prep in enumerate(animal.get("preparations", [])):
                for key in REQUIRED_PREPARATION_KEYS:
                    if key not in prep:
                        problems.append(f"animals[{i}].preparations[{j}] missing '{key}'")
                for k, cell in enumerate(prep.get("cells", [])):
                    for key in REQUIRED_CELL_KEYS:
                        if key not in cell:
                            problems.append(
                                f"animals[{i}].preparations[{j}].cells[{k}] missing '{key}'"
                            )

    return problems


def main():
    json_files = sorted(f for f in os.listdir(META_DIR) if f.endswith(".json"))
    print(f"Scanning {len(json_files)} meta JSON files in {META_DIR}\n")

    n_bad = 0
    for fname in json_files:
        path = os.path.join(META_DIR, fname)
        problems = check_meta_file(path)
        if problems:
            n_bad += 1
            print(f"[BAD]  {fname}")
            for p in problems:
                print(f"         - {p}")

    print(f"\n{n_bad} of {len(json_files)} files have a problem that would crash populate_database().")
    if n_bad == 0:
        print("All meta files look structurally OK -- the KeyError may be coming from")
        print("something else. Paste the 'Adding <path>' line that printed right before")
        print("the traceback and I'll dig further.")


if __name__ == "__main__":
    main()
