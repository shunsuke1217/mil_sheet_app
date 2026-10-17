# ミルシート読み取りアプリ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スキャンしたミルシート PDF のフォルダを Gemini で読み取り、品名順・サイズ順に並べた xlsx と、同じ順に並べ替えて 1 つにまとめた PDF を出力する、Windows / Mac 両対応のデスクトップアプリを作る。

**Architecture:** 読み取り（Gemini）→ 生の結果（`_raw.json`）→ 正規化・計算・チェック → 並べ替え → 出力（xlsx / JSON / PDF）の一方向のパイプライン。
API を使うのは読み取りだけで、それ以降は `_raw.json` とスプレッドシートの単重マスタだけから何度でも作り直せる。
画面（PySide6）は `pipeline.py` の 2 つの関数（`run` / `rebuild`）を別スレッドで呼ぶだけにし、ロジックを持たない。

**Tech Stack:** Python 3.12 / PySide6 / PyMuPDF / google-genai（Interactions API）/ pydantic v2 / openpyxl / httpx / platformdirs / keyring / pytest / PyInstaller / GitHub Actions

**Spec:** [SPEC.md](../../../SPEC.md)（章番号はすべて SPEC.md のもの）

## Global Constraints

- Python は **3.12**（uv で用意する。`uv venv --python 3.12`）。依存は `requirements.txt` に書き、開発用（pytest など）は `requirements-dev.txt`
- Gemini のモデルは定数 `MODEL = "gemini-3.8-flash"`（6.3）。設定画面からは変えない
- 「AI には紙に書いてあることを読むことだけをさせる」。品名の判定・表記の統一・換算・計算・チェックはすべてアプリ側（2章、6.4）
- 単重は**スプレッドシートの単重マスタ（取得できないときはそのキャッシュ）からだけ**引く。内蔵の初期マスタは計算に使わない（7.3、8.4）
- API キー（Gemini・Google）は keyring にだけ保存する。settings.json・ログ・エラーメッセージ・exe・ソースに入れない（6.3、7.3）。keyring のサービス名は `ミルシート読み取り`
- データ用フォルダは `platformdirs.user_data_dir("ミルシート読み取り", appauthor=False, roaming=True)`（10章）
- 寸法の区切りは全角 `×`、整数は小数点なし（8.2）。ページ欄は全角 `Ｐ-{n}`（8.1）
- 重量の四捨五入は **0.5 を切り上げる**（`Decimal` + `ROUND_HALF_UP`。Python の `round` は使わない）。例: `5.5 × 5 × 5.91 = 162.525 → 163`
- 出力ファイル名: 出力先に `X.xlsx` を指定したら、`X.json`・`X_raw.json`・`X.pdf` を同じフォルダに作る（12章）
- テストは `pytest`。実 API のテストは環境変数 `GEMINI_API_KEY` があるときだけ動く（`tests/test_extract_live.py`）

## Review Focus

1. **サブフォルダに同じ名前の PDF がある**（`A/001.pdf` と `B/001.pdf`）→ 別のファイルとして扱い、ページやキャッシュが混ざらない。ファイルの識別は常に「読み込んだフォルダからの相対パス（`/` 区切り）」で行う → Task 8 `test_list_pdfs_same_name_in_subfolders`
2. **証明書なのに AI が `lines` を空で返した** → 行が消えず、全項目 null の 1 行を `要確認`（理由「行が読み取れませんでした」）で出す → Task 5 `test_certificate_with_no_lines_yields_review_row`
3. **スプレッドシートの単重やサイズに全角・カンマ・前後の空白がある**（`４９．９`、`1,234`、`Ｈ-200×200×8×12 `）→ NFKC と空白除去のあと数値として読める。見出しの前後の空白も無視する → Task 4 `test_parse_sheet_values_tolerates_fullwidth_and_spaces`
4. **壊れた・暗号化された PDF が混ざっている** → そのファイルだけ読み取り失敗の 1 行（ページ番号なし、ページ欄 `—`）にし、他のファイルは処理を続ける。まとめた PDF には入れない → Task 6 `test_unreadable_pdf_row_gets_no_page_number`、Task 8 `test_open_failure_yields_error_entry`
5. **出力先の xlsx を Excel で開いたまま実行する**（Windows では上書きできない）→ 読み取り結果（`_raw.json`）は保存したうえで、「xlsx が他のアプリで開かれています。閉じてから『作り直す』を押してください」と表示し、課金をやり直させない → Task 9 `test_run_reports_locked_output_and_keeps_raw`

---

## ファイル構成

```
mil_card_app/
├─ SPEC.md
├─ requirements.txt / requirements-dev.txt / pytest.ini / .gitignore
├─ main.py                       # 画面の起動
├─ .github/workflows/build.yml
├─ millsheet/
│  ├─ __init__.py
│  ├─ schema.py                  # Line / PageResult（6.1）、PageEntry
│  ├─ paths.py                   # データ用フォルダ（10章）
│  ├─ settings.py                # settings.json と keyring
│  ├─ applog.py                  # ログの設定（API キーを伏せる）
│  ├─ classify.py                # 品名の判定（6.4）
│  ├─ sizes.py                   # 寸法・長さの正規化（8.2、8.3）
│  ├─ master.py                  # 単重マスタの取得・検証・キャッシュ・CSV 書き出し（7章）
│  ├─ normalize.py               # Record の作成・計算・チェック（8.4、8.5、9章）
│  ├─ ordering.py                # 並べ替えとページ番号（8.6）
│  ├─ merge_pdf.py               # 並べ替えた PDF（12.4）
│  ├─ rawfile.py                 # _raw.json の読み書き（12.3）
│  ├─ prompt.py                  # Gemini へのプロンプト（6.2）
│  ├─ extract.py                 # PDF の一覧・画像化・Gemini 呼び出し（5章、6章）
│  ├─ cache.py                   # ページ単位の読み取りキャッシュ
│  ├─ pipeline.py                # run / rebuild（画面から呼ぶ入口）
│  ├─ export/
│  │  ├─ __init__.py
│  │  ├─ base.py                 # Exporter Protocol（12.5）
│  │  ├─ local_xlsx.py           # LocalXlsxExporter（12.2）
│  │  └─ json_out.py             # X.json（12.1）
│  └─ unit_weights.json          # 内蔵の初期マスタ（{品名, サイズ, 単重}）
├─ gui/
│  ├─ __init__.py
│  ├─ main_window.py
│  ├─ worker.py                  # QThread
│  ├─ settings_dialog.py
│  └─ master_dialog.py
├─ scripts/
│  └─ convert_fixtures.py        # 一度だけ使う変換スクリプト
└─ tests/
   ├─ fixtures/
   │  ├─ 20261014084620.pdf
   │  ├─ sample_raw.json         # 6.1 の形・12.3 の形に変換済み
   │  └─ unit_weights.json       # スプレッドシートの代わりの単重マスタ
   ├─ conftest.py               # フィクスチャ（下の「テストの共通部品」）
   ├─ helpers.py                # rec() / line() / page_with() / make_pdf() / FakeReader
   ├─ test_classify.py / test_sizes.py / test_master.py / test_normalize.py
   ├─ test_ordering.py / test_merge_pdf.py / test_export.py / test_extract.py
   ├─ test_pipeline.py / test_gui_smoke.py
   └─ test_extract_live.py
```

ルートにある `20261014084620.pdf`・`ミルシート他表紙類2025.xlsx`・`sample_raw.json`・`unit_weights.json` は元データとして残し、`.gitignore` に入れる（社外秘。17章）。

## 共通の型（各タスクが使う名前）

