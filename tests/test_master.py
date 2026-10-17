from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

from millsheet.master import (MasterFetchError, MasterValidationError, export_bundled_csv, fetch_master,
                              load_master_file, parse_sheet_values, spreadsheet_id_from_url)
from millsheet.paths import master_cache_path
from tests.helpers import URL, VALUES, client_raising, client_returning


def test_spreadsheet_id_from_url():
    assert spreadsheet_id_from_url("https://docs.google.com/spreadsheets/d/1AbC-_x/edit#gid=0") == "1AbC-_x"
    assert spreadsheet_id_from_url("1AbC-_x") == "1AbC-_x"
    with pytest.raises(MasterFetchError, match="URL"):
        spreadsheet_id_from_url("https://example.com/")


def test_parse_sheet_values_ok():
    es = parse_sheet_values([["品名", "サイズ", "単重"], ["H形鋼", "Ｈ-200×200×8×12", "49.9"], [],
                             ["FB", "FB-9×25", 1.77]])
    assert [e.unit_weight for e in es] == [49.9, 1.77]


def test_parse_sheet_values_tolerates_fullwidth_and_spaces():
    es = parse_sheet_values([[" サイズ ", "単重", "品名"], ["Ｈ-200×200×8×12 ", "４９．９", "H形鋼"],
                             ["PL-50", "1,234", "PL"]])
    assert es[0].size == "Ｈ-200×200×8×12" and es[0].unit_weight == 49.9 and es[1].unit_weight == 1234


def test_parse_sheet_values_short_rows_are_padded():
    with pytest.raises(MasterValidationError) as e:
        parse_sheet_values([["品名", "サイズ", "単重"], ["H形鋼", "Ｈ-1×1×1×1"]])
    assert "2 行目" in e.value.errors[0]


def test_parse_sheet_values_reports_all_errors_with_row_numbers():
    with pytest.raises(MasterValidationError) as e:
        parse_sheet_values([["品名", "サイズ", "単重"], ["H形鋼", "Ｈ-1×1×1×1", "0"], ["H形鋼", "Ｈ-2×2×2×2", "x"],
                            ["C", "C-100×50×20×4.0", "1"], ["C", "C-100×50×20×4", "2"]])
    msg = "\n".join(e.value.errors)
    assert "2 行目" in msg and "3 行目" in msg and "重複" in msg


def test_parse_sheet_values_missing_header():
    with pytest.raises(MasterValidationError):
        parse_sheet_values([["サイズ", "単重"], ["Ｈ-1×1×1×1", "1"]])


def test_fetch_master_success_writes_cache():
    seen = []
    m, warnings = fetch_master(URL, "単重 'マスタ'", "KEY", client=client_returning(200, {"values": VALUES}, seen))
    assert m.source == "sheet" and warnings == [] and master_cache_path().exists() and len(m.entries) == 225
    url = unquote(str(seen[0].url))
    assert "/spreadsheets/TESTID/values/'単重 ''マスタ'''!A:Z" in url and "valueRenderOption=UNFORMATTED_VALUE" in url


def test_fetch_master_without_sheet_name_uses_first_sheet():
    seen = []
    fetch_master(URL, "", "KEY", client=client_returning(200, {"values": VALUES}, seen))
    assert "/values/A%3AZ" in str(seen[0].url)


def test_fetch_master_falls_back_to_cache():
    fetch_master(URL, "", "KEY", client=client_returning(200, {"values": VALUES}))
    m, warnings = fetch_master(URL, "", "KEY", client=client_raising(httpx.ConnectError("x")))
    assert m.source == "cache" and len(m.entries) == 225
    assert "前回取得した単重" in warnings[0] and "ネットに接続できません" in warnings[0]


def test_fetch_master_no_cache_403_message():
    with pytest.raises(MasterFetchError, match="共有設定"):
        fetch_master(URL, "", "KEY", client=client_returning(403, {}))


def test_fetch_master_404_and_bad_range_messages():
    with pytest.raises(MasterFetchError, match="URL を確認"):
        fetch_master(URL, "", "KEY", client=client_returning(404, {}))
    with pytest.raises(MasterFetchError, match="シート名「x」"):
        fetch_master(URL, "x", "KEY", client=client_returning(400, {"error": {"message": "Unable to parse range: x"}}))


def test_fetch_master_validation_error_does_not_use_cache():
    fetch_master(URL, "", "KEY", client=client_returning(200, {"values": VALUES}))
    with pytest.raises(MasterValidationError):
        fetch_master(URL, "", "KEY", client=client_returning(
            200, {"values": [["品名", "サイズ", "単重"], ["H", "Ｈ-1×1×1×1", "0"]]}))


def test_error_messages_never_contain_key():
    with pytest.raises(MasterFetchError) as e:
        fetch_master(URL, "", "AIzaSECRET", client=client_returning(400, {"error": {"message": "API key not valid"}}))
    assert "AIzaSECRET" not in str(e.value) and "API キー" in str(e.value)


def test_lookup_returns_master_entry():
    m = load_master_file(Path("tests/fixtures/unit_weights.json"))
    assert m.lookup("Ｈ-200×200×8×12").unit_weight == 49.9
    assert m.lookup("［-100×50×5").unit_weight == 9.36
    assert m.lookup("φ-1×1") is None
    assert m.meta()["件数"] == 225


def test_export_bundled_csv_has_bom(tmp_path):
    export_bundled_csv(tmp_path / "m.csv")
    b = (tmp_path / "m.csv").read_bytes()
    assert b.startswith(b"\xef\xbb\xbf") and len(b.decode("utf-8-sig").splitlines()) == 226
    assert b.decode("utf-8-sig").splitlines()[0] == "品名,サイズ,単重"
