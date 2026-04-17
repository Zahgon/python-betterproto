import asyncio
from abc import ABC
from typing import (
    TYPE_CHECKING,
    AsyncIterable,
    AsyncIterator,
    Collection,
    Iterable,
    Mapping,
    Optional,
    Tuple,
    Type,
    Union,
)

import grpclib.const


if TYPE_CHECKING:
    from grpclib.client import Channel
    from grpclib.metadata import Deadline

    from .._types import (
        ST,
        IProtoMessage,
        Message,
        T,
    )


Value = Union[str, bytes]
MetadataLike = Union[Mapping[str, Value], Collection[Tuple[str, Value]]]
MessageSource = Union[Iterable["IProtoMessage"], AsyncIterable["IProtoMessage"]]


class ServiceStub(ABC):
    """
    Base class for async gRPC clients.
    """

    def __init__(
        self,
        channel: "Channel",
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> None:
        self.channel = channel
        self.timeout = timeout
        self.deadline = deadline
        self.metadata = metadata


    async def _unary_unary(
        self,
        route: str,
        request: "IProtoMessage",
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> "T":
        """Make a unary request and return the response."""
        pass

    async def _unary_stream(
        self,
        route: str,
        request: "IProtoMessage",
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> AsyncIterator["T"]:
        """Make a unary request and return the stream response iterator."""
        pass

    async def _stream_unary(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: Type["IProtoMessage"],
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> "T":
        """Make a stream request and return the response."""
        pass

    async def _stream_stream(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: Type["IProtoMessage"],
        response_type: Type["T"],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> AsyncIterator["T"]:
        """
        Make a stream request and return an AsyncIterator to iterate over response
        messages.
        """
        pass

