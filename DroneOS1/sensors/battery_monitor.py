import asyncio
from typing import Callable, Coroutine, Any, Optional
from DroneOS.shared.utils.logger import setup_logger

logger = setup_logger("BatteryMonitor")

class BatteryMonitor:
    """
    Monitors battery levels and triggers callbacks if it falls below critical thresholds.
    """
    def __init__(self, check_interval: float = 1.0, low_threshold: float = 20.0, critical_threshold: float = 10.0):
        self.check_interval = check_interval
        self.low_threshold = low_threshold
        self.critical_threshold = critical_threshold
        self.on_low_battery: Callable[[], Coroutine[Any, Any, None]] = None
        self.on_critical_battery: Callable[[], Coroutine[Any, Any, None]] = None
        self._running = False
        
    async def start(self, get_battery_level: Callable[[], Optional[float]]) -> None:
        self._running = True
        logger.info("Battery Monitor started.")
        
        while self._running:
            try:
                level = get_battery_level()
                if level is not None:
                    if level <= self.critical_threshold:
                        logger.warning(f"CRITICAL BATTERY: {level}%")
                        if self.on_critical_battery:
                            await self.on_critical_battery()
                    elif level <= self.low_threshold:
                        logger.warning(f"LOW BATTERY: {level}%")
                        if self.on_low_battery:
                            await self.on_low_battery()
            except asyncio.CancelledError:
                logger.info("Battery Monitor loop cancelled.")
                break
            except Exception as e:
                logger.exception(f"Error checking battery: {e}")
                
            await asyncio.sleep(self.check_interval)
            
    def stop(self) -> None:
        self._running = False
        logger.info("Battery Monitor stopped.")
