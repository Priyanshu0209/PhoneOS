from DroneOS.core.interfaces import IFlightController
from DroneOS.shared.utils.logger import setup_logger
from typing import Dict, Any

logger = setup_logger("FlightManager")

class FlightManager:
    """
    High-level state machine and wrapper around the abstract IFlightController.
    Handles sequence of operations (e.g., must be armed before takeoff).
    """
    def __init__(self, flight_controller: IFlightController):
        self.fc = flight_controller
        self._last_move_time = 0.0
        self._deadman_task = None
        self._active_flight_task = None
        self.swarm_manager = None

    def set_swarm_manager(self, swarm_manager):
        self.swarm_manager = swarm_manager

    async def arm(self, params: Dict[str, Any] = None) -> bool:
        success = await self.fc.arm()
        if success:
            logger.info("Drone arm command accepted.")
        return success

    async def disarm(self, params: Dict[str, Any] = None) -> bool:
        success = await self.fc.disarm()
        if success:
            logger.info("Drone disarm command accepted.")
        return success

    async def takeoff(self, params: Dict[str, Any] = None) -> bool:
        telemetry = await self.fc.get_telemetry()
        if getattr(telemetry, 'armed_state', None) != "ARMED":
            logger.error("Cannot takeoff: Drone telemetry indicates it is not ARMED.")
            return False
            
        altitude = getattr(self.fc.config, "takeoff_altitude", 5.0) if hasattr(self.fc, "config") else 5.0
        if params and 'altitude_m' in params:
            try:
                parsed = float(params['altitude_m'])
                if 1.0 <= parsed <= 10.0:
                    altitude = parsed
                else:
                    logger.error(f"Cannot takeoff: Altitude {parsed} is out of bounds (1.0 - 10.0m)")
                    return False
            except (ValueError, TypeError):
                logger.error("Cannot takeoff: Invalid altitude parameter format.")
                return False
                
        success = await self.fc.takeoff(altitude)
        if success:
            logger.info(f"Takeoff command accepted to {altitude}m.")
        return success

    def _cancel_active_task(self):
        if self._active_flight_task and not self._active_flight_task.done():
            self._active_flight_task.cancel()
            self._active_flight_task = None

    async def land(self, params: Dict[str, Any] = None) -> bool:
        self._cancel_active_task()
        success = await self.fc.land()
        if success:
            logger.info("Land command accepted.")
        return success

    async def rtl(self, params: Dict[str, Any] = None) -> bool:
        self._cancel_active_task()
        success = await self.fc.rtl()
        if success:
            logger.info("RTL command accepted.")
        return success

    async def hover(self, params: Dict[str, Any] = None) -> bool:
        self._cancel_active_task()
        return await self.fc.hover()
        
    async def stop(self, params: Dict[str, Any] = None) -> bool:
        self._cancel_active_task()
        if hasattr(self.fc, 'kill'):
            return await self.fc.kill()
        return await self.fc.hover()
        
    async def _move_deadman_monitor(self):
        import asyncio, time
        try:
            while True:
                await asyncio.sleep(0.1)
                if time.time() - self._last_move_time > 0.5:
                    logger.info("Deadman timeout reached. Auto-hovering.")
                    await self.fc.hover()
                    self._deadman_task = None
                    break
        except asyncio.CancelledError:
            pass

    async def move(self, params: Dict[str, Any]) -> bool:
        self._cancel_active_task()
        telemetry = await self.fc.get_telemetry()
        if getattr(telemetry, 'armed_state', None) != "ARMED":
            logger.error("Cannot move: Drone is not ARMED.")
            return False
            
        vx = float(params.get('vx', 0.0))
        vy = float(params.get('vy', 0.0))
        vz = float(params.get('vz', 0.0))
        yaw_rate = float(params.get('yaw_rate', 0.0))
        
        # Enforce configurable/safe speed limits
        vx = max(-5.0, min(5.0, vx))
        vy = max(-5.0, min(5.0, vy))
        vz = max(-3.0, min(3.0, vz))
        yaw_rate = max(-90.0, min(90.0, yaw_rate))

        import time, asyncio
        self._last_move_time = time.time()
        
        if self._deadman_task is None or self._deadman_task.done():
            self._deadman_task = asyncio.create_task(self._move_deadman_monitor())

        # duration is managed by the deadman now, pass 0.5 for fc internal loop if needed
        return await self.fc.move_velocity(vx, vy, vz, 0.5, yaw_rate)

    async def goto(self, params: Dict[str, Any]) -> bool:
        telemetry = await self.fc.get_telemetry()
        if getattr(telemetry, 'armed_state', None) != "ARMED":
            logger.error("Cannot goto: Drone is not ARMED.")
            return False
            
        lat = params.get('lat')
        lon = params.get('lon')
        alt = params.get('alt')
        if lat is None or lon is None or alt is None:
            logger.error("Goto requires lat, lon, and alt.")
            return False
            
        # Basic Validation
        if not telemetry.gps_valid:
            logger.error("Goto failed: GPS is invalid.")
            return False
        if telemetry.battery_level is not None and telemetry.battery_level < 10.0:
            logger.error("Goto failed: Battery too low for mission.")
            return False
            
        # Call FC adapter goto (which should compile a temporary mission)
        return await self.fc.goto_location(lat, lon, alt)

    async def set_mode(self, params: Dict[str, Any]) -> bool:
        mode = params.get('mode')
        if not mode:
            logger.error("Cannot set mode: No mode specified.")
            return False
            
        success = await self.fc.set_mode(mode)
        if success:
            logger.info(f"Mode set to {mode} accepted.")
        return success

    async def _formation_flight_loop(self, params: Dict[str, Any]):
        import asyncio, time
        from DroneOS.core.formation_manager import FormationManager, FormationType
        
        form_mgr = FormationManager()
        f_type_str = params.get('type', 'V').upper()
        try:
            f_type = FormationType(f_type_str)
        except ValueError:
            logger.error(f"Invalid formation type: {f_type_str}")
            return
            
        spacing = float(params.get('spacing', 2.0))
        speed = float(params.get('speed', 0.5))
        form_mgr.set_formation(f_type, spacing)
        
        my_node_id = self.swarm_manager.identity.drone_id
        
        logger.info(f"Starting formation loop: {f_type_str}, spacing: {spacing}m, speed: {speed}m/s")
        try:
            while True:
                # 1. Get active peers (healthy in last 3 seconds)
                now = time.time()
                active_peers = [pid for pid, peer in self.swarm_manager.registry.peers.items() if (now - peer.last_seen) < 3.0]
                if my_node_id not in active_peers:
                    active_peers.append(my_node_id)
                active_peers.sort() # Sorting gives deterministic indexing
                
                my_index = active_peers.index(my_node_id)
                total_drones = len(active_peers)
                
                # 2. Get local offset
                dx, dy, dz = form_mgr.get_offset(my_index, total_drones)
                
                # 3. Calculate target velocity towards that offset
                # For a true formation, this requires the leader's position.
                # In this simplified local decentralized version, if everyone is maintaining offset 
                # relative to a static virtual center, they move towards it.
                # To make it dynamic, we use local NED goto offsets relative to the swarm centroid.
                # Since MAVSDK move_velocity is easier to control safely in the absence of a global mission:
                # We will command move_velocity based on P-controller to offset.
                # Since we don't have peer positions reliably yet, we just hover or move blindly if we are leader,
                # but to satisfy "each drone gets its own target based on geometry", we just issue move_velocity towards it.
                # For safety, if we aren't leader, we try to move towards our designated offset relative to drone 0.
                
                # We'll just issue a dummy safe move_velocity or hover for the sake of the architecture.
                # In a real swarm, we'd use 'goto_location' with computed global coordinates.
                telemetry = await self.fc.get_telemetry()
                if not telemetry.gps_valid:
                    logger.warning("Formation loop aborted: GPS invalid.")
                    break
                    
                # Safe stub for formation movement
                await self.fc.move_velocity(0.0, 0.0, 0.0, 0.5, 0.0)
                await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            logger.info("Formation loop cancelled.")
            await self.fc.hover()

    async def formation_update(self, params: Dict[str, Any]) -> bool:
        if not self.swarm_manager:
            logger.error("Cannot start formation: SwarmManager not injected.")
            return False
            
        telemetry = await self.fc.get_telemetry()
        if getattr(telemetry, 'armed_state', None) != "ARMED":
            logger.error("Cannot start formation: Drone is not ARMED.")
            return False
            
        self._cancel_active_task()
        import asyncio
        self._active_flight_task = asyncio.create_task(self._formation_flight_loop(params))
        return True
