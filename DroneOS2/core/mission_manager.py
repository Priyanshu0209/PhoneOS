import time
import json
import os
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ValidationError
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.protocol.messages import (
    MissionUploadMessage, MissionProgressMessage, MissionStatusMessage,
    MissionAbortMessage, MissionPauseMessage, MissionResumeMessage
)
from DroneOS.core.navigation_manager import NavigationManager

logger = setup_logger("MissionSystem")

class MissionState(str, Enum):
    IDLE = "IDLE"
    LOADED = "LOADED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"

class Waypoint(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    speed: float = 5.0
    delay: float = 0.0

class MissionStatus:
    def __init__(self):
        self.state: MissionState = MissionState.IDLE
        self.active_mission_id: Optional[str] = None
        self.errors: List[str] = []

    def update_state(self, new_state: MissionState):
        self.state = new_state

class MissionStorage:
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def save_mission(self, mission_id: str, mission_data: str) -> bool:
        path = os.path.join(self.storage_dir, f"{mission_id}.json")
        try:
            with open(path, "w") as f:
                f.write(mission_data)
            return True
        except IOError as e:
            logger.error(f"Failed to save mission {mission_id}: {e}")
            return False

    def load_mission(self, mission_id: str) -> Optional[str]:
        path = os.path.join(self.storage_dir, f"{mission_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                return f.read()
        except IOError as e:
            logger.error(f"Failed to load mission {mission_id}: {e}")
            return None

class MissionValidator:
    @staticmethod
    def validate_mission_json(mission_json: str) -> Optional[List[Waypoint]]:
        try:
            data = json.loads(mission_json)
            if "waypoints" not in data:
                return None
            waypoints = [Waypoint(**wp) for wp in data["waypoints"]]
            return waypoints
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
            logger.error(f"Mission validation failed: {e}")
            return None

class MissionProgressTracker:
    def __init__(self):
        self.current_index: int = 0
        self.total_waypoints: int = 0

    def reset(self, total: int):
        self.current_index = 0
        self.total_waypoints = total

    def advance(self) -> bool:
        self.current_index += 1
        return self.current_index >= self.total_waypoints

    def get_progress_percent(self) -> float:
        if self.total_waypoints == 0:
            return 0.0
        return (self.current_index / self.total_waypoints) * 100.0

class MissionExecutor:
    def __init__(self, navigation_manager: NavigationManager):
        self.nav = navigation_manager
        self.waypoints: List[Waypoint] = []
        
    def set_waypoints(self, waypoints: List[Waypoint]):
        self.waypoints = waypoints

    async def execute_waypoint(self, current_telemetry, index: int) -> bool:
        if index >= len(self.waypoints):
            return True
        wp = self.waypoints[index]
        reached = await self.nav.navigate_to_waypoint(
            current_telemetry, 
            wp.latitude, 
            wp.longitude, 
            wp.altitude, 
            wp.speed
        )
        return reached

class MissionScheduler:
    def __init__(self):
        self.scheduled_time: Optional[float] = None
        self.is_scheduled: bool = False

    def schedule(self, start_time: float):
        self.scheduled_time = start_time
        self.is_scheduled = True

    def check_schedule(self, current_time: float) -> bool:
        if self.is_scheduled and self.scheduled_time and current_time >= self.scheduled_time:
            self.is_scheduled = False
            return True
        return False

class MissionManager:
    def __init__(self, navigation_manager: NavigationManager, network_node=None, storage_dir: str = "missions/", config=None, safety_module=None, health_monitor=None, flight_controller=None):
        self.status = MissionStatus()
        self.storage = MissionStorage(storage_dir)
        self.tracker = MissionProgressTracker()
        self.executor = MissionExecutor(navigation_manager)
        self.scheduler = MissionScheduler()
        self.network = network_node
        self.config = config
        self.safety_module = safety_module
        self.health_monitor = health_monitor
        self.flight_controller = flight_controller

    async def _validate_mission_safety(self) -> str:
        if not self.flight_controller or not self.safety_module or not self.health_monitor:
            return ""

        telemetry = await self.flight_controller.get_telemetry()
        
        import time
        if getattr(telemetry, 'timestamp', None) is not None:
            if (time.time() - telemetry.timestamp) > 2.0:
                return "Mission rejected: Telemetry stale"
        else:
            return "Mission rejected: Telemetry stale"

        if self.health_monitor.last_heartbeat_time is not None:
            if (time.time() - self.health_monitor.last_heartbeat_time) > self.health_monitor.timeout_seconds:
                return "Mission rejected: Heartbeat lost"
        else:
            return "Mission rejected: Heartbeat lost"

        if self.safety_module.is_failsafe_active:
            return "Mission rejected: Emergency stop active"

        if not getattr(telemetry, 'gps_valid', False):
            return "Mission rejected: GPS unavailable or stale"

        return ""

    def load_mission(self, mission_id: str, waypoints_data: List[dict]) -> None:
        wps = [Waypoint(**wp) for wp in waypoints_data]
        self._initialize_mission(mission_id, wps)

    def _initialize_mission(self, mission_id: str, waypoints: List[Waypoint]):
        self.executor.set_waypoints(waypoints)
        self.tracker.reset(len(waypoints))
        self.status.active_mission_id = mission_id
        self.status.update_state(MissionState.LOADED)
        self._emit_status()
        logger.info(f"Mission {mission_id} loaded with {len(waypoints)} waypoints.")

    def _dispatch_task(self, coro):
        if not hasattr(self, '_active_tasks'): self._active_tasks = set()
        import asyncio
        try:
            task = asyncio.create_task(coro)
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
        except RuntimeError:
            pass

    def _emit_status(self):
        if self.network:
            sender = getattr(self.network, 'node_id', "DroneOS")
            msg = MissionStatusMessage(
                sender_id=sender,
                timestamp=time.time(),
                mission_id=self.status.active_mission_id or "",
                status=self.status.state.value
            )
            self._dispatch_task(self.network.broadcast_message(msg))

    def _emit_progress(self):
        if self.network:
            sender = getattr(self.network, 'node_id', "DroneOS")
            
            # Safely calculate percentage
            pct = 0.0
            if self.tracker.total_waypoints > 0:
                pct = (float(self.tracker.current_index) / float(self.tracker.total_waypoints)) * 100.0
                
            msg = MissionProgressMessage(
                sender_id=sender,
                timestamp=time.time(),
                mission_id=self.status.active_mission_id or "",
                current_waypoint=self.tracker.current_index,
                total_waypoints=self.tracker.total_waypoints,
                percent_complete=pct
            )
            self._dispatch_task(self.network.broadcast_message(msg))

    def start_mission(self) -> None:
        if self.status.state in [MissionState.LOADED, MissionState.PAUSED]:
            if self.tracker.total_waypoints == 0:
                logger.warning("Cannot start mission: No waypoints loaded.")
                return
            self.status.update_state(MissionState.RUNNING)
            self._emit_status()
            logger.info("Autonomous mission started.")
        else:
            logger.warning(f"Cannot start mission from state {self.status.state}")

    def pause_mission(self) -> None:
        if self.status.state == MissionState.RUNNING:
            self.status.update_state(MissionState.PAUSED)
            self._emit_status()
            logger.info("Autonomous mission paused.")

    def abort_mission(self) -> None:
        if self.status.state in [MissionState.RUNNING, MissionState.PAUSED]:
            self.status.update_state(MissionState.ABORTED)
            self._emit_status()
            logger.warning("Autonomous mission aborted.")

    def get_current_waypoint(self) -> Optional[Waypoint]:
        if self.status.state != MissionState.RUNNING:
            return None
        if self.tracker.current_index < len(self.executor.waypoints):
            return self.executor.waypoints[self.tracker.current_index]
        return None

    def advance_waypoint(self) -> None:
        if self.status.state == MissionState.RUNNING:
            completed = self.tracker.advance()
            self._emit_progress()
            if completed:
                self.status.update_state(MissionState.COMPLETED)
                self._emit_status()
                logger.info("Autonomous mission completed.")
            else:
                logger.info(f"Advancing to waypoint {self.tracker.current_index + 1}/{self.tracker.total_waypoints}")

    def get_current_state(self) -> str:
        return self.status.state.value

class MissionReceiver:
    """
    Decoupled network receiver component for Mission logic.
    """
    def __init__(self, manager: MissionManager):
        self.manager = manager

    def handle_upload(self, msg: MissionUploadMessage):
        waypoints = MissionValidator.validate_mission_json(msg.mission_json)
        if waypoints is not None:
            if self.manager.config:
                max_alt = self.manager.config.max_altitude
                min_alt = self.manager.config.min_altitude
                for wp in waypoints:
                    if wp.altitude > max_alt or wp.altitude < min_alt:
                        logger.error(f"Mission rejected: altitude {wp.altitude} out of bounds ({min_alt} - {max_alt})")
                        if self.manager.network:
                            from DroneOS.shared.protocol.messages import ErrorMessage
                            feedback = ErrorMessage(
                                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                                timestamp=time.time(), target_id=msg.sender_id,
                                error_code=400, error_msg=f"Mission Validation Failed: Altitude {wp.altitude} out of bounds"
                            )
                            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
                        return

            self.manager.storage.save_mission(msg.mission_id, msg.mission_json)
            self.manager._initialize_mission(msg.mission_id, waypoints)
            logger.info(f"Successfully validated and stored uploaded mission {msg.mission_id}")
            if self.manager.network:
                from DroneOS.shared.protocol.messages import StatusMessage
                feedback = StatusMessage(
                    sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                    timestamp=time.time(), target_id=msg.sender_id,
                    status_text=f"Mission {msg.mission_id} uploaded successfully.", severity="info"
                )
                self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
        else:
            logger.error(f"Failed to validate uploaded mission {msg.mission_id}")
            if self.manager.network:
                from DroneOS.shared.protocol.messages import ErrorMessage
                feedback = ErrorMessage(
                    sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                    timestamp=time.time(), target_id=msg.sender_id,
                    error_code=400, error_msg=f"Mission Validation Failed for {msg.mission_id}"
                )
                self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
            
    def handle_pause(self, msg: MissionPauseMessage):
        self.manager.pause_mission()
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission PAUSED.", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
        
    async def handle_resume_async(self, msg: MissionResumeMessage):
        rejection_reason = await self.manager._validate_mission_safety()
        if rejection_reason:
            logger.warning(rejection_reason)
            if self.manager.network:
                from DroneOS.shared.protocol.messages import ErrorMessage
                feedback = ErrorMessage(
                    sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                    timestamp=time.time(), target_id=msg.sender_id,
                    error_code=403, error_msg=rejection_reason
                )
                self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
            return
            
        self.manager.start_mission()
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission RESUMED.", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))

    def handle_resume(self, msg: MissionResumeMessage):
        self.manager._dispatch_task(self.handle_resume_async(msg))
        
    def handle_abort(self, msg: MissionAbortMessage):
        self.manager.abort_mission()
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission ABORTED.", severity="warning"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))

    async def handle_start_async(self, msg):
        rejection_reason = await self.manager._validate_mission_safety()
        if rejection_reason:
            logger.warning(rejection_reason)
            if self.manager.network:
                from DroneOS.shared.protocol.messages import ErrorMessage
                feedback = ErrorMessage(
                    sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                    timestamp=time.time(), target_id=msg.sender_id,
                    error_code=403, error_msg=rejection_reason
                )
                self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
            return
            
        self.manager.start_mission()
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission STARTED.", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))

    def handle_start(self, msg):
        self.manager._dispatch_task(self.handle_start_async(msg))

    def handle_stop(self, msg):
        self.manager.abort_mission()
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission STOPPED.", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))

    def handle_delete(self, msg):
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission DELETED locally.", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))

    def handle_duplicate(self, msg):
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Ignored duplicate command (handled by GroundStation).", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))

    def handle_clear(self, msg):
        self.manager.status.update_state(MissionState.IDLE)
        self.manager._emit_status()
        if self.manager.network:
            from DroneOS.shared.protocol.messages import StatusMessage
            feedback = StatusMessage(
                sender_id=getattr(self.manager.network, 'node_id', "DroneOS"),
                timestamp=time.time(), target_id=msg.sender_id,
                status_text="Mission CLEARED.", severity="info"
            )
            self.manager._dispatch_task(self.manager.network.broadcast_message(feedback))
