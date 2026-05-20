from importlib import import_module
from pathlib import Path
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from ..models import Config, Device, Input


async def get_devices_with_details(session: AsyncSession) -> list[Device]:
	stmt = select(Device).options(
		selectinload(Device.config).selectinload(Config.software),
		selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
		selectinload(Device.config).selectinload(Config.outputs),
		selectinload(Device.config).selectinload(Config.time_limit)
	)
	results = await session.execute(stmt)
	return list(results.scalars().all())


import os
import logging

_log = logging.getLogger(__name__)

def check_device_online(port: str, slx_model: str) -> dict:
    # returns {"online": bool, "usable": bool, "reason": str}
    _log.debug("[check_device_online] port=%r slx_model=%r", port, slx_model)

    try:
        import matlab.engine
    except ImportError:
        reason = "MATLAB engine not installed"
        _log.warning("[check_device_online] FAIL – %s", reason)
        return {"online": False, "usable": False, "reason": reason}

    if not os.path.exists(port):
        reason = f"Port {port} not found"
        _log.warning("[check_device_online] FAIL – %s", reason)
        return {"online": False, "usable": False, "reason": reason}

    _log.debug("[check_device_online] port %r exists", port)

    try:
        engines = matlab.engine.find_matlab()
    except Exception as e:
        reason = f"MATLAB engine error: {e}"
        _log.warning("[check_device_online] FAIL – %s", reason)
        return {"online": False, "usable": False, "reason": reason}

    _log.debug("[check_device_online] MATLAB engines found: %r", engines)

    if not engines:
        reason = "No running MATLAB engine found"
        _log.warning("[check_device_online] FAIL – %s", reason)
        return {"online": False, "usable": False, "reason": reason}

    try:
        matlab_instance = matlab.engine.connect_matlab(engines[0])
        _log.debug("[check_device_online] connected to engine %r", engines[0])
        matlab_instance.load_system(slx_model, nargout=0)
        status = matlab_instance.get_param(slx_model.replace(".slx", ""), "SimulationStatus")
        _log.debug("[check_device_online] SimulationStatus=%r", status)
    except Exception as e:
        reason = f"Simulink model error: {e}"
        _log.warning("[check_device_online] FAIL – %s", reason)
        return {"online": True, "usable": False, "reason": reason}

    if status == "running":
        reason = "Device busy - simulation already running"
        _log.warning("[check_device_online] FAIL – %s", reason)
        return {"online": True, "usable": False, "reason": reason}

    _log.debug("[check_device_online] OK – device ready")
    return {"online": True, "usable": True, "reason": "Device ready"}
