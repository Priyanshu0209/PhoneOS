from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List

class MessageType(str, Enum):
    HEARTBEAT = "heartbeat"
    TELEMETRY = "telemetry"
    CONTROL = "control"
    STATUS = "status"
    ERROR = "error"
    COMMAND_LIFECYCLE = "command_lifecycle"
    EMERGENCY = "emergency"
    TASK_BID = "task_bid"
    MISSION = "mission"
    MISSION_PROGRESS = "mission_progress"
    MISSION_STATUS = "mission_status"
    MISSION_COMPLETE = "mission_complete"
    MISSION_ABORT = "mission_abort"
    MISSION_PAUSE = "mission_pause"
    MISSION_RESUME = "mission_resume"
    MISSION_UPLOAD = "mission_upload"
    MISSION_START = "mission_start"
    MISSION_STOP = "mission_stop"
    MISSION_DELETE = "mission_delete"
    MISSION_DUPLICATE = "mission_duplicate"
    MISSION_CLEAR = "mission_clear"
    DRONE_JOIN = "drone_join"
    DRONE_LEAVE = "drone_leave"
    SWARM_STATE = "swarm_state"
    PEER_STATE = "peer_state"
    DRONE_IDENTITY = "drone_identity"
    SWARM_HEARTBEAT = "swarm_heartbeat"
    PARAM_REQUEST = "param_request"
    PARAM_RESPONSE = "param_response"
    DIAGNOSTICS = "diagnostics"
    TEST_INJECT = "test_inject"

class BaseMessage(BaseModel):
    msg_type: MessageType
    sender_id: str
    timestamp: float = Field(description="Unix timestamp")
    target_id: Optional[str] = None

class TestInjectMessage(BaseMessage):
    msg_type: MessageType = MessageType.TEST_INJECT
    injection_type: str
    active: bool = True

class HeartbeatMessage(BaseMessage):
    msg_type: MessageType = MessageType.HEARTBEAT
    status: str = "active"

class TelemetryData(BaseModel):
    timestamp: Optional[float] = None
    gps_valid: Optional[bool] = None
    battery_level: Optional[float] = None
    voltage: Optional[float] = None
    altitude: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    velocity_x: Optional[float] = None
    velocity_y: Optional[float] = None
    velocity_z: Optional[float] = None
    ground_speed: Optional[float] = None
    heading: Optional[float] = None
    pitch: Optional[float] = None
    roll: Optional[float] = None
    yaw: Optional[float] = None
    health_all_ok: Optional[bool] = None
    gyro_calibrated: Optional[bool] = None
    accel_calibrated: Optional[bool] = None
    mag_calibrated: Optional[bool] = None
    local_pos_valid: Optional[bool] = None
    global_pos_valid: Optional[bool] = None
    is_armable: Optional[bool] = None
    home_valid: Optional[bool] = None
    status_text: Optional[str] = None
    heartbeat_age: Optional[float] = None
    flight_mode: str
    armed_state: Optional[str] = None
    mission_state: str = "IDLE"      # Added for decentralized mission awareness
    future_intent: str = "NONE"      # Added for collision avoidance and swarm intent
    active_injections: List[str] = Field(default_factory=list) # Marks injected states

class TelemetryMessage(BaseMessage):
    msg_type: MessageType = MessageType.TELEMETRY
    telemetry: TelemetryData

class TaskBidMessage(BaseMessage):
    msg_type: MessageType = MessageType.TASK_BID
    task_id: str
    bid_value: float
    is_award: bool = False

class CommandAction(str, Enum):
    ARM = "arm"
    DISARM = "disarm"
    TAKEOFF = "takeoff"
    LAND = "land"
    RTL = "rtl"
    HOVER = "hover"
    STOP = "stop"
    MOVE = "move"
    FORMATION_UPDATE = "formation_update"
    SET_MODE = "set_mode"
    GOTO = "goto"

