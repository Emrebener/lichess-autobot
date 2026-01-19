# Lichess Autobot

<img width="1920" height="1038" alt="image" src="https://github.com/user-attachments/assets/633b8476-c849-445c-84fd-f83bb7b9ab9f" />
<img width="714" height="692" alt="image" src="https://github.com/user-attachments/assets/e5f31584-147c-4f72-818b-dbf5898431c1" />

A desktop application that plays chess on Lichess using the Board API. This bot is designed for testing and understanding the Lichess Board API, particularly useful for physical chess board development.

## ⚠️ Important Notice

This application uses the **Board API**, which is intended for physical chess boards and third-party clients. Engine assistance is **forbidden** on regular Lichess accounts when using the Board API. This tool is for educational and development purposes only.

If you want to run an engine-assisted bot legally on Lichess, you need to:

1. Create a fresh account (no games played)
2. Upgrade it to a Bot account using the Bot API
3. Use the Bot API endpoints instead

## Features

### Core Functionality

- 🎨 **Real-time Chess Board UI**: Visual display with correct orientation (a1 is dark square) and move highlighting
- ⏱️ **Player Info & Clocks**: Live countdown clocks with player names, ratings, titles, and captured pieces displayed
- 🎮 **Smart Move Timing**: Configurable move time ranges for opening (moves 1-10) and midgame/endgame
- 🔧 **UCI Engine Support**: Compatible with any UCI-compliant chess engine (Stockfish, Leela, Maia, etc.)
- ⚙️ **Engine Options**: Configure UCI settings like threads, hash size, skill level, and more
- 🎯 **Single Node Mode**: Special support for non-searching engines like Maia (nodes=1)

### Analysis & Evaluation

- 📊 **Real-time Position Evaluation**: Separate evaluation engine with toggle on/off control
- 📈 **Visual Evaluation Bar**: Shows position advantage with automatic orientation based on your color
- 🔄 **Continuous Analysis**: Position evaluates every 0.5 seconds with centipawn scores and mate detection
- 👁️ **Evaluation Visibility**: Hide/show evaluation bar via preferences toggle

### Game Navigation & Review

- 📝 **Full Move Navigation**: Click moves or use arrow keys (←/→) to review game history
- ⏮⏭ **Navigation Buttons**: Jump to start, previous, next, or live position
- 🔴 **LIVE Indicator**: Red indicator when game is active, shows navigation status
- 🌐 **Clickable Game Links**: Direct link to view game on Lichess website

### Material & Pieces

- ♟️ **Captured Pieces Display**: Shows all captured pieces next to each player's clock
- 📊 **Material Advantage**: Dynamic +N indicator showing point advantage
- 🎯 **Smart Positioning**: Material display adapts to board orientation

### Data & Settings

- 💾 **Persistent Storage**: All settings, stats, and game history saved in SQLite
- 📈 **Statistics Tracking**: Games played, wins, losses, draws, win rate
- 🔄 **Auto-Save Settings**: Token, engine selection, time controls, and preferences remembered
- 📋 **Comprehensive Logging**: All events logged with severity levels

### User Interface

- 🎛️ **Preferences Panel**: Centralized evaluation settings at top of board
- 📱 **Responsive Layout**: Adapts to window size with scrollable controls
- ⌨️ **Keyboard Shortcuts**: Arrow keys for navigation, Home/End for start/live
- 🖱️ **Interactive Elements**: Clickable moves, toggles, and status displays

## Installation

### Prerequisites

- Python 3.10 or higher
- A Lichess account with a Personal API Access Token

### Setup

1. Clone or download this repository

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Place your UCI chess engine(s) in the `engines/` folder:

   ```
   engines/
   ├── stockfish.exe
   ├── komodo.exe
   └── ...
   ```

4. Get a Lichess API token:
   - Go to https://lichess.org/account/oauth/token
   - Create a new token with the following scopes:
     - `board:play` - Play games with the Board API
     - `challenge:read` - Read incoming challenges
     - `challenge:write` - Accept/decline challenges

## Usage

1. **Run the application:**

   ```bash
   python src/main.py
   ```

