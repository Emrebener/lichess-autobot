"""
Main Window for Lichess Autobot
Contains the main UI with chess board, controls, stats, and game info panels
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QComboBox, QLabel, QLineEdit, QCheckBox,
    QGroupBox, QMessageBox, QSplitter, QFrame, QStatusBar,
    QSizePolicy, QSpacerItem, QDoubleSpinBox, QScrollArea, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QFont, QIcon, QKeyEvent, QPainter, QColor, QBrush

import chess

from ui.chess_board import ChessBoardWidget, AspectRatioContainer
from ui.player_info_widget import PlayerInfoWidget, PIECE_VALUES
from ui.evaluation_widget import EvaluationWidget
from ui.move_list_widget import MoveListWidget
from ui.engine_options_dialog import EngineOptionsDialog
from database import DatabaseManager, LogSeverity
from engine import UCIEngine, EngineScanner, UCIOption
from lichess import LichessClient, LichessAPIError, TIME_CONTROLS, TimeControl


class ToggleSwitch(QWidget):
    """Custom toggle switch widget"""
    
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._handle_position = 3  # Start position of handle
        
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Animation for smooth toggle
        self._animation = QPropertyAnimation(self, b"handle_position")
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
    
    def isChecked(self) -> bool:
        return self._checked
    
    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self._animate_toggle()
    
    def _get_handle_position(self) -> int:
        return self._handle_position
    
    def _set_handle_position(self, pos: int):
        self._handle_position = pos
        self.update()
    
    handle_position = pyqtProperty(int, fget=_get_handle_position, fset=_set_handle_position)
    
    def _animate_toggle(self):
        self._animation.setStartValue(self._handle_position)
        self._animation.setEndValue(23 if self._checked else 3)
        self._animation.start()
    
    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._animate_toggle()
        self.toggled.emit(self._checked)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background track
        if self._checked:
            track_color = QColor("#4CAF50")  # Green when on
        else:
            track_color = QColor("#555555")  # Gray when off
        
        painter.setBrush(QBrush(track_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 44, 24, 12, 12)
        
        # Draw handle
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(self._handle_position, 3, 18, 18)


class AsyncSignals(QObject):
    """Signals for async operations"""
    game_started = pyqtSignal(dict)
    game_state_updated = pyqtSignal(dict)
    game_finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)  # title, message
    status_changed = pyqtSignal(str)
    stats_updated = pyqtSignal()


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self, db: DatabaseManager, engines_dir: str):
        super().__init__()
        
        self.db = db
        self.engines_dir = engines_dir
        self.signals = AsyncSignals()
        
        # State
        self.lichess_client: Optional[LichessClient] = None
        self.engine: Optional[UCIEngine] = None
        self.eval_engine: Optional[UCIEngine] = None  # Separate engine for evaluation
        self.is_running = False
        self.current_game_id: Optional[str] = None
        self.our_color: Optional[str] = None
        self.game_board: Optional[chess.Board] = None
        
        # Flag to prevent saving settings during initialization
        self._loading_settings = True
        
        # Player info
        self.white_player: Dict[str, Any] = {}
        self.black_player: Dict[str, Any] = {}
        self.white_time_ms: int = 0
        self.black_time_ms: int = 0
        
        # Tasks
        self.event_stream_task: Optional[asyncio.Task] = None
        self.game_stream_task: Optional[asyncio.Task] = None
        self.seek_task: Optional[asyncio.Task] = None
        self.eval_task: Optional[asyncio.Task] = None
        
        # Stop after current game flag
        self.stop_after_game: bool = False
        
        # Evaluation state
        self._last_eval_fen: str = ""  # Last evaluated position
        self._eval_analysis = None  # Current analysis context manager
        
        # Set up UI
        self._setup_ui()
        self._connect_signals()
        self._scan_engines()  # Populate engine combos first
        self._load_settings()  # Then load saved settings
        self._loading_settings = False  # Now allow saving on changes
        
        # Window settings
        self.setWindowTitle("Lichess Autobot")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        
        # Enable keyboard focus for arrow key navigation
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def _setup_ui(self):
        """Set up the main UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # ===== LEFT SIDE: Game area (board, players, eval, moves) =====
        game_area = QWidget()
        game_layout = QVBoxLayout(game_area)
        game_layout.setContentsMargins(0, 0, 0, 0)
        game_layout.setSpacing(5)
        
        # Preferences container (at the top)
        preferences_group = QGroupBox("Preferences")
        preferences_layout = QHBoxLayout(preferences_group)
        preferences_layout.setContentsMargins(10, 5, 10, 5)
        preferences_layout.setSpacing(15)
        
        # Evaluation settings in a vertical sub-layout
        eval_settings_layout = QVBoxLayout()
        eval_settings_layout.setSpacing(5)
        
        # Top row: Toggle switch and label
        eval_toggle_row = QHBoxLayout()
        eval_toggle_row.setSpacing(8)
        
        self.eval_toggle = ToggleSwitch()
        self.eval_toggle.setChecked(True)  # On by default
        self.eval_toggle.toggled.connect(self._on_eval_toggle_changed)
        
        eval_toggle_label = QLabel("Real-time Evaluation")
        eval_toggle_label.setStyleSheet("font-size: 12px;")
        
        eval_toggle_row.addWidget(self.eval_toggle)
        eval_toggle_row.addWidget(eval_toggle_label)
        eval_toggle_row.addStretch()
        
        eval_settings_layout.addLayout(eval_toggle_row)
        
        # Bottom row: Engine dropdown
        eval_engine_row = QHBoxLayout()
        eval_engine_row.setSpacing(8)
        
        eval_engine_label = QLabel("Engine:")
        eval_engine_label.setStyleSheet("font-size: 12px;")
        self.eval_engine_combo = QComboBox()
        self.eval_engine_combo.setMinimumWidth(180)
        self.eval_engine_combo.addItem("None (no evaluation)", None)
        self.eval_engine_combo.currentIndexChanged.connect(self._on_eval_engine_changed)
        
        eval_engine_row.addWidget(eval_engine_label)
        eval_engine_row.addWidget(self.eval_engine_combo)
        eval_engine_row.addStretch()
        
        eval_settings_layout.addLayout(eval_engine_row)
        
        preferences_layout.addLayout(eval_settings_layout)
        preferences_layout.addStretch()
        
        game_layout.addWidget(preferences_group)
        
        # Top player info (opponent when playing as white) - sticks to top
        self.top_player = PlayerInfoWidget(is_top=True)
        game_layout.addWidget(self.top_player)
        
        # Middle section: Eval bar | Chess board | Moves list
        middle_section = QHBoxLayout()
        middle_section.setSpacing(5)
        
        # Evaluation widget (on the left, takes full height)
        self.evaluation_widget = EvaluationWidget()
        self.evaluation_widget.setMinimumWidth(50)
        self.evaluation_widget.setMaximumWidth(60)
        self.evaluation_widget.set_no_engine()
        middle_section.addWidget(self.evaluation_widget)
        
        # Chess board in aspect ratio container (center, dynamically sized square)
        self.chess_board = ChessBoardWidget()
        self.board_container = AspectRatioContainer(self.chess_board)
        middle_section.addWidget(self.board_container, stretch=1)
        
        # Move list (on the right of board, takes full height of middle section)
        self.move_list = MoveListWidget()
        self.move_list.setMinimumWidth(160)
        self.move_list.setMaximumWidth(200)
        self.move_list.move_selected.connect(self._on_move_selected)
        self.move_list.jump_to_live.connect(self._on_jump_to_live)
        middle_section.addWidget(self.move_list)
        
        game_layout.addLayout(middle_section, stretch=1)
        
        # Bottom player info (us when playing as white) - sticks to bottom
        self.bottom_player = PlayerInfoWidget(is_top=False)
        game_layout.addWidget(self.bottom_player)
        
        # Game link label (clickable link to open game in browser)
        self.game_link_label = QLabel()
        self.game_link_label.setOpenExternalLinks(True)
        self.game_link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.game_link_label.setStyleSheet("color: #5a9; font-size: 11px;")
        self.game_link_label.hide()  # Hidden until a game starts
        game_layout.addWidget(self.game_link_label)
        
        main_layout.addWidget(game_area, stretch=2)
        
        # ===== RIGHT SIDE: Controls and stats (scrollable) =====
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setMinimumWidth(290)
        right_scroll.setMaximumWidth(360)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 20, 0)  # More right margin for scrollbar
        right_layout.setSpacing(8)
        
        # API Token group
        token_group = QGroupBox("Lichess API")
        token_layout = QVBoxLayout(token_group)
        
        token_label = QLabel("Bearer Token:")
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Enter your Lichess API token")
        
        self.validate_token_btn = QPushButton("Validate Token")
        self.validate_token_btn.clicked.connect(self._on_validate_token)
        
        self.token_status_label = QLabel("")
        self.token_status_label.setStyleSheet("font-size: 11px;")
        
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_input)
        token_layout.addWidget(self.validate_token_btn)
        token_layout.addWidget(self.token_status_label)
        
        right_layout.addWidget(token_group)
        
        # Playing Engine selection group
        engine_group = QGroupBox("Playing Engine")
        engine_layout = QVBoxLayout(engine_group)
        
        engine_label = QLabel("Select Engine:")
        self.engine_combo = QComboBox()
        self.engine_combo.setMinimumWidth(200)
        self.engine_combo.currentIndexChanged.connect(self._on_settings_changed)
        
        self.refresh_engines_btn = QPushButton("🔄")
        self.refresh_engines_btn.setFixedWidth(35)
        self.refresh_engines_btn.setToolTip("Refresh engine list")
        self.refresh_engines_btn.clicked.connect(self._scan_engines)
        
        self.engine_options_btn = QPushButton("⚙️ Options")
        self.engine_options_btn.setToolTip("Configure UCI engine options")
        self.engine_options_btn.clicked.connect(self._on_engine_options)
        
        engine_row = QHBoxLayout()
        engine_row.addWidget(self.engine_combo, stretch=1)
        engine_row.addWidget(self.refresh_engines_btn)
        engine_row.addWidget(self.engine_options_btn)
        
        # Single node checkbox (for engines like Maia that don't need search)
        self.single_node_checkbox = QCheckBox("Single node?")
        self.single_node_checkbox.setToolTip(
            "Use 'go nodes 1' for engines like Maia that play without searching the move tree"
        )
        self.single_node_checkbox.stateChanged.connect(self._on_settings_changed)

        engine_layout.addWidget(engine_label)
        engine_layout.addLayout(engine_row)
        engine_layout.addWidget(self.single_node_checkbox)

        right_layout.addWidget(engine_group)

        # Game settings group
        settings_group = QGroupBox("Game Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        # Time control
        tc_label = QLabel("Time Control:")
        self.time_control_combo = QComboBox()
        for tc in TIME_CONTROLS:
            self.time_control_combo.addItem(tc.name, tc)
        
        # Move time range settings (separate for opening and rest of game)
        move_time_label = QLabel("Move Time Range:")
        
        # Opening phase (first 10 moves) - min/max range for randomization
        opening_time_layout = QHBoxLayout()
        opening_time_label = QLabel("  Opening (moves 1-10):")
        self.opening_time_min_spin = QDoubleSpinBox()
        self.opening_time_min_spin.setRange(0.1, 60.0)
        self.opening_time_min_spin.setValue(1.0)
        self.opening_time_min_spin.setSingleStep(0.5)
        self.opening_time_min_spin.setSuffix(" sec")
        self.opening_time_min_spin.setToolTip("Minimum time per move during opening")
        
        opening_to_label = QLabel("to")
        
        self.opening_time_max_spin = QDoubleSpinBox()
        self.opening_time_max_spin.setRange(0.1, 60.0)
        self.opening_time_max_spin.setValue(3.0)
        self.opening_time_max_spin.setSingleStep(0.5)
        self.opening_time_max_spin.setSuffix(" sec")
        self.opening_time_max_spin.setToolTip("Maximum time per move during opening")
        
        opening_time_layout.addWidget(opening_time_label)
        opening_time_layout.addWidget(self.opening_time_min_spin)
        opening_time_layout.addWidget(opening_to_label)
        opening_time_layout.addWidget(self.opening_time_max_spin)
        
        # Middle/endgame phase (after move 10) - min/max range for randomization
        midgame_time_layout = QHBoxLayout()
        midgame_time_label = QLabel("  After move 10:")
        self.midgame_time_min_spin = QDoubleSpinBox()
        self.midgame_time_min_spin.setRange(0.1, 60.0)
        self.midgame_time_min_spin.setValue(3.0)
        self.midgame_time_min_spin.setSingleStep(0.5)
        self.midgame_time_min_spin.setSuffix(" sec")
        self.midgame_time_min_spin.setToolTip("Minimum time per move after opening")
        
        midgame_to_label = QLabel("to")
        
        self.midgame_time_max_spin = QDoubleSpinBox()
        self.midgame_time_max_spin.setRange(0.1, 60.0)
        self.midgame_time_max_spin.setValue(8.0)
        self.midgame_time_max_spin.setSingleStep(0.5)
        self.midgame_time_max_spin.setSuffix(" sec")
        self.midgame_time_max_spin.setToolTip("Maximum time per move after opening")
        
        midgame_time_layout.addWidget(midgame_time_label)
        midgame_time_layout.addWidget(self.midgame_time_min_spin)
        midgame_time_layout.addWidget(midgame_to_label)
        midgame_time_layout.addWidget(self.midgame_time_max_spin)
        
        # Rated toggle
        self.rated_checkbox = QCheckBox("Rated Games")
        
        # Connect settings change signals to save settings
        self.time_control_combo.currentIndexChanged.connect(self._on_settings_changed)
        self.rated_checkbox.stateChanged.connect(self._on_settings_changed)
        self.opening_time_min_spin.valueChanged.connect(self._on_settings_changed)
        self.opening_time_max_spin.valueChanged.connect(self._on_settings_changed)
        self.midgame_time_min_spin.valueChanged.connect(self._on_settings_changed)
        self.midgame_time_max_spin.valueChanged.connect(self._on_settings_changed)
        
        settings_layout.addWidget(tc_label)
        settings_layout.addWidget(self.time_control_combo)
        settings_layout.addWidget(move_time_label)
        settings_layout.addLayout(opening_time_layout)
        settings_layout.addLayout(midgame_time_layout)
        settings_layout.addWidget(self.rated_checkbox)
        
        right_layout.addWidget(settings_group)
        
        # Control buttons
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        
        self.start_btn = QPushButton("▶ Start Bot")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_btn.clicked.connect(self._on_start_bot)
        
        self.stop_btn = QPushButton("⏹ Stop Bot")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_bot)
        
        self.stop_after_game_btn = QPushButton("⏸ Stop After Game")
        self.stop_after_game_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QPushButton:checked {
                background-color: #e65100;
            }
        """)
        self.stop_after_game_btn.setEnabled(False)
        self.stop_after_game_btn.setCheckable(True)
        self.stop_after_game_btn.setToolTip("Stop the bot after the current game finishes")
        self.stop_after_game_btn.clicked.connect(self._on_stop_after_game)
        
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.stop_after_game_btn)
        
        right_layout.addWidget(controls_group)
        
        # Statistics group
        stats_group = QGroupBox("Statistics")
        stats_layout = QGridLayout(stats_group)
        
        self.games_played_label = QLabel("0")
        self.games_won_label = QLabel("0")
        self.games_lost_label = QLabel("0")
        self.games_drawn_label = QLabel("0")
        self.win_rate_label = QLabel("0%")
        
        # Style the stat values
        for label in [self.games_played_label, self.games_won_label, 
                      self.games_lost_label, self.games_drawn_label, self.win_rate_label]:
            label.setStyleSheet("font-weight: bold; font-size: 14px;")
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        stats_layout.addWidget(QLabel("Games Played:"), 0, 0)
        stats_layout.addWidget(self.games_played_label, 0, 1)
        stats_layout.addWidget(QLabel("Wins:"), 1, 0)
        stats_layout.addWidget(self.games_won_label, 1, 1)
        stats_layout.addWidget(QLabel("Losses:"), 2, 0)
        stats_layout.addWidget(self.games_lost_label, 2, 1)
        stats_layout.addWidget(QLabel("Draws:"), 3, 0)
        stats_layout.addWidget(self.games_drawn_label, 3, 1)
        stats_layout.addWidget(QLabel("Win Rate:"), 4, 0)
        stats_layout.addWidget(self.win_rate_label, 4, 1)
        
        self.reset_stats_btn = QPushButton("Reset Statistics")
        self.reset_stats_btn.clicked.connect(self._on_reset_stats)
        stats_layout.addWidget(self.reset_stats_btn, 5, 0, 1, 2)
        
        right_layout.addWidget(stats_group)
        
        # Add stretch at bottom to push content up
        right_layout.addStretch()
        
        # Set widget to scroll area and add to main layout
        right_scroll.setWidget(right_widget)
        main_layout.addWidget(right_scroll)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Lichess Autobot - Ready")
        
        # Update stats display
        self._update_stats_display()
    
    def _connect_signals(self):
        """Connect async signals to slots"""
        self.signals.game_started.connect(self._handle_game_started)
        self.signals.game_state_updated.connect(self._handle_game_state_updated)
        self.signals.game_finished.connect(self._handle_game_finished)
        self.signals.error_occurred.connect(self._show_error)
        self.signals.status_changed.connect(self._update_status)
        self.signals.stats_updated.connect(self._update_stats_display)
    
    def _load_settings(self):
        """Load settings from database"""
        # Load token
        token = self.db.get_bearer_token()
        if token:
            self.token_input.setText(token)
        
        # Load rated mode
        rated = self.db.get_rated_mode()
        self.rated_checkbox.setChecked(rated)
        
        # Load time control
        last_tc = self.db.get_last_time_control()
        for i in range(self.time_control_combo.count()):
            tc = self.time_control_combo.itemData(i)
            if tc.name == last_tc:
                self.time_control_combo.setCurrentIndex(i)
                break
        
        # Load max move time settings (min/max ranges)
        for setting, spinner in [
            ("opening_time_min", self.opening_time_min_spin),
            ("opening_time_max", self.opening_time_max_spin),
            ("midgame_time_min", self.midgame_time_min_spin),
            ("midgame_time_max", self.midgame_time_max_spin),
        ]:
            value = self.db.get_setting(setting)
            if value:
                try:
                    spinner.setValue(float(value))
                except ValueError:
                    pass

        # Load single node setting
        single_node = self.db.get_setting("single_node")
        self.single_node_checkbox.setChecked(single_node == "true")
        
        # Load eval toggle setting (default to enabled)
        eval_enabled = self.db.get_setting("eval_enabled")
        eval_is_enabled = eval_enabled != "false"  # Default to true if not set
        self.eval_toggle.setChecked(eval_is_enabled)
        
        # Show/hide eval bar based on toggle state
        if eval_is_enabled:
            self.evaluation_widget.show()
        else:
            self.evaluation_widget.hide()

        # Load evaluation engine selection (done after _scan_engines populates the combo)
        # This is handled in _scan_engines to ensure engines are available first
    
    def _save_settings(self):
        """Save current settings to database"""
        self.db.set_bearer_token(self.token_input.text())
        self.db.set_rated_mode(self.rated_checkbox.isChecked())
        
        tc = self.time_control_combo.currentData()
        if tc:
            self.db.set_last_time_control(tc.name)
        
        # Save selected playing engine
        engine_path = self.engine_combo.currentData()
        if engine_path:
            self.db.set_last_engine(engine_path)
        
        # Save selected evaluation engine
        eval_engine_path = self.eval_engine_combo.currentData()
        self.db.set_setting("last_eval_engine", eval_engine_path or "")
        
        # Save max move time settings (min/max ranges)
        self.db.set_setting("opening_time_min", str(self.opening_time_min_spin.value()))
        self.db.set_setting("opening_time_max", str(self.opening_time_max_spin.value()))
        self.db.set_setting("midgame_time_min", str(self.midgame_time_min_spin.value()))
        self.db.set_setting("midgame_time_max", str(self.midgame_time_max_spin.value()))

        # Save single node setting
        self.db.set_setting("single_node", "true" if self.single_node_checkbox.isChecked() else "false")
        
        # Save eval toggle setting
        self.db.set_setting("eval_enabled", "true" if self.eval_toggle.isChecked() else "false")

    def _scan_engines(self):
        """Scan for available chess engines"""
        self.engine_combo.clear()
        
        # Also update evaluation engine combo
        self.eval_engine_combo.clear()
        self.eval_engine_combo.addItem("None (no evaluation)", None)
        
        scanner = EngineScanner(self.engines_dir)
        engines = scanner.get_engine_names()
        
        if not engines:
            self.engine_combo.addItem("No engines found", None)
            self.db.log_warning("No chess engines found in engines directory")
        else:
            for name, path in engines:
                self.engine_combo.addItem(name, path)
                self.eval_engine_combo.addItem(name, path)
            
            # Restore last selected playing engine (gracefully handle missing engines)
            last_engine = self.db.get_last_engine()
            if last_engine:
                found = False
                for i in range(self.engine_combo.count()):
                    if self.engine_combo.itemData(i) == last_engine:
                        self.engine_combo.setCurrentIndex(i)
                        found = True
                        break
                if not found:
                    self.db.log_warning(f"Previously selected engine not found: {last_engine}")
            
            # Restore last selected evaluation engine (gracefully handle missing engines)
            last_eval_engine = self.db.get_setting("last_eval_engine", "")
            if last_eval_engine:
                found = False
                for i in range(self.eval_engine_combo.count()):
                    if self.eval_engine_combo.itemData(i) == last_eval_engine:
                        self.eval_engine_combo.setCurrentIndex(i)
                        found = True
                        break
                if not found:
                    self.db.log_warning(f"Previously selected eval engine not found: {last_eval_engine}")
            
            self.db.log_info(f"Found {len(engines)} chess engine(s)")
    
    def _on_settings_changed(self, *args):
        """Handle any settings change - save to database"""
        # Don't save during initialization
        if self._loading_settings:
            return
        self._save_settings()
    
    def _on_eval_toggle_changed(self, checked: bool):
        """Handle evaluation toggle switch change"""
        if not self._loading_settings:
            self._save_settings()
        
        if checked:
            # Enable evaluation - show eval bar and start eval engine if one is selected
            self.evaluation_widget.show()
            asyncio.ensure_future(self._update_eval_engine())
        else:
            # Disable evaluation - hide eval bar, stop the evaluation
            self.evaluation_widget.hide()
            self._stop_current_analysis()
    
    def _on_eval_engine_changed(self, index: int):
        """Handle evaluation engine selection change"""
        # Save settings when eval engine changes
        if not self._loading_settings:
            self._save_settings()
        # Only start engine if eval toggle is on
        if self.eval_toggle.isChecked():
            asyncio.ensure_future(self._update_eval_engine())
    
    async def _update_eval_engine(self):
        """Update the evaluation engine"""
        # Don't start if evaluation is disabled
        if not self.eval_toggle.isChecked():
            return
            
        # Stop existing eval engine if any
        # Stop any running analysis first
        self._stop_current_analysis()
        
        if self.eval_engine:
            try:
                await asyncio.wait_for(self.eval_engine.stop(), timeout=2.0)
            except:
                pass
            self.eval_engine = None
        
        # Get selected engine
        eval_path = self.eval_engine_combo.currentData()
        if not eval_path:
            self.evaluation_widget.set_no_engine()
            return
        
        # Start new eval engine
        try:
            self._update_status("Starting evaluation engine...")
            self.eval_engine = UCIEngine(eval_path)
            await self.eval_engine.start()
            self.db.log_info(f"Evaluation engine started: {self.eval_engine.name}")
            self._update_status("Ready")
            
            # Save the selection
            self._save_settings()
            
            # If we have a game in progress (check game_id or if board has moves), start evaluation
            # Clear last eval FEN to force re-evaluation
            self._last_eval_fen = None
            if self.current_game_id or self.chess_board.get_live_ply() > 0:
                self._start_evaluation()
        except Exception as e:
            self.db.log_error("Failed to start evaluation engine", str(e))
            self.evaluation_widget.set_no_engine()
            self._update_status("Ready")

    def _start_evaluation(self):
        """Start or restart position evaluation"""
        # Check if evaluation is enabled
        if not self.eval_toggle.isChecked():
            return
            
        if not self.eval_engine or not self.eval_engine.is_running:
            return
        
        # Get current position FEN
        board = self.chess_board.get_board()
        current_fen = board.fen()
        
        # Skip if same position already being evaluated
        if current_fen == self._last_eval_fen:
            return
        
        # Cancel existing eval task and analysis
        self._stop_current_analysis()
        
        self._last_eval_fen = current_fen
        self.evaluation_widget.set_analyzing()
        self.eval_task = asyncio.ensure_future(self._run_evaluation())
    
    def _stop_current_analysis(self):
        """Stop any running analysis"""
        # Cancel the eval task
        if self.eval_task and not self.eval_task.done():
            self.eval_task.cancel()
        
        # Stop the analysis context if it exists
        if self._eval_analysis:
            try:
                self._eval_analysis.stop()
            except:
                pass
            self._eval_analysis = None
    
    async def _run_evaluation(self):
        """Run continuous position evaluation with periodic updates"""
        try:
            # Get the currently displayed board
            board = self.chess_board.get_board()
            
            if board.is_game_over():
                # Show terminal eval
                if board.is_checkmate():
                    if board.turn == chess.WHITE:
                        self.evaluation_widget.set_evaluation(mate_in=-0)  # Black won
                    else:
                        self.evaluation_widget.set_evaluation(mate_in=0)  # White won
                else:
                    self.evaluation_widget.set_evaluation(centipawns=0)  # Draw
                return
            
            # Start continuous analysis (no time limit - runs until stopped)
            try:
                # Use analysis() for continuous evaluation
                self._eval_analysis = await self.eval_engine.engine.analysis(board)
                
                last_update_time = 0
                update_interval = 0.5  # Update UI every 0.5 seconds
                
                async for info in self._eval_analysis:
                    import time
                    current_time = time.monotonic()
                    
                    # Only update UI at the specified interval
                    if current_time - last_update_time >= update_interval:
                        last_update_time = current_time
                        
                        score = info.get('score')
                        if score:
                            # Get score from white's perspective for consistent display
                            white_score = score.white()
                            if white_score.is_mate():
                                mate_in = white_score.mate()
                                self.evaluation_widget.set_evaluation(mate_in=mate_in)
                            else:
                                cp = white_score.score()
                                if cp is not None:
                                    self.evaluation_widget.set_evaluation(centipawns=cp)
                    
                    # Small yield to prevent blocking
                    await asyncio.sleep(0.01)
                    
            except asyncio.CancelledError:
                raise  # Re-raise to be handled by outer try
            except Exception as e:
                self.db.log_warning(f"Analysis error: {e}")
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.db.log_warning(f"Evaluation error: {e}")
        finally:
            # Clean up analysis context
            if self._eval_analysis:
                try:
                    self._eval_analysis.stop()
                except:
                    pass
                self._eval_analysis = None
    
    def _on_move_selected(self, ply: int):
        """Handle move selection from move list"""
        self.chess_board.navigate_to_ply(ply)
        board = self.chess_board.get_board()
        self._update_captured_pieces(board)
        self._start_evaluation()
    
    def _on_jump_to_live(self):
        """Handle jump to live position"""
        self.chess_board.jump_to_live()
        board = self.chess_board.get_board()
        self._update_captured_pieces(board)
        self._start_evaluation()
    
    def _update_player_displays(self):
        """Update player info widgets based on board orientation"""
        if self.chess_board.flipped:
            # Black on bottom, white on top
            top_info = self.white_player
            bottom_info = self.black_player
            top_time = self.white_time_ms
            bottom_time = self.black_time_ms
            top_active = self.game_board and self.game_board.turn == chess.WHITE
            bottom_active = self.game_board and self.game_board.turn == chess.BLACK
        else:
            # White on bottom, black on top
            top_info = self.black_player
            bottom_info = self.white_player
            top_time = self.black_time_ms
            bottom_time = self.white_time_ms
            top_active = self.game_board and self.game_board.turn == chess.BLACK
            bottom_active = self.game_board and self.game_board.turn == chess.WHITE
        
        # Update top player
        self.top_player.set_player_info(
            name=top_info.get("username", "Waiting..."),
            rating=top_info.get("rating", 0),
            title=top_info.get("title", "")
        )
        self.top_player.set_time(top_time)
        self.top_player.set_active(top_active if self.current_game_id else False)
        
        # Update bottom player
        self.bottom_player.set_player_info(
            name=bottom_info.get("username", "Waiting..."),
            rating=bottom_info.get("rating", 0),
            title=bottom_info.get("title", "")
        )
        self.bottom_player.set_time(bottom_time)
        self.bottom_player.set_active(bottom_active if self.current_game_id else False)
    
    def _update_captured_pieces(self, board: chess.Board):
        """Update captured pieces display for both players"""
        # Count pieces on the board
        white_pieces = {}
        black_pieces = {}
        
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            white_pieces[piece_type] = len(board.pieces(piece_type, chess.WHITE))
            black_pieces[piece_type] = len(board.pieces(piece_type, chess.BLACK))
        
        # Starting piece counts
        starting_counts = {
            chess.PAWN: 8,
            chess.KNIGHT: 2,
            chess.BISHOP: 2,
            chess.ROOK: 2,
            chess.QUEEN: 1,
        }
        
        # Calculate captured pieces
        white_captured = {}  # Black pieces captured by white
        black_captured = {}  # White pieces captured by black
        
        for piece_type, start_count in starting_counts.items():
            # Black pieces captured = starting - remaining
            captured_by_white = start_count - black_pieces[piece_type]
            if captured_by_white > 0:
                white_captured[piece_type] = captured_by_white
            
            # White pieces captured = starting - remaining
            captured_by_black = start_count - white_pieces[piece_type]
            if captured_by_black > 0:
                black_captured[piece_type] = captured_by_black
        
        # Calculate material totals
        white_material = sum(PIECE_VALUES[pt] * white_pieces[pt] for pt in white_pieces)
        black_material = sum(PIECE_VALUES[pt] * black_pieces[pt] for pt in black_pieces)
        material_diff = white_material - black_material  # Positive if white is ahead
        
        # Determine which player is on top/bottom based on board orientation
        if self.chess_board.flipped:
            # Black on bottom, white on top
            self.top_player.set_player_color(True)  # Top is white
            self.bottom_player.set_player_color(False)  # Bottom is black
            self.top_player.set_captured_pieces(white_captured, material_diff if material_diff > 0 else 0)
            self.bottom_player.set_captured_pieces(black_captured, -material_diff if material_diff < 0 else 0)
        else:
            # White on bottom, black on top
            self.top_player.set_player_color(False)  # Top is black
            self.bottom_player.set_player_color(True)  # Bottom is white
            self.top_player.set_captured_pieces(black_captured, -material_diff if material_diff < 0 else 0)
            self.bottom_player.set_captured_pieces(white_captured, material_diff if material_diff > 0 else 0)
    
    def _on_engine_options(self):
        """Open engine options dialog"""
        engine_path = self.engine_combo.currentData()
        if not engine_path:
            QMessageBox.warning(self, "No Engine", "Please select an engine first.")
            return
        
        # We need to start the engine temporarily to discover its options
        asyncio.ensure_future(self._show_engine_options_async(engine_path))
    
    async def _show_engine_options_async(self, engine_path: str):
        """Async method to discover options and show dialog"""
        self._update_status("Discovering engine options...")
        
        try:
            # Start engine temporarily
            temp_engine = UCIEngine(engine_path)
            await temp_engine.start()
            
            # Get options
            engine_name = temp_engine.name
            options = temp_engine.options
            
            # Stop engine
            await temp_engine.stop()
            
            if not options:
                QMessageBox.information(
                    self, "No Options",
                    f"{engine_name} does not expose any configurable UCI options."
                )
                self._update_status("Ready")
                return
            
            # Get saved options from database
            saved_options = self.db.get_engine_options(engine_path)
            
            # Show dialog
            dialog = EngineOptionsDialog(engine_name, options, saved_options, self)
            
            def on_options_changed(new_options: dict):
                # Save to database
                self.db.set_engine_options(engine_path, new_options)
                self.db.log_info(f"Saved {len(new_options)} options for {engine_name}")
            
            dialog.options_changed.connect(on_options_changed)
            dialog.exec()
            
            self._update_status("Ready")
            
        except Exception as e:
            self.db.log_error("Failed to get engine options", str(e))
            QMessageBox.warning(
                self, "Engine Error",
                f"Failed to start engine: {str(e)}"
            )
            self._update_status("Ready")
    
    def _update_stats_display(self):
        """Update the statistics display"""
        stats = self.db.get_statistics()
        
        self.games_played_label.setText(str(stats["games_played"]))
        self.games_won_label.setText(str(stats["games_won"]))
        self.games_lost_label.setText(str(stats["games_lost"]))
        self.games_drawn_label.setText(str(stats["games_drawn"]))
        
        if stats["games_played"] > 0:
            win_rate = (stats["games_won"] / stats["games_played"]) * 100
            self.win_rate_label.setText(f"{win_rate:.1f}%")
        else:
            self.win_rate_label.setText("N/A")
    
    def _update_status(self, message: str):
        """Update status bar"""
        self.status_bar.showMessage(message)
    
    def _show_error(self, title: str, message: str):
        """Show error message and log it"""
        self.db.log_error(title, message)
        QMessageBox.critical(self, title, message)
    
    def _on_validate_token(self):
        """Validate the bearer token"""
        token = self.token_input.text().strip()
        if not token:
            self.token_status_label.setText("❌ Please enter a token")
            self.token_status_label.setStyleSheet("color: red; font-size: 11px;")
            return
        
        # Run validation asynchronously
        asyncio.ensure_future(self._validate_token_async(token))
    
    async def _validate_token_async(self, token: str):
        """Async token validation"""
        self.token_status_label.setText("⏳ Validating...")
        self.token_status_label.setStyleSheet("color: gray; font-size: 11px;")
        
        try:
            client = LichessClient(token)
            account = await client.get_account()
            await client.close()
            
            username = account.get("username", "Unknown")
            self.token_status_label.setText(f"✅ Valid - {username}")
            self.token_status_label.setStyleSheet("color: green; font-size: 11px;")
            
            self.db.set_bearer_token(token)
            self.db.log_info(f"Token validated for user: {username}")
            
        except LichessAPIError as e:
            self.token_status_label.setText(f"❌ Invalid token")
            self.token_status_label.setStyleSheet("color: red; font-size: 11px;")
            self.db.log_error("Token validation failed", str(e))
        except Exception as e:
            self.token_status_label.setText(f"❌ Error: {str(e)[:30]}")
            self.token_status_label.setStyleSheet("color: red; font-size: 11px;")
            self.db.log_error("Token validation error", str(e))
    
    def _on_start_bot(self):
        """Start the bot"""
        # Validate inputs
        token = self.token_input.text().strip()
        if not token:
            self._show_error("Missing Token", "Please enter your Lichess API token.")
            return
        
        engine_path = self.engine_combo.currentData()
        if not engine_path:
            self._show_error("No Engine", "Please select a chess engine.")
            return
        
        # Validate time ranges
        if not self._validate_time_settings():
            return
        
        # Reset stop after game flag
        self.stop_after_game = False
        self.stop_after_game_btn.setChecked(False)
        
        # Save settings
        self._save_settings()
        
        # Start the bot
        asyncio.ensure_future(self._start_bot_async(token, engine_path))
    
    def _validate_time_settings(self) -> bool:
        """Validate time range settings. Returns True if valid."""
        opening_min = self.opening_time_min_spin.value()
        opening_max = self.opening_time_max_spin.value()
        midgame_min = self.midgame_time_min_spin.value()
        midgame_max = self.midgame_time_max_spin.value()
        
        errors = []
        
        if opening_min > opening_max:
            errors.append("Opening: minimum time cannot be greater than maximum time")
        
        if midgame_min > midgame_max:
            errors.append("After move 10: minimum time cannot be greater than maximum time")
        
        if errors:
            self._show_error("Invalid Time Settings", "\n".join(errors))
            return False
        
        return True
    
    def _on_stop_after_game(self):
        """Toggle stop after current game"""
        self.stop_after_game = self.stop_after_game_btn.isChecked()
        
        if self.stop_after_game:
            self.db.log_info("Bot will stop after current game")
            self._update_status("Will stop after current game...")
            self.stop_after_game_btn.setText("⏸ Stopping After Game...")
        else:
            self.db.log_info("Cancelled stop after game")
            if self.current_game_id:
                self._update_status("Playing...")
            else:
                self._update_status("Seeking game...")
            self.stop_after_game_btn.setText("⏸ Stop After Game")
    
    async def _start_bot_async(self, token: str, engine_path: str):
        """Async bot startup"""
        try:
            self._update_status("Starting engine...")
            
            # Start the chess engine
            self.engine = UCIEngine(engine_path)
            await self.engine.start()
            self.db.log_info(f"Engine started: {self.engine.name}")
            
            # Apply saved engine options
            saved_options = self.db.get_engine_options(engine_path)
            if saved_options:
                self._update_status("Applying engine options...")
                # Convert string values back to appropriate types
                options_to_apply = {}
                for name, value in saved_options.items():
                    opt = self.engine.get_option(name)
                    if opt:
                        from engine import UCIOptionType
                        if opt.type == UCIOptionType.SPIN:
                            try:
                                options_to_apply[name] = int(value)
                            except ValueError:
                                options_to_apply[name] = value
                        elif opt.type == UCIOptionType.CHECK:
                            options_to_apply[name] = value.lower() in ('true', '1', 'yes')
                        else:
                            options_to_apply[name] = value
                    else:
                        options_to_apply[name] = value
                
                try:
                    await self.engine.set_options(options_to_apply)
                    self.db.log_info(f"Applied {len(options_to_apply)} engine options")
                except Exception as e:
                    self.db.log_warning(f"Some engine options could not be applied: {e}")
            
            self._update_status("Connecting to Lichess...")
            
            # Create Lichess client
            self.lichess_client = LichessClient(token)
            
            # Validate token
            account = await self.lichess_client.get_account()
            username = account.get("username", "Unknown")
            self.db.log_info(f"Connected to Lichess as {username}")
            
            # Update UI state
            self.is_running = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.stop_after_game_btn.setEnabled(True)
            self.token_input.setEnabled(False)
            self.engine_combo.setEnabled(False)
            self.engine_options_btn.setEnabled(False)
            self.single_node_checkbox.setEnabled(False)
            self.time_control_combo.setEnabled(False)
            self.rated_checkbox.setEnabled(False)
            self.opening_time_min_spin.setEnabled(False)
            self.opening_time_max_spin.setEnabled(False)
            self.midgame_time_min_spin.setEnabled(False)
            self.midgame_time_max_spin.setEnabled(False)
            
            self._update_status(f"Connected as {username}. Starting event stream...")
            
            # Start event stream
            self.event_stream_task = asyncio.create_task(self._run_event_stream())
            
            # Start seeking games
            await self._seek_game()
            
        except Exception as e:
            self.db.log_error("Failed to start bot", str(e))
            self._show_error("Start Failed", f"Failed to start bot: {str(e)}")
            await self._cleanup()
    
    async def _run_event_stream(self):
        """Run the event stream to listen for game events with auto-reconnect"""
        print("[DEBUG] _run_event_stream task started")  # Debug
        reconnect_delay = 1.0
        max_reconnect_delay = 30.0
        
        while self.is_running:
            try:
                self.db.log_debug("Starting event stream...")
                print("[DEBUG] About to call stream_events...")  # Debug
                await self.lichess_client.stream_events(
                    on_game_start=self._on_game_start,
                    on_game_finish=self._on_game_finish,
                    on_challenge=self._on_challenge
                )
                print("[DEBUG] stream_events returned")  # Debug
                # If stream ends normally, wait a bit and reconnect
                if self.is_running:
                    self.db.log_warning("Event stream ended, reconnecting...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
            except asyncio.CancelledError:
                print("[DEBUG] Event stream task cancelled")  # Debug
                break
            except Exception as e:
                print(f"[DEBUG] Event stream exception: {e}")  # Debug
                if self.is_running:
                    self.db.log_error("Event stream error", str(e))
                    # Wait before reconnecting
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                else:
                    break
    
    async def _on_game_start(self, game: Dict[str, Any]):
        """Handle game start event"""
        game_id = game.get("gameId") or game.get("id")
        if not game_id:
            return
        
        self.current_game_id = game_id
        self.our_color = game.get("color", "white")
        
        self.db.log_info(f"Game started: {game_id}", f"Playing as {self.our_color}")
        self.signals.game_started.emit(game)
        
        # Update game link
        game_url = f"https://lichess.org/{game_id}"
        self.game_link_label.setText(f'<a href="{game_url}" style="color: #5a9;">Open game in browser: {game_id}</a>')
        self.game_link_label.show()
        
        # Cancel seek if active
        if self.seek_task and not self.seek_task.done():
            self.seek_task.cancel()
        
        # Start game stream
        self.game_stream_task = asyncio.create_task(self._run_game_stream(game_id))
    
    async def _on_game_finish(self, game: Dict[str, Any]):
        """Handle game finish event"""
        game_id = game.get("gameId") or game.get("id")
        status = game.get("status", "unknown")
        
        self.db.log_info(f"Game finished: {game_id} ({status})")
        self.signals.game_finished.emit(game)
        
        # Check for abort/noStart - don't count in stats
        if status in ["aborted", "noStart"]:
            self._update_status(f"Game aborted ({status})")
            
            # Stop clocks
            self.top_player.clock.set_active(False)
            self.bottom_player.clock.set_active(False)
            
            # Reset game state
            self.current_game_id = None
            self.our_color = None
            self.game_board = None
            
            # Reset UI
            self.chess_board.reset()
            self.move_list.reset()
            self.evaluation_widget.reset()
            self.game_link_label.hide()
            
            # If still running, seek new game
            if self.is_running:
                await asyncio.sleep(2)
                await self._seek_game()
            return
        
        # Determine result
        winner = game.get("winner")
        
        if winner == self.our_color:
            result = "win"
        elif winner is not None:
            result = "loss"
        else:
            result = "draw"
        
        # Update stats
        self.db.update_statistics(result)
        
        # Get opponent info
        opponent = game.get("opponent", {})
        opponent_name = opponent.get("username", "Unknown")
        
        # Add to game history
        tc = self.time_control_combo.currentData()
        self.db.add_game(
            game_id=game_id,
            opponent=opponent_name,
            color=self.our_color or "unknown",
            result=result,
            time_control=tc.name if tc else "unknown",
            rated=self.rated_checkbox.isChecked()
        )
        
        self.signals.stats_updated.emit()
        
        # Stop clocks
        self.top_player.clock.set_active(False)
        self.bottom_player.clock.set_active(False)
        
        # Reset game state
        self.current_game_id = None
        self.our_color = None
        self.game_board = None
        
        # Check if we should stop after this game
        if self.stop_after_game:
            self.db.log_info("Stopping bot after game as requested")
            self._on_stop_bot()
            return
        
        # If still running, seek new game
        if self.is_running:
            await asyncio.sleep(2)  # Brief pause between games
            await self._seek_game()
    
    async def _on_challenge(self, challenge: Dict[str, Any]):
        """Handle incoming challenge"""
        # For now, decline challenges (we create seeks instead)
        challenge_id = challenge.get("id")
        if challenge_id:
            await self.lichess_client.decline_challenge(challenge_id, "generic")
            self.db.log_info(f"Declined challenge: {challenge_id}")
    
    async def _run_game_stream(self, game_id: str):
        """Stream game state"""
        try:
            await self.lichess_client.stream_game(
                game_id,
                on_game_full=self._on_game_full,
                on_game_state=self._on_game_state
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self.is_running:
                self.db.log_error("Game stream error", str(e))
    
    async def _on_game_full(self, event: Dict[str, Any]):
        """Handle full game state"""
        self.game_board = chess.Board()
        
        # Get player information
        white = event.get("white", {})
        black = event.get("black", {})
        
        self.white_player = {
            "username": white.get("name", white.get("id", "White")),
            "rating": white.get("rating", 0),
            "title": white.get("title", "")
        }
        self.black_player = {
            "username": black.get("name", black.get("id", "Black")),
            "rating": black.get("rating", 0),
            "title": black.get("title", "")
        }
        
        # Set up board orientation (our color at bottom)
        self.chess_board.set_flipped(self.our_color == "black")
        
        # Set up eval bar orientation (our color at bottom)
        self.evaluation_widget.set_flipped(self.our_color == "black")
        
        # Process initial state
        state = event.get("state", {})
        moves = state.get("moves", "")
        
        # Get initial times
        self.white_time_ms = state.get("wtime", 600000)
        self.black_time_ms = state.get("btime", 600000)
        
        if moves:
            self.chess_board.set_position_from_moves(moves)
            self.game_board = self.chess_board.get_live_board()
        else:
            self.chess_board.reset()
            self.game_board = chess.Board()
        
        # Update UI
        self.move_list.set_moves(self.game_board)
        self._update_captured_pieces(self.game_board)
        self._update_player_displays()
        
        # Start evaluation
        self._start_evaluation()
        
        # Make move if it's our turn
        await self._maybe_make_move(state)
    
    async def _on_game_state(self, event: Dict[str, Any]):
        """Handle game state update"""
        moves = event.get("moves", "")
        status = event.get("status", "started")
        
        # Check for game ending statuses
        if status in ["aborted", "noStart"]:
            await self._on_game_aborted(status)
            return
        
        if status in ["mate", "resign", "stalemate", "timeout", "draw", "outoftime", "cheat", "variantEnd"]:
            # Game ended - update the board with final moves before returning
            self.chess_board.set_position_from_moves(moves)
            self.game_board = self.chess_board.get_live_board()
            self.move_list.set_moves(self.game_board)
            self._update_captured_pieces(self.game_board)
            self._update_player_displays()
            self._start_evaluation()
            
            self._update_status(f"Game ended: {status}")
            # This will be handled by _on_game_finish from event stream
            return
        
        # Update times
        self.white_time_ms = event.get("wtime", self.white_time_ms)
        self.black_time_ms = event.get("btime", self.black_time_ms)
        
        # Update board
        self.chess_board.set_position_from_moves(moves)
        self.game_board = self.chess_board.get_live_board()
        
        # Update UI
        self.move_list.set_moves(self.game_board)
        self._update_captured_pieces(self.game_board)
        self._update_player_displays()
        
        # If viewing live, update evaluation
        if self.chess_board.is_viewing_live:
            self._start_evaluation()
        
        self.signals.game_state_updated.emit(event)
        
        # Check if game is still ongoing
        if status not in ["started", "created"]:
            return
        
        # Make move if it's our turn
        await self._maybe_make_move(event)
    
    async def _on_game_aborted(self, reason: str):
        """Handle game abort"""
        self.db.log_info(f"Game aborted: {reason}")
        self._update_status(f"Game aborted ({reason})")
        
        # Stop clocks
        self.top_player.clock.set_active(False)
        self.bottom_player.clock.set_active(False)
        
        # Reset game state
        self.current_game_id = None
        self.our_color = None
        self.game_board = None
        
        # Reset board to starting position
        self.chess_board.reset()
        self.move_list.reset()
        self.evaluation_widget.reset()
        self.game_link_label.hide()
        
        # If still running, seek new game after a brief pause
        if self.is_running:
            await asyncio.sleep(2)
            await self._seek_game()
    
    async def _maybe_make_move(self, state: Dict[str, Any]):
        """Make a move if it's our turn"""
        if not self.game_board or not self.engine or not self.current_game_id:
            return
        
        # Check if game is over
        if self.game_board.is_game_over():
            return
        
        # Check if it's our turn
        is_white_turn = self.game_board.turn == chess.WHITE
        is_our_turn = (is_white_turn and self.our_color == "white") or \
                      (not is_white_turn and self.our_color == "black")
        
        if not is_our_turn:
            self._update_status("Waiting for opponent...")
            return
        
        self._update_status("Thinking...")
        
        try:
            import time
            import random
            
            # Record start time for throttling
            think_start_time = time.monotonic()
            
            # Get time information
            wtime = state.get("wtime", 60000)
            btime = state.get("btime", 60000)
            winc = state.get("winc", 0)
            binc = state.get("binc", 0)
            
            # Determine which time range to use based on move number
            # fullmove_number is the move number (1 for first move, etc.)
            move_number = self.game_board.fullmove_number
            
            if move_number <= 10:
                time_min = self.opening_time_min_spin.value()
                time_max = self.opening_time_max_spin.value()
            else:
                time_min = self.midgame_time_min_spin.value()
                time_max = self.midgame_time_max_spin.value()
            
            # Random target time between min and max for human-like play
            target_move_time = random.uniform(time_min, time_max)
            
            # Get best move from engine with max time limit
            # If single node mode is enabled (for engines like Maia), use nodes=1
            nodes_limit = 1 if self.single_node_checkbox.isChecked() else None
            move = await self.engine.get_best_move(
                self.game_board,
                time_limit=time_max,  # Cap engine thinking to max time
                nodes=nodes_limit,
                wtime=wtime,
                btime=btime,
                winc=winc,
                binc=binc
            )
            
            if move:
                move_uci = move.uci()
                self.db.log_debug(f"Engine move: {move_uci}")
                
                # Throttling: ensure we don't play faster than target_move_time
                elapsed = time.monotonic() - think_start_time
                remaining_wait = target_move_time - elapsed
                
                if remaining_wait > 0:
                    self._update_status(f"Move ready, waiting {remaining_wait:.1f}s...")
                    await asyncio.sleep(remaining_wait)
                
                # Make the move on Lichess
                success = await self.lichess_client.make_move(self.current_game_id, move_uci)
                
                if success:
                    total_time = time.monotonic() - think_start_time
                    self._update_status(f"Played: {move_uci} ({total_time:.1f}s)")
                else:
                    self.db.log_warning(f"Move may have failed: {move_uci}")
            else:
                self.db.log_warning("Engine returned no move")
                
        except Exception as e:
            self.db.log_error("Error making move", str(e))
    
    async def _seek_game(self):
        """Create a seek to find a game"""
        if not self.is_running or not self.lichess_client:
            return
        
        tc = self.time_control_combo.currentData()
        rated = self.rated_checkbox.isChecked()
        
        self._update_status(f"Seeking {tc.name} game...")
        self.db.log_info(f"Creating seek: {tc.name}, rated={rated}")
        
        try:
            self.seek_task = asyncio.create_task(
                self.lichess_client.create_seek(tc, rated=rated)
            )
            await self.seek_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self.is_running:
                self.db.log_error("Seek error", str(e))
                self.signals.error_occurred.emit("Seek Failed", str(e))
    
    def _on_stop_bot(self):
        """Stop the bot"""
        # Check if there's an ongoing game - warn user about resignation
        if self.current_game_id:
            reply = QMessageBox.warning(
                self,
                "Game In Progress",
                "You have a game in progress. Stopping now will resign the current game.\n\n"
                "Are you sure you want to stop?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No  # Default to No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return  # User cancelled
        
        # Disable stop button immediately to prevent double-clicks
        self.stop_btn.setEnabled(False)
        self.stop_after_game_btn.setEnabled(False)
        self.stop_btn.setText("⏹ Stopping...")
        asyncio.ensure_future(self._stop_bot_async())
    
    async def _stop_bot_async(self):
        """Async bot shutdown"""
        self._update_status("Stopping bot...")
        self.is_running = False
        
        # Signal the lichess client to stop streams immediately
        if self.lichess_client:
            self.lichess_client.request_stop()
        
        # If there's an ongoing game, try to abort it first (works in first few moves)
        # If abort fails, resign the game
        if self.current_game_id and self.lichess_client:
            try:
                self._update_status("Aborting game...")
                aborted = await asyncio.wait_for(
                    self.lichess_client.abort_game(self.current_game_id),
                    timeout=3.0
                )
                if aborted:
                    self.db.log_info(f"Aborted game: {self.current_game_id}")
                else:
                    # Abort failed (probably game too far along), try resign
                    self._update_status("Resigning game...")
                    await asyncio.wait_for(
                        self.lichess_client.resign_game(self.current_game_id),
                        timeout=3.0
                    )
                    self.db.log_info(f"Resigned game: {self.current_game_id}")
            except asyncio.TimeoutError:
                self.db.log_warning("Timeout while trying to abort/resign game")
            except Exception as e:
                self.db.log_warning(f"Could not abort/resign game: {e}")
        
        await self._cleanup()
        
        self.stop_btn.setText("⏹ Stop Bot")
        self._update_status("Bot stopped")
        self.db.log_info("Bot stopped")
    
    async def _cleanup(self):
        """Clean up resources with timeouts to ensure responsive shutdown"""
        # Cancel all tasks
        tasks_to_cancel = [t for t in [self.event_stream_task, self.game_stream_task, self.seek_task, self.eval_task]
                          if t and not t.done()]
        
        for task in tasks_to_cancel:
            task.cancel()
        
        # Wait for tasks with a timeout
        if tasks_to_cancel:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                    timeout=3.0
                )
            except asyncio.TimeoutError:
                self.db.log_warning("Some tasks did not terminate cleanly")
        
        # Stop playing engine with timeout
        if self.engine:
            try:
                await asyncio.wait_for(self.engine.stop(), timeout=2.0)
            except asyncio.TimeoutError:
                self.db.log_warning("Engine stop timed out")
            except Exception:
                pass
            self.engine = None
        
        # Note: eval_engine is kept running if user wants to analyze positions after game
        
        # Close Lichess client with timeout
        if self.lichess_client:
            try:
                await asyncio.wait_for(self.lichess_client.close(), timeout=3.0)
            except asyncio.TimeoutError:
                self.db.log_warning("Lichess client close timed out")
            except Exception:
                pass
            self.lichess_client = None
        
        # Reset state
        self.current_game_id = None
        self.our_color = None
        self.game_board = None
        self.is_running = False
        
        # Stop clocks
        self.top_player.clock.set_active(False)
        self.bottom_player.clock.set_active(False)
        
        # Update UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("⏹ Stop Bot")
        self.stop_after_game_btn.setEnabled(False)
        self.stop_after_game_btn.setChecked(False)
        self.stop_after_game_btn.setText("⏸ Stop After Game")
        self.stop_after_game = False
        self.token_input.setEnabled(True)
        self.engine_combo.setEnabled(True)
        self.engine_options_btn.setEnabled(True)
        self.single_node_checkbox.setEnabled(True)
        self.time_control_combo.setEnabled(True)
        self.rated_checkbox.setEnabled(True)
        self.opening_time_min_spin.setEnabled(True)
        self.opening_time_max_spin.setEnabled(True)
        self.midgame_time_min_spin.setEnabled(True)
        self.midgame_time_max_spin.setEnabled(True)
    
    def _on_reset_stats(self):
        """Reset statistics"""
        reply = QMessageBox.question(
            self, "Reset Statistics",
            "Are you sure you want to reset all statistics?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.db.reset_statistics()
            self._update_stats_display()
            self.db.log_info("Statistics reset")
    
    def _handle_game_started(self, game: Dict[str, Any]):
        """Handle game started signal"""
        game_id = game.get("gameId") or game.get("id")
        opponent = game.get("opponent", {})
        opponent_name = opponent.get("username", "Unknown")
        
        self._update_status(f"Game started vs {opponent_name}")
        
        # Reset board and move list
        self.chess_board.reset()
        self.move_list.clear()
    
    def _handle_game_state_updated(self, state: Dict[str, Any]):
        """Handle game state update signal"""
        pass  # Board is updated in the async handler
    
    def _handle_game_finished(self, game: Dict[str, Any]):
        """Handle game finished signal"""
        winner = game.get("winner")
        status = game.get("status", {})
        
        if winner == self.our_color:
            result_text = "You won!"
            result_notation = "1-0" if self.our_color == "white" else "0-1"
        elif winner is not None:
            result_text = "You lost"
            result_notation = "0-1" if self.our_color == "white" else "1-0"
        else:
            result_text = "Draw"
            result_notation = "½-½"
        
        self.move_list.add_result(result_notation)
        self._update_status(f"Game finished - {result_text}")
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events for move navigation"""
        if event.key() == Qt.Key.Key_Left:
            self.move_list._on_prev()
        elif event.key() == Qt.Key.Key_Right:
            self.move_list._on_next()
        elif event.key() == Qt.Key.Key_Home:
            self.move_list._on_start()
        elif event.key() == Qt.Key.Key_End:
            self.move_list._on_end()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.is_running:
            reply = QMessageBox.question(
                self, "Quit",
                "Bot is still running. Stop and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            
            # Stop the bot synchronously
            self.is_running = False
        
        # Stop eval engine
        if self.eval_engine:
            try:
                asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(self.eval_engine.stop(), timeout=1.0)
                )
            except:
                pass
        
        # Save settings
        self._save_settings()
        
        # Accept close
        event.accept()
