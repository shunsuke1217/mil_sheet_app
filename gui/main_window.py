"""メイン画面（SPEC 13章）。ロジックは持たず、pipeline を別スレッドで呼ぶだけ。"""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from gui.master_dialog import MasterDialog
from gui.settings_dialog import SettingsDialog
from gui.worker import MasterWorker, RunWorker
from millsheet.master import Master
from millsheet.pipeline import RunResult, outputs_for, review_messages
from millsheet.settings import get_secret, load_settings


class DropArea(QLabel):
    """PDF のフォルダをドロップする枠。"""

    def __init__(self, on_folder):
        super().__init__("ここに PDF のフォルダをドロップ")
        self.on_folder = on_folder
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(110)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QLabel { border: 2px dashed #999; border-radius: 8px; font-size: 15px; }")

    def _folder(self, event) -> Path | None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            return Path(urls[0].toLocalFile())
        return None

    def dragEnterEvent(self, event):
        if self._folder(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        folder = self._folder(event)
        if folder:
            self.on_folder(folder)


class MainWindow(QMainWindow):
    def __init__(self, fetch_on_start: bool = True):
        super().__init__()
        self.setWindowTitle("ミルシート読み取り")
        self.resize(820, 680)
        self.source_dir: Path | None = None
        self.master: Master | None = None
        self.result: RunResult | None = None
        self.worker = None
        self.master_worker = None

        self.drop = DropArea(self.set_source_dir)
        choose = QPushButton("フォルダを選ぶ…")
        choose.clicked.connect(self._choose_folder)
        self.source_label = QLabel("フォルダが選ばれていません")

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("出力する xlsx")
        self.output_edit.textChanged.connect(self._update_buttons)
        browse = QPushButton("参照…")
        browse.clicked.connect(self._choose_output)

        self.run_button = QPushButton("読み取りを実行")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self._start_run)
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.progress = QProgressBar()
        self.status = QLabel()

        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("color: #b45309;")
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.review_list = QListWidget()
        self.review_list.setWordWrap(True)
        self.review_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        QShortcut(QKeySequence.StandardKey.Copy, self.review_list, self.copy_selected_reviews)

        self.open_xlsx = QPushButton("xlsx を開く")
        self.open_pdf = QPushButton("PDF を開く")
        self.open_folder = QPushButton("フォルダを開く")
        self.open_sheet = QPushButton("スプレッドシートを開く")
        self.rebuild_button = QPushButton("マスタを読み直して作り直す")
        self.open_xlsx.clicked.connect(lambda: self._open(self.result.outputs.xlsx))
        self.open_pdf.clicked.connect(lambda: self._open(self.result.outputs.pdf))
        self.open_folder.clicked.connect(lambda: self._open(self.result.outputs.xlsx.parent))
        self.open_sheet.clicked.connect(self._open_sheet)
        self.rebuild_button.clicked.connect(self._start_rebuild)

        self.master_label = QLabel("単重マスタ: 未取得")
        master_button = QPushButton("単重マスタ一覧")
        master_button.clicked.connect(self._show_master)
        settings_button = QPushButton("設定")
        settings_button.clicked.connect(self._show_settings)

        src_row = QHBoxLayout(); src_row.addWidget(self.source_label, 1); src_row.addWidget(choose)
        out_row = QHBoxLayout(); out_row.addWidget(QLabel("出力先")); out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(browse)
        run_row = QHBoxLayout(); run_row.addWidget(self.run_button); run_row.addWidget(self.cancel_button)
        run_row.addWidget(self.progress, 1)
        open_row = QHBoxLayout()
        for b in (self.open_xlsx, self.open_pdf, self.open_folder, self.open_sheet, self.rebuild_button):
            open_row.addWidget(b)
        open_row.addStretch()
        master_row = QHBoxLayout(); master_row.addWidget(self.master_label, 1); master_row.addWidget(master_button)
        master_row.addWidget(settings_button)

        layout = QVBoxLayout()
        layout.addWidget(self.drop)
        layout.addLayout(src_row)
        layout.addLayout(out_row)
        layout.addLayout(run_row)
        layout.addWidget(self.status)
        layout.addWidget(self.notice)
        layout.addWidget(QLabel("要確認の一覧（選んで Ctrl+C / ⌘C でコピーできます）"))
        layout.addWidget(self.review_list, 1)
        layout.addLayout(open_row)
        layout.addLayout(master_row)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self._update_buttons()
        if fetch_on_start:
            self.refresh_master()

    # 入力
    def set_source_dir(self, folder: Path) -> None:
        self.source_dir = Path(folder)
        self.source_label.setText(str(self.source_dir))
        if not self.output_edit.text():
            out_dir = Path(load_settings().output_path or self.source_dir.parent)
            self.set_output_path(out_dir / f"{self.source_dir.name}.xlsx")
        self._update_buttons()

    def set_output_path(self, path: Path) -> None:
        path = Path(path)
        if path.suffix.lower() != ".xlsx":
            path = path.with_name(path.name + ".xlsx")
        self.output_edit.setText(str(path))

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "PDF のフォルダを選ぶ")
        if d:
            self.set_source_dir(Path(d))

    def _choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "出力する xlsx", self.output_edit.text(), "Excel (*.xlsx)")
        if path:
            self.set_output_path(Path(path))

    def _busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _update_buttons(self) -> None:
        busy = self._busy()
        self.run_button.setEnabled(not busy and self.source_dir is not None and bool(self.output_edit.text()))
        self.cancel_button.setEnabled(busy)
        has = self.result is not None
        self.open_xlsx.setEnabled(has and not busy)
        self.open_pdf.setEnabled(has and not busy and self.result.outputs.pdf is not None)
        self.open_folder.setEnabled(has and not busy)
        out = self.output_edit.text()
        self.rebuild_button.setEnabled(not busy and bool(out) and outputs_for(Path(out)).raw.exists())
        self.open_sheet.setEnabled(bool(load_settings().sheet_url))

    # 実行
    def _pipeline_kwargs(self) -> dict:
        return dict(settings=load_settings(), google_key=get_secret("google_api_key") or "",
                    xlsx=Path(self.output_edit.text()))

    def _start_run(self) -> None:
        kw = self._pipeline_kwargs()
        self._start(RunWorker("run", source_dir=self.source_dir, gemini_key=get_secret("gemini_api_key") or "", **kw))

    def _start_rebuild(self) -> None:
        kw = self._pipeline_kwargs()
        self._start(RunWorker("rebuild", raw=outputs_for(kw["xlsx"]).raw, **kw))

    def _start(self, worker: RunWorker) -> None:
        self.worker = worker
        self.review_list.clear()
        self.notice.clear()
        self.progress.setRange(0, 0)
        self.status.setText("単重マスタを確かめています…")
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._update_buttons)
        worker.start()
        self._update_buttons()

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.status.setText("キャンセルしています…（読み取り中のページが終わるまで待ちます）")

    def _on_progress(self, text: str, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText(f"{text}（全体 {done}/{total}）")

    def _on_finished(self, result: RunResult) -> None:
        self.result = result
        self.master = result.master
        self._show_master_label()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        messages = review_messages(result.records)
        self.status.setText(f"完了: {len(result.records)} 行を出力しました（要確認 {len(messages)} 件）")
        self.notice.setText("\n".join(result.warnings + result.errors))
        self.review_list.addItems(messages or ["要確認の行はありません"])

    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setText("止まりました")
        QMessageBox.warning(self, "ミルシート読み取り", message)

    # マスタ
    def refresh_master(self) -> None:
        s = load_settings()
        key = get_secret("google_api_key") or ""
        if not s.sheet_url or not key:
            self.master_label.setText("単重マスタ: 設定画面でスプレッドシートの URL と Google の API キーを入力してください")
            return
        self.master_label.setText("単重マスタ: 取得中…")
        self.master_worker = MasterWorker(s.sheet_url, s.sheet_name, key)
        self.master_worker.finished_ok.connect(self._on_master)
        self.master_worker.failed.connect(lambda m: self.master_label.setText(f"単重マスタ: {m}"))
        self.master_worker.start()

    def _on_master(self, master: Master, warnings: list) -> None:
        self.master = master
        self._show_master_label()
        if warnings:
            self.notice.setText("\n".join(warnings))

    def _show_master_label(self) -> None:
        m = self.master.meta()
        self.master_label.setText(f"単重マスタ: {m['件数']} 件（{m['取得元']}、{m['取得日時']}）")

    def _show_master(self) -> None:
        if self.master is None:
            QMessageBox.information(self, "単重マスタ", "単重マスタをまだ取得していません。設定を確かめてください。")
            return
        MasterDialog(self.master, self, sheet_url=load_settings().sheet_url, reload=self._reload_master_sync).exec()

    def _reload_master_sync(self) -> Master | None:
        from millsheet.master import MasterFetchError, MasterValidationError, fetch_master
        s = load_settings()
        try:
            self.master, warnings = fetch_master(s.sheet_url, s.sheet_name, get_secret("google_api_key") or "")
        except (MasterFetchError, MasterValidationError) as e:
            QMessageBox.warning(self, "単重マスタ", str(e))
            return None
        self._show_master_label()
        return self.master

    def _show_settings(self) -> None:
        if SettingsDialog(self).exec():
            self._update_buttons()
            self.refresh_master()

    def copy_selected_reviews(self) -> None:
        rows = sorted(self.review_list.selectedIndexes(), key=lambda i: i.row())
        QGuiApplication.clipboard().setText("\n".join(self.review_list.item(i.row()).text() for i in rows))

    def _open(self, path: Path | None) -> None:
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_sheet(self) -> None:
        QDesktopServices.openUrl(QUrl(load_settings().sheet_url))

    def closeEvent(self, event):
        if self._busy():
            self.worker.cancel()
            self.worker.wait(30000)
        super().closeEvent(event)
