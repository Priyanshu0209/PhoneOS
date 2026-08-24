from DroneOS.shared.utils.logger import setup_logger
from DroneOS.core.interfaces import IFlightController

logger = setup_logger("SafetyModule")

class SafetyModule:
    """
    Coordinates safety actions. Decouples safety triggers from flight logic.
    """
    def __init__(self, flight_controller: IFlightController, config=None):
        self.fc = flight_controller
        self.config = config
        self.is_failsafe_active: bool = False
        self.mission_manager = None

    def set_mission_manager(self, mm):
        self.mission_manager = mm

    async def trigger_emergency_stop(self) -> None:
        self.is_failsafe_active = True
        logger.critical("EMERGENCY STOP INITIATED!")
        # Cut power, stop all movement immediately
        try:
            await self.fc.move_velocity(0.0, 0.0, 0.0, 1.0, 0.0)
        except Exception as e:
            logger.error(f"Failed to send zero velocity during emergency stop: {e}")
            
        await self.fc.kill()
        
        if self.mission_manager:
            self.mission_manager.abort_mission()


    def reset_failsafe(self) -> None:
        self.is_failsafe_active = False
        logger.info("Failsafe/Emergency stop reset manually.")

    async def trigger_connection_lost_failsafe(self) -> None:
        self.is_failsafe_active = True
        telemetry = await self.fc.get_telemetry()
        
        if telemetry.armed_state != "ARMED":
            logger.info("Connection lost, but drone is not armed. Waiting for reconnection.")
            return

        is_indoor = self.config and getattr(self.config, "profile", "") == "indoor"
        if is_indoor:
            logger.warning("Connection lost failsafe! Indoor mode active -> Landing.")
            await self.fc.land()
        elif telemetry.home_valid:
            logger.warning("Connection lost failsafe! Returning to launch...")
            await self.fc.rtl()
        else:
            logger.warning("Connection lost failsafe! Home invalid -> Landing.")
            await self.fc.land()

    async def trigger_low_battery_failsafe(self) -> None:
        self.is_failsafe_active = True
        is_indoor = self.config and getattr(self.config, "profile", "") == "indoor"
        if is_indoor:
            logger.warning("Low battery failsafe triggered! Indoor mode active -> Landing.")
            await self.fc.land()
        else:
            logger.warning("Low battery failsafe triggered! Returning to launch...")
            await self.fc.rtl()

    async def trigger_critical_battery_failsafe(self) -> None:
        self.is_failsafe_active = True
        logger.critical("Critical battery failsafe triggered! Landing immediately...")
        await self.fc.land()
