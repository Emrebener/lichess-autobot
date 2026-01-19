#!/usr/bin/env python3
"""Test script to verify imports work correctly"""

import sys
sys.path.insert(0, 'src')

print("Testing imports...")

try:
    from ui.chess_board import ChessBoardWidget
    print("✓ ChessBoardWidget")
except Exception as e:
    print(f"✗ ChessBoardWidget: {e}")

try:
    from ui.player_info_widget import PlayerInfoWidget
    print("✓ PlayerInfoWidget")
except Exception as e:
    print(f"✗ PlayerInfoWidget: {e}")

try:
    from ui.evaluation_widget import EvaluationWidget
    print("✓ EvaluationWidget")
except Exception as e:
    print(f"✗ EvaluationWidget: {e}")

try:
    from ui.move_list_widget import MoveListWidget
    print("✓ MoveListWidget")
except Exception as e:
    print(f"✗ MoveListWidget: {e}")

try:
    from ui.main_window import MainWindow
    print("✓ MainWindow")
except Exception as e:
    print(f"✗ MainWindow: {e}")

print("\nAll imports completed!")
