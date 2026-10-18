import pytest

from millsheet.classify import CATEGORIES, KEYWORDS, classify


@pytest.mark.parametrize("raw,size,expected", [
    ("H形鋼", "200X200X8X12", "H形鋼"),
    ("MILLEDGED STEEL PLATE", "22X2438X12192", "PL"),
    ("HOT ROLLED STEEL PLATE", "19 X 2438 X 12192", "PL"),
    ("溝形鋼", "150X75X6.5", "溝形鋼"),
    ("CHANNELS", "100X50X5", "溝形鋼"),
    ("軽量形鋼", "2.3X100X50X20", "Cチャン"),
    ("一般構造用形鋼", "L65X65X6", "アングル"),      # 寸法の補助ルール
    ("等アングル", "6X65X65", "アングル"),
    ("DECK PLATE", None, "デッキ"),                  # DECK が PLATE より優先
    ("LIP CHANNEL", None, "Cチャン"),                # LIP があれば Cチャン
    ("ＣＨＡＮＮＥＬ", None, "溝形鋼"),              # 全角
    ("CONTRACT", None, None),                         # CT は単語でないと当たらない
    ("PLATEN", None, None),                           # PLATE も単語単位
    ("H-BEAM / 別表", None, "H形鋼"),
    ("一般構造用形鋼", "65X65X6", None),              # L で始まらなければ未分類
    (None, " l65x65x6", "アングル"),                  # 補助ルールも NFKC・strip・大文字
    ("BCR295", None, "コラム"),                       # 数字は区切り
    ("STK400", None, "丸パイプ"),
    ("STKR400", None, "STKR"),                        # STK は STKR に当たらない（R は英字）
    (None, None, None),
])
def test_classify(raw, size, expected):
    assert classify(raw, size) == expected


def test_categories_are_the_17_in_priority_order():
    assert CATEGORIES == ["デッキ", "H形鋼", "I形鋼", "コラム", "STKR", "丸パイプ", "Cチャン", "溝形鋼", "アングル",
                          "T形鋼", "チェッカープレート", "PL", "FB", "D（鉄筋）", "角鋼", "丸鋼", "EXメタ"]


def test_no_keyword_is_shadowed_by_an_earlier_one():
    """キーワードを足したときに、優先度の高い短いキーワードに飲み込まれて届かなくなる組を防ぐ。"""
    for category, words in KEYWORDS:
        for w in words:
            assert classify(w, None) == category, f"「{w}」が {classify(w, None)} に判定される"


@pytest.mark.parametrize("raw,size,expected", [
    ("一般構造用形鋼", "K12 L65X65X6", "アングル"),       # 寸法の直前の L を見る
    ("一般構造用形鋼", "K12 L 65X65X6", "アングル"),
    ("一般構造用形鋼", "COIL 65X65X6", None),             # 単語の末尾の L は記号ではない
])
def test_angle_rule_looks_at_symbol_before_dimension(raw, size, expected):
    assert classify(raw, size) == expected
