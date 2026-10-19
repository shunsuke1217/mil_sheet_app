# ミルシート読み取りアプリ 実装の現状と残りの作業

> **For agentic workers:** 残りの作業（5章）を進めるときは superpowers:executing-plans を使う。各作業はテストを先に書き（`- [ ]` で進捗を付ける）、終わったら `.venv/bin/pytest -q` が全部通ることを確かめてからコミットする。

**Goal:** スキャンしたミルシート PDF のフォルダを Gemini で読み取り、材種順・サイズ順に並べた xlsx と、同じ順に並べ替えて 1 つにまとめた PDF を、実行ごとの出力フォルダに出す Windows / Mac 両対応のデスクトップアプリ。

**Architecture:** 読み取り（Gemini）→ 生の結果（`_raw.json`）→ 計算・チェック → 並べ替え → 出力（xlsx・PDF・JSON）の一方向のパイプライン。API を使うのは読み取りだけで、それ以降は `_raw.json` と単重マスタだけから何度でも作り直せる。画面（PySide6）は `pipeline.run` / `pipeline.rebuild` を別スレッドで呼ぶだけで、ロジックを持たない。

**Tech Stack:** Python 3.12 / PySide6 / PyMuPDF / google-genai 2.31（Interactions API）/ pydantic v2 / openpyxl / httpx / platformdirs / keyring / pytest / PyInstaller / GitHub Actions

**Spec:** [SPEC.md](../../../SPEC.md)（章番号はすべて SPEC.md のもの）

この文書は、最初の実装計画（2026-10-17 版）を、実装後の状態に合わせて書き直したもの。最初の計画との違いは 4 章にまとめた。

---

## 1. 現状（2026-10-19 時点）

| 項目 | 状態 |
|---|---|
| 実装 | SPEC の第 1 段階はすべて実装済み。ブランチ `feat/millsheet-app`（`main` には未マージ） |
| 自動テスト | 191 件通過、1 件スキップ（`tests/test_extract_live.py`。環境変数 `GEMINI_API_KEY` があるときだけ動く） |
| 受け入れ基準（SPEC 18 章） | サンプル 10 ページの正解表を `sample_raw.json` から完全に再現できる（API を使わないテスト） |
| 実 API での動作 | 2026-10-17 に実際のミルシート 10 件で読み取り・出力まで動いたことをログで確認。**出力の中身の正しさは未照合** |
| Mac 用ビルド | Apple シリコン用の `.app` を作り、起動すること・Gemini の部品と内蔵マスタが入っていることを確認 |
| Windows 用ビルド | 未実施（GitHub Actions のワークフローは用意済み） |
| 既知の不具合 | 5.1（Gemini の呼び出しが最初に失敗することがある）。配る前に直す |

## 2. 処理の流れ

```
[画面] PDF のフォルダをドロップ → 保存する場所・出力フォルダ名を決める → 「読み取りを実行」
  │  （別スレッド: gui/worker.py の RunWorker）
  ▼
① 準備のチェック   pipeline.run     Gemini のキー・単重マスタの URL・PDF の有無。出力フォルダを作る
② 単重マスタ       master.fetch_master   リンク共有したスプレッドシートを CSV で読む（課金の前に止められる）
③ 読み取り         extract.read_folder   ページごとに キャッシュ → PNG(200dpi) → Gemini → PageResult（4 並列）
④ 生の結果を保存   rawfile.write_raw     出力フォルダ/作業データ/名前_raw.json
⑤ 計算とチェック   normalize.build_records   材種の判定・寸法の統一・単重・重量・要確認
⑥ 並べ替え         ordering.order_records    材種の順・サイズの大きい順・長さの長い順、Ｐ-n を振る
⑦ 出力             local_xlsx / merge_pdf / json_out
  ▼
[画面] 要確認の一覧を表示し、出力フォルダを開く
```

「マスタを読み直して作り直す」（`pipeline.rebuild`）は ③ を飛ばし、`_raw.json` から ⑤〜⑦ をやり直す（課金なし）。

出力フォルダの中身:

```
保存する場所/
└─ 出力フォルダ名/
   ├─ 出力フォルダ名.xlsx
   ├─ 出力フォルダ名.pdf          ← 並べ替えてまとめた PDF（n ページ目 = xlsx の Ｐ-n）
   └─ 作業データ/
      ├─ 出力フォルダ名.json
      └─ 出力フォルダ名_raw.json  ← 作り直しに使う
```

## 3. ファイル構成と役割

