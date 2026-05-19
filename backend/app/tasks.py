import dramatiq
import json
import asyncio
from datetime import datetime, UTC
import sys
import os
import re

from .redis_client import redis_client
from .websocket_manager import ws_manager
from .services.services import calculate_estimated_wait_time, RESERVED_KEYWORDS


LOCK_TTL_SECONDS = 6 * 60 * 60


_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _to_float(value):
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            s = value.strip().replace(',', '.')
            if not s:
                return None
            return float(s)
    except (TypeError, ValueError):
        return None
    return None


def _chart_point_from_dict(data: dict) -> dict | None:
    time_val = _to_float(data.get("time"))
    if time_val is None:
        return None

    point = {"time": round(time_val, 6)}
    has_numeric = False

    for key, value in data.items():
        if key in {"time", "status", "sim_status", "out_line", "log", "source", "error"}:
            continue
        num = _to_float(value)
        if num is not None:
            point[key] = num
            has_numeric = True

    return point if has_numeric else None


def _chart_point_from_line(line: str, elapsed: float) -> dict | None:
    raw = line.strip()
    if not raw:
        return None

    # Try JSON line first.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _chart_point_from_dict(parsed)
    except json.JSONDecodeError:
        pass

    # Parse key=value or key:value pairs.
    pairs = {}
    for token in re.split(r"[;,]\s*", raw):
        if "=" in token:
            k, v = token.split("=", 1)
        elif ":" in token:
            k, v = token.split(":", 1)
        else:
            continue
        key = k.strip()
        if not key:
            continue
        num = _to_float(v)
        if num is not None:
            pairs[key] = num

    if pairs:
        return {"time": round(elapsed, 6), **pairs}

    # Fallback: if line contains only numbers/CSV-like tokens, map to v1..vN.
    numbers = [_to_float(m.group(0)) for m in _NUM_RE.finditer(raw)]
    values = [n for n in numbers if n is not None]
    if values:
        point = {"time": round(elapsed, 6)}
        for idx, num in enumerate(values, start=1):
            point[f"v{idx}"] = num
        return point

    return None

def acquire_lock(device_id: int, task_id: str | None = None) -> bool:
    lock_key = f"device_lock:{device_id}"
    lock_payload = {
        "task_id": task_id,
        "acquired_at": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
    }
    result = redis_client.set(
        lock_key,
        json.dumps(lock_payload),
        nx=True,
        ex=LOCK_TTL_SECONDS,
    )
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

    acquired = False
    try:
        experiment = json.loads(queued_task)
        print(f"Running experiment: {experiment.get('task_id')}")
        acquired = acquire_lock(device_id, experiment.get("task_id"))
        if not acquired:
            print(f"Device {device_id} is locked, returning task to queue")
            redis_client.rpush(f"device_queue:{device_id}", queued_task)
            return
        asyncio.run(run_experiment(experiment))
        
    finally:
        if acquired:
            release_lock(device_id)


async def run_experiment(experiment: dict):
    task_id = experiment["task_id"]
    device_id = experiment["device_id"]
    experiment_key = f"experiment:{task_id}"
    output_history: list[dict] = []
    started_at = datetime.now(UTC).isoformat()
    run_start_ts = asyncio.get_running_loop().time()

    # Validate that input arguments don't use reserved keywords
    input_arguments = experiment.get("input_arguments", {})
    for input_name in input_arguments:
        if input_name.lower() in RESERVED_KEYWORDS:
            error_msg = f"Device configuration error: Input name '{input_name}' is a reserved keyword"
            await ws_manager.send_message(task_id, {"status": "error", "device_id": device_id, "error": error_msg})
            redis_client.set(
                experiment_key,
                json.dumps({
                    "device_name": experiment.get("device_name", ""),
                    "software_name": experiment.get("software_name", ""),
                    "run": None,
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "finish_reason": error_msg,
                }),
            )
            return

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
        sys.executable, os.path.join(os.path.dirname(__file__), '..', '..', 'test_device_script.py'),
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

    stdout_seen = False

    async def send_running_with_chart(data: dict):
        await ws_manager.send_message(task_id, {
            "status": "running",
            "device_id": device_id,
            "data": data
        })
        chart_point = _chart_point_from_dict(data) if isinstance(data, dict) else None
        if chart_point:
            await ws_manager.send_message(task_id, {
                "status": "chart_point",
                "device_id": device_id,
                "data": chart_point,
            })

    async def stream_stdout():
        nonlocal stdout_seen
        if process.stdout is None:
            return
        async for line in process.stdout:
            stdout_seen = True
            output = line.decode().strip()
            if not output:
                continue
            print(f"Output: {output}")
            try:
                data = json.loads(output)
                if isinstance(data, dict) and "time" in data:
                    output_history.append(data)
                await send_running_with_chart(data)
            except json.JSONDecodeError:
                elapsed = round(asyncio.get_running_loop().time() - run_start_ts, 2)
                chart_point = _chart_point_from_line(output, elapsed)
                await ws_manager.send_message(task_id, {
                    "status": "running",
                    "device_id": device_id,
                    "output": output
                })
                if chart_point:
                    output_history.append(chart_point)
                    await ws_manager.send_message(task_id, {
                        "status": "chart_point",
                        "device_id": device_id,
                        "data": chart_point,
                    })

    async def stream_output_file_fallback():
        # If nothing arrives on stdout, stream new lines from output file directly.
        await asyncio.sleep(3)
        if stdout_seen:
            return

        output_path = experiment.get("output_path")
        if not output_path:
            return

        last_pos = 0
        if os.path.exists(output_path):
            try:
                last_pos = os.path.getsize(output_path)
            except OSError:
                last_pos = 0

        while process.returncode is None:
            if os.path.exists(output_path):
                try:
                    with open(output_path, "r", encoding="utf-8", errors="replace") as out_file:
                        out_file.seek(last_pos)
                        chunk = out_file.read()
                        last_pos = out_file.tell()
                except OSError:
                    chunk = ""

                if chunk:
                    elapsed = round(asyncio.get_running_loop().time() - run_start_ts, 2)
                    for raw_line in chunk.splitlines():
                        line = raw_line.strip()
                        if not line:
                            continue
                        payload = {
                            "time": elapsed,
                            "out_line": line,
                            "source": "output_file",
                        }
                        output_history.append(payload)
                        await send_running_with_chart(payload)
                        chart_point = _chart_point_from_line(line, elapsed)
                        if chart_point:
                            output_history.append(chart_point)
                            await ws_manager.send_message(task_id, {
                                "status": "chart_point",
                                "device_id": device_id,
                                "data": chart_point,
                            })

            await asyncio.sleep(0.5)

    stdout_task = asyncio.create_task(stream_stdout())
    fallback_task = asyncio.create_task(stream_output_file_fallback())

    await stdout_task
    await process.wait()
    await fallback_task

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
