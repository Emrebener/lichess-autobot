"""
Human Difficulty Calculator for Chess Positions

This module calculates a "Human Difficulty Score" (0-10) that estimates
the likelihood of a human player making a blunder in a given position.

The algorithm quantifies "how hard it is to find a non-losing move" by:
1. Analyzing all legal moves with a chess engine
2. Counting how many moves are "safe" vs "blunders"
3. Considering static complexity factors
4. Applying time pressure multipliers

Score Interpretation:
- 0-3: Easy position - many safe moves, low blunder risk
- 4-6: Moderate - requires care, some traps
- 7-10: Critical - only 1-2 moves don't lose, high blunder risk
"""

import asyncio
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
import chess
import chess.engine


@dataclass
class DifficultyAnalysis:
    """Results of difficulty analysis"""
    score: float  # 0.0 to 10.0
    safe_moves: int  # Number of non-blundering moves
    total_moves: int  # Total legal moves
    survival_ratio: float  # safe_moves / total_moves
    complexity_score: float  # Static complexity (0-10)
    volatility_score: float  # How much evals vary between moves
    best_move: Optional[str]  # Best move in UCI notation
    best_eval: Optional[int]  # Best move evaluation in centipawns
    is_critical: bool  # True if only 1-2 safe moves exist
    factors: Dict[str, float]  # Individual factor contributions


# Blunder threshold in centipawns
# A move is considered a "blunder" if it drops eval by this much
BLUNDER_THRESHOLD_CP = 200

# Mistake threshold - smaller drop but still significant
MISTAKE_THRESHOLD_CP = 100

# Weights for final score calculation
# These sum to 1.0 for the base score before time pressure
WEIGHT_SURVIVAL_RATIO = 0.45  # Primary factor: ratio of safe moves
WEIGHT_VOLATILITY = 0.25      # How much evals swing between moves
WEIGHT_COMPLEXITY = 0.20      # Static position complexity
WEIGHT_CRITICAL = 0.10        # Bonus for "only move" situations


def calculate_static_complexity(board: chess.Board) -> Tuple[float, Dict[str, float]]:
    """
    Calculate static complexity factors from the position.
    Returns a score (0-10) and breakdown of factors.
    
    Factors considered:
    - Piece count (more pieces = more complex)
    - Hanging pieces (undefended attacked pieces)
    - King safety (exposed king, checks)
    - Pawn structure tension
    - Piece mobility
    """
    factors = {}
    
    # === Material Count (0-2 points) ===
    # More pieces on the board = more to calculate
    piece_count = len(board.piece_map())
    # Normalize: 32 pieces = 2.0, 8 pieces = 0.5
    material_score = min(2.0, piece_count / 16.0)
    factors['material'] = material_score
    
    # === Hanging Pieces (0-3 points) ===
    # Count pieces that are attacked but not defended (or under-defended)
    hanging_score = 0.0
    for square, piece in board.piece_map().items():
        attackers = board.attackers(not piece.color, square)
        defenders = board.attackers(piece.color, square)
        
        if attackers:
            if not defenders:
                # Completely undefended and attacked
                piece_value = _get_piece_value(piece.piece_type)
                hanging_score += min(1.0, piece_value / 5.0)  # Cap contribution
            elif len(attackers) > len(defenders):
                # More attackers than defenders
                hanging_score += 0.3
    
    factors['hanging'] = min(3.0, hanging_score)
    
    # === King Safety (0-2 points) ===
    king_safety_score = 0.0
    
    # Check if in check
    if board.is_check():
        king_safety_score += 1.5
    
    # Analyze king exposure
    for color in [chess.WHITE, chess.BLACK]:
        king_square = board.king(color)
        if king_square is not None:
            # Count attackers near king
            king_zone = chess.SquareSet(chess.BB_KING_ATTACKS[king_square])
            attackers_near_king = 0
            for sq in king_zone:
                if board.is_attacked_by(not color, sq):
                    attackers_near_king += 1
            king_safety_score += attackers_near_king * 0.1
    
    factors['king_safety'] = min(2.0, king_safety_score)
    
    # === Pawn Tension (0-1.5 points) ===
    # Count pawns that can capture each other
    tension_score = 0.0
    for square, piece in board.piece_map().items():
        if piece.piece_type == chess.PAWN:
            # Check if this pawn can capture
            attacks = board.attacks(square)
            for target in attacks:
                target_piece = board.piece_at(target)
                if target_piece and target_piece.color != piece.color:
                    tension_score += 0.2
    
    factors['pawn_tension'] = min(1.5, tension_score)
    
    # === Tactical Patterns (0-1.5 points) ===
    tactical_score = 0.0
    
    # Forks potential: pieces attacking multiple valuable targets
    for square, piece in board.piece_map().items():
        if piece.piece_type in [chess.KNIGHT, chess.QUEEN]:
            attacks = board.attacks(square)
            valuable_targets = 0
            for target in attacks:
                target_piece = board.piece_at(target)
                if target_piece and target_piece.color != piece.color:
                    if target_piece.piece_type in [chess.QUEEN, chess.ROOK, chess.KING]:
                        valuable_targets += 1
            if valuable_targets >= 2:
                tactical_score += 0.5
    
    factors['tactical'] = min(1.5, tactical_score)
    
    # Sum up all factors
    total = sum(factors.values())
    
    return min(10.0, total), factors


