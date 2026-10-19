import shutil
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtCore import Qt

from gui.main_window import MainWindow
from gui.settings_dialog import SettingsDialog
from millsheet.settings import get_secret, load_settings


def test_main_window_opens(qtbot):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    assert w.run_button.isEnabled() is False          # フォルダと出力先が決まるまで押せない


def test_main_window_enables_run(qtbot, tmp_path):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "現場A").mkdir()
    w.set_sources([tmp_path / "現場A"])
    assert w.run_button.isEnabled()
    # 設定の出力先が空欄なら PDF のフォルダの隣。同じ名前にならないよう「_出力」を付ける
    assert w.output_name_edit.text() == "現場A_出力" and w.output_dir() == tmp_path / "現場A_出力"


def test_output_folder_uses_settings_base(qtbot, tmp_path):
    from millsheet.settings import Settings, save_settings
    save_settings(Settings(output_path=str(tmp_path / "出力")))
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "現場A").mkdir()
    w.set_sources([tmp_path / "現場A"])
    assert w.output_name_edit.text() == "現場A"
    w.output_name_edit.setText("2026-10 現場A")
    assert w.output_dir() == tmp_path / "出力/2026-10 現場A"


def test_invalid_folder_name_disables_run(qtbot, tmp_path):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path])
    for bad in ("", "a/b", "a:b", "..", "  "):
        w.output_name_edit.setText(bad)
        assert not w.run_button.isEnabled(), bad


def test_output_inside_source_folder_is_refused(qtbot, tmp_path):
    from millsheet.settings import Settings, save_settings
    (tmp_path / "A").mkdir()
    save_settings(Settings(output_path=str(tmp_path / "A")))
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path / "A"])
    assert not w.run_button.isEnabled() and "PDF のフォルダの中" in w.output_path_label.text()


def test_settings_dialog_saves_without_writing_keys_to_file(qtbot, data_dir):
    d = SettingsDialog(); qtbot.addWidget(d)
    d.gemini_key_edit.setText("GKEY123"); d.output_path_edit.setText(str(data_dir / "出力"))
    d.accept()
    assert get_secret("gemini_api_key") == "GKEY123"
    assert load_settings().output_path == str(data_dir / "出力")
    assert "GKEY123" not in (data_dir / "settings.json").read_text("utf-8")


def test_settings_dialog_blank_key_keeps_existing(qtbot):
    from millsheet.settings import set_secret
    set_secret("gemini_api_key", "OLD")
    d = SettingsDialog(); qtbot.addWidget(d)
    d.accept()
    assert get_secret("gemini_api_key") == "OLD"


def test_settings_dialog_has_no_unit_weight_master(qtbot):
    d = SettingsDialog(); qtbot.addWidget(d)
    assert not hasattr(d, "sheet_url_edit") and not hasattr(d, "test_button")






def test_run_worker_reports_friendly_error(qtbot, tmp_path):
    from gui.worker import RunWorker
    from millsheet.settings import Settings
    w = RunWorker(sources=[tmp_path], out_dir=tmp_path / "o", settings=Settings(),
                  gemini_key="")
    with qtbot.waitSignal(w.failed, timeout=10000) as sig:
        w.start()
    assert "Gemini の API キー" in sig.args[0]


def test_review_list_copy(qtbot):
    from PySide6.QtGui import QGuiApplication
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.review_list.addItems(["a.pdf の 1 ページ目", "b.pdf の 2 ページ目"])
    w.review_list.selectAll()
    w.copy_selected_reviews()
    assert QGuiApplication.clipboard().text() == "a.pdf の 1 ページ目\nb.pdf の 2 ページ目"




# I4
def test_new_folder_updates_auto_output(qtbot, tmp_path):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "A").mkdir(); (tmp_path / "B").mkdir()
    w.set_sources([tmp_path / "A"]); w.set_sources([tmp_path / "B"])
    assert w.output_name_edit.text() == "B_出力"


def test_user_chosen_output_is_kept(qtbot, tmp_path):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "A").mkdir(); (tmp_path / "B").mkdir()
    w.set_sources([tmp_path / "A"]); w.output_name_edit.setText("自分で付けた名前")
    w.set_sources([tmp_path / "B"])
    assert w.output_name_edit.text() == "自分で付けた名前"


def test_existing_output_asks_before_overwrite(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    (tmp_path / "A").mkdir(); (tmp_path / "A_出力").mkdir(); (tmp_path / "A_出力/A_出力.xlsx").write_text("x")
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path / "A"])
    asked = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "question", asked)
    w._start_run()
    assert asked.called and w.worker is None


