"""出力先を差し替えられる形（SPEC 12.5）。"""
import os
from pathlib import Path
from typing import Callable, Protocol


class Exporter(Protocol):
    def export(self, records: list[dict], meta: dict) -> str: ...  # 保存先（パスや URL）を返す


class OutputLockedError(Exception):
    def __init__(self, path: Path):
        super().__init__(f"{Path(path).name} が他のアプリで開かれています")
        self.path = Path(path)


def save_atomic(path: Path, write: Callable[[Path], None]) -> None:
    """一時ファイルに書いてから置き換える。書けなければ OutputLockedError。"""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        write(tmp)
        os.replace(tmp, path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise OutputLockedError(path) from None
