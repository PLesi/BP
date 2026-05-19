#!/usr/bin/python3

# example command: python3 start.py --port=/dev/ttyUSB0 --output=out.txt --input=bulb:100,fan:0,led:100,reg_output:light_intensity,reg_signal:bulb,reg_target:35,Kc:2,Ti:1,U_min:0,U_max:5 --duration=10 --sampletime=10

import time
import os
import sys
import json
import re

# Custom logging mechanism for this script
import logging

logger = logging.getLogger('uDAQ_logger')  # Create logger witn name 'uDAQ_logger'.
logger.setLevel(logging.DEBUG)  # Set up logging utility with level=DEBUG (lowest)
# Create file handler for 'uDAQ_logger'.
fhandler = logging.FileHandler("/home/mackousko/Documents/pymatlab.log")
fhandler.setLevel(logging.DEBUG)
# Specify format of LOG messages and assign it to handler.
logformat = logging.Formatter('[%(asctime)s] - %(name)s - [%(levelname)s] - %(message)s')
fhandler.setFormatter(logformat)
# Assign file handler to 'uDAQ_logger' logging facility.
logger.addHandler(fhandler)
logger.info('_:: Python MATLAB start.py logger was initialized. ::_')



# Argument parser for olm-api arguments.
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=str, help='Path to serial device port e.g. /dev/ttyUSB0')
parser.add_argument('--output', type=str, help='Path to output file e.g. output.txt')
parser.add_argument('--input', type=str, help='Comma-separated key:value pairs of input parameters. e.g.: in_bulb:100,in_fan:100 etc...')
parser.add_argument('--duration', type=int, help='Duration of the simulation in seconds.')
parser.add_argument('--sampletime', type=float, help='Sampling time in milliseconds.')
parser.add_argument('--slx-model', type=str, default='PI_RED.slx', help='Simulink model filename (e.g. PI_RED.slx)')

args = parser.parse_args()
inputs = dict()

for keyval_pair in args.input.split(','):
    parameter = keyval_pair.split(':')
    inputs[parameter[0]] = parameter[1]


