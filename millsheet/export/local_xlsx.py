"""xlsx を PC 内に保存する（SPEC 12.2）。"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from millsheet.export.base import save_atomic

COLUMNS = [  # (見出し, レコードのキー)
    ("ページ", "ページ"), ("品名", "品名"), ("材質", "材質"), ("寸法", "寸法"), ("長さ(mm)", "長さ_mm"),
    ("本数", "本数"), ("ミルシート重量(kg/m)", "ミルシート重量"), ("重量(kg)", "重量"),
    ("要確認", "要確認"), ("確認理由", "確認理由"),
]
YELLOW = PatternFill("solid", fgColor="FFF9C4")
RED = PatternFill("solid", fgColor="FFCDD2")
NUMBER_FORMAT_COLUMNS = {5, 8}
VALUE_COLUMNS = range(1, 9)        # null を赤くする列（要確認・確認理由の列は除く）
PL_BLANK_COLUMNS = {5, 7}          # PL は長さ・ミルシート重量が空欄で正しい


class LocalXlsxExporter:
    def __init__(self, path: Path):
        self.path = Path(path)

    def export(self, records: list[dict], meta: dict) -> str:
        wb = Workbook()
        ws = wb.active
        ws.title = "ミルシート"
        ws.append([h for h, _ in COLUMNS])
        for c in ws[1]:
            c.font = Font(bold=True)
        for row_no, rec in enumerate(records, start=2):
            for col, (_, key) in enumerate(COLUMNS, start=1):
                v = rec.get(key)
                if key == "要確認":
                    v = "要確認" if v else None
                elif key == "確認理由":
                    v = "、".join(v) if v else None
                cell = ws.cell(row_no, col, v)
                if col in NUMBER_FORMAT_COLUMNS:
                    cell.number_format = "#,##0"
                pl_blank = rec.get("品名") == "PL" and col in PL_BLANK_COLUMNS
                if v is None and col in VALUE_COLUMNS and not pl_blank:
                    cell.fill = RED
                elif rec.get("要確認"):
                    cell.fill = YELLOW
        last = 1 + len(records)
        ws.cell(last + 1, 7, "合計").font = Font(bold=True)
        total = ws.cell(last + 1, 8, f"=SUM(H2:H{last})")
        total.number_format = "#,##0"
        total.font = Font(bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:J{last}"
        for col, width in zip("ABCDEFGHIJ", (8, 12, 10, 22, 10, 7, 12, 10, 8, 60)):
            ws.column_dimensions[col].width = width
        save_atomic(self.path, lambda p: wb.save(p))
        return str(self.path)
