"""読み取り結果からレコードを作り、正規化・チェックする（SPEC 8章、9章）。重量は xlsx の数式で出す（8.5 節）。"""
from dataclasses import dataclass
from typing import Literal

from millsheet.classify import classify
from millsheet.schema import Line, PageEntry, PageResult
from millsheet.sizes import normalize_size, parse_length_mm

R_NO_CIRCLE = "丸数字が書かれていません"
R_UNREADABLE = "丸数字が読めません"
R_MISSING = "必須項目が空です（{}）"
R_UNCERTAIN = "AI が読み取りに自信がないと返しました{}"
R_OVER_QTY = "丸数字の本数（{}）が印字された本数（{}）を超えています"
R_STAMP = "押印の本数（{}）と丸数字の合計（{}）が一致しません"
R_NOT_CERT = "証明書ではないページです"
R_ERROR = "読み取りに失敗しました（{}）"
R_NO_LINES = "行が読み取れませんでした"


@dataclass
class Record:
    file: str
    page_no: int | None
    category: str | None
    grade: str | None
    size: str | None
    length_mm: int | None
    qty: int | None
    printed_qty: int | None    # 元本数（印字された員数）
    mass_kg: float | None      # 証明書に印字された質量
    reasons: list[str]
    input_index: int
    kind: Literal["line", "no_lines", "not_certificate", "error"] = "line"   # no_lines: 証明書だが行が 1 つも返らなかった
    page_label: str | None = None

    def needs_review(self) -> bool:
        return bool(self.reasons)

    def to_dict(self) -> dict:
        return {
            "ページ": self.page_label or "—",
            "ファイル": self.file,
            "ページ番号": self.page_no,
            "材種": self.category,
            "材質": self.grade,
            "寸法": self.size,
            "長さ_mm": self.length_mm,
            "本数": self.qty,
            "要確認": self.needs_review(),
            "確認理由": list(self.reasons),
            "元本数": self.printed_qty,
            "質量": self.mass_kg,
        }


def _empty(entry: PageEntry, index: int, kind: str, reasons: list[str]) -> Record:
    return Record(entry.file, entry.page_no, None, None, None, None, None, None, None, reasons, index, kind)


def _line_record(entry: PageEntry, ln: Line, index: int, stamp_reason: str | None) -> Record:
    category = classify(ln.commodity_raw, ln.size_raw)
    is_pl = category == "PL"
    size = normalize_size(category, ln.size_raw)
    length = None if is_pl else parse_length_mm(ln.length_raw)
    qty = ln.circled_qty if ln.circle_status == "あり" else None
    reasons: list[str] = []

    # 9章のチェック（番号順）
    if ln.circle_status == "なし":
        reasons.append(R_NO_CIRCLE)
    elif ln.circle_status == "読めない":
        reasons.append(R_UNREADABLE)
    required = [("材種", category), ("材質", ln.grade), ("寸法", size)]
    if not is_pl:
        required.append(("長さ", length))
    required += [("本数", qty), ("元本数", ln.printed_qty or None), ("質量", ln.mass_kg)]
    missing = [name for name, v in required if v is None or v == ""]
    if missing:
        reasons.append(R_MISSING.format("、".join(missing)))
    if ln.uncertain:
        reasons.append(R_UNCERTAIN.format(f"（{ln.note}）" if ln.note else ""))
    if qty is not None and ln.printed_qty and qty > ln.printed_qty:   # 0 は読めなかったものとして元本数の空で知らせる
        reasons.append(R_OVER_QTY.format(qty, ln.printed_qty))
    if stamp_reason:
        reasons.append(stamp_reason)

    return Record(entry.file, entry.page_no, category, ln.grade, size, length, qty, ln.printed_qty, ln.mass_kg,
                  reasons, index)


def _stamp_reason(result: PageResult) -> str | None:
    circled = [ln.circled_qty for ln in result.lines if ln.circle_status == "あり" and ln.circled_qty is not None]
    if not circled or result.stamp_valid_qty is None:
        return None
    total = sum(circled)
    return None if total == result.stamp_valid_qty else R_STAMP.format(result.stamp_valid_qty, total)


def build_records(pages: list[PageEntry]) -> list[Record]:
    records: list[Record] = []
    for entry in pages:
        r = entry.result
        if r is None:
            records.append(_empty(entry, len(records), "error", [R_ERROR.format(entry.error or "原因不明")]))
        elif not r.is_certificate:
            records.append(_empty(entry, len(records), "not_certificate", [R_NOT_CERT]))
        elif not r.lines:
            records.append(_empty(entry, len(records), "no_lines", [R_NO_LINES]))
        else:
            stamp = _stamp_reason(r)
            for ln in r.lines:
                records.append(_line_record(entry, ln, len(records), stamp))
    return records
