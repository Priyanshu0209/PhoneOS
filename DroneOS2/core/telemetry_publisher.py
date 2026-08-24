import time
import asyncio
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.protocol.messages import HeartbeatMessage, TelemetryMessage

logger = setup_logger("TelemetryPublisher")

class TelemetryPublisher:
    """
    Decouples the periodic broadcasting of telemetry and heartbeat 
    from the main application loop, enhancing modularity.
    """
    def __init__(self, node_id, network_adapter, flight_controller, flight_manager, mission_manager,
                 health_monitor=None, telemetry_interval: float = 0.5, heartbeat_interval: float = 1.0):
        self.node_id = node_id
        self.network = network_adapter
        self.fc = flight_controller
        self.fm = flight_manager
        self.mission = mission_manager
        self.health_monitor = health_monitor
        self.telemetry_interval = telemetry_interval
        self.heartbeat_interval = heartbeat_interval
        self._running = False
        self._active_tasks = set()

    async def _publish_telemetry_loop(self) -> None:
        while self._running:
            try:
                telemetry = await self.fc.get_telemetry()
                telemetry.mission_state = self.mission.get_current_state()
                
                if self.health_monitor and self.health_monitor.last_heartbeat_time is not None:
                    telemetry.heartbeat_age = time.time() - self.health_monitor.last_heartbeat_time
                else:
                    telemetry.heartbeat_age = None
                
                msg = TelemetryMessage(
                    sender_id=self.node_id,
                    timestamp=time.time(),
                    telemetry=telemetry
                )
                await self.network.broadcast_message(msg)
            except asyncio.CancelledError:
                logger.info("Telemetry loop cancelled.")
                break
            except (OSError, RuntimeError, ValueError) as e:
                logger.exception(f"Error publishing telemetry: {e}")
            await asyncio.sleep(self.telemetry_interval)

    async def _publish_heartbeat_loop(self) -> None:
        while self._running:
            try:
                telemetry = await self.fc.get_telemetry()
                is_armed = getattr(telemetry, 'armed_state', None) == "ARMED"
                msg = HeartbeatMessage(
                    sender_id=self.node_id,
                    timestamp=time.time(),
                    status="active" if is_armed else "standby"
                )
                await self.network.broadcast_message(msg)
            except asyncio.CancelledError:
                logger.info("Heartbeat loop cancelled.")
                break
            except (OSError, RuntimeError, ValueError) as e:
                logger.exception(f"Error publishing heartbeat: {e}")
            await asyncio.sleep(self.heartbeat_interval)

    def start(self):
        self._running = True
        for t in [
            asyncio.create_task(self._publish_telemetry_loop()),
            asyncio.create_task(self._publish_heartbeat_loop())
        ]:
            self._active_tasks.add(t)
            t.add_done_callback(self._active_tasks.discard)
        logger.info("TelemetryPublisher loops started.")
        
    def stop(self):
        self._running = False
        for task in self._active_tasks:
            task.cancel()
