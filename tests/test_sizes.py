import pytest

from millsheet.sizes import fmt_num, normalize_size, parse_length_mm, parse_numbers, size_key


@pytest.mark.parametrize("cat,raw,expected", [
    ("H形鋼", "200X100X5.5/8", "Ｈ-200×100×5.5×8"),
    ("H形鋼", "200X200X8X12", "Ｈ-200×200×8×12"),
    ("溝形鋼", "5X50X100", "［-100×50×5"),
    ("溝形鋼", "150X75X6.5", "［-150×75×6.5"),
    ("Cチャン", "2.3X100X50X20", "C-100×50×20×2.3"),
    ("アングル", "6X65X65", "L-65×65×6"),
    ("アングル", "L65X65X6", "L-65×65×6"),
    ("コラム", "250X250X12", "□-250×250×12"),
    ("STKR", "12X250X250", "□-250×250×12"),
    ("FB", "25X9", "FB-9×25"),
    ("PL", "19 X 2438 X 12192", "PL-19×2438×12192"),
    ("I形鋼", "200X100X7X10", "200×100×7×10"),
    (None, "100X50", "100×50"),
    ("H形鋼", None, None),
    ("H形鋼", "読めない", None),
])
def test_normalize_size(cat, raw, expected):
    assert normalize_size(cat, raw) == expected


def test_parse_numbers_handles_fullwidth_and_commas():
    assert parse_numbers("２２Ｘ2,438X12192") == [22.0, 2438.0, 12192.0]
    assert parse_numbers(None) == []


def test_fmt_num():
    assert fmt_num(5.0) == "5" and fmt_num(5.5) == "5.5" and fmt_num(2.30) == "2.3"


def test_size_key_treats_4_0_and_4_as_same():
    assert size_key("C-100×50×20×4.0") == size_key("C-100×50×20×4")
    assert size_key("Ｈ-200×200×8×12") == ("H", (200.0, 200.0, 8.0, 12.0))
    assert size_key("［-100×50×5") == ("[", (100.0, 50.0, 5.0))
    assert size_key("□-250×250×12") == ("□", (250.0, 250.0, 12.0))
    assert size_key("200×100") == ("", (200.0, 100.0))
    assert size_key("Ｈ-") is None


@pytest.mark.parametrize("raw,mm", [("11.5M", 11500), ("5.500m", 5500), ("12,000", 12000),
                                    ("5.5", 5500), ("7.000m", 7000), ("10M", 10000), (None, None), ("-", None)])
def test_parse_length_mm(raw, mm):
    assert parse_length_mm(raw) == mm


# 寸法の前後に製品番号・色などが付いている場合（Gemini が品番まで写したとき）
@pytest.mark.parametrize("cat,raw,expected", [
    ("Cチャン", "K5674Dグレー\n2.3X100X50X20", "C-100×50×20×2.3"),
    ("H形鋼", "ロットA12 200X100X5.5/8", "Ｈ-200×100×5.5×8"),
    ("溝形鋼", "No.3 5X50X100", "［-100×50×5"),
    ("アングル", "K12 L65X65X6", "L-65×65×6"),
    ("コラム", "BCR295 250X250X12", "□-250×250×12"),
    ("FB", "9 X 25", "FB-9×25"),
    ("PL", "22 X 2,438 X 12,192", "PL-22×2438×12192"),
    ("アングル", "L65X65X6 / 別表 6X65X65", "L-65×65×6"),       # 同じ長さなら先に出てくる方
    ("Cチャン", "2.3X100X50X20 L=6000", "C-100×50×20×2.3"),     # 後ろの余計な数字も除く
    ("丸鋼", "φ22", "22"),                                       # 並びが無ければ全部の数字
])
def test_normalize_size_ignores_codes_around_the_dimension(cat, raw, expected):
    assert normalize_size(cat, raw) == expected


def test_extract_dimension():
    from millsheet.sizes import extract_dimension
    assert extract_dimension("K5674Dグレー\n2.3X100X50X20") == "2.3X100X50X20"
    assert extract_dimension("２．３Ｘ１００Ｘ５０Ｘ２０") == "2.3X100X50X20"
    assert extract_dimension("200X100X5.5/8 と 10X20") == "200X100X5.5/8"
    assert extract_dimension("φ22") is None and extract_dimension(None) is None
