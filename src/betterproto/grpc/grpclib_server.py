from abc import ABC
from collections.abc import AsyncIterable
from typing import (
    Any,
    Callable,
    Dict,
)

import grpclib
import grpclib.server


class ServiceBase(ABC):
    """
    Base class for async gRPC servers.
    """

