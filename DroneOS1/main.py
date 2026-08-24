import asyncio
import sys
from pathlib import Path

from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.communication.serializers import JsonSerializer
from DroneOS.shared.communication.network_node import UdpNetworkAdapter
from DroneOS.shared.protocol.messages import (
    BaseMessage, MessageType, CommandAction
)

from DroneOS.adapters.factory import AdapterFactory
from DroneOS.core.flight_manager import FlightManager
from DroneOS.core.command_handler import CommandHandler
from DroneOS.core.safety import SafetyModule
from DroneOS.core.swarm_manager import SwarmMembership
from DroneOS.sensors.health_monitor import HealthMonitor
from DroneOS.sensors.battery_monitor import BatteryMonitor

from DroneOS.core.mission_manager import MissionManager, MissionReceiver
from DroneOS.core.collision_avoidance import StandardCollisionAvoidance
from DroneOS.core.navigation_manager import NavigationManager
from DroneOS.core.decision_engine import LocalDecisionEngine
from DroneOS.core.telemetry_publisher import TelemetryPublisher
from DroneOS.core.diagnostics import ConfigurationValidator, SystemHealthReporter

from DroneOS.shared.config.loader import load_yaml_config
from DroneOS.shared.config.models import DroneConfig, NetworkConfig, FlightConfig

logger = setup_logger("DroneOS_Main")

