"""
SQLite Database Manager for Lichess Autobot
Handles settings, statistics, and logging
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import IntEnum


def _normalize_path(path: str) -> str:
    """Normalize a file path for consistent database storage"""
    # Convert to absolute path with consistent separators and case
    # On Windows, paths are case-insensitive, so we lowercase for consistency
    normalized = os.path.normpath(os.path.abspath(path))
    if os.name == 'nt':  # Windows
        normalized = normalized.lower()
    return normalized


class LogSeverity(IntEnum):
    """Log severity levels"""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class DatabaseManager:
    """Manages SQLite database operations"""
    
    def __init__(self, db_path: str = "lichess_autobot.db"):
        """Initialize database connection and create tables if needed"""
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
    
    def _connect(self):
        """Establish database connection"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def _create_tables(self):
        """Create all required tables if they don't exist"""
        cursor = self.conn.cursor()
        
        # Settings table for storing configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Statistics table for game stats
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                games_lost INTEGER DEFAULT 0,
                games_drawn INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Game history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT UNIQUE NOT NULL,
                opponent TEXT,
                color TEXT,
                result TEXT,
                time_control TEXT,
                rated INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Logs table with severity column
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                severity INTEGER NOT NULL,
                message TEXT NOT NULL,
                details TEXT
            )
        """)
        
        # Engine options table for storing UCI options per engine
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engine_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine_path TEXT NOT NULL,
                option_name TEXT NOT NULL,
                option_value TEXT,
                UNIQUE(engine_path, option_name)
            )
        """)
        
        # Initialize statistics if not exists
        cursor.execute("SELECT COUNT(*) FROM statistics")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO statistics (games_played, games_won, games_lost, games_drawn) VALUES (0, 0, 0, 0)")
        
        self.conn.commit()
    
    # ========== Settings Operations ==========
    
    def get_setting(self, key: str, default: str = "") -> str:
        """Get a setting value by key"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default
    
    def set_setting(self, key: str, value: str):
        """Set a setting value"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        """, (key, value))
        self.conn.commit()
    
    def get_bearer_token(self) -> str:
        """Get the stored bearer token"""
        return self.get_setting("bearer_token", "")
    
    def set_bearer_token(self, token: str):
        """Store the bearer token"""
        self.set_setting("bearer_token", token)
    
    def get_last_engine(self) -> str:
        """Get the last used engine path"""
        return self.get_setting("last_engine", "")
    
    def set_last_engine(self, engine_path: str):
        """Store the last used engine path"""
        self.set_setting("last_engine", engine_path)
    
    def get_last_time_control(self) -> str:
        """Get the last used time control"""
        return self.get_setting("last_time_control", "15+10")
    
    def set_last_time_control(self, time_control: str):
        """Store the last used time control"""
        self.set_setting("last_time_control", time_control)
    
    def get_rated_mode(self) -> bool:
        """Get whether to play rated games"""
        return self.get_setting("rated_mode", "false").lower() == "true"
    
    def set_rated_mode(self, rated: bool):
        """Store rated mode preference"""
        self.set_setting("rated_mode", "true" if rated else "false")
    
    # ========== Statistics Operations ==========
    
    def get_statistics(self) -> Dict[str, int]:
        """Get current statistics"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT games_played, games_won, games_lost, games_drawn FROM statistics ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return {
                "games_played": row["games_played"],
                "games_won": row["games_won"],
                "games_lost": row["games_lost"],
                "games_drawn": row["games_drawn"]
            }
        return {"games_played": 0, "games_won": 0, "games_lost": 0, "games_drawn": 0}
    
    def update_statistics(self, result: str):
        """
        Update statistics after a game
        result: 'win', 'loss', or 'draw'
        """
        stats = self.get_statistics()
        stats["games_played"] += 1
        
        if result == "win":
            stats["games_won"] += 1
        elif result == "loss":
            stats["games_lost"] += 1
        elif result == "draw":
            stats["games_drawn"] += 1
        
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE statistics SET 
                games_played = ?,
                games_won = ?,
                games_lost = ?,
                games_drawn = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = (SELECT MAX(id) FROM statistics)
        """, (stats["games_played"], stats["games_won"], stats["games_lost"], stats["games_drawn"]))
        self.conn.commit()
    
    def reset_statistics(self):
        """Reset all statistics to zero"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE statistics SET 
                games_played = 0,
                games_won = 0,
                games_lost = 0,
                games_drawn = 0,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = (SELECT MAX(id) FROM statistics)
        """)
        self.conn.commit()
    
    # ========== Game History Operations ==========
    
    def add_game(self, game_id: str, opponent: str, color: str, result: str, 
                 time_control: str, rated: bool):
        """Add a game to history"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO game_history 
            (game_id, opponent, color, result, time_control, rated)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (game_id, opponent, color, result, time_control, rated))
        self.conn.commit()
    
    def get_recent_games(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent games from history"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM game_history 
            ORDER BY played_at DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ========== Logging Operations ==========
    
    def log(self, severity: LogSeverity, message: str, details: str = None):
        """Add a log entry"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO logs (severity, message, details)
            VALUES (?, ?, ?)
        """, (int(severity), message, details))
        self.conn.commit()
    
    def log_debug(self, message: str, details: str = None):
        """Log a debug message"""
        self.log(LogSeverity.DEBUG, message, details)
    
    def log_info(self, message: str, details: str = None):
        """Log an info message"""
        self.log(LogSeverity.INFO, message, details)
    
    def log_warning(self, message: str, details: str = None):
        """Log a warning message"""
        self.log(LogSeverity.WARNING, message, details)
    
    def log_error(self, message: str, details: str = None):
        """Log an error message"""
        self.log(LogSeverity.ERROR, message, details)
    
    def log_critical(self, message: str, details: str = None):
        """Log a critical message"""
        self.log(LogSeverity.CRITICAL, message, details)
    
    def get_logs(self, min_severity: LogSeverity = LogSeverity.DEBUG, 
                 limit: int = 100) -> List[Dict[str, Any]]:
        """Get log entries filtered by minimum severity"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM logs 
            WHERE severity >= ?
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (int(min_severity), limit))
        return [dict(row) for row in cursor.fetchall()]
    
    def clear_logs(self):
        """Clear all log entries"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM logs")
        self.conn.commit()
    
    # ========== Engine Options Operations ==========
    
    def get_engine_options(self, engine_path: str) -> Dict[str, str]:
        """
        Get stored options for an engine
        
        Args:
            engine_path: Path to the engine executable
        
        Returns:
            Dictionary of option names to values
        """
        normalized_path = _normalize_path(engine_path)
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT option_name, option_value FROM engine_options
            WHERE engine_path = ?
        """, (normalized_path,))
        
        return {row["option_name"]: row["option_value"] for row in cursor.fetchall()}
    
    def set_engine_option(self, engine_path: str, option_name: str, option_value: Any):
        """
        Set an engine option value
        
        Args:
            engine_path: Path to the engine executable
            option_name: UCI option name
            option_value: Option value (will be converted to string)
        """
        normalized_path = _normalize_path(engine_path)
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO engine_options (engine_path, option_name, option_value)
            VALUES (?, ?, ?)
        """, (normalized_path, option_name, str(option_value)))
        self.conn.commit()
    
    def set_engine_options(self, engine_path: str, options: Dict[str, Any]):
        """
        Set multiple engine options at once
        
        Args:
            engine_path: Path to the engine executable
            options: Dictionary of option names to values
        """
        normalized_path = _normalize_path(engine_path)
        cursor = self.conn.cursor()
        for name, value in options.items():
            cursor.execute("""
                INSERT OR REPLACE INTO engine_options (engine_path, option_name, option_value)
                VALUES (?, ?, ?)
            """, (normalized_path, name, str(value)))
        self.conn.commit()
    
    def delete_engine_options(self, engine_path: str):
        """Delete all stored options for an engine"""
        normalized_path = _normalize_path(engine_path)
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM engine_options WHERE engine_path = ?", (normalized_path,))
        self.conn.commit()
    
    # ========== Cleanup ==========
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
