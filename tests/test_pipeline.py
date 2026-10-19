import shutil
from pathlib import Path
from unittest.mock import Mock

import pymupdf
import pytest

from millsheet.export.base import OutputLockedError
from millsheet.export.local_xlsx import LocalXlsxExporter
from millsheet.pipeline import outputs_for, review_messages, run
from millsheet.settings import Settings
from tests.helpers import FakeReader, make_pdf, page_result, png_hash, rec

KW = dict(settings=Settings(), gemini_key="g")


def test_outputs_for_is_a_folder_with_xlsx_pdf_and_work_data(tmp_path):
    o = outputs_for(tmp_path / "現場A")
    assert o.dir == tmp_path / "現場A"
    assert o.xlsx == tmp_path / "現場A/現場A.xlsx" and o.pdf == tmp_path / "現場A/現場A.pdf"
    assert o.json == tmp_path / "現場A/作業データ/現場A.json" and o.raw == tmp_path / "現場A/作業データ/現場A_raw.json"


def test_run_writes_all_outputs(tmp_path, sample_folder, fake_reader):
    res = run(sample_folder, tmp_path / "out", reader=fake_reader, **KW)
    o = res.outputs
    assert o.xlsx.exists() and o.json.exists() and o.raw.exists() and o.pdf.exists()
    assert pymupdf.open(o.pdf).page_count == 10 and res.errors == []
    assert [r.mass_kg for r in res.records] == [10332, 1460, 5287, 4567, 1632, 3708, 7305, 1950, 3640, 2015]






def test_missing_keys_are_reported(tmp_path):
    with pytest.raises(ValueError, match="Gemini"):
        run(tmp_path, tmp_path / "o", settings=Settings(), gemini_key="",
            reader=None)


def test_run_reports_locked_output_and_keeps_raw(tmp_path, monkeypatch):
    make_pdf(tmp_path / "src/a.pdf", 1)
    monkeypatch.setattr(LocalXlsxExporter, "export", Mock(side_effect=OutputLockedError(tmp_path / "o/o.xlsx")))
    res = run(tmp_path / "src", tmp_path / "o", reader=FakeReader(), **KW)
    assert res.outputs.raw.exists() and res.outputs.pdf.exists()
    assert any("o.xlsx が他のアプリで開かれていたため保存できませんでした" in e for e in res.errors)




def test_merged_pdf_page_n_is_source_of_label_n(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1); make_pdf(tmp_path / "src/b.pdf", 1)
    # a.pdf p1 = 溝形鋼、b.pdf p1 = H形鋼 → 並べると b が Ｐ-1
    reader = FakeReader(results={
        png_hash(tmp_path / "src/a.pdf", 1): page_result(commodity_raw="溝形鋼", size_raw="150X75X6.5"),
        png_hash(tmp_path / "src/b.pdf", 1): page_result(commodity_raw="H形鋼", size_raw="200X200X8X12")})
    res = run(tmp_path / "src", tmp_path / "o", reader=reader, **KW)
    doc = pymupdf.open(res.outputs.pdf)
    labels = {r.page_label: r.file for r in res.records}
    assert doc[0].get_text().strip() == "b-1" and labels["Ｐ-1"] == "b.pdf"
    assert doc[1].get_text().strip() == "a-1" and labels["Ｐ-2"] == "a.pdf"




def test_review_messages():
    assert review_messages([rec(file="a.pdf", page=3, reasons=["丸数字が読めません"]), rec(reasons=[])]) == \
        ["a.pdf の 3 ページ目がうまく読み込めませんでした（丸数字が読めません）"]
    assert review_messages([rec(file="b.pdf", page=None, kind="error", reasons=["読み取りに失敗しました（x）"])]) == \
        ["b.pdf を読み込めませんでした（読み取りに失敗しました（x））"]
    msg = review_messages([rec(file="c.pdf", page=1, reasons=["必須項目が空です（質量、重量）",
                                                              "AI が読み取りに自信がないと返しました"])])[0]
    assert msg == "c.pdf の 1 ページ目がうまく読み込めませんでした（必須項目が空です（質量、重量）、AI が読み取りに自信がないと返しました）"


def test_empty_folder_is_reported_before_reading(tmp_path):
    (tmp_path / "src").mkdir()
    with pytest.raises(ValueError, match="PDF がありません"):
        run(tmp_path / "src", tmp_path / "o", reader=FakeReader(), **KW)


def test_run_puts_only_xlsx_and_pdf_at_top_of_folder(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1)
    res = run(tmp_path / "src", tmp_path / "out/現場A", reader=FakeReader(), **KW)
    assert res.outputs.dir == tmp_path / "out/現場A"
    assert sorted(p.name for p in res.outputs.dir.iterdir()) == ["作業データ", "現場A.pdf", "現場A.xlsx"]




def test_run_with_one_concatenated_pdf_matches_folder(tmp_path, sample_folder, fake_reader):
    pdf = next(sample_folder.glob("*.pdf"))
    res = run([pdf], tmp_path / "out", reader=fake_reader, **KW)
    assert [r.mass_kg for r in res.records] == [10332, 1460, 5287, 4567, 1632, 3708, 7305, 1950, 3640, 2015]
    assert pymupdf.open(res.outputs.pdf).page_count == 10 and res.errors == []


def test_run_with_files_from_different_folders(tmp_path):
    make_pdf(tmp_path / "A/a.pdf", 1); make_pdf(tmp_path / "B/b.pdf", 1); make_pdf(tmp_path / "B/読まない.pdf", 1)
    reader = FakeReader()
    res = run([tmp_path / "A/a.pdf", tmp_path / "B/b.pdf"], tmp_path / "o", reader=reader, **KW)
    assert reader.calls == 2 and sorted(r.file for r in res.records) == ["A/a.pdf", "B/b.pdf"]
    assert pymupdf.open(res.outputs.pdf).page_count == 2 and res.errors == []


def test_non_pdf_file_is_reported_before_reading(tmp_path):
    (tmp_path / "表.xlsx").write_text("x")
    reader = FakeReader()
    with pytest.raises(ValueError, match="PDF ではない"):
        run([tmp_path / "表.xlsx"], tmp_path / "o", reader=reader, **KW)
    assert reader.calls == 0
