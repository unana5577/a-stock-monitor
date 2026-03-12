import glob
import json
import os


def _data_dir():
    return os.path.join(os.path.dirname(__file__), "..", "data")


def _latest_overview_file():
    files = glob.glob(os.path.join(_data_dir(), "overview-history-*.json"))
    assert files
    files.sort()
    return files[-1]


def test_overview_history_integrity():
    file_path = _latest_overview_file()
    with open(file_path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    day = obj.get("day")
    assert day
    day_key = day.replace("-", "")
    assert day_key in os.path.basename(file_path)
    series = obj.get("series") or {}
    sse = series.get("sse") or []
    assert len(sse) > 0
    volume = obj.get("volume") or []
    archive_file = os.path.join(_data_dir(), f"archive-{day_key}.jsonl")
    assert os.path.exists(archive_file)
    volume_file = os.path.join(_data_dir(), f"volume-{day_key}.jsonl")
    assert os.path.exists(volume_file)
    with open(volume_file, "r", encoding="utf-8") as fh:
        lines = [line for line in fh.read().splitlines() if line.strip()]
    assert len(lines) >= 30
