import asyncio
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.core.collision_avoidance import ICollisionAvoidance
from DroneOS.core.mission_manager import MissionManager
from DroneOS.core.swarm_manager import SwarmMembership
from DroneOS.core.navigation_manager import NavigationManager
from DroneOS.shared.protocol.messages import TelemetryData

logger = setup_logger("DecisionEngine")

class LocalDecisionEngine:
    """
    Acts as the decentralized 'brain' of the drone.
    Evaluates input from the SwarmManager, SafetyModule, and MissionManager 
    to dynamically alter flight parameters without GroundStation.
    """
    def __init__(
        self, 
        mission_manager: MissionManager, 
        swarm_manager: SwarmMembership,
        collision_avoidance: ICollisionAvoidance,
        navigation_manager: NavigationManager,
        safety_module
    ):
        """
        Initializes the DecisionEngine, binding the high-level managers 
        to evaluate situational context continuously.
        """
        self.mission = mission_manager
        self.swarm = swarm_manager
        self.ca = collision_avoidance
        self.nav = navigation_manager
        self.safety = safety_module
        self.is_active = True
        self.active_bids = {}

    def calculate_bid(self, my_telemetry: TelemetryData, target_lat: float, target_lon: float) -> float:
        """Calculates CNP bid based on Haversine distance and battery life."""
        if not my_telemetry.latitude or not my_telemetry.longitude:
            return float('inf')
            
        import math
        # Simplified distance metric for bidding
        dist = math.hypot(my_telemetry.latitude - target_lat, my_telemetry.longitude - target_lon)
        
        # Battery penalty (lower battery = higher bid/less likely to win)
        batt = my_telemetry.battery_level or 100.0
        penalty = (100.0 - batt) * 0.1
        return dist + penalty

    async def evaluate_tick(self, current_telemetry: TelemetryData) -> None:
        """
        Called periodically by the main loop.
        Evaluates current state against swarm intent and modifies navigation if required.
        """
        if not self.is_active:
            return
            
        if self.safety.is_failsafe_active:
            logger.debug("DecisionEngine suspended: Safety failsafe is active.")
            return
            
        # 1. Collect peer telemetry
        peer_telemetry = {}
        for peer_id in self.swarm.registry.get_all_peers():
            state = self.swarm.registry.get_peer(peer_id)
            if state and state.is_active and state.telemetry:
                peer_telemetry[peer_id] = state.telemetry
                
        # 2. Evaluate Collision Threats (Highest Priority)
        state, correction, threat_peer, dist = self.ca.evaluate_threats(
            current_telemetry, 
            peer_telemetry
        )
        
        if state != "NORMAL":
            import time
            mode = current_telemetry.flight_mode or "UNKNOWN"
            log_str = (
                f"SAFETY INTERVENTION | state: {state} | "
                f"own_id: {self.swarm.identity.drone_id} | neighbor_id: {threat_peer} | "
                f"dist: {dist:.2f}m | mode: {mode} | ts: {time.time()} | reason: Minimum separation breached"
            )
            if state == "WARNING":
                logger.warning(log_str + " | action: NONE (Logging)")
            elif state == "AVOIDANCE":
                logger.warning(log_str + " | action: EVASIVE_MOVE")
                if correction:
                    await self.nav.flight_manager.move(correction)
                return
            elif state == "EMERGENCY":
                logger.critical(log_str + " | action: EMERGENCY_HOVER")
                await self.nav.flight_manager.hover()
                return

        # 3. Proceed with Mission Execution
        mission_state = self.mission.get_current_state()
        if mission_state == "RUNNING":
            wp = self.mission.get_current_waypoint()
            if wp:
                reached = await self.mission.executor.execute_waypoint(
                    current_telemetry, 
                    self.mission.tracker.current_index
                )
                if reached:
                    logger.info("Waypoint reached, advancing mission.")
                    if wp.delay > 0:
                        await asyncio.sleep(wp.delay)
                    self.mission.advance_waypoint()
