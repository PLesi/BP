# Redis Installation and Setup

## Install Redis (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

## Verify Redis is running
```bash
redis-cli ping
# Should return: PONG
```

## Start Dramatiq Worker

In a separate terminal, run:
```bash
cd /home/plesi/Documents/BP
source .venv/bin/activate
dramatiq backend.app.tasks --processes 4 --threads 8
```

## Start FastAPI Server

In another terminal:
```bash
cd /home/plesi/Documents/BP
source .venv/bin/activate
uvicorn backend.app.main:app --reload
```

## Test the setup

1. Create a device with config:
```bash
curl -X POST http://localhost:8000/devices -H "Content-Type: application/json" -d '{"name": "Test Device"}'
```

2. Submit an experiment:
```bash
curl -X POST http://localhost:8000/experiments/run \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": 1,
    "input_values": {"temperature": 25.5, "duration": 60},
    "period": 3600,
    "frequency": 10
  }'
```

3. Check experiment status:
```bash
curl http://localhost:8000/experiments/status/{task_id}
```

## Architecture

```
User Request → FastAPI → Redis Queue → Dramatiq Worker → Device
                ↓                              ↓
            task_id                        Results
                ↓                              ↓
            Polling ← FastAPI ← Redis Results ←┘
```
