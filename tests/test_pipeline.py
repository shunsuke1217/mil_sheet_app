from pathlib import Path
from unittest.mock import Mock

import pymupdf
import pytest

from millsheet.export.base import OutputLockedError
from millsheet.export.local_xlsx import LocalXlsxExporter
from millsheet.master import MasterFetchError
from millsheet.pipeline import outputs_for, rebuild, review_messages, run
from millsheet.settings import Settings
from tests.conftest import _fixture_master_loader
from tests.helpers import FakeReader, make_pdf, page_result, png_hash, rec

KW = dict(settings=Settings(), gemini_key="g")


def test_outputs_for(tmp_path):
    o = outputs_for(tmp_path / "結果.xlsx")
    assert (o.xlsx.name, o.json.name, o.raw.name, o.pdf.name) == ("結果.xlsx", "結果.json", "結果_raw.json", "結果.pdf")


def test_run_writes_all_outputs(tmp_path, sample_folder, fake_reader, fixture_master_loader):
    res = run(sample_folder, tmp_path / "out.xlsx", reader=fake_reader, master_loader=fixture_master_loader, **KW)
    o = res.outputs
    assert o.xlsx.exists() and o.json.exists() and o.raw.exists() and o.pdf.exists()
    assert pymupdf.open(o.pdf).page_count == 10 and res.errors == []
    assert [r.weight for r in res.records] == [574, 293, 5287, 4567, 1432, 51, 1949, 520, 33, 163]


def test_rebuild_does_not_call_reader(tmp_path, sample_folder, fake_reader, fixture_master_loader):
    run(sample_folder, tmp_path / "out.xlsx", reader=fake_reader, master_loader=fixture_master_loader, **KW)
    n = fake_reader.calls
    res = rebuild(tmp_path / "out_raw.json", tmp_path / "out.xlsx", settings=Settings(),
                  master_loader=fixture_master_loader)
    assert fake_reader.calls == n and len(res.records) == 10 and res.outputs.pdf.exists()


def test_master_failure_stops_before_reading(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1)
    reader = FakeReader()

    def bad():
        raise MasterFetchError("ネットに接続できません")
    with pytest.raises(MasterFetchError):
        run(tmp_path / "src", tmp_path / "o.xlsx", reader=reader, master_loader=bad, **KW)
    assert reader.calls == 0


def test_missing_keys_are_reported(tmp_path):
    with pytest.raises(ValueError, match="Gemini"):
        run(tmp_path, tmp_path / "o.xlsx", settings=Settings(), gemini_key="",
            reader=None, master_loader=_fixture_master_loader)


def test_run_reports_locked_output_and_keeps_raw(tmp_path, monkeypatch):
    make_pdf(tmp_path / "src/a.pdf", 1)
    monkeypatch.setattr(LocalXlsxExporter, "export", Mock(side_effect=OutputLockedError(tmp_path / "o.xlsx")))
    res = run(tmp_path / "src", tmp_path / "o.xlsx", reader=FakeReader(), master_loader=_fixture_master_loader, **KW)
    assert res.outputs.raw.exists() and res.outputs.pdf.exists()
    assert any("o.xlsx が他のアプリで開かれています" in e for e in res.errors)


def test_rebuild_without_source_pdf(tmp_path):
    res = rebuild(Path("tests/fixtures/sample_raw.json"), tmp_path / "o.xlsx", settings=Settings(),
                  master_loader=_fixture_master_loader)
    assert res.outputs.pdf is None and "元の PDF" in res.errors[0] and res.outputs.xlsx.exists()


def test_merged_pdf_page_n_is_source_of_label_n(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1); make_pdf(tmp_path / "src/b.pdf", 1)
    # a.pdf p1 = 溝形鋼、b.pdf p1 = H形鋼 → 並べると b が Ｐ-1
    reader = FakeReader(results={
        png_hash(tmp_path / "src/a.pdf", 1): page_result(commodity_raw="溝形鋼", size_raw="150X75X6.5"),
        png_hash(tmp_path / "src/b.pdf", 1): page_result(commodity_raw="H形鋼", size_raw="200X200X8X12")})
    res = run(tmp_path / "src", tmp_path / "o.xlsx", reader=reader, master_loader=_fixture_master_loader, **KW)
    doc = pymupdf.open(res.outputs.pdf)
    labels = {r.page_label: r.file for r in res.records}
    assert doc[0].get_text().strip() == "b-1" and labels["Ｐ-1"] == "b.pdf"
    assert doc[1].get_text().strip() == "a-1" and labels["Ｐ-2"] == "a.pdf"


def test_master_warning_is_passed_through(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1)
    res = run(tmp_path / "src", tmp_path / "o.xlsx", reader=FakeReader(),
              master_loader=lambda: (_fixture_master_loader()[0], ["前回取得した単重を使います"]), **KW)
    assert res.warnings == ["前回取得した単重を使います"]


def test_review_messages():
    assert review_messages([rec(file="a.pdf", page=3, reasons=["丸数字が読めません"]), rec(reasons=[])]) == \
        ["a.pdf の 3 ページ目がうまく読み込めませんでした（丸数字が読めません）"]
    assert review_messages([rec(file="b.pdf", page=None, kind="error", reasons=["読み取りに失敗しました（x）"])]) == \
        ["b.pdf を読み込めませんでした（読み取りに失敗しました（x））"]
    msg = review_messages([rec(file="c.pdf", page=1, cat="I形鋼", size="200×100×7×10",
                               reasons=["単重がマスタに未登録です", "AI が読み取りに自信がないと返しました"])])[0]
    assert msg == ("c.pdf の 1 ページ目がうまく読み込めませんでした（単重がマスタに未登録です、AI が読み取りに自信がないと返しました）"
                   "　登録が必要: I形鋼 200×100×7×10")


def test_empty_folder_is_reported_before_reading(tmp_path):
    (tmp_path / "src").mkdir()
    with pytest.raises(ValueError, match="PDF がありません"):
        run(tmp_path / "src", tmp_path / "o.xlsx", reader=FakeReader(), master_loader=_fixture_master_loader, **KW)
