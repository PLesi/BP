"""
Delete problematic inputs with reserved keyword names
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

async def delete_reserved_inputs(device_id: int = None):
    """Delete inputs with reserved keyword names"""
    
    # Reserved keywords
    RESERVED = {
        'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
        'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
        'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise',
        'return', 'try', 'while', 'with', 'yield',
    }
    
    await init_db()
    
    async for session in get_session():
        # Get all devices or specific device
        if device_id:
            stmt = select(Device).where(Device.id == device_id)
        else:
            stmt = select(Device)
        
        result = await session.execute(stmt)
        devices = result.scalars().all()
        
        for device in devices:
            if not device.config:
                continue
            
            bad_inputs = [inp for inp in device.config.inputs if inp.name.lower() in RESERVED]
            
            if bad_inputs:
                print(f"\n🔴 Device: {device.name} (ID: {device.id})")
                for inp in bad_inputs:
                    print(f"   Deleting reserved keyword input: '{inp.name}' (ID: {inp.id})")
                    await session.delete(inp)
                
                await session.commit()
                print(f"   ✅ Deleted {len(bad_inputs)} problematic input(s)")
            else:
                print(f"\n✅ Device {device.name} (ID: {device.id}) - No reserved keyword inputs")

if __name__ == "__main__":
    device_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(delete_reserved_inputs(device_id))
