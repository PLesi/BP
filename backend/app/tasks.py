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


def _make_point(data: dict) -> dict | None:
    t = _to_float(data.get("time"))
    if t is None:
        return None

    skip = {"time", "status", "sim_status", "out_line", "log", "source", "error"}
    point = {"time": round(t, 6)}
    for k, v in data.items():
        if k not in skip:
            n = _to_float(v)
            if n is not None:
                point[k] = n

    return point if len(point) > 1 else None


def _parse_point(line: str, elapsed: float, columns: list[str] | None = None) -> dict | None:
    raw = line.strip()
    if not raw:
        return None

    # Try JSON line first.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _make_point(parsed)
    except json.JSONDecodeError:
        pass

    # key=value or key:value pairs
    kv: dict = {}
    for token in re.split(r"[;,]\s*", raw):
        if "=" in token:
            k, v = token.split("=", 1)
        elif ":" in token:
            k, v = token.split(":", 1)
        else:
            continue
        k = k.strip()
        if k and (n := _to_float(v)) is not None:
            kv[k] = n

    if kv:
        return {"time": round(elapsed, 6), **kv}

    # fallback: CSV numbers mapped to column headers or v1..vN
    numbers = [_to_float(m.group(0)) for m in _NUM_RE.finditer(raw)]
    values = [n for n in numbers if n is not None]
    if values:
        point: dict = {"time": round(elapsed, 6)}
        for idx, num in enumerate(values):
            if columns and idx < len(columns):
                col = columns[idx]
                if col.lower() in {"time", "t", "timestamp"}:
                    # first column is usually time on x-axis
                    point["time"] = round(num, 6)
                else:
                    point[col] = num
            else:
                point[f"v{idx + 1}"] = num
        # skip if only time field survived
        if len(point) > 1:
            return point

    return None