```python
# millsheet/schema.py
class Line(BaseModel): ...          # SPEC 6.1 のとおり（フィールド名・型をそのまま）
class PageResult(BaseModel): ...    # SPEC 6.1 のとおり

@dataclass
class PageEntry:
    file: str                 # 読み込んだフォルダからの相対パス（"/" 区切り）。例 "20261014084620.pdf"
    page_no: int | None       # 1 始まり。PDF 自体が開けなかったときは None
    result: PageResult | None # 失敗したときは None
    error: str | None = None  # 失敗の理由（画面と確認理由に出す日本語）

# millsheet/normalize.py
@dataclass
class Record:
    file: str
    page_no: int | None
    category: str | None      # 品名
    grade: str | None         # 材質
    size: str | None          # 寸法（8.2 の書き方。マスタに一致したらマスタの文字列）
    length_mm: int | None
    qty: int | None           # 本数（= 丸数字）
    unit_weight: float | None # ミルシート重量
    weight: int | None        # 重量
    reasons: list[str]        # 確認理由（空なら要確認=false）
    input_index: int          # 入力順（0 始まり。並べ替えの最後のキー）
    kind: Literal["line", "not_certificate", "error"] = "line"
    page_label: str | None = None  # "Ｐ-3"。ordering が入れる。ページ番号が無ければ None
    def needs_review(self) -> bool: ...   # bool(reasons)
    def to_dict(self) -> dict: ...        # SPEC 12.1 のキーと順。ページ欄は page_label or "—"
```

## テストの共通部品

`tests/conftest.py` のフィクスチャは、使い始めるタスクで足していく:
`data_dir`（`MILLSHEET_DATA_DIR` を tmp に向け、そのパスを返す。Task 1）、`sample_pdf`（`tests/fixtures/20261014084620.pdf`。無ければ skip。Task 1）、
`sample_pages`（`read_raw("tests/fixtures/sample_raw.json")` の pages。Task 5。`rawfile` は Task 7 なので、Task 5 では conftest 内で同じ形を直接読む小さな関数を使い、Task 7 で `read_raw` に置き換える）、
`fixture_master`（`load_master_file("tests/fixtures/unit_weights.json")`。Task 5）、`sample_records`（Task 6）、`ordered_sample_dicts`（Task 7）、
`sample_folder` / `fake_reader` / `fixture_master_loader`（Task 9）。
`tests/helpers.py` の `rec()`・`line()`・`page_with()`・`make_pdf(path, n)`（各ページに `"{ファイル名の stem}-{n}"` を書いた PDF）・`FakeReader`（`calls` を数え、決まった `PageResult` を返す）は、最初に使うタスクで作る。

---