def test_output_base_chosen_on_main_window_is_remembered(qtbot, tmp_path):
    from millsheet.settings import load_settings
    (tmp_path / "現場A").mkdir()
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path / "現場A"])
    w.set_output_base(tmp_path / "出力")
    assert w.output_dir() == tmp_path / "出力/現場A"     # PDF の隣ではなくなったので「_出力」は付けない
    assert load_settings().output_path == str(tmp_path / "出力")
    assert str(tmp_path / "出力") in w.output_base_label.text()
    w2 = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w2)
    assert str(tmp_path / "出力") in w2.output_base_label.text()


def test_output_base_label_when_unset(qtbot):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    assert "PDF のフォルダの隣" in w.output_base_label.text()




def _drag_events(*paths):
    from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    return mime, enter, drop


def test_drop_is_reported_as_accepted_copy(qtbot, tmp_path):
    """Mac で「受け取った」と返さないと、ドラッグしたアイコンが元の場所へ戻るアニメーションになる。"""
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    mime, _, drop = _drag_events(tmp_path)   # mime は保持しておく（解放されると落ちる）
    drop.ignore()
    w.drop.dropEvent(drop)
    assert drop.isAccepted() and drop.dropAction() == Qt.DropAction.CopyAction
    assert w.sources == [tmp_path]


def test_drop_area_highlights_while_dragging(qtbot, tmp_path):
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    from PySide6.QtGui import QDragLeaveEvent
    mime, enter, drop = _drag_events(tmp_path)
    w.drop.dragEnterEvent(enter)
    assert enter.isAccepted() and w.drop.property("dragging") is True
    w.drop.dragLeaveEvent(QDragLeaveEvent())
    assert w.drop.property("dragging") is False
    w.drop.dragEnterEvent(enter); w.drop.dropEvent(drop)
    assert w.drop.property("dragging") is False


def test_non_pdf_file_drop_is_refused(qtbot, tmp_path):
    (tmp_path / "a.txt").write_text("x")
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    mime, enter, _ = _drag_events(tmp_path / "a.txt")
    enter.ignore()
    w.drop.dragEnterEvent(enter)
    assert not enter.isAccepted() and w.drop.property("dragging") is not True


# PDF ファイル単体・複数・フォルダと混ぜたもの
def test_single_pdf_file_outputs_next_to_it(qtbot, tmp_path):
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "scan/20261019.pdf", 2)
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path / "scan/20261019.pdf"])
    assert w.run_button.isEnabled() and str(tmp_path / "scan/20261019.pdf") in w.source_label.text()
    assert w.output_name_edit.text() == "20261019_出力" and w.output_dir() == tmp_path / "scan/20261019_出力"


def test_several_files_are_named_after_the_first(qtbot, tmp_path):
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "A/a.pdf", 1); make_pdf(tmp_path / "B/b.pdf", 1)
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path / "A/a.pdf", tmp_path / "B/b.pdf"])
    assert "a.pdf ほか 1 件" in w.source_label.text()
    assert w.output_name_edit.text() == "aほか_出力" and w.output_dir() == tmp_path / "aほか_出力"


def test_output_inside_a_given_folder_is_refused_when_mixed(qtbot, tmp_path):
    from millsheet.settings import Settings, save_settings
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "A/1.pdf", 1); make_pdf(tmp_path / "b.pdf", 1)
    save_settings(Settings(output_path=str(tmp_path / "A")))
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_sources([tmp_path / "A", tmp_path / "b.pdf"])
    assert not w.run_button.isEnabled() and "PDF のフォルダの中" in w.output_path_label.text()


def test_drop_accepts_files_and_folders_together(qtbot, tmp_path):
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "A/1.pdf", 1); make_pdf(tmp_path / "b.pdf", 1)
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    mime, enter, drop = _drag_events(tmp_path / "A", tmp_path / "b.pdf")
    w.drop.dragEnterEvent(enter); w.drop.dropEvent(drop)
    assert enter.isAccepted() and drop.isAccepted() and w.sources == [tmp_path / "A", tmp_path / "b.pdf"]


def test_drop_refuses_non_pdf_file(qtbot, tmp_path):
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "a.pdf", 1); (tmp_path / "表.xlsx").write_text("x")
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    mime, enter, _ = _drag_events(tmp_path / "a.pdf", tmp_path / "表.xlsx")
    w.drop.dragEnterEvent(enter)
    assert not enter.isAccepted() and w.sources == []


def test_run_worker_gets_the_chosen_sources(qtbot, tmp_path, monkeypatch):
    from gui import main_window
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "a.pdf", 1); make_pdf(tmp_path / "b.pdf", 1)
    created = Mock()
    monkeypatch.setattr(main_window, "RunWorker", created)
    w = MainWindow(open_folder_on_finish=False); qtbot.addWidget(w)
    monkeypatch.setattr(w, "_start", Mock())
    w.set_sources([tmp_path / "a.pdf", tmp_path / "b.pdf"])
    w._start_run()
    assert created.call_args.kwargs["sources"] == [tmp_path / "a.pdf", tmp_path / "b.pdf"]
