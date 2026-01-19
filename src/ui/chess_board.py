"""
Chess Board Widget for PyQt6
Displays a chess board with pieces, non-interactive
Supports move navigation (viewing historical positions)
Uses cburnett SVG piece set from lichess
"""

from typing import Optional, Dict, List
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QSizePolicy, QFrame, QVBoxLayout
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QPixmap
from PyQt6.QtSvg import QSvgRenderer

import chess


# Path to piece SVG files
PIECES_DIR = Path(__file__).parent / "assets" / "pieces" / "cburnett"

# Mapping from piece symbol to SVG filename
PIECE_FILES = {
    'K': 'wK.svg', 'Q': 'wQ.svg', 'R': 'wR.svg', 'B': 'wB.svg', 'N': 'wN.svg', 'P': 'wP.svg',
    'k': 'bK.svg', 'q': 'bQ.svg', 'r': 'bR.svg', 'b': 'bB.svg', 'n': 'bN.svg', 'p': 'bP.svg',
}

# Cache for SVG renderers
_svg_cache: Dict[str, QSvgRenderer] = {}

# Colors
LIGHT_SQUARE = QColor(240, 217, 181)  # Light tan
DARK_SQUARE = QColor(181, 136, 99)   # Brown
HIGHLIGHT_COLOR = QColor(255, 255, 0, 100)  # Yellow highlight for last move
HISTORY_OVERLAY = QColor(100, 100, 150, 40)  # Slight overlay when viewing history


def get_svg_renderer(piece: str) -> Optional[QSvgRenderer]:
    """Get or create an SVG renderer for a piece"""
    if piece not in PIECE_FILES:
        return None
    
    if piece not in _svg_cache:
        svg_path = PIECES_DIR / PIECE_FILES[piece]
        if svg_path.exists():
            _svg_cache[piece] = QSvgRenderer(str(svg_path))
        else:
            return None
    
    return _svg_cache.get(piece)


