from importlib import import_module
from pathlib import Path
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from ..models import Config, Device, Input


async def get_devices_with_details(session: AsyncSession) -> list[Device]:
	"""Return all devices with related config, software, inputs, outputs and time limit."""
	stmt = select(Device).options(
		selectinload(Device.config).selectinload(Config.software),
		selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
		selectinload(Device.config).selectinload(Config.outputs),
		selectinload(Device.config).selectinload(Config.time_limit)
	)
	results = await session.execute(stmt)
	return list(results.scalars().all())


import os
import matlab.engine

def check_device_online(port: str, slx_model: str) -> dict:
    """
    Skontroluje tri vrstvy pripravenosti zariadenia.
    
    Returns:
        {"online": bool, "usable": bool, "reason": str}
    """
    # 1. Serial port (fyzický HW)
    if not os.path.exists(port):
        return {"online": False, "usable": False, "reason": f"Port {port} not found"}

    # 2. MATLAB engine
    try:
        engines = matlab.engine.find_matlab()
    except Exception as e:
        return {"online": False, "usable": False, "reason": f"MATLAB engine error: {e}"}

    if not engines:
        return {"online": False, "usable": False, "reason": "No running MATLAB engine found"}

    # 3. Simulink model status
    try:
        matlab_instance = matlab.engine.connect_matlab(engines[0])
        matlab_instance.load_system(slx_model, nargout=0)
        status = matlab_instance.get_param(slx_model.replace(".slx", ""), "SimulationStatus")
    except Exception as e:
        return {"online": True, "usable": False, "reason": f"Simulink model error: {e}"}

    if status == "running":
        return {"online": True, "usable": False, "reason": "Device busy - simulation already running"}

    return {"online": True, "usable": True, "reason": "Device ready"}
