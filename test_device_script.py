import sys
import os
import json
import argparse
import subprocess
import time
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--task-id', required=True)
parser.add_argument('--device-id', required=True)
parser.add_argument('--device-name', required=True)
parser.add_argument('--software-name', required=True)
parser.add_argument('--port', required=False, default='/dev/ttyUSB0')
parser.add_argument('--output-path', required=False, default='out.txt')
parser.add_argument('--slx-model', required=False, default='PI_RED.slx')
parser.add_argument('--input-arguments', required=True)
parser.add_argument('--output-arguments', required=True)
parser.add_argument('--simulation-time', required=True)
parser.add_argument('--sample-rate', required=True)
parser.add_argument('--setpoint-changes', required=False, default='null')
args = parser.parse_args()

input_arguments = json.loads(args.input_arguments)
simulation_time = int(float(args.simulation_time))
sample_rate = float(args.sample_rate)


def pick_python_with_matlab() -> str:
    # Prefer explicit override if set.
    env_python = os.getenv("MATLAB_PYTHON_EXECUTABLE")
    candidates = [
        env_python,
        sys.executable,
        shutil.which("python3"),
        "/usr/bin/python3",
    ]

    tested: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.abspath(candidate)
        if candidate in tested:
            continue
        tested.add(candidate)

        probe = subprocess.run(
            [candidate, "-c", "import matlab.engine"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return candidate

    raise RuntimeError(
        "No Python interpreter with matlab.engine found. "
        "Set MATLAB_PYTHON_EXECUTABLE to your system Python."
    )

start_script = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'backend', 'app', 'routers', 'start.py'
)

cmd = [
    pick_python_with_matlab(), start_script,
    f'--port={args.port}',
    f'--output={args.output_path}',
    f'--slx-model={args.slx_model}',
    f'--input-json={args.input_arguments}',
    f'--duration={simulation_time}',
    f'--sampletime={sample_rate}',
]

process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

start_time = time.time()

for line in process.stdout:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
        print(json.dumps(data), flush=True)
    except json.JSONDecodeError:
        elapsed = round(time.time() - start_time, 2)
        print(json.dumps({"time": elapsed, "log": line}), flush=True)

process.wait()

if process.returncode != 0:
    err = process.stderr.read()
    print(json.dumps({"time": -1, "error": err}), flush=True)
    sys.exit(process.returncode)