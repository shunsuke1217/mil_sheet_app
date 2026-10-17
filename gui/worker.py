"""読み取り・作り直し・マスタ取得を別スレッドで行う（画面を固めない）。"""
import logging
import threading
from typing import Literal

from PySide6.QtCore import QThread, Signal

from millsheet import paths
from millsheet.extract import Cancelled, ReaderAuthError
from millsheet.master import MasterFetchError, MasterValidationError, fetch_master
from millsheet.pipeline import rebuild, run

log = logging.getLogger(__name__)

EXPECTED_ERRORS = (MasterFetchError, MasterValidationError, ReaderAuthError, ValueError, FileNotFoundError)


def friendly_error(e: Exception) -> str:
    if isinstance(e, Cancelled):
        return "キャンセルしました（読み取り済みのページは保存してあるので、次は続きから読み取ります）"
    if isinstance(e, EXPECTED_ERRORS):
        return str(e)
    log.exception("予期しないエラー")
    return f"予期しないエラーが起きました。ログを確認してください: {paths.logs_dir()}"


class RunWorker(QThread):
    progress = Signal(str, int, int)      # 文言, 全体の何ページ目, 全ページ数
    finished_ok = Signal(object)          # RunResult
    failed = Signal(str)

    def __init__(self, mode: Literal["run", "rebuild"], **pipeline_kwargs):
        super().__init__()
        self.mode = mode
        self.kwargs = pipeline_kwargs
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _on_progress(self, file: str, page: int, file_pages: int, done: int, total: int) -> None:
        self.progress.emit(f"{file} {page}/{file_pages} ページ目を読み取りました", done, total)

    def run(self) -> None:
        try:
            if self.mode == "run":
                result = run(**self.kwargs, on_progress=self._on_progress, cancel=self._cancel)
            else:
                result = rebuild(**self.kwargs)
            self.finished_ok.emit(result)
        except Exception as e:  # 画面に日本語で出し、詳しくはログへ
            self.failed.emit(friendly_error(e))


class MasterWorker(QThread):
    finished_ok = Signal(object, list)    # Master, 警告
    failed = Signal(str)

    def __init__(self, url: str, sheet_name: str, api_key: str):
        super().__init__()
        self.args = (url, sheet_name, api_key)

    def run(self) -> None:
        try:
            master, warnings = fetch_master(*self.args)
            self.finished_ok.emit(master, warnings)
        except Exception as e:
            self.failed.emit(friendly_error(e))
