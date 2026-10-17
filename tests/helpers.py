"""テストの共通部品。"""
import json
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"

URL = "https://docs.google.com/spreadsheets/d/TESTID/edit"
VALUES = [["品名", "サイズ", "単重"]] + [
    [e["品名"], e["サイズ"], str(e["単重"])]
    for e in json.loads((FIXTURES / "unit_weights.json").read_text("utf-8"))
]


def client_returning(status: int, body: dict, seen: list | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def client_raising(exc: Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc
    return httpx.Client(transport=httpx.MockTransport(handler))


def line(**kw):
    from millsheet.schema import Line
    d = dict(commodity_raw="H形鋼", grade="SS400", size_raw="200X200X8X12", length_raw="11.5M",
             circle_status="あり", circled_qty=1, printed_qty=18, mass_kg=10332, uncertain=False, note=None)
    d.update(kw)
    return Line(**d)


def page_with(*lines, stamp_valid_qty=None, file="x.pdf", page_no=1):
    from millsheet.schema import PageEntry, PageResult
    return PageEntry(file, page_no, PageResult(is_certificate=True, stamp_valid_qty=stamp_valid_qty, lines=list(lines)))


_rec_counter = [0]


def rec(**kw):
    """並べ替え・出力のテスト用の Record。file を省略すると入力順ごとに別ページになる。"""
    from millsheet.normalize import Record
    i = kw.pop("i", None)
    if i is None:
        i = _rec_counter[0]
        _rec_counter[0] += 1
    d = dict(file=kw.pop("file", f"p{i}.pdf"), page_no=kw.pop("page", 1), category=kw.pop("cat", "H形鋼"),
             grade="SS400", size=kw.pop("size", "Ｈ-200×200×8×12"), length_mm=kw.pop("length", 11500), qty=1,
             unit_weight=49.9, weight=574, reasons=kw.pop("reasons", []), input_index=i)
    d.update(kw)
    return Record(**d)


def make_pdf(path, n: int):
    """各ページに "{stem}-{n}" と書いた PDF を作る。"""
    import pymupdf
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for i in range(1, n + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"{path.stem}-{i}")
    doc.save(path)
    return path
