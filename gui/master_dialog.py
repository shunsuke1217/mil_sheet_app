"""単重マスタの一覧（SPEC 7.5）。表示だけで、編集はスプレッドシートで行う。"""
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from millsheet.master import Master

ALL = "すべての材種"


class MasterDialog(QDialog):
    def __init__(self, master: Master, parent: QWidget | None = None, *, sheet_url: str = "",
                 reload: Callable[[], Master | None] | None = None):
        super().__init__(parent)
        self.setWindowTitle("単重マスタ")
        self.resize(560, 640)
        self.sheet_url = sheet_url
        self.reload = reload

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("サイズで検索（例: 200×200）")
        self.category_combo = QComboBox()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["材種", "サイズ", "単重(kg/m)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.info = QLabel()

        open_button = QPushButton("スプレッドシートを開く")
        open_button.setEnabled(bool(sheet_url))
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.sheet_url)))
        reload_button = QPushButton("読み直す")
        reload_button.setEnabled(reload is not None)
        reload_button.clicked.connect(self._reload)

        top = QHBoxLayout()
        top.addWidget(self.search_edit)
        top.addWidget(self.category_combo)
        bottom = QHBoxLayout()
        bottom.addWidget(self.info)
        bottom.addStretch()
        bottom.addWidget(open_button)
        bottom.addWidget(reload_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addLayout(bottom)

        self.search_edit.textChanged.connect(self._apply_filter)
        self.category_combo.currentTextChanged.connect(self._apply_filter)
        self.set_master(master)

    def set_master(self, master: Master) -> None:
        self.table.setRowCount(len(master.entries))
        for row, e in enumerate(master.entries):
            for col, v in enumerate((e.category, e.size, f"{e.unit_weight:g}")):
                self.table.setItem(row, col, QTableWidgetItem(v))
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItems([ALL] + sorted({e.category for e in master.entries}))
        self.category_combo.blockSignals(False)
        meta = master.meta()
        self.info.setText(f"{meta['件数']} 件（{meta['取得元']}、{meta['取得日時']}）")
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self.search_edit.text().strip().replace("x", "×").replace("X", "×")
        cat = self.category_combo.currentText()
        for row in range(self.table.rowCount()):
            category, size = self.table.item(row, 0).text(), self.table.item(row, 1).text()
            visible = (cat in ("", ALL) or category == cat) and (not q or q in size)
            self.table.setRowHidden(row, not visible)

    def visible_row_count(self) -> int:
        return sum(not self.table.isRowHidden(r) for r in range(self.table.rowCount()))

    def _reload(self) -> None:
        master = self.reload()
        if master is not None:
            self.set_master(master)
