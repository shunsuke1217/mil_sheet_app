from millsheet.normalize import (R_ERROR, R_MISSING, R_NO_CIRCLE, R_NO_LINES, R_NO_MASTER, R_NOT_CERT, R_OVER_QTY,
                                 R_STAMP, R_UNCERTAIN, R_UNREADABLE, build_records)
from millsheet.schema import PageEntry, PageResult
from tests.helpers import line, page_with, rec

EXPECTED = [  # SPEC 18章（ページ番号, 品名, 材質, 寸法, 長さ, 本数, 単重, 重量）
    (1, "H形鋼", "SS400", "Ｈ-200×200×8×12", 11500, 1, 49.9, 574),
    (2, "H形鋼", "SS400", "Ｈ-200×100×5.5×8", 7000, 2, 20.9, 293),
    (3, "PL", "SN490C", "PL-22×2438×12192", None, 1, None, 5287),
    (4, "PL", "SN490C", "PL-19×2438×12192", None, 1, None, 4567),
    (5, "溝形鋼", "SS400", "［-150×75×6.5", 5500, 14, 18.6, 1432),
    (6, "溝形鋼", "SS400", "［-100×50×5", 5500, 1, 9.36, 51),
    (7, "Cチャン", "SSC400", "C-100×50×20×2.3", 12000, 40, 4.06, 1949),
    (8, "Cチャン", "SSC400", "C-100×50×20×2.3", 8000, 16, 4.06, 520),
    (9, "アングル", "SS400", "L-65×65×6", 5500, 1, 5.91, 33),
    (10, "アングル", "SS400", "L-65×65×6", 5500, 5, 5.91, 163),
]


def test_sample_reproduces_acceptance_table(sample_pages, fixture_master):
    recs = [r for r in build_records(sample_pages, fixture_master) if r.file == "20261014084620.pdf"]
    got = [(r.page_no, r.category, r.grade, r.size, r.length_mm, r.qty, r.unit_weight, r.weight) for r in recs]
    assert got == EXPECTED
    assert all(not r.needs_review() for r in recs)


def test_exception_sample_rows_are_kept_and_flagged(sample_pages, fixture_master):
    recs = [r for r in build_records(sample_pages, fixture_master) if r.file == "サンプル_例外.pdf"]
    assert len(recs) == 3                                           # 丸数字なしの 2 行 + API エラーの 1 行
    assert R_NO_CIRCLE in recs[0].reasons and recs[0].qty is None and recs[0].size == "Ｈ-294×200×8×12"
    assert R_MISSING.format("本数、重量") in recs[0].reasons
    assert recs[2].kind == "error" and recs[2].reasons == [R_ERROR.format("APIタイムアウト")]


def test_input_index_runs_across_pages(sample_pages, fixture_master):
    assert [r.input_index for r in build_records(sample_pages, fixture_master)] == list(range(13))


def test_unreadable_circle_reason_differs_from_no_circle(fixture_master):
    recs = build_records([page_with(line(circle_status="読めない", circled_qty=None, uncertain=True))], fixture_master)
    assert R_UNREADABLE in recs[0].reasons and R_NO_CIRCLE not in recs[0].reasons
    assert R_UNCERTAIN.format("") in recs[0].reasons


def test_uncertain_note_is_shown(fixture_master):
    r = build_records([page_with(line(uncertain=True, note="長さがかすれている"))], fixture_master)[0]
    assert R_UNCERTAIN.format("（長さがかすれている）") in r.reasons


def test_unregistered_size(fixture_master):
    r = build_records([page_with(line(commodity_raw="I形鋼", size_raw="200X100X7X10"))], fixture_master)[0]
    assert R_NO_MASTER in r.reasons and r.unit_weight is None and r.weight is None
    assert not any(x.startswith("必須項目") for x in r.reasons)


def test_over_qty_and_stamp_mismatch(fixture_master):
    recs = build_records([page_with(line(circled_qty=20, printed_qty=18), stamp_valid_qty=3)], fixture_master)
    assert R_OVER_QTY.format(20, 18) in recs[0].reasons and R_STAMP.format(3, 20) in recs[0].reasons


def test_stamp_mismatch_applies_to_every_line_on_page(fixture_master):
    recs = build_records([page_with(line(circled_qty=1), line(circle_status="なし", circled_qty=None),
                                    stamp_valid_qty=2)], fixture_master)
    assert all(R_STAMP.format(2, 1) in r.reasons for r in recs)


def test_stamp_skipped_when_missing_or_no_circles(fixture_master):
    assert not any(x.startswith("押印") for x in
                   build_records([page_with(line(circled_qty=5))], fixture_master)[0].reasons)
    assert not any(x.startswith("押印") for x in build_records(
        [page_with(line(circle_status="なし", circled_qty=None), stamp_valid_qty=3)], fixture_master)[0].reasons)


def test_mass_difference_detected(fixture_master):   # 長さを読み違えた想定: 11.5M のところ 5.5M
    r = build_records([page_with(line(length_raw="5.5M", circled_qty=1, printed_qty=18, mass_kg=10332))],
                      fixture_master)[0]
    assert any(x.startswith("計算した重量") for x in r.reasons)


def test_pl_weight_prorated_and_half_up(fixture_master):
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circled_qty=1, printed_qty=2, mass_kg=657))], fixture_master)[0]
    assert r.weight == 329 and r.length_mm is None and r.unit_weight is None   # 328.5 → 329（ROUND_HALF_UP）
    assert r.reasons == []


def test_pl_over_qty_uses_full_mass(fixture_master):
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circled_qty=3, printed_qty=2, mass_kg=657))], fixture_master)[0]
    assert r.weight == 657 and R_OVER_QTY.format(3, 2) in r.reasons


def test_pl_without_circle_has_no_weight(fixture_master):
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circle_status="なし", circled_qty=None, printed_qty=2, mass_kg=657))],
                      fixture_master)[0]
    assert r.weight is None and R_NO_CIRCLE in r.reasons


def test_not_certificate_page(fixture_master):
    r = build_records([PageEntry("x.pdf", 1, PageResult(is_certificate=False, stamp_valid_qty=None, lines=[]))],
                      fixture_master)[0]
    assert r.kind == "not_certificate" and r.reasons == [R_NOT_CERT]


def test_certificate_with_no_lines_yields_review_row(fixture_master):
    r = build_records([PageEntry("x.pdf", 1, PageResult(is_certificate=True, stamp_valid_qty=None, lines=[]))],
                      fixture_master)
    assert len(r) == 1 and r[0].kind == "no_lines" and r[0].reasons == [R_NO_LINES]


def test_unknown_category_is_missing(fixture_master):
    r = build_records([page_with(line(commodity_raw="一般構造用形鋼", size_raw="65X65X6"))], fixture_master)[0]
    assert r.category is None and r.size == "65×65×6" and R_MISSING.format("材種、ミルシート重量、重量") in r.reasons


def test_to_dict_keys():
    d = rec(reasons=["x"]).to_dict()
    assert list(d) == ["ページ", "ファイル", "ページ番号", "材種", "材質", "寸法",
                       "長さ_mm", "本数", "ミルシート重量", "重量", "要確認", "確認理由"]
    assert d["ページ"] == "—" and d["要確認"] is True and d["確認理由"] == ["x"]
