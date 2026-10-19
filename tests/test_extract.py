import threading
import time
from unittest.mock import Mock

import pytest

from millsheet import extract
from millsheet.cache import PageCache, file_hash
from millsheet.extract import (Cancelled, GeminiReader, InputError, PageReadError, ReaderAuthError, inline_refs, list_pdfs,
                               read_folder, render_png, resolve_inputs)
from millsheet.schema import PageEntry, PageResult
from tests.helpers import FakeReader, make_pdf, page_result


def test_list_pdfs_same_name_in_subfolders(tmp_path):
    make_pdf(tmp_path / "B/001.pdf", 1); make_pdf(tmp_path / "A/001.pdf", 1); make_pdf(tmp_path / "c.PDF", 1)
    (tmp_path / "note.txt").write_text("x")
    assert list_pdfs(tmp_path) == ["A/001.pdf", "B/001.pdf", "c.PDF"]


def test_render_png_is_png(sample_pdf):
    assert render_png(sample_pdf, 1)[:8] == b"\x89PNG\r\n\x1a\n"


def test_read_folder_order_and_cache(tmp_path):
    make_pdf(tmp_path / "src/b.pdf", 2); make_pdf(tmp_path / "src/a.pdf", 1)
    reader = FakeReader()
    progress = []
    entries = read_folder(tmp_path / "src", reader, PageCache(tmp_path / "cache"),
                          on_progress=lambda *a: progress.append(a))
    assert [(e.file, e.page_no) for e in entries] == [("a.pdf", 1), ("b.pdf", 1), ("b.pdf", 2)]
    assert reader.calls == 3
    assert sorted(p[3] for p in progress) == [1, 2, 3] and {p[4] for p in progress} == {3}
    read_folder(tmp_path / "src", reader, PageCache(tmp_path / "cache"))
    assert reader.calls == 3                                         # 2 回目はキャッシュだけ


def test_same_name_in_subfolders_do_not_share_cache(tmp_path):
    make_pdf(tmp_path / "src/A/001.pdf", 1)
    make_pdf(tmp_path / "src/B/001.pdf", 2)
    entries = read_folder(tmp_path / "src", FakeReader(), PageCache(tmp_path / "cache"))
    assert [(e.file, e.page_no) for e in entries] == [("A/001.pdf", 1), ("B/001.pdf", 1), ("B/001.pdf", 2)]


def test_read_folder_page_error_becomes_entry(tmp_path):
    make_pdf(tmp_path / "a.pdf", 1)
    e = read_folder(tmp_path, FakeReader(raise_error=PageReadError("503")), PageCache(tmp_path / "c"))
    assert e[0].result is None and e[0].error == "503"


def test_failed_pages_are_not_cached(tmp_path):
    make_pdf(tmp_path / "a.pdf", 1)
    read_folder(tmp_path, FakeReader(raise_error=PageReadError("503")), PageCache(tmp_path / "c"))
    reader = FakeReader()
    read_folder(tmp_path, reader, PageCache(tmp_path / "c"))
    assert reader.calls == 1


def test_auth_error_stops_everything(tmp_path):
    make_pdf(tmp_path / "a.pdf", 2)
    with pytest.raises(ReaderAuthError):
        read_folder(tmp_path, FakeReader(raise_error=ReaderAuthError("x")), PageCache(tmp_path / "c"))