def _get_piece_value(piece_type: int) -> float:
    """Get approximate piece value for calculations"""
    values = {
        chess.PAWN: 1.0,
        chess.KNIGHT: 3.0,
        chess.BISHOP: 3.0,
        chess.ROOK: 5.0,
        chess.QUEEN: 9.0,
        chess.KING: 0.0,  # Can't be captured
    }
    return values.get(piece_type, 0.0)


def calculate_time_pressure_multiplier(time_left_seconds: float) -> float:
    """
    Calculate a multiplier based on time pressure.
    
    Time pressure increases difficulty because:
    - Less time to calculate variations
    - Higher chance of mouse slips
    - Stress affects decision making
    
    Returns a multiplier between 1.0 and 1.5
    """
    if time_left_seconds <= 0:
        return 1.5  # Maximum pressure
    elif time_left_seconds < 10:
        return 1.4  # Severe time trouble
    elif time_left_seconds < 30:
        return 1.3  # Time trouble
    elif time_left_seconds < 60:
        return 1.2  # Getting low
    elif time_left_seconds < 120:
        return 1.1  # Mild pressure
    else:
        return 1.0  # Comfortable


async def calculate_human_difficulty(
    fen: str,
    engine: chess.engine.UciProtocol,
    time_left_seconds: float = 600,
    analysis_time: float = 0.3,
    max_multipv: int = 20
) -> DifficultyAnalysis:
    """
    Calculate the human difficulty score for a position.
    
    Args:
        fen: FEN string of the position
        engine: An already-initialized UCI engine protocol
        time_left_seconds: Time remaining on clock (for time pressure)
        analysis_time: How long to analyze each move (seconds)
        max_multipv: Maximum number of moves to analyze with MultiPV
    
    Returns:
        DifficultyAnalysis with score and detailed breakdown
    """
    board = chess.Board(fen)
    
    # Handle terminal positions
    if board.is_game_over():
        return DifficultyAnalysis(
            score=0.0,
            safe_moves=0,
            total_moves=0,
            survival_ratio=0.0,
            complexity_score=0.0,
            volatility_score=0.0,
            best_move=None,
            best_eval=None,
            is_critical=False,
            factors={}
        )
    
    legal_moves = list(board.legal_moves)
    total_moves = len(legal_moves)
    
    if total_moves == 0:
        return DifficultyAnalysis(
            score=0.0,
            safe_moves=0,
            total_moves=0,
            survival_ratio=0.0,
            complexity_score=0.0,
            volatility_score=0.0,
            best_move=None,
            best_eval=None,
            is_critical=False,
            factors={}
        )
    
    # If only one legal move, difficulty is 0 (forced move)
    if total_moves == 1:
        return DifficultyAnalysis(
            score=0.0,
            safe_moves=1,
            total_moves=1,
            survival_ratio=1.0,
            complexity_score=0.0,
            volatility_score=0.0,
            best_move=legal_moves[0].uci(),
            best_eval=None,
            is_critical=False,
            factors={'forced_move': 0.0}
        )
    
    # === Engine Analysis with MultiPV ===
    multipv = min(max_multipv, total_moves)
    
    try:
        # Analyze with MultiPV to get evaluations for multiple moves
        analysis = await engine.analyse(
            board,
            chess.engine.Limit(time=analysis_time),
            multipv=multipv
        )
    except Exception as e:
        # If engine analysis fails, return a default moderate difficulty
        static_score, static_factors = calculate_static_complexity(board)
        return DifficultyAnalysis(
            score=5.0,
            safe_moves=total_moves // 2,
            total_moves=total_moves,
            survival_ratio=0.5,
            complexity_score=static_score,
            volatility_score=0.0,
            best_move=None,
            best_eval=None,
            is_critical=False,
            factors={'error': 5.0, **static_factors}
        )
    
    # Extract evaluations from MultiPV analysis
    move_evals: List[Tuple[chess.Move, int, bool]] = []  # (move, centipawns, is_mate)
    
    # Handle both list and single result
    if isinstance(analysis, list):
        pv_results = analysis
    else:
        pv_results = [analysis]
    
    for info in pv_results:
        if 'pv' not in info or len(info['pv']) == 0:
            continue
        
        move = info['pv'][0]
        score = info.get('score')
        
        if score is None:
            continue
        
        # Get score from the perspective of the side to move
        pov_score = score.white() if board.turn == chess.WHITE else score.black()
        
        if pov_score.is_mate():
            # Convert mate to a large centipawn value
            mate_in = pov_score.mate()
            if mate_in > 0:
                cp = 30000 - mate_in * 100  # Positive mate
            else:
                cp = -30000 - mate_in * 100  # Negative mate
            move_evals.append((move, cp, True))
        else:
            cp = pov_score.score()
            if cp is not None:
                move_evals.append((move, cp, False))
    
    if not move_evals:
        # No valid evaluations
        static_score, static_factors = calculate_static_complexity(board)
        return DifficultyAnalysis(
            score=5.0,
            safe_moves=total_moves // 2,
            total_moves=total_moves,
            survival_ratio=0.5,
            complexity_score=static_score,
            volatility_score=0.0,
            best_move=None,
            best_eval=None,
            is_critical=False,
            factors={'no_eval': 5.0, **static_factors}
        )
    
    # Sort by evaluation (best first)
    move_evals.sort(key=lambda x: x[1], reverse=True)
    
    best_move, best_eval, best_is_mate = move_evals[0]
    
    # === Calculate Survival Ratio ===
    # Count moves that don't lose significant evaluation
    safe_moves = 0
    mistake_moves = 0
    blunder_moves = 0
    
    for move, eval_cp, is_mate in move_evals:
        eval_drop = best_eval - eval_cp
        
        if eval_drop < MISTAKE_THRESHOLD_CP:
            safe_moves += 1
        elif eval_drop < BLUNDER_THRESHOLD_CP:
            mistake_moves += 1
        else:
            blunder_moves += 1
    
    # Moves not analyzed are assumed to be worse than analyzed ones
    unanalyzed = total_moves - len(move_evals)
    blunder_moves += unanalyzed
    
    survival_ratio = safe_moves / total_moves if total_moves > 0 else 0.0
    
    # === Calculate Volatility ===
    # How much do evaluations swing between moves?
    if len(move_evals) >= 2:
        evals = [e[1] for e in move_evals]
        eval_range = max(evals) - min(evals)
        # Normalize: 1000cp range = high volatility
        volatility_score = min(10.0, eval_range / 100.0)
    else:
        volatility_score = 0.0
    
    # === Static Complexity ===
    complexity_score, complexity_factors = calculate_static_complexity(board)
    
    # === Critical Position Detection ===
    # Only 1-2 safe moves = critical
    is_critical = safe_moves <= 2 and total_moves > 3
    
    # === Calculate Final Score ===
    factors = {}
    
    # 1. Survival ratio contribution (inverted: lower ratio = higher difficulty)
    survival_contribution = (1.0 - survival_ratio) * 10.0 * WEIGHT_SURVIVAL_RATIO
    factors['survival'] = survival_contribution
    
    # 2. Volatility contribution
    volatility_contribution = volatility_score * WEIGHT_VOLATILITY
    factors['volatility'] = volatility_contribution
    
    # 3. Complexity contribution
    complexity_contribution = complexity_score * WEIGHT_COMPLEXITY
    factors['complexity'] = complexity_contribution
    
    # 4. Critical position bonus
    critical_contribution = 0.0
    if is_critical:
        # Scale by how few safe moves there are
        critical_contribution = (3 - safe_moves) * 3.0 * WEIGHT_CRITICAL
    factors['critical'] = critical_contribution
    
    # Add complexity breakdown
    for key, value in complexity_factors.items():
        factors[f'static_{key}'] = value
    
    # Base score (before time pressure)
    base_score = (
        survival_contribution +
        volatility_contribution +
        complexity_contribution +
        critical_contribution
    )
    
    # Apply time pressure multiplier
    time_multiplier = calculate_time_pressure_multiplier(time_left_seconds)
    factors['time_pressure'] = time_multiplier
    
    final_score = base_score * time_multiplier
    
    # Clamp to 0-10
    final_score = max(0.0, min(10.0, final_score))
    
    return DifficultyAnalysis(
        score=final_score,
        safe_moves=safe_moves,
        total_moves=total_moves,
        survival_ratio=survival_ratio,
        complexity_score=complexity_score,
        volatility_score=volatility_score,
        best_move=best_move.uci(),
        best_eval=best_eval,
        is_critical=is_critical,
        factors=factors
    )


def get_difficulty_label(score: float) -> str:
    """Get a human-readable label for the difficulty score"""
    if score < 2.0:
        return "Easy"
    elif score < 4.0:
        return "Simple"
    elif score < 5.5:
        return "Moderate"
    elif score < 7.0:
        return "Tricky"
    elif score < 8.5:
        return "Difficult"
    else:
        return "Critical"


def get_difficulty_color(score: float) -> str:
    """Get a color code for the difficulty score (for UI)"""
    if score < 2.0:
        return "#4CAF50"  # Green
    elif score < 4.0:
        return "#8BC34A"  # Light green
    elif score < 5.5:
        return "#FFC107"  # Amber
    elif score < 7.0:
        return "#FF9800"  # Orange
    elif score < 8.5:
        return "#FF5722"  # Deep orange
    else:
        return "#F44336"  # Red
