#!/usr/bin/python3

# example command: python3 start.py --port=/dev/ttyUSB0 --output=out.txt --input=bulb:100,fan:0,led:100,reg_output:light_intensity,reg_signal:bulb,reg_target:35,Kc:2,Ti:1,U_min:0,U_max:5 --duration=10 --sampletime=10

import time
import os
import sys

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

import matlab.engine

logger.info('trying to connect MATLAB shared engine = \'iolabserver_engine\'')
matlab_instance = matlab.engine.connect_matlab('iolabserver_engine')  # Try directly connect MATLAB
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
    
# logger.info('simulation is running, hold on...')
while matlab_instance.get_param(model_name, 'SimulationStatus') != 'stopped':
    pass

logger.info('simulation stopped, closing MATLAB instance...')
matlab_instance.quit()

logger.info('done... bye!')
