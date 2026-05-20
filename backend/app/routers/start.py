#!/usr/bin/python3

# example command: python3 start.py --port=/dev/ttyUSB0 --output=out.txt --input-json='{"fan":{"value":0},"bulb":{"value":100},"led":{"value":100},"reg_output":{"value":"light_intensity"},"reg_signal":{"value":"bulb"},"reg_target":{"value":35},"Kc":{"value":2},"Ti":{"value":1},"U_min":{"value":0},"U_max":{"value":5}}' --duration=10 --sampletime=10

import time
import os
import sys
import json
import re

import logging

logger = logging.getLogger('uDAQ_logger')
logger.setLevel(logging.DEBUG)
fhandler = logging.FileHandler("/home/mackousko/Documents/pymatlab.log")
fhandler.setLevel(logging.DEBUG)
logformat = logging.Formatter('[%(asctime)s] - %(name)s - [%(levelname)s] - %(message)s')
fhandler.setFormatter(logformat)
logger.addHandler(fhandler)
logger.info('_:: Python MATLAB start.py logger was initialized. ::_')



import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=str, help='Path to serial device port e.g. /dev/ttyUSB0')
parser.add_argument('--output', type=str, help='Path to output file e.g. output.txt')
parser.add_argument('--input-json', type=str, help='JSON object of validated input arguments, e.g. {"fan":{"value":0}, ...}')
parser.add_argument('--duration', type=int, help='Duration of the simulation in seconds.')
parser.add_argument('--sampletime', type=float, help='Sampling time in milliseconds.')
parser.add_argument('--slx-model', type=str, default='PI_RED.slx', help='Simulink model filename (e.g. PI_RED.slx)')

args = parser.parse_args()

# Parse input args — extract plain values from the validated JSON
inputs = {k: v['value'] for k, v in json.loads(args.input_json).items()}


def _to_num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    # matlab.double / list-like containers often come as one-element arrays
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        first = value[0]
        if isinstance(first, (list, tuple)) and first:
            first = first[0]
        return _to_num(first)

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_outputs(outputs_obj):
    if not isinstance(outputs_obj, dict):
        return {}
    numeric = {}
    for key, value in outputs_obj.items():
        num = _to_num(value)
        if num is not None:
            numeric[str(key)] = num
    return numeric


def _read_outputs(matlab_instance, model_name):
    try:
        outputs_obj = matlab_instance.workspace['outputs']
        return _parse_outputs(outputs_obj)
    except Exception:
        return {}


_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _line_to_point(line: str, elapsed: float):
    raw = line.strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            point = {"time": round(elapsed, 6)}
            has_numeric = False
            for key, value in parsed.items():
                if key in {"time", "status", "sim_status", "out_line", "log", "source", "error"}:
                    continue
                num = _to_num(value)
                if num is not None:
                    point[str(key)] = num
                    has_numeric = True
            return point if has_numeric else None
    except json.JSONDecodeError:
        pass

    kv_pairs = {}
    for token in re.split(r"[;,]\s*", raw):
        if "=" in token:
            key, value = token.split("=", 1)
        elif ":" in token:
            key, value = token.split(":", 1)
        else:
            continue

        key = key.strip()
        num = _to_num(value)
        if key and num is not None:
            kv_pairs[key] = num

    if kv_pairs:
        return {"time": round(elapsed, 6), **kv_pairs}

    values = []
    for match in _NUM_RE.finditer(raw):
        num = _to_num(match.group(0))
        if num is not None:
            values.append(num)

    if values:
        point = {"time": round(elapsed, 6)}
        for index, num in enumerate(values, start=1):
            point[f"v{index}"] = num
        return point

    return None

import matlab.engine

logger.info('trying to connect MATLAB shared engine = \'iolabserver_engine\'')
matlab_instance = matlab.engine.connect_matlab('iolabserver_engine')  
i = 0
if matlab_instance is None:
    logger.info('\'iolabserver_engine\' shared engine not found...')
    logger.info('Trying to find any running MATLAB shared engine.')
    try:
        while (len(matlab.engine.find_matlab()) == 0):
            time.sleep(5)
            i += 1
            if ((i*5) > 35):
                logger.info('No shared engine found...')
                logger.info('will try to start MATLAB directly, hang on...')
                matlab_instance = matlab.engine.start_matlab()
                matlab_instance.desktop(nargout=0)
                time.sleep(5)
                break
    except Exception as ex:
        logger.exception('ERROR: exception while finding/runnung MATLAB.')

if matlab_instance is None:
    logger.info('Trying to connect running MATLAB shared engine.')
    matlab_instance = matlab.engine.connect_matlab(matlab.engine.find_matlab()[0])


matlab_instance.workspace['outputs'] = {'temp':0, 'f_temp':0, 'intens':0, 'f_intens':0, 'fan_amp':0, 'fan_rpm':0, 'ambt':0}

logger.info('setting MATLAB workspace input variables:')
logger.info(args)

port = f"{args.port},{args.output}"

# Resolve out_path against MATLAB's CWD so both MATLAB and Python use the same absolute path.
if os.path.isabs(args.output):
    out_path = args.output
else:
    matlab_cwd = matlab_instance.pwd()
    out_path = os.path.join(matlab_cwd, args.output)

