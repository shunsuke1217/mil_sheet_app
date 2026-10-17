"""実 API を使うテスト（GEMINI_API_KEY があるときだけ動く）。SPEC 18章。"""
import os

import pytest

from millsheet.extract import GeminiReader, render_png
from millsheet.normalize import build_records
from millsheet.schema import PageEntry
from tests.test_normalize import EXPECTED

pytestmark = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY がありません")

FIELDS = ["ページ", "品名", "材質", "寸法", "長さ", "本数", "単重", "重量"]


def test_sample_pdf_matches_acceptance_table(sample_pdf, fixture_master):
    reader = GeminiReader(os.environ["GEMINI_API_KEY"])
    pages = [PageEntry(sample_pdf.name, n, reader.read(render_png(sample_pdf, n))) for n in range(1, 11)]
    recs = build_records(pages, fixture_master)
    got = [(r.page_no, r.category, r.grade, r.size, r.length_mm, r.qty, r.unit_weight, r.weight) for r in recs]
    total = matched = 0
    for g, e in zip(got, EXPECTED):
        for name, gv, ev in zip(FIELDS, g, e):
            total += 1
            matched += gv == ev
            if gv != ev:
                print(f"  {e[0]} ページ目 {name}: 期待 {ev} / 読み取り {gv}")
    print(f"一致率: {matched}/{total}（{matched / total:.0%}）")
    assert got == EXPECTED
