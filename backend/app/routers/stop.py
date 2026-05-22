#!/usr/bin/python3

# example command:
# python3 stop.py --slx-model=PI_RED.slx

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
logger.info('_:: Python MATLAB stop.py logger was initialized. ::_')


import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--slx-model', type=str, default='PI_RED.slx',
                    help='Simulink model filename (e.g. PI_RED.slx)')

args = parser.parse_args()

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
                logger.info('No shared engine found — cannot stop without a running MATLAB session.')
                print(json.dumps({"status": "error", "error": "No running MATLAB shared engine found."}), flush=True)
                sys.exit(1)
    except Exception as ex:
        logger.exception('ERROR: exception while finding MATLAB.')
        print(json.dumps({"status": "error", "error": str(ex)}), flush=True)
        sys.exit(1)

if matlab_instance is None:
    logger.info('Trying to connect running MATLAB shared engine.')
    matlab_instance = matlab.engine.connect_matlab(matlab.engine.find_matlab()[0])

# Resolve model name — same logic as start.py / change.py
slx_model = args.slx_model.strip() if args.slx_model else 'PI_RED.slx'
model_file = slx_model if slx_model.endswith('.slx') else f"{slx_model}.slx"
model_name = os.path.splitext(os.path.basename(model_file))[0]

sim_status = matlab_instance.get_param(model_name, 'SimulationStatus')
if sim_status == 'stopped':
    logger.info('Simulation is already stopped — nothing to do.')
    print(json.dumps({"status": "already_stopped"}), flush=True)
    sys.exit(0)

logger.info('Simulation is running. Sending stop command...')
try:
    matlab_instance.set_param(model_name, 'SimulationCommand', 'stop', nargout=0)
except Exception as ex:
    logger.exception('ERROR: exception while sending stop command.')
    print(json.dumps({"status": "error", "error": str(ex)}), flush=True)
    sys.exit(1)

logger.info('Stop command sent successfully.')
print(json.dumps({"status": "stop_sent"}), flush=True)

# Do NOT call matlab_instance.quit() — start.py owns the MATLAB session lifecycle
# and will call quit() once it detects SimulationStatus == 'stopped'.
