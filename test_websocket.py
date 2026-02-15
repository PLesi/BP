import asyncio
import websockets
import json
import httpx

async def test_experiment():
    # 1. Spusti experiment
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/experiments/run',
            json={
                "device_id": 1,
                "input_values": {"multiplier": 2},
                "period": 10,
                "frequency": 1
            }
        )
        data = response.json()
        task_id = data['task_id']
        print(f"Experiment started: {task_id}")
    
    # 2. Pripoj sa na WebSocket
    uri = f"ws://localhost:8000/experiments/ws/{task_id}"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to WebSocket: {task_id}")
        
        # 3. Počúvaj správy
        async for message in websocket:
            data = json.loads(message)
            print(f"Received: {data}")
            
            if data.get('status') == 'completed':
                print("Experiment completed!")
                break

if __name__ == "__main__":
    asyncio.run(test_experiment())