"""品名（標準分類名）の判定（SPEC 6.4）。AI ではなくアプリが機械的に判定する。"""
import re
import unicodedata

from millsheet.sizes import symbol_before_dimension

# 優先度の小さい順。最初に当たったものを品名にする
KEYWORDS: list[tuple[str, list[str]]] = [
    ("デッキ", ["DECK", "DECK PLATE", "デッキプレート", "デッキ"]),
    ("H形鋼", ["H-BEAM", "WIDE FLANGE", "H-SHAPE", "H形鋼", "H鋼"]),
    ("I形鋼", ["I-BEAM", "I-SHAPE", "I形鋼", "I鋼"]),
    ("コラム", ["BCR", "BCP", "COLUMN", "コラム", "建築構造用角形鋼管", "ロールコラム", "プレスコラム"]),
    ("STKR", ["STKR", "STKR400", "STKR490", "一般構造用角形鋼管", "角パイプ", "角鋼管"]),
    ("丸パイプ", ["CIRCULAR TUBE", "STEEL PIPE", "STK", "STKN", "SGP", "STPG", "丸パイプ", "鋼管", "配管"]),
    ("Cチャン", ["LIP GROOVE", "C-CHANNEL", "C-CHANNELS", "C-SHAPE", "SSC", "LIP", "リップ溝形鋼", "C形鋼", "Cチャン", "軽量形鋼"]),
    ("溝形鋼", ["CHANNEL", "CHANNELS", "MC", "溝形鋼", "チャンネル", "角チャンネル"]),
    ("アングル", ["EQUAL ANGLE", "UNEQUAL ANGLE", "ANGLE", "ANGLES", "山形鋼", "アングル", "L形鋼"]),
    ("T形鋼", ["CT", "T-BAR", "T-SHAPE", "T形鋼", "カットT"]),
    ("チェッカープレート", ["CHECKERED", "CHECKER", "チェッカー", "縞鋼板", "縞板"]),
    ("PL", ["MILLEDGED", "CUT EDGED", "HOT ROLLED PLATE", "COLD ROLLED PLATE", "STEEL PLATE", "PL", "PLATE", "SHEET", "SHEETS", "鋼板", "中厚板"]),
    ("FB", ["FLAT BAR", "FB", "平鋼", "フラットバー"]),
    ("D（鉄筋）", ["DEFORMED BAR", "SD295", "SD345", "異形棒鋼", "異形丸鋼", "鉄筋"]),
    ("角鋼", ["SQUARE BAR", "角鋼", "角棒"]),
    ("丸鋼", ["ROUND BAR", "RB", "丸鋼", "丸棒"]),
    ("EXメタ", ["EXPANDED", "エキスパンドメタル"]),
]

CATEGORIES: list[str] = [c for c, _ in KEYWORDS]

_ASCII_KEYWORD = re.compile(r"[A-Z0-9 \-]+")


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).upper()


def _compile(word: str):
    w = _normalize(word)
    if _ASCII_KEYWORD.fullmatch(w):
        # 英字のキーワードは単語として独立しているときだけ当たる（英字以外は区切り）
        pattern = re.compile(rf"(?<![A-Z]){re.escape(w)}(?![A-Z])")
        return pattern.search
    return lambda text: w in text


_MATCHERS = [(c, [_compile(w) for w in words]) for c, words in KEYWORDS]


def classify(commodity_raw: str | None, size_raw: str | None) -> str | None:
    if commodity_raw:
        text = _normalize(commodity_raw)
        for category, matchers in _MATCHERS:
            if any(m(text) for m in matchers):
                return category
    # 寸法による補助ルール: 寸法が L で始まる、または寸法の並びの直前の記号が L（"K12 L65X65X6" など）
    if size_raw and (_normalize(size_raw).strip().startswith("L") or symbol_before_dimension(size_raw) == "L"):
        return "アングル"
    return None
