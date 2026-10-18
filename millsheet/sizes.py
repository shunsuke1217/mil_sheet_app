"""寸法の表記（SPEC 8.2）と長さ（SPEC 8.3）の正規化。"""
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# 寸法 = 区切り記号（X × * /）でつながった数字の並び（例: 2.3X100X50X20、19 X 2438 X 12192、200X100X5.5/8）
_DIMENSION = re.compile(r"\d+(?:\.\d+)?(?:\s*[X×*/]\s*\d+(?:\.\d+)?)+")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")

# 品名 → (記号, 並べ方)
_RULES = {
    "H形鋼": ("Ｈ-", "h"),
    "溝形鋼": ("［-", "channel"),
    "Cチャン": ("C-", "lip"),
    "アングル": ("L-", "desc"),
    "コラム": ("□-", "desc"),
    "STKR": ("□-", "desc"),
    "丸パイプ": ("φ-", "desc"),
    "FB": ("FB-", "asc"),
    "PL": ("PL-", "as_is"),
}


def parse_numbers(text: str | None) -> list[float]:
    if not text:
        return []
    t = unicodedata.normalize("NFKC", text).replace(",", "")
    return [float(m) for m in _NUMBER.findall(t)]


def _prepare(text: str) -> str:
    return _THOUSANDS.sub("", unicodedata.normalize("NFKC", text)).upper()


def _dimension_match(text: str | None) -> tuple[str, re.Match] | None:
    if not text:
        return None
    t = _prepare(text)
    matches = list(_DIMENSION.finditer(t))
    if not matches:
        return None
    # 製品番号・色などの前後の文字は捨て、数字のいちばん多い並びを寸法とする（同じなら先に出てくる方）
    best = max(matches, key=lambda m: (len(_NUMBER.findall(m.group())), -m.start()))
    return t, best


def extract_dimension(text: str | None) -> str | None:
    """寸法の文字列から、寸法らしい部分（区切りでつながった数字の並び）だけを取り出す。"""
    found = _dimension_match(text)
    return found[1].group() if found else None


def symbol_before_dimension(text: str | None) -> str:
    """寸法の並びの直前にある記号（例: "K12 L65X65X6" → "L"）。単語の末尾の文字は記号とみなさない。"""
    found = _dimension_match(text)
    if not found:
        return ""
    t, m = found
    head = re.search(r"(?<![A-Z])([A-Z]{1,2})[\s\-]*$", t[:m.start()])
    return head.group(1) if head else ""


def dimension_numbers(size_raw: str | None) -> list[float]:
    """寸法の数字。並びが見つからなければ（φ22 など）全部の数字。"""
    dim = extract_dimension(size_raw)
    return parse_numbers(dim if dim is not None else size_raw)


def fmt_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else format(Decimal(str(x)).normalize(), "f")


def _reverse_if_needed(nums: list[float]) -> list[float]:
    # 「必要なら逆順」= 先頭の数値が末尾の数値より小さければ逆順にする
    return list(reversed(nums)) if nums and nums[0] < nums[-1] else nums


def normalize_size(category: str | None, size_raw: str | None) -> str | None:
    nums = dimension_numbers(size_raw)
    if not nums:
        return None
    prefix, rule = _RULES.get(category, ("", "as_is"))
    if rule == "h":
        nums = nums[:4]
    elif rule == "channel":
        nums = _reverse_if_needed(nums)[:3]
    elif rule == "lip":
        i = nums.index(min(nums))
        rest = nums[:i] + nums[i + 1:]
        nums = sorted(rest, reverse=True) + [nums[i]]
    elif rule == "desc":
        nums = _reverse_if_needed(nums)
    elif rule == "asc":
        nums = sorted(nums)
    return prefix + "×".join(fmt_num(n) for n in nums)


def size_key(size: str) -> tuple[str, tuple[float, ...]] | None:
    """マスタとの照合・並べ替えに使う「記号＋数値の組」。"""
    t = unicodedata.normalize("NFKC", size)
    m = re.search(r"\d", t)
    if not m:
        return None
    symbol = re.sub(r"\s", "", t[:m.start()]).rstrip("-")
    return symbol, tuple(parse_numbers(t[m.start():]))


def parse_length_mm(length_raw: str | None) -> int | None:
    nums = parse_numbers(length_raw)
    if not nums:
        return None
    v = Decimal(str(nums[0]))
    if v < 100:
        v *= 1000
    return int(v.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