def test_open_failure_yields_error_entry(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    e = read_folder(tmp_path, FakeReader(), PageCache(tmp_path / "c"))
    assert e == [PageEntry("broken.pdf", None, None, "PDF を開けませんでした")]


def test_encrypted_pdf_yields_error_entry(tmp_path):
    import pymupdf
    doc = pymupdf.open(); doc.new_page()
    doc.save(tmp_path / "locked.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    e = read_folder(tmp_path, FakeReader(), PageCache(tmp_path / "c"))
    assert e == [PageEntry("locked.pdf", None, None, "PDF にパスワードが掛かっているため開けませんでした")]


def test_cancel_raises(tmp_path):
    make_pdf(tmp_path / "a.pdf", 3); ev = threading.Event(); ev.set()
    with pytest.raises(Cancelled):
        read_folder(tmp_path, FakeReader(), PageCache(tmp_path / "c"), cancel=ev)


def test_cache_key_includes_hash_and_page(tmp_path):
    c = PageCache(tmp_path)
    c.put("h1", 1, page_result(circled_qty=7))
    assert c.get("h1", 1).lines[0].circled_qty == 7 and c.get("h1", 2) is None and c.get("h2", 1) is None


def test_file_hash(tmp_path):
    p = make_pdf(tmp_path / "a.pdf", 1)
    assert len(file_hash(p)) == 64


def test_gemini_reader_retries_then_reports_error(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    r = GeminiReader("KEY"); r._call = Mock(side_effect=RuntimeError("503 KEY"))
    with pytest.raises(PageReadError) as e:
        r.read(b"png")
    assert r._call.call_count == 4 and sleeps == [1, 2, 4] and "KEY" not in str(e.value)


def test_gemini_reader_succeeds_after_retry(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = GeminiReader("KEY"); r._call = Mock(side_effect=[RuntimeError("503"), page_result()])
    assert isinstance(r.read(b"png"), PageResult) and r._call.call_count == 2


def test_gemini_reader_invalid_key_is_not_retried(monkeypatch):
    from google.genai import errors
    monkeypatch.setattr(time, "sleep", lambda s: None)
    err = errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                                             "status": "INVALID_ARGUMENT"}})
    r = GeminiReader("KEY"); r._call = Mock(side_effect=err)
    with pytest.raises(ReaderAuthError):
        r.read(b"png")
    assert r._call.call_count == 1


def test_inline_refs_removes_defs():
    s = inline_refs(PageResult.model_json_schema())
    assert "$defs" not in s and "$ref" not in str(s)
    assert s["properties"]["lines"]["items"]["properties"]["circle_status"]["enum"] == ["あり", "なし", "読めない"]


def test_model_constant():
    assert extract.MODEL == "gemini-3.8-flash"


# 入力（フォルダ・PDF ファイル・混ぜたもの）
def test_resolve_inputs_folder_is_same_as_list_pdfs(tmp_path):
    make_pdf(tmp_path / "src/b.pdf", 1); make_pdf(tmp_path / "src/sub/a.pdf", 1)
    s = resolve_inputs([tmp_path / "src"])
    assert s.base == (tmp_path / "src").resolve() and s.files == ["b.pdf", "sub/a.pdf"]


def test_resolve_inputs_single_file(tmp_path):
    make_pdf(tmp_path / "scan/連結.pdf", 3)
    s = resolve_inputs([tmp_path / "scan/連結.pdf"])
    assert s.base == (tmp_path / "scan").resolve() and s.files == ["連結.pdf"]


def test_resolve_inputs_files_from_different_folders_use_common_parent(tmp_path):
    make_pdf(tmp_path / "A/001.pdf", 1); make_pdf(tmp_path / "B/001.pdf", 1)
    s = resolve_inputs([tmp_path / "B/001.pdf", tmp_path / "A/001.pdf"])
    assert s.base == tmp_path.resolve() and s.files == ["A/001.pdf", "B/001.pdf"]


def test_resolve_inputs_mixed_folder_and_files_without_duplicates(tmp_path):
    make_pdf(tmp_path / "A/1.pdf", 1); make_pdf(tmp_path / "A/2.pdf", 1); make_pdf(tmp_path / "c.PDF", 1)
    s = resolve_inputs([tmp_path / "A", tmp_path / "A/1.pdf", tmp_path / "c.PDF"])
    assert s.base == tmp_path.resolve() and s.files == ["A/1.pdf", "A/2.pdf", "c.PDF"]


def test_resolve_inputs_refuses_non_pdf_file(tmp_path):
    make_pdf(tmp_path / "a.pdf", 1); (tmp_path / "表.xlsx").write_text("x")
    with pytest.raises(InputError, match="表.xlsx"):
        resolve_inputs([tmp_path / "a.pdf", tmp_path / "表.xlsx"])


def test_resolve_inputs_refuses_missing_path(tmp_path):
    with pytest.raises(InputError, match="見つかりません"):
        resolve_inputs([tmp_path / "無い.pdf"])


def test_resolve_inputs_refuses_when_no_pdf(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(InputError, match="PDF がありません"):
        resolve_inputs([tmp_path / "empty"])


def test_resolve_inputs_refuses_different_drives(tmp_path, monkeypatch):
    make_pdf(tmp_path / "a.pdf", 1); make_pdf(tmp_path / "b.pdf", 1)

    def commonpath(paths):
        raise ValueError("Paths don't have the same drive")   # Windows で C: と D: を混ぜたとき
    monkeypatch.setattr(extract.os.path, "commonpath", commonpath)
    with pytest.raises(InputError, match="ドライブ"):
        resolve_inputs([tmp_path / "a.pdf", tmp_path / "b.pdf"])


def test_read_folder_reads_only_given_files(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1); make_pdf(tmp_path / "src/b.pdf", 2)
    entries = read_folder(tmp_path / "src", FakeReader(), PageCache(tmp_path / "cache"), files=["b.pdf"])
    assert [(e.file, e.page_no) for e in entries] == [("b.pdf", 1), ("b.pdf", 2)]


def test_read_folder_keeps_the_list_taken_at_start(tmp_path):
    """読み取り中に足された PDF が、結果から黙って抜けたり、途中で増えたりしない。"""
    make_pdf(tmp_path / "src/a.pdf", 1)

    class AddingReader(FakeReader):
        def read(self, png):
            make_pdf(tmp_path / "src/z.pdf", 1)
            return super().read(png)
    entries = read_folder(tmp_path / "src", AddingReader(), PageCache(tmp_path / "cache"), workers=1)
    assert [(e.file, e.page_no) for e in entries] == [("a.pdf", 1)]
