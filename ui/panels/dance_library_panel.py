"""Dance & motion library â€” tabbed, compact layout."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QSlider, QTabWidget, QGridLayout, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer
from models.robot_profile import RobotProfile
from services.dance_service import DanceService
from ui.widgets.dance_card import DanceCard
from ui.widgets.sequencer_editor import SequencerEditor
from ui.dialogs.message_dialog import AppMessageBox


DANCE_DISPLAY_ORDER = [
    ("èƒœåˆ©ä¹‹èˆž",),
    ("çƒ­çƒˆ",),
    ("ä½Žä¿—å°è¯´",),
    ("é¡ºé£Žé¡ºæ°´é¡ºè´¢ç¥ž",),
    ("ä¸‡ç‰©ç”Ÿ",),
    ("æœºæ¢°èˆž",),
    ("ç›¸äº²ç›¸çˆ±",),
    ("APT",),
    ("æ‰­èƒ¯èˆž", "abracadabræ‰­èƒ¯èˆž"),
    ("å¡æ‹‰æ°¸è¿œok", "å¡æ‹‰æ°¸è¿œOK"),
    ("æ¥ä¸ªè¹¦è¹¦",),
    ("gentleman",),
    ("ç®¡ä»–ä»€ä¹ˆéŸ³ä¹",),
    ("å­¤èº«æ‘‡",),
]

UNRELIABLE_MOTIONS = {
    "raise_and_introduce": "è¯¥åŠ¨ä½œå½“å‰å›ºä»¶ä¸è¿”å›žå®Œæˆé€šçŸ¥ï¼Œæš‚ä¸å‚ä¸Žè‡ªåŠ¨éªŒæ”¶",
}


def _normalize_dance_label(value: str) -> str:
    return "".join(value.lower().split())


def _dance_display_order_key(dance: dict, original_index: int) -> tuple[int, int]:
    labels = [
        _normalize_dance_label(str(dance.get("name", ""))),
        _normalize_dance_label(str(dance.get("english_name", ""))),
        _normalize_dance_label(str(dance.get("rc_mapping", ""))),
    ]
    for order, aliases in enumerate(DANCE_DISPLAY_ORDER):
        normalized_aliases = [_normalize_dance_label(alias) for alias in aliases]
        if any(alias and any(alias in label for label in labels) for alias in normalized_aliases):
            return (order, original_index)
    return (len(DANCE_DISPLAY_ORDER), original_index)


class FlowGrid(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._count = 0
        self._cols = 5

    def add_card(self, card: DanceCard):
        row = self._count // self._cols
        col = self._count % self._cols
        self._layout.addWidget(card, row, col)
        self._count += 1

    def clear_cards(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._count = 0


class DanceLibraryPanel(QWidget):
    def __init__(self, dance_service: DanceService, parent=None):
        super().__init__(parent)
        self._service = dance_service
        self._allowed_tools: frozenset[str] | None = None
        self._profile_key = ""
        self._robot_status = ""
        self._dance_cards: dict[str, DanceCard] = {}
        self._motion_cards: dict[str, DanceCard] = {}
        self._walk_timer: QTimer | None = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Toolbar
        bar = QHBoxLayout()
        self.refresh_dances_btn = QPushButton("åˆ·æ–°èˆžè¹ˆ")
        self.refresh_motions_btn = QPushButton("åˆ·æ–°åŠ¨ä½œ")
        self.motion_engine_btn = QPushButton("æ‰‹åŠ¨åŠ¨ä½œåº“æ¨¡å¼")
        self.stop_repeat_btn = QPushButton("åœæ­¢è¿žç»­åŠ¨ä½œ")
        self.stop_repeat_btn.setEnabled(False)
        self.motion_engine_btn.setCheckable(True)
        for b in [self.refresh_dances_btn, self.refresh_motions_btn, self.motion_engine_btn, self.stop_repeat_btn]:
            b.setFixedHeight(30)
            b.setStyleSheet(
                "QPushButton { background: #FFFFFF; color: #1D2129; border: 1px solid #E5E6EB; "
                "border-radius: 6px; padding: 4px 14px; font-size: 12px; }"
                "QPushButton:hover { border-color: #6C5CE7; color: #6C5CE7; }"
                "QPushButton:checked { background: #6C5CE7; color: #fff; border-color: #6C5CE7; }")
        bar.addWidget(self.refresh_dances_btn)
        bar.addWidget(self.refresh_motions_btn)
        bar.addWidget(self.motion_engine_btn)
        bar.addWidget(self.stop_repeat_btn)
        bar.addStretch()
        layout.addLayout(bar)

        self.action_status_label = QLabel("æ‰§è¡Œèˆžè¹ˆ/åŠ¨ä½œæ—¶ä¼šè‡ªåŠ¨è¿›å…¥åŠ¨ä½œåº“æ¨¡å¼ï¼Œç»“æŸåŽè‡ªåŠ¨å›žæ‹Ÿäººè¡Œèµ°æ¨¡å¼")
        self.action_status_label.setStyleSheet(
            "color: #4E5969; font-size: 12px; padding: 2px 0; border: none; background: transparent;"
        )
        layout.addWidget(self.action_status_label)

        # Tabs: Dances | Motions | Walk | Sequencer
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #E5E6EB; background: #FFFFFF; border-radius: 8px; }
            QTabBar::tab { background: #F2F3F5; color: #86909C; padding: 8px 18px; border: none; font-size: 12px; margin-right: 2px; }
            QTabBar::tab:selected { background: #FFFFFF; color: #6C5CE7; border-bottom: 2px solid #6C5CE7; }
            QTabBar::tab:hover:!selected { color: #4E5969; }
        """)

        # Tab 1: Dances
        self.dance_grid = FlowGrid()
        dance_scroll = QScrollArea()
        dance_scroll.setWidgetResizable(True)
        dance_scroll.setWidget(self.dance_grid)
        dance_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.tabs.addTab(dance_scroll, "èˆžè¹ˆ (Dances)")

        # Tab 2: Motions
        self.motion_grid = FlowGrid()
        motion_scroll = QScrollArea()
        motion_scroll.setWidgetResizable(True)
        motion_scroll.setWidget(self.motion_grid)
        motion_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.tabs.addTab(motion_scroll, "åŠ¨ä½œ (Motions)")

        # Tab 3: Walking
        walk_tab = QWidget()
        walk_layout = QVBoxLayout(walk_tab)
        walk_layout.setContentsMargins(16, 16, 16, 16)
        for name, attr in [("å‰åŽ vx", "vx"), ("æ¨ªå‘ vy", "vy"), ("æ—‹è½¬ yaw", "yaw")]:
            row = QHBoxLayout()
            lbl = QLabel(f"{name}: 0.00")
            lbl.setStyleSheet("color: #4E5969; min-width: 80px; font-size: 12px; border: none; background: transparent;")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-100, 100)
            slider.setValue(0)
            slider.valueChanged.connect(
                lambda v, l=lbl, n=name: l.setText(f"{n}: {v / 100:.2f}"))
            setattr(self, f"slider_{attr}", slider)
            row.addWidget(lbl)
            row.addWidget(slider)
            walk_layout.addLayout(row)
        self.apply_walk_btn = QPushButton("åº”ç”¨é€Ÿåº¦")
        self.apply_walk_btn.setStyleSheet(
            "QPushButton { background: #6C5CE7; color: #fff; border: none; "
            "border-radius: 6px; padding: 8px; font-weight: 700; }"
            "QPushButton:hover { background: #5A4BD1; }")
        self.apply_walk_btn.clicked.connect(self._apply_walk)
        walk_layout.addWidget(self.apply_walk_btn)
        self.walk_status_label = QLabel("éžé›¶é€Ÿåº¦ä¼šæŒç»­å‘é€ï¼›ä¸‰è½´å½’é›¶åŽç‚¹å‡»åº”ç”¨é€Ÿåº¦å¯åœæ­¢")
        self.walk_status_label.setStyleSheet(
            "color: #86909C; font-size: 12px; border: none; background: transparent;"
        )
        walk_layout.addWidget(self.walk_status_label)
        self._walk_timer = QTimer(self)
        self._walk_timer.setInterval(200)
        self._walk_timer.timeout.connect(self._send_walk_velocity_once)
        walk_layout.addStretch()
        self.tabs.addTab(walk_tab, "è¡Œèµ°")

        # Tab 4: Sequencer
        seq_tab = QWidget()
        seq_layout = QVBoxLayout(seq_tab)
        seq_layout.setContentsMargins(8, 8, 8, 8)
        self.sequencer = SequencerEditor()
        seq_layout.addWidget(self.sequencer)
        self.tabs.addTab(seq_tab, "åºåˆ—å™¨")

        layout.addWidget(self.tabs)

    def _connect_signals(self):
        self.refresh_dances_btn.clicked.connect(self._service.load_dances)
        self.refresh_motions_btn.clicked.connect(self._service.load_motions)
        self.motion_engine_btn.clicked.connect(self._on_motion_engine_toggled)
        self.stop_repeat_btn.clicked.connect(self._service.stop_motion_repeat)
        self._service.dance_list_loaded.connect(self._populate_dances)
        self._service.motion_list_loaded.connect(self._populate_motions)
        self._service.dance_executed.connect(self._on_dance_executed)
        self._service.dance_target_completed.connect(self._on_dance_target_completed)
        self._service.motion_executed.connect(self._on_motion_executed)
        self._service.count_reset.connect(self._on_count_reset)
        self._service.action_state_changed.connect(self._on_action_state_changed)
        self._service.motion_engine_changed.connect(self.motion_engine_btn.setChecked)
        self.sequencer.execute_sequence_clicked.connect(self._on_execute_sequence)
        self.sequencer.save_sequence_clicked.connect(self._service.save_sequence)

    def _populate_dances(self, dances: list[dict]):
        self.dance_grid.clear_cards()
        self._dance_cards.clear()
        names = []
        ordered_dances = [
            dance for _, dance in sorted(
                enumerate(dances),
                key=lambda item: _dance_display_order_key(item[1], item[0]),
            )
        ]
        for d in ordered_dances:
            rc = d.get("rc_mapping", "")
            cn = d.get("name", "") or d.get("english_name", rc)
            en = d.get("english_name", "")
            dur = d.get("duration", 0)
            count = self._service.get_count(rc, "dance")
            card = DanceCard(cn, "dance", count, subtitle=f"{en} Â· {dur}s" if en else "")
            card.execute_clicked.connect(lambda n=rc: self._request_dance_execution(n))
            card.reset_clicked.connect(lambda n=rc: self._confirm_reset(n, "dance"))
            card.setEnabled(self._action_ready("execute_dance"))
            self.dance_grid.add_card(card)
            self._dance_cards[rc] = card
            names.append(rc)
        self.sequencer.set_dance_names(names)

    def _populate_motions(self, motions: list[dict]):
        self.motion_grid.clear_cards()
        self._motion_cards.clear()
        for m in motions:
            en = m.get("motion_name_en", "")
            cn = m.get("motion_name_cn", "")
            count = self._service.get_count(en, "motion")
            unavailable_reason = UNRELIABLE_MOTIONS.get(en, "")
            subtitle = unavailable_reason if unavailable_reason else (en if cn else "")
            card = DanceCard(
                cn or en,
                "motion",
                count,
                subtitle=subtitle,
                repeat_enabled=self._profile_key != "hu_l04_01",
                executable=not unavailable_reason,
                unavailable_reason=unavailable_reason,
            )
            if not unavailable_reason:
                card.execute_clicked.connect(lambda n=en: self._request_motion_execution(n))
                if self._profile_key != "hu_l04_01":
                    card.repeat_clicked.connect(lambda n=en: self._service.execute_motion_repeat(n, times=5, delay_ms=2000))
            card.reset_clicked.connect(lambda n=en: self._confirm_reset(n, "motion"))
            card.setEnabled(self._action_ready("execute_motion") and not unavailable_reason)
            self.motion_grid.add_card(card)
            self._motion_cards[en] = card

    def _on_dance_executed(self, name: str, count: int):
        if name in self._dance_cards:
            self._dance_cards[name].set_count(count)

    def _on_dance_target_completed(self, name: str, count: int, robot_accid: str):
        display_name = self._dance_cards[name].dance_name if name in self._dance_cards else name
        AppMessageBox.information(
            self,
            "èˆžè¹ˆæµ‹è¯•å®Œæˆ",
            f"{robot_accid}\n{display_name} å·²æµ‹è¯•åˆ°ç¬¬ {count} éã€‚",
        )

    def _on_motion_executed(self, name: str, count: int):
        if name in self._motion_cards:
            self._motion_cards[name].set_count(count)

    def _confirm_reset(self, name: str, category: str):
        card_map = self._dance_cards if category == "dance" else self._motion_cards
        display_name = card_map[name].dance_name if name in card_map else name
        answer = QMessageBox.question(
            self,
            "æ¸…é›¶æ‰§è¡Œæ¬¡æ•°",
            f"ç¡®å®šå°†â€œ{display_name}â€çš„æ‰§è¡Œæ¬¡æ•°æ¸…é›¶å—ï¼Ÿ",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._service.reset_count(name, category)

    def _on_count_reset(self, name: str, category: str, count: int):
        card_map = self._dance_cards if category == "dance" else self._motion_cards
        if name in card_map:
            card_map[name].set_count(count)

    def _on_action_state_changed(self, running: bool, label: str):
        if running:
            self.stop_continuous_walk(reset_sliders=True, send_stop=True)
        self.action_status_label.setText(label)
        repeat_running = label.startswith("è¿žç»­åŠ¨ä½œ")
        for card in self._dance_cards.values():
            card.setEnabled(not running and self._action_ready("execute_dance"))
        for name, card in self._motion_cards.items():
            card.setEnabled(
                not running
                and self._action_ready("execute_motion")
                and name not in UNRELIABLE_MOTIONS
            )
        self.refresh_dances_btn.setEnabled(not running and self._tool_allowed("get_dances"))
        self.refresh_motions_btn.setEnabled(not running and self._tool_allowed("get_motions"))
        self.motion_engine_btn.setEnabled(not running and self._tool_allowed("set_motion_engine"))
        self.sequencer.setEnabled(not running and self._sequence_execution_allowed())
        self.stop_repeat_btn.setEnabled(repeat_running and running)

    def apply_profile(self, profile: RobotProfile | None):
        self._profile_key = profile.key if profile else ""
        self._robot_status = ""
        self._allowed_tools = profile.allowed_tools if profile else frozenset()
        if not self._tool_allowed("set_walk_velocity"):
            self.stop_continuous_walk(reset_sliders=True, send_stop=False)
        self.refresh_dances_btn.setEnabled(self._tool_allowed("get_dances"))
        self.refresh_motions_btn.setEnabled(self._tool_allowed("get_motions"))
        self.motion_engine_btn.setEnabled(self._tool_allowed("set_motion_engine"))
        self.apply_walk_btn.setEnabled(self._tool_allowed("set_walk_velocity"))
        self.tabs.setTabEnabled(2, self._tool_allowed("set_walk_velocity"))
        self.tabs.setTabEnabled(3, self._sequence_execution_allowed())
        self.sequencer.setEnabled(self._sequence_execution_allowed())
        for card in self._dance_cards.values():
            card.setEnabled(self._action_ready("execute_dance"))
        for name, card in self._motion_cards.items():
            card.setEnabled(
                self._action_ready("execute_motion") and name not in UNRELIABLE_MOTIONS
            )
        if self._profile_key == "hu_l04_01":
            self.action_status_label.setText("Luna L04 å•æ¬¡åŠ¨ä½œä»…åœ¨ Walk çŠ¶æ€å¼€æ”¾")
        elif profile and not self._tool_allowed("execute_motion"):
            self.action_status_label.setText(
                f"{profile.display_name} å½“å‰ä»…å¼€æ”¾åŠ¨ä½œä¸Žèˆžè¹ˆåˆ—è¡¨æŸ¥è¯¢"
            )

    def update_robot_status(self, info: dict):
        self._robot_status = str(info.get("robot_status", ""))
        if self._profile_key != "hu_l04_01":
            return
        ready = self._robot_status == "Walk"
        for card in self._dance_cards.values():
            card.setEnabled(ready and self._tool_allowed("execute_dance"))
        for name, card in self._motion_cards.items():
            card.setEnabled(
                ready
                and self._tool_allowed("execute_motion")
                and name not in UNRELIABLE_MOTIONS
            )
        self.action_status_label.setText(
            "Luna L04 å•æ¬¡åŠ¨ä½œå·²å°±ç»ª"
            if ready else f"Luna L04 å½“å‰çŠ¶æ€ {self._robot_status or 'æœªçŸ¥'}ï¼Œéœ€å…ˆåˆ‡æ¢åˆ° Walk"
        )

    def _request_dance_execution(self, rc_mapping: str):
        if (
            self._confirm_luna_action("èˆžè¹ˆ", rc_mapping)
            and self._service.authorize_next_action("dance", rc_mapping)
        ):
            self._service.execute_dance(rc_mapping)

    def _request_motion_execution(self, motion_name: str):
        if (
            self._confirm_luna_action("åŽŸå­åŠ¨ä½œ", motion_name)
            and self._service.authorize_next_action("motion", motion_name)
        ):
            self._service.execute_motion(motion_name)

    def _confirm_luna_action(self, action_type: str, name: str) -> bool:
        if self._profile_key != "hu_l04_01":
            return True
        if self._robot_status != "Walk":
            AppMessageBox.warning(
                self,
                "Luna åŠ¨ä½œå·²é˜»æ­¢",
                f"å½“å‰çŠ¶æ€ä¸º {self._robot_status or 'æœªçŸ¥'}ï¼Œä»…å…è®¸åœ¨ Walk çŠ¶æ€æ‰§è¡Œã€‚",
            )
            return False
        box = AppMessageBox(
            self,
            "ç¡®è®¤ Luna çœŸæœºåŠ¨ä½œ",
            f"å³å°†æ‰§è¡Œ{action_type}ï¼š{name}\n\n"
            "è¯·ç¡®è®¤æœºå™¨äººå‘¨å›´æ— äººã€æ— éšœç¢ç‰©ï¼Œæ€¥åœå¯ç”¨ï¼Œå¹¶å®‰æŽ’äººå‘˜çŽ°åœºçœ‹æŠ¤ã€‚",
            QMessageBox.Icon.Warning,
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        confirm_button = box.button(QMessageBox.StandardButton.Yes)
        cancel_button = box.button(QMessageBox.StandardButton.No)
        if confirm_button:
            confirm_button.setText("ç¡®è®¤æ‰§è¡Œ")
            confirm_button.setObjectName("confirmButton")
        if cancel_button:
            cancel_button.setText("å–æ¶ˆ")
        return box.exec() == QMessageBox.StandardButton.Yes

    def _action_ready(self, tool_name: str) -> bool:
        return self._tool_allowed(tool_name) and (
            self._profile_key != "hu_l04_01" or self._robot_status == "Walk"
        )

    def _sequence_execution_allowed(self) -> bool:
        return (
            self._profile_key != "hu_l04_01"
            and self._tool_allowed("execute_motion")
            and self._tool_allowed("set_walk_velocity")
        )

    def _tool_allowed(self, tool_name: str) -> bool:
        return self._allowed_tools is None or tool_name in self._allowed_tools

    def _apply_walk(self):
        vx = self.slider_vx.value() / 100.0
        vy = self.slider_vy.value() / 100.0
        yaw = self.slider_yaw.value() / 100.0

        self._send_walk_velocity_once()
        if vx == 0 and vy == 0 and yaw == 0:
            if self._walk_timer and self._walk_timer.isActive():
                self._walk_timer.stop()
            self.apply_walk_btn.setText("åº”ç”¨é€Ÿåº¦")
            self.walk_status_label.setText("å·²å‘é€åœæ­¢é€Ÿåº¦")
            return

        if self._walk_timer and not self._walk_timer.isActive():
            self._walk_timer.start()
        self.apply_walk_btn.setText("æ›´æ–°æŒç»­é€Ÿåº¦")
        self.walk_status_label.setText(f"æŒç»­å‘é€: vx={vx:.2f}, vy={vy:.2f}, yaw={yaw:.2f}")

    def _send_walk_velocity_once(self):
        self._service.set_walk_velocity(
            self.slider_vx.value() / 100.0,
            self.slider_vy.value() / 100.0,
            self.slider_yaw.value() / 100.0,
        )

    def stop_continuous_walk(self, reset_sliders: bool = True, send_stop: bool = True):
        if self._walk_timer and self._walk_timer.isActive():
            self._walk_timer.stop()
        if reset_sliders:
            self.slider_vx.setValue(0)
            self.slider_vy.setValue(0)
            self.slider_yaw.setValue(0)
        if send_stop and self._tool_allowed("set_walk_velocity"):
            self._service.set_walk_velocity(0.0, 0.0, 0.0)
        self.apply_walk_btn.setText("åº”ç”¨é€Ÿåº¦")
        self.walk_status_label.setText("æŒç»­è¡Œèµ°å·²åœæ­¢")

    def _on_motion_engine_toggled(self, checked: bool):
        self.stop_continuous_walk(reset_sliders=True, send_stop=True)
        self._service.set_motion_engine(1 if checked else 0)

    def _on_execute_sequence(self, sequence):
        self.stop_continuous_walk(reset_sliders=True, send_stop=True)
        self._service.execute_sequence(sequence)