2. **Configure API Token:**
   - Enter your Lichess bearer token
   - Click "Validate Token" to verify
   - Token is saved automatically

3. **Set Up Evaluation (Optional):**
   - Toggle "Real-time Evaluation" in Preferences panel
   - Select an evaluation engine from dropdown
   - Evaluation bar will show/hide based on toggle

4. **Select Playing Engine:**
   - Choose your chess engine from "Playing Engine" dropdown
   - Click ⚙️ Options to configure UCI settings
   - Enable "Single node?" for engines like Maia that don't search

5. **Configure Game Settings:**
   - **Time Control**: Choose from Rapid, Classical, or Correspondence
   - **Move Time Range (Opening)**: Set min/max seconds for moves 1-10
   - **Move Time Range (After move 10)**: Set min/max for midgame/endgame
   - **Rated Games**: Toggle for rated vs casual games

6. **Start Playing:**
   - Click "▶ Start Bot" to begin seeking games
   - Bot will automatically play moves and manage time
   - Watch live evaluation and material count

7. **During a Game:**
   - Review moves by clicking in move list or using arrow keys
   - See captured pieces and material advantage next to clocks
   - Click game link at bottom to view on Lichess
   - Navigate with ⏮ ◀ ▶ ⏭ buttons or Home/End keys

8. **Stop Playing:**
   - Click "⏹ Stop Bot" to finish current game and stop
   - Or click "⏸ Stop After Game" to finish gracefully

## Project Structure

```
lichess-autobot/
├── engines/                      # Place UCI engines here
├── src/
│   ├── main.py                   # Application entry point
│   ├── database/
│   │   ├── __init__.py
│   │   └── db_manager.py         # SQLite database operations
│   ├── engine/
│   │   ├── __init__.py
│   │   └── uci_engine.py         # UCI engine communication
│   ├── lichess/
│   │   ├── __init__.py
│   │   └── api_client.py         # Lichess Board API client
│   └── ui/
│       ├── __init__.py
│       ├── chess_board.py        # Chess board widget with move navigation
│       ├── player_info_widget.py # Player name, rating, clock, and captured pieces
│       ├── evaluation_widget.py  # Position evaluation bar
│       ├── move_list_widget.py   # Move list with click/arrow navigation
│       ├── engine_options_dialog.py # UCI options configuration
│       └── main_window.py        # Main application window
├── requirements.txt
├── README.md
└── lichess_autobot.db            # SQLite database (created on first run)
```

## Database Schema

The application uses SQLite to store:

### Settings Table

- Bearer token (encrypted display, stored securely)
- Last used playing engine
- Last used evaluation engine
- Last time control
- Rated mode preference
- Move time ranges (opening min/max, midgame min/max)
- Single node mode setting
- Evaluation toggle state (enabled/disabled)

### Statistics Table

- Games played
- Games won
- Games lost
- Games drawn

### Game History Table

- Game ID
- Opponent username
- Color played
- Result
- Time control
- Rated/casual

### Logs Table

- Timestamp
- Severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Message
- Details

## API Endpoints Used

| Endpoint                                    | Description                                      |
| ------------------------------------------- | ------------------------------------------------ |
| `GET /api/account`                          | Validate token and get account info              |
| `GET /api/stream/event`                     | Stream incoming events (game starts, challenges) |
| `POST /api/board/seek`                      | Create a seek to find opponents                  |
| `GET /api/board/game/stream/{gameId}`       | Stream game state                                |
| `POST /api/board/game/{gameId}/move/{move}` | Make a move                                      |
| `POST /api/board/game/{gameId}/resign`      | Resign a game                                    |
| `POST /api/challenge/{challengeId}/decline` | Decline challenges                               |

## UI Guide

### Preferences Panel (Top)

Centralized evaluation settings:

- **Real-time Evaluation Toggle**: Switch to enable/disable live analysis
  - When OFF: Evaluation bar is hidden from board
  - When ON: Continuous position analysis every 0.5 seconds
- **Evaluation Engine Dropdown**: Select which engine analyzes positions
  - Runs independently from playing engine
  - Can use different engine than the one playing

### Chess Board Area

The main board area shows:

