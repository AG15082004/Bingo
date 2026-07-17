import os
import time
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Initialize logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Real-Time Multiplayer Bingo")

# Import our managers and helper tools
from game_manager import game_manager, serialize_room
from websocket_manager import manager

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")

# REST Request Models
class CreateRoomRequest(BaseModel):
    draw_interval: int = 5

# REST Routes
@app.post("/api/create-room")
async def create_room(payload: CreateRoomRequest):
    """Creates a new room code."""
    room = game_manager.create_room(
        host_id="",  # Will be populated by the first WS connection
        draw_interval=payload.draw_interval
    )
    return {"room_code": room.code}

@app.get("/api/check-room/{room_code}")
async def check_room(room_code: str):
    """Returns whether a room exists in memory."""
    room = game_manager.get_room(room_code)
    if room:
        return {"exists": True, "state": room.state}
    return {"exists": False}

# WS Endpoint
@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    """Handles real-time WebSocket communication for a room."""
    await websocket.accept()
    
    # Handshake Phase: Verify that player registers with name and ID
    player_id = None
    player_name = None
    
    try:
        handshake_data = await websocket.receive_json()
        if handshake_data.get("type") != "join_room":
            logger.warning("Invalid WS handshake type. Closing connection.")
            await websocket.close(code=1008)
            return
            
        player_name = handshake_data.get("player_name", "").strip()
        player_id = handshake_data.get("player_id", "").strip()
        
        if not player_name or not player_id:
            logger.warning("Empty name or player_id in WS handshake. Closing.")
            await websocket.close(code=1008)
            return
            
        room = game_manager.get_room(room_code)
        if not room:
            await websocket.send_json({"event": "error", "message": "Room not found."})
            await websocket.close()
            return
            
        # Register in WS Connection Manager
        manager.room_connections.setdefault(room.code, []).append(websocket)
        manager.connection_metadata[websocket] = (room.code, player_id)
        
        # Register in Game Manager
        player = await game_manager.add_player_to_room(room.code, player_id, player_name)
        
        # Send initial room state
        await manager.send_personal_message({
            "event": "room_state",
            "room": serialize_room(room),
            "my_player_id": player_id
        }, websocket)
        
        # Notify others
        await manager.broadcast_to_room(room.code, {
            "event": "player_joined",
            "player_id": player_id,
            "player_name": player.name,
            "room": serialize_room(room)
        })
        
    except Exception as e:
        logger.error(f"WS handshaking error for room {room_code}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    # Message Listening Phase
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            # Fetch latest room/player state
            room = game_manager.get_room(room_code)
            if not room:
                await websocket.send_json({"event": "error", "message": "Room has been deleted."})
                break
                
            player = room.players.get(player_id)
            if not player:
                await websocket.send_json({"event": "error", "message": "Player session expired."})
                break
                
            if msg_type == "start_game":
                if player.is_host:
                    await game_manager.start_game(room.code)
                else:
                    await websocket.send_json({"event": "error", "message": "Only the host can start the game."})
                    
            elif msg_type == "play_again":
                if player.is_host:
                    await game_manager.start_game(room.code)
                else:
                    await websocket.send_json({"event": "error", "message": "Only the host can restart the game."})
                    
            elif msg_type == "select_number":
                num = data.get("number")
                if num is not None:
                    await game_manager.select_number(room.code, player_id, int(num))

                    
            elif msg_type == "send_chat":
                msg_text = data.get("message", "").strip()
                if msg_text:
                    chat_msg = {
                        "name": player.name,
                        "timestamp": time.strftime("%H:%M"),
                        "message": msg_text[:200]  # Cap length for safety
                    }
                    room.chat_history.append(chat_msg)
                    if len(room.chat_history) > 40:
                        room.chat_history.pop(0)
                        
                    await manager.broadcast_to_room(room.code, {
                        "event": "chat_message",
                        "chat": chat_msg
                    })
                    
            elif msg_type == "send_reaction":
                emoji = data.get("emoji", "").strip()
                if emoji in ["👍", "😂", "🔥", "🎉"]:
                    await manager.broadcast_to_room(room.code, {
                        "event": "reaction",
                        "player_name": player.name,
                        "emoji": emoji
                    })
                    
            elif msg_type == "leave_room":
                await game_manager.remove_player_from_room(room.code, player_id)
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket closed by client: Room {room_code}, Player {player_id}")
    except Exception as e:
        logger.error(f"Error handling WS message inside connection: {e}")
    finally:
        # Deregister connection and update player state
        r_code, p_id = manager.disconnect(websocket)
        if r_code and p_id:
            await game_manager.handle_player_disconnect(r_code, p_id)

# Serve UI Assets
@app.get("/")
async def get_index():
    """Serves the home page."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found. Ensure static files are placed in static/ folder.")
    return FileResponse(index_path)

@app.get("/room/{room_code}")
async def get_room_index(room_code: str):
    """Serves the room landing view."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(index_path)

# Serve Javascript and CSS stylesheets
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.error(f"Static directory not found at path: {STATIC_DIR}")
