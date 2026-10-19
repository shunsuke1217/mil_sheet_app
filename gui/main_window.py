"""メイン画面（SPEC 13章）。ロジックは持たず、pipeline を別スレッドで呼ぶだけ。"""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from gui.settings_dialog import SettingsDialog
from gui.worker import RunWorker
from millsheet.extract import InputError, common_base, is_pdf_file
from millsheet.pipeline import RunResult, outputs_for, review_messages
from millsheet.settings import get_secret, load_settings, save_settings


INVALID_NAME_CHARS = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]


class DropArea(QLabel):
    """PDF のフォルダ・PDF ファイル（いくつでも、混ぜてもよい）をドロップする枠。
    持ってくると枠を強調し、落とすと受け取ったと返す。PDF でないファイルが混ざっていれば受け取らない。"""

    STYLE = """
        QLabel { border: 2px dashed #999; border-radius: 8px; font-size: 15px; }
        QLabel[dragging="true"] { border: 2px solid #2563eb; background: rgba(37, 99, 235, 0.08); }
    """

    def __init__(self, on_paths):
        super().__init__("ここに PDF のフォルダか PDF ファイルをドロップ（いくつでも）")
        self.on_paths = on_paths
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(110)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(self.STYLE)
        self._set_dragging(False)

    def _set_dragging(self, on: bool) -> None:
        self.setProperty("dragging", on)
        self.style().unpolish(self)   # プロパティに合わせて見た目を付け直す
        self.style().polish(self)

    def _paths(self, event) -> list[Path] | None:
        urls = event.mimeData().urls()
        if not urls or not all(u.isLocalFile() for u in urls):
            return None
        paths = [Path(u.toLocalFile()) for u in urls]
        return paths if all(p.is_dir() or (p.is_file() and is_pdf_file(p)) for p in paths) else None

    def _accept_as_copy(self, event) -> None:
        # 「コピーとして受け取った」と返す。返さないと Mac はドロップが断られたとみなし、アイコンを元の場所へ戻す
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragEnterEvent(self, event):
        if self._paths(event):
            self._accept_as_copy(event)
            self._set_dragging(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._paths(event):
            self._accept_as_copy(event)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_dragging(False)

    def dropEvent(self, event):
        self._set_dragging(False)
        paths = self._paths(event)
        if paths:
            self._accept_as_copy(event)
            self.on_paths(paths)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    def __init__(self, open_folder_on_finish: bool = True):
        super().__init__()
        self.setWindowTitle("ミルシート読み取り")
        self.resize(820, 680)
        self.sources: list[Path] = []     # 渡された PDF のフォルダ・ファイル
        self.result: RunResult | None = None
        self.worker = None
        self._auto_name = ""              # 自動で入れた名前（ユーザーが変えていなければ、渡した PDF に合わせて替える）
        self.open_folder_on_finish = open_folder_on_finish

        self.drop = DropArea(self.set_sources)
        choose = QPushButton("フォルダを選ぶ…")
        choose.clicked.connect(self._choose_folder)
        choose_files = QPushButton("ファイルを選ぶ…")
        choose_files.clicked.connect(self._choose_files)
        self.source_label = QLabel("まだ選ばれていません")

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("出力フォルダの名前")
        self.output_name_edit.textChanged.connect(self._update_buttons)
        self.output_base_label = QLabel()
        self.output_base_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        browse = QPushButton("選ぶ…")
        browse.clicked.connect(self._choose_output_base)
        self.output_path_label = QLabel()
        self.output_path_label.setWordWrap(True)
        self.output_path_label.setStyleSheet("color: gray;")

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
        self.open_xlsx.clicked.connect(lambda: self._open(self.result.outputs.xlsx))
        self.open_pdf.clicked.connect(lambda: self._open(self.result.outputs.pdf))
        self.open_folder.clicked.connect(lambda: self._open(self.result.outputs.dir))

        settings_button = QPushButton("設定")
        settings_button.clicked.connect(self._show_settings)

        src_row = QHBoxLayout(); src_row.addWidget(QLabel("読み取る PDF")); src_row.addWidget(self.source_label, 1)
        src_row.addWidget(choose); src_row.addWidget(choose_files)
        base_row = QHBoxLayout(); base_row.addWidget(QLabel("保存する場所")); base_row.addWidget(self.output_base_label, 1)
        base_row.addWidget(browse)
        out_row = QHBoxLayout(); out_row.addWidget(QLabel("出力フォルダ名")); out_row.addWidget(self.output_name_edit, 1)
        run_row = QHBoxLayout(); run_row.addWidget(self.run_button); run_row.addWidget(self.cancel_button)
        run_row.addWidget(self.progress, 1)
        open_row = QHBoxLayout()
        for b in (self.open_xlsx, self.open_pdf, self.open_folder):
            open_row.addWidget(b)
        open_row.addStretch()
        settings_row = QHBoxLayout(); settings_row.addStretch(); settings_row.addWidget(settings_button)

        layout = QVBoxLayout()
        layout.addWidget(self.drop)
        layout.addLayout(src_row)
        layout.addLayout(base_row)
        layout.addLayout(out_row)
        layout.addWidget(self.output_path_label)
        layout.addLayout(run_row)
        layout.addWidget(self.status)
        layout.addWidget(self.notice)
        layout.addWidget(QLabel("要確認の一覧（選んで Ctrl+C / ⌘C でコピーできます）"))
        layout.addWidget(self.review_list, 1)
        layout.addLayout(open_row)
        layout.addLayout(settings_row)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self._update_buttons()

    # 入力
    def set_sources(self, paths: list[Path]) -> None:
        """読み取る PDF のフォルダ・ファイルを決める（混ぜてもよい）。"""
        self.sources = [Path(p) for p in paths]
        first = self.sources[0]
        self.source_label.setText(str(first) if len(self.sources) == 1
                                  else f"{first.name} ほか {len(self.sources) - 1} 件")
        self._refresh_auto_name()
        self._update_buttons()

    def set_output_base(self, folder: Path) -> None:
        """出力フォルダを作る場所を決める。次回も同じ場所を使えるよう設定に保存する。"""
        settings = load_settings()
        settings.output_path = str(folder)
        save_settings(settings)
        self._refresh_auto_name()
        self._update_buttons()

    def _refresh_auto_name(self) -> None:
        if not self.sources:
            return
        if self.output_name_edit.text() and self.output_name_edit.text() != self._auto_name:
            return   # ユーザーが付けた名前はそのまま
        first = self.sources[0]
        name = first.stem if is_pdf_file(first) else first.name
        if len(self.sources) > 1:
            name += "ほか"
        if self._output_base() == self._default_base():
            name += "_出力"   # PDF の隣に置くので、同じ名前にならないようにする
        self.output_name_edit.setText(name)
        self._auto_name = name

    def _output_base(self) -> Path | None:
        configured = load_settings().output_path
        if configured:
            return Path(configured)
        return self._default_base()

    def _source_folders(self) -> list[Path]:
        return [p.resolve() for p in self.sources if not is_pdf_file(p)]

    def _default_base(self) -> Path | None:
        """保存する場所が未設定のときの置き場所。PDF のフォルダならその隣、PDF ファイルならそれと同じフォルダ。"""
        if not self.sources:
            return None
        try:
            base = common_base(self.sources)
        except InputError:
            return None
        return base.parent if base in self._source_folders() else base

    def output_dir(self) -> Path | None:
        base, name = self._output_base(), self.output_name_edit.text().strip()
        return base / name if base and name else None

    def _output_problem(self) -> str | None:
        name = self.output_name_edit.text().strip()
        if not name:
            return "出力フォルダの名前を入れてください"
        if name in (".", "..") or any(c in name for c in INVALID_NAME_CHARS):
            return f"フォルダの名前に次の文字は使えません: {' '.join(INVALID_NAME_CHARS)}"
        out = self.output_dir()
        if self.sources:
            try:
                common_base(self.sources)
            except InputError as e:
                return str(e)
        if out and any(out.resolve() == d or d in out.resolve().parents for d in self._source_folders()):
            return "出力フォルダが PDF のフォルダの中になっています。場所か名前を変えてください"
        return None

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "PDF のフォルダを選ぶ")
        if d:
            self.set_sources([Path(d)])

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "PDF ファイルを選ぶ（いくつでも）", "", "PDF (*.pdf *.PDF)")
        if files:
            self.set_sources([Path(f) for f in files])

    def _choose_output_base(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "出力フォルダを作る場所", str(self._output_base() or ""))
        if d:
            self.set_output_base(Path(d))

    def _busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _update_buttons(self) -> None:
        busy = self._busy()
        configured = load_settings().output_path
        self.output_base_label.setText(configured or "未設定（PDF のフォルダの隣か、PDF ファイルと同じフォルダに作ります）")
        problem = self._output_problem()
        out = self.output_dir()
        if not self.sources:
            self.output_path_label.setText("")
        else:
            self.output_path_label.setText(problem or f"出力先: {out}（この中に xlsx と PDF を作ります）")
        self.run_button.setEnabled(not busy and bool(self.sources) and problem is None)
        self.cancel_button.setEnabled(busy)
        has = self.result is not None
        self.open_xlsx.setEnabled(has and not busy)
        self.open_pdf.setEnabled(has and not busy and self.result.outputs.pdf is not None)
        self.open_folder.setEnabled(has and not busy)

    # 実行
    def _start_run(self) -> None:
        out = self.output_dir()
        if outputs_for(out).xlsx.exists() or outputs_for(out).pdf.exists():
            answer = QMessageBox.question(self, "上書きの確認",
                                          f"出力フォルダ「{out.name}」には前の結果があります。上書きしますか？\n（{out}）")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._start(RunWorker(sources=self.sources, out_dir=out, settings=load_settings(),
                              gemini_key=get_secret("gemini_api_key") or ""))

    def _start(self, worker: RunWorker) -> None:
        self.worker = worker
        self.review_list.clear()
        self.notice.clear()
        self.progress.setRange(0, 0)
        self.status.setText("読み取りの準備をしています…")
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
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        messages = review_messages(result.records)
        self.status.setText(f"完了: {len(result.records)} 行を出力しました（要確認 {len(messages)} 件）\n"
                            f"出力フォルダ: {result.outputs.dir}")
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if self.open_folder_on_finish:
            self._open(result.outputs.dir)
        self.notice.setText("\n".join(result.errors))
        self.review_list.addItems(messages or ["要確認の行はありません"])

    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setText("止まりました")
        QMessageBox.warning(self, "ミルシート読み取り", message)

    def _show_settings(self) -> None:
        if SettingsDialog(self).exec():
            self._update_buttons()

    def copy_selected_reviews(self) -> None:
        rows = sorted(self.review_list.selectedIndexes(), key=lambda i: i.row())
        QGuiApplication.clipboard().setText("\n".join(self.review_list.item(i.row()).text() for i in rows))

    def _open(self, path: Path | None) -> None:
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self._busy():
            self.worker.cancel()
            self.worker.wait(30000)
        super().closeEvent(event)
