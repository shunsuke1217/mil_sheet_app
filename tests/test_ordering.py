from millsheet.ordering import CATEGORY_ORDER, order_records
from tests.helpers import rec


def test_category_order_constant():
    assert CATEGORY_ORDER == ["H形鋼", "I形鋼", "コラム", "STKR", "PL", "FB", "溝形鋼", "Cチャン", "丸パイプ", "アングル",
                              "T形鋼", "チェッカープレート", "角鋼", "丸鋼", "D（鉄筋）", "デッキ", "EXメタ"]


def test_category_order():
    recs = [rec(cat="アングル", i=0), rec(cat="I形鋼", i=1), rec(cat=None, i=2), rec(cat="PL", i=3),
            rec(cat="H形鋼", i=4), rec(kind="error", cat=None, i=5), rec(kind="no_lines", cat=None, i=6)]
    ordered = order_records(recs)[0]
    assert [r.category for r in ordered][:4] == ["H形鋼", "I形鋼", "PL", "アングル"]
    assert [r.input_index for r in ordered][4:] == [2, 6, 5]


def test_size_desc_then_length_desc_then_input_order():
    recs = [rec(size="Ｈ-200×100×5.5×8", length=7000, i=0), rec(size="Ｈ-400×200×8×13", length=11000, i=1),
            rec(size="Ｈ-400×200×8×13", length=12000, i=2), rec(size="Ｈ-350×175×7×11", length=7000, i=3),
            rec(size="Ｈ-400×200×8×13", length=12000, i=4), rec(size=None, length=9000, i=5)]
    assert [r.input_index for r in order_records(recs)[0]] == [2, 4, 1, 3, 0, 5]


def test_null_length_goes_last_within_size():
    recs = [rec(size="Ｈ-400×200×8×13", length=None, i=0), rec(size="Ｈ-400×200×8×13", length=5000, i=1)]
    assert [r.input_index for r in order_records(recs)[0]] == [1, 0]


def test_page_placed_at_earliest_row_and_shares_label():
    # 1.pdf p1 に 溝形鋼、2.pdf p1 に H形鋼 と 溝形鋼
    recs = [rec(file="1.pdf", page=1, cat="溝形鋼", size="［-150×75×6.5", i=0),
            rec(file="2.pdf", page=1, cat="H形鋼", size="Ｈ-200×200×8×12", i=1),
            rec(file="2.pdf", page=1, cat="溝形鋼", size="［-100×50×5", i=2)]
    ordered, pages = order_records(recs)
    assert pages == [("2.pdf", 1), ("1.pdf", 1)]
    assert [(r.input_index, r.page_label) for r in ordered] == [(1, "Ｐ-1"), (0, "Ｐ-2"), (2, "Ｐ-1")]


def test_unreadable_pdf_row_gets_no_page_number():
    ordered, pages = order_records([rec(kind="error", file="broken.pdf", page=None, cat=None, i=0)])
    assert ordered[0].page_label is None and pages == [] and ordered[0].to_dict()["ページ"] == "—"


def test_sample_keeps_original_order(sample_records):
    ordered, pages = order_records([r for r in sample_records if r.file == "20261014084620.pdf"])
    assert [r.page_label for r in ordered] == [f"Ｐ-{i}" for i in range(1, 11)]
    assert pages == [("20261014084620.pdf", i) for i in range(1, 11)]


def test_does_not_mutate_input_order(sample_records):
    before = [r.input_index for r in sample_records]
    order_records(sample_records)
    assert [r.input_index for r in sample_records] == before
