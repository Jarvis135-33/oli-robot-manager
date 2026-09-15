from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from config import APP_CONFIG, ROBOT_CONFIG
from database.connection import DatabaseConnection
from database.repository import DanceCountRepository
from services.dance_service import DanceService
from ui.panels.dance_library_panel import DanceLibraryPanel
from ui.widgets.dance_card import DanceCard
from workers.mcp_worker import McpWorker


def _worker():
    return McpWorker("ws://10.192.1.2:5000", "robot-1")


def test_reset_clears_count_and_last_executed(tmp_path, monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "data_dir", str(tmp_path))
    DatabaseConnection().initialize_schema()
    repository = DanceCountRepository()

    repository.increment("robot-1", "wave", "motion")
    assert repository.get_count("robot-1", "wave") == 1

    assert repository.reset("robot-1", "wave") is True
    assert repository.get_count("robot-1", "wave") == 0

    connection = DatabaseConnection().get_connection()
    row = connection.execute(
        "SELECT count, last_executed FROM dance_counts "
        "WHERE robot_accid = ? AND name = ?",
        ("robot-1", "wave"),
    ).fetchone()
    connection.close()
    assert row["count"] == 0
    assert row["last_executed"] is None


def test_service_reset_updates_current_robot_cache(qtbot, monkeypatch):
    service = DanceService(_worker())
    monkeypatch.setattr(ROBOT_CONFIG, "ws_accid", "robot-1")
    reset_calls = []
    monkeypatch.setattr(
        service._count_repo,
        "reset",
        lambda robot_accid, name: reset_calls.append((robot_accid, name)) or True,
    )
    service._counts[("robot-1", "wave")] = 4

    with qtbot.waitSignal(service.count_reset, timeout=1000) as signal:
        result = service.reset_count("wave", "motion")

    assert result == 0
    assert reset_calls == [("robot-1", "wave")]
    assert service.get_count("wave") == 0
    assert signal.args == ["wave", "motion", 0]


def test_dance_card_reset_button_is_labeled_and_emits(qtbot):
    card = DanceCard("挥手", "motion", count=3)
    qtbot.addWidget(card)

    assert card.reset_btn.text() == "清零"
    assert card.reset_btn.width() == 48
    with qtbot.waitSignal(card.reset_clicked, timeout=1000):
        qtbot.mouseClick(card.reset_btn, Qt.MouseButton.LeftButton)


def test_reset_confirmation_cancel_keeps_count(qtbot, monkeypatch):
    service = DanceService(_worker())
    monkeypatch.setattr(service, "get_count", lambda _name: 3)
    reset_calls = []
    monkeypatch.setattr(
        service,
        "reset_count",
        lambda name, category: reset_calls.append((name, category)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    panel = DanceLibraryPanel(service)
    qtbot.addWidget(panel)
    panel._populate_motions([{"motion_name_en": "wave", "motion_name_cn": "挥手"}])

    panel._confirm_reset("wave", "motion")

    assert reset_calls == []
    assert panel._motion_cards["wave"].count_badge.text() == "3"
