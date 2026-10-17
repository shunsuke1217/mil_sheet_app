"""AI に返させる JSON（SPEC 6.1）と、ページ単位の読み取り結果。"""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


class Line(BaseModel):
    commodity_raw: str | None   # ミルシートの品名欄の表記をそのまま（例: H形鋼, CHANNELS, 軽量形鋼）。品名は AI ではなくアプリが判定する（6.4 節）
    grade: str | None           # 材質の記号のみ（SS400, SN490C, SSC400 など）。"JIS G3101" は含めない
    size_raw: str | None        # 寸法を印字どおりに（例: 200X100X5.5/8）
    length_raw: str | None      # 長さを印字どおり単位も含めて（例: 11.5M, 5.500m, 12,000, 5.5）
    circle_status: Literal["あり", "なし", "読めない"]  # この行の手書きの丸数字の状態
    circled_qty: int | None     # 丸数字の値。circle_status が「あり」のときだけ入れ、それ以外は null
    printed_qty: int | None     # 印字された本数・員数
    mass_kg: float | None       # 印字された質量(kg)
    uncertain: bool             # 読み取りに自信が無い値があれば true
    note: str | None            # 気になった点


class PageResult(BaseModel):
    is_certificate: bool        # 鋼材の検査証明書なら true
    stamp_valid_qty: int | None # 押印「○印 N 本のみ有効」の N
    lines: list[Line]


@dataclass
class PageEntry:
    file: str                  # 読み込んだフォルダからの相対パス（"/" 区切り）
    page_no: int | None        # 1 始まり。PDF 自体が開けなかったときは None
    result: PageResult | None  # 失敗したときは None
    error: str | None = None   # 失敗の理由（画面と確認理由に出す日本語）
