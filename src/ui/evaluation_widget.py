"""
Evaluation Widget for Lichess Autobot
Displays real-time position evaluation with a visual bar
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QFont


class EvaluationBar(QWidget):
    """
    Visual evaluation bar showing who is winning.
    White portion represents white's advantage, black portion for black.
    The evaluation text is drawn inside the bar.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._evaluation = 0.0  # Positive = white winning, negative = black winning
        self._is_mate = False
        self._mate_in = 0
        self._eval_text = "0.0"
        self._no_engine = False
        self._analyzing = False
        self._flipped = False  # If True, black side at bottom (playing as black)
        
        self.setMinimumWidth(50)
        self.setMaximumWidth(60)
    
    def set_flipped(self, flipped: bool):
        """Set whether the bar is flipped (black at bottom when playing as black)"""
        self._flipped = flipped
        self.update()
    
    def set_evaluation(self, eval_score: float, is_mate: bool = False, mate_in: int = 0, text: str = "0.0"):
        """
        Set the evaluation score.
        
        Args:
            eval_score: Centipawns/100 (e.g., 1.5 means white is up 1.5 pawns)
            is_mate: Whether it's a forced mate
            mate_in: Number of moves to mate (positive = white mates, negative = black mates)
            text: The formatted text to display
        """
        self._evaluation = eval_score
        self._is_mate = is_mate
        self._mate_in = mate_in
        self._eval_text = text
        self._no_engine = False
        self._analyzing = False
        self.update()
    
    def set_no_engine(self):
        """Show that no evaluation engine is selected"""
        self._no_engine = True
        self._analyzing = False
        self._eval_text = "--"
        self.update()
    
    def set_analyzing(self):
        """Show that analysis is in progress"""
        self._analyzing = True
        self._no_engine = False
        self._eval_text = "..."
        self.update()
    
    def paintEvent(self, event):
        """Paint the evaluation bar with text inside"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        width = self.width()
        height = self.height()
        
        # Calculate the split point (0.5 = equal, 1.0 = white winning, 0.0 = black winning)
        if self._is_mate:
            if self._mate_in > 0:
                split = 1.0  # White wins
            elif self._mate_in < 0:
                split = 0.0  # Black wins
            else:
                split = 0.5
        else:
            # Convert evaluation to split point
            # Use sigmoid-like function to cap the visual at ~7 pawns
            max_eval = 7.0
            clamped_eval = max(-max_eval, min(max_eval, self._evaluation))
            split = 0.5 + (clamped_eval / max_eval) * 0.5
        
        # Flip the split if viewing from black's perspective
        if self._flipped:
            split = 1.0 - split
        
        # When flipped: black at bottom, white at top
        # When not flipped: white at bottom, black at top
        if self._flipped:
            # Black portion (bottom)
            black_height = int(height * split)
            painter.fillRect(0, height - black_height, width, black_height, QColor(50, 50, 50))
            
            # White portion (top)
            white_height = height - black_height
            painter.fillRect(0, 0, width, white_height, QColor(240, 240, 240))
        else:
            # White portion (bottom)
            white_height = int(height * split)
            painter.fillRect(0, height - white_height, width, white_height, QColor(240, 240, 240))
            
            # Black portion (top)
            black_height = height - white_height
            painter.fillRect(0, 0, width, black_height, QColor(50, 50, 50))
        
        # Draw center line indicator
        center_y = height // 2
        painter.setPen(QColor(128, 128, 128))
        painter.drawLine(0, center_y, width, center_y)
        
        # Draw border
        painter.setPen(QColor(100, 100, 100))
        painter.drawRect(0, 0, width - 1, height - 1)
        
        # Draw evaluation text
        font = QFont("Consolas", 12, QFont.Weight.Bold)
        painter.setFont(font)
        
        text_rect = painter.fontMetrics().boundingRect(self._eval_text)
        x = (width - text_rect.width()) // 2
        
        # Determine text position and color based on evaluation
        # Orange only for exactly 0.0 (equal position), centered
        # Otherwise: white text at bottom (on black bg), black text at top (on white bg)
        
        if self._evaluation == 0.0 and not self._is_mate:
            # Exactly equal - orange text at center with black outline
            y = (height + text_rect.height()) // 2 - 2
            # Draw black outline
            painter.setPen(QColor(0, 0, 0))
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        painter.drawText(x + dx, y + dy, self._eval_text)
            # Draw main text in orange
            painter.setPen(QColor(255, 200, 0))
            painter.drawText(x, y, self._eval_text)
        elif (self._evaluation > 0 and not self._is_mate) or (self._is_mate and self._mate_in > 0):
            # White is winning - show black text at white end
            if self._flipped:
                # White end is at top when flipped
                y = text_rect.height() + 5
            else:
                # White end is at bottom when not flipped
                y = height - 5
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(x, y, self._eval_text)
        else:
            # Black is winning - show white text at black end
            if self._flipped:
                # Black end is at bottom when flipped
                y = height - 5
            else:
                # Black end is at top when not flipped
                y = text_rect.height() + 5
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(x, y, self._eval_text)
    
    def reset(self):
        """Reset to equal position"""
        self._evaluation = 0.0
        self._is_mate = False
        self._mate_in = 0
        self._eval_text = "0.0"
        self._no_engine = False
        self._analyzing = False
        self.update()


class EvaluationWidget(QFrame):
    """
    Complete evaluation widget with bar that displays text inside.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the evaluation UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Evaluation bar (now contains the text inside)
        self.eval_bar = EvaluationBar()
        layout.addWidget(self.eval_bar)
    
    def set_evaluation(self, centipawns: int = None, mate_in: int = None):
        """
        Set the evaluation from engine analysis.
        
        Args:
            centipawns: Score in centipawns (100 = 1 pawn advantage for white)
            mate_in: Mate in X moves (positive = white mates, negative = black mates)
        """
        if mate_in is not None:
            # Mate score
            if mate_in > 0:
                eval_text = f"M{mate_in}"
            else:
                eval_text = f"M{abs(mate_in)}"
            self.eval_bar.set_evaluation(0, is_mate=True, mate_in=mate_in, text=eval_text)
        elif centipawns is not None:
            # Regular evaluation
            pawns = centipawns / 100.0
            
            # Format the display
            if abs(pawns) >= 10:
                eval_text = f"{pawns:+.0f}"
            else:
                eval_text = f"{pawns:+.1f}"
            
            self.eval_bar.set_evaluation(pawns, text=eval_text)
        else:
            self.reset()
    
    def set_analyzing(self, analyzing: bool = True):
        """Show that analysis is in progress"""
        if analyzing:
            self.eval_bar.set_analyzing()
    
    def set_no_engine(self):
        """Show that no evaluation engine is selected"""
        self.eval_bar.set_no_engine()
    
    def set_flipped(self, flipped: bool):
        """Set whether the bar is flipped (black at bottom when playing as black)"""
        self.eval_bar.set_flipped(flipped)
    
    def reset(self):
        """Reset to default state"""
        self.eval_bar.reset()