### Task 1: 土台（環境・設定・データ用フォルダ・テスト用データ）

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.gitignore`, `millsheet/__init__.py`, `millsheet/schema.py`, `millsheet/paths.py`, `millsheet/settings.py`, `millsheet/applog.py`, `scripts/convert_fixtures.py`, `millsheet/unit_weights.json`, `tests/fixtures/*`, `tests/conftest.py`
- Test: `tests/test_foundation.py`

**Interfaces:**
- Produces:
  - `schema.Line`, `schema.PageResult`, `schema.PageEntry`（上の「共通の型」）
  - `paths.data_dir() -> Path`（無ければ作る）、`paths.cache_dir()`、`paths.logs_dir()`、`paths.master_cache_path() -> Path`（`unit_weights_cache.json`）、`paths.bundled_master_path() -> Path`（PyInstaller 実行時は `sys._MEIPASS/millsheet/unit_weights.json`）。テストでは環境変数 `MILLSHEET_DATA_DIR` で差し替えられる
  - `settings.Settings`（dataclass: `sheet_url: str = ""`, `sheet_name: str = ""`, `output_path: str = ""`, `exporter: str = "local_xlsx"`）、`settings.load_settings() -> Settings`、`settings.save_settings(s: Settings) -> None`
  - `settings.get_secret(name: Literal["gemini_api_key", "google_api_key"]) -> str | None`、`settings.set_secret(name, value: str) -> None`
  - `applog.setup_logging() -> None`（`logs/app.log`、5MB × 5 世代）、`applog.mask(text: str, secrets: list[str]) -> str`

- [ ] **Step 1: 環境を作る**

```bash
git init
uv venv --python 3.12 .venv
```
`requirements.txt`: `PySide6`, `pymupdf`, `google-genai`, `pydantic>=2`, `openpyxl`, `httpx`, `platformdirs`, `keyring`（バージョンはインストールした時点のものを `==` で固定）。`requirements-dev.txt`: `-r requirements.txt`, `pytest`, `pytest-qt`。
`uv pip install -r requirements-dev.txt` が通ること。
`.gitignore`: `.venv/`, `__pycache__/`, `dist/`, `build/`, `*.spec`, `/20261014084620.pdf`, `/ミルシート他表紙類2025.xlsx`, `/sample_raw.json`, `/unit_weights.json`, `*.key.json`, `.env`。
`tests/fixtures/20261014084620.pdf` も社外秘なので `.gitignore` に入れ、PDF を使うテストはファイルが無ければ `pytest.skip` する（`conftest.py` に `sample_pdf` フィクスチャを置く）。

- [ ] **Step 2: テスト用データを変換するスクリプトを書いて実行する**

`scripts/convert_fixtures.py`（引数なし。ルートの元データを読み、次の 3 つを書く）:
- `tests/fixtures/sample_raw.json`: 12.3 の形 `{"source_dir": null, "pages": {<相対パス>: [{"page": n, "result": PageResult|null, "error": str|null}]}}`。
  各 line から `category` を除き、`circle_status` を入れる（`circled_qty` が数値 → `"あり"`、ページの `has_circle` が false → `"なし"`）。ページの `has_circle` も除く
- `millsheet/unit_weights.json` と `tests/fixtures/unit_weights.json`: `[{"品名", "サイズ", "単重"}]`。品名はサイズの記号から付ける（`Ｈ-`→H形鋼、`［-`→溝形鋼、`C-`→Cチャン、`L-`→アングル、`□-`→コラム/STKR、`FB-`→FB、`PL-`→PL。7.1）
- `tests/fixtures/20261014084620.pdf` にルートの PDF をコピー

- [ ] **Step 3: 失敗するテストを書く** — `tests/test_foundation.py`

```python
def test_fixture_raw_matches_schema():
    raw = json.loads(Path("tests/fixtures/sample_raw.json").read_text("utf-8"))
    pages = raw["pages"]["20261014084620.pdf"]
    assert len(pages) == 10
    for p in pages:
        PageResult.model_validate(p["result"])
    assert raw["pages"]["サンプル_例外.pdf"][0]["result"]["lines"][0]["circle_status"] == "なし"
    assert raw["pages"]["サンプル_例外.pdf"][1]["error"] == "APIタイムアウト"

def test_bundled_master_has_225_entries_with_category():
    data = json.loads(Path("millsheet/unit_weights.json").read_text("utf-8"))
    assert len(data) == 225
    assert {"品名", "サイズ", "単重"} == set(data[0])
    assert {d["品名"] for d in data} == {"H形鋼", "溝形鋼", "Cチャン", "アングル", "コラム/STKR", "FB", "PL"}

def test_data_dir_created_and_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("MILLSHEET_DATA_DIR", str(tmp_path / "d"))
    assert paths.data_dir().is_dir()

def test_settings_roundtrip_has_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("MILLSHEET_DATA_DIR", str(tmp_path))
    save_settings(Settings(sheet_url="https://docs.google.com/spreadsheets/d/abc/edit"))
    assert load_settings().sheet_url.endswith("/abc/edit")
    assert "key" not in (tmp_path / "settings.json").read_text("utf-8").lower()

def test_mask_hides_secrets():
    assert mask("url?key=AIzaXYZ", ["AIzaXYZ"]) == "url?key=***"
```

- [ ] **Step 4: 実行して失敗を確かめる** — `pytest tests/test_foundation.py -v` → ImportError で FAIL
- [ ] **Step 5: `schema.py`・`paths.py`・`settings.py`・`applog.py` を実装する**
  `Line` / `PageResult` は 6.1 のコードをそのまま（コメント含む）。settings.json が壊れていたら既定値で起動し、ログに警告を書く
- [ ] **Step 6: 実行して通ることを確かめる** — `pytest tests/test_foundation.py -v` → PASS
- [ ] **Step 7: コミット** — `git add -A && git commit -m "chore: 土台（環境・設定・データ用フォルダ・テスト用データ）"`

---

### Task 2: 品名の判定（6.4）

**Files:**
- Create: `millsheet/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Produces:
  - `classify.CATEGORIES: list[str]` — 6.4 の表の 17 種類（優先度順）
  - `classify.classify(commodity_raw: str | None, size_raw: str | None) -> str | None`

照合のしかた（6.4 のとおり）: NFKC → 大文字 → 英字キーワードは「前後が英数字でない」ときだけ一致（正規表現 `(?<![A-Z0-9])KEYWORD(?![A-Z0-9])`。キーワード中のハイフン・空白はそのまま比べる）、日本語キーワードは部分一致。優先度の小さい順に調べ、最初に当たったもの。当たらなければ `size_raw` を NFKC・strip・大文字にして先頭が `L` ならアングル、それ以外は None。キーワード表は 6.4 の表をそのまま定数にする。

- [ ] **Step 1: 失敗するテストを書く**

```python
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
    (None, None, None),
])
def test_classify(raw, size, expected):
    assert classify(raw, size) == expected
```

- [ ] **Step 2: 実行して失敗を確かめる** — `pytest tests/test_classify.py -v` → FAIL
- [ ] **Step 3: `classify()` を実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — PASS
- [ ] **Step 5: コミット** — `git commit -m "feat: 品名の判定ルール"`

---

### Task 3: 寸法・長さの正規化（8.2、8.3）

**Files:**
- Create: `millsheet/sizes.py`
- Test: `tests/test_sizes.py`

**Interfaces:**
- Produces:
  - `sizes.parse_numbers(text: str | None) -> list[float]` — NFKC 後、`\d+(?:\.\d+)?` をすべて取り出す（カンマは先に除く）
  - `sizes.fmt_num(x: float) -> str` — `5.0 → "5"`、`5.5 → "5.5"`
  - `sizes.normalize_size(category: str | None, size_raw: str | None) -> str | None` — 8.2 の表。数値が取れなければ None
  - `sizes.size_key(size: str) -> tuple[str, tuple[float, ...]] | None` — マスタ照合用。記号部分（最初の数字より前）を NFKC・空白除去・末尾の `-` 除去したものと数値の組。`"Ｈ-200×200×8×12"` → `("H", (200, 200, 8, 12))`、`"［-100×50×5"` → `("[", (100, 50, 5))`
  - `sizes.parse_length_mm(length_raw: str | None) -> int | None` — 8.3（100 未満は ×1000、結果は四捨五入した int）

8.2 の並べ方（記号と規則）は SPEC の表どおり。H形鋼は「印字順のまま 4 つ」、溝形鋼は「必要なら逆順にし先頭 3 つ」、Cチャンは「最小値を最後、残りは大きい順」、アングル・コラム・STKR・丸パイプは「必要なら逆順」、FB は小さい順、PL は印字順。表に無い品名と None は記号なしで印字順に `×` でつなぐ。

- [ ] **Step 1: 失敗するテストを書く**

```python
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

def test_size_key_treats_4_0_and_4_as_same():
    assert size_key("C-100×50×20×4.0") == size_key("C-100×50×20×4")
    assert size_key("Ｈ-200×200×8×12") == ("H", (200.0, 200.0, 8.0, 12.0))

@pytest.mark.parametrize("raw,mm", [("11.5M", 11500), ("5.500m", 5500), ("12,000", 12000),
                                    ("5.5", 5500), ("7.000m", 7000), ("10M", 10000), (None, None), ("-", None)])
def test_parse_length_mm(raw, mm):
    assert parse_length_mm(raw) == mm
```

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — PASS
- [ ] **Step 5: コミット** — `git commit -m "feat: 寸法と長さの正規化"`

---

### Task 4: 単重マスタ（7章）

**Files:**
- Create: `millsheet/master.py`
- Test: `tests/test_master.py`

**Interfaces:**
- Consumes: `sizes.size_key`、`paths.master_cache_path`、`paths.bundled_master_path`
- Produces:
  - `master.MasterEntry`（dataclass: `category: str`, `size: str`, `unit_weight: float`）
  - `master.Master`（dataclass: `entries: list[MasterEntry]`, `source: Literal["sheet", "cache", "file"]`, `fetched_at: datetime`）。メソッド `lookup(size: str) -> MasterEntry | None`（`size_key` で照合）、`meta() -> dict`（`{"取得元", "件数", "取得日時"}`。出力 JSON に入れる）
  - `master.MasterValidationError(Exception)`（`errors: list[str]`。例 `"5 行目: 単重が 0 より大きい数値ではありません"`）
  - `master.MasterFetchError(Exception)`（`str(e)` が画面に出す日本語）
  - `master.spreadsheet_id_from_url(url: str) -> str`（`/spreadsheets/d/{ID}/` を取り出す。URL でなく ID そのものが入っていてもよい。取れなければ `MasterFetchError("スプレッドシートの URL が正しくありません")`）
  - `master.parse_sheet_values(values: list[list[str]]) -> list[MasterEntry]` — 1 行目を見出しとして `品名`/`サイズ`/`単重` の列を探す。空行は無視。検証は 7.3（見出し・単重 > 0・サイズの重複（`size_key` で比べる））。問題があれば全件まとめて `MasterValidationError`
  - `master.fetch_master(url: str, sheet_name: str, api_key: str, *, client: httpx.Client | None = None) -> tuple[Master, list[str]]` — 戻り値の 2 つ目は警告。取得・検証に成功したらキャッシュに保存して `source="sheet"`。通信・HTTP の失敗ならキャッシュを読んで `source="cache"` と警告 `"スプレッドシートを読めなかったため、前回取得した単重（{取得日時}）を使います: {原因}"`。キャッシュも無ければ `MasterFetchError`。**検証エラー（`MasterValidationError`）のときはキャッシュに逃げずにそのまま投げる**（シートの誤りを隠さないため）
  - `master.load_master_file(path: Path) -> Master`（`[{"品名","サイズ","単重"}]` の JSON を読む。`source="file"`。テストと pipeline のテスト用）
  - `master.export_bundled_csv(path: Path) -> None`（内蔵マスタを UTF-8 BOM 付き CSV、見出し `品名,サイズ,単重`）

取得は `GET https://sheets.googleapis.com/v4/spreadsheets/{ID}/values/{range}?key={key}`。`range` は `sheet_name` があれば `'{sheet_name}'!A:Z`（URL エンコード）、無ければ `A:Z`。タイムアウト 15 秒。
エラーの文言（`MasterFetchError` とキャッシュ時の警告の「原因」）:
- 通信できない → `"ネットに接続できません"`
- 400 で本文に `API key not valid` → `"Google の API キーが正しくありません"`
- 400 で `Unable to parse range` → `"シート名「{sheet_name}」が見つかりません"`
- 403 → `"読み取りが許可されていません。共有設定が「リンクを知っている全員が閲覧可」か、API キーで Google Sheets API が使えるかを確認してください"`
- 404 → `"スプレッドシートが見つかりません。URL を確認してください"`
- 文言にも、ログに出す URL にも API キーを入れない（`applog.mask`）

- [ ] **Step 1: 失敗するテストを書く**（HTTP は `httpx.MockTransport` で差し替える）

```python
def test_spreadsheet_id_from_url():
    assert spreadsheet_id_from_url("https://docs.google.com/spreadsheets/d/1AbC-_x/edit#gid=0") == "1AbC-_x"
    assert spreadsheet_id_from_url("1AbC-_x") == "1AbC-_x"

def test_parse_sheet_values_ok():
    es = parse_sheet_values([["品名", "サイズ", "単重"], ["H形鋼", "Ｈ-200×200×8×12", "49.9"], [], ["FB", "FB-9×25", "1.77"]])
    assert [e.unit_weight for e in es] == [49.9, 1.77]

def test_parse_sheet_values_tolerates_fullwidth_and_spaces():
    es = parse_sheet_values([[" サイズ ", "単重", "品名"], ["Ｈ-200×200×8×12 ", "４９．９", "H形鋼"], ["PL-50", "1,234", "PL"]])
    assert es[0].size == "Ｈ-200×200×8×12" and es[0].unit_weight == 49.9 and es[1].unit_weight == 1234

def test_parse_sheet_values_reports_all_errors_with_row_numbers():
    with pytest.raises(MasterValidationError) as e:
        parse_sheet_values([["品名", "サイズ", "単重"], ["H形鋼", "Ｈ-1×1×1×1", "0"], ["H形鋼", "Ｈ-2×2×2×2", "x"],
                            ["C", "C-100×50×20×4.0", "1"], ["C", "C-100×50×20×4", "2"]])
    msg = "\n".join(e.value.errors)
    assert "2 行目" in msg and "3 行目" in msg and "重複" in msg

def test_parse_sheet_values_missing_header():
    with pytest.raises(MasterValidationError):
        parse_sheet_values([["サイズ", "単重"], ["Ｈ-1×1×1×1", "1"]])

def test_fetch_master_success_writes_cache(data_dir):        # data_dir: MILLSHEET_DATA_DIR を tmp に向ける conftest のフィクスチャ
    m, warnings = fetch_master(URL, "", "KEY", client=client_returning(200, {"values": VALUES}))
    assert m.source == "sheet" and warnings == [] and master_cache_path().exists()

def test_fetch_master_falls_back_to_cache(data_dir):
    fetch_master(URL, "", "KEY", client=client_returning(200, {"values": VALUES}))
    m, warnings = fetch_master(URL, "", "KEY", client=client_raising(httpx.ConnectError("x")))
    assert m.source == "cache" and "前回取得した単重" in warnings[0]

def test_fetch_master_no_cache_403_message(data_dir):
    with pytest.raises(MasterFetchError, match="共有設定"):
        fetch_master(URL, "", "KEY", client=client_returning(403, {}))

def test_fetch_master_validation_error_does_not_use_cache(data_dir):
    fetch_master(URL, "", "KEY", client=client_returning(200, {"values": VALUES}))
    with pytest.raises(MasterValidationError):
        fetch_master(URL, "", "KEY", client=client_returning(200, {"values": [["品名", "サイズ", "単重"], ["H", "Ｈ-1×1×1×1", "0"]]}))

def test_error_messages_never_contain_key(data_dir):
    with pytest.raises(MasterFetchError) as e:
        fetch_master(URL, "", "AIzaSECRET", client=client_returning(400, {"error": {"message": "API key not valid"}}))
    assert "AIzaSECRET" not in str(e.value)

def test_lookup_returns_master_string():
    m = load_master_file(Path("tests/fixtures/unit_weights.json"))
    assert m.lookup("Ｈ-200×200×8×12").unit_weight == 49.9
    assert m.lookup("［-100×50×5").unit_weight == 9.36
    assert m.lookup("φ-1×1") is None

def test_export_bundled_csv_has_bom(tmp_path):
    export_bundled_csv(tmp_path / "m.csv")
    b = (tmp_path / "m.csv").read_bytes()
    assert b.startswith(b"\xef\xbb\xbf") and len(b.decode("utf-8-sig").splitlines()) == 226
```

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 実装する**（キャッシュの形は `{"fetched_at": ISO8601, "entries": [{"品名","サイズ","単重"}]}`、一時ファイルに書いてから `os.replace`）
- [ ] **Step 4: 実行して通ることを確かめる** — PASS
- [ ] **Step 5: コミット** — `git commit -m "feat: スプレッドシートの単重マスタ"`

---

### Task 5: レコードの作成・計算・チェック（8.4、8.5、9章）

**Files:**
- Create: `millsheet/normalize.py`
- Test: `tests/test_normalize.py`

**Interfaces:**
- Consumes: `classify.classify`、`sizes.*`、`master.Master`、`schema.PageEntry`
- Produces: `normalize.Record`（「共通の型」）、`normalize.build_records(pages: list[PageEntry], master: Master) -> list[Record]`、確認理由の定数（下）

各ページの扱い:
- `result is None`（API エラー・PDF が開けない）→ `kind="error"` の 1 行。ページ以外は全部 None、理由は `R_ERROR.format(error)`
- `is_certificate=false` → `kind="not_certificate"` の 1 行、理由 `R_NOT_CERT`
- 証明書で `lines` が空 → 全項目 None の 1 行、理由 `R_NO_LINES`
- それ以外 → `lines` の 1 行ごとに 1 レコード。`input_index` は全ページを通した連番（ページの順は `pages` の並び。呼ぶ側がファイル名順・ページ順にして渡す）

1 行の計算: 品名 `classify(commodity_raw, size_raw)` → 寸法 `normalize_size` → マスタに一致したらマスタのサイズ文字列に置き換え → 長さ（PL は None）→ 本数は `circled_qty` → 単重（PL は None、PL 以外は `master.lookup`）→ 重量（8.5。`Decimal(str(x))` で計算して `ROUND_HALF_UP`）。PL の重量は `mass_kg`、本数と印字本数がどちらもあって違うときは `mass_kg / printed_qty × 本数`。

確認理由（9章の番号順に、当てはまるものをすべて。文言は固定）:

```python
R_NO_CIRCLE   = "丸数字が書かれていません"
R_UNREADABLE  = "丸数字が読めません"
R_MISSING     = "必須項目が空です（{}）"            # 空の項目名を「、」でつなぐ。項目名は 品名/材質/寸法/本数/重量/長さ/ミルシート重量
R_NO_MASTER   = "単重がマスタに未登録です"          # 品名が判定でき、PL 以外で、寸法があり、マスタに無いとき
R_UNCERTAIN   = "AI が読み取りに自信がないと返しました{}"   # note があれば "（{note}）"
R_OVER_QTY    = "丸数字の本数（{}）が印字された本数（{}）を超えています"
R_STAMP       = "押印の本数（{}）と丸数字の合計（{}）が一致しません"   # そのページの全行に付ける
R_MASS_DIFF   = "計算した重量（{}kg）が証明書の質量からの按分（{}kg）と5%以上ずれています"
R_NOT_CERT    = "証明書ではないページです"
R_ERROR       = "読み取りに失敗しました（{}）"
R_NO_LINES    = "行が読み取れませんでした"
```
- 必須項目のチェック（2）は `kind="line"` の行だけ。単重未登録（3）のときは「ミルシート重量」「重量」の空は R_MISSING に含めない（理由の重複を避ける）
- 押印（6）は `circle_status="あり"` の行が 1 つ以上あり、`stamp_valid_qty` があるページだけで比べる
- 質量のずれ（7）は PL 以外で、重量・`mass_kg`・`printed_qty` が揃っているときだけ。`abs(重量 - 按分) / 按分 >= 0.05`

- [ ] **Step 1: 失敗するテストを書く**

```python
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

def test_sample_reproduces_acceptance_table(sample_pages, fixture_master):   # conftest: sample_raw.json → list[PageEntry]
    recs = [r for r in build_records(sample_pages, fixture_master) if r.file == "20261014084620.pdf"]
    got = [(r.page_no, r.category, r.grade, r.size, r.length_mm, r.qty, r.unit_weight, r.weight) for r in recs]
    assert got == EXPECTED
    assert all(not r.needs_review() for r in recs)

def test_exception_sample_rows_are_kept_and_flagged(sample_pages, fixture_master):
    recs = [r for r in build_records(sample_pages, fixture_master) if r.file == "サンプル_例外.pdf"]
    assert len(recs) == 3                                           # 丸数字なしの 2 行 + API エラーの 1 行
    assert R_NO_CIRCLE in recs[0].reasons and recs[0].qty is None and recs[0].size == "Ｈ-294×200×8×12"
    assert recs[2].kind == "error" and recs[2].reasons == [R_ERROR.format("APIタイムアウト")]

def test_unreadable_circle_reason_differs_from_no_circle(fixture_master):
    recs = build_records([page_with(line(circle_status="読めない", uncertain=True))], fixture_master)
    assert R_UNREADABLE in recs[0].reasons and R_NO_CIRCLE not in recs[0].reasons

def test_unregistered_size(fixture_master):
    r = build_records([page_with(line(commodity_raw="I形鋼", size_raw="200X100X7X10"))], fixture_master)[0]
    assert R_NO_MASTER in r.reasons and r.unit_weight is None and r.weight is None

def test_over_qty_and_stamp_mismatch(fixture_master):
    recs = build_records([page_with(line(circled_qty=20, printed_qty=18), stamp_valid_qty=3)], fixture_master)
    assert R_OVER_QTY.format(20, 18) in recs[0].reasons and R_STAMP.format(3, 20) in recs[0].reasons

def test_mass_difference_detected(fixture_master):   # 長さを読み違えた想定: 11.5M のところ 5.5M
    r = build_records([page_with(line(length_raw="5.5M", circled_qty=1, printed_qty=18, mass_kg=10332))], fixture_master)[0]
    assert any(x.startswith("計算した重量") for x in r.reasons)

def test_pl_weight_prorated_and_half_up(fixture_master):
    r = build_records([page_with(line(commodity_raw="PLATE", size_raw="9X1524X3048", length_raw=None,
                                      circled_qty=1, printed_qty=2, mass_kg=657))], fixture_master)[0]
    assert r.weight == 329                                          # 328.5 → 329（ROUND_HALF_UP）

def test_not_certificate_page(fixture_master):
    r = build_records([PageEntry("x.pdf", 1, PageResult(is_certificate=False, stamp_valid_qty=None, lines=[]))], fixture_master)[0]
    assert r.kind == "not_certificate" and r.reasons == [R_NOT_CERT]

def test_certificate_with_no_lines_yields_review_row(fixture_master):
    r = build_records([PageEntry("x.pdf", 1, PageResult(is_certificate=True, stamp_valid_qty=None, lines=[]))], fixture_master)
    assert len(r) == 1 and r[0].reasons == [R_NO_LINES]

def test_to_dict_keys():
    assert list(sample_record().to_dict()) == ["ページ", "ファイル", "ページ番号", "品名", "材質", "寸法",
                                                "長さ_mm", "本数", "ミルシート重量", "重量", "要確認", "確認理由"]
```
`page_with(...)` / `line(...)` は既定値付きでテスト用の `PageEntry` / `Line` を作るヘルパー（テストファイル内。既定は H形鋼 200X200X8X12、11.5M、丸数字 1、印字 18、質量 10332）。

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — PASS
- [ ] **Step 5: コミット** — `git commit -m "feat: レコードの計算とチェック"`

---

### Task 6: 並べ替えとページ番号（8.6）

**Files:**
- Create: `millsheet/ordering.py`
- Test: `tests/test_ordering.py`

**Interfaces:**
- Consumes: `normalize.Record`、`sizes.size_key`
- Produces:
  - `ordering.CATEGORY_ORDER: list[str]` — 8.6 (1) の 1〜17 の順（`H形鋼, I形鋼, コラム, STKR, PL, FB, 溝形鋼, Cチャン, 丸パイプ, アングル, T形鋼, チェッカープレート, 角鋼, 丸鋼, D（鉄筋）, デッキ, EXメタ`）
  - `ordering.PageRef = tuple[str, int]`（相対パス, 1 始まりのページ番号）
  - `ordering.order_records(records: list[Record]) -> tuple[list[Record], list[PageRef]]` — 並べた新しいリストと、まとめた PDF のページの順を返す。各 Record の `page_label` を `"Ｐ-{n}"` に設定する（`page_no is None` の行は None のまま、`PageRef` にも入れない）

並べ替えのキー（この順に比べる）:
1. 品名の順位: `CATEGORY_ORDER` の位置、品名 None の `line` は 17、`not_certificate` / `error` は 18
2. 寸法が None なら後ろ
3. 寸法の数値の組を大きい順（`size_key(size)[1]` の各数値を符号反転したタプルで昇順）
4. 長さが None なら後ろ、長さの長い順
5. `input_index`

ページ番号: 並べた行を上から見て、まだ番号の無い `(file, page_no)` に出てきた順で 1, 2, 3… を振る。同じページの他の行も同じ番号。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_category_order():
    recs = [rec(cat="アングル"), rec(cat="I形鋼"), rec(cat=None), rec(cat="PL"), rec(cat="H形鋼"), rec(kind="error", cat=None)]
    assert [r.category for r in order_records(recs)[0]][:4] == ["H形鋼", "I形鋼", "PL", "アングル"]
    assert order_records(recs)[0][-1].kind == "error"

def test_size_desc_then_length_desc_then_input_order():
    recs = [rec(size="Ｈ-200×100×5.5×8", length=7000, i=0), rec(size="Ｈ-400×200×8×13", length=11000, i=1),
            rec(size="Ｈ-400×200×8×13", length=12000, i=2), rec(size="Ｈ-350×175×7×11", length=7000, i=3),
            rec(size="Ｈ-400×200×8×13", length=12000, i=4), rec(size=None, length=9000, i=5)]
    assert [r.input_index for r in order_records(recs)[0]] == [2, 4, 1, 3, 0, 5]

def test_page_placed_at_earliest_row_and_shares_label():
    # 1.pdf p1 に 溝形鋼、2.pdf p1 に H形鋼 と 溝形鋼
    recs = [rec(file="1.pdf", page=1, cat="溝形鋼", size="［-150×75×6.5", i=0),
            rec(file="2.pdf", page=1, cat="H形鋼", size="Ｈ-200×200×8×12", i=1),
            rec(file="2.pdf", page=1, cat="溝形鋼", size="［-100×50×5", i=2)]
    ordered, pages = order_records(recs)
    assert pages == [("2.pdf", 1), ("1.pdf", 1)]
    assert [(r.input_index, r.page_label) for r in ordered] == [(1, "Ｐ-1"), (0, "Ｐ-2"), (2, "Ｐ-1")]

def test_unreadable_pdf_row_gets_no_page_number():
    ordered, pages = order_records([rec(kind="error", file="broken.pdf", page=None, cat=None)])
    assert ordered[0].page_label is None and pages == [] and ordered[0].to_dict()["ページ"] == "—"

def test_sample_keeps_original_order(sample_records):   # conftest: build_records(sample_pages, fixture_master)
    ordered, pages = order_records([r for r in sample_records if r.file == "20261014084620.pdf"])
    assert [r.page_label for r in ordered] == [f"Ｐ-{i}" for i in range(1, 11)]
    assert pages == [("20261014084620.pdf", i) for i in range(1, 11)]
```
`rec(...)` は既定値付きで `Record` を作るテスト用ヘルパー（`file` 省略時は入力順ごとに別ページ）。

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — PASS
- [ ] **Step 5: コミット** — `git commit -m "feat: 並べ替えとページ番号"`

---

### Task 7: 出力（xlsx・JSON・raw・まとめた PDF）（12章）

**Files:**
- Create: `millsheet/export/__init__.py`, `millsheet/export/base.py`, `millsheet/export/local_xlsx.py`, `millsheet/export/json_out.py`, `millsheet/rawfile.py`, `millsheet/merge_pdf.py`
- Test: `tests/test_export.py`, `tests/test_merge_pdf.py`

**Interfaces:**
- Consumes: `Record.to_dict()`、`ordering.PageRef`、`schema.PageEntry`
- Produces:
  - `export.base.Exporter`（12.5 の Protocol そのまま: `export(self, records: list[dict], meta: dict) -> str`）
  - `export.local_xlsx.LocalXlsxExporter(path: Path)`（`export` は保存したパスを返す）
  - `export.get_exporter(name: str, xlsx_path: Path) -> Exporter`（`"local_xlsx"` だけ。他は `ValueError`）
  - `export.json_out.write_json(path: Path, records: list[dict], meta: dict) -> None`（`{"meta": meta, "records": records}`）
  - `rawfile.write_raw(path: Path, source_dir: Path | None, pages: list[PageEntry]) -> None`、`rawfile.read_raw(path: Path) -> tuple[Path | None, list[PageEntry]]`（12.3 の形。`pages` はファイル名順・ページ順に並べて返す。`page_no` が None のエントリは `"page": null`）
  - `merge_pdf.merge_pages(pages: list[PageRef], source_dir: Path, out_path: Path) -> None`（PyMuPDF の `insert_pdf(src, from_page=n-1, to_page=n-1)`。開けないファイルがあれば何も書かずに `MergeError(missing: list[str])`）
  - `merge_pdf.MergeError(Exception)`

xlsx（12.2）: シート名「ミルシート」、列 `ページ / 品名 / 材質 / 寸法 / 長さ(mm) / 本数 / ミルシート重量(kg/m) / 重量(kg) / 要確認 / 確認理由`。要確認は `"要確認"` か空、確認理由は `"、"` でつなぐ。要確認の行は薄い黄色 `FFF9C4`、null のセルは薄い赤 `FFCDD2`（要確認・確認理由の列と、PL の長さ・ミルシート重量の列は null でも塗らない）。最終行の下の行に「合計」と `=SUM(H2:H{last})`。`freeze_panes="A2"`、オートフィルタは見出しからデータの最終行まで。長さ・重量は `#,##0`。保存は一時ファイルに書いてから `os.replace`、`PermissionError` は `OutputLockedError(path)` にして投げる（`export/base.py` に定義）。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_xlsx_layout(tmp_path, ordered_sample_dicts):   # conftest: 並べ替え済みサンプル + 例外サンプルの to_dict()
    p = LocalXlsxExporter(tmp_path / "out.xlsx").export(ordered_sample_dicts, {})
    ws = openpyxl.load_workbook(p)["ミルシート"]
    assert [c.value for c in ws[1]] == ["ページ", "品名", "材質", "寸法", "長さ(mm)", "本数", "ミルシート重量(kg/m)", "重量(kg)", "要確認", "確認理由"]
    assert ws["A2"].value == "Ｐ-1" and ws["H2"].value == 574 and ws["H2"].number_format == "#,##0"
    last = 1 + len(ordered_sample_dicts)
    assert ws.cell(last + 1, 8).value == f"=SUM(H2:H{last})"
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref == f"A1:J{last}"

def test_xlsx_colors(tmp_path, ordered_sample_dicts):
    ws = openpyxl.load_workbook(LocalXlsxExporter(tmp_path / "o.xlsx").export(ordered_sample_dicts, {}))["ミルシート"]
    review_row = next(r for r in range(2, ws.max_row) if ws.cell(r, 10).value == "丸数字が書かれていません")
    assert ws.cell(review_row, 2).fill.fgColor.rgb.endswith("FFF9C4")    # 品名あり → 黄色
    assert ws.cell(review_row, 6).fill.fgColor.rgb.endswith("FFCDD2")    # 本数 null → 赤
    ok_row = 2
    assert ws.cell(ok_row, 2).fill.fgColor.rgb in (None, "00000000")      # 要確認でない行は塗らない
    pl_row = next(r for r in range(2, ws.max_row) if ws.cell(r, 2).value == "PL")
    assert ws.cell(pl_row, 5).value is None and not ws.cell(pl_row, 5).fill.fgColor.rgb.endswith("FFCDD2")

def test_xlsx_locked_raises(tmp_path, monkeypatch, ordered_sample_dicts):
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(OutputLockedError):
        LocalXlsxExporter(tmp_path / "o.xlsx").export(ordered_sample_dicts, {})

def test_raw_roundtrip(tmp_path, sample_pages):
    write_raw(tmp_path / "x_raw.json", tmp_path, sample_pages)
    src, pages = read_raw(tmp_path / "x_raw.json")
    assert src == tmp_path and pages == sample_pages

def test_read_raw_accepts_fixture():
    src, pages = read_raw(Path("tests/fixtures/sample_raw.json"))
    assert src is None and len(pages) == 12

# tests/test_merge_pdf.py — PyMuPDF で各ページに "A-1" などの文字を書いた PDF を tmp に作って使う
def test_merge_pages_order(tmp_path, two_pdfs):         # A.pdf(2 ページ), sub/B.pdf(1 ページ)
    merge_pages([("sub/B.pdf", 1), ("A.pdf", 2), ("A.pdf", 1)], tmp_path, tmp_path / "out.pdf")
    doc = pymupdf.open(tmp_path / "out.pdf")
    assert [p.get_text().strip() for p in doc] == ["B-1", "A-2", "A-1"]

def test_merge_pages_missing_file(tmp_path, two_pdfs):
    with pytest.raises(MergeError) as e:
        merge_pages([("none.pdf", 1)], tmp_path, tmp_path / "out.pdf")
    assert e.value.missing == ["none.pdf"] and not (tmp_path / "out.pdf").exists()
```

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — `pytest tests/test_export.py tests/test_merge_pdf.py -v` → PASS
- [ ] **Step 5: コミット** — `git commit -m "feat: xlsx・JSON・raw・PDF の出力"`

---

### Task 8: 読み取り（PDF の一覧・画像化・Gemini・キャッシュ）（5章、6章）

**Files:**
- Create: `millsheet/prompt.py`, `millsheet/extract.py`, `millsheet/cache.py`
- Test: `tests/test_extract.py`, `tests/test_extract_live.py`

**Interfaces:**
- Consumes: `schema.PageResult`、`schema.PageEntry`、`paths.cache_dir`
- Produces:
  - `prompt.SYSTEM_PROMPT: str`（6.2 のルールを箇条書きで全部入れる。6.1 の各フィールドの意味も書く）、`prompt.PROMPT_VERSION: str`（プロンプトを変えたら上げる。キャッシュのキーに使う）
  - `extract.MODEL = "gemini-3.8-flash"`
  - `extract.list_pdfs(folder: Path) -> list[str]`（サブフォルダも含め `.pdf`（大文字小文字を区別しない）を相対パス `/` 区切りで、相対パスの文字列順に返す）
  - `extract.page_count(pdf: Path) -> int`（開けなければ `PdfOpenError`）
  - `extract.render_png(pdf: Path, page_no: int, dpi: int = 200) -> bytes`
  - `extract.PageReader`（Protocol: `read(png: bytes) -> PageResult`）
  - `extract.GeminiReader(api_key: str)`（`PageReader` を実装）
  - `extract.read_folder(folder: Path, reader: PageReader, cache: PageCache, *, workers: int = 4, on_progress: Callable[[str, int, int], None] = ..., cancel: threading.Event | None = None) -> list[PageEntry]` — 戻り値はファイル名順・ページ順。`on_progress(相対パス, 何ページ目, そのファイルのページ数)` は読み取りを始めるたびに呼ぶ。キャンセルされたら `Cancelled` を投げる（終わったページはキャッシュに残る）
  - `extract.Cancelled(Exception)`、`extract.PdfOpenError(Exception)`、`extract.PageReadError(Exception)`（1 ページの読み取りがリトライ後も失敗）、`extract.ReaderAuthError(Exception)`（キーの誤り・課金未設定。全体を止める）
  - `cache.PageCache(dir: Path)`: `get(pdf_hash: str, page_no: int) -> PageResult | None`、`put(pdf_hash, page_no, result) -> None`、`cache.file_hash(path: Path) -> str`（SHA-256）。キーは `f"{pdf_hash}_{page_no}_{MODEL}_{PROMPT_VERSION}"`、成功した結果だけ保存する

`GeminiReader.read` の呼び出し（6.3。SDK の書き方は実装時にインストールした `google-genai` で確かめる。Interactions API が使えない版なら `client.models.generate_content(..., config={"response_mime_type": "application/json", "response_schema": PageResult, "temperature": 0, "seed": 0})` にする）:

```python
interaction = client.interactions.create(
    model=MODEL,
    system_instruction=SYSTEM_PROMPT,
    input=[{"type": "text", "text": "この画像の検査証明書を読み取ってください。"},
           {"type": "image", "data": base64.b64encode(png).decode(), "mime_type": "image/png"}],
    response_format={"type": "text", "mime_type": "application/json", "schema": PageResult.model_json_schema()},
    generation_config={"thinking_level": "low", "seed": 0},
    store=False,
)
return PageResult.model_validate_json(interaction.output_text)
```
リトライは `GeminiReader.read` の中で行う: 例外（通信・5xx・429・JSON の検証エラー）のとき 1, 2, 4 秒待って最大 3 回やり直し、4 回目も失敗したら `PageReadError(メッセージ)` を投げる（メッセージの API キーは `applog.mask` で伏せる）。`read_folder` は `PageReadError` を受けて `PageEntry.error` にする。401/403（キーの誤り・課金未設定）はリトライせず、全体を止めて `ReaderAuthError("Gemini の API キーが正しくないか、課金が設定されていません")` を投げる。
`read_folder`: PDF が開けなければ `PageEntry(file, None, None, "PDF を開けませんでした")` を 1 つ入れて次のファイルへ。ページごとに キャッシュ → 無ければ `render_png` → `reader.read` を `ThreadPoolExecutor(max_workers=workers)` で回す。

- [ ] **Step 1: 失敗するテストを書く**（`FakeReader` は呼ばれた回数を数え、決まった `PageResult` を返すか、指定回数だけ例外を投げる）

```python
def test_list_pdfs_same_name_in_subfolders(tmp_path):
    make_pdf(tmp_path / "B/001.pdf", 1); make_pdf(tmp_path / "A/001.pdf", 1); make_pdf(tmp_path / "c.PDF", 1)
    (tmp_path / "note.txt").write_text("x")
    assert list_pdfs(tmp_path) == ["A/001.pdf", "B/001.pdf", "c.PDF"]

def test_render_png_is_png(sample_pdf):
    assert render_png(sample_pdf, 1)[:8] == b"\x89PNG\r\n\x1a\n"

def test_read_folder_order_and_cache(tmp_path):
    make_pdf(tmp_path / "b.pdf", 2); make_pdf(tmp_path / "a.pdf", 1)
    reader = FakeReader()
    entries = read_folder(tmp_path, reader, PageCache(tmp_path / "cache"))
    assert [(e.file, e.page_no) for e in entries] == [("a.pdf", 1), ("b.pdf", 1), ("b.pdf", 2)]
    assert reader.calls == 3
    read_folder(tmp_path, reader, PageCache(tmp_path / "cache"))
    assert reader.calls == 3                                         # 2 回目はキャッシュだけ

def test_read_folder_page_error_becomes_entry(tmp_path):
    make_pdf(tmp_path / "a.pdf", 1)
    e = read_folder(tmp_path, FakeReader(raise_error=PageReadError("503")), PageCache(tmp_path / "c"))
    assert e[0].result is None and e[0].error == "503"

def test_open_failure_yields_error_entry(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    e = read_folder(tmp_path, FakeReader(), PageCache(tmp_path / "c"))
    assert e == [PageEntry("broken.pdf", None, None, "PDF を開けませんでした")]

def test_cancel_raises(tmp_path):
    make_pdf(tmp_path / "a.pdf", 3); ev = threading.Event(); ev.set()
    with pytest.raises(Cancelled):
        read_folder(tmp_path, FakeReader(), PageCache(tmp_path / "c"), cancel=ev)

def test_gemini_reader_retries_then_reports_error(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = GeminiReader("KEY"); r._call = Mock(side_effect=RuntimeError("503"))   # _call: SDK を呼ぶ 1 回分（内部メソッド）
    with pytest.raises(PageReadError):
        r.read(b"png")
    assert r._call.call_count == 4
```
`GeminiReader._call(png: bytes) -> PageResult` は SDK を 1 回呼ぶだけの内部メソッド（テストで差し替えるため分ける）。

`tests/test_extract_live.py`（`GEMINI_API_KEY` が無ければ skip）: サンプル PDF の 10 ページを `GeminiReader` で読み、Task 5 の `build_records` に通して `EXPECTED` と項目ごとの一致率を表示し、10 ページすべて一致を assert する（18章）。

- [ ] **Step 2: 実行して失敗を確かめる** — `pytest tests/test_extract.py -v` → FAIL
- [ ] **Step 3: `prompt.py`・`cache.py`・`extract.py` を実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — PASS
- [ ] **Step 5: 実 API で確かめる**（キーがあるとき）— `GEMINI_API_KEY=... pytest tests/test_extract_live.py -v -s` → 一致率が表示され PASS。合わない項目があれば `prompt.py` を直して `PROMPT_VERSION` を上げる
- [ ] **Step 6: コミット** — `git commit -m "feat: PDF の画像化と Gemini での読み取り"`

---

### Task 9: パイプライン（run / rebuild）

**Files:**
- Create: `millsheet/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 4〜8 のすべて
- Produces:
  - `pipeline.Outputs`（dataclass: `xlsx: Path`, `json: Path`, `raw: Path`, `pdf: Path | None`）、`pipeline.outputs_for(xlsx: Path) -> Outputs`（`X.xlsx` → `X.json` / `X_raw.json` / `X.pdf`）
  - `pipeline.RunResult`（dataclass: `records: list[Record]`, `outputs: Outputs`, `master: Master`, `warnings: list[str]`, `errors: list[str]`）。`errors` は出力の一部ができなかった理由（xlsx が開かれている、PDF が作れない）
  - `pipeline.run(source_dir: Path, xlsx: Path, *, settings: Settings, gemini_key: str, google_key: str, reader: PageReader | None = None, master_loader: Callable[[], tuple[Master, list[str]]] | None = None, on_progress=..., cancel=None) -> RunResult`
  - `pipeline.rebuild(raw: Path, xlsx: Path, *, settings: Settings, google_key: str, master_loader=None) -> RunResult`
  - `pipeline.review_messages(records: list[Record]) -> list[str]`（画面の要確認一覧の文言。13章の例 `"○○.pdf の 3 ページ目がうまく読み込めませんでした（丸数字が読めません）"`。ページ番号が無いときは `"○○.pdf を読み込めませんでした（…）"`）

`run` の順番: キーの有無を確かめる（無ければ `ValueError("設定画面で Gemini の API キーを入力してください")` など）→ **マスタを先に取得**（失敗したら課金前に止める）→ `read_folder` → `_raw.json` を保存 → `_build_and_export`。
`rebuild` は `_raw.json` を読み、マスタを取り直して `_build_and_export`。`source_dir` が None か、元の PDF が無ければ PDF は作らず `errors` に `"元の PDF が見つからないため、PDF は作れませんでした"`。
`_build_and_export`: `build_records` → `order_records` → JSON・xlsx（`get_exporter(settings.exporter, xlsx)`）・PDF。meta は `{"作成日時", "モデル": MODEL, "単重マスタ": master.meta()}`。`OutputLockedError` は `errors` に `"xlsx が他のアプリで開かれています。閉じてから『作り直す』を押してください"` を入れて続ける（raw は保存済み）。`master_loader` を省略したら `fetch_master(settings.sheet_url, settings.sheet_name, google_key)` を使う。

- [ ] **Step 1: 失敗するテストを書く**（`reader` は raw フィクスチャの結果を返す偽物、`master_loader` は `load_master_file` を返す）

```python
def test_run_writes_all_outputs(tmp_path, sample_folder, fake_reader, fixture_master_loader):
    res = run(sample_folder, tmp_path / "out.xlsx", settings=Settings(), gemini_key="g", google_key="k",
              reader=fake_reader, master_loader=fixture_master_loader)
    o = res.outputs
    assert o.xlsx.exists() and o.json.exists() and o.raw.exists() and o.pdf.exists()
    assert pymupdf.open(o.pdf).page_count == 10 and res.errors == []

def test_rebuild_does_not_call_reader(tmp_path, sample_folder, fake_reader, fixture_master_loader):
    run(sample_folder, tmp_path / "out.xlsx", settings=Settings(), gemini_key="g", google_key="k",
        reader=fake_reader, master_loader=fixture_master_loader)
    n = fake_reader.calls
    res = rebuild(tmp_path / "out_raw.json", tmp_path / "out.xlsx", settings=Settings(), google_key="k",
                  master_loader=fixture_master_loader)
    assert fake_reader.calls == n and len(res.records) == 10

def test_master_failure_stops_before_reading(tmp_path, sample_folder, fake_reader):
    def bad(): raise MasterFetchError("ネットに接続できません")
    with pytest.raises(MasterFetchError):
        run(sample_folder, tmp_path / "o.xlsx", settings=Settings(), gemini_key="g", google_key="k",
            reader=fake_reader, master_loader=bad)
    assert fake_reader.calls == 0

def test_run_reports_locked_output_and_keeps_raw(tmp_path, sample_folder, fake_reader, fixture_master_loader, monkeypatch):
    monkeypatch.setattr(LocalXlsxExporter, "export", Mock(side_effect=OutputLockedError(tmp_path / "o.xlsx")))
    res = run(sample_folder, tmp_path / "o.xlsx", settings=Settings(), gemini_key="g", google_key="k",
              reader=fake_reader, master_loader=fixture_master_loader)
    assert res.outputs.raw.exists() and any("開かれています" in e for e in res.errors)

def test_rebuild_without_source_pdf(tmp_path, fixture_master_loader):
    res = rebuild(Path("tests/fixtures/sample_raw.json"), tmp_path / "o.xlsx", settings=Settings(), google_key="k",
                  master_loader=fixture_master_loader)
    assert res.outputs.pdf is None and "元の PDF" in res.errors[0]

def test_review_messages():
    assert review_messages([rec(file="a.pdf", page=3, reasons=["丸数字が読めません"])]) == \
        ["a.pdf の 3 ページ目がうまく読み込めませんでした（丸数字が読めません）"]
```
`sample_folder` は `tests/fixtures/20261014084620.pdf` だけを tmp のフォルダにコピーしたもの（PDF が無ければ skip）。

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — PASS。続けて `pytest -q` で全体が通ること
- [ ] **Step 5: コミット** — `git commit -m "feat: 読み取りから出力までのパイプライン"`

---

### Task 10: 画面（13章）

**Files:**
- Create: `main.py`, `gui/__init__.py`, `gui/worker.py`, `gui/main_window.py`, `gui/settings_dialog.py`, `gui/master_dialog.py`
- Test: `tests/test_gui_smoke.py`（`pytest-qt`、`QT_QPA_PLATFORM=offscreen` を `pytest.ini` の `env` ではなく `conftest.py` で設定）

**Interfaces:**
- Consumes: `pipeline.run` / `rebuild` / `review_messages` / `outputs_for`、`master.fetch_master` / `export_bundled_csv` / `MasterFetchError` / `MasterValidationError`、`settings.*`、`applog.setup_logging`
- Produces:
  - `gui.worker.RunWorker(QThread)`（`__init__(mode: Literal["run", "rebuild"], **pipeline_kwargs)`。シグナル `progress(str, int, int)`（文言, 全体の何ページ目, 全ページ数）, `finished_ok(object)`（RunResult）, `failed(str)`。`cancel()` で `threading.Event` を立てる）
  - `gui.main_window.MainWindow(QMainWindow)`（`__init__(fetch_on_start: bool = True)`、属性 `run_button`、メソッド `set_source_dir(p: Path)`・`set_output_path(p: Path)`）
  - `gui.settings_dialog.SettingsDialog(QDialog)`（属性 `gemini_key_edit`・`google_key_edit`・`sheet_url_edit`・`sheet_name_edit`）
  - `gui.master_dialog.MasterDialog(QDialog)`（`__init__(master: Master)`、属性 `search_edit`・`category_combo`、メソッド `visible_row_count() -> int`）
  - `main.py`: `applog.setup_logging()` → `QApplication` → `MainWindow().show()`

画面の中身（13章）:
- メイン: フォルダのドロップ枠（`dragEnterEvent` でフォルダだけ受け付ける）＋「フォルダを選ぶ」、出力先の xlsx（「参照」）、実行・キャンセル、進捗バーと `"{ファイル名} {n}/{全} ページ目を読み取り中"`、要確認の一覧（`QListWidget`。`review_messages` の文言。単重未登録の行は品名・サイズを選択してコピーできる）、「スプレッドシートを開く」「マスタを読み直して作り直す」「xlsx を開く」「PDF を開く」「フォルダを開く」（`QDesktopServices.openUrl`）、警告と `errors` の表示、マスタの件数・取得日時・取得元（起動時に別スレッドで `fetch_master`）
- 設定: Gemini の API キー、Google の API キー（どちらも `QLineEdit.EchoMode.Password`、空欄のまま保存したら変更しない）、スプレッドシートの URL、シート名、「接続を確かめる」（`fetch_master` の件数か失敗の文言）、「初期マスタを CSV で書き出す」
- マスタ一覧: `QTableWidget`（品名・サイズ・単重）、検索欄（サイズの部分一致）、品名の絞り込み（`QComboBox`）、「スプレッドシートを開く」「読み直す」。編集はできない
- 例外は画面に日本語で出し、詳しい内容はログに書く。API キーは画面にもログにも出さない

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_main_window_opens(qtbot, data_dir):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    assert w.run_button.isEnabled() is False          # フォルダと出力先が決まるまで押せない

def test_main_window_enables_run(qtbot, data_dir, tmp_path):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path); w.set_output_path(tmp_path / "o.xlsx")
    assert w.run_button.isEnabled()

def test_settings_dialog_saves_without_writing_keys_to_file(qtbot, data_dir, monkeypatch):
    saved = {}
    monkeypatch.setattr("millsheet.settings.set_secret", lambda n, v: saved.__setitem__(n, v))
    d = SettingsDialog(); qtbot.addWidget(d)
    d.gemini_key_edit.setText("G"); d.sheet_url_edit.setText("https://docs.google.com/spreadsheets/d/x/edit")
    d.accept()
    assert saved["gemini_api_key"] == "G" and "G" not in (data_dir / "settings.json").read_text("utf-8")

def test_master_dialog_filters(qtbot):
    d = MasterDialog(load_master_file(Path("tests/fixtures/unit_weights.json"))); qtbot.addWidget(d)
    d.category_combo.setCurrentText("FB")
    assert d.visible_row_count() == 36
```

- [ ] **Step 2: 実行して失敗を確かめる** — FAIL
- [ ] **Step 3: 画面を実装する**
- [ ] **Step 4: 実行して通ることを確かめる** — `pytest tests/test_gui_smoke.py -v` → PASS
- [ ] **Step 5: 手で動かして確かめる** — `python main.py`。設定でキーとシートを入れ、「接続を確かめる」で件数が出る → サンプルのフォルダをドロップ → 実行 → 進捗が進み、xlsx・PDF ができ、「xlsx を開く」「PDF を開く」が動く。途中で「キャンセル」が効く
- [ ] **Step 6: コミット** — `git commit -m "feat: 画面"`

---

### Task 11: ビルドと配布（11章）

**Files:**
- Create: `.github/workflows/build.yml`, `README.md`

**Interfaces:**
- Consumes: `main.py`、`millsheet/unit_weights.json`

- [ ] **Step 1: ワークフローを書く** — SPEC 11章の例をもとに、`pip install -r requirements.txt pyinstaller` と
  `pyinstaller --noconfirm --windowed --name ミルシート読み取り --add-data "millsheet/unit_weights.json:millsheet" main.py`（PyInstaller 6 以降は Windows でも `:` 区切りでよい）。テストも先に流す（`pip install -r requirements-dev.txt` → `pytest -q`。PDF が無いテストは skip される）。Mac は `macos-latest`（Apple シリコン）
- [ ] **Step 2: 手元で Mac 用をビルドして起動を確かめる** — 上の `pyinstaller` コマンドで `dist/ミルシート読み取り.app` ができ、起動して設定画面が開き、「初期マスタを CSV で書き出す」が 225 件の CSV を作る（内蔵マスタが読めている）
- [ ] **Step 3: README を書く** — 使い始めの手順（初期マスタの CSV を書き出してスプレッドシートに読み込む → 共有を「リンクを知っている全員が閲覧可」にする → Google Cloud で API キーを作り Google Sheets API だけに制限する → 設定画面に URL・キー・Gemini のキーを入れる）、開発の手順（`uv venv --python 3.12` → `pytest`）、配布の手順（タグを push）、署名なしの起動方法（11章）
- [ ] **Step 4: コミット** — `git commit -m "build: GitHub Actions と README"`

---

## 実行のあとに確かめること

- `pytest -q` が全部通る（実 API のテストは skip でよい）
- 実 API のテストで、サンプル 10 ページの一致率を出し、結果を報告する（18章）
- 手で 1 回、サンプルのフォルダで最後まで動かし、xlsx の `Ｐ-n` とまとめた PDF の n ページ目が同じ証明書であることを目で見て確かめる
