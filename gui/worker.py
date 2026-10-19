"""読み取りを別スレッドで行う（画面を固めない）。"""
import logging
import threading

from PySide6.QtCore import QThread, Signal

from millsheet import paths
from millsheet.extract import Cancelled, ReaderAuthError, ReaderRequestError
from millsheet.pipeline import run

log = logging.getLogger(__name__)

EXPECTED_ERRORS = (ReaderAuthError, ReaderRequestError, ValueError, FileNotFoundError)


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

    def __init__(self, **pipeline_kwargs):
        super().__init__()
        self.kwargs = pipeline_kwargs
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _on_progress(self, file: str, page: int, file_pages: int, done: int, total: int) -> None:
        self.progress.emit(f"{file} {page}/{file_pages} ページ目を読み取りました", done, total)

    def run(self) -> None:
        try:
            result = run(**self.kwargs, on_progress=self._on_progress, cancel=self._cancel)
            self.finished_ok.emit(result)
        except Exception as e:  # 画面に日本語で出し、詳しくはログへ
            self.failed.emit(friendly_error(e))

