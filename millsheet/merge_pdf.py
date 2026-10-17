"""並べ替えた PDF を 1 つにまとめる（SPEC 12.4）。元の PDF のページをそのままコピーする。"""
from pathlib import Path

import pymupdf

from millsheet.export.base import save_atomic

PageRef = tuple[str, int]


class MergeError(Exception):
    def __init__(self, missing: list[str]):
        super().__init__("元の PDF が見つかりません: " + "、".join(missing))
        self.missing = missing


def merge_pages(pages: list[PageRef], source_dir: Path, out_path: Path) -> None:
    sources: dict[str, pymupdf.Document] = {}
    missing = []
    for file, _ in pages:
        if file in sources or file in missing:
            continue
        try:
            sources[file] = pymupdf.open(Path(source_dir) / file)
        except (pymupdf.FileNotFoundError, pymupdf.FileDataError, RuntimeError):
            missing.append(file)
    if missing:
        raise MergeError(missing)
    out = pymupdf.open()
    try:
        for file, page_no in pages:
            out.insert_pdf(sources[file], from_page=page_no - 1, to_page=page_no - 1)
        save_atomic(Path(out_path), lambda p: out.save(p, garbage=3, deflate=True))
    finally:
        out.close()
        for d in sources.values():
            d.close()
