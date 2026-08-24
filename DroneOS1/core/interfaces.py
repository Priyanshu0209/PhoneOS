from abc import ABC, abstractmethod
from DroneOS.shared.protocol.messages import TelemetryData

class IFlightController(ABC):
    """
    Abstract interface for flight controllers (AirSim, PX4).
    The rest of the DroneOS must rely ONLY on this interface.
    """
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connects to the underlying flight controller backend.
        Inputs: None
        Outputs: True if connected successfully, False otherwise.
        Failure Modes: Network timeout, adapter crash, backend unavailable.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Gracefully disconnects from the backend and releases resources.
        Inputs: None
        Outputs: None
        Failure Modes: Connection already closed, adapter crash.
        """
        pass

    @abstractmethod
    async def arm(self) -> bool:
        """
        Arms the drone motors for flight.
        Inputs: None
        Outputs: True if successful, False if rejected by FC.
        Failure Modes: Pre-flight checks failed, already armed.
        """
        pass

    @abstractmethod
    async def disarm(self) -> bool:
        """
        Disarms the drone motors.
        Inputs: None
        Outputs: True if successful, False if rejected by FC.
        Failure Modes: Already disarmed, FC refusing disarm in-air.
        """
        pass

    @abstractmethod
    async def takeoff(self, altitude: float = 10.0) -> bool:
        """
        Initiates autonomous takeoff sequence to the specified altitude.
        Inputs: altitude (float, meters)
        Outputs: True if sequence initiated, False if rejected.
        Failure Modes: Not armed, FC GPS lock missing, altitude out of bounds.
        """
        pass

    @abstractmethod
    async def land(self) -> bool:
        """
        Commands the drone to land at its current lateral position.
        Inputs: None
        Outputs: True if landing initiated, False if rejected.
        Failure Modes: FC rejecting command, already landed.
        """
        pass
        
    @abstractmethod
    async def rtl(self) -> bool:
        """
        Commands the drone to Return to Launch (RTL).
        Inputs: None
        Outputs: True if RTL initiated, False if rejected.
        Failure Modes: No home position set on FC, FC rejecting command.
        """
        pass

    @abstractmethod
    async def hover(self) -> bool:
        """
        Commands the drone to hold its current position and altitude.
        Inputs: None
        Outputs: True if hover initiated, False if rejected.
        Failure Modes: FC rejecting command, GPS lock lost.
        """
        pass

    @abstractmethod
    async def move_velocity(self, vx: float, vy: float, vz: float, duration: float, yaw_rate: float = 0.0) -> bool:
        """
        Commands velocity targets in the local NED frame.
        Inputs: vx, vy, vz (m/s), duration (s), yaw_rate (deg/s)
        Outputs: True if command accepted, False if rejected.
        Failure Modes: Network delay, FC bounds exceeded.
        """
        pass

    @abstractmethod
    async def get_telemetry(self) -> TelemetryData:
        """
        Retrieves the latest telemetry data from the FC.
        Inputs: None
        Outputs: TelemetryData object containing position, velocity, and battery.
        Failure Modes: FC disconnected, missing GPS lock. Returns empty TelemetryData on fail.
        """
        pass

    @abstractmethod
    async def set_mode(self, mode: str) -> bool:
        """
        Commands the drone to enter the specified flight mode.
        Inputs: mode (str) e.g., 'STABILIZE', 'GUIDED', 'RTL'
        Outputs: True if accepted, False if rejected.
        Failure Modes: FC rejecting command, mode not supported.
        """
        pass

    @abstractmethod
    async def get_all_params(self) -> dict:
        """
        Retrieves all parameters from the flight controller.
        Outputs: dict mapping parameter name to value.
        """
        pass

    @abstractmethod
    async def get_param(self, name: str, param_type: str = "float"):
        """
        Retrieves a single parameter.
        Inputs: name (str), param_type ("float" or "int")
        Outputs: The value of the parameter, or None if not found.
        """
        pass

    @abstractmethod
    async def set_param(self, name: str, value, param_type: str = "float") -> bool:
        """
        Sets a single parameter.
        Inputs: name (str), value, param_type ("float" or "int")
        Outputs: True if successfully set.
        """
        pass
