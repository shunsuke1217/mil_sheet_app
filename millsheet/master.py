"""単重マスタ（SPEC 7章）。Google スプレッドシートを API キーで読む。"""
import csv
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx

from millsheet import paths
from millsheet.applog import mask
from millsheet.sizes import size_key

log = logging.getLogger(__name__)

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
HEADERS = ("品名", "サイズ", "単重")


@dataclass
class MasterEntry:
    category: str
    size: str
    unit_weight: float


@dataclass
class Master:
    entries: list[MasterEntry]
    source: Literal["sheet", "cache", "file"]
    fetched_at: datetime

    def __post_init__(self):
        self._index = {size_key(e.size): e for e in self.entries}

    def lookup(self, size: str) -> MasterEntry | None:
        key = size_key(size)
        return self._index.get(key) if key else None

    def meta(self) -> dict:
        source = {"sheet": "スプレッドシート", "cache": "キャッシュ", "file": "ファイル"}[self.source]
        return {"取得元": source, "件数": len(self.entries), "取得日時": self.fetched_at.isoformat(timespec="seconds")}


class MasterValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("単重マスタに問題があります:\n" + "\n".join(errors))
        self.errors = errors


class MasterFetchError(Exception):
    pass


def spreadsheet_id_from_url(url: str) -> str:
    url = url.strip()
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{5,}", url):
        return url
    raise MasterFetchError("スプレッドシートの URL が正しくありません")


def _cell(v) -> str:
    return unicodedata.normalize("NFKC", str(v)).strip() if v is not None else ""


def parse_sheet_values(values: list[list]) -> list[MasterEntry]:
    if not values:
        raise MasterValidationError(["シートが空です"])
    header = [_cell(h) for h in values[0]]
    missing = [h for h in HEADERS if h not in header]
    if missing:
        raise MasterValidationError([f"1 行目に見出し「{'」「'.join(missing)}」がありません"])
    col = {h: header.index(h) for h in HEADERS}
    entries, errors, seen = [], [], {}
    for row_no, row in enumerate(values[1:], start=2):
        if not any(_cell(v) for v in row):
            continue
        get = lambda h: row[col[h]] if col[h] < len(row) else None  # noqa: E731
        category, size_text, weight = _cell(get("品名")), str(get("サイズ") or "").strip(), get("単重")
        try:
            uw = float(weight) if isinstance(weight, (int, float)) else float(_cell(weight).replace(",", ""))
        except ValueError:
            uw = None
        if uw is None or not uw > 0:
            errors.append(f"{row_no} 行目: 単重が 0 より大きい数値ではありません（{_cell(weight)}）")
            continue
        key = size_key(size_text) if size_text else None
        if key is None:
            errors.append(f"{row_no} 行目: サイズが正しくありません（{size_text}）")
            continue
        if key in seen:
            errors.append(f"{row_no} 行目: サイズ「{size_text}」が {seen[key]} 行目と重複しています")
            continue
        seen[key] = row_no
        entries.append(MasterEntry(category, size_text, uw))
    if errors:
        raise MasterValidationError(errors)
    return entries


def _entries_to_json(entries: list[MasterEntry]) -> list[dict]:
    return [{"品名": e.category, "サイズ": e.size, "単重": e.unit_weight} for e in entries]


def _entries_from_json(data: list[dict]) -> list[MasterEntry]:
    return [MasterEntry(d["品名"], d["サイズ"], float(d["単重"])) for d in data]


def _write_cache(m: Master) -> None:
    p = paths.master_cache_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": m.fetched_at.isoformat(), "entries": _entries_to_json(m.entries)},
                              ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def _read_cache() -> Master | None:
    p = paths.master_cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text("utf-8"))
        return Master(_entries_from_json(data["entries"]), "cache", datetime.fromisoformat(data["fetched_at"]))
    except (ValueError, KeyError, TypeError) as e:
        log.warning("単重マスタのキャッシュを読めません: %s", e)
        return None


def _http_error_message(status: int, body: str, sheet_name: str) -> str:
    if status == 400 and ("API key not valid" in body or "API_KEY_INVALID" in body):
        return "Google の API キーが正しくありません"
    if status == 400 and "Unable to parse range" in body:
        return f"シート名「{sheet_name}」が見つかりません"
    if status == 403:
        return ("読み取りが許可されていません。共有設定が「リンクを知っている全員が閲覧可」か、"
                "API キーで Google Sheets API が使えるかを確認してください")
    if status == 404:
        return "スプレッドシートが見つかりません。URL を確認してください"
    return f"スプレッドシートを読めませんでした（HTTP {status}）"


def _fetch_values(sheet_id: str, sheet_name: str, api_key: str, client: httpx.Client) -> list[list]:
    rng = f"'{sheet_name.replace(chr(39), chr(39) * 2)}'!A:Z" if sheet_name else "A:Z"
    url = f"{SHEETS_API}/{sheet_id}/values/{quote(rng, safe='')}"
    try:
        r = client.get(url, params={"key": api_key, "valueRenderOption": "UNFORMATTED_VALUE"}, timeout=15)
    except httpx.HTTPError as e:
        log.warning("スプレッドシートに接続できません: %s", mask(str(e), [api_key]))
        raise MasterFetchError("ネットに接続できません") from None
    if r.status_code != 200:
        log.warning("スプレッドシートの取得に失敗: HTTP %s %s", r.status_code, mask(r.text[:300], [api_key]))
        raise MasterFetchError(_http_error_message(r.status_code, r.text, sheet_name))
    return r.json().get("values", [])


def fetch_master(url: str, sheet_name: str, api_key: str, *,
                 client: httpx.Client | None = None) -> tuple[Master, list[str]]:
    sheet_id = spreadsheet_id_from_url(url)
    if not api_key:
        raise MasterFetchError("設定画面で Google の API キーを入力してください")
    client = client or httpx.Client()
    try:
        values = _fetch_values(sheet_id, sheet_name.strip(), api_key, client)
    except MasterFetchError as e:
        cached = _read_cache()
        if cached is None:
            raise
        when = cached.fetched_at.strftime("%Y-%m-%d %H:%M")
        return cached, [f"スプレッドシートを読めなかったため、前回取得した単重（{when}）を使います: {e}"]
    m = Master(parse_sheet_values(values), "sheet", datetime.now())
    _write_cache(m)
    log.info("単重マスタを取得しました: %s 件", len(m.entries))
    return m, []


def load_master_file(path: Path) -> Master:
    data = json.loads(Path(path).read_text("utf-8"))
    return Master(_entries_from_json(data), "file", datetime.fromtimestamp(Path(path).stat().st_mtime))


def export_bundled_csv(path: Path) -> None:
    data = json.loads(paths.bundled_master_path().read_text("utf-8"))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        for d in data:
            w.writerow([d["品名"], d["サイズ"], d["単重"]])
