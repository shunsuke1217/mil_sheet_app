"""設定画面（SPEC 13章）。API キーは keyring にだけ保存する。"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from millsheet.master import MasterFetchError, MasterValidationError, export_bundled_csv, fetch_master
from millsheet.settings import get_secret, load_settings, save_settings, set_secret


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setMinimumWidth(560)
        self.settings = load_settings()

        self.gemini_key_edit = self._key_edit("gemini_api_key")
        self.sheet_url_edit = QLineEdit(self.settings.sheet_url)
        self.sheet_url_edit.setPlaceholderText("単重のタブを開いた状態のアドレスを貼る（https://docs.google.com/spreadsheets/d/…）")
        sheet_hint = QLabel("スプレッドシートの共有設定を「リンクを知っている全員」（閲覧者）にしてください。API キーは不要です。")
        sheet_hint.setWordWrap(True)
        sheet_hint.setStyleSheet("color: gray;")
        self.output_path_edit = QLineEdit(self.settings.output_path)
        self.output_path_edit.setPlaceholderText("xlsx を保存するフォルダ（空欄なら PDF のフォルダの隣）")
        browse = QPushButton("参照…")
        browse.clicked.connect(self._choose_output_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_path_edit)
        out_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("Gemini の API キー", self.gemini_key_edit)
        form.addRow("単重マスタの URL", self.sheet_url_edit)
        form.addRow("", sheet_hint)
        form.addRow("出力先のフォルダ", out_row)

        self.test_button = QPushButton("接続を確かめる")
        self.test_button.clicked.connect(self._test_connection)
        csv_button = QPushButton("初期マスタを CSV で書き出す")
        csv_button.clicked.connect(self._export_csv)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tools = QHBoxLayout()
        tools.addWidget(self.test_button)
        tools.addWidget(csv_button)
        tools.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(tools)
        layout.addWidget(self.test_result)
        layout.addWidget(buttons)

    def _key_edit(self, name: str) -> QLineEdit:
        e = QLineEdit()
        e.setEchoMode(QLineEdit.EchoMode.Password)
        e.setPlaceholderText("保存済み（変更するときだけ入力）" if get_secret(name) else "未設定")
        return e

    def _choose_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "出力先のフォルダ", self.output_path_edit.text())
        if d:
            self.output_path_edit.setText(d)

    def _test_connection(self) -> None:
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            master, warnings = fetch_master(self.sheet_url_edit.text())
            text = f"{len(master.entries)} 件の単重を取得できました"
            self.test_result.setText("\n".join([text, *warnings]))
        except (MasterFetchError, MasterValidationError) as e:
            self.test_result.setText(str(e))
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "初期マスタを CSV で書き出す", "単重マスタ.csv", "CSV (*.csv)")
        if path:
            export_bundled_csv(Path(path))
            QMessageBox.information(self, "書き出しました",
                                    f"{path}\nを書き出しました。スプレッドシートの「ファイル → インポート」で読み込んでください。")

    def accept(self) -> None:
        if self.gemini_key_edit.text().strip():
            set_secret("gemini_api_key", self.gemini_key_edit.text().strip())
        self.settings.sheet_url = self.sheet_url_edit.text().strip()
        self.settings.output_path = self.output_path_edit.text().strip()
        save_settings(self.settings)
        super().accept()
