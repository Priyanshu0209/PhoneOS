from typing import Dict, Any, Callable, Coroutine
from pydantic import ValidationError
from DroneOS.shared.protocol.messages import ControlMessage, CommandAction, CommandLifecycleMessage
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.utils.event_logger import event_logger

logger = setup_logger("CommandHandler")

class CommandHandler:
    """
    Parses incoming ControlMessages and routes them to the appropriate subsystem (e.g. FlightManager).
    """
    def __init__(self, node_id: str = "DroneOS", safety_module=None, flight_controller=None, health_monitor=None, battery_monitor=None, error_learning=None):
        # Maps CommandAction to a coroutine handler
        self._handlers: Dict[CommandAction, Callable[[Dict[str, Any]], Coroutine[Any, Any, bool]]] = {}
        self.network = None
        self.node_id = node_id
        self._active_tasks = set()
        
        self.safety_module = safety_module
        self.flight_controller = flight_controller
        self.health_monitor = health_monitor
        self.battery_monitor = battery_monitor
        self.error_learning = error_learning
        self._processed_cmds = []

    def _send_lifecycle(self, sender_id: str, action: CommandAction, stage: str, reason: str = None, cmd_id: str = None) -> None:
        if self.network:
            import asyncio
            import time
            msg = CommandLifecycleMessage(
                sender_id=self.node_id,
                target_id=sender_id,
                timestamp=time.time(),
                action=action,
                stage=stage,
                reason=reason,
                cmd_id=cmd_id
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.network.broadcast_message(msg))
            except RuntimeError:
                pass

            # Structured Logging
            severity = "ERROR" if stage in ["REJECTED", "FAILED", "TIMEOUT"] else "INFO"
            event_type = f"COMMAND_{stage}"
            event_logger.log_event(
                source="DRONEOS",
                severity=severity,
                drone_id=self.node_id,
                event_type=event_type,
                message=f"{action.name} {stage}{f': {reason}' if reason else ''}"
            )

    async def _validate_safety_gate(self, action: CommandAction) -> str:
        if not self.flight_controller or not self.safety_module or not self.health_monitor:
            return "" # Tests or incomplete DI

        telemetry = await self.flight_controller.get_telemetry()
        
        import time
        # Telemetry Freshness
        is_telemetry_stale = False
        if getattr(telemetry, 'timestamp', None) is not None:
            if (time.time() - telemetry.timestamp) > 2.0:
                is_telemetry_stale = True
        else:
            is_telemetry_stale = True

        # Heartbeat Freshness
        is_heartbeat_stale = False
        if self.health_monitor.last_heartbeat_time is not None:
            if (time.time() - self.health_monitor.last_heartbeat_time) > self.health_monitor.timeout_seconds:
                is_heartbeat_stale = True

        is_emergency = self.safety_module.is_failsafe_active
        is_battery_critical = False # Assumed from the failsafe state or we can read telemetry voltage. Actually failsafe covers it.

        if action == CommandAction.ARM:
            if is_heartbeat_stale: return "Command rejected: Heartbeat stale"
            if is_telemetry_stale: return "Command rejected: Telemetry stale"
            if is_emergency: return "Command rejected: Emergency stop active"
            
        elif action == CommandAction.TAKEOFF:
            if is_heartbeat_stale: return "Command rejected: Heartbeat stale"
            if is_telemetry_stale: return "Command rejected: Telemetry stale"
            if is_emergency: return "Command rejected: Emergency stop active"
            
        elif action == CommandAction.STOP:
            self.safety_module.reset_failsafe()
            return "" # Approved

        elif action == CommandAction.MOVE:
            if is_heartbeat_stale: return "Command rejected: Heartbeat stale"
            if is_emergency: return "Command rejected: Emergency stop active"

        elif action == CommandAction.RTL:
            if is_heartbeat_stale: return "Command rejected: Heartbeat stale"
            if is_emergency: return "Command rejected: Emergency stop active"
            if not getattr(telemetry, 'home_valid', False): return "Command rejected: Home position unavailable (RTL requires home)"
            if getattr(telemetry, 'flight_mode', '').upper() == 'MANUAL' and not getattr(telemetry, 'gps_valid', False):
                return "Command rejected: GPS unavailable (RTL requires global position)"

        elif action == CommandAction.GOTO:
            if is_heartbeat_stale: return "Command rejected: Heartbeat stale"
            if is_emergency: return "Command rejected: Emergency stop active"
            if not getattr(telemetry, 'gps_valid', False): return "Command rejected: GPS unavailable (GOTO requires global position)"
            
        return ""

    def _dispatch_task(self, coro):
        import asyncio
        try:
            task = asyncio.create_task(coro)
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
        except Exception as e:
            logger.error(f"Failed to dispatch task: {e}")
    def register_handler(self, action: CommandAction, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, bool]]) -> None:
        self._handlers[action] = handler

    async def handle_command(self, message: ControlMessage) -> bool:
        if message.cmd_id:
            if message.cmd_id in self._processed_cmds:
                logger.debug(f"Ignoring duplicate command {message.cmd_id}")
                return True
            self._processed_cmds.append(message.cmd_id)
            if len(self._processed_cmds) > 100:
                self._processed_cmds.pop(0)

        if message.action in self._handlers:
            logger.info(f"COMMAND_RX sender={message.sender_id} target={message.target_id} action={message.action.value}")
            self._send_lifecycle(message.sender_id, message.action, "BACKEND_RECEIVED", cmd_id=message.cmd_id)
            
            critical_actions = [CommandAction.ARM, CommandAction.TAKEOFF, CommandAction.LAND, CommandAction.RTL]
            is_critical = message.action in critical_actions
            
            if is_critical:
                if getattr(self, '_active_critical_command', None) is not None:
                    rejection = f"Command rejected: Another critical command ({self._active_critical_command.value}) is already active."
                    logger.warning(rejection)
                    self._send_lifecycle(message.sender_id, message.action, "REJECTED", reason=rejection, cmd_id=message.cmd_id)
                    return False
                self._active_critical_command = message.action

            rejection_reason = await self._validate_safety_gate(message.action)
            if rejection_reason:
                logger.warning(rejection_reason)
                self._send_lifecycle(message.sender_id, message.action, "REJECTED", reason=rejection_reason, cmd_id=message.cmd_id)
                if is_critical:
                    self._active_critical_command = None
                return False

            params = message.params or {}
            try:
                self._send_lifecycle(message.sender_id, message.action, "SENDING", cmd_id=message.cmd_id)
                
                # Use asyncio.wait_for to handle TIMEOUT
                import asyncio
                try:
                    success = await asyncio.wait_for(self._handlers[message.action](params), timeout=15.0)
                except asyncio.TimeoutError:
                    error_text = f"{message.action.name} timed out."
                    self._send_lifecycle(message.sender_id, message.action, "TIMEOUT", reason=error_text, cmd_id=message.cmd_id)
                    if is_critical:
                        self._active_critical_command = None
                    return False

                if not success:
                    logger.warning(f"Command {message.action.value} failed to execute properly.")
                    error_text = f"{message.action.name} rejected by FlightManager."
                    if message.action == CommandAction.ARM:
                        error_text = "ARM rejected by Pixhawk; check Pixhawk pre-arm checks."
                    self._send_lifecycle(message.sender_id, message.action, "REJECTED", reason=error_text, cmd_id=message.cmd_id)
                    if is_critical:
                        self._active_critical_command = None
                    return False
                
                self._send_lifecycle(message.sender_id, message.action, "ACCEPTED", cmd_id=message.cmd_id)
                if is_critical:
                    self._active_critical_command = None
                return True
            except Exception as e:
                error_msg = str(e)
                if "ActionError" in str(type(e)):
                    error_msg = str(e).split(':', 1)[-1].strip()
                logger.exception(f"Exception while executing {message.action.value}: {error_msg}")
                self._send_lifecycle(message.sender_id, message.action, "REJECTED", reason=error_msg, cmd_id=message.cmd_id)
                if hasattr(self, 'error_learning') and self.error_learning:
                    self.error_learning.report_error(self.node_id, "COMMAND_HANDLER", error_msg)
                if is_critical:
                    self._active_critical_command = None
                return False
        else:
            logger.warning(f"No handler registered for command: {message.action.value}")
            return False
