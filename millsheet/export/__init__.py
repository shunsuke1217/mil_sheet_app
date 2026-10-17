from pathlib import Path

from millsheet.export.base import Exporter
from millsheet.export.local_xlsx import LocalXlsxExporter


def get_exporter(name: str, xlsx_path: Path) -> Exporter:
    if name == "local_xlsx":
        return LocalXlsxExporter(xlsx_path)
    raise ValueError(f"出力先「{name}」には対応していません")
