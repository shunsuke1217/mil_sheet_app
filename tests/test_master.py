from pathlib import Path

import httpx
import pytest

from millsheet.master import (MasterFetchError, MasterValidationError, export_bundled_csv, fetch_master,
                              gid_from_url, load_master_file, parse_sheet_values, spreadsheet_id_from_url)
from millsheet.paths import master_cache_path
from tests.helpers import URL, VALUES, client_csv, client_login_page, client_raising, to_csv


def test_spreadsheet_id_from_url():
    assert spreadsheet_id_from_url("https://docs.google.com/spreadsheets/d/1AbC-_x/edit#gid=0") == "1AbC-_x"
    assert spreadsheet_id_from_url("1AbC-_x") == "1AbC-_x"
    with pytest.raises(MasterFetchError, match="URL"):
        spreadsheet_id_from_url("https://example.com/")


def test_parse_sheet_values_ok():
    es = parse_sheet_values([["材種", "サイズ", "単重"], ["H形鋼", "Ｈ-200×200×8×12", "49.9"], [],
                             ["FB", "FB-9×25", 1.77]])
    assert [e.unit_weight for e in es] == [49.9, 1.77]


def test_parse_sheet_values_tolerates_fullwidth_and_spaces():
    es = parse_sheet_values([[" サイズ ", "単重", "材種"], ["Ｈ-200×200×8×12 ", "４９．９", "H形鋼"],
                             ["PL-50", "1,234", "PL"]])
    assert es[0].size == "Ｈ-200×200×8×12" and es[0].unit_weight == 49.9 and es[1].unit_weight == 1234


def test_parse_sheet_values_short_rows_are_padded():
    with pytest.raises(MasterValidationError) as e:
        parse_sheet_values([["材種", "サイズ", "単重"], ["H形鋼", "Ｈ-1×1×1×1"]])
    assert "2 行目" in e.value.errors[0]


def test_parse_sheet_values_reports_all_errors_with_row_numbers():
    with pytest.raises(MasterValidationError) as e:
        parse_sheet_values([["材種", "サイズ", "単重"], ["H形鋼", "Ｈ-1×1×1×1", "0"], ["H形鋼", "Ｈ-2×2×2×2", "x"],
                            ["C", "C-100×50×20×4.0", "1"], ["C", "C-100×50×20×4", "2"]])
    msg = "\n".join(e.value.errors)
    assert "2 行目" in msg and "3 行目" in msg and "重複" in msg


def test_parse_sheet_values_missing_header():
    with pytest.raises(MasterValidationError):
        parse_sheet_values([["サイズ", "単重"], ["Ｈ-1×1×1×1", "1"]])


def test_fetch_master_reads_csv_of_the_tab_in_the_url_and_writes_cache():
    seen = []
    m, warnings = fetch_master(URL, client=client_csv(to_csv(VALUES), seen=seen))
    assert m.source == "sheet" and warnings == [] and master_cache_path().exists() and len(m.entries) == 225
    assert str(seen[0].url) == "https://docs.google.com/spreadsheets/d/TESTID/export?format=csv&gid=123"


def test_fetch_master_without_gid_reads_first_tab():
    seen = []
    fetch_master("https://docs.google.com/spreadsheets/d/TESTID/edit", client=client_csv(to_csv(VALUES), seen=seen))
    assert str(seen[0].url) == "https://docs.google.com/spreadsheets/d/TESTID/export?format=csv"


def test_gid_from_url():
    assert gid_from_url("https://docs.google.com/spreadsheets/d/X/edit#gid=0") == "0"
    assert gid_from_url("https://docs.google.com/spreadsheets/d/X/edit?gid=55#gid=55") == "55"
    assert gid_from_url("https://docs.google.com/spreadsheets/d/X/edit") is None


def test_fetch_master_falls_back_to_cache():
    fetch_master(URL, client=client_csv(to_csv(VALUES)))
    m, warnings = fetch_master(URL, client=client_raising(httpx.ConnectError("x")))
    assert m.source == "cache" and len(m.entries) == 225
    assert "前回取得した単重" in warnings[0] and "ネットに接続できません" in warnings[0]


def test_not_shared_sheet_message():
    with pytest.raises(MasterFetchError, match="リンクを知っている全員"):
        fetch_master(URL, client=client_login_page())


def test_not_found_html_page_is_not_reported_as_sharing_problem():
    # 実際の Google は存在しない ID に 404 と HTML を返す
    with pytest.raises(MasterFetchError, match="URL を確認"):
        fetch_master(URL, client=client_csv("<html>", status=404, content_type="text/html; charset=utf-8"))


def test_not_found_messages():
    with pytest.raises(MasterFetchError, match="URL を確認"):
        fetch_master(URL, client=client_csv("", status=404))
    with pytest.raises(MasterFetchError, match="タブ"):
        fetch_master(URL, client=client_csv("", status=400))


def test_fetch_master_validation_error_does_not_use_cache():
    fetch_master(URL, client=client_csv(to_csv(VALUES)))
    with pytest.raises(MasterValidationError):
        fetch_master(URL, client=client_csv(to_csv([["材種", "サイズ", "単重"], ["H", "Ｈ-1×1×1×1", "0"]])))


def test_csv_with_bom_and_formatted_numbers():
    text = "\ufeff" + to_csv([["材種", "サイズ", "単重"], ["PL", "PL-50", "1,234"], ["H形鋼", "Ｈ-200×200×8×12", "49.9"]])
    m, _ = fetch_master(URL, client=client_csv(text))
    assert [e.unit_weight for e in m.entries] == [1234, 49.9]


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
    assert b.decode("utf-8-sig").splitlines()[0] == "材種,サイズ,単重"


def test_old_header_name_is_reported():
    with pytest.raises(MasterValidationError) as e:
        parse_sheet_values([["品名", "サイズ", "単重"], ["H形鋼", "Ｈ-200×200×8×12", "49.9"]])
    assert "材種" in e.value.errors[0]
