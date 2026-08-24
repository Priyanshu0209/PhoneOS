import asyncio
import socket
from pydantic import ValidationError
from typing import Callable, Coroutine, Any, List, Optional

from DroneOS.shared.communication.interfaces import INetworkAdapter, IMessageSerializer
from DroneOS.shared.protocol.messages import BaseMessage
from DroneOS.shared.utils.logger import setup_logger

logger = setup_logger("UdpNetworkNode")

class UdpNetworkAdapter(INetworkAdapter):
    """
    A basic UDP Network Adapter for local LAN communication and discovery.
    Uses a simple broadcast for all messages for now to satisfy LAN auto-discovery.
    In a more advanced implementation, this could use TCP for reliable messages and UDP for telemetry.
    """
    def __init__(self, node_id: str, host: str, port: int, broadcast_address: str, 
                 serializer: IMessageSerializer, peer_host: Optional[str] = None, peer_port: Optional[int] = None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.broadcast_address = broadcast_address
        self.serializer = serializer
        self.configured_peer_host = peer_host
        self.configured_peer_port = peer_port
        self.known_endpoints = {}
        self.callbacks: List[Callable[[BaseMessage], Coroutine[Any, Any, None]]] = []
        
        self.transport = None
        self.protocol = None
        self._running = False
        self._active_tasks = set()
        self.loop = None
        
    class _UdpProtocol(asyncio.DatagramProtocol):
        def __init__(self, adapter: 'UdpNetworkAdapter'):
            self.adapter = adapter
            self.transport = None
            
        def connection_made(self, transport):
            self.transport = transport
            logger.info(f"UDP connection made on {self.adapter.port}")

        def datagram_received(self, data, addr):
            # Do not process our own broadcasts if they loop back
            logger.debug(f"Raw datagram received from {addr} ({len(data)} bytes)")
            if self.adapter.loop and self.adapter.loop.is_running():
                task = self.adapter.loop.create_task(self.adapter._handle_incoming(data, addr))
                # Keep a strong reference to avoid silent GC drops in asyncio
                self.adapter._active_tasks.add(task)
                task.add_done_callback(self.adapter._active_tasks.discard)

    async def start(self) -> None:
        if self._running:
            return
            
        self.loop = asyncio.get_running_loop()
        
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        try:
            sock.bind((self.host, self.port))
        except OSError as e:
            logger.error(f"Failed to bind to {self.host}:{self.port} - {e}")
            raise
            
        self.transport, self.protocol = await self.loop.create_datagram_endpoint(
            lambda: self._UdpProtocol(self),
            sock=sock
        )
        self._running = True
        logger.info(f"UdpNetworkAdapter started on {self.host}:{self.port}")

    async def stop(self) -> None:
        if not self._running:
            return
        if self.transport:
            self.transport.close()
        self._running = False
        
        for task in self._active_tasks:
            if not task.done():
                task.cancel()
        self._active_tasks.clear()
        
        logger.info("UdpNetworkAdapter stopped.")

    async def send_message(self, target_id: str, message: BaseMessage) -> None:
        if not self.transport:
            return
            
        if target_id in self.known_endpoints:
            addr = self.known_endpoints[target_id]
            data = self.serializer.serialize(message)
            self.transport.sendto(data, addr)
            logger.debug(f"Packet sent (Learned Unicast) to {target_id} at {addr[0]}:{addr[1]}")
        else:
            await self.broadcast_message(message)

    async def broadcast_message(self, message: BaseMessage) -> None:
        if not self.transport:
            logger.warning("Attempted to send message while adapter is stopped.")
            return
            
        try:
            data = self.serializer.serialize(message)
            
            # If we have a statically configured peer, prefer Unicast over Broadcast
            if self.configured_peer_host and self.configured_peer_port:
                addr = (self.configured_peer_host, self.configured_peer_port)
                self.transport.sendto(data, addr)
                logger.debug(f"Packet sent (Configured Unicast) to {addr[0]}:{addr[1]}")
            else:
                bcast_port = self.configured_peer_port if self.configured_peer_port else self.port
                addr = (self.broadcast_address, bcast_port)
                self.transport.sendto(data, addr)
                logger.debug(f"Packet sent (Discovery Broadcast) to {addr[0]}:{addr[1]}")
                
        except OSError as e:
            logger.exception(f"Failed to transmit message: {e}")

    def register_callback(self, callback: Callable[[BaseMessage], Coroutine[Any, Any, None]]) -> None:
        self.callbacks.append(callback)

    async def _handle_incoming(self, data: bytes, addr: tuple) -> None:
        if not data: return
        # MAVLink 1 is 0xFE, MAVLink 2 is 0xFD
        if data[0] in (0xFE, 0xFD):
            # Silently ignore binary MAVLink packets
            return
        # Basic check for JSON
        if data[0] not in (ord('{'), ord('[')):
            logger.warning(f"Packet rejected: Not a valid JSON payload from {addr}")
            return
            
        try:
            message = self.serializer.deserialize(data)
        except ValidationError as e:
            logger.warning(f"Packet rejected (Schema mismatch) from {addr}: {e}")
            return
        except Exception as e:
            logger.exception(f"Packet rejected: Error parsing datagram from {addr}: {e}")
            return

        logger.debug(f"Packet validated: sender={message.sender_id}, type={message.msg_type.value}")
        
        # Ignore our own messages
        if message.sender_id == self.node_id:
            logger.debug(f"Packet rejected: Dropping loopback packet from self ({self.node_id})")
            return
            
        # Dynamic Unicast Peer Learning
        if message.sender_id not in self.known_endpoints:
            logger.debug(f"Peer learned: {message.sender_id} at {addr[0]}:{addr[1]}")
            if self.configured_peer_host is None:
                logger.info(f"Connection established! Learned peer endpoint: {addr[0]}:{addr[1]}")
        elif self.known_endpoints[message.sender_id] != addr:
            logger.debug(f"Peer updated: {message.sender_id} moved to {addr[0]}:{addr[1]}")
            
        self.known_endpoints[message.sender_id] = addr
            
        for callback in self.callbacks:
            try:
                await callback(message)
            except Exception as e:
                logger.exception(f"Internal Application Error during callback execution for {message.msg_type.value}: {e}")
