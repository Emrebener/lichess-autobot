"""
Lichess Autobot - Main Entry Point
A bot that plays chess on Lichess using the Board API
"""

import sys
import os
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from qasync import QEventLoop, asyncSlot, asyncClose

from database import DatabaseManager
from ui import MainWindow


def get_engines_dir() -> str:
    """Get the engines directory path"""
    # Look for engines directory relative to the script
    script_dir = Path(__file__).parent.parent
    engines_dir = script_dir / "engines"
    
    # Create if doesn't exist
    engines_dir.mkdir(exist_ok=True)
    
    return str(engines_dir)


def get_db_path() -> str:
    """Get the database file path"""
    script_dir = Path(__file__).parent.parent
    return str(script_dir / "lichess_autobot.db")


def main():
    """Main entry point"""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Lichess Autobot")
    app.setApplicationVersion("1.0.0")
    
    # Set up async event loop with qasync
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Initialize database
    db_path = get_db_path()
    db = DatabaseManager(db_path)
    db.log_info("Application started")
    
    # Get engines directory
    engines_dir = get_engines_dir()
    
    # Create and show main window
    window = MainWindow(db, engines_dir)
    window.show()
    
    # Run the event loop
    with loop:
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            db.log_info("Application closed")
            db.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
