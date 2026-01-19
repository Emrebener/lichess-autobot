"""
Lichess API Client for Board API
Handles all communication with Lichess using NDJSON streaming
"""

import asyncio
import json
import time
from typing import Optional, Callable, AsyncIterator, Dict, Any
from dataclasses import dataclass
from enum import Enum

import aiohttp


class GameSpeed(Enum):
    """Game speed/time control categories"""
    RAPID = "rapid"
    CLASSICAL = "classical"
    CORRESPONDENCE = "correspondence"


@dataclass
class TimeControl:
    """Represents a time control setting"""
    name: str
    time: Optional[float]  # Initial time in minutes (None for correspondence)
    increment: Optional[int]  # Increment in seconds (None for correspondence)
    days: Optional[int] = None  # Days per move (only for correspondence)
    speed: GameSpeed = GameSpeed.RAPID
    
    def __str__(self) -> str:
        return self.name


# Available time controls for Board API
TIME_CONTROLS = [
    # Rapid (10-15 min games)
    TimeControl("15+10", 15, 10, speed=GameSpeed.RAPID),
    TimeControl("10+5", 10, 5, speed=GameSpeed.RAPID),
    TimeControl("10+0", 10, 0, speed=GameSpeed.RAPID),
    TimeControl("15+0", 15, 0, speed=GameSpeed.RAPID),
    # Classical (25+ min games)
    TimeControl("30+0", 30, 0, speed=GameSpeed.CLASSICAL),
    TimeControl("30+20", 30, 20, speed=GameSpeed.CLASSICAL),
    TimeControl("45+45", 45, 45, speed=GameSpeed.CLASSICAL),
    # Correspondence
    TimeControl("1 day", None, None, days=1, speed=GameSpeed.CORRESPONDENCE),
    TimeControl("3 days", None, None, days=3, speed=GameSpeed.CORRESPONDENCE),
    TimeControl("7 days", None, None, days=7, speed=GameSpeed.CORRESPONDENCE),
]


