import threading
import time
from unittest.mock import Mock

import pytest

from millsheet import extract
from millsheet.cache import PageCache, file_hash
from millsheet.extract import (Cancelled, GeminiReader, PageReadError, ReaderAuthError, inline_refs, list_pdfs,
                               read_folder, render_png)
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
