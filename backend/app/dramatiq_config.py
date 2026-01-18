"""
Dramatiq configuration for experiment task queue
"""
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AsyncIO

# Redis broker configuration
redis_broker = RedisBroker(
    host="localhost",
    port=6379,
    db=0
)

# Add AsyncIO middleware for async support
redis_broker.add_middleware(AsyncIO())

# Set as default broker
dramatiq.set_broker(redis_broker)