- **Player Info Panels** (top and bottom):
  - Player names with titles (GM, IM, etc.)
  - Ratings in parentheses
  - Captured pieces display (pieces opponent captured)
  - Material advantage (+N indicator when ahead)
  - Live countdown clocks (turns red under 30 seconds)
- **Evaluation Bar** (left of board, when enabled):
  - White advantage shown at white's end, black at black's end
  - Flips orientation based on your playing color
  - Shows centipawn evaluation (e.g., +1.5 = white up 1.5 pawns)
  - Shows mate scores (M5 = mate in 5 moves)
  - Orange "0.0" for exactly equal positions
- **Chess Board** (center):
  - Last move highlighted in yellow
  - Piece images from cburnett set
  - Automatically flips when playing as black
- **Move List** (right of board):
  - Algebraic notation for all moves
  - LIVE indicator (red during active game)
  - Navigation buttons: ⏮ ◀ ▶ ⏭
  - Click any move to jump to that position

- **Game Link** (below board):
  - Clickable URL to view game on Lichess
  - Only shown during active games

### Move Navigation

Review the game while it's in progress:

- **Click on a move**: Jump to that position instantly
- **Arrow keys**: ← (previous) / → (next) / Home (start) / End (live)
- **Navigation buttons**:
  - ⏮ : Jump to game start
  - ◀ : Previous move
  - ▶ : Next move
  - ⏭ : Jump to live position
- **LIVE indicator**:
  - Red: Game is active and you're viewing live position
  - Hidden: When reviewing past moves or no game active

When reviewing past moves:

- New moves continue to be recorded
- You stay at your current view position
- Evaluation shows the position you're viewing
- Click ⏭ or press End to return to live game

### Control Panel (Right Side)

**Lichess API**: Token validation and account info

**Playing Engine**:

- Engine selection with auto-detection
- UCI Options configuration (⚙️ button)
- Single node mode for Maia-style engines

**Game Settings**:

- Time control selection
- Move time ranges (opening and midgame)
- Rated/casual toggle

**Controls**:

- Start Bot / Stop Bot buttons
- Stop After Game option

**Statistics**:

- Games played, won, lost, drawn
- Win rate percentage
- Reset stats button

**Status Bar (Bottom)**: Shows current bot status and activities

## Troubleshooting

### "No engines found"

- Make sure you've placed UCI engine executables in the `engines/` folder
- On Windows, engines should be `.exe` files (e.g., `stockfish.exe`)
- Click the "🔄" refresh button to rescan
- Check that engine files have execute permissions

### Token validation fails

- Ensure your token has the required scopes (`board:play`, `challenge:read`, `challenge:write`)
- Check that the token hasn't expired
- Verify your internet connection
- Try generating a new token from Lichess settings

### Game doesn't start

- Board API only allows Rapid, Classical, and Correspondence time controls
- Make sure you're not already in a game
- Check the status bar (bottom-left) for error messages
- Verify your token is validated (green checkmark)

### Evaluation not working

- Check that "Real-time Evaluation" toggle is ON in Preferences
- Verify an evaluation engine is selected in the dropdown
- Some engines require network files (e.g., Leela needs .pb weights)
- Check the evaluation bar is visible (shows when toggle is enabled)

### Engine errors

- Verify the engine is a valid UCI engine
- Try running the engine manually from command line to check for errors
- For Stockfish: Ensure you have the correct binary for your system
- For Leela (lc0): Make sure network weights file is in the same folder
- For Maia: Enable "Single node?" checkbox
- Check UCI options (⚙️ button) for engine-specific settings

### Board orientation wrong

- The bottom-left square should be dark (a1)
- Board automatically flips when playing as black
- If issues persist, check you're running the latest version

### Performance issues

- Reduce engine threads in UCI Options
- Lower hash table size for evaluation engine
- Disable real-time evaluation if not needed
- Close other resource-intensive applications

## License

This project is for educational purposes. Please respect Lichess Terms of Service.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Acknowledgments

- [Lichess](https://lichess.org) for the excellent API documentation
- [python-chess](https://python-chess.readthedocs.io/) for chess logic
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) for the GUI framework
