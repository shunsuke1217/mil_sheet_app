"""AI に返させる JSON（SPEC 6.1）と、ページ単位の読み取り結果。"""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class Line(BaseModel):
    commodity_raw: str | None = Field(description=(
        "品名欄（品名・品種・COMMODITY など）の表記を印字どおりに写す（例: H形鋼, CHANNELS, 軽量形鋼）。"
        "本表と別表の両方に品名があれば \" / \" でつないで両方入れる。品名の判定はしない"))
    grade: str | None = Field(description=(
        "材質の記号だけ（例: SS400, SN490C, SSC400）。\"JIS G3101\" などの規格番号は含めない"))
    size_raw: str | None = Field(description=(
        "寸法を印字どおりに写す（例: 200X100X5.5/8）。並べ替え・換算はしない"))
    length_raw: str | None = Field(description=(
        "長さを印字どおり、単位も含めて写す（例: 11.5M, 5.500m, 12000, 5.5）。換算はしない。数値のカンマは除く"))
    circle_status: Literal["あり", "なし", "読めない"] = Field(description=(
        "この行の、赤色の手書きの丸数字の状態（黒色の印字・書き込みは丸数字として扱わない）。丸数字があり数字が読める → あり。"
        "丸はあるが、かすれ・押印の重なりなどで数字が読めない → 読めない。丸数字が書かれていない → なし"))
    circled_qty: int | None = Field(description=(
        "赤色の手書きの丸数字の値（この現場で使う本数）。circle_status が「あり」のときだけ入れ、それ以外は null"))
    printed_qty: int | None = Field(description="印字された本数・員数。数値のカンマは除く")
    mass_kg: float | None = Field(description="印字された質量(kg)。数値のカンマは除く")
    uncertain: bool = Field(description="この行に読み取りに自信が無い値があれば true。読めずに null にした値があるときも true")
    note: str | None = Field(description="気になった点があれば短く書く。なければ null")


class PageResult(BaseModel):
    is_certificate: bool = Field(description=(
        "表題に「検査証明書」とあり、化学成分と機械的性質の欄があるページなら true。"
        "それ以外（出荷票・材料明細表・切断リスト・送付状など）は false にし、lines は空にする"))
    stamp_valid_qty: int | None = Field(description=(
        "「本証明書は○印 N 本のみ有効です」という押印の手書きの N。押印が無い・読めないときは null"))
    lines: list[Line] = Field(description="赤色の手書きの丸数字が付いた行（数字が読めない丸数字の行も含む）")


@dataclass
class PageEntry:
    file: str                  # 読み込んだフォルダからの相対パス（"/" 区切り）
    page_no: int | None        # 1 始まり。PDF 自体が開けなかったときは None
    result: PageResult | None  # 失敗したときは None
    error: str | None = None   # 失敗の理由（画面と確認理由に出す日本語）
