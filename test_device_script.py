import sys
import time
import json
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--task-id', required=True)
parser.add_argument('--device-id', required=True)
parser.add_argument('--inputs', required=True)
args = parser.parse_args()

inputs = json.loads(args.inputs)

print(f"Starting experiment on device {args.device_id}")
print(f"Task ID: {args.task_id}")
print(f"Inputs: {inputs}")

# Simulácia počítania do 10
for i in range(1, 11):
    result = {
        "iteration": i,
        "value": i * inputs.get("multiplier", 1),
        "timestamp": time.time()
    }
    print(json.dumps(result))  # Toto pôjde do WebSocketu
    sys.stdout.flush()  # Dôležité pre real-time streaming
    time.sleep(1)

print(json.dumps({"status": "finished"}))