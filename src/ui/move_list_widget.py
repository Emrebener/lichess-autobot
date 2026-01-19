"""
Move List Widget for Lichess Autobot
Displays algebraic notation with move navigation
"""

from typing import Optional, List, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

import chess


class MoveLabel(QLabel):
    """Clickable move label"""
    
    clicked = pyqtSignal(int)  # Emits the ply (half-move) index
    
    # Pre-defined stylesheets to avoid creating new strings
    STYLE_NORMAL = """
        QLabel {
            padding: 2px 5px;
            border-radius: 3px;
        }
        QLabel:hover {
            background-color: #3a5a8a;
        }
    """
    STYLE_SELECTED = """
        QLabel {
            padding: 2px 5px;
            border-radius: 3px;
            background-color: #4a7aba;
            color: white;
        }
    """
    
    def __init__(self, text: str, ply: int, parent=None):
        super().__init__(text, parent)
        self.ply = ply
        self._is_selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self.STYLE_NORMAL)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.ply)
        super().mousePressEvent(event)
    
    def set_selected(self, selected: bool):
        """Highlight this move as selected"""
        if selected == self._is_selected:
            return  # No change
        self._is_selected = selected
        if selected:
            self.setStyleSheet(self.STYLE_SELECTED)
        else:
            self.setStyleSheet(self.STYLE_NORMAL)


