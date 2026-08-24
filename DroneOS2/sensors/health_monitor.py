import asyncio
import time
from typing import Callable, Coroutine, Any
from DroneOS.shared.utils.logger import setup_logger

logger = setup_logger("HealthMonitor")

class HealthMonitor:
    """
    Monitors connection health by tracking heartbeats from GroundStation.
    """
    def __init__(self, timeout_seconds: float = 5.0, check_interval: float = 1.0):
        self.timeout_seconds = timeout_seconds
        self.check_interval = check_interval
        self.last_heartbeat_time: float | None = None
        
        self.on_connection_lost: Callable[[], Coroutine[Any, Any, None]] = None
        self.on_connection_restored: Callable[[], Coroutine[Any, Any, None]] = None
        self._running = False
        self._connection_lost = False
        
    def record_heartbeat(self) -> None:
        self.last_heartbeat_time = time.time()

    async def start(self) -> None:
        self._running = True
        self.last_heartbeat_time = None
        self._connection_lost = False
        logger.info("Health Monitor started.")
        
        while self._running:
            try:
                if self.last_heartbeat_time is not None:
                    time_since_last = time.time() - self.last_heartbeat_time
                    if time_since_last > self.timeout_seconds:
                        if not self._connection_lost:
                            self._connection_lost = True
                            logger.warning(f"CONNECTION LOST! No heartbeat for {time_since_last:.1f}s")
                            if self.on_connection_lost:
                                await self.on_connection_lost()
                    else:
                        if self._connection_lost:
                            self._connection_lost = False
                            logger.info("Connection restored!")
                            if self.on_connection_restored:
                                await self.on_connection_restored()
            except asyncio.CancelledError:
                logger.info("Health Monitor loop cancelled.")
                break
            except Exception as e:
                logger.exception(f"Error in health monitor: {e}")
                
            await asyncio.sleep(self.check_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("Health Monitor stopped.")
