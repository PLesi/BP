from fastapi import WebSocket
from typing import Dict
import json
import redis

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

class WebSocketManager:    
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.connections[task_id] = websocket
        print(f"🔌 WebSocket connected for task {task_id}")

    async def disconnect(self, websocket: WebSocket, task_id: str):
        if task_id in self.connections:
            del self.connections[task_id]
            print(f"🔌 WebSocket disconnected for task {task_id}")
    
    async def send_message(self, task_id: str, message: dict):
        """Send message directly if WS is in this process, otherwise publish to Redis"""
        if task_id in self.connections:
            print(f"📤 Sending message to WebSocket: {message}")
            await self.connections[task_id].send_json(message)
        else:
            # WebSocket not in this process, publish to Redis
            print(f"📡 Publishing to Redis channel ws:{task_id}")
            redis_client.publish(f"ws:{task_id}", json.dumps(message))
    
ws_manager = WebSocketManager()