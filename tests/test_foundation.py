import json

from millsheet import paths
from millsheet.applog import mask
from millsheet.schema import PageResult
from millsheet.settings import Settings, get_secret, load_settings, save_settings, set_secret


def test_fixture_raw_matches_schema(sample_raw):
    raw = json.loads(sample_raw.read_text("utf-8"))
    pages = raw["pages"]["20261014084620.pdf"]
    assert len(pages) == 10
    for p in pages:
        PageResult.model_validate(p["result"])
    assert raw["pages"]["サンプル_例外.pdf"][0]["result"]["lines"][0]["circle_status"] == "なし"
    assert raw["pages"]["サンプル_例外.pdf"][1]["error"] == "APIタイムアウト"




def test_data_dir_created_and_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("MILLSHEET_DATA_DIR", str(tmp_path / "d"))
    assert paths.data_dir() == tmp_path / "d"
    assert paths.data_dir().is_dir()
    assert paths.cache_dir().is_dir() and paths.logs_dir().is_dir()




def test_settings_roundtrip_has_no_secrets(data_dir):
    save_settings(Settings(output_path="/tmp/出力"))
    set_secret("gemini_api_key", "GKEY123")
    assert load_settings().output_path == "/tmp/出力"
    assert "GKEY123" not in (data_dir / "settings.json").read_text("utf-8")
    assert get_secret("gemini_api_key") == "GKEY123"


def test_broken_settings_falls_back_to_default(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text("{broken", "utf-8")
    assert load_settings() == Settings()


def test_mask_hides_secrets():
    assert mask("url?key=AIzaXYZ", ["AIzaXYZ"]) == "url?key=***"
    assert mask("abc", [None, ""]) == "abc"
