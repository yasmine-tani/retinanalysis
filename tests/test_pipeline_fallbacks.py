from retinanalysis.classes import mea_pipeline
from retinanalysis.utils import vision_utils


def test_create_mea_pipeline_falls_back_to_datafile_chunk_when_nearest_noise_missing(monkeypatch):
    class FakeStimBlock:
        def __init__(self, *args, **kwargs):
            self.nearest_noise_chunk = None

    class FakeResponseBlock:
        def __init__(self, *args, **kwargs):
            pass

    class FakeAnalysisChunk:
        def __init__(self, exp_name, chunk_name, ss_version, verbose=True):
            if chunk_name is None:
                raise ValueError("chunk_name cannot be None")
            self.exp_name = exp_name
            self.chunk_name = chunk_name
            self.ss_version = ss_version
            self.data_files = []

    class FakePipeline:
        def __init__(self, stim, resp, analysis_chunk, typing_file, verbose=True):
            self.stim = stim
            self.resp = resp
            self.analysis_chunk = analysis_chunk
            self.typing_file = typing_file
            self.verbose = verbose

    monkeypatch.setattr(mea_pipeline, "MEAStimBlock", FakeStimBlock)
    monkeypatch.setattr(mea_pipeline, "MEAResponseBlock", FakeResponseBlock)
    monkeypatch.setattr(mea_pipeline, "AnalysisChunk", FakeAnalysisChunk)
    monkeypatch.setattr(mea_pipeline, "MEAPipeline", FakePipeline)

    pipeline = mea_pipeline.create_mea_pipeline(
        "20260506A",
        "data007",
        analysis_chunk_name=None,
        ss_version="kilosort25",
        verbose=False,
    )

    assert pipeline.analysis_chunk.chunk_name == "data007"


def test_get_analysis_vcd_uses_chunk_name_for_dataset(monkeypatch, tmp_path):
    captured = {}

    def fake_load_vision_data(data_path, dataset_name, **kwargs):
        captured["data_path"] = data_path
        captured["dataset_name"] = dataset_name
        return object()

    monkeypatch.setattr(vision_utils, "load_vision_data", fake_load_vision_data)
    monkeypatch.setattr(
        vision_utils,
        "_resolve_vision_data_path",
        lambda exp_name, chunk_name, ss_version: str(tmp_path),
    )
    (tmp_path / "data007.globals").write_text("placeholder", encoding="utf-8")

    vision_utils.get_analysis_vcd("exp", "data007", "kilosort25", verbose=False)

    assert captured["dataset_name"] == "data007"