| ファイル | 役割 | 主な関数・クラス |
|---|---|---|
| `main.py` | 画面の起動 | `main()` |
| `gui/main_window.py` | メイン画面。ドロップ枠、保存する場所、出力フォルダ名、実行・キャンセル、要確認の一覧 | `DropArea`、`MainWindow`（`set_source_dir`・`set_output_base`・`output_dir`・`refresh_master`） |
| `gui/worker.py` | 別スレッドでの実行と、エラーの日本語化 | `RunWorker`、`MasterWorker`、`friendly_error` |
| `gui/settings_dialog.py` | 設定画面（Gemini のキー、単重マスタの URL、保存する場所、接続の確認、初期マスタの CSV 書き出し） | `SettingsDialog` |
| `gui/master_dialog.py` | 単重マスタの一覧（表示だけ。検索・材種で絞り込み） | `MasterDialog` |
| `millsheet/pipeline.py` | 処理全体の入口 | `run`、`rebuild`、`outputs_for`、`review_messages` |
| `millsheet/extract.py` | PDF の一覧・画像化、Gemini での読み取り、リトライ、並列化 | `list_pdfs`、`render_png`、`GeminiReader`、`read_folder` |
| `millsheet/prompt.py` | モデル名・プロンプト・プロンプトの版 | `MODEL = "gemini-3.8-flash"`、`SYSTEM_PROMPT`、`PROMPT_VERSION` |
| `millsheet/schema.py` | Gemini に返させる JSON の形（項目ごとの説明付き） | `Line`、`PageResult`、`PageEntry` |
| `millsheet/cache.py` | ページ単位の読み取りキャッシュ（PDF のハッシュ＋ページ＋モデル＋プロンプトの版） | `PageCache`、`file_hash` |
| `millsheet/master.py` | 単重マスタの取得（CSV）・検証・キャッシュ・照合 | `fetch_master`、`parse_sheet_values`、`Master.lookup`、`export_bundled_csv` |
| `millsheet/classify.py` | 材種の判定（SPEC 6.4 のキーワード表） | `classify`、`KEYWORDS` |
| `millsheet/sizes.py` | 寸法の取り出し・統一、長さの換算、照合用のキー | `extract_dimension`、`normalize_size`、`size_key`、`parse_length_mm` |
| `millsheet/normalize.py` | 1 行ごとの計算とチェック、確認理由の文言 | `build_records`、`Record`、`R_*` |
| `millsheet/ordering.py` | 並べ替えとページ番号 | `CATEGORY_ORDER`、`order_records` |
| `millsheet/merge_pdf.py` | 並べ替えた PDF の作成（元のページをそのままコピー） | `merge_pages` |
| `millsheet/export/` | 出力（差し替えられる形） | `Exporter`、`LocalXlsxExporter`、`write_json`、`save_atomic`、`OutputLockedError` |
| `millsheet/rawfile.py` | `_raw.json` の読み書き | `write_raw`、`read_raw` |
| `millsheet/settings.py` | `settings.json` と keyring（API キー） | `Settings`、`load_settings`、`get_secret`、`set_secret` |
| `millsheet/paths.py` | データ用フォルダ（`MILLSHEET_DATA_DIR` で差し替え可） | `data_dir`、`bundled_master_path` |
| `millsheet/applog.py` | ログ（API キーを伏せる） | `setup_logging`、`mask` |
| `millsheet/unit_weights.json` | 内蔵の初期単重マスタ（225 件、`{材種, サイズ, 単重}`） | — |
| `tests/` | 自動テスト。`conftest.py` はデータ用フォルダ・keyring・ダイアログを毎回差し替える | — |
| `.github/workflows/build.yml` | Windows（exe 1 つ）と Mac（.app の zip）のビルド | — |

## 4. 主な決定事項（最初の計画からの変更を含む）

