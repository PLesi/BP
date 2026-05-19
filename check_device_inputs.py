"""
Check inputs for a device
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app.db import get_session, init_db
from backend.app.models import Device, Config, Input
from sqlalchemy import select
from sqlalchemy.orm import selectinload

async def check_device(device_id: int):
    """Check inputs for a device"""
    
    await init_db()
    
    async for session in get_session():
        # Get device with config and inputs
        stmt = (
            select(Device)
            .where(Device.id == device_id)
            .options(
                selectinload(Device.config).selectinload(Config.inputs)
            )
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        
        if not device:
            print(f"Device {device_id} not found")
            return
        
        if not device.config:
            print(f"Device {device_id} has no config")
            return
        
        print(f"\n📱 Device: {device.name} (ID: {device.id})")
        print(f"   Inputs:")
        for inp in device.config.inputs:
            print(f"     - {inp.name} (type: {inp.type}, id: {inp.id})")

if __name__ == "__main__":
    device_id = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(check_device(device_id))