class LichessAPIError(Exception):
    """Exception raised for Lichess API errors"""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class LichessClient:
    """Async client for Lichess Board API"""
    
    BASE_URL = "https://lichess.org"
    
    # Timeout for read operations (seconds) - Lichess sends keepalives every ~15-30 seconds
    READ_TIMEOUT = 60.0
    
    def __init__(self, token: str):
        """
        Initialize the Lichess client
        
        Args:
            token: Bearer token for authentication
        """
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None
        self._event_stream_task: Optional[asyncio.Task] = None
        self._game_stream_task: Optional[asyncio.Task] = None
        self._seek_task: Optional[asyncio.Task] = None
        self._active = False
        self._stopping = False
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/x-ndjson"
        }
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self._session is None or self._session.closed:
            # Set a long read timeout for streaming (Lichess sends keepalives every ~20s)
            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
    
    async def close(self):
        """Close the client and all streams"""
        self._active = False
        self._stopping = True  # Signal streams to stop
        
        # Cancel active tasks with a short timeout
        tasks_to_cancel = [t for t in [self._event_stream_task, self._game_stream_task, self._seek_task] 
                          if t and not t.done()]
        
        for task in tasks_to_cancel:
            task.cancel()
        
        # Wait for all tasks with a timeout
        if tasks_to_cancel:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                    timeout=3.0  # Don't wait more than 3 seconds
                )
            except asyncio.TimeoutError:
                pass  # Force continue even if tasks don't finish
        
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def get_account(self) -> Dict[str, Any]:
        """
        Get the account information
        
        Returns:
            Account data dictionary
        """
        await self._ensure_session()
        
        async with self._session.get(
            f"{self.BASE_URL}/api/account",
            headers={"Authorization": f"Bearer {self.token}"}
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise LichessAPIError(f"Failed to get account: {text}", response.status)
            return await response.json()
    
    async def validate_token(self) -> bool:
        """
        Validate the bearer token
        
        Returns:
            True if token is valid, False otherwise
        """
        try:
            await self.get_account()
            return True
        except LichessAPIError:
            return False
    
    def request_stop(self):
        """Request the client to stop all streams"""
        self._stopping = True
    
    async def _stream_ndjson(self, url: str, 
                             callback: Callable[[Dict[str, Any]], None]) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream NDJSON from a URL with responsive cancellation
        
        Args:
            url: URL to stream from
            callback: Callback function for each JSON object
        """
        await self._ensure_session()
        
        # Use a timeout so we can check for cancellation periodically
        timeout = aiohttp.ClientTimeout(total=None, sock_read=self.READ_TIMEOUT)
        
        print(f"[DEBUG] Opening stream connection to {url}")  # Debug
        
        async with self._session.get(url, headers=self.headers, timeout=timeout) as response:
            if response.status != 200:
                text = await response.text()
                raise LichessAPIError(f"Stream error: {text}", response.status)
            
            print(f"[DEBUG] Stream connected, status={response.status}")  # Debug
            
            buffer = b""
            last_stop_check = time.time()
            
            while not self._stopping:
                try:
                    # Read without wait_for to avoid timer exhaustion in qasync
                    # aiohttp handles timeouts internally via ClientTimeout
                    chunk = await response.content.read(1024)
                    
                    if not chunk:
                        print("[DEBUG] Stream ended (empty chunk)")  # Debug
                        break  # Stream ended
                    
                    buffer += chunk
                    
                    # Process complete lines
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        line_str = line.decode('utf-8').strip()
                        
                        if line_str:  # Skip empty keepalive lines
                            print(f"[DEBUG] Received line: {line_str[:200]}")  # Debug (truncated)
                            try:
                                data = json.loads(line_str)
                                if callback:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback(data)
                                    else:
                                        callback(data)
                                yield data
                            except json.JSONDecodeError:
                                print(f"[DEBUG] JSON decode error for: {line_str}")  # Debug
                                continue
                        else:
                            print("[DEBUG] Keepalive received")  # Debug
                    
                    # Check for stop periodically (every 2 seconds)
                    now = time.time()
                    if now - last_stop_check > 2.0:
                        last_stop_check = now
                        if self._stopping:
                            break
                
                except aiohttp.ClientError as e:
                    # Socket timeout or other client error - reconnect will happen
                    print(f"[DEBUG] Client error in stream: {e}")  # Debug
                    break
                except asyncio.CancelledError:
                    print("[DEBUG] Stream cancelled")  # Debug
                    raise
    
    async def stream_events(self, 
                           on_game_start: Callable = None,
                           on_game_finish: Callable = None,
                           on_challenge: Callable = None):
        """
        Stream incoming events (games, challenges)
        
        Args:
            on_game_start: Callback for game start events
            on_game_finish: Callback for game finish events
            on_challenge: Callback for challenge events
        """
        url = f"{self.BASE_URL}/api/stream/event"
        
        print(f"[DEBUG] Starting event stream from {url}")  # Debug
        
        async for event in self._stream_ndjson(url, None):
            event_type = event.get("type")
            
            print(f"[DEBUG] Event received: type={event_type}, data={event}")  # Debug
            
            if event_type == "gameStart" and on_game_start:
                print(f"[DEBUG] Calling on_game_start callback")  # Debug
                if asyncio.iscoroutinefunction(on_game_start):
                    await on_game_start(event.get("game", {}))
                else:
                    on_game_start(event.get("game", {}))
            
            elif event_type == "gameFinish" and on_game_finish:
                if asyncio.iscoroutinefunction(on_game_finish):
                    await on_game_finish(event.get("game", {}))
                else:
                    on_game_finish(event.get("game", {}))
            
            elif event_type == "challenge" and on_challenge:
                if asyncio.iscoroutinefunction(on_challenge):
                    await on_challenge(event.get("challenge", {}))
                else:
                    on_challenge(event.get("challenge", {}))
    
    async def stream_game(self, game_id: str,
                          on_game_full: Callable = None,
                          on_game_state: Callable = None,
                          on_chat_line: Callable = None,
                          on_opponent_gone: Callable = None):
        """
        Stream a game's state
        
        Args:
            game_id: The game ID to stream
            on_game_full: Callback for initial full game state
            on_game_state: Callback for game state updates
            on_chat_line: Callback for chat messages
            on_opponent_gone: Callback for opponent gone events
        """
        url = f"{self.BASE_URL}/api/board/game/stream/{game_id}"
        
        async for event in self._stream_ndjson(url, None):
            event_type = event.get("type")
            
            if event_type == "gameFull" and on_game_full:
                if asyncio.iscoroutinefunction(on_game_full):
                    await on_game_full(event)
                else:
                    on_game_full(event)
            
            elif event_type == "gameState" and on_game_state:
                if asyncio.iscoroutinefunction(on_game_state):
                    await on_game_state(event)
                else:
                    on_game_state(event)
            
            elif event_type == "chatLine" and on_chat_line:
                if asyncio.iscoroutinefunction(on_chat_line):
                    await on_chat_line(event)
                else:
                    on_chat_line(event)
            
            elif event_type == "opponentGone" and on_opponent_gone:
                if asyncio.iscoroutinefunction(on_opponent_gone):
                    await on_opponent_gone(event)
                else:
                    on_opponent_gone(event)
    
    async def create_seek(self, time_control: TimeControl, 
                          rated: bool = False,
                          color: str = "random",
                          variant: str = "standard") -> bool:
        """
        Create a seek to find a game
        
        Args:
            time_control: Time control for the game
            rated: Whether the game should be rated
            color: Preferred color (white/black/random)
            variant: Chess variant
        
        Returns:
            True if seek was accepted (game started), False if cancelled
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/board/seek"
        
        data = {
            "rated": "true" if rated else "false",
            "variant": variant,
            "color": color
        }
        
        if time_control.days is not None:
            # Correspondence seek
            data["days"] = str(time_control.days)
        else:
            # Real-time seek
            data["time"] = str(time_control.time)
            data["increment"] = str(time_control.increment)
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            async with self._session.post(url, headers=headers, data=data) as response:
                if response.status == 400:
                    text = await response.text()
                    raise LichessAPIError(f"Seek failed: {text}", 400)
                
                # For real-time seeks, the connection stays open until matched
                # For correspondence, it returns immediately with seek ID
                if time_control.days is not None:
                    result = await response.json()
                    return True
                else:
                    # Stream until we get matched or cancelled
                    async for line in response.content:
                        pass  # Just keep connection open
                    return True
        except asyncio.CancelledError:
            return False
    
    async def make_move(self, game_id: str, move: str, 
                        offering_draw: bool = False) -> bool:
        """
        Make a move in a game
        
        Args:
            game_id: The game ID
            move: Move in UCI format (e.g., 'e2e4')
            offering_draw: Whether to offer a draw with this move
        
        Returns:
            True if successful
        """
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/board/game/{game_id}/move/{move}"
        if offering_draw:
            url += "?offeringDraw=true"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with self._session.post(url, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                raise LichessAPIError(f"Move failed: {text}", response.status)
            result = await response.json()
            return result.get("ok", False)
    
    async def resign_game(self, game_id: str) -> bool:
        """Resign the current game"""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/board/game/{game_id}/resign"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with self._session.post(url, headers=headers) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
    
    async def abort_game(self, game_id: str) -> bool:
        """Abort the current game"""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/board/game/{game_id}/abort"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with self._session.post(url, headers=headers) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
    
    async def write_chat(self, game_id: str, text: str, 
                         room: str = "player") -> bool:
        """Write a message in the game chat"""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/board/game/{game_id}/chat"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"room": room, "text": text}
        
        async with self._session.post(url, headers=headers, data=data) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
    
    async def claim_victory(self, game_id: str) -> bool:
        """Claim victory when opponent has left"""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/board/game/{game_id}/claim-victory"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with self._session.post(url, headers=headers) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
    
    async def handle_draw(self, game_id: str, accept: bool) -> bool:
        """Accept or decline a draw offer"""
        await self._ensure_session()
        
        action = "yes" if accept else "no"
        url = f"{self.BASE_URL}/api/board/game/{game_id}/draw/{action}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with self._session.post(url, headers=headers) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
    
    async def accept_challenge(self, challenge_id: str) -> bool:
        """Accept an incoming challenge"""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/challenge/{challenge_id}/accept"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with self._session.post(url, headers=headers) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
    
    async def decline_challenge(self, challenge_id: str, 
                                reason: str = "generic") -> bool:
        """Decline an incoming challenge"""
        await self._ensure_session()
        
        url = f"{self.BASE_URL}/api/challenge/{challenge_id}/decline"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"reason": reason}
        
        async with self._session.post(url, headers=headers, data=data) as response:
            if response.status != 200:
                return False
            result = await response.json()
            return result.get("ok", False)
