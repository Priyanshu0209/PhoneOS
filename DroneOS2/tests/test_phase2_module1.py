import pytest
from DroneOS.shared.config.models import DroneConfig, NetworkConfig, FlightConfig, SafetyConfig, LoggingConfig
from DroneOS.shared.config.loader import load_yaml_config

def test_config_loader():
    # Load Drone config
    drone_cfg = load_yaml_config("DroneOS/configs/drone.yaml", DroneConfig)
    assert drone_cfg.drone_id == "drone1"
    
    # Load Network config
    net_cfg = load_yaml_config("DroneOS/configs/network.yaml", NetworkConfig)
    assert net_cfg.port == 14550
    assert net_cfg.broadcast_address == "255.255.255.255"
    
    # Load Flight config
    flight_cfg = load_yaml_config("DroneOS/configs/flight.yaml", FlightConfig)
    assert flight_cfg.adapter_type == "px4"
    
    # Load Safety config
    safety_cfg = load_yaml_config("DroneOS/configs/safety.yaml", SafetyConfig)
    assert safety_cfg.low_battery_threshold == 20.0
    
    # Load Logging config
    log_cfg = load_yaml_config("DroneOS/configs/logging.yaml", LoggingConfig)
    assert log_cfg.level == "INFO"

def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_yaml_config("NonExistent/configs/drone.yaml", DroneConfig)
