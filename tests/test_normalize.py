from millsheet.normalize import (R_ERROR, R_MISSING, R_NO_CIRCLE, R_NO_LINES, R_NOT_CERT, R_OVER_QTY, R_STAMP,
                                 R_UNCERTAIN, R_UNREADABLE, build_records)
from millsheet.schema import PageEntry, PageResult
from tests.helpers import line, page_with, rec

EXPECTED = [  # SPEC 18章（ページ番号, 材種, 材質, 寸法, 長さ, 本数, 重量 = 質量 ÷ 員数 × 本数）
    (1, "H形鋼", "SS400", "Ｈ-200×200×8×12", 11500, 1, 574),        # 10332 ÷ 18 × 1
    (2, "H形鋼", "SS400", "Ｈ-200×100×5.5×8", 7000, 2, 292),        # 1460 ÷ 10 × 2
    (3, "PL", "SN490C", "PL-22×2438×12192", None, 1, 5287),        # 員数 1 をすべて使う → 質量そのまま
    (4, "PL", "SN490C", "PL-19×2438×12192", None, 1, 4567),
    (5, "溝形鋼", "SS400", "［-150×75×6.5", 5500, 14, 1428),         # 1632 ÷ 16 × 14
    (6, "溝形鋼", "SS400", "［-100×50×5", 5500, 1, 52),             # 3708 ÷ 72 × 1 = 51.5 → 52
    (7, "Cチャン", "SSC400", "C-100×50×20×2.3", 12000, 40, 1948),    # 7305 ÷ 150 × 40
    (8, "Cチャン", "SSC400", "C-100×50×20×2.3", 8000, 16, 520),
    (9, "アングル", "SS400", "L-65×65×6", 5500, 1, 33),
    (10, "アングル", "SS400", "L-65×65×6", 5500, 5, 163),
]


def test_sample_reproduces_acceptance_table(sample_pages):
    recs = [r for r in build_records(sample_pages) if r.file == "20261014084620.pdf"]
    got = [(r.page_no, r.category, r.grade, r.size, r.length_mm, r.qty, r.weight) for r in recs]
    assert got == EXPECTED
    assert all(not r.needs_review() for r in recs)


def test_exception_sample_rows_are_kept_and_flagged(sample_pages):
    recs = [r for r in build_records(sample_pages) if r.file == "サンプル_例外.pdf"]
    assert len(recs) == 3                                           # 丸数字なしの 2 行 + API エラーの 1 行
    assert R_NO_CIRCLE in recs[0].reasons and recs[0].qty is None and recs[0].size == "Ｈ-294×200×8×12"
    assert R_MISSING.format("本数、重量") in recs[0].reasons
    assert recs[2].kind == "error" and recs[2].reasons == [R_ERROR.format("APIタイムアウト")]


def test_input_index_runs_across_pages(sample_pages):
    assert [r.input_index for r in build_records(sample_pages)] == list(range(13))


def test_unreadable_circle_reason_differs_from_no_circle():
    recs = build_records([page_with(line(circle_status="読めない", circled_qty=None, uncertain=True))])
    assert R_UNREADABLE in recs[0].reasons and R_NO_CIRCLE not in recs[0].reasons
    assert R_UNCERTAIN.format("") in recs[0].reasons


def test_uncertain_note_is_shown():
    r = build_records([page_with(line(uncertain=True, note="長さがかすれている"))])[0]
    assert R_UNCERTAIN.format("（長さがかすれている）") in r.reasons


def test_weight_is_mass_per_piece_times_circled_qty_for_every_category():
    r = build_records([page_with(line(commodity_raw="I形鋼", size_raw="200X100X7X10",
                                      circled_qty=3, printed_qty=10, mass_kg=2000))])[0]
    assert r.weight == 600 and r.reasons == []


def test_weight_needs_mass_and_printed_qty():
    r = build_records([page_with(line(mass_kg=None))])[0]
    assert r.weight is None and R_MISSING.format("質量、重量") in r.reasons
    r = build_records([page_with(line(printed_qty=None))])[0]
    assert r.weight is None and R_MISSING.format("員数、重量") in r.reasons


def test_over_qty_and_stamp_mismatch():
    recs = build_records([page_with(line(circled_qty=20, printed_qty=18), stamp_valid_qty=3)])
    assert R_OVER_QTY.format(20, 18) in recs[0].reasons and R_STAMP.format(3, 20) in recs[0].reasons


def test_stamp_mismatch_applies_to_every_line_on_page():
    recs = build_records([page_with(line(circled_qty=1), line(circle_status="なし", circled_qty=None),
                                    stamp_valid_qty=2)])
    assert all(R_STAMP.format(2, 1) in r.reasons for r in recs)


def test_stamp_skipped_when_missing_or_no_circles():
    assert not any(x.startswith("押印") for x in build_records([page_with(line(circled_qty=5))])[0].reasons)
    assert not any(x.startswith("押印") for x in build_records(
        [page_with(line(circle_status="なし", circled_qty=None), stamp_valid_qty=3)])[0].reasons)


def test_weight_prorated_and_half_up():
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circled_qty=1, printed_qty=2, mass_kg=657))])[0]
    assert r.weight == 329 and r.length_mm is None                    # 328.5 → 329（ROUND_HALF_UP）
    assert r.reasons == []


def test_over_qty_uses_full_mass():
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circled_qty=3, printed_qty=2, mass_kg=657))])[0]
    assert r.weight == 657 and R_OVER_QTY.format(3, 2) in r.reasons


def test_without_circle_has_no_weight():
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circle_status="なし", circled_qty=None, printed_qty=2, mass_kg=657))])[0]
    assert r.weight is None and R_NO_CIRCLE in r.reasons


def test_not_certificate_page():
    r = build_records([PageEntry("x.pdf", 1, PageResult(is_certificate=False, stamp_valid_qty=None, lines=[]))])[0]
    assert r.kind == "not_certificate" and r.reasons == [R_NOT_CERT]


def test_certificate_with_no_lines_yields_review_row():
    r = build_records([PageEntry("x.pdf", 1, PageResult(is_certificate=True, stamp_valid_qty=None, lines=[]))])
    assert len(r) == 1 and r[0].kind == "no_lines" and r[0].reasons == [R_NO_LINES]


def test_unknown_category_is_missing_but_weight_is_kept():
    r = build_records([page_with(line(commodity_raw="一般構造用形鋼", size_raw="65X65X6"))])[0]
    assert r.category is None and r.size == "65×65×6" and R_MISSING.format("材種") in r.reasons
    assert r.weight == 574


def test_to_dict_keys():
    d = rec(reasons=["x"]).to_dict()
    assert list(d) == ["ページ", "ファイル", "ページ番号", "材種", "材質", "寸法",
                       "長さ_mm", "本数", "重量", "要確認", "確認理由"]
    assert d["ページ"] == "—" and d["要確認"] is True and d["確認理由"] == ["x"]
