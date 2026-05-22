#!/usr/bin/python3

# example command:
# python3 change.py \
#   --slx-model=PI_RED.slx \
#   --input-json='{"fan":{"value":0,"type":"number","unit":"","order":1,"workspace":"inputs"},"bulb":{"value":100,"type":"number","unit":"","order":2,"workspace":"inputs"}}'

import os
import sys
import json
import time

import logging

logger = logging.getLogger('uDAQ_logger')
logger.setLevel(logging.DEBUG)
fhandler = logging.FileHandler("/home/mackousko/Documents/pymatlab.log")
fhandler.setLevel(logging.DEBUG)
logformat = logging.Formatter('[%(asctime)s] - %(name)s - [%(levelname)s] - %(message)s')
fhandler.setFormatter(logformat)
logger.addHandler(fhandler)
logger.info('_:: Python MATLAB change.py logger was initialized. ::_')


import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--input-json', type=str, required=True,
                    help='JSON object of validated input arguments, e.g. {"fan":{"value":0}, ...}')
parser.add_argument('--slx-model', type=str, default='PI_RED.slx',
                    help='Simulink model filename (e.g. PI_RED.slx)')

args = parser.parse_args()

# Parse input JSON — same format as start.py
_input_meta = json.loads(args.input_json)

import matlab.engine

logger.info("trying to connect MATLAB shared engine = 'iolabserver_engine'")
matlab_instance = matlab.engine.connect_matlab('iolabserver_engine')
i = 0
if matlab_instance is None:
    logger.info("'iolabserver_engine' shared engine not found...")
    logger.info('Trying to find any running MATLAB shared engine.')
    try:
        while len(matlab.engine.find_matlab()) == 0:
            time.sleep(5)
            i += 1
            if (i * 5) > 35:
                logger.info('No shared engine found — cannot apply change without a running MATLAB session.')
                print(json.dumps({"status": "error", "error": "No running MATLAB shared engine found."}), flush=True)
                sys.exit(1)
    except Exception as ex:
        logger.exception('ERROR: exception while finding MATLAB.')
        print(json.dumps({"status": "error", "error": str(ex)}), flush=True)
        sys.exit(1)

if matlab_instance is None:
    logger.info('Trying to connect running MATLAB shared engine.')
    matlab_instance = matlab.engine.connect_matlab(matlab.engine.find_matlab()[0])

# Resolve model name — same logic as start.py
slx_model = args.slx_model.strip() if args.slx_model else 'PI_RED.slx'
model_file = slx_model if slx_model.endswith('.slx') else f"{slx_model}.slx"
model_name = os.path.splitext(os.path.basename(model_file))[0]

# Require an active simulation — change command cannot work on a stopped model.
sim_status = matlab_instance.get_param(model_name, 'SimulationStatus')
if sim_status == 'stopped':
    logger.info('Simulation is stopped, nothing to change. Exiting.')
    print(json.dumps({"status": "error", "error": "Simulation is not running. change command requires an active experiment run."}), flush=True)
    sys.exit(1)

logger.info('Simulation is running. Applying change...')

# String → MATLAB numeric code map (same hardware constants as start.py).
_str_to_num = {
    'temperature': 1.0, 'light_intensity': 2.0, 'fan_rpm': 3.0,
    'bulb': 1.0, 'fan': 2.0, 'led': 3.0,
}

_ws_inputs = {}
_ws_regparams = {}

for _k, _meta in _input_meta.items():
    _value = _meta['value']
    _target = _meta.get('workspace', 'inputs')
    if _target == 'regparams':
        if isinstance(_value, str):
            _ws_regparams[_k] = _str_to_num.get(_value, 0.0)
        else:
            _ws_regparams[_k] = float(_value)
    else:
        if not isinstance(_value, bool):
            if isinstance(_value, str):
                _ws_inputs[_k] = _str_to_num.get(_value, 0.0)
            else:
                _ws_inputs[_k] = float(_value)

matlab_instance.workspace['inputs'] = _ws_inputs
matlab_instance.workspace['regparams'] = _ws_regparams

logger.info('MATLAB workspace variables updated.')

try:
    matlab_instance.set_param(model_name, 'SimulationCommand', 'update', nargout=0)
except Exception as ex:
    logger.exception('ERROR: exception while applying SimulationCommand update.')
    print(json.dumps({"status": "error", "error": str(ex)}), flush=True)
    sys.exit(1)

logger.info('Change applied successfully.')
print(json.dumps({"status": "change_applied"}), flush=True)

# Do NOT call matlab_instance.quit() — the simulation started by start.py
# is still running and owns the MATLAB session lifecycle.