def acquire_lock(device_id: int, task_id: str | None = None) -> bool:
    ok = redis_client.set(
        f"device_lock:{device_id}",
        json.dumps({"task_id": task_id, "acquired_at": datetime.now(UTC).isoformat(), "pid": os.getpid()}),
        nx=True,
        ex=LOCK_TTL_SECONDS,
    )
    print(f"Acquiring lock for device {device_id}: {ok}")
    return ok

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
    stopped_by_user: list[bool] = [False]  # mutable flag accessible from inner coroutines

    def _log_input_args(raw: dict) -> dict:
        """Strip internal fields (workspace) from input args for the log."""
        _exclude = {"workspace"}
        return {
            k: {f: v for f, v in arg.items() if f not in _exclude}
            for k, arg in raw.items()
        }

    input_history: list[dict] = [
        {
            "command": "start",
            "input_args": _log_input_args(experiment.get("input_arguments", {})),
            "applied_at": 0.0,
        }
    ]
    started_at = datetime.now(UTC).isoformat()
    run_start_ts = asyncio.get_running_loop().time()
    out_columns: list[str] | None = None

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
        chart_point = _make_point(data) if isinstance(data, dict) else None
        if chart_point:
            await ws_manager.send_message(task_id, {
                "status": "chart_point",
                "device_id": device_id,
                "data": chart_point,
            })

    async def stream_stdout():
        nonlocal stdout_seen, out_columns
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

                # column header announcement
                if isinstance(data, dict) and data.get("status") == "headers":
                    out_columns = data.get("columns") or None
                    continue

                # out_line from out.txt — parse into clean named dict
                if isinstance(data, dict) and "out_line" in data:
                    elapsed = round(asyncio.get_running_loop().time() - run_start_ts, 2)
                    out_line = data["out_line"]
                    if isinstance(out_line, dict):
                        chart_point = out_line
                    else:
                        chart_point = _parse_point(out_line, elapsed, out_columns)
                    if chart_point:
                        output_history.append(chart_point)
                        await ws_manager.send_message(task_id, {
                            "status": "running",
                            "device_id": device_id,
                            "data": {**data, "out_line": chart_point},
                        })
                    else:
                        await ws_manager.send_message(task_id, {
                            "status": "running",
                            "device_id": device_id,
                            "data": data,
                        })
                else:
                    # Heartbeat / direct measurement — extract clean point if present
                    chart_point = _make_point(data) if isinstance(data, dict) else None
                    if chart_point:
                        output_history.append(chart_point)
                    await ws_manager.send_message(task_id, {
                        "status": "running",
                        "device_id": device_id,
                        "data": data,
                    })
            except json.JSONDecodeError:
                elapsed = round(asyncio.get_running_loop().time() - run_start_ts, 2)
                chart_point = _parse_point(output, elapsed, out_columns)
                await ws_manager.send_message(task_id, {
                    "status": "running",
                    "device_id": device_id,
                    "output": output
                })
                if chart_point:
                    output_history.append(chart_point)

    async def stream_output_file_fallback():
        # nothing on stdout after 3s — read output file directly
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
                        await send_running_with_chart(payload)
                        chart_point = _parse_point(line, elapsed, out_columns)
                        if chart_point:
                            output_history.append(chart_point)

            await asyncio.sleep(0.5)

    async def poll_input_changes():
        """Poll Redis for incoming change/stop commands and apply them."""
        change_script = os.path.join(os.path.dirname(__file__), 'routers', 'change.py')
        stop_script = os.path.join(os.path.dirname(__file__), 'routers', 'stop.py')
        while process.returncode is None:
            # --- stop signal ---
            if redis_client.rpop(f"stop_signal:{task_id}"):
                stopped_by_user[0] = True
                stop_proc = await asyncio.create_subprocess_exec(
                    sys.executable, stop_script,
                    '--slx-model', experiment.get("slx_model", "PI_RED.slx"),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await stop_proc.communicate()
                # start.py will detect SimulationStatus==stopped and exit naturally.
                break
            change_raw = redis_client.rpop(f"input_changes:{task_id}")
            if change_raw:
                try:
                    change = json.loads(change_raw)
                    elapsed = round(asyncio.get_running_loop().time() - run_start_ts, 2)
                    input_args = change.get("input_args", {})
                    input_history.append({
                        "command": "change",
                        "input_args": _log_input_args(input_args),
                        "applied_at": elapsed,
                    })
                    # Invoke change.py to update MATLAB workspace variables.
                    change_proc = await asyncio.create_subprocess_exec(
                        sys.executable, change_script,
                        '--slx-model', experiment.get("slx_model", "PI_RED.slx"),
                        '--input-json', json.dumps(input_args),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    change_stdout, change_stderr = await change_proc.communicate()
                    if change_proc.returncode != 0:
                        err = change_stderr.decode().strip() if change_stderr else "unknown error"
                        await ws_manager.send_message(task_id, {
                            "status": "change_failed",
                            "device_id": device_id,
                            "error": err,
                        })
                    else:
                        await ws_manager.send_message(task_id, {
                            "status": "change_applied",
                            "device_id": device_id,
                            "applied_at": elapsed,
                        })
                except (json.JSONDecodeError, KeyError):
                    pass
            await asyncio.sleep(0.1)

    stdout_task = asyncio.create_task(stream_stdout())
    fallback_task = asyncio.create_task(stream_output_file_fallback())
    change_poll_task = asyncio.create_task(poll_input_changes())

    await stdout_task
    await process.wait()
    await fallback_task
    change_poll_task.cancel()
    try:
        await change_poll_task
    except asyncio.CancelledError:
        pass
    # Clean up per-task Redis keys
    redis_client.delete(f"input_changes:{task_id}")
    redis_client.delete(f"stop_signal:{task_id}")

    def _build_run() -> dict:
        return {
            "input_history": input_history,
            "output_history": output_history,
        }

    if process.returncode != 0:
        stderr_output = await process.stderr.read()
        error_text = stderr_output.decode().strip() if stderr_output else "Unknown execution error"
        failed_log = {
            "device_name": experiment.get("device_name", ""),
            "software_name": experiment.get("software_name", ""),
            "run": _build_run(),
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "finish_reason": f"failed: {error_text}",
        }
        redis_client.set(experiment_key, json.dumps(failed_log))
        await ws_manager.send_message(
            task_id,
            {
                "status": "failed",
                "device_id": device_id,
                "error": error_text,
            },
        )
        return

    finished_at = datetime.now(UTC).isoformat()
    finish_reason = "user_stopped" if stopped_by_user[0] else "simulation_time_reached"
    final_log = {
        "device_name": experiment.get("device_name", ""),
        "software_name": experiment.get("software_name", ""),
        "run": _build_run(),
        "started_at": started_at,
        "finished_at": finished_at,
        "finish_reason": finish_reason,
    }
    redis_client.set(experiment_key, json.dumps(final_log))
    print(f"Experiment {'stopped' if stopped_by_user[0] else 'completed'} for task {task_id}")
    ws_status = "stopped" if stopped_by_user[0] else "completed"
    await ws_manager.send_message(task_id, {
        "status": ws_status,
        "device_id": device_id,
        "result": final_log,
    })

async def update_queue_positions(device_id: int):
    queue_key = f"device_queue:{device_id}"
    for task_json in redis_client.lrange(queue_key, 0, -1):
        task = json.loads(task_json)
        task_id = task["task_id"]
        estimated_wait_and_position = calculate_estimated_wait_time(device_id, task_id)
        await ws_manager.send_message(task_id, estimated_wait_and_position)
