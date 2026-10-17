"""出力の JSON（SPEC 12.1）。"""
import json
from pathlib import Path

from millsheet.export.base import save_atomic


def write_json(path: Path, records: list[dict], meta: dict) -> None:
    text = json.dumps({"meta": meta, "records": records}, ensure_ascii=False, indent=1)
    save_atomic(path, lambda p: p.write_text(text, "utf-8"))