class ControlMessage(BaseMessage):
    msg_type: MessageType = MessageType.CONTROL
    action: CommandAction
    params: Optional[Dict[str, Any]] = None
    cmd_id: Optional[str] = None

class StatusMessage(BaseMessage):
    msg_type: MessageType = MessageType.STATUS
    status_text: str
    severity: str = "info"

class CommandLifecycleMessage(BaseMessage):
    msg_type: MessageType = MessageType.COMMAND_LIFECYCLE
    action: CommandAction
    stage: str # REQUESTED, BACKEND_RECEIVED, MAVSDK_REQUESTED, MAVSDK_RESPONSE, PX4_TELEMETRY_CONFIRMATION, SUCCESS, REJECTED, TIMEOUT, FAILED
    reason: Optional[str] = None
    cmd_id: Optional[str] = None

class ErrorMessage(BaseMessage):
    msg_type: MessageType = MessageType.ERROR
    error_code: int
    error_msg: str

class EmergencyMessage(BaseMessage):
    msg_type: MessageType = MessageType.EMERGENCY
    action: str = "stop_and_land"

class MissionMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION
    mission_id: str
    mission_data: Dict[str, Any]

class MissionProgressMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_PROGRESS
    mission_id: str
    current_waypoint: int
    total_waypoints: int
    percent_complete: float

class MissionStatusMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_STATUS
    mission_id: str
    status: str

class MissionCompleteMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_COMPLETE
    mission_id: str

class MissionAbortMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_ABORT
    mission_id: str

class MissionPauseMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_PAUSE
    mission_id: str

class MissionResumeMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_RESUME
    mission_id: str

class MissionUploadMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_UPLOAD
    mission_id: str
    mission_json: str

class MissionStartMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_START
    mission_id: str

class MissionStopMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_STOP
    mission_id: str

class MissionDeleteMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_DELETE
    mission_id: str

class MissionDuplicateMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_DUPLICATE
    mission_id: str

class MissionClearMessage(BaseMessage):
    msg_type: MessageType = MessageType.MISSION_CLEAR
    mission_id: str

class DroneJoinMessage(BaseMessage):
    msg_type: MessageType = MessageType.DRONE_JOIN
    drone_ip: str
    drone_port: int
    capabilities: Optional[Dict[str, Any]] = None

class DroneLeaveMessage(BaseMessage):
    msg_type: MessageType = MessageType.DRONE_LEAVE
    reason: str = "shutdown"

class SwarmStateMessage(BaseMessage):
    msg_type: MessageType = MessageType.SWARM_STATE
    active_drones: int
    formation_type: str
    target_waypoints: List[Dict[str, Any]]

class PeerStateMessage(BaseMessage):
    msg_type: MessageType = MessageType.PEER_STATE
    peer_id: str
    is_active: bool
    current_task: Optional[str] = None

class DroneIdentityMessage(BaseMessage):
    msg_type: MessageType = MessageType.DRONE_IDENTITY
    drone_id: str
    role: str = "peer"

class SwarmHeartbeatMessage(BaseMessage):
    msg_type: MessageType = MessageType.SWARM_HEARTBEAT
    status: str = "active"
    battery_level: Optional[float] = None

class ParamRequestMessage(BaseMessage):
    msg_type: MessageType = MessageType.PARAM_REQUEST
    action: str  # "read_all", "read", or "write"
    param_name: Optional[str] = None
    param_value: Optional[Any] = None
    param_type: Optional[str] = None # "float" or "int"

class ParamResponseMessage(BaseMessage):
    msg_type: MessageType = MessageType.PARAM_RESPONSE
    action: str  # "read_all", "read", or "write"
    success: bool
    message: str = ""
    parameters: Optional[Dict[str, Any]] = None # For read_all
    param_name: Optional[str] = None
    param_value: Optional[Any] = None
    param_type: Optional[str] = None

class DiagnosticsMessage(BaseMessage):
    msg_type: MessageType = MessageType.DIAGNOSTICS
    diagnostics: Dict[str, Any]
