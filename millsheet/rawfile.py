"""AI の生の読み取り結果（SPEC 12.3）。これがあれば API を使わずに作り直せる。"""
import json
from pathlib import Path

from millsheet.export.base import save_atomic
from millsheet.schema import PageEntry, PageResult


def write_raw(path: Path, source_dir: Path | None, pages: list[PageEntry]) -> None:
    grouped: dict[str, list[dict]] = {}
    for e in pages:
        grouped.setdefault(e.file, []).append({
            "page": e.page_no,
            "result": e.result.model_dump(mode="json") if e.result else None,
            "error": e.error,
        })
    data = {"source_dir": str(source_dir) if source_dir else None, "pages": grouped}
    text = json.dumps(data, ensure_ascii=False, indent=1)
    save_atomic(path, lambda p: p.write_text(text, "utf-8"))


def read_raw(path: Path) -> tuple[Path | None, list[PageEntry]]:
    data = json.loads(Path(path).read_text("utf-8"))
    pages = []
    for file in sorted(data["pages"]):
        for e in sorted(data["pages"][file], key=lambda e: e["page"] or 0):
            r = e.get("result")
            pages.append(PageEntry(file, e["page"], PageResult.model_validate(r) if r else None, e.get("error")))
    src = data.get("source_dir")
    return (Path(src) if src else None), pages
