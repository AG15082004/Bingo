import asyncio
import time
import random
import string
import logging
from typing import Dict, List, Optional, Union
from bingo import generate_card, check_win, count_completed_lines
from websocket_manager import manager
from models import GameRoomModel, PlayerModel, BingoCardModel, ChatMessageModel

logger = logging.getLogger(__name__)

# Configurable draw interval in seconds
DRAW_INTERVAL = 5

def serialize_room(room) -> dict:
    """Helper to convert runtime GameRoom instance into Pydantic serialized dict."""
    players_dict = {}
    for pid, p in room.players.items():
        players_dict[pid] = PlayerModel(
            id=p.id,
            name=p.name,
            card=BingoCardModel(matrix=p.card["matrix"], marked=p.card["marked"]),
            is_host=p.is_host,
            is_connected=p.is_connected,
            completed_lines=p.completed_lines
        )
    
    room_model = GameRoomModel(
        code=room.code,
        host_id=room.host_id,
        players=players_dict,
        state=room.state,
        draw_history=room.draw_history,
        current_draw=room.current_draw,
        winners=room.winners,
        winning_pattern=room.winning_pattern,
        chat_history=[ChatMessageModel(**c) for c in room.chat_history],
        draw_interval=room.draw_interval,
        total_calls=room.total_calls,
        duration=room.duration,
        turn_order=room.turn_order,
        current_turn_player_id=room.current_turn_player_id,
        leaderboard=room.leaderboard
    )
    return room_model.model_dump()

class Player:
    def __init__(self, player_id: str, name: str, is_host: bool):
        self.id = player_id
        self.name = name
        self.is_host = is_host
        self.is_connected = True
        self.completed_lines = 0
        
        # Card generation (server-side, randomized)
        matrix, marked = generate_card()
        self.card = {
            "matrix": matrix,
            "marked": marked
        }

    def reset_card(self):
        """Generates a fresh card for a new round."""
        matrix, marked = generate_card()
        self.card = {
            "matrix": matrix,
            "marked": marked
        }
        self.completed_lines = 0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "card": self.card,
            "is_host": self.is_host,
            "is_connected": self.is_connected,
            "completed_lines": self.completed_lines
        }

class GameRoom:
    def __init__(self, code: str, host_id: str, draw_interval: int = DRAW_INTERVAL):
        self.code = code
        self.host_id = host_id
        self.players: Dict[str, Player] = {}  # player_id -> Player
        self.state = "lobby"  # "lobby", "playing", "game_over"
        self.draw_history: List[int] = []
        self.current_draw: Optional[int] = None
        self.winners: List[str] = []
        self.winning_pattern: Optional[dict] = None
        self.chat_history: List[dict] = []
        self.draw_interval = draw_interval
        self.total_calls = 0
        self.started_at: Optional[float] = None
        self.last_draw_time: Optional[float] = None
        self.duration = 0.0
        self.turn_order: List[str] = []
        self.current_turn_player_id: Optional[str] = None
        self.leaderboard: List[dict] = []
        
        # Background task references
        self.game_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None

    def to_dict(self):
        return {
            "code": self.code,
            "host_id": self.host_id,
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "state": self.state,
            "draw_history": self.draw_history,
            "current_draw": self.current_draw,
            "winners": self.winners,
            "winning_pattern": self.winning_pattern,
            "chat_history": self.chat_history,
            "draw_interval": self.draw_interval,
            "total_calls": self.total_calls,
            "duration": self.duration,
            "turn_order": self.turn_order,
            "current_turn_player_id": self.current_turn_player_id,
            "leaderboard": self.leaderboard
        }

