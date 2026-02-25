import requests
import asyncio
import websockets
import json
import sys

SERVER_IP = "localhost"  # IP servera

print("=" * 60)
print("REMOTE TEST")
print("=" * 60)

# Test 1: Skontroluj či server responds
print("\n[1/3] Server connection")
print(f"     URL: http://{SERVER_IP}:8000/docs")
sys.stdout.flush()

try:
    resp = requests.get(f'http://{SERVER_IP}:8000/docs', timeout=5)
    print(f"     Status: {resp.status_code}")
    print("     Result: OK")
except requests.exceptions.ConnectionError as e:
    print(f"     Result: FAIL ({e})")
    print("     Hint: check firewall, server IP, port 8000")
    sys.exit(1)
except Exception as e:
    print(f"     Result: ERROR ({type(e).__name__}: {e})")
    sys.exit(1)

# Test 2: Spusti experiment
print("\n[2/3] Create experiment task")
sys.stdout.flush()

try:
    exp_resp = requests.post(f'http://{SERVER_IP}:8000/experiments/run',
                            json={
                                "device_id": 1,
                                "input_values": {"param1": 10},
                                "period": 60,
                                "frequency": 30
                            },
                            timeout=10)
    print(f"     Response status: {exp_resp.status_code}")
    task_data = exp_resp.json()
    task_id = task_data.get('task_id')
    print("     Result: OK")
    print(f"     Task ID: {task_id}")
except requests.exceptions.Timeout:
    print("     Result: TIMEOUT (server too slow)")
    sys.exit(1)
except requests.exceptions.JSONDecodeError as e:
    print(f"     Result: INVALID JSON ({exp_resp.text})")
    sys.exit(1)
except Exception as e:
    print(f"     Result: ERROR ({type(e).__name__}: {e})")
    sys.exit(1)

# Test 3: WebSocket pripojenie
print("\n[3/3] WebSocket")
sys.stdout.flush()

async def test_ws():
    try:
        uri = f"ws://{SERVER_IP}:8000/experiments/ws/{task_id}"
        print(f"     URI: {uri}")
        sys.stdout.flush()
        
        ws = await asyncio.wait_for(websockets.connect(uri), timeout=5)
        try:
            print("     Connected")
            max_messages = 50
            for i in range(max_messages):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    print(f"     [{i+1}] {msg}")
                    try:
                        data = json.loads(msg)
                        if data.get("status") == "completed":
                            print("     Experiment completed")
                            break
                    except json.JSONDecodeError:
                        pass
                except asyncio.TimeoutError:
                    print(f"     [{i+1}] Waiting for message...")
                    break
        finally:
            await ws.close()
    except asyncio.TimeoutError:
        print("     Result: TIMEOUT")
    except Exception as e:
        print(f"     Result: ERROR ({type(e).__name__}: {e})")

print()
asyncio.run(test_ws())

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)