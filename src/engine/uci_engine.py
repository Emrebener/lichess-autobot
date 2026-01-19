"""
UCI Engine Manager for Lichess Autobot
Handles communication with UCI-compatible chess engines
"""

import os
import glob
import asyncio
from typing import Optional, List, Callable, Dict, Any, Union
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

import chess
import chess.engine


class UCIOptionType(Enum):
    """Types of UCI options"""
    SPIN = "spin"       # Integer with min/max
    CHECK = "check"     # Boolean
    COMBO = "combo"     # Selection from list
    STRING = "string"   # Text input
    BUTTON = "button"   # Action button


@dataclass
class UCIOption:
    """Represents a UCI engine option"""
    name: str
    type: UCIOptionType
    default: Any = None
    min_val: Optional[int] = None
    max_val: Optional[int] = None
    var_list: Optional[List[str]] = None  # For combo type
    
    @classmethod
    def from_engine_option(cls, opt: chess.engine.Option) -> "UCIOption":
        """Create UCIOption from python-chess Option object"""
        # Determine type
        if opt.type == "spin":
            return cls(
                name=opt.name,
                type=UCIOptionType.SPIN,
                default=opt.default,
                min_val=opt.min,
                max_val=opt.max
            )
        elif opt.type == "check":
            return cls(
                name=opt.name,
                type=UCIOptionType.CHECK,
                default=opt.default
            )
        elif opt.type == "combo":
            return cls(
                name=opt.name,
                type=UCIOptionType.COMBO,
                default=opt.default,
                var_list=list(opt.var) if opt.var else []
            )
        elif opt.type == "string":
            return cls(
                name=opt.name,
                type=UCIOptionType.STRING,
                default=opt.default or ""
            )
        elif opt.type == "button":
            return cls(
                name=opt.name,
                type=UCIOptionType.BUTTON
            )
        else:
            # Unknown type, treat as string
            return cls(
                name=opt.name,
                type=UCIOptionType.STRING,
                default=str(opt.default) if opt.default else ""
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "name": self.name,
            "type": self.type.value,
            "default": self.default,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "var_list": self.var_list
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UCIOption":
        """Create from dictionary"""
        return cls(
            name=data["name"],
            type=UCIOptionType(data["type"]),
            default=data.get("default"),
            min_val=data.get("min_val"),
            max_val=data.get("max_val"),
            var_list=data.get("var_list")
        )


class UCIEngine:
    """Manages UCI chess engine communication"""
    
    def __init__(self, engine_path: str):
        """
        Initialize engine manager
        
        Args:
            engine_path: Path to the UCI engine executable
        """
        self.engine_path = engine_path
        self.engine: Optional[chess.engine.UciProtocol] = None
        self.transport: Optional[asyncio.SubprocessTransport] = None
        self._is_running = False
        self._options: Dict[str, UCIOption] = {}
        self._engine_name: Optional[str] = None
        self._engine_author: Optional[str] = None
    
    @property
    def is_running(self) -> bool:
        """Check if engine is currently running"""
        return self._is_running and self.engine is not None
    
    @property
    def name(self) -> str:
        """Get the engine name (from UCI id, or filename as fallback)"""
        return self._engine_name or Path(self.engine_path).stem
    
    @property
    def author(self) -> Optional[str]:
        """Get the engine author"""
        return self._engine_author
    
    @property
    def options(self) -> Dict[str, UCIOption]:
        """Get available UCI options"""
        return self._options.copy()
    
    async def start(self):
        """Start the UCI engine"""
        if self._is_running:
            return
        
        try:
            self.transport, self.engine = await chess.engine.popen_uci(self.engine_path)
            self._is_running = True
            
            # Extract engine info
            if hasattr(self.engine, 'id'):
                self._engine_name = self.engine.id.get('name')
                self._engine_author = self.engine.id.get('author')
            
            # Discover available options
            await self._discover_options()
            
        except Exception as e:
            self._is_running = False
            raise RuntimeError(f"Failed to start engine: {e}")
    
    async def _discover_options(self):
        """Discover available UCI options from the engine"""
        self._options.clear()
        
        if self.engine and hasattr(self.engine, 'options'):
            for name, opt in self.engine.options.items():
                try:
                    uci_opt = UCIOption.from_engine_option(opt)
                    self._options[name] = uci_opt
                except Exception:
                    pass  # Skip options that can't be parsed
    
    def get_option(self, name: str) -> Optional[UCIOption]:
        """Get a specific option by name"""
        return self._options.get(name)
    
    def get_common_options(self) -> Dict[str, UCIOption]:
        """Get commonly used options that users typically want to configure"""
        common_names = [
            # Strength limiting
            "UCI_LimitStrength", "UCI_Elo", "Skill Level",
            # Performance
            "Threads", "Hash", "MultiPV",
            # Tablebase
            "SyzygyPath", "SyzygyProbeLimit",
            # Playing style
            "Contempt", "Ponder",
            # Analysis
            "UCI_AnalyseMode", "UCI_Chess960",
        ]
        
        result = {}
        for name in common_names:
            if name in self._options:
                result[name] = self._options[name]
        return result
    
    async def set_option(self, name: str, value: Any) -> bool:
        """
        Set an engine option
        
        Args:
            name: Option name
            value: Option value
        
        Returns:
            True if successful
        """
        if not self.is_running:
            raise RuntimeError("Engine is not running")
        
        try:
            await self.engine.configure({name: value})
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to set option {name}: {e}")
    
    # Options that python-chess manages automatically and shouldn't be set manually
    MANAGED_OPTIONS = {"MultiPV", "Ponder", "UCI_AnalyseMode", "UCI_Chess960"}
    
    async def set_options(self, options: Dict[str, Any]) -> bool:
        """
        Set multiple engine options at once
        
        Args:
            options: Dictionary of option names and values
        
        Returns:
            True if all successful
        """
        if not self.is_running:
            raise RuntimeError("Engine is not running")
        
        # Filter out options that python-chess manages automatically
        filtered_options = {
            name: value for name, value in options.items()
            if name not in self.MANAGED_OPTIONS
        }
        
        try:
            await self.engine.configure(filtered_options)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to set options: {e}")
    
    async def stop(self):
        """Stop the UCI engine"""
        if self.engine and self._is_running:
            try:
                await self.engine.quit()
            except Exception:
                pass  # Engine may already be closed
            finally:
                self.engine = None
                self.transport = None
                self._is_running = False
    
    async def get_best_move(self, board: chess.Board, 
                            time_limit: float = None,
                            depth: int = None,
                            nodes: int = None,
                            wtime: int = None,
                            btime: int = None,
                            winc: int = None,
                            binc: int = None) -> chess.Move:
        """
        Get the best move for the current position
        
        Args:
            board: Current chess position
            time_limit: Time limit in seconds for analysis
            depth: Search depth limit
            nodes: Node count limit
            wtime: White time remaining in milliseconds
            btime: Black time remaining in milliseconds
            winc: White increment in milliseconds
            binc: Black increment in milliseconds
        
        Returns:
            Best move according to the engine
        """
        if not self.is_running:
            raise RuntimeError("Engine is not running")
        
        # Build the limit object based on provided parameters
        limit_kwargs = {}
        
        if time_limit is not None:
            limit_kwargs["time"] = time_limit
        if depth is not None:
            limit_kwargs["depth"] = depth
        if nodes is not None:
            limit_kwargs["nodes"] = nodes
        if wtime is not None:
            limit_kwargs["white_clock"] = wtime / 1000.0  # Convert to seconds
        if btime is not None:
            limit_kwargs["black_clock"] = btime / 1000.0
        if winc is not None:
            limit_kwargs["white_inc"] = winc / 1000.0
        if binc is not None:
            limit_kwargs["black_inc"] = binc / 1000.0
        
        # Default to 1 second if no limit specified
        if not limit_kwargs:
            limit_kwargs["time"] = 1.0
        
        limit = chess.engine.Limit(**limit_kwargs)
        
        result = await self.engine.play(board, limit)
        return result.move
    
    async def analyze(self, board: chess.Board, 
                      time_limit: float = 1.0,
                      depth: int = None,
                      multipv: int = 1) -> List[dict]:
        """
        Analyze a position
        
        Args:
            board: Current chess position
            time_limit: Time limit in seconds
            depth: Search depth limit
            multipv: Number of principal variations to return
        
        Returns:
            List of analysis info dictionaries
        """
        if not self.is_running:
            raise RuntimeError("Engine is not running")
        
        limit_kwargs = {"time": time_limit}
        if depth is not None:
            limit_kwargs["depth"] = depth
        
        limit = chess.engine.Limit(**limit_kwargs)
        
        info = await self.engine.analyse(board, limit, multipv=multipv)
        return info if isinstance(info, list) else [info]
    
    async def analyze_position(self, board: chess.Board, time_limit: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        Analyze a position and return the evaluation.
        
        Args:
            board: Current chess position
            time_limit: Time limit in seconds
        
        Returns:
            Dictionary with 'score' (PovScore) and 'pv' (best line) keys,
            or None if analysis failed
        """
        if not self.is_running:
            return None
        
        try:
            limit = chess.engine.Limit(time=time_limit)
            info = await self.engine.analyse(board, limit)
            return info
        except Exception:
            return None
    
    async def set_option(self, name: str, value):
        """Set an engine option"""
        if not self.is_running:
            raise RuntimeError("Engine is not running")
        
        await self.engine.configure({name: value})
    
    def __repr__(self) -> str:
        status = "running" if self.is_running else "stopped"
        return f"UCIEngine({self.name}, {status})"


class EngineScanner:
    """Scans for available UCI engines in a directory"""
    
    # Common engine executable patterns
    ENGINE_PATTERNS = [
        "*.exe",  # Windows
        "stockfish*",
        "komodo*",
        "lc0*",
        "leela*",
        "ethereal*",
        "laser*",
        "rubi*",
        "crafty*",
        "fruit*",
        "toga*",
        "houdini*",
        "fire*",
        "andscacs*",
        "arasan*",
        "rodent*",
        "senpai*",
        "texel*",
        "demolito*",
        "winter*",
        "xiphos*",
        "pedone*",
        "igel*",
        "minic*",
        "berserk*",
        "koivisto*",
        "slowchess*",
        "weiss*",
        "clover*",
        "caissa*",
    ]
    
    def __init__(self, engines_dir: str):
        """
        Initialize scanner
        
        Args:
            engines_dir: Directory to scan for engines
        """
        self.engines_dir = Path(engines_dir)
    
    def scan(self) -> List[str]:
        """
        Scan for available engine executables
        
        Returns:
            List of absolute paths to found engines
        """
        if not self.engines_dir.exists():
            return []
        
        found_engines = set()
        
        # On Windows, look for .exe files
        if os.name == 'nt':
            for exe_file in self.engines_dir.glob("*.exe"):
                found_engines.add(str(exe_file.absolute()))
        else:
            # On Unix, look for executable files
            for item in self.engines_dir.iterdir():
                if item.is_file() and os.access(item, os.X_OK):
                    found_engines.add(str(item.absolute()))
        
        # Also check subdirectories one level deep
        for subdir in self.engines_dir.iterdir():
            if subdir.is_dir():
                if os.name == 'nt':
                    for exe_file in subdir.glob("*.exe"):
                        found_engines.add(str(exe_file.absolute()))
                else:
                    for item in subdir.iterdir():
                        if item.is_file() and os.access(item, os.X_OK):
                            found_engines.add(str(item.absolute()))
        
        return sorted(list(found_engines))
    
    def get_engine_names(self) -> List[tuple]:
        """
        Get list of (name, path) tuples for found engines
        
        Returns:
            List of (display_name, full_path) tuples
        """
        engines = self.scan()
        return [(Path(path).stem, path) for path in engines]


async def test_engine(engine_path: str) -> bool:
    """
    Test if an engine is valid and working
    
    Args:
        engine_path: Path to the engine executable
    
    Returns:
        True if engine is valid, False otherwise
    """
    try:
        engine = UCIEngine(engine_path)
        await engine.start()
        
        # Try getting a move from starting position
        board = chess.Board()
        move = await engine.get_best_move(board, time_limit=0.1)
        
        await engine.stop()
        return move is not None
    except Exception:
        return False
