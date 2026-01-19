"""
Player Info Widget for Lichess Autobot
Displays player name, rating, and clock
"""

from typing import Optional, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

import chess

# Piece values for material calculation
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

# Unicode symbols for pieces
PIECE_SYMBOLS_WHITE = {
    chess.PAWN: '♙',
    chess.KNIGHT: '♘',
    chess.BISHOP: '♗',
    chess.ROOK: '♖',
    chess.QUEEN: '♕',
}

PIECE_SYMBOLS_BLACK = {
    chess.PAWN: '♟',
    chess.KNIGHT: '♞',
    chess.BISHOP: '♝',
    chess.ROOK: '♜',
    chess.QUEEN: '♛',
}


class ClockWidget(QFrame):
    """Chess clock display widget"""
    
    time_expired = pyqtSignal()  # Signal when time runs out
    
    def __init__(self, is_top: bool = False, parent=None):
        super().__init__(parent)
        self.is_top = is_top
        self.time_ms: int = 0
        self.is_active = False
        self.is_ticking = False
        self._last_style_state: str = ""  # Track style state to avoid redundant updates
        
        # Timer for countdown
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.setInterval(100)  # Update every 100ms
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the clock UI"""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.time_label = QLabel("--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setFont(QFont("Consolas", 24, QFont.Weight.Bold))
        
        layout.addWidget(self.time_label)
        
        self._update_style(force=True)
        self.setMinimumHeight(50)
    
    def _get_style_state(self) -> str:
        """Get a key representing the current style state"""
        if not self.is_active:
            return "inactive"
        elif self.time_ms <= 30000:
            return "active_low"
        else:
            return "active_ok"
    
    def _update_style(self, force: bool = False):
        """Update the clock style based on state"""
        style_state = self._get_style_state()
        
        # Only update if style state changed
        if not force and style_state == self._last_style_state:
            return
        
        self._last_style_state = style_state
        
        if self.is_active:
            bg_color = "#2d5a27" if self.time_ms > 30000 else "#8b0000"  # Green or red
            text_color = "white"
        else:
            bg_color = "#3a3a3a"
            text_color = "#888888"
        
        self.setStyleSheet(f"""
            ClockWidget {{
                background-color: {bg_color};
                border-radius: 5px;
            }}
        """)
        self.time_label.setStyleSheet(f"color: {text_color};")
    
    def set_time(self, time_ms: int):
        """Set the current time in milliseconds"""
        new_time = max(0, time_ms)
        if new_time == self.time_ms:
            return  # No change
        self.time_ms = new_time
        self._update_display()
        self._update_style()  # Style might change if crossing 30s threshold
    
    def set_active(self, active: bool):
        """Set whether this clock is currently active (running)"""
        if self.is_active == active:
            return  # No change
        
        self.is_active = active
        if active and not self.is_ticking:
            self.is_ticking = True
            self._tick_timer.start()
        elif not active and self.is_ticking:
            self.is_ticking = False
            self._tick_timer.stop()
        self._update_style()
    
    def _tick(self):
        """Called every 100ms to update the display"""
        if self.is_active and self.time_ms > 0:
            self.time_ms = max(0, self.time_ms - 100)
            self._update_display()
            self._update_style()  # Will only update if state changed
            
            if self.time_ms == 0:
                self.time_expired.emit()
    
    def _update_display(self):
        """Update the time display"""
        total_seconds = self.time_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        
        if self.time_ms < 20000:  # Show tenths under 20 seconds
            tenths = (self.time_ms % 1000) // 100
            self.time_label.setText(f"{minutes:02d}:{seconds:02d}.{tenths}")
        else:
            self.time_label.setText(f"{minutes:02d}:{seconds:02d}")
    
    def reset(self):
        """Reset the clock"""
        self.time_ms = 0
        self.is_active = False
        self.is_ticking = False
        self._tick_timer.stop()
        self.time_label.setText("--:--")
        self._update_style()


class PlayerInfoWidget(QFrame):
    """
    Widget displaying player information including:
    - Player name
    - Rating
    - Clock
    """
    
    def __init__(self, is_top: bool = False, parent=None):
        super().__init__(parent)
        self.is_top = is_top
        self.player_name = ""
        self.player_rating = 0
        self.player_title = ""
        self.captured_pieces: Dict[int, int] = {}  # piece_type -> count
        self.material_advantage: int = 0  # Positive if this player is ahead
        self.is_white_pieces = True  # Whether this player plays white (affects piece symbols)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the player info UI"""
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)
        
        # Player info section (left)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        # Name and title row
        name_row = QHBoxLayout()
        name_row.setSpacing(5)
        
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #bf811d;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.title_label.hide()
        
        self.name_label = QLabel("Waiting...")
        self.name_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 14px;
            }
        """)
        
        name_row.addWidget(self.title_label)
        name_row.addWidget(self.name_label)
        name_row.addStretch()
        
        info_layout.addLayout(name_row)
        
        # Rating
        self.rating_label = QLabel("")
        self.rating_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 12px;
            }
        """)
        info_layout.addWidget(self.rating_label)
        
        main_layout.addLayout(info_layout, stretch=1)
        
        # Captured pieces section (before clock)
        captured_layout = QHBoxLayout()
        captured_layout.setSpacing(3)
        
        # Captured pieces label
        self.captured_label = QLabel("")
        self.captured_label.setFont(QFont("Segoe UI Symbol", 12))
        self.captured_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        captured_layout.addWidget(self.captured_label)
        
        # Material advantage label
        self.advantage_label = QLabel("")
        self.advantage_label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.advantage_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.advantage_label.setMinimumWidth(25)
        captured_layout.addWidget(self.advantage_label)
        
        main_layout.addLayout(captured_layout)
        
        # Clock (right)
        self.clock = ClockWidget(is_top=self.is_top)
        self.clock.setMinimumWidth(120)
        self.clock.setMaximumWidth(150)
        main_layout.addWidget(self.clock)
        
        self.setMaximumHeight(70)
    
    def set_player_info(self, name: str, rating: int = 0, title: str = ""):
        """Set player information"""
        # Only update if values changed
        if name == self.player_name and rating == self.player_rating and title == self.player_title:
            return
        
        if name != self.player_name:
            self.player_name = name
            self.name_label.setText(name)
        
        if title != self.player_title:
            self.player_title = title
            if title:
                self.title_label.setText(title)
                self.title_label.show()
            else:
                self.title_label.hide()
        
        if rating != self.player_rating:
            self.player_rating = rating
            if rating > 0:
                self.rating_label.setText(f"({rating})")
            else:
                self.rating_label.setText("")
    
    def set_time(self, time_ms: int):
        """Set the clock time"""
        self.clock.set_time(time_ms)
    
    def set_active(self, active: bool):
        """Set whether this player's clock is active"""
        self.clock.set_active(active)
    
    def set_player_color(self, is_white: bool):
        """Set the player's piece color (for displaying captured pieces)"""
        self.is_white_pieces = is_white
    
    def set_captured_pieces(self, captured: Dict[int, int], advantage: int):
        """Set the captured pieces and material advantage
        
        Args:
            captured: Dict mapping piece_type to count (pieces this player captured)
            advantage: Positive if this player is ahead in material, 0 or negative otherwise
        """
        # Update captured pieces display
        # Show opponent's pieces that this player captured
        # If we are white, we captured black pieces, so show black symbols
        symbols = PIECE_SYMBOLS_BLACK if self.is_white_pieces else PIECE_SYMBOLS_WHITE
        
        # Build the display string (order: queen, rook, bishop, knight, pawn)
        text_parts = []
        for piece_type in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]:
            count = captured.get(piece_type, 0)
            if count > 0:
                text_parts.append(symbols[piece_type] * count)
        
        captured_text = ''.join(text_parts)
        if captured_text != self.captured_label.text():
            self.captured_label.setText(captured_text)
        
        # Update advantage display (only show if this player is ahead)
        if advantage > 0:
            new_adv_text = f"+{advantage}"
            if self.advantage_label.text() != new_adv_text:
                self.advantage_label.setText(new_adv_text)
        else:
            if self.advantage_label.text() != "":
                self.advantage_label.setText("")
    
    def reset(self):
        """Reset the widget"""
        self.player_name = ""
        self.player_rating = 0
        self.player_title = ""
        self.captured_pieces = {}
        self.material_advantage = 0
        self.name_label.setText("Waiting...")
        self.title_label.hide()
        self.rating_label.setText("")
        self.captured_label.setText("")
        self.advantage_label.setText("")
        self.clock.reset()
