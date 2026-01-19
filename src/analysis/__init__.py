"""
Analysis module for Lichess Autobot
Contains position analysis tools including difficulty calculation
"""

from analysis.difficulty_calculator import (
    calculate_human_difficulty,
    calculate_static_complexity,
    calculate_time_pressure_multiplier,
    get_difficulty_label,
    get_difficulty_color,
    DifficultyAnalysis,
    BLUNDER_THRESHOLD_CP,
    MISTAKE_THRESHOLD_CP,
)

__all__ = [
    "calculate_human_difficulty",
    "calculate_static_complexity", 
    "calculate_time_pressure_multiplier",
    "get_difficulty_label",
    "get_difficulty_color",
    "DifficultyAnalysis",
    "BLUNDER_THRESHOLD_CP",
    "MISTAKE_THRESHOLD_CP",
]
