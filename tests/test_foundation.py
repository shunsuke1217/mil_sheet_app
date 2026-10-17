import json
from pathlib import Path

from millsheet import paths
from millsheet.applog import mask
from millsheet.schema import PageResult
from millsheet.settings import Settings, get_secret, load_settings, save_settings, set_secret


def test_fixture_raw_matches_schema():
    raw = json.loads(Path("tests/fixtures/sample_raw.json").read_text("utf-8"))
    pages = raw["pages"]["20261014084620.pdf"]
    assert len(pages) == 10
    for p in pages:
        PageResult.model_validate(p["result"])
    assert raw["pages"]["サンプル_例外.pdf"][0]["result"]["lines"][0]["circle_status"] == "なし"
    assert raw["pages"]["サンプル_例外.pdf"][1]["error"] == "APIタイムアウト"


def test_bundled_master_has_225_entries_with_category():
    data = json.loads(Path("millsheet/unit_weights.json").read_text("utf-8"))
    assert len(data) == 225
    assert {"品名", "サイズ", "単重"} == set(data[0])
    assert {d["品名"] for d in data} == {"H形鋼", "溝形鋼", "Cチャン", "アングル", "コラム/STKR", "FB", "PL"}


def test_data_dir_created_and_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("MILLSHEET_DATA_DIR", str(tmp_path / "d"))
    assert paths.data_dir() == tmp_path / "d"
    assert paths.data_dir().is_dir()
    assert paths.master_cache_path() == tmp_path / "d" / "unit_weights_cache.json"
    assert paths.cache_dir().is_dir() and paths.logs_dir().is_dir()


def test_bundled_master_path_exists():
    assert paths.bundled_master_path().exists()


def test_settings_roundtrip_has_no_secrets(data_dir):
    save_settings(Settings(sheet_url="https://docs.google.com/spreadsheets/d/abc/edit"))
    set_secret("gemini_api_key", "GKEY123")
    assert load_settings().sheet_url.endswith("/abc/edit")
    assert "GKEY123" not in (data_dir / "settings.json").read_text("utf-8")
    assert get_secret("gemini_api_key") == "GKEY123"


def test_broken_settings_falls_back_to_default(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text("{broken", "utf-8")
    assert load_settings() == Settings()


def test_mask_hides_secrets():
    assert mask("url?key=AIzaXYZ", ["AIzaXYZ"]) == "url?key=***"
    assert mask("abc", [None, ""]) == "abc"