class AspectRatioContainer(QWidget):
    """
    A container widget that maintains a 1:1 aspect ratio for its child widget.
    The child widget is centered and sized to the largest square that fits.
    """
    
    def __init__(self, child_widget: QWidget, parent=None):
        super().__init__(parent)
        self.child_widget = child_widget
        self.child_widget.setParent(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
    def resizeEvent(self, event):
        """Resize and center the child widget maintaining square aspect ratio"""
        super().resizeEvent(event)
        
        # Calculate the largest square that fits
        size = min(self.width(), self.height())
        
        # Center the child widget
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2
        
        self.child_widget.setGeometry(x, y, size, size)


class SquareWidget(QFrame):
    """A single square on the chess board"""
    
    def __init__(self, row: int, col: int, parent=None):
        super().__init__(parent)
        self.row = row
        self.col = col
        self.piece = None
        self.is_highlighted = False
        self._last_style_key = None  # Track last applied background style
        
        # Determine square color (a1 should be dark, so when row+col is even it's dark)
        self.is_light = (row + col) % 2 == 0
        
        # Style
        self._update_style()
        
        # Size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(40, 40)
    
    def _update_style(self):
        """Update the square's visual style"""
        # Calculate style key to check if update is needed
        style_key = (self.is_light, self.is_highlighted)
        if style_key == self._last_style_key:
            return
        self._last_style_key = style_key
        
        if self.is_light:
            bg_color = LIGHT_SQUARE
        else:
            bg_color = DARK_SQUARE
        
        if self.is_highlighted:
            # Blend highlight with square color
            bg_color = QColor(
                (bg_color.red() + HIGHLIGHT_COLOR.red()) // 2,
                (bg_color.green() + HIGHLIGHT_COLOR.green()) // 2,
                (bg_color.blue() + HIGHLIGHT_COLOR.blue()) // 2
            )
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: none;
            }}
        """)
    
    def set_piece(self, piece: Optional[str]):
        """Set the piece on this square (None for empty)"""
        if piece == self.piece:
            return  # No change
        self.piece = piece
        self.update()  # Trigger repaint
    
    def set_highlighted(self, highlighted: bool):
        """Set whether this square should be highlighted"""
        if highlighted == self.is_highlighted:
            return  # No change
        self.is_highlighted = highlighted
        self._update_style()
    
    def paintEvent(self, event):
        """Paint the square and piece"""
        super().paintEvent(event)
        
        if self.piece:
            renderer = get_svg_renderer(self.piece)
            if renderer:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                
                # Calculate centered square for the piece
                size = min(self.width(), self.height())
                margin = int(size * 0.05)  # 5% margin
                piece_size = size - 2 * margin
                
                x = (self.width() - piece_size) // 2
                y = (self.height() - piece_size) // 2
                
                from PyQt6.QtCore import QRectF
                renderer.render(painter, QRectF(x, y, piece_size, piece_size))
                
                painter.end()


class ChessBoardWidget(QWidget):
    """
    Chess board widget displaying the current position.
    Supports viewing historical positions while the game continues.
    Always maintains a square aspect ratio.
    """
    
    # Signal emitted when board is updated
    board_updated = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = chess.Board()
        self.flipped = False  # Whether to show board from black's perspective
        self.last_move: Optional[chess.Move] = None
        
        # Move history for navigation
        self.move_history: List[chess.Move] = []  # All moves in the game
        self.current_ply: int = 0  # Currently displayed position (0 = start)
        self.is_viewing_live: bool = True  # Whether viewing the live position
        
        self._setup_ui()
        self._update_board()
    
    def _setup_ui(self):
        """Set up the board UI"""
        layout = QGridLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create squares
        self.squares: Dict[tuple, SquareWidget] = {}
        
        for row in range(8):
            for col in range(8):
                square = SquareWidget(row, col, self)
                self.squares[(row, col)] = square
                layout.addWidget(square, row, col)
        
        # File labels (a-h)
        self.file_labels = []
        for col in range(8):
            label = QLabel(chr(ord('a') + col))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: gray; font-size: 10px;")
            layout.addWidget(label, 8, col)
            self.file_labels.append(label)
        
        # Rank labels (1-8)
        self.rank_labels = []
        for row in range(8):
            label = QLabel(str(8 - row))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: gray; font-size: 10px;")
            layout.addWidget(label, row, 8)
            self.rank_labels.append(label)
        
        # Set size policy for expanding
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)
    
    def resizeEvent(self, event):
        """Dynamically resize while maintaining square aspect ratio"""
        super().resizeEvent(event)
        # We don't force fixed size here - parent container handles aspect ratio
    
    def sizeHint(self) -> QSize:
        """Provide a square size hint"""
        return QSize(400, 400)
    
    def _update_board(self):
        """Update the visual representation of the board"""
        # Clear highlights
        for square in self.squares.values():
            square.set_highlighted(False)
        
        # Highlight last move
        if self.last_move:
            from_sq = self.last_move.from_square
            to_sq = self.last_move.to_square
            
            from_row = 7 - chess.square_rank(from_sq)
            from_col = chess.square_file(from_sq)
            to_row = 7 - chess.square_rank(to_sq)
            to_col = chess.square_file(to_sq)
            
            if self.flipped:
                from_row, from_col = 7 - from_row, 7 - from_col
                to_row, to_col = 7 - to_row, 7 - to_col
            
            if (from_row, from_col) in self.squares:
                self.squares[(from_row, from_col)].set_highlighted(True)
            if (to_row, to_col) in self.squares:
                self.squares[(to_row, to_col)].set_highlighted(True)
        
        # Update pieces
        for row in range(8):
            for col in range(8):
                # Convert visual coordinates to chess coordinates
                if self.flipped:
                    chess_row = row
                    chess_col = 7 - col
                else:
                    chess_row = 7 - row
                    chess_col = col
                
                square = chess.square(chess_col, chess_row)
                piece = self.board.piece_at(square)
                
                if piece:
                    piece_char = piece.symbol()
                else:
                    piece_char = None
                
                self.squares[(row, col)].set_piece(piece_char)
        
        # Update file labels
        for col, label in enumerate(self.file_labels):
            if self.flipped:
                label.setText(chr(ord('h') - col))
            else:
                label.setText(chr(ord('a') + col))
        
        # Update rank labels
        for row, label in enumerate(self.rank_labels):
            if self.flipped:
                label.setText(str(row + 1))
            else:
                label.setText(str(8 - row))
        
        self.board_updated.emit()
    
    def set_position(self, fen: str = None, board: chess.Board = None):
        """
        Set the board position
        
        Args:
            fen: FEN string for the position
            board: Chess board object
        """
        if board is not None:
            self.board = board.copy()
        elif fen is not None:
            self.board = chess.Board(fen)
        
        self._update_board()
    
    def set_position_from_moves(self, moves_uci: str):
        """
        Set position from a space-separated string of UCI moves.
        Updates the move history and displays the live position.
        
        Args:
            moves_uci: Space-separated UCI moves (e.g., "e2e4 e7e5 g1f3")
        """
        # Parse all moves into history
        self.move_history = []
        temp_board = chess.Board()
        
        if moves_uci:
            move_list = moves_uci.split()
            for move_str in move_list:
                try:
                    move = chess.Move.from_uci(move_str)
                    if move in temp_board.legal_moves:
                        self.move_history.append(move)
                        temp_board.push(move)
                except ValueError:
                    break
        
        # Update live position
        if self.is_viewing_live:
            self.current_ply = len(self.move_history)
        
        # Build board for current view position
        self._rebuild_board_at_ply(self.current_ply)
    
    def _rebuild_board_at_ply(self, ply: int):
        """Rebuild the board state at a specific ply"""
        self.board = chess.Board()
        self.last_move = None
        
        for i, move in enumerate(self.move_history[:ply]):
            self.board.push(move)
            if i == ply - 1:
                self.last_move = move
        
        self._update_board()
    
    def navigate_to_ply(self, ply: int):
        """
        Navigate to a specific ply in the game history.
        
        Args:
            ply: The half-move number to display (0 = starting position)
        """
        ply = max(0, min(ply, len(self.move_history)))
        self.current_ply = ply
        self.is_viewing_live = (ply == len(self.move_history))
        self._rebuild_board_at_ply(ply)
    
    def jump_to_live(self):
        """Jump to the live (latest) position"""
        self.is_viewing_live = True
        self.current_ply = len(self.move_history)
        self._rebuild_board_at_ply(self.current_ply)
    
    def make_move(self, move: chess.Move):
        """Make a move on the board"""
        if move in self.board.legal_moves:
            self.board.push(move)
            self.last_move = move
            self._update_board()
    
    def reset(self):
        """Reset to starting position"""
        self.board = chess.Board()
        self.last_move = None
        self.move_history = []
        self.current_ply = 0
        self.is_viewing_live = True
        self._update_board()
    
    def flip(self):
        """Flip the board orientation"""
        self.flipped = not self.flipped
        self._update_board()
    
    def set_flipped(self, flipped: bool):
        """Set board orientation"""
        self.flipped = flipped
        self._update_board()
    
    def get_fen(self) -> str:
        """Get current FEN string (of displayed position)"""
        return self.board.fen()
    
    def get_board(self) -> chess.Board:
        """Get the current displayed board object"""
        return self.board.copy()
    
    def get_live_board(self) -> chess.Board:
        """Get the live (latest) board position"""
        board = chess.Board()
        for move in self.move_history:
            board.push(move)
        return board
    
    def get_displayed_ply(self) -> int:
        """Get the currently displayed ply"""
        return self.current_ply
    
    def get_live_ply(self) -> int:
        """Get the live (latest) ply"""
        return len(self.move_history)


class NotationWidget(QWidget):
    """Widget displaying move notation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.moves = []
    
    def _setup_ui(self):
        """Set up the notation display"""
        from PyQt6.QtWidgets import QVBoxLayout, QTextEdit
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("Move Notation")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Notation text area
        self.notation_text = QTextEdit()
        self.notation_text.setReadOnly(True)
        self.notation_text.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.notation_text)
    
    def set_moves(self, board: chess.Board):
        """Update notation from a board's move stack"""
        self.moves = []
        temp_board = chess.Board()
        
        notation_lines = []
        move_number = 1
        
        for i, move in enumerate(board.move_stack):
            san = temp_board.san(move)
            
            if i % 2 == 0:
                notation_lines.append(f"{move_number}. {san}")
            else:
                notation_lines[-1] += f" {san}"
                move_number += 1
            
            temp_board.push(move)
            self.moves.append(san)
        
        self.notation_text.setText("\n".join(notation_lines))
        
        # Scroll to bottom
        scrollbar = self.notation_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear(self):
        """Clear the notation"""
        self.moves = []
        self.notation_text.clear()
    
    def add_result(self, result: str):
        """Add game result to notation"""
        current_text = self.notation_text.toPlainText()
        if current_text:
            self.notation_text.setText(current_text + f"\n\n{result}")
        else:
            self.notation_text.setText(result)
