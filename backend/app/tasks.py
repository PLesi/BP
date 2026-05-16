import dramatiq
import json
import asyncio
from datetime import datetime, UTC
import sys
import os

from .redis_client import redis_client
from .websocket_manager import ws_manager
from .services.services import calculate_estimated_wait_time

def acquire_lock(device_id: int) -> bool:
    lock_key = f"device_lock:{device_id}"
    result = redis_client.set(lock_key, "locked", nx=True)
    print(f"Acquiring lock for device {device_id}: {result}")
    return result

def release_lock(device_id: int):
    lock_key = f"device_lock:{device_id}"
    redis_client.delete(lock_key)
    print(f"Released lock for device {device_id}")

    if redis_client.llen(f"device_queue:{device_id}") > 0:
        print(f"Found more tasks in queue for device {device_id}, triggering worker")

        asyncio.run(update_queue_positions(device_id))
        device_worker.send(device_id)


@dramatiq.actor
def device_worker(device_id: int):
    print(f"Worker started for device {device_id}")
    
    queued_task = redis_client.rpop(f"device_queue:{device_id}")
    print(f"Popped from queue: {queued_task}")
    
    if not queued_task:
        print(f"Queue empty for device {device_id}")
        return

    if not acquire_lock(device_id): 
        print(f"Device {device_id} is locked, returning task to queue")
        redis_client.rpush(f"device_queue:{device_id}", queued_task)
        return

    try:
        experiment = json.loads(queued_task)
        print(f"Running experiment: {experiment.get('task_id')}")
        asyncio.run(run_experiment(experiment))
        
    finally:
        release_lock(device_id)


async def run_experiment(experiment: dict):
    task_id = experiment["task_id"]
    device_id = experiment["device_id"]
    experiment_key = f"experiment:{task_id}"
    output_history: list[dict] = []
    started_at = datetime.now(UTC).isoformat()

    redis_client.set(
        experiment_key,
        json.dumps(
            {
                "device_name": experiment.get("device_name", ""),
                "software_name": experiment.get("software_name", ""),
                "run": None,
                "started_at": started_at,
                "finished_at": None,
                "finish_reason": "n/a",
            }
        ),
    )

    print(f"Sending 'starting' message for task {task_id}")
    await ws_manager.send_message(task_id, {"status": "starting", "device_id": device_id})

    print(f"Starting subprocess for task {task_id}")
    process = await asyncio.create_subprocess_exec(
        sys.executable, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'test_device_script.py'),
        '--task-id', task_id,
        '--device-id', str(device_id),
        '--device-name', experiment.get("device_name", ""),
        '--software-name', experiment.get("software_name", ""),
        '--port', experiment.get("port", "/dev/ttyUSB0"),
        '--output-path', experiment.get("output_path", "out.txt"),
        '--slx-model', experiment.get("slx_model", "PI_RED.slx"),
        '--input-arguments', json.dumps(experiment.get("input_arguments", {})),
        '--output-arguments', json.dumps(experiment.get("output_arguments", [])),
        '--simulation-time', str(experiment.get("simulation_time", 0)),
        '--sample-rate', str(experiment.get("sample_rate", 1)),
        '--setpoint-changes', json.dumps(experiment.get("setpoint_changes")),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async for line in process.stdout:
        output = line.decode().strip()
        print(f"Output: {output}")
        try:
            data = json.loads(output)
            if isinstance(data, dict) and "time" in data:
                output_history.append(data)
            await ws_manager.send_message(task_id, {
                "status": "running",
                "device_id": device_id,
                "data": data                    
            })
        except json.JSONDecodeError:
            await ws_manager.send_message(task_id, {
                "status": "running",
                "device_id": device_id,
                "output": output                    
            })
    
    await process.wait()

    if process.returncode != 0:
        stderr_output = await process.stderr.read()
        error_text = stderr_output.decode().strip() if stderr_output else "Unknown execution error"
        redis_client.set(
            experiment_key,
            json.dumps(
                {
                    "device_name": experiment.get("device_name", ""),
                    "software_name": experiment.get("software_name", ""),
                    "run": {
                        "input_history": [
                            {
                                "command": "start",
                                "input_args": experiment.get("input_arguments", {}),
                                "applied_at": 0.0,
                            }
                        ],
                        "output_history": output_history,
                        "setpoint_changes": experiment.get("setpoint_changes"),
                    },
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "finish_reason": f"failed: {error_text}",
                }
            ),
        )
        await ws_manager.send_message(
            task_id,
            {
                "status": "failed",
                "device_id": device_id,
                "error": error_text,
            },
        )
        return

    redis_client.set(
        experiment_key,
        json.dumps(
            {
                "device_name": experiment.get("device_name", ""),
                "software_name": experiment.get("software_name", ""),
                "run": {
                    "input_history": [
                        {
                            "command": "start",
                            "input_args": experiment.get("input_arguments", {}),
                            "applied_at": 0.0,
                        }
                    ],
                    "output_history": output_history,
                    "setpoint_changes": experiment.get("setpoint_changes"),
                },
                "started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(),
                "finish_reason": "simulation_time_reached",
            }
        ),
    )
    print(f"Experiment completed for task {task_id}")
    await ws_manager.send_message(task_id, {"status": "completed", "device_id": device_id})

async def update_queue_positions(device_id: int):
    queue_key = f"device_queue:{device_id}"
    for task_json in redis_client.lrange(queue_key, 0, -1):
        task = json.loads(task_json)
        task_id = task["task_id"]
        estimated_wait_and_position = calculate_estimated_wait_time(device_id, task_id)
        await ws_manager.send_message(task_id, estimated_wait_and_position)
