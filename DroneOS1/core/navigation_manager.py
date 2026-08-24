import math
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.core.flight_manager import FlightManager
from DroneOS.shared.protocol.messages import TelemetryData

logger = setup_logger("NavigationManager")

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Earth radius in meters
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360) % 360

class NavigationManager:
    """
    Converts high-level mission waypoints into concrete velocity and yaw vectors for the FlightManager.
    Calculates bearing, distance, and implements a proportional controller for velocity.
    """
    def __init__(self, flight_manager: FlightManager):
        self.flight_manager = flight_manager
        self.waypoint_tolerance: float = 2.0  # meters

    async def navigate_to_waypoint(self, current_telemetry: TelemetryData, target_lat: float, target_lon: float, target_alt: float, target_speed: float) -> bool:
        if current_telemetry.latitude is None or current_telemetry.longitude is None:
            logger.warning("Cannot navigate without GPS lock.")
            return False

        dist = haversine_distance(current_telemetry.latitude, current_telemetry.longitude, target_lat, target_lon)
        
        # Check if waypoint reached
        alt_diff = abs((current_telemetry.altitude or 0.0) - target_alt)
        if dist < self.waypoint_tolerance and alt_diff < self.waypoint_tolerance:
            logger.info("Waypoint reached.")
            return True

        # Calculate Velocity Vector
        bearing = calculate_bearing(current_telemetry.latitude, current_telemetry.longitude, target_lat, target_lon)
        bearing_rad = math.radians(bearing)
        
        # Simple proportional velocity cap
        speed = min(target_speed, dist * 0.5)
        if speed < 0.5:
            speed = 0.5
            
        vx = speed * math.cos(bearing_rad)
        vy = speed * math.sin(bearing_rad)
        
        # Vertical velocity
        vz = 0.0
        if current_telemetry.altitude is not None:
            vz_error = target_alt - current_telemetry.altitude
            vz = max(-2.0, min(2.0, vz_error * 0.5))
            # Note: NED coordinate system has positive Z pointing DOWN
            # If target_alt > current_alt, we need to go UP, which is negative Z velocity
            vz = -vz 
            
        # Optional: Calculate Yaw rate to face the bearing
        # For a holonomic drone, we can just move without yawing, but for realism we can point the nose
        # AirSim uses yaw rate. Let's just issue a simple holonomic move for now.
        yaw_rate = 0.0 

        await self.flight_manager.move({
            "vx": vx,
            "vy": vy,
            "vz": vz,
            "duration": 0.5,
            "yaw_rate": yaw_rate
        })
        
        return False # False means waypoint not reached yet
