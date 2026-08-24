import os
import psutil
import asyncio
from typing import Dict, Any, List
from DroneOS.shared.config.models import AppConfig
from DroneOS.shared.utils.logger import setup_logger

logger = setup_logger("Diagnostics")

class ConfigurationValidator:
    """Validates YAML configuration syntactically and semantically before startup."""
    @staticmethod
    def validate(config: AppConfig) -> List[str]:
        errors = []
        if not config.drone or not config.drone.drone_id:
            errors.append("Missing Drone ID")
        if not config.network or not config.network.host:
            errors.append("Missing Network Host")
        if config.flight:
            if config.flight.adapter_type not in ["airsim", "px4", "mavsdk"]:
                errors.append(f"Invalid adapter type: {config.flight.adapter_type}")
        if config.mission:
            if not os.path.exists(config.mission.mission_storage_dir):
                try:
                    os.makedirs(config.mission.mission_storage_dir, exist_ok=True)
                except OSError:
                    errors.append(f"Cannot create mission dir: {config.mission.mission_storage_dir}")
        return errors

class RuntimeDiagnostics:
    """Provides lightweight, non-blocking CPU/Memory/Task metrics."""
    @staticmethod
    def get_system_metrics() -> Dict[str, Any]:
        process = psutil.Process(os.getpid())
        
        # Try to read Pi Temperature
        temp_c = None
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_c = float(f.read().strip()) / 1000.0
        except Exception as e:
            logger.debug(f"Failed to read Pi temperature (likely not on Pi hardware): {e}")
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_mb": process.memory_info().rss / (1024 * 1024),
            "async_tasks": len(asyncio.all_tasks()),
            "threads": process.num_threads(),
            "temperature_c": temp_c
        }

class SystemHealthReporter:
    """Aggregates sub-reporters into a unified diagnostic status."""
    def __init__(self, network, flight_controller, swarm_manager, mission_manager):
        self.network = network
        self.fc = flight_controller
        self.swarm = swarm_manager
        self.mission = mission_manager

    def get_full_report(self) -> Dict[str, Any]:
        return {
            "system": RuntimeDiagnostics.get_system_metrics(),
            "network": {
                "active_tasks": len(self.network._active_tasks) if hasattr(self.network, "_active_tasks") else 0,
                "known_peers": len(self.network.known_endpoints) if hasattr(self.network, "known_endpoints") else 0
            },
            "adapter": {
                "connected": getattr(self.fc, "_connected", False),
                "reconnecting": getattr(self.fc, "_reconnecting", False)
            },
            "swarm": {
                "active_peers": len(self.swarm.registry.get_all_peers()) if hasattr(self.swarm, "registry") else 0
            },
            "mission": {
                "status": self.mission.status.state if hasattr(self.mission, "status") else "UNKNOWN"
            }
        }