def _coerce_numeric(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    # matlab.double / list-like containers often come as one-element arrays.
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        first = value[0]
        if isinstance(first, (list, tuple)) and first:
            first = first[0]
        return _coerce_numeric(first)

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_numeric_outputs(outputs_obj):
    numeric = {}
    if not isinstance(outputs_obj, dict):
        return numeric

    for key, value in outputs_obj.items():
        num = _coerce_numeric(value)
        if num is not None:
            numeric[str(key)] = num
    return numeric


def _extract_numeric_outputs_from_matlab(matlab_instance):
    """Read MATLAB workspace `outputs` and convert it to flat numeric dict."""
    try:
        # jsonencode in MATLAB gives us a stable transport format for Python.
        encoded = matlab_instance.eval("jsonencode(outputs)", nargout=1)
    except Exception:
        return {}

    if not encoded:
        return {}

    try:
        parsed = json.loads(encoded)
    except json.JSONDecodeError:
        return {}

    numeric = {}
    if isinstance(parsed, dict):
        for key, value in parsed.items():
            num = _coerce_numeric(value)
            if num is not None:
                numeric[str(key)] = num
            elif isinstance(value, dict):
                # Keep one-level nested structures graphable as key.subkey.
                for sub_key, sub_val in value.items():
                    sub_num = _coerce_numeric(sub_val)
                    if sub_num is not None:
                        numeric[f"{key}.{sub_key}"] = sub_num
    return numeric


_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _extract_numeric_outputs_from_line(line: str, elapsed: float):
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
                num = _coerce_numeric(value)
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
        num = _coerce_numeric(value)
        if key and num is not None:
            kv_pairs[key] = num

    if kv_pairs:
        return {"time": round(elapsed, 6), **kv_pairs}

    values = []
    for match in _NUM_RE.finditer(raw):
        num = _coerce_numeric(match.group(0))
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


# Clear output variables in workspace from previous experiment runs.
logger.info('Clearing MATLAB workspace output variables.')
matlab_instance.workspace['outputs'] = {'temp':0, 'f_temp':0, 'intens':0, 'f_intens':0, 'fan_amp':0, 'fan_rpm':0, 'ambt':0}

logger.info('setting MATLAB workspace input variables:')
logger.info(args)

port = f"{args.port},{args.output}"

# Simulation parameters as port, simulation time, sampling rate.
matlab_instance.workspace['com_port'] = args.port  # COM port
matlab_instance.workspace['out_path'] = args.output  # COM port

matlab_instance.workspace['simparams'] = {
    't_sim':float(args.duration),  # Simulation time
    'Ts':1/float(args.sampletime),  # Sampling rate
    'duration':float(0)  # Sampled duration - output from simulation
} 

# Input values for system variables - light bulb, fan and LED.
matlab_instance.workspace['inputs'] = {
    'fan':float(inputs['fan']),  # Input value for fan
    'bulb':float(inputs['bulb']),  # Input value for light bulb
    'led':float(inputs['led'])  # Input value for LED diode
}

# Output variable for regulation i.e. wanted value.
reg_output = dict()
if inputs['reg_output'] == 'temperature':
    reg_output = {'reg_output':float(1)}
elif inputs['reg_output'] == 'light_intensity':
    reg_output = {'reg_output':float(2)}
elif inputs['reg_output'] == 'fan_rpm':
    reg_output = {'reg_output':float(3)}

# Control signal for regulation, i.e. action variable.
reg_signal = dict()
if inputs['reg_signal'] == 'bulb':
    reg_signal = {'reg_signal':float(1)}
elif inputs['reg_signal'] == 'fan':
    reg_signal = {'reg_signal':float(2)}
elif inputs['reg_signal'] == 'led':
    reg_signal = {'reg_signal':float(3)}

# Regulator specific values.    
matlab_instance.workspace['regparams'] = {
    **reg_signal, **reg_output,  # Merge values for acion variable and desired value
    'reg_target':float(inputs['reg_target']),  # Target value for regulator
    'Kc':float(inputs['Kc']),  # Kc parameter of regulator
    'Ti':float(inputs['Ti']),  # Ti parameter of regulator
    'U_min':float(inputs['U_min']),  # U_min limiter parameter
    'U_max':float(inputs['U_max'])  # U_max limiter parameter
}

logger.info('MATLAB workspace variables set...')
logger.info('trying to run Simuling simulation on uDAQ28LT_system...')

# Custom model hook kept for later use.
# slx_model = args.slx_model.strip() if args.slx_model else 'PI_RED.slx'
# model_file = slx_model if slx_model.endswith('.slx') else f"{slx_model}.slx"
# model_name = os.path.splitext(os.path.basename(model_file))[0]

model_file = "PI_RED.slx"
model_name = "PI_RED"

matlab_instance.load_system(model_file)

try:
    matlab_instance.set_param(model_name, 'SimulationCommand', 'start', nargout=0)
except Exception as ex:
    logger.exception('ERROR: exception while starting simulation.')
    matlab_instance.quit()
    raise

# Emit heartbeat messages so WS clients receive real-time progress.
start_ts = time.time()
last_out_pos = 0
if args.output and os.path.exists(args.output):
    # Start from EOF so WS gets only new lines from this run.
    last_out_pos = os.path.getsize(args.output)

while True:
    status = matlab_instance.get_param(model_name, 'SimulationStatus')
    elapsed = round(time.time() - start_ts, 2)

    if args.output and os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8', errors='replace') as out_file:
            out_file.seek(last_out_pos)
            chunk = out_file.read()
            last_out_pos = out_file.tell()

        if chunk:
            for line in chunk.splitlines():
                if line.strip():
                    output_point = _extract_numeric_outputs_from_line(line, elapsed)
                    payload = {"time": elapsed, "status": "running", "out_line": line}
                    if output_point:
                        payload["outputs"] = output_point
                    print(json.dumps(payload), flush=True)

    payload = {"time": elapsed, "status": "running", "sim_status": status}
    workspace_outputs = _extract_numeric_outputs_from_matlab(matlab_instance)
    if workspace_outputs:
        payload["workspace_outputs"] = workspace_outputs

    print(json.dumps(payload), flush=True)
    if status == 'stopped':
        break
    time.sleep(1.0)

# Flush final out.txt lines written right before simulation stop.
if args.output and os.path.exists(args.output):
    with open(args.output, 'r', encoding='utf-8', errors='replace') as out_file:
        out_file.seek(last_out_pos)
        tail_chunk = out_file.read()

    if tail_chunk:
        final_elapsed = round(time.time() - start_ts, 2)
        for line in tail_chunk.splitlines():
            if line.strip():
                output_point = _extract_numeric_outputs_from_line(line, final_elapsed)
                payload = {"time": final_elapsed, "status": "running", "out_line": line}
                if output_point:
                    payload["outputs"] = output_point
                print(json.dumps(payload), flush=True)

logger.info('simulation stopped, closing MATLAB instance...')
matlab_instance.quit()

logger.info('done... bye!')
