from fastapi import WebSocket
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # room_code -> list of active WebSocket connections
        self.room_connections: Dict[str, List[WebSocket]] = {}
        # websocket -> (room_code, player_id)
        self.connection_metadata: Dict[WebSocket, Tuple[str, str]] = {}

    async def connect(self, websocket: WebSocket, room_code: str, player_id: str):
        """Accepts a WebSocket connection and registers it in the room."""
        await websocket.accept()
        if room_code not in self.room_connections:
            self.room_connections[room_code] = []
        self.room_connections[room_code].append(websocket)
        self.connection_metadata[websocket] = (room_code, player_id)
        logger.info(f"WebSocket connected: Room {room_code}, Player {player_id}")

    def disconnect(self, websocket: WebSocket) -> Tuple[Optional[str], Optional[str]]:
        """
        Removes the WebSocket connection from registries.
        Returns (room_code, player_id) if it was registered, else (None, None).
        """
        meta = self.connection_metadata.pop(websocket, None)
        if meta:
            room_code, player_id = meta
            if room_code in self.room_connections:
                if websocket in self.room_connections[room_code]:
                    self.room_connections[room_code].remove(websocket)
                if not self.room_connections[room_code]:
                    del self.room_connections[room_code]
            logger.info(f"WebSocket disconnected: Room {room_code}, Player {player_id}")
            return room_code, player_id
        return None, None

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Sends a JSON message to a single WebSocket client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")

    async def broadcast_to_room(self, room_code: str, message: dict):
        """Broadcasts a JSON message to all active WebSockets in a room."""
        if room_code in self.room_connections:
            # Iterate over a copy of the list to handle disconnects gracefully
            for connection in list(self.room_connections[room_code]):
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to broadcast to connection: {e}")

# Global instance of connection manager
manager = ConnectionManager()
