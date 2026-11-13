"""xlsx の行の並び順と、まとめた PDF のページ番号（SPEC 8.6）。"""
from millsheet.normalize import Record
from millsheet.sizes import size_key

# 出力の並び順の唯一の定義（classify.CATEGORIES は判定の優先度で、別の意味）
CATEGORY_ORDER: list[str] = [
    "H形鋼", "I形鋼", "コラム", "STKR", "PL", "FB", "溝形鋼", "Cチャン", "丸パイプ", "アングル",
    "T形鋼", "チェッカープレート", "角鋼", "丸鋼", "D（鉄筋）", "デッキ", "EXメタ",
]
_RANK_UNCLASSIFIED = len(CATEGORY_ORDER)       # 品名が null の行・行が読めなかった証明書
_RANK_NOT_LINE = len(CATEGORY_ORDER) + 1       # 証明書ではないページ・読み取りに失敗したページ

PageRef = tuple[str, int]


def _sort_key(r: Record):
    if r.kind in ("not_certificate", "error"):
        rank = _RANK_NOT_LINE
    elif r.category in CATEGORY_ORDER:
        rank = CATEGORY_ORDER.index(r.category)
    else:
        rank = _RANK_UNCLASSIFIED
    key = size_key(r.size) if r.size else None
    size_part = (1, ()) if key is None else (0, tuple(-n for n in key[1]))
    length_part = (1, 0) if r.length_mm is None else (0, -r.length_mm)
    return rank, size_part, length_part, r.input_index


def order_records(records: list[Record]) -> tuple[list[Record], list[PageRef]]:
    """並べ替えたうえで、同じページの行は、そのページで一番早く出てくる行の位置にまとめる。"""
    by_sort = sorted(records, key=_sort_key)
    groups: dict[object, list[Record]] = {}   # ページごとの行（並べ替えた順）。ページの無い行は 1 行ずつ
    for r in by_sort:
        key = (r.file, r.page_no) if r.page_no is not None else id(r)
        groups.setdefault(key, []).append(r)
    ordered: list[Record] = []
    pages: list[PageRef] = []
    for key, rows in groups.items():
        label = None
        if rows[0].page_no is not None:
            pages.append(key)
            label = f"Ｐ-{len(pages)}"
        for r in rows:
            r.page_label = label
        ordered.extend(rows)
    return ordered, pages
