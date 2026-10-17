"""ルートの元データから、テスト用データと内蔵マスタを作る（一度だけ使う）。"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIX_CATEGORY = [
    ("Ｈ-", "H形鋼"), ("［-", "溝形鋼"), ("C-", "Cチャン"), ("L-", "アングル"),
    ("□-", "コラム/STKR"), ("FB-", "FB"), ("PL-", "PL"),
]


def convert_raw():
    src = json.loads((ROOT / "sample_raw.json").read_text("utf-8"))
    pages = {}
    for file, entries in src.items():
        out = []
        for e in entries:
            result = e.get("result")
            if result is not None:
                has_circle = result.pop("has_circle", True)
                for line in result["lines"]:
                    line.pop("category", None)
                    if line.get("circled_qty") is not None:
                        line["circle_status"] = "あり"
                    else:
                        line["circle_status"] = "なし" if not has_circle else "読めない"
            out.append({"page": e["page"], "result": result, "error": e.get("error")})
        pages[file] = out
    data = {"source_dir": None, "pages": pages}
    (ROOT / "tests/fixtures/sample_raw.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def category_of(size):
    for prefix, cat in PREFIX_CATEGORY:
        if size.startswith(prefix):
            return cat
    raise ValueError(f"記号が分からないサイズ: {size}")


def convert_master():
    src = json.loads((ROOT / "unit_weights.json").read_text("utf-8"))
    data = [{"材種": category_of(e["size"]), "サイズ": e["size"], "単重": e["unit_weight"]} for e in src]
    text = json.dumps(data, ensure_ascii=False, indent=1)
    (ROOT / "millsheet/unit_weights.json").write_text(text, "utf-8")
    (ROOT / "tests/fixtures/unit_weights.json").write_text(text, "utf-8")


if __name__ == "__main__":
    convert_raw()
    convert_master()
    shutil.copy(ROOT / "20261014084620.pdf", ROOT / "tests/fixtures/20261014084620.pdf")