class MoveListWidget(QWidget):
    """
    Widget displaying move notation with navigation.
    
    Features:
    - Algebraic notation display
    - Click on move to navigate
    - Arrow buttons for navigation
    - "Live" indicator when viewing current position
    """
    
    # Signals
    move_selected = pyqtSignal(int)  # Emits ply index when user navigates
    jump_to_live = pyqtSignal()      # Emits when user wants to return to live
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self.moves: List[str] = []         # List of SAN moves
        self.current_ply: int = 0          # Currently viewed position (0 = start)
        self.live_ply: int = 0             # Latest position in the game
        self.is_viewing_live: bool = True  # Whether viewing the live position
        self.game_active: bool = False     # Whether there's an ongoing game
        self.move_labels: List[MoveLabel] = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the move list UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Header with title and live indicator
        header_layout = QHBoxLayout()
        
        title = QLabel("Moves")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        self.live_indicator = QLabel("● LIVE")
        self.live_indicator.setStyleSheet("""
            QLabel {
                color: #f44336;
                font-weight: bold;
                font-size: 10px;
            }
        """)
        self.live_indicator.hide()  # Hidden until game starts
        header_layout.addWidget(self.live_indicator)
        
        layout.addLayout(header_layout)
        
        # Scroll area for moves
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 5px;
            }
        """)
        
        # Container for moves
        self.moves_container = QWidget()
        self.moves_layout = QGridLayout(self.moves_container)
        self.moves_layout.setContentsMargins(5, 5, 5, 5)
        self.moves_layout.setSpacing(2)
        self.moves_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.moves_container)
        layout.addWidget(self.scroll_area, stretch=1)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(5)
        
        self.btn_start = QPushButton("⏪")
        self.btn_start.setToolTip("Go to start")
        self.btn_start.setFixedWidth(40)
        self.btn_start.clicked.connect(self._on_start)
        
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip("Previous move")
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.clicked.connect(self._on_prev)
        
        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip("Next move")
        self.btn_next.setFixedWidth(40)
        self.btn_next.clicked.connect(self._on_next)
        
        self.btn_end = QPushButton("⏩")
        self.btn_end.setToolTip("Go to latest (live)")
        self.btn_end.setFixedWidth(40)
        self.btn_end.clicked.connect(self._on_end)
        
        # Style navigation buttons
        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
            }
        """
        for btn in [self.btn_start, self.btn_prev, self.btn_next, self.btn_end]:
            btn.setStyleSheet(btn_style)
        
        nav_layout.addWidget(self.btn_start)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_end)
        
        layout.addLayout(nav_layout)
        
        self._update_nav_buttons()
    
    def set_moves(self, board: chess.Board):
        """Update the move list from a board's move stack"""
        # Mark game as active when we receive moves
        self.game_active = True
        
        # Build new moves list
        new_moves = []
        temp_board = chess.Board()
        
        for move in board.move_stack:
            san = temp_board.san(move)
            new_moves.append(san)
            temp_board.push(move)
        
        # Check if moves actually changed
        if new_moves == self.moves:
            # No change in moves, just update live ply if needed
            return
        
        # Check if this is just appending new moves (common case)
        if len(new_moves) > len(self.moves) and new_moves[:len(self.moves)] == self.moves:
            # Just append new moves, don't rebuild everything
            old_count = len(self.moves)
            self.moves = new_moves
            self.live_ply = len(self.moves)
            
            # Add only the new moves
            self._append_moves_from(old_count)
        else:
            # Full rebuild needed (e.g., takeback or new game)
            self._clear_moves()
            self.moves = new_moves
            self.live_ply = len(self.moves)
            self._rebuild_move_display()
        
        # If we were viewing live, stay at live
        if self.is_viewing_live:
            self.current_ply = self.live_ply
        
        self._update_selection()
        self._update_nav_buttons()
        self._update_live_indicator()
        
        # Scroll to current position
        if self.is_viewing_live:
            self._scroll_to_current()
    
    def _clear_moves(self):
        """Clear all move labels"""
        for label in self.move_labels:
            label.deleteLater()
        self.move_labels.clear()
        
        # Clear layout
        while self.moves_layout.count():
            item = self.moves_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _append_moves_from(self, start_index: int):
        """Append moves starting from a given index (for incremental updates)"""
        for i in range(start_index, len(self.moves)):
            row = i // 2
            col = (i % 2) + 1  # Column 1 for white, 2 for black
            
            # Add move number if this is white's move
            if i % 2 == 0:
                move_num = (i // 2) + 1
                num_label = QLabel(f"{move_num}.")
                num_label.setStyleSheet("color: #888; font-size: 12px;")
                num_label.setFixedWidth(30)
                self.moves_layout.addWidget(num_label, row, 0)
            
            # Add the move
            move_label = MoveLabel(self.moves[i], i + 1)
            move_label.clicked.connect(self._on_move_clicked)
            move_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 12px;
                    padding: 2px 5px;
                    border-radius: 3px;
                }
                QLabel:hover {
                    background-color: #3a5a8a;
                }
            """)
            self.move_labels.append(move_label)
            self.moves_layout.addWidget(move_label, row, col)
    
    def _rebuild_move_display(self):
        """Rebuild the move display grid"""
        self._clear_moves()
        
        row = 0
        for i in range(0, len(self.moves), 2):
            # Move number
            move_num = (i // 2) + 1
            num_label = QLabel(f"{move_num}.")
            num_label.setStyleSheet("color: #888; font-size: 12px;")
            num_label.setFixedWidth(30)
            self.moves_layout.addWidget(num_label, row, 0)
            
            # White's move
            white_move = MoveLabel(self.moves[i], i + 1)
            white_move.clicked.connect(self._on_move_clicked)
            white_move.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 12px;
                    padding: 2px 5px;
                    border-radius: 3px;
                }
                QLabel:hover {
                    background-color: #3a5a8a;
                }
            """)
            self.move_labels.append(white_move)
            self.moves_layout.addWidget(white_move, row, 1)
            
            # Black's move (if exists)
            if i + 1 < len(self.moves):
                black_move = MoveLabel(self.moves[i + 1], i + 2)
                black_move.clicked.connect(self._on_move_clicked)
                black_move.setStyleSheet("""
                    QLabel {
                        color: white;
                        font-size: 12px;
                        padding: 2px 5px;
                        border-radius: 3px;
                    }
                    QLabel:hover {
                        background-color: #3a5a8a;
                    }
                """)
                self.move_labels.append(black_move)
                self.moves_layout.addWidget(black_move, row, 2)
            
            row += 1
        
        # Add stretch at the bottom
        self.moves_layout.setRowStretch(row, 1)
        
        # Update selection
        self._update_selection()
    
    def _update_selection(self):
        """Update which move is highlighted as selected"""
        for label in self.move_labels:
            label.set_selected(label.ply == self.current_ply)
    
    def _update_nav_buttons(self):
        """Update navigation button enabled states"""
        self.btn_start.setEnabled(self.current_ply > 0)
        self.btn_prev.setEnabled(self.current_ply > 0)
        self.btn_next.setEnabled(self.current_ply < self.live_ply)
        self.btn_end.setEnabled(self.current_ply < self.live_ply)
    
    def _update_live_indicator(self):
        """Update the live indicator visibility"""
        if not self.game_active:
            self.live_indicator.hide()
            return
        
        self.live_indicator.show()
        if self.is_viewing_live:
            new_text = "● LIVE"
            if self.live_indicator.text() != new_text:
                self.live_indicator.setText(new_text)
                self.live_indicator.setStyleSheet("""
                    QLabel {
                        color: #f44336;
                        font-weight: bold;
                        font-size: 10px;
                    }
                """)
        else:
            behind = self.live_ply - self.current_ply
            new_text = f"◉ {behind} move{'s' if behind != 1 else ''} behind"
            if self.live_indicator.text() != new_text:
                self.live_indicator.setText(new_text)
                self.live_indicator.setStyleSheet("""
                    QLabel {
                        color: #ff9800;
                        font-weight: bold;
                        font-size: 10px;
                    }
                """)
    
    def _scroll_to_current(self):
        """Scroll to show the current move"""
        if self.current_ply > 0 and self.current_ply <= len(self.move_labels):
            label = self.move_labels[self.current_ply - 1]
            self.scroll_area.ensureWidgetVisible(label)
    
    def _on_move_clicked(self, ply: int):
        """Handle click on a move"""
        self.navigate_to(ply)
    
    def _on_start(self):
        """Navigate to the starting position"""
        self.navigate_to(0)
    
    def _on_prev(self):
        """Navigate to previous move"""
        if self.current_ply > 0:
            self.navigate_to(self.current_ply - 1)
    
    def _on_next(self):
        """Navigate to next move"""
        if self.current_ply < self.live_ply:
            self.navigate_to(self.current_ply + 1)
    
    def _on_end(self):
        """Navigate to the live position"""
        self.navigate_to(self.live_ply)
    
    def navigate_to(self, ply: int):
        """Navigate to a specific ply"""
        ply = max(0, min(ply, self.live_ply))
        
        if ply == self.current_ply:
            return
        
        self.current_ply = ply
        self.is_viewing_live = (ply == self.live_ply)
        
        self._update_selection()
        self._update_nav_buttons()
        self._update_live_indicator()
        self._scroll_to_current()
        
        if self.is_viewing_live:
            self.jump_to_live.emit()
        else:
            self.move_selected.emit(ply)
    
    def on_new_move(self):
        """Called when a new move arrives from the game.
        
        If viewing live, stay at live. Otherwise, stay at current position.
        """
        if self.is_viewing_live:
            self.current_ply = self.live_ply
    
    def clear(self):
        """Clear the move list"""
        self._clear_moves()
        self.moves = []
        self.current_ply = 0
        self.live_ply = 0
        self.is_viewing_live = True
        self.game_active = False
        self._update_nav_buttons()
        self._update_live_indicator()
    
    def reset(self):
        """Alias for clear()"""
        self.clear()
    
    def add_result(self, result: str):
        """Add game result to the display"""
        row = self.moves_layout.rowCount()
        result_label = QLabel(result)
        result_label.setStyleSheet("""
            QLabel {
                color: #ffd700;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }
        """)
        result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.moves_layout.addWidget(result_label, row, 0, 1, 3)
    
    def get_board_at_ply(self, ply: int) -> chess.Board:
        """Get the board position at a specific ply"""
        board = chess.Board()
        for i in range(min(ply, len(self.moves))):
            try:
                move = board.parse_san(self.moves[i])
                board.push(move)
            except ValueError:
                break
        return board
    
    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Left:
            self._on_prev()
        elif event.key() == Qt.Key.Key_Right:
            self._on_next()
        elif event.key() == Qt.Key.Key_Home:
            self._on_start()
        elif event.key() == Qt.Key.Key_End:
            self._on_end()
        else:
            super().keyPressEvent(event)