class DroneOSApp:
    def __init__(self):
        self._running = False
        self._active_tasks = set()
        
        # Load Configs Dynamically
        if len(sys.argv) > 1:
            config_dir = Path(sys.argv[1]).resolve()
        else:
            config_dir = Path(__file__).resolve().parent / "configs"
        self.drone_cfg = load_yaml_config(config_dir / "drone.yaml", DroneConfig)
        self.network_cfg = load_yaml_config(config_dir / "network.yaml", NetworkConfig)
        self.flight_cfg = load_yaml_config(config_dir / "flight.yaml", FlightConfig)
        
        # We need MissionConfig to provide storage dir
        try:
            from DroneOS.shared.config.models import MissionConfig
            self.mission_cfg = load_yaml_config(config_dir / "mission.yaml", MissionConfig)
            storage_dir = self.mission_cfg.mission_storage_dir
        except Exception as e:
            logger.debug(f"Failed to load mission config: {e}. Defaulting storage_dir to 'missions/'")
            storage_dir = "missions/"
            
        self.node_id = self.drone_cfg.drone_id
        
        # Configuration Validation
        from DroneOS.shared.config.models import AppConfig
        app_config = AppConfig(
            drone=self.drone_cfg,
            network=self.network_cfg,
            flight=self.flight_cfg,
            mission=getattr(self, 'mission_cfg', None)
        )
        config_errors = ConfigurationValidator.validate(app_config)
        if config_errors:
            logger.error(f"Configuration Validation Failed: {config_errors}")
            sys.exit(1)
        
        # Dependency Injection / Wiring
        from DroneOS.core.error_learning import ErrorLearningSystem
        self.error_learning = ErrorLearningSystem()
        
        self.serializer = JsonSerializer()
        self.network = UdpNetworkAdapter(
            self.node_id, 
            self.network_cfg.host, 
            self.network_cfg.port, 
            self.network_cfg.broadcast_address,
            self.serializer,
            self.network_cfg.peer_host,
            self.network_cfg.peer_port
        )
        
        self.flight_controller = AdapterFactory.create_flight_controller(
            drone_cfg=self.drone_cfg, 
            flight_cfg=self.flight_cfg
        )
        self.flight_manager = FlightManager(self.flight_controller)
        # Safety & Failsafe Module
        self.safety_module = SafetyModule(self.flight_controller, config=self.flight_cfg)
        self.health_monitor = HealthMonitor(timeout_seconds=self.network_cfg.connection_timeout)
        self.battery_monitor = BatteryMonitor()
        
        self.command_handler = CommandHandler(
            node_id=self.node_id,
            safety_module=self.safety_module,
            flight_controller=self.flight_controller,
            health_monitor=self.health_monitor,
            battery_monitor=self.battery_monitor,
            error_learning=self.error_learning
        )
        self.command_handler.network = self.network
        self.swarm_manager = SwarmMembership(self.node_id)
        # Update heartbeat timeout safely
        self.swarm_manager.heartbeat_mgr.timeout_sec = self.network_cfg.connection_timeout
        
        # New Autonomous Subsystems
        self.collision_avoidance = StandardCollisionAvoidance(
            config=self.flight_cfg.collision_avoidance
        )
        self.navigation_manager = NavigationManager(self.flight_manager)
        self.mission_manager = MissionManager(
            self.navigation_manager, 
            network_node=self.network, 
            storage_dir=storage_dir,
            config=getattr(self, 'mission_cfg', None),
            safety_module=self.safety_module,
            health_monitor=self.health_monitor,
            flight_controller=self.flight_controller
        )
        self.mission_receiver = MissionReceiver(self.mission_manager)
        self.safety_module.set_mission_manager(self.mission_manager)
        
        self.decision_engine = LocalDecisionEngine(
            self.mission_manager, 
            self.swarm_manager, 
            self.collision_avoidance,
            self.navigation_manager,
            self.safety_module
        )
        
        self.telemetry_publisher = TelemetryPublisher(
            self.node_id, 
            self.network, 
            self.flight_controller, 
            self.flight_manager, 
            self.mission_manager,
            health_monitor=self.health_monitor,
            telemetry_interval=self.network_cfg.telemetry_interval,
            heartbeat_interval=self.network_cfg.heartbeat_interval
        )
        
        self.diagnostics = SystemHealthReporter(
            self.network,
            self.flight_controller,
            self.swarm_manager,
            self.mission_manager
        )
        # Inject SwarmMembership into FlightManager for formation logic
        self.flight_manager.set_swarm_manager(self.swarm_manager)
        
        # Register commands
        self.command_handler.register_handler(CommandAction.ARM, self.flight_manager.arm)
        self.command_handler.register_handler(CommandAction.DISARM, self.flight_manager.disarm)
        self.command_handler.register_handler(CommandAction.TAKEOFF, self.flight_manager.takeoff)
        self.command_handler.register_handler(CommandAction.LAND, self.flight_manager.land)
        self.command_handler.register_handler(CommandAction.RTL, self.flight_manager.rtl)
        self.command_handler.register_handler(CommandAction.HOVER, self.flight_manager.hover)
        self.command_handler.register_handler(CommandAction.STOP, self.flight_manager.stop)
        self.command_handler.register_handler(CommandAction.MOVE, self.flight_manager.move)
        self.command_handler.register_handler(CommandAction.SET_MODE, self.flight_manager.set_mode)
        self.command_handler.register_handler(CommandAction.GOTO, self.flight_manager.goto)
        self.command_handler.register_handler(CommandAction.FORMATION_UPDATE, self.flight_manager.formation_update)
        
        # Register safety callbacks
        self.health_monitor.on_connection_lost = self.safety_module.trigger_connection_lost_failsafe
        self.battery_monitor.on_low_battery = self.safety_module.trigger_low_battery_failsafe
        self.battery_monitor.on_critical_battery = self.safety_module.trigger_critical_battery_failsafe

        # Register network callbacks
        self.network.register_callback(self._on_message_received)

    def _dispatch_task(self, coro):
        import asyncio
        try:
            task = asyncio.create_task(coro)
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
        except Exception as e:
            logger.error(f"Failed to dispatch task in main: {e}")

    async def _on_message_received(self, msg: BaseMessage) -> None:
        if msg.msg_type == MessageType.HEARTBEAT:
            # If from GroundStation, record health heartbeat
            if msg.sender_id.startswith("gs"):
                self.health_monitor.record_heartbeat()
            # If from another drone, update swarm manager
            elif msg.sender_id.startswith("drone"):
                self.swarm_manager.heartbeat_mgr.handle_heartbeat(msg)
                
        elif msg.msg_type == MessageType.TELEMETRY:
            if msg.sender_id.startswith("drone"):
                self.swarm_manager.sync.handle_telemetry(msg)
                
        elif msg.msg_type == MessageType.CONTROL:
            target = getattr(msg, 'target_id', None)
            if target and target.lower() not in [self.node_id.lower(), "all"]:
                logger.debug(f"Ignoring command meant for {target}")
                return
            await self.command_handler.handle_command(msg)
            
        elif msg.msg_type == MessageType.EMERGENCY:
            target = getattr(msg, 'target_id', None)
            if target and target.lower() not in [self.node_id.lower(), "all"]:
                logger.debug(f"Ignoring EMERGENCY meant for {target}")
                return
            await self.safety_module.trigger_emergency_stop()
            
        elif msg.msg_type.startswith("mission_"):
            target = getattr(msg, 'target_id', None)
            if target and target.lower() not in [self.node_id.lower(), "all"]:
                logger.debug(f"Ignoring {msg.msg_type} meant for {target}")
                return
                
            if msg.msg_type == MessageType.MISSION_UPLOAD:
                self.mission_receiver.handle_upload(msg)
            elif msg.msg_type == MessageType.MISSION_PAUSE:
                self.mission_receiver.handle_pause(msg)
            elif msg.msg_type == MessageType.MISSION_RESUME:
                self.mission_receiver.handle_resume(msg)
            elif msg.msg_type == MessageType.MISSION_ABORT:
                self.mission_receiver.handle_abort(msg)
            elif msg.msg_type == MessageType.MISSION_START:
                self.mission_receiver.handle_start(msg)
            elif msg.msg_type == MessageType.MISSION_STOP:
                self.mission_receiver.handle_stop(msg)
            elif msg.msg_type == MessageType.MISSION_DELETE:
                self.mission_receiver.handle_delete(msg)
            elif msg.msg_type == MessageType.MISSION_DUPLICATE:
                self.mission_receiver.handle_duplicate(msg)
            elif msg.msg_type == MessageType.MISSION_CLEAR:
                self.mission_receiver.handle_clear(msg)
        elif msg.msg_type == MessageType.TEST_INJECT:
            target = getattr(msg, 'target_id', None)
            if target and target.lower() not in [self.node_id.lower(), "all"]:
                return
            injection_type = getattr(msg, 'injection_type', '')
            active = getattr(msg, 'active', True)
            
            if injection_type == "RESTORE_ALL":
                if hasattr(self.flight_controller, '_injections'):
                    self.flight_controller._injections.clear()
                # Also restore any manually dropped peers
                self.swarm_manager.heartbeat_mgr.registry.peers = {
                   k: v for k, v in self.swarm_manager.heartbeat_mgr.registry.peers.items()
                } # In a real scenario we'd remove them from a dropped list
            elif hasattr(self.flight_controller, 'set_test_injection'):
                self.flight_controller.set_test_injection(injection_type, active)
            
            # Swarm loss injection
            if injection_type.endswith("_LOST"):
                # e.g., DR-01_LOST -> DR-01
                peer_id = injection_type.replace("_LOST", "")
                if peer_id.lower() != self.node_id.lower():
                    # manually remove them from tracking to test swarm resilience
                    self.swarm_manager.heartbeat_mgr.registry.peers.pop(peer_id, None)

        elif msg.msg_type == MessageType.PARAM_REQUEST:
            target = getattr(msg, 'target_id', None)
            if target and target.lower() not in [self.node_id.lower(), "all"]:
                return
            
            # Fire and forget task to avoid blocking main receive loop
            import asyncio
            self._dispatch_task(self._handle_param_request(msg))

    async def _handle_param_request(self, msg: BaseMessage) -> None:
        from DroneOS.shared.protocol.messages import ParamResponseMessage
        import time
        response = ParamResponseMessage(
            sender_id=self.node_id, 
            target_id=msg.sender_id,
            timestamp=time.time(),
            action=msg.action,
            success=False
        )
        try:
            if msg.action == "read_all":
                params = await self.flight_controller.get_all_params()
                response.parameters = params
                response.success = True
            elif msg.action == "read":
                val = await self.flight_controller.get_param(msg.param_name, msg.param_type)
                if val is not None:
                    response.param_name = msg.param_name
                    response.param_value = val
                    response.param_type = msg.param_type
                    response.success = True
                else:
                    response.message = f"Param {msg.param_name} not found."
            elif msg.action == "write":
                success = await self.flight_controller.set_param(msg.param_name, msg.param_value, msg.param_type)
                if success:
                    # Readback to confirm
                    val = await self.flight_controller.get_param(msg.param_name, msg.param_type)
                    if val is not None:
                        # Check match
                        is_match = False
                        if msg.param_type == "int":
                            is_match = int(val) == int(msg.param_value)
                        else:
                            is_match = abs(float(val) - float(msg.param_value)) < 0.0001
                        
                        if is_match:
                            response.param_name = msg.param_name
                            response.param_value = val
                            response.param_type = msg.param_type
                            response.success = True
                        else:
                            response.success = False
                            response.message = f"PX4 rejected parameter change. Expected {msg.param_value}, got {val}"
                    else:
                        response.success = False
                        response.message = f"Failed to readback param {msg.param_name} after writing."
                else:
                    response.success = False
                    response.message = f"PX4 rejected write for param {msg.param_name}."
        except Exception as e:
            logger.error(f"Param request failed: {e}")
            response.message = str(e)
            
        await self.network.broadcast_message(response)

    async def _autonomous_evaluation_loop(self) -> None:
        while self._running:
            try:
                telemetry = await self.flight_controller.get_telemetry()
                await self.decision_engine.evaluate_tick(telemetry)
                
                # Periodically log and publish diagnostic metrics at DEBUG level
                report = self.diagnostics.get_full_report()
                logger.debug(f"Diagnostics: {report}")
                
                from DroneOS.shared.protocol.messages import DiagnosticsMessage
                import time
                diag_msg = DiagnosticsMessage(
                    sender_id=self.node_id,
                    timestamp=time.time(),
                    diagnostics=report
                )
                self._dispatch_task(self.network.broadcast_message(diag_msg))
                
            except asyncio.CancelledError:
                logger.info("Autonomous evaluation loop cancelled.")
                break
            except Exception as e:
                logger.exception(f"Decision Engine error: {e}")
                
            # Watchdog for Pixhawk reconnection
            if getattr(self.flight_controller, '_connected', False) is False:
                try:
                    logger.info("Attempting to reconnect to flight controller...")
                    await self.flight_controller.connect()
                except Exception as e:
                    logger.debug(f"Reconnect attempt failed: {e}")
                    
            await asyncio.sleep(0.5)

    async def run(self) -> None:
        logger.info(f"Starting DroneOS Node: {self.node_id}")
        self._running = True
        
        try:
            connected = await self.flight_controller.connect()
            if not connected:
                logger.error("Could not connect to flight controller initially. Will continue starting DroneOS and retry later.")
        except Exception as e:
            logger.error(f"Flight controller connection error during startup: {e}. DroneOS will continue.")

        await self.network.start()
        
        # Start sensors
        self._dispatch_task(self.health_monitor.start())
        self._dispatch_task(self.battery_monitor.start(
            get_battery_level=lambda: self.flight_controller._telemetry.battery_level if self.flight_controller else None
        ))
        self._dispatch_task(self._autonomous_evaluation_loop())
        
        # Start publisher loops
        self.telemetry_publisher.start()
        
        logger.info("DroneOS is running. Press Ctrl+C to stop.")
        
        try:
            while self._running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        logger.info("Shutting down DroneOS...")
        self._running = False
        
        for task in self._active_tasks:
            task.cancel()
        self._active_tasks.clear()
        
        self.telemetry_publisher.stop()
        self.health_monitor.stop()
        self.battery_monitor.stop()
        await self.network.stop()
        await self.flight_controller.disconnect()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    app = DroneOSApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down DroneOS...")
    except asyncio.CancelledError:
        pass
    finally:
        # Note: In a full implementation, we would await app.stop() gracefully
        # but since asyncio.run is closing, we just log here. 
        # App internal loop catches the cancel.
        logger.info("DroneOS shutdown complete.")
