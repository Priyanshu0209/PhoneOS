from DroneOS.core.interfaces import IFlightController
from DroneOS.shared.config.models import FlightConfig, DroneConfig
from DroneOS.shared.utils.logger import setup_logger

logger = setup_logger("AdapterFactory")

class AdapterFactory:
    """
    Dynamically loads the requested Flight Controller adapter based on the YAML configuration.
    This guarantees that adding a MAVSDK or PX4 adapter in the future requires ZERO changes 
    to the DroneOS application logic or bootstrap wiring.
    """
    @staticmethod
    def create_flight_controller(drone_cfg: DroneConfig, flight_cfg: FlightConfig) -> IFlightController:
        backend_type = flight_cfg.adapter_type.lower()
        
        if backend_type in ["mavsdk", "px4"]:
            from DroneOS.adapters.px4_adapter import PX4FlightController
            logger.info("Initializing PX4/MAVSDK Flight Controller Adapter.")
            return PX4FlightController(vehicle_name=drone_cfg.vehicle_name, config=flight_cfg)
            
        else:
            raise ValueError(f"Unknown adapter_type in configuration: {backend_type}")
