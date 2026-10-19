"""設定画面（SPEC 13章）。API キーは keyring にだけ保存する。"""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from millsheet.settings import get_secret, load_settings, save_settings, set_secret


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setMinimumWidth(560)
        self.settings = load_settings()

        self.gemini_key_edit = self._key_edit("gemini_api_key")
        self.output_path_edit = QLineEdit(self.settings.output_path)
        self.output_path_edit.setPlaceholderText("空欄なら PDF のフォルダの隣か、PDF ファイルと同じフォルダ（Google ドライブの同期フォルダも選べます）")
        browse = QPushButton("参照…")
        browse.clicked.connect(self._choose_output_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_path_edit)
        out_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("Gemini の API キー", self.gemini_key_edit)
        form.addRow("出力フォルダを作る場所", out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _key_edit(self, name: str) -> QLineEdit:
        e = QLineEdit()
        e.setEchoMode(QLineEdit.EchoMode.Password)
        e.setPlaceholderText("保存済み（変更するときだけ入力）" if get_secret(name) else "未設定")
        return e

    def _choose_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "出力フォルダを作る場所", self.output_path_edit.text())
        if d:
            self.output_path_edit.setText(d)

    def accept(self) -> None:
        if self.gemini_key_edit.text().strip():
            set_secret("gemini_api_key", self.gemini_key_edit.text().strip())
        self.settings.output_path = self.output_path_edit.text().strip()
        save_settings(self.settings)
        super().accept()
