"""ページ単位の読み取りキャッシュ（PDF のハッシュ＋ページ番号）。成功した結果だけ保存する。"""
import hashlib
import os
from pathlib import Path

from millsheet.prompt import MODEL, PROMPT_VERSION
from millsheet.schema import PageResult


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class PageCache:
    def __init__(self, dir: Path):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, pdf_hash: str, page_no: int) -> Path:
        return self.dir / f"{pdf_hash}_{page_no}_{MODEL}_{PROMPT_VERSION}.json"

    def get(self, pdf_hash: str, page_no: int) -> PageResult | None:
        p = self._path(pdf_hash, page_no)
        if not p.exists():
            return None
        try:
            return PageResult.model_validate_json(p.read_text("utf-8"))
        except ValueError:
            return None

    def put(self, pdf_hash: str, page_no: int, result: PageResult) -> None:
        p = self._path(pdf_hash, page_no)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(result.model_dump_json(), "utf-8")
        os.replace(tmp, p)
