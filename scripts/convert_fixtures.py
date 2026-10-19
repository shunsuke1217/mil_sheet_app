"""ルートの元データから、テスト用データを作る（一度だけ使う）。"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


if __name__ == "__main__":
    convert_raw()
    shutil.copy(ROOT / "20261014084620.pdf", ROOT / "tests/fixtures/20261014084620.pdf")
