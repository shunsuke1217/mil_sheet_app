"""読み取りから出力までの入口。画面はここの run / rebuild を別スレッドで呼ぶだけにする。"""
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from millsheet import paths
from millsheet.cache import PageCache
from millsheet.export import get_exporter
from millsheet.export.base import OutputLockedError
from millsheet.export.json_out import write_json
from millsheet.extract import GeminiReader, PageReader, list_pdfs, read_folder
from millsheet.master import Master, fetch_master
from millsheet.merge_pdf import MergeError, merge_pages
from millsheet.normalize import R_NO_MASTER, Record, build_records
from millsheet.ordering import order_records
from millsheet.prompt import MODEL
from millsheet.rawfile import read_raw, write_raw
from millsheet.schema import PageEntry
from millsheet.settings import Settings

log = logging.getLogger(__name__)

MasterLoader = Callable[[], tuple[Master, list[str]]]


@dataclass
class Outputs:
    xlsx: Path
    json: Path
    raw: Path
    pdf: Path | None


@dataclass
class RunResult:
    records: list[Record]
    outputs: Outputs
    master: Master
    warnings: list[str]
    errors: list[str]


def outputs_for(xlsx: Path) -> Outputs:
    xlsx = Path(xlsx)
    stem = xlsx.stem   # 「2026.10.17.xlsx」でも最後の拡張子だけを外す
    return Outputs(xlsx, xlsx.with_name(f"{stem}.json"), xlsx.with_name(f"{stem}_raw.json"),
                   xlsx.with_name(f"{stem}.pdf"))


def _locked_message(e: OutputLockedError) -> str:
    return f"{e.path.name} が他のアプリで開かれています。閉じてから『作り直す』を押してください"


def _master_loader(settings: Settings, master_loader: MasterLoader | None) -> MasterLoader:
    if master_loader:
        return master_loader
    if not settings.sheet_url:
        raise ValueError("設定画面で単重マスタのスプレッドシートの URL を入力してください")
    return lambda: fetch_master(settings.sheet_url)


def _build_and_export(pages: list[PageEntry], source_dir: Path | None, outputs: Outputs, master: Master,
                      warnings: list[str], settings: Settings) -> RunResult:
    errors: list[str] = []
    ordered, refs = order_records(build_records(pages, master))
    dicts = [r.to_dict() for r in ordered]
    meta = {"作成日時": datetime.now().isoformat(timespec="seconds"), "モデル": MODEL, "単重マスタ": master.meta()}
    try:
        write_json(outputs.json, dicts, meta)
    except OutputLockedError as e:
        errors.append(_locked_message(e))
    try:
        get_exporter(settings.exporter, outputs.xlsx).export(dicts, meta)
    except OutputLockedError as e:
        errors.append(_locked_message(e))
    pdf = outputs.pdf
    if source_dir is None or not Path(source_dir).is_dir():
        pdf = None
        errors.append("元の PDF が見つからないため、PDF は作れませんでした")
    elif not refs:
        pdf = None
    else:
        try:
            merge_pages(refs, Path(source_dir), outputs.pdf)
        except MergeError as e:
            pdf = None
            errors.append(f"元の PDF が見つからないため、PDF は作れませんでした（{'、'.join(e.missing)}）")
        except OutputLockedError as e:
            errors.append(_locked_message(e))
    outputs = Outputs(outputs.xlsx, outputs.json, outputs.raw, pdf)
    for msg in warnings + errors:
        log.warning(msg)
    log.info("出力しました: %s（%d 行）", outputs.xlsx, len(ordered))
    return RunResult(ordered, outputs, master, warnings, errors)


def run(source_dir: Path, xlsx: Path, *, settings: Settings, gemini_key: str,
        reader: PageReader | None = None, workers: int = 4, master_loader: MasterLoader | None = None,
        on_progress: Callable[[str, int, int, int, int], None] = lambda *a: None,
        cancel: threading.Event | None = None) -> RunResult:
    source_dir = Path(source_dir)
    if reader is None and not gemini_key:
        raise ValueError("設定画面で Gemini の API キーを入力してください")
    loader = _master_loader(settings, master_loader)
    if not list_pdfs(source_dir):
        raise ValueError(f"フォルダに PDF がありません: {source_dir}")
    Path(xlsx).parent.mkdir(parents=True, exist_ok=True)   # 読み終えてから保存できないのを防ぐ
    log.info("読み取りを始めます: %s → %s", source_dir, xlsx)
    master, warnings = loader()           # 課金の前にマスタを確かめる
    pages = read_folder(source_dir, reader or GeminiReader(gemini_key), PageCache(paths.cache_dir()),
                        workers=workers, on_progress=on_progress, cancel=cancel)
    outputs = outputs_for(xlsx)
    write_raw(outputs.raw, source_dir, pages)
    return _build_and_export(pages, source_dir, outputs, master, list(warnings), settings)


def rebuild(raw: Path, xlsx: Path, *, settings: Settings,
            master_loader: MasterLoader | None = None) -> RunResult:
    loader = _master_loader(settings, master_loader)
    master, warnings = loader()
    source_dir, pages = read_raw(raw)
    log.info("作り直します: %s → %s", raw, xlsx)
    outputs = outputs_for(xlsx)
    outputs = Outputs(outputs.xlsx, outputs.json, Path(raw), outputs.pdf)
    return _build_and_export(pages, source_dir, outputs, master, list(warnings), settings)


def review_messages(records: list[Record]) -> list[str]:
    out = []
    for r in records:
        if not r.reasons:
            continue
        why = "、".join(r.reasons)
        if r.page_no is None:
            msg = f"{r.file} を読み込めませんでした（{why}）"
        else:
            msg = f"{r.file} の {r.page_no} ページ目がうまく読み込めませんでした（{why}）"
        if R_NO_MASTER in r.reasons:
            msg += f"　登録が必要: {r.category} {r.size}"
        out.append(msg)
    return out