class GameManager:
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}

    def get_room(self, code: str) -> Optional[GameRoom]:
        """Looks up a room by code (case-insensitive, handles ROOM- prefix dynamically)."""
        code_upper = code.upper().strip()
        if not code_upper.startswith("ROOM-"):
            code_upper = f"ROOM-{code_upper}"
        return self.rooms.get(code_upper)

    def create_room(self, host_id: str, draw_interval: int = DRAW_INTERVAL) -> GameRoom:
        """Creates a new game room with a unique random code."""
        while True:
            code_chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            code = f"ROOM-{code_chars}"
            if code not in self.rooms:
                break
                
        room = GameRoom(code, host_id, draw_interval)
        self.rooms[code] = room
        logger.info(f"Created room {code} with host {host_id}")
        return room

    def remove_room(self, room_code: str):
        """Deletes a room and stops its background loop tasks."""
        room = self.rooms.pop(room_code, None)
        if room:
            if room.game_task and not room.game_task.done():
                room.game_task.cancel()
            if room.cleanup_task and not room.cleanup_task.done():
                room.cleanup_task.cancel()
            logger.info(f"Room {room_code} has been removed.")

    async def add_player_to_room(self, room_code: str, player_id: str, player_name: str) -> Player:
        """Adds a player to a room. If they are the first player, they become the host."""
        room = self.get_room(room_code)
        if not room:
            raise ValueError("Room not found")
            
        # Check if player is reconnecting
        if player_id in room.players:
            player = room.players[player_id]
            player.is_connected = True
            player.name = player_name  # In case name changed slightly
            logger.info(f"Player {player_name} reconnected to Room {room.code}")
            return player
            
        is_host = (len(room.players) == 0 or room.host_id == player_id)
        player = Player(player_id, player_name, is_host)
        
        # If they became host, update room's host_id
        if is_host:
            room.host_id = player_id
            
        room.players[player_id] = player
        logger.info(f"Player {player_name} ({player_id}) joined Room {room.code}")
        return player

    def advance_turn(self, room: GameRoom):
        """Advances current_turn_player_id to the next connected player in turn_order."""
        if not room.turn_order:
            room.current_turn_player_id = None
            return

        current_player_id = room.current_turn_player_id
        if current_player_id not in room.turn_order:
            for pid in room.turn_order:
                if room.players.get(pid) and room.players[pid].is_connected:
                    room.current_turn_player_id = pid
                    return
            room.current_turn_player_id = None
            return

        curr_idx = room.turn_order.index(current_player_id)
        for i in range(1, len(room.turn_order) + 1):
            candidate_idx = (curr_idx + i) % len(room.turn_order)
            candidate_id = room.turn_order[candidate_idx]
            if room.players.get(candidate_id) and room.players[candidate_id].is_connected:
                room.current_turn_player_id = candidate_id
                return
        
        # If no other connected players, keep the current player if they are connected
        if room.players.get(current_player_id) and room.players[current_player_id].is_connected:
            room.current_turn_player_id = current_player_id
        else:
            room.current_turn_player_id = None

    async def handle_player_disconnect(self, room_code: str, player_id: str):
        """Flags a player as disconnected. Triggers clean-up if room becomes abandoned."""
        room = self.get_room(room_code)
        if not room:
            return
            
        player = room.players.get(player_id)
        if player:
            player.is_connected = False
            logger.info(f"Player {player.name} in Room {room.code} marked disconnected")
            
            # If playing and it was their turn, advance the turn to someone else
            if room.state == "playing" and room.current_turn_player_id == player_id:
                self.advance_turn(room)
            
            # Broadcast player disconnection event
            await manager.broadcast_to_room(room.code, {
                "event": "player_left",
                "player_id": player_id,
                "player_name": player.name,
                "room": serialize_room(room)
            })
            
            # Schedule room clean-up if all remaining players are disconnected
            self.schedule_room_cleanup(room.code)

    async def remove_player_from_room(self, room_code: str, player_id: str):
        """Explicitly deletes a player from a room (e.g. they click leave)."""
        room = self.get_room(room_code)
        if not room:
            return
            
        # Reassign host if the host left
        player = room.players.get(player_id)
        if player:
            # Advance turn first if it was their turn
            if room.state == "playing" and room.current_turn_player_id == player_id:
                self.advance_turn(room)
                
            if player_id in room.turn_order:
                room.turn_order.remove(player_id)
                
            room.players.pop(player_id, None)
            logger.info(f"Player {player.name} explicitly left Room {room.code}")
            
            if player.is_host and room.players:
                next_host_id = list(room.players.keys())[0]
                room.players[next_host_id].is_host = True
                room.host_id = next_host_id
                logger.info(f"Host reassigned to {room.players[next_host_id].name}")
                
            await manager.broadcast_to_room(room.code, {
                "event": "player_left",
                "player_id": player_id,
                "player_name": player.name,
                "room": serialize_room(room)
            })
            
            # Immediate deletion if empty
            if not room.players:
                self.remove_room(room.code)
            else:
                self.schedule_room_cleanup(room.code)

    def schedule_room_cleanup(self, room_code: str):
        """Starts a countdown timer to delete the room if nobody is connected."""
        room = self.get_room(room_code)
        if not room:
            return
            
        # Clean up if all players are disconnected
        if all(not p.is_connected for p in room.players.values()):
            if room.cleanup_task and not room.cleanup_task.done():
                return  # Cleanup already pending
            room.cleanup_task = asyncio.create_task(self._room_cleanup_job(room.code))

    async def _room_cleanup_job(self, room_code: str):
        # Wait 15 seconds for reconnection attempts
        await asyncio.sleep(15.0)
        room = self.get_room(room_code)
        if room:
            if not room.players or all(not p.is_connected for p in room.players.values()):
                logger.info(f"Auto-deleting room {room_code} (no active players)")
                self.remove_room(room_code)
                await manager.broadcast_to_room(room_code, {"event": "room_deleted"})

    async def start_game(self, room_code: str):
        """Starts the turn-based game room."""
        room = self.get_room(room_code)
        if not room:
            return
            
        if room.state == "playing":
            return  # Already playing
            
        # Reset game states
        room.draw_history = []
        room.current_draw = None
        room.state = "playing"
        room.winners = []
        room.winning_pattern = None
        room.started_at = time.time()
        room.duration = 0.0
        room.leaderboard = []
        
        # Reset all player cards and lines
        for p in room.players.values():
            p.reset_card()
            
        # Establish turn order with connected players
        pids = [pid for pid, p in room.players.items() if p.is_connected]
        if not pids:
            pids = list(room.players.keys())
            
        random.shuffle(pids)
        room.turn_order = pids
        room.current_turn_player_id = pids[0] if pids else None
        
        await manager.broadcast_to_room(room.code, {
            "event": "game_started",
            "room": serialize_room(room)
        })

    async def select_number(self, room_code: str, player_id: str, number: int):
        """Marks the selected number on all players' cards and advances turn or detects winner."""
        room = self.get_room(room_code)
        if not room or room.state != "playing":
            return
            
        if room.current_turn_player_id != player_id:
            logger.warning(f"Player {player_id} tried to play out of turn.")
            return
            
        if number in room.draw_history:
            logger.warning(f"Number {number} has already been selected.")
            return
            
        # Cross number on all players' boards and update completed lines
        for p in room.players.values():
            for r in range(5):
                for c in range(5):
                    if p.card["matrix"][r][c] == number:
                        p.card["marked"][r][c] = True
            p.completed_lines = count_completed_lines(p.card["marked"])
            
        room.current_draw = number
        room.draw_history.append(number)
        room.total_calls = len(room.draw_history)
        
        # Check if anyone has won
        winners = []
        winning_pattern = None
        for p in room.players.values():
            win_details = check_win(p.card["marked"])
            if win_details:
                winners.append(p.name)
                if not winning_pattern:
                    winning_pattern = {
                        "player_name": p.name,
                        "type": win_details["type"],
                        "index": win_details["index"],
                        "cells": win_details["cells"]
                    }
                    
        if winners:
            room.state = "game_over"
            room.winners = winners
            room.winning_pattern = winning_pattern
            room.duration = round(time.time() - room.started_at, 1)
            
            # Generate leaderboard
            sorted_players = sorted(room.players.values(), key=lambda x: x.completed_lines, reverse=True)
            leaderboard = []
            for idx, p in enumerate(sorted_players):
                if idx == 0:
                    rank = "🥇 1"
                    status = "Winner"
                elif idx == 1:
                    rank = "🥈 2"
                    status = "Runner-up"
                elif idx == 2:
                    rank = "🥉 3"
                    status = "Third"
                else:
                    rank = str(idx + 1)
                    status = "-"
                
                # Multiple winners tie handling
                if p.completed_lines >= 5 and idx > 0:
                    rank = "🥇 1"
                    status = "Winner"
                    
                leaderboard.append({
                    "rank": rank,
                    "name": p.name,
                    "completed_lines": p.completed_lines,
                    "status": status
                })
            room.leaderboard = leaderboard
            
            await manager.broadcast_to_room(room.code, {
                "event": "winner_detected",
                "room": serialize_room(room)
            })
        else:
            # Advance turn
            self.advance_turn(room)
            
            await manager.broadcast_to_room(room.code, {
                "event": "number_drawn",
                "number": number,
                "room": serialize_room(room)
            })

# Global GameManager instance
game_manager = GameManager()

