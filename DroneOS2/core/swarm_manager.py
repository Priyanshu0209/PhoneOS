import time
from typing import Dict, Optional, List, Any
from DroneOS.shared.utils.logger import setup_logger
from DroneOS.shared.protocol.messages import (
    SwarmHeartbeatMessage, DroneJoinMessage, DroneLeaveMessage,
    SwarmStateMessage, PeerStateMessage, DroneIdentityMessage, TelemetryMessage, TelemetryData
)

logger = setup_logger("SwarmManager")

class DroneIdentityManager:
    def __init__(self, drone_id: str):
        self.drone_id = drone_id
        self.role = "peer"
        self.capabilities: Dict[str, Any] = {"camera": True, "lidar": False}
        
    def get_identity_message(self) -> DroneIdentityMessage:
        return DroneIdentityMessage(
            sender_id=self.drone_id, timestamp=time.time(),
            drone_id=self.drone_id, role=self.role
        )

class PeerStateManager:
    def __init__(self, drone_id: str):
        self.drone_id = drone_id
        self.last_seen: float = time.time()
        self.is_active: bool = True
        self.current_task: Optional[str] = None
        self.telemetry: Optional[TelemetryData] = None

class SwarmRegistry:
    def __init__(self):
        self.peers: Dict[str, PeerStateManager] = {}

    def get_peer(self, drone_id: str) -> Optional[PeerStateManager]:
        return self.peers.get(drone_id)

    def add_peer(self, drone_id: str):
        if drone_id not in self.peers:
            self.peers[drone_id] = PeerStateManager(drone_id)
            logger.info(f"Registered new peer: {drone_id}")

    def remove_peer(self, drone_id: str):
        if drone_id in self.peers:
            del self.peers[drone_id]
            logger.info(f"Removed peer from registry: {drone_id}")

    def get_all_peers(self) -> List[str]:
        return list(self.peers.keys())

class DroneDiscoveryManager:
    def __init__(self, registry: SwarmRegistry):
        self.registry = registry

    def handle_join(self, msg: DroneJoinMessage):
        self.registry.add_peer(msg.sender_id)
        logger.info(f"Discovery: {msg.sender_id} joined from {msg.drone_ip}:{msg.drone_port}")

class DroneRemovalManager:
    def __init__(self, registry: SwarmRegistry):
        self.registry = registry

    def handle_leave(self, msg: DroneLeaveMessage):
        self.registry.remove_peer(msg.sender_id)
        logger.info(f"Removal: {msg.sender_id} left due to: {msg.reason}")

class SwarmHeartbeatManager:
    def __init__(self, registry: SwarmRegistry, timeout_sec: float = 5.0):
        self.registry = registry
        self.timeout_sec = timeout_sec

    def handle_heartbeat(self, msg: SwarmHeartbeatMessage):
        peer = self.registry.get_peer(msg.sender_id)
        if not peer:
            self.registry.add_peer(msg.sender_id)
            peer = self.registry.get_peer(msg.sender_id)
        if peer:
            peer.last_seen = time.time()
            peer.is_active = (msg.status == "active")

    def purge_stale_peers(self):
        current = time.time()
        stale = [pid for pid, peer in self.registry.peers.items() if current - peer.last_seen > self.timeout_sec]
        for pid in stale:
            self.registry.remove_peer(pid)
            logger.warning(f"Purged stale peer {pid} after {self.timeout_sec}s timeout")

class PeerSynchronization:
    def __init__(self, registry: SwarmRegistry):
        self.registry = registry

    def handle_peer_state(self, msg: PeerStateMessage):
        peer = self.registry.get_peer(msg.peer_id)
        if peer:
            peer.is_active = msg.is_active
            peer.current_task = msg.current_task

    def handle_telemetry(self, msg: TelemetryMessage):
        peer = self.registry.get_peer(msg.sender_id)
        if peer:
            peer.telemetry = msg.telemetry

class SwarmMembership:
    """
    Coordinates the decentralized swarm network.
    No Master/Slave interactions exist. Every drone evaluates SwarmRegistry identically.
    """
    def __init__(self, drone_id: str):
        self.identity = DroneIdentityManager(drone_id)
        self.registry = SwarmRegistry()
        self.discovery = DroneDiscoveryManager(self.registry)
        self.removal = DroneRemovalManager(self.registry)
        self.heartbeat_mgr = SwarmHeartbeatManager(self.registry)
        self.sync = PeerSynchronization(self.registry)
        
    def generate_swarm_state(self) -> SwarmStateMessage:
        return SwarmStateMessage(
            sender_id=self.identity.drone_id,
            timestamp=time.time(),
            active_drones=len(self.registry.get_all_peers()),
            formation_type="dynamic",
            target_waypoints=[]
        )