| 項目 | 決定 | 理由 |
|---|---|---|
| 単重マスタの置き場所・読み方 | Google スプレッドシートを「リンクを知っている全員（閲覧者）」にし、`…/export?format=csv&gid=…` から CSV で読む。**API キー・Google Cloud は不要**。設定は URL を貼るだけ | 最初の計画は Sheets API と API キーだったが、読むだけなら不要なため変更。共有されていないシートは Google のログイン画面が返るので見分けて案内する |
| 単重マスタの見出し | `材種` / `サイズ` / `単重`（列の順は自由、他の列は無視）。照合はサイズだけで、材種の列は一覧の絞り込み用 | 現場では H形鋼・Cチャンなどの区分を「材種」と呼ぶため |
| 単重の追加・変更 | アプリではしない。スプレッドシートを直接編集する | 読むだけの方式にしたため |
| 出力 | 実行ごとに出力フォルダを作り、xlsx と PDF を入れる。JSON と `_raw.json` は `作業データ/` に入れる。保存する場所はメイン画面で選び、次回も使う | 依頼主の希望 |
| 出力の列名 | 「品名」ではなく「材種」 | 同上 |
| 並び順 | H形鋼 → I形鋼 → コラム → STKR → PL → FB → 溝形鋼 → Cチャン → 丸パイプ → アングル → その他 → 未分類 → 証明書でない・失敗。同じ材種はサイズの大きい順・長さの長い順 | SPEC 8.6 |
| 材種の判定 | アプリ側のキーワード表だけ。AI には判定させない | 結果が毎回同じで、テストでき、直しても再課金にならない。判定できない行は要確認として人が見る |
| 寸法の読み方 | 区切り記号でつながった数字の並びだけを寸法とし、前後の製品番号・色などは捨てる | 実データで `K5674Dグレー` の改行のあとに `2.3X100X50X20` と読まれ、未登録になったため |
| 重量 | PL 以外は「長さ × 本数 × 単重」。証明書の質量は 5% ずれのチェックだけに使う。PL は質量（使った本数が少なければ按分） | 依頼主の既存の目次が単重から重量を出しているため |
| Gemini への送り方 | 1 ページずつ PNG（200dpi）で送る。モデルは `gemini-3.8-flash`、Interactions API、`temperature=0`・`seed=0`・`thinking_level="low"`・`store=False` | 1 ページずつにすることで、対応のずれを防ぎ、失敗したページだけ送り直し、送信サイズの上限を避け、ページ単位でキャッシュできる |
| プロンプト | 役割の指定（「あなたは〜係」）はやめ、何の書類を何のために読むかを説明する。項目の説明は JSON スキーマの `description` に入れる | 今のモデルでは役割の指定の効果は薄いため |
| リトライ | 429・5xx・通信の失敗・JSON の形の誤りだけ 1・2・4 秒あけて最大 3 回。キーの誤り・その他の 4xx はすぐ全体を止める | 全ページが同じ理由で失敗するものを、時間をかけて繰り返さないため |
| API キー | Gemini のキーだけ。OS の保管場所（Mac: キーチェーン / Windows: 資格情報マネージャー）に保存し、設定ファイル・ログには書かない | — |
| 押印の N が読めないページ | 比べずに飛ばし、要確認にもしない | 依頼主の判断 |
| 出力先の Google ドライブ化 | 今はしない（ローカルのみ）。必要ならパソコン版 Google ドライブの同期フォルダを保存する場所に選ぶ | アプリから直接アップロードするには、Google Cloud への登録（OAuth）が必要なため（6 章） |

## 5. 残りの作業

### 5.1 Gemini のクライアントを 1 つだけ作る（配る前に直す）

**現象:** 4 ページを同時に読むと、最初の数ページが「Cannot send a request, as the client has been closed.」で失敗し、やり直しで成功する（2026-10-17 の実行で 3 ページ）。課金はされないが、やり直しも失敗するとそのページがエラー行になる。

**原因:** `GeminiReader._call` が「クライアントがまだ無ければ作る」をスレッドごとに同時に行い、後から作ったものに上書きされた古いクライアントが閉じられる。

**Files:** `millsheet/extract.py`（`GeminiReader`）、`tests/test_extract.py`

- [ ] 失敗するテストを書く: `genai.Client` を、作られた回数を数え、作成に少し時間がかかる偽物に差し替える。8 スレッドから同時に `GeminiReader("KEY")._call(b"png")` を呼び、作られた回数が 1 であることを確かめる（`interactions.create` は決まった `PageResult` の JSON を返す偽物）
- [ ] 実行して失敗することを確かめる（回数が 2 以上）
- [ ] `GeminiReader.__init__` に `threading.Lock` を持たせ、クライアントの作成をロックの中で 1 回だけ行う
- [ ] テスト全体を流して通ることを確かめ、コミットする

### 5.2 読み取りの精度を確かめる

