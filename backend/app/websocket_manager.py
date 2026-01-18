"""
WebSocket manager for broadcasting experiment results
"""
from fastapi import WebSocket
from typing import Dict, Set
import json


class WebSocketManager:
    """Manages WebSocket connections and broadcasts"""
    
    def __init__(self):
        # Dictionary mapping task_id to set of connected websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # All connections for broadcast
        self.all_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket, task_id: str = None):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.all_connections.add(websocket)
        
        if task_id:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = set()
            self.active_connections[task_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, task_id: str = None):
        self.all_connections.discard(websocket)
        
        if task_id and task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
    
    async def send_to_task_subscribers(self, task_id: str, message: dict):
        """Send message to all clients subscribed to specific task_id"""
        if task_id in self.active_connections:
            disconnected = set()
            for websocket in self.active_connections[task_id]:
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.add(websocket)
            
            # Clean up disconnected clients
            for websocket in disconnected:
                self.disconnect(websocket, task_id)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = set()
        for websocket in self.all_connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.add(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            self.all_connections.discard(websocket)


# Global WebSocket manager instance
ws_manager = WebSocketManager()
