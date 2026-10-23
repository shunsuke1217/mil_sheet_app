"""最終レビューの指摘の再現テスト。"""
import threading
import time
from unittest.mock import Mock

import httpx
import pytest
from google.genai._gaos.lib import compat_errors as ce

from millsheet import extract
from millsheet.cache import PageCache
from millsheet.extract import GeminiReader, ReaderAuthError, ReaderRequestError, read_folder
from millsheet.pipeline import outputs_for, run
from millsheet.settings import Settings
from tests.helpers import FakeReader, line, make_pdf, page_result, page_with


def _sdk_error(cls, status, message):
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/interactions")
    resp = httpx.Response(status, request=req, json={"error": {"code": status, "message": message}})
    return cls(message, response=resp, body={"error": {"code": status, "message": message}})


# C1
def test_outputs_for_keeps_dots_in_name(tmp_path):
    o = outputs_for(tmp_path / "2026.10.17")
    assert (o.json.name, o.raw.name, o.pdf.name) == ("2026.10.17.json", "2026.10.17_raw.json", "2026.10.17.pdf")


# C2
@pytest.mark.parametrize("err", [
    _sdk_error(ce.BadRequestError, 400, "API key not valid. Please pass a valid API key."),
    _sdk_error(ce.PermissionDeniedError, 403, "Permission denied"),
    _sdk_error(ce.AuthenticationError, 401, "Unauthenticated"),
])
def test_real_sdk_auth_errors_stop_without_retry(monkeypatch, err):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = GeminiReader("KEY"); r._call = Mock(side_effect=err)
    with pytest.raises(ReaderAuthError):
        r.read(b"png")
    assert r._call.call_count == 1


# I1
@pytest.mark.parametrize("err", [
    _sdk_error(ce.BadRequestError, 400, "Invalid JSON payload: unknown field temperature"),
    _sdk_error(ce.NotFoundError, 404, "models/gemini-x is not found"),
])
def test_other_4xx_stop_the_run_with_reason(monkeypatch, err):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = GeminiReader("KEY"); r._call = Mock(side_effect=err)
    with pytest.raises(ReaderRequestError) as e:
        r.read(b"png")
    assert r._call.call_count == 1 and str(err.status_code) in str(e.value)


def test_429_and_5xx_are_retried(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = GeminiReader("KEY")
    r._call = Mock(side_effect=[_sdk_error(ce.RateLimitError, 429, "quota"),
                                _sdk_error(ce.InternalServerError, 500, "oops"), page_result()])
    r.read(b"png")
    assert r._call.call_count == 3


# I2
def test_concurrent_cache_put_same_key(tmp_path):
    c = PageCache(tmp_path)
    errors = []
    barrier = threading.Barrier(8)

    def put():
        barrier.wait()
        try:
            for _ in range(20):
                c.put("h", 1, page_result())
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=put) for _ in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert errors == [] and c.get("h", 1) is not None


def test_cache_put_tolerates_windows_replace_conflict(tmp_path, monkeypatch):
    """Windows では、別のスレッドが置き換え中のファイルへの os.replace が PermissionError になる。"""
    c = PageCache(tmp_path)
    c.put("h", 1, page_result())
    monkeypatch.setattr("millsheet.cache.os.replace", Mock(side_effect=PermissionError(13, "Access is denied")))
    c.put("h", 1, page_result())
    assert c.get("h", 1) is not None and list(tmp_path.glob("*.tmp")) == []


def test_cache_put_raises_replace_error_when_nothing_written(tmp_path, monkeypatch):
    c = PageCache(tmp_path)
    monkeypatch.setattr("millsheet.cache.os.replace", Mock(side_effect=PermissionError(13, "Access is denied")))
    with pytest.raises(PermissionError):
        c.put("h", 1, page_result())
    assert list(tmp_path.glob("*.tmp")) == []


def test_cache_write_failure_does_not_stop_reading(tmp_path, monkeypatch):
    make_pdf(tmp_path / "src/a.pdf", 1)
    monkeypatch.setattr(PageCache, "put", Mock(side_effect=OSError("disk full")))
    e = read_folder(tmp_path / "src", FakeReader(), PageCache(tmp_path / "c"))
    assert e[0].result is not None




# I6
def test_render_failure_becomes_page_error(tmp_path, monkeypatch):
    make_pdf(tmp_path / "src/a.pdf", 2)
    real = extract.render_png

    def flaky(pdf, page_no, dpi=200):
        if page_no == 2:
            raise RuntimeError("cannot render")
        return real(pdf, page_no, dpi)
    monkeypatch.setattr(extract, "render_png", flaky)
    e = read_folder(tmp_path / "src", FakeReader(), PageCache(tmp_path / "c"))
    assert e[0].result is not None and e[1].result is None and "画像にできませんでした" in e[1].error


def test_unreadable_file_hash_becomes_file_error(tmp_path, monkeypatch):
    make_pdf(tmp_path / "src/a.pdf", 1); make_pdf(tmp_path / "src/b.pdf", 1)
    real = extract.file_hash
    monkeypatch.setattr(extract, "file_hash",
                        lambda p: (_ for _ in ()).throw(OSError("locked")) if p.name == "a.pdf" else real(p))
    e = read_folder(tmp_path / "src", FakeReader(), PageCache(tmp_path / "c"))
    assert e[0].file == "a.pdf" and e[0].page_no is None and e[0].error == "PDF を読み込めませんでした"
    assert e[1].result is not None


# Minor（取り返しがつかないので修正）: 出力先のフォルダが無くても raw を保存する
def test_missing_output_dir_is_created(tmp_path):
    make_pdf(tmp_path / "src/a.pdf", 1)
    res = run(tmp_path / "src", tmp_path / "new/dir/o", settings=Settings(), gemini_key="g",
              reader=FakeReader())
    assert res.outputs.raw.exists() and res.outputs.xlsx.exists()