# Simulation parameters as port, simulation time, sampling rate.
matlab_instance.workspace['com_port'] = args.port
matlab_instance.workspace['out_path'] = out_path

matlab_instance.workspace['simparams'] = {
    't_sim': float(args.duration),          # Simulation time in seconds
    'Ts': 1.0 / float(args.sampletime),     # Sampling period in seconds
    'duration': float(0)                    # Sampled duration — written back by simulation
}

# device inputs — anything that's not a reg param
_reg_keys = {'reg_output', 'reg_signal', 'reg_target', 'Kc', 'Ti', 'U_min', 'U_max'}
matlab_instance.workspace['inputs'] = {
    k: float(v) for k, v in inputs.items() if k not in _reg_keys
}

# string names to MATLAB numeric codes
_reg_output_map = {'temperature': 1.0, 'light_intensity': 2.0, 'fan_rpm': 3.0}
_reg_signal_map = {'bulb': 1.0, 'fan': 2.0, 'led': 3.0}
reg_output = {'reg_output': _reg_output_map[inputs['reg_output']]} if inputs.get('reg_output') in _reg_output_map else {}
reg_signal = {'reg_signal': _reg_signal_map[inputs['reg_signal']]} if inputs.get('reg_signal') in _reg_signal_map else {}

_scalar_reg_keys = ['reg_target', 'Kc', 'Ti', 'U_min', 'U_max']
regparams = {**reg_signal, **reg_output}
for _k in _scalar_reg_keys:
    if _k in inputs:
        regparams[_k] = float(inputs[_k])
matlab_instance.workspace['regparams'] = regparams

logger.info('MATLAB workspace variables set...')
logger.info('trying to run Simuling simulation on uDAQ28LT_system...')

slx_model = args.slx_model.strip() if args.slx_model else 'PI_RED.slx'
model_file = slx_model if slx_model.endswith('.slx') else f"{slx_model}.slx"
model_name = os.path.splitext(os.path.basename(model_file))[0]

matlab_instance.load_system(model_file)

matlab_instance.set_param(model_name, 'StopTime', str(float(args.duration)), nargout=0)
ts = 1.0 / float(args.sampletime)
try:
    matlab_instance.set_param(model_name, 'FixedStep', str(ts), nargout=0)
except Exception:
    pass  # variable-step solver — sample time is controlled inside the model

try:
    matlab_instance.set_param(model_name, 'SimulationCommand', 'start', nargout=0)
except Exception as ex:
    logger.exception('ERROR: exception while starting simulation.')
    matlab_instance.quit()
    raise

# Emit heartbeat messages so WS clients receive real-time progress.
start_ts = time.time()
last_out_pos = 0
if out_path and os.path.exists(out_path):
    # Start from EOF so WS gets only new lines from this run.
    last_out_pos = os.path.getsize(out_path)

# Detect column headers from the first line of out.txt.
# Wait up to 10 s for MATLAB to create/write the file.
out_headers = None
if out_path:
    _wait = 0.0
    while not os.path.exists(out_path) and _wait < 10:
        time.sleep(0.5)
        _wait += 0.5
    if os.path.exists(out_path):
        try:
            with open(out_path, 'r', encoding='utf-8', errors='replace') as _hf:
                _first = _hf.readline().strip()
            if _first and re.search(r'[a-zA-Z_]', _first):
                out_headers = [h.strip() for h in re.split(r'[,\t]', _first)]
                print(json.dumps({"status": "headers", "columns": out_headers}), flush=True)
        except OSError:
            pass

while True:
    status = matlab_instance.get_param(model_name, 'SimulationStatus')
    elapsed = round(time.time() - start_ts, 2)
    data_sent = False

    if out_path and os.path.exists(out_path):
        current_size = os.path.getsize(out_path)
        if current_size < last_out_pos:
            # File was truncated/recreated — reset position.
            last_out_pos = 0

        with open(out_path, 'r', encoding='utf-8', errors='replace') as out_file:
            out_file.seek(last_out_pos)
            chunk = out_file.read()
            last_out_pos = out_file.tell()

        if chunk:
            for line in chunk.splitlines():
                if not line.strip():
                    continue
                # Skip header rows (lines that contain letters).
                if re.search(r'[a-zA-Z_]', line.strip()):
                    continue
                print(json.dumps({"time": elapsed, "status": "running", "out_line": line}), flush=True)
                data_sent = True

    # Only send the heartbeat when no out_line data was sent this tick.
    if not data_sent:
        print(json.dumps({"time": elapsed, "status": "running", "sim_status": status}), flush=True)
    if status == 'stopped':
        break
    time.sleep(1.0)

# Flush final out.txt lines written right before simulation stop.
if out_path and os.path.exists(out_path):
    with open(out_path, 'r', encoding='utf-8', errors='replace') as out_file:
        out_file.seek(last_out_pos)
        tail_chunk = out_file.read()

    if tail_chunk:
        final_elapsed = round(time.time() - start_ts, 2)
        for line in tail_chunk.splitlines():
            if not line.strip():
                continue
            if re.search(r'[a-zA-Z_]', line.strip()):
                continue
            print(json.dumps({"time": final_elapsed, "status": "running", "out_line": line}), flush=True)

logger.info('simulation stopped, closing MATLAB instance...')
matlab_instance.quit()

logger.info('done... bye!')
