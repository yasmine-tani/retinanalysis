from pathlib import Path

from retinanalysis.utils import database_pop, database_utils


def test_discover_sorting_chunks_supports_data_dir_layout(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "exp1"

    data000_dir = experiment_dir / "data000" / "ksfiles"
    data000_dir.mkdir(parents=True)
    (data000_dir / "spike_times.npy").write_text("placeholder", encoding="utf-8")

    data001_dir = experiment_dir / "data001" / "ksfiles"
    data001_dir.mkdir(parents=True)
    (data001_dir / "cluster_KSLabel.tsv").write_text(
        "cluster_id\tlabel\n0\tGood\n",
        encoding="utf-8",
    )

    candidates = database_pop.discover_sorting_chunks(experiment_dir)

    chunk_names = [candidate["chunk_name"] for candidate in candidates]
    assert chunk_names == ["data000", "data001"]
    assert all(candidate["chunk_path"].exists() for candidate in candidates)


def test_populate_database_passes_refresh_existing(monkeypatch) -> None:
    calls = {}

    def fake_append_data(data_dir, meta_dir, tags_dir, username, db_param, refresh_existing=False):
        calls["refresh_existing"] = refresh_existing
        return 0

    monkeypatch.setattr(database_utils.database_pop, "append_data", fake_append_data)
    monkeypatch.setattr(database_utils, "get_schema_module", lambda: object())

    assert database_utils.populate_database(refresh_existing=True) == 0
    assert calls["refresh_existing"] is True
