import json
from pydantic import ValidationError

from DroneOS.shared.protocol.messages import (
    BaseMessage, MessageType, HeartbeatMessage, TelemetryMessage,
    ControlMessage, StatusMessage, ErrorMessage, EmergencyMessage,
    MissionMessage, MissionProgressMessage, MissionStatusMessage,
    MissionCompleteMessage, MissionAbortMessage, MissionPauseMessage,
    MissionResumeMessage, MissionUploadMessage, MissionStartMessage,
    MissionStopMessage, MissionDeleteMessage, MissionDuplicateMessage,
    MissionClearMessage, CommandLifecycleMessage, TestInjectMessage,
    ParamRequestMessage, ParamResponseMessage, DiagnosticsMessage,
    DroneJoinMessage, DroneLeaveMessage, SwarmStateMessage,
    PeerStateMessage, DroneIdentityMessage, SwarmHeartbeatMessage,
    TaskBidMessage
)
from DroneOS.shared.communication.interfaces import IMessageSerializer

class JsonSerializer(IMessageSerializer):
    def __init__(self):
        # Map message types to their corresponding Pydantic models
        self._type_map = {
            MessageType.HEARTBEAT: HeartbeatMessage,
            MessageType.TELEMETRY: TelemetryMessage,
            MessageType.CONTROL: ControlMessage,
            MessageType.STATUS: StatusMessage,
            MessageType.ERROR: ErrorMessage,
            MessageType.EMERGENCY: EmergencyMessage,
            MessageType.MISSION: MissionMessage,
            MessageType.MISSION_PROGRESS: MissionProgressMessage,
            MessageType.MISSION_STATUS: MissionStatusMessage,
            MessageType.MISSION_COMPLETE: MissionCompleteMessage,
            MessageType.MISSION_ABORT: MissionAbortMessage,
            MessageType.MISSION_PAUSE: MissionPauseMessage,
            MessageType.MISSION_RESUME: MissionResumeMessage,
            MessageType.MISSION_UPLOAD: MissionUploadMessage,
            MessageType.MISSION_START: MissionStartMessage,
            MessageType.MISSION_STOP: MissionStopMessage,
            MessageType.MISSION_DELETE: MissionDeleteMessage,
            MessageType.MISSION_DUPLICATE: MissionDuplicateMessage,
            MessageType.MISSION_CLEAR: MissionClearMessage,
            MessageType.COMMAND_LIFECYCLE: CommandLifecycleMessage,
            MessageType.TEST_INJECT: TestInjectMessage,
            MessageType.PARAM_REQUEST: ParamRequestMessage,
            MessageType.PARAM_RESPONSE: ParamResponseMessage,
            MessageType.DIAGNOSTICS: DiagnosticsMessage,
            MessageType.DRONE_JOIN: DroneJoinMessage,
            MessageType.DRONE_LEAVE: DroneLeaveMessage,
            MessageType.SWARM_STATE: SwarmStateMessage,
            MessageType.PEER_STATE: PeerStateMessage,
            MessageType.DRONE_IDENTITY: DroneIdentityMessage,
            MessageType.SWARM_HEARTBEAT: SwarmHeartbeatMessage,
            MessageType.TASK_BID: TaskBidMessage
        }

    def serialize(self, message: BaseMessage) -> bytes:
        return message.model_dump_json().encode('utf-8')

    def deserialize(self, data: bytes) -> BaseMessage:
        try:
            json_str = data.decode('utf-8')
            parsed_dict = json.loads(json_str)
            
            if 'msg_type' not in parsed_dict:
                raise ValueError("Missing 'msg_type' in message")
                
            msg_type = MessageType(parsed_dict['msg_type'])
            
            if msg_type not in self._type_map:
                raise ValueError(f"Unknown message type: {msg_type}")
                
            model_class = self._type_map[msg_type]
            return model_class.model_validate(parsed_dict)
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        except ValidationError as e:
            raise ValueError(f"Message validation error: {e}")
