from abc import ABC, abstractmethod
from typing import Callable, Any, Coroutine
from DroneOS.shared.protocol.messages import BaseMessage

class IMessageSerializer(ABC):
    @abstractmethod
    def serialize(self, message: BaseMessage) -> bytes:
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> BaseMessage:
        pass

class INetworkAdapter(ABC):
    @abstractmethod
    async def start(self) -> None:
        """
        Binds to the network socket and begins listening for incoming datagrams.
        Inputs: None
        Outputs: None
        Failure Modes: Port already in use, OSError, permission denied.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Closes the network socket and cleans up resources.
        Inputs: None
        Outputs: None
        Failure Modes: Already stopped.
        """
        pass

    @abstractmethod
    async def send_message(self, target_id: str, message: BaseMessage) -> None:
        """
        Transmits a single unicast message to a known target node.
        Inputs: target_id (str), message (BaseMessage)
        Outputs: None
        Failure Modes: Target endpoint unknown, serialization failure, network offline.
        """
        pass

    @abstractmethod
    async def broadcast_message(self, message: BaseMessage) -> None:
        """
        Transmits a message to all known peers or the local broadcast address.
        Inputs: message (BaseMessage)
        Outputs: None
        Failure Modes: Serialization failure, network offline.
        """
        pass

    @abstractmethod
    def register_callback(self, callback: Callable[[BaseMessage], Coroutine[Any, Any, None]]) -> None:
        """
        Registers an async callback to trigger whenever a valid message is received.
        Inputs: callback (async function accepting BaseMessage)
        Outputs: None
        Failure Modes: None.
        """
        pass
