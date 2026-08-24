import math
import time
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.protocol.messages import TelemetryData
from DroneOS.shared.config.models import CollisionAvoidanceConfig

logger = setup_logger("CollisionAvoidance")

class ICollisionAvoidance(ABC):
    @abstractmethod
    def evaluate_threats(self, self_telemetry: TelemetryData, swarm_telemetry: Dict[str, TelemetryData]) -> Tuple[str, Optional[Dict[str, float]], Optional[str], float]:
        """
        Evaluates potential collisions based on self telemetry and the swarm telemetry map.
        Returns (safety_state, corrective_velocity_vector, peer_id, distance)
        safety_state: NORMAL, WARNING, AVOIDANCE, EMERGENCY
        """
        pass

class StandardCollisionAvoidance(ICollisionAvoidance):
    """
    Decentralized collision avoidance logic using Predictive Separation.
    """
    def __init__(self, config: Optional[CollisionAvoidanceConfig] = None):
        self.config = config or CollisionAvoidanceConfig()
        self.enabled = self.config.enabled
        self.min_h_dist = self.config.min_horizontal_distance
        self.min_v_dist = self.config.min_vertical_distance
        self.warn_dist = self.config.warning_distance
        self.emg_dist = self.config.emergency_distance
        self.timeout = self.config.neighbor_timeout_sec

    def evaluate_threats(self, self_telemetry: TelemetryData, swarm_telemetry: Dict[str, TelemetryData]) -> Tuple[str, Optional[Dict[str, float]], Optional[str], float]:
        if not self.enabled:
            return "NORMAL", None, None, 0.0
            
        if self_telemetry.latitude is None or self_telemetry.longitude is None:
            return "NORMAL", None, None, 0.0

        my_lat = self_telemetry.latitude
        my_lon = self_telemetry.longitude
        my_alt = self_telemetry.altitude or 0.0

        worst_state = "NORMAL"
        best_correction = None
        threat_peer = None
        min_dist_found = float('inf')

        for peer_id, peer_t in swarm_telemetry.items():
            if peer_t.latitude is None or peer_t.longitude is None:
                continue
                
            # Check staleness
            if peer_t.timestamp is not None:
                age = time.time() - peer_t.timestamp
                if age > self.timeout:
                    # Ignore stale neighbor state
                    continue
                
            # Distance in meters
            R = 6371000
            phi1 = math.radians(my_lat)
            phi2 = math.radians(peer_t.latitude)
            delta_phi = math.radians(peer_t.latitude - my_lat)
            delta_lambda = math.radians(peer_t.longitude - my_lon)

            a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist = R * c
            
            alt_diff = abs(my_alt - (peer_t.altitude or 0.0))
            
            # Simple check if vertically separated
            if alt_diff > self.min_v_dist:
                continue
                
            if dist < self.emg_dist:
                state = "EMERGENCY"
            elif dist < self.min_h_dist:
                state = "AVOIDANCE"
            elif dist < self.warn_dist:
                state = "WARNING"
            else:
                state = "NORMAL"
                
            if state != "NORMAL":
                if dist < min_dist_found:
                    min_dist_found = dist
                    worst_state = state
                    threat_peer = peer_id
                    
                    if state == "AVOIDANCE":
                        # Simple repel vector (move away from peer)
                        bearing = math.atan2(
                            math.sin(delta_lambda) * math.cos(phi2),
                            math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
                        )
                        # Opposite direction
                        escape_bearing = bearing + math.pi
                        
                        vx = 2.0 * math.cos(escape_bearing)
                        vy = 2.0 * math.sin(escape_bearing)
                        vz = 0.0 
                        best_correction = {"vx": vx, "vy": vy, "vz": vz, "duration": 1.0}

        return worst_state, best_correction, threat_peer, min_dist_found
