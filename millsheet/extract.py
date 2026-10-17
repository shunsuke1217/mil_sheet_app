"""PDF の一覧・画像化と、Gemini での読み取り（SPEC 5章、6章）。"""
import base64
import copy
import logging
import threading
import time
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable, Protocol

import pymupdf

from millsheet.applog import mask
from millsheet.cache import PageCache, file_hash
from millsheet.prompt import MODEL, SYSTEM_PROMPT, USER_PROMPT
from millsheet.schema import PageEntry, PageResult

log = logging.getLogger(__name__)

RETRY_WAITS = (1, 2, 4)
_render_lock = threading.Lock()  # PyMuPDF はスレッドセーフではないので画像化は 1 つずつ


class Cancelled(Exception):
    pass


class PdfOpenError(Exception):
    pass


class PageReadError(Exception):
    pass


class ReaderAuthError(Exception):
    pass


class PageReader(Protocol):
    def read(self, png: bytes) -> PageResult: ...


def list_pdfs(folder: Path) -> list[str]:
    folder = Path(folder)
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".pdf")


def _open(pdf: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(pdf)
    except Exception as e:  # 壊れた PDF は様々な例外になる
        raise PdfOpenError("PDF を開けませんでした") from e
    if doc.needs_pass:
        doc.close()
        raise PdfOpenError("PDF にパスワードが掛かっているため開けませんでした")
    return doc


def page_count(pdf: Path) -> int:
    with _render_lock:
        doc = _open(pdf)
        try:
            return doc.page_count
        finally:
            doc.close()


def render_png(pdf: Path, page_no: int, dpi: int = 200) -> bytes:
    with _render_lock:
        doc = _open(pdf)
        try:
            return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")
        finally:
            doc.close()


def inline_refs(schema: dict) -> dict:
    """pydantic の JSON スキーマの $defs / $ref を展開する（API が $ref を受け付けない場合に備える）。"""
    defs = schema.get("$defs", {})

    def expand(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return expand(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: expand(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [expand(v) for v in node]
        return node

    return expand(schema)


def _is_auth_error(e: Exception) -> bool:
    code = getattr(e, "code", None)
    text = f"{getattr(e, 'message', '')} {getattr(e, 'details', '')} {e}"
    if code in (401, 403):
        return True
    return code == 400 and ("API_KEY_INVALID" in text or "API key not valid" in text)


class GeminiReader:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._schema = inline_refs(PageResult.model_json_schema())

    def _call(self, png: bytes) -> PageResult:
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        interaction = self._client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM_PROMPT,
            input=[{"type": "text", "text": USER_PROMPT},
                   {"type": "image", "data": base64.b64encode(png).decode(), "mime_type": "image/png"}],
            response_format={"type": "text", "mime_type": "application/json", "schema": self._schema},
            generation_config={"temperature": 0, "seed": 0, "thinking_level": "low"},
            store=False,
        )
        return PageResult.model_validate_json(interaction.output_text)

    def read(self, png: bytes) -> PageResult:
        last: Exception | None = None
        for attempt in range(len(RETRY_WAITS) + 1):
            try:
                return self._call(png)
            except Exception as e:
                if _is_auth_error(e):
                    raise ReaderAuthError("Gemini の API キーが正しくありません") from None
                last = e
                log.warning("Gemini の呼び出しに失敗（%d 回目）: %s", attempt + 1, mask(str(e), [self.api_key]))
                if attempt < len(RETRY_WAITS):
                    time.sleep(RETRY_WAITS[attempt])
        raise PageReadError(mask(f"{type(last).__name__}: {last}", [self.api_key])[:300])


def read_folder(folder: Path, reader: PageReader, cache: PageCache, *, workers: int = 4,
                on_progress: Callable[[str, int, int, int, int], None] = lambda *a: None,
                cancel: threading.Event | None = None) -> list[PageEntry]:
    folder = Path(folder)
    cancel = cancel or threading.Event()
    jobs: list[tuple[str, int, int, str]] = []          # (相対パス, ページ, そのファイルのページ数, ハッシュ)
    failed: dict[str, PageEntry] = {}
    for rel in list_pdfs(folder):
        try:
            n = page_count(folder / rel)
        except PdfOpenError as e:
            log.warning("%s: %s", rel, e)
            failed[rel] = PageEntry(rel, None, None, str(e))
            continue
        h = file_hash(folder / rel)
        jobs += [(rel, p, n, h) for p in range(1, n + 1)]
    total = len(jobs)
    results: dict[tuple[str, int], PageEntry] = {}
    done = [0]
    lock = threading.Lock()

    def work(job):
        rel, page, n, h = job
        if cancel.is_set():
            raise Cancelled()
        cached = cache.get(h, page)
        if cached is not None:
            entry, how = PageEntry(rel, page, cached), "キャッシュ"
        else:
            try:
                result = reader.read(render_png(folder / rel, page))
                cache.put(h, page, result)
                entry, how = PageEntry(rel, page, result), "読み取り成功"
            except PageReadError as e:
                entry, how = PageEntry(rel, page, None, str(e)), f"失敗（{e}）"
        log.info("%s %dページ目: %s", rel, page, how)
        with lock:
            results[(rel, page)] = entry
            done[0] += 1
            count = done[0]
        on_progress(rel, page, n, count, total)

    if cancel.is_set():
        raise Cancelled()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        finished, _ = wait(futures, return_when=FIRST_EXCEPTION)
        errors = [f.exception() for f in finished if f.exception()]
        if errors:
            cancel.set()
            pool.shutdown(wait=True, cancel_futures=True)
            raise errors[0]

    out = []
    for rel in list_pdfs(folder):
        if rel in failed:
            out.append(failed[rel])
        else:
            out += [results[k] for k in sorted(k for k in results if k[0] == rel)]
    return out
