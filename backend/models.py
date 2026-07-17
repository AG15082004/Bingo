from pydantic import BaseModel
from typing import List, Dict, Union, Optional

class BingoCardModel(BaseModel):
    matrix: List[List[Union[int, str]]]
    marked: List[List[bool]]

class PlayerModel(BaseModel):
    id: str
    name: str
    card: BingoCardModel
    is_host: bool
    is_connected: bool
    completed_lines: int = 0

class ChatMessageModel(BaseModel):
    name: str
    timestamp: str
    message: str

class GameRoomModel(BaseModel):
    code: str
    host_id: str
    players: Dict[str, PlayerModel]
    state: str  # "lobby", "playing", "game_over"
    draw_history: List[int]
    current_draw: Optional[int] = None
    winners: List[str]  # List of player names
    winning_pattern: Optional[Dict] = None
    chat_history: List[ChatMessageModel]
    draw_interval: int
    total_calls: int = 0
    duration: float = 0.0
    turn_order: List[str] = []
    current_turn_player_id: Optional[str] = None
    leaderboard: List[Dict] = []

