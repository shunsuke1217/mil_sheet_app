"""寸法の表記（SPEC 8.2）と長さ（SPEC 8.3）の正規化。"""
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

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


def fmt_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else format(Decimal(str(x)).normalize(), "f")


def _reverse_if_needed(nums: list[float]) -> list[float]:
    # 「必要なら逆順」= 先頭の数値が末尾の数値より小さければ逆順にする
    return list(reversed(nums)) if nums and nums[0] < nums[-1] else nums


def normalize_size(category: str | None, size_raw: str | None) -> str | None:
    nums = parse_numbers(size_raw)
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