- [ ] 2026-10-17 に出力した `test_1.xlsx` を元の PDF と 1 行ずつ見比べ、違いを記録する
- [ ] `GEMINI_API_KEY=… .venv/bin/pytest tests/test_extract_live.py -s` で、サンプル 10 ページの項目ごとの一致率を出す（SPEC 18 章。目標は 10 ページすべて一致）
- [ ] 合わない項目があれば `prompt.py` / `schema.py` の説明を直し、`PROMPT_VERSION` を上げて測り直す
- [ ] （任意）PNG で送る場合と、1 ページだけの PDF に切り出して送る場合で一致率を比べる

### 5.3 後回しにした細かい不具合

それぞれ、失敗するテストを先に書いてから直す。

- [ ] 単重マスタのサイズにダッシュの異体字（`ー` `−` `‐` `–`）があると照合できない → `size_key` で記号の後ろの区切りをまとめてそろえる（`master.py` の重複チェックも同じキーなので一緒に直る）
- [ ] 作り直すときに元の PDF のページが減っていると、`insert_pdf` が黙って最後のページを入れる → `_raw.json` に元の PDF のハッシュかページ数を記録し、`merge_pages` の前に照合して合わなければ PDF を作らない
- [ ] 読み取り中に追加された PDF が結果から黙って抜ける → `read_folder` で最初に取った PDF の一覧を最後まで使う
- [ ] Mac の `._*.pdf` などの隠しファイルがエラー行になる → `list_pdfs` で `.` で始まる名前を除く
- [ ] xlsx の保存に失敗しても「完了」と表示する → `RunResult.errors` があるときは「一部の出力ができませんでした」と表示し、「xlsx を開く」を押せなくする
- [ ] 作り直しの最中にキャンセルボタンが押せるが効かない → 作り直しの間はキャンセルボタンを押せなくする
- [ ] 設定画面の「接続を確かめる」が最大 15 秒画面を止め、キャッシュで成功したときも「取得できました」と出る → `MasterWorker` で別スレッドにし、キャッシュのときは警告を表示する

### 5.4 配る準備

- [ ] 5.1 を直してから Mac 用をビルドし、zip にする（README の「配布」、コマンドは下）
- [ ] 使う人の PC が Intel の Mac か確認する。必要なら Rosetta を入れて Intel 用を別にビルドする
- [ ] Windows 用: GitHub に非公開リポジトリを作る前に、履歴に入っている社外秘のファイル（`20261014084620.pdf`、`ミルシート他表紙類2025.xlsx`、`sample_raw.json`）を外した新しい履歴を作る → push → タグ `v1.0.0` で Actions を動かす → 依頼主の PC で起動・読み取りを確かめる
- [ ] Gemini の API キーの配り方（全員で 1 つを共有するか、各自で作るか）を決める
- [ ] （任意）単重マスタの URL を配る版に最初から入れておく

```bash
.venv/bin/pyinstaller --noconfirm --windowed --name ミルシート読み取り --add-data "millsheet/unit_weights.json:millsheet" main.py
ditto -c -k --keepParent "dist/ミルシート読み取り.app" "dist/ミルシート読み取り-mac.zip"
```

### 5.5 依頼主に確認すること（SPEC 14 章の残り）

- [ ] 重量の考え方: 単重から出す理論重量（今の作り）でよいか、証明書の質量の按分にしたいか
- [ ] 重量の端数（今は整数に四捨五入）
- [ ] 丸数字が無いページの行の扱い（今は出力し、要確認。並び順は他の行と同じ規則なので先頭に来ることもある）
- [ ] 単重マスタに無い寸法が出たとき、誰がスプレッドシートに登録するか
- [ ] 単重マスタの誤りらしき値（`FB-3×32`、`□-11×11×1.6`、`□-500×500×11`）を直すか
- [ ] 会社の Google Workspace で、スプレッドシートを「リンクを知っている全員」に共有できるか

### 5.6 不要なファイルの整理

- [ ] ルートの `unit_weights.json`・`sample_raw.json`・`20261014084620.pdf` と `scripts/convert_fixtures.py` を消すか決める（アプリは使っていない。変換は済んでいる）。消す場合は README の「開発」の案内も直す
- [ ] 手元で削除済みの `ミルシート他表紙類2025.xlsx` の削除をコミットするか決める
- [ ] `feat/millsheet-app` を `main` にマージするか決める

### 5.7 追加の依頼（2026-10-19）

#### ビルド

- [ ] Windows 用をビルドし、起動・読み取りを確かめる（手順は 5.4）
- [ ] Intel の Mac 用をビルドし、起動・読み取りを確かめる（Apple シリコン用とは別の `.app`。GitHub Actions に `macos-13` などの Intel のランナーを足すか、Rosetta 上の x86_64 の Python でビルドする）

#### 入力: PDF ファイル単体・複数ページの PDF も受け付ける

- [ ] フォルダだけでなく、PDF ファイル 1 つ・複数の PDF ファイルのドロップ／選択を受け付ける（`DropArea`・`pipeline.run`・`extract.list_pdfs` / `read_folder`）
- [ ] 何ページもつながった PDF（スキャナーでまとめて取り込んだもの）を、ページごとに読み取る。今の 1 ページずつ送る作りのままでよいか、ページ数が多いときのキャッシュ・進み具合の表示・`PageEntry.file` の表記を確かめる
- [ ] 出力フォルダ名の初期値（今はフォルダ名）を、ファイルを渡したときはファイル名から作る

#### 重量: 全材種を「質量 ÷ 員数 × 丸数字」で出す

4 章の「重量」の決定と、5.5 の 1 つ目の確認を置き換える。

- [ ] 重量 = 証明書の質量（`mass_kg`）÷ 員数（`printed_qty`）× 丸数字（`circled_qty`）にする（PL 以外も）。質量か員数が読めないときは重量を空にし、要確認にする
- [ ] 単重マスタにその寸法があるときは、「長さ × 単重」で 1 本あたりの重さを出し、上の 1 本あたりの重さ（質量 ÷ 員数）と比べる（ずれの許容は今の 5% を引き継ぐか決める）
- [ ] 比べて合わない、またはマスタに無いなどで比べられなかったときは要確認にし、xlsx の確認理由に「証明書の質量に間違いがないか確かめてください」という趣旨の文言を書く（`normalize.py` の `R_*` に足す。今の `R_MASS_DIFF`・`R_NO_MASTER`・`R_PL_NO_PRINTED` の扱いも見直す）
- [ ] `normalize.py` のテストと、受け入れ基準の正解表（`sample_raw.json` から作るもの）を新しい計算に合わせて直す

#### 証明書ではない書類を無視する

`検査証明書_分割_100`（121 ページ）のうち 20 ページが証明書ではない。4 種類ある。

| 種類 | 見た目 | ページ |
|---|---|---|
| 出荷票 | 「出荷予定日」「出荷【ミルシート 部】」の表。表題に「ミルシート」とあるので紛らわしい | p007・p012・p014・p016 |
| 材料明細表 | 鋼材店の納品明細（規格・品種・寸法・長さ・員数・重量）。横向きのものもある | p009・p018・p024・p032 |
| 出荷一覧 | 「工事名」の下に「出荷日・メーカー・材質・本数・鋼ナンバー」だけの表 | p042・p046・p049・p054 |
| 切断リスト | 加工業者の「鋼番・商品・サイズ・長さ・本数」「製品長さ」の表。手書きの丸・「2本」が書かれていることがある。横向き・ほぼ空のものもある | p067〜p072・p103・p104 |

証明書の下に小さな送り状が一緒に写っているページ（p058・p062・p063・p081・p082・p099 など）は証明書として読む。

- [ ] `schema.py` の `PageResult` に、`is_certificate` の前に `page_type`（`"検査証明書" | "出荷票" | "材料明細表" | "出荷一覧" | "切断リスト" | "その他"`）を足し、`is_certificate` は `page_type == "検査証明書"` のときだけ true と説明する
- [ ] `prompt.py` の「送付状・表紙など」を、検査証明書の見分け方（化学成分・機械的性質の欄がある、メーカーの発行）と上の 4 種類の説明に替え、`PROMPT_VERSION` を上げる
- [ ] 121 ページを流し、上の 20 ページだけが `is_certificate=false` になること（101 ページの証明書を落としていないこと）を確かめる
- [ ] 証明書ではないページを、今のように xlsx の最後に「証明書でない」の行として出し続けるか、xlsx・PDF から外すかを決める

## 6. 第 2 段階（後で検討）

- **出力を Google ドライブ（共有ドライブ）に直接上げる**: 各自が会社の Google アカウントでログインする方式（OAuth）。組織で 1 回、Google Cloud で「Drive API を有効化」「OAuth 同意画面を『内部』で作成」「デスクトップ アプリ用の OAuth クライアント ID を作成」が必要。アプリ側は `millsheet/export/` に Exporter を足し、ローカルの出力は保険として残す（SPEC 12.5、16 章）
- **確認画面**（ページの画像と読み取り結果を並べ、人が直してから出力する）: 今回は作らないと決めた（SPEC 16 章）
- **画像ファイル（jpg・png）での入力**: 今は PDF だけを読む
