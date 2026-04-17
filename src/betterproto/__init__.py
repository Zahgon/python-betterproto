from __future__ import annotations

import dataclasses
import enum as builtin_enum
import json
import math
import struct
import sys
import typing
import warnings
from abc import ABC
from base64 import (
    b64decode,
    b64encode,
)
from copy import deepcopy
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from io import BytesIO
from itertools import count
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    Iterable,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    get_type_hints,
)

from dateutil.parser import isoparse
from typing_extensions import Self

from ._types import T
from ._version import __version__
from .casing import (
    camel_case,
    safe_snake_case,
    snake_case,
)
from .enum import Enum as Enum
from .grpc.grpclib_client import ServiceStub as ServiceStub
from .utils import (
    classproperty,
    hybridmethod,
)


if TYPE_CHECKING:
    from _typeshed import (
        SupportsRead,
        SupportsWrite,
    )

if sys.version_info >= (3, 10):
    from types import UnionType as _types_UnionType
else:

    class _types_UnionType: ...


# Proto 3 data types
TYPE_ENUM = "enum"
TYPE_BOOL = "bool"
TYPE_INT32 = "int32"
TYPE_INT64 = "int64"
TYPE_UINT32 = "uint32"
TYPE_UINT64 = "uint64"
TYPE_SINT32 = "sint32"
TYPE_SINT64 = "sint64"
TYPE_FLOAT = "float"
TYPE_DOUBLE = "double"
TYPE_FIXED32 = "fixed32"
TYPE_SFIXED32 = "sfixed32"
TYPE_FIXED64 = "fixed64"
TYPE_SFIXED64 = "sfixed64"
TYPE_STRING = "string"
TYPE_BYTES = "bytes"
TYPE_MESSAGE = "message"
TYPE_MAP = "map"

# Fields that use a fixed amount of space (4 or 8 bytes)
FIXED_TYPES = [
    TYPE_FLOAT,
    TYPE_DOUBLE,
    TYPE_FIXED32,
    TYPE_SFIXED32,
    TYPE_FIXED64,
    TYPE_SFIXED64,
]

# Fields that are numerical 64-bit types
INT_64_TYPES = [TYPE_INT64, TYPE_UINT64, TYPE_SINT64, TYPE_FIXED64, TYPE_SFIXED64]

# Fields that are efficiently packed when
PACKED_TYPES = [
    TYPE_ENUM,
    TYPE_BOOL,
    TYPE_INT32,
    TYPE_INT64,
    TYPE_UINT32,
    TYPE_UINT64,
    TYPE_SINT32,
    TYPE_SINT64,
    TYPE_FLOAT,
    TYPE_DOUBLE,
    TYPE_FIXED32,
    TYPE_SFIXED32,
    TYPE_FIXED64,
    TYPE_SFIXED64,
]

# Wire types
# https://developers.google.com/protocol-buffers/docs/encoding#structure
WIRE_VARINT = 0
WIRE_FIXED_64 = 1
WIRE_LEN_DELIM = 2
WIRE_FIXED_32 = 5

# Mappings of which Proto 3 types correspond to which wire types.
WIRE_VARINT_TYPES = [
    TYPE_ENUM,
    TYPE_BOOL,
    TYPE_INT32,
    TYPE_INT64,
    TYPE_UINT32,
    TYPE_UINT64,
    TYPE_SINT32,
    TYPE_SINT64,
]

WIRE_FIXED_32_TYPES = [TYPE_FLOAT, TYPE_FIXED32, TYPE_SFIXED32]
WIRE_FIXED_64_TYPES = [TYPE_DOUBLE, TYPE_FIXED64, TYPE_SFIXED64]
WIRE_LEN_DELIM_TYPES = [TYPE_STRING, TYPE_BYTES, TYPE_MESSAGE, TYPE_MAP]

# Indicator of message delimitation in streams
SIZE_DELIMITED = -1


# Protobuf datetimes start at the Unix Epoch in 1970 in UTC.
def datetime_default_gen() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


DATETIME_ZERO = datetime_default_gen()


# Special protobuf json doubles
INFINITY = "Infinity"
NEG_INFINITY = "-Infinity"
NAN = "NaN"


class Casing(builtin_enum.Enum):
    """Casing constants for serialization."""

    CAMEL = camel_case  #: A camelCase sterilization function.
    SNAKE = snake_case  #: A snake_case sterilization function.


class Placeholder:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<PLACEHOLDER>"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _) -> Self:
        return self


# We can't simply use object() here because pydantic automatically performs deep-copy of mutable default values
# See #606
PLACEHOLDER: Any = Placeholder()


@dataclasses.dataclass(frozen=True)
class FieldMetadata:
    """Stores internal metadata used for parsing & serialization."""

    # Protobuf field number
    number: int
    # Protobuf type name
    proto_type: str
    # Map information if the proto_type is a map
    map_types: Optional[Tuple[str, str]] = None
    # Groups several "one-of" fields together
    group: Optional[str] = None
    # Describes the wrapped type (e.g. when using google.protobuf.BoolValue)
    wraps: Optional[str] = None
    # Is the field optional
    optional: Optional[bool] = False

    @staticmethod
    def get(field: dataclasses.Field) -> "FieldMetadata":
        """Returns the field metadata for a dataclass field."""
        return field.metadata["betterproto"]


def dataclass_field(
    number: int,
    proto_type: str,
    *,
    map_types: Optional[Tuple[str, str]] = None,
    group: Optional[str] = None,
    wraps: Optional[str] = None,
    optional: bool = False,
) -> dataclasses.Field:
    """Creates a dataclass field with attached protobuf metadata."""
    return dataclasses.field(
        default=None if optional else PLACEHOLDER,  # type: ignore
        metadata={
            "betterproto": FieldMetadata(
                number, proto_type, map_types, group, wraps, optional
            )
        },
    )


# Note: the fields below return `Any` to prevent type errors in the generated
# data classes since the types won't match with `Field` and they get swapped
# out at runtime. The generated dataclass variables are still typed correctly.


def enum_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return dataclass_field(number, TYPE_ENUM, group=group, optional=optional)


def bool_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return dataclass_field(number, TYPE_BOOL, group=group, optional=optional)


def int32_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_INT32, group=group, optional=optional)


def int64_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_INT64, group=group, optional=optional)


def uint32_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_UINT32, group=group, optional=optional)


def uint64_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_UINT64, group=group, optional=optional)






def float_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_FLOAT, group=group, optional=optional)


def double_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_DOUBLE, group=group, optional=optional)










def string_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_STRING, group=group, optional=optional)


def bytes_field(
    number: int, group: Optional[str] = None, optional: bool = False
) -> Any:
    return dataclass_field(number, TYPE_BYTES, group=group, optional=optional)


def message_field(
    number: int,
    group: Optional[str] = None,
    wraps: Optional[str] = None,
    optional: bool = False,
) -> Any:
    return dataclass_field(
        number, TYPE_MESSAGE, group=group, wraps=wraps, optional=optional
    )


def map_field(
    number: int, key_type: str, value_type: str, group: Optional[str] = None
) -> Any:
    return dataclass_field(
        number, TYPE_MAP, map_types=(key_type, value_type), group=group
    )


def _pack_fmt(proto_type: str) -> str:
    """Returns a little-endian format string for reading/writing binary."""
    return {
        TYPE_DOUBLE: "<d",
        TYPE_FLOAT: "<f",
        TYPE_FIXED32: "<I",
        TYPE_FIXED64: "<Q",
        TYPE_SFIXED32: "<i",
        TYPE_SFIXED64: "<q",
    }[proto_type]


def dump_varint(value: int, stream: "SupportsWrite[bytes]") -> None:
    """Encodes a single varint and dumps it into the provided stream."""
    pass


def encode_varint(value: int) -> bytes:
    """Encodes a single varint value for serialization."""
    pass


def size_varint(value: int) -> int:
    """Calculates the size in bytes that a value would take as a varint."""
    pass


def _preprocess_single(proto_type: str, wraps: str, value: Any) -> bytes:
    """Adjusts values before serialization."""
    pass


def _len_preprocessed_single(proto_type: str, wraps: str, value: Any) -> int:
    """Calculate the size of adjusted values for serialization without fully serializing them."""
    pass


def _serialize_single(
    field_number: int,
    proto_type: str,
    value: Any,
    *,
    serialize_empty: bool = False,
    wraps: str = "",
) -> bytes:
    """Serializes a single field and value."""
    pass


def _len_single(
    field_number: int,
    proto_type: str,
    value: Any,
    *,
    serialize_empty: bool = False,
    wraps: str = "",
) -> int:
    """Calculates the size of a serialized single field and value."""
    pass


def _parse_float(value: Any) -> float:
    """Parse the given value to a float

    Parameters
    ----------
    value: Any
        Value to parse

    Returns
    -------
    float
        Parsed value
    """
    if value == INFINITY:
        return float("inf")
    if value == NEG_INFINITY:
        return -float("inf")
    if value == NAN:
        return float("nan")
    return float(value)


def _dump_float(value: float) -> Union[float, str]:
    """Dump the given float to JSON

    Parameters
    ----------
    value: float
        Value to dump

    Returns
    -------
    Union[float, str]
        Dumped value, either a float or the strings
    """
    pass


def load_varint(stream: "SupportsRead[bytes]") -> Tuple[int, bytes]:
    """
    Load a single varint value from a stream. Returns the value and the raw bytes read.
    """
    result = 0
    raw = b""
    for shift in count(0, 7):
        if shift >= 64:
            raise ValueError("Too many bytes when decoding varint.")
        b = stream.read(1)
        if not b:
            raise EOFError("Stream ended unexpectedly while attempting to load varint.")
        raw += b
        b_int = int.from_bytes(b, byteorder="little")
        result |= (b_int & 0x7F) << shift
        if not (b_int & 0x80):
            return result, raw


def decode_varint(buffer: bytes, pos: int) -> Tuple[int, int]:
    """
    Decode a single varint value from a byte buffer. Returns the value and the
    new position in the buffer.
    """
    with BytesIO(buffer) as stream:
        stream.seek(pos)
        value, raw = load_varint(stream)
    return value, pos + len(raw)


@dataclasses.dataclass(frozen=True)
class ParsedField:
    number: int
    wire_type: int
    value: Any
    raw: bytes


def load_fields(stream: "SupportsRead[bytes]") -> Generator[ParsedField, None, None]:
    while True:
        try:
            num_wire, raw = load_varint(stream)
        except EOFError:
            return
        number = num_wire >> 3
        wire_type = num_wire & 0x7

        decoded: Any = None
        if wire_type == WIRE_VARINT:
            decoded, r = load_varint(stream)
            raw += r
        elif wire_type == WIRE_FIXED_64:
            decoded = stream.read(8)
            raw += decoded
        elif wire_type == WIRE_LEN_DELIM:
            length, r = load_varint(stream)
            decoded = stream.read(length)
            raw += r
            raw += decoded
        elif wire_type == WIRE_FIXED_32:
            decoded = stream.read(4)
            raw += decoded

        yield ParsedField(number=number, wire_type=wire_type, value=decoded, raw=raw)




class ProtoClassMetadata:
    __slots__ = (
        "oneof_group_by_field",
        "oneof_field_by_group",
        "default_gen",
        "cls_by_field",
        "field_name_by_number",
        "meta_by_field_name",
        "sorted_field_names",
    )

    oneof_group_by_field: Dict[str, str]
    oneof_field_by_group: Dict[str, Set[dataclasses.Field]]
    field_name_by_number: Dict[int, str]
    meta_by_field_name: Dict[str, FieldMetadata]
    sorted_field_names: Tuple[str, ...]
    default_gen: Dict[str, Callable[[], Any]]
    cls_by_field: Dict[str, Type]

    def __init__(self, cls: Type["Message"]):
        by_field = {}
        by_group: Dict[str, Set] = {}
        by_field_name = {}
        by_field_number = {}

        fields = dataclasses.fields(cls)
        for field in fields:
            meta = FieldMetadata.get(field)

            if meta.group:
                # This is part of a one-of group.
                by_field[field.name] = meta.group

                by_group.setdefault(meta.group, set()).add(field)

            by_field_name[field.name] = meta
            by_field_number[meta.number] = field.name

        self.oneof_group_by_field = by_field
        self.oneof_field_by_group = by_group
        self.field_name_by_number = by_field_number
        self.meta_by_field_name = by_field_name
        self.sorted_field_names = tuple(
            by_field_number[number] for number in sorted(by_field_number)
        )
        self.default_gen = self._get_default_gen(cls, fields)
        self.cls_by_field = self._get_cls_by_field(cls, fields)




class Message(ABC):
    """
    The base class for protobuf messages, all generated messages will inherit from
    this. This class registers the message fields which are used by the serializers and
    parsers to go between the Python, binary and JSON representations of the message.

    .. container:: operations

        .. describe:: bytes(x)

            Calls :meth:`__bytes__`.

        .. describe:: bool(x)

            Calls :meth:`__bool__`.
    """

    _serialized_on_wire: bool
    _unknown_fields: bytes
    _group_current: Dict[str, str]
    _betterproto_meta: ClassVar[ProtoClassMetadata]

    def __post_init__(self) -> None:
        # Keep track of whether every field was default
        all_sentinel = True

        # Set current field of each group after `__init__` has already been run.
        group_current: Dict[str, Optional[str]] = {}
        for field_name, meta in self._betterproto.meta_by_field_name.items():
            if meta.group:
                group_current.setdefault(meta.group)

            value = self.__raw_get(field_name)
            if value is not PLACEHOLDER and not (meta.optional and value is None):
                # Found a non-sentinel value
                all_sentinel = False

                if meta.group:
                    # This was set, so make it the selected value of the one-of.
                    group_current[meta.group] = field_name

        # Now that all the defaults are set, reset it!
        self.__dict__["_serialized_on_wire"] = not all_sentinel
        self.__dict__["_unknown_fields"] = b""
        self.__dict__["_group_current"] = group_current


    def __eq__(self, other) -> bool:
        if type(self) is not type(other):
            return NotImplemented

        for field_name in self._betterproto.meta_by_field_name:
            self_val = self.__raw_get(field_name)
            other_val = other.__raw_get(field_name)
            if self_val is PLACEHOLDER:
                if other_val is PLACEHOLDER:
                    continue
                self_val = self._get_field_default(field_name)
            elif other_val is PLACEHOLDER:
                other_val = other._get_field_default(field_name)

            if self_val != other_val:
                # We consider two nan values to be the same for the
                # purposes of comparing messages (otherwise a message
                # is not equal to itself)
                if (
                    isinstance(self_val, float)
                    and isinstance(other_val, float)
                    and math.isnan(self_val)
                    and math.isnan(other_val)
                ):
                    continue
                else:
                    return False

        return True

    def __repr__(self) -> str:
        parts = [
            f"{field_name}={value!r}"
            for field_name in self._betterproto.sorted_field_names
            for value in (self.__raw_get(field_name),)
            if value is not PLACEHOLDER
        ]
        return f"{self.__class__.__name__}({', '.join(parts)})"

    def __rich_repr__(self) -> Iterable[Tuple[str, Any, Any]]:
        for field_name in self._betterproto.sorted_field_names:
            yield field_name, self.__raw_get(field_name), PLACEHOLDER

    if not TYPE_CHECKING:

        def __getattribute__(self, name: str) -> Any:
            """
            Lazily initialize default values to avoid infinite recursion for recursive
            message types.
            Raise :class:`AttributeError` on attempts to access unset ``oneof`` fields.
            """
            try:
                group_current = super().__getattribute__("_group_current")
            except AttributeError:
                pass
            else:
                if name not in {"__class__", "_betterproto"}:
                    group = self._betterproto.oneof_group_by_field.get(name)
                    if group is not None and group_current[group] != name:
                        if sys.version_info < (3, 10):
                            raise AttributeError(
                                f"{group!r} is set to {group_current[group]!r}, not {name!r}"
                            )
                        else:
                            raise AttributeError(
                                f"{group!r} is set to {group_current[group]!r}, not {name!r}",
                                name=name,
                                obj=self,
                            )

            value = super().__getattribute__(name)
            if value is not PLACEHOLDER:
                return value

            value = self._get_field_default(name)
            super().__setattr__(name, value)
            return value

    def __setattr__(self, attr: str, value: Any) -> None:
        if (
            isinstance(value, Message)
            and hasattr(value, "_betterproto")
            and not value._betterproto.meta_by_field_name
        ):
            value._serialized_on_wire = True

        if attr != "_serialized_on_wire":
            # Track when a field has been set.
            self.__dict__["_serialized_on_wire"] = True

        if hasattr(self, "_group_current"):  # __post_init__ had already run
            if attr in self._betterproto.oneof_group_by_field:
                group = self._betterproto.oneof_group_by_field[attr]
                for field in self._betterproto.oneof_field_by_group[group]:
                    if field.name == attr:
                        self._group_current[group] = field.name
                    else:
                        super().__setattr__(field.name, PLACEHOLDER)

        super().__setattr__(attr, value)

    def __bool__(self) -> bool:
        """True if the Message has any fields with non-default values."""
        return any(
            self.__raw_get(field_name)
            not in (PLACEHOLDER, self._get_field_default(field_name))
            for field_name in self._betterproto.meta_by_field_name
        )

    def __deepcopy__(self: T, _: Any = {}) -> T:
        kwargs = {}
        for name in self._betterproto.sorted_field_names:
            value = self.__raw_get(name)
            if value is not PLACEHOLDER:
                kwargs[name] = deepcopy(value)
        return self.__class__(**kwargs)  # type: ignore

    def __copy__(self: T, _: Any = {}) -> T:
        kwargs = {}
        for name in self._betterproto.sorted_field_names:
            value = self.__raw_get(name)
            if value is not PLACEHOLDER:
                kwargs[name] = value
        return self.__class__(**kwargs)  # type: ignore

    @classproperty
    def _betterproto(cls: type[Self]) -> ProtoClassMetadata:  # type: ignore
        """
        Lazy initialize metadata for each protobuf class.
        It may be initialized multiple times in a multi-threaded environment,
        but that won't affect the correctness.
        """
        pass

    def dump(self, stream: "SupportsWrite[bytes]", delimit: bool = False) -> None:
        """
        Dumps the binary encoded Protobuf message to the stream.

        Parameters
        -----------
        stream: :class:`BinaryIO`
            The stream to dump the message to.
        delimit:
            Whether to prefix the message with a varint declaring its size.
        """
        pass

    def __bytes__(self) -> bytes:
        """
        Get the binary encoded Protobuf representation of this message instance.
        """
        with BytesIO() as stream:
            self.dump(stream)
            return stream.getvalue()

    def __len__(self) -> int:
        """
        Get the size of the encoded Protobuf representation of this message instance.
        """
        size = 0
        for field_name, meta in self._betterproto.meta_by_field_name.items():
            try:
                value = getattr(self, field_name)
            except AttributeError:
                continue

            if value is None:
                # Optional items should be skipped. This is used for the Google
                # wrapper types and proto3 field presence/optional fields.
                continue

            # Being selected in a group means this field is the one that is
            # currently set in a `oneof` group, so it must be serialized even
            # if the value is the default zero value.
            #
            # Note that proto3 field presence/optional fields are put in a
            # synthetic single-item oneof by protoc, which helps us ensure we
            # send the value even if the value is the default zero value.
            selected_in_group = bool(meta.group)

            # Empty messages can still be sent on the wire if they were
            # set (or received empty).
            serialize_empty = isinstance(value, Message) and value._serialized_on_wire

            include_default_value_for_oneof = self._include_default_value_for_oneof(
                field_name=field_name, meta=meta
            )

            if value == self._get_field_default(field_name) and not (
                selected_in_group or serialize_empty or include_default_value_for_oneof
            ):
                # Default (zero) values are not serialized. Two exceptions are
                # if this is the selected oneof item or if we know we have to
                # serialize an empty message (i.e. zero value was explicitly
                # set by the user).
                continue

            if isinstance(value, list):
                if meta.proto_type in PACKED_TYPES:
                    # Packed lists look like a length-delimited field. First,
                    # preprocess/encode each value into a buffer and then
                    # treat it like a field of raw bytes.
                    buf = bytearray()
                    for item in value:
                        buf += _preprocess_single(meta.proto_type, "", item)
                    size += _len_single(meta.number, TYPE_BYTES, buf)
                else:
                    for item in value:
                        size += (
                            _len_single(
                                meta.number,
                                meta.proto_type,
                                item,
                                wraps=meta.wraps or "",
                                serialize_empty=True,
                            )
                            # if it's an empty message it still needs to be represented
                            # as an item in the repeated list
                            or 2
                        )

            elif isinstance(value, dict):
                for k, v in value.items():
                    assert meta.map_types
                    sk = _serialize_single(1, meta.map_types[0], k)
                    sv = _serialize_single(2, meta.map_types[1], v)
                    size += _len_single(meta.number, meta.proto_type, sk + sv)
            else:
                # If we have an empty string and we're including the default value for
                # a oneof, make sure we serialize it. This ensures that the byte string
                # output isn't simply an empty string. This also ensures that round trip
                # serialization will keep `which_one_of` calls consistent.
                if (
                    isinstance(value, str)
                    and value == ""
                    and include_default_value_for_oneof
                ):
                    serialize_empty = True

                size += _len_single(
                    meta.number,
                    meta.proto_type,
                    value,
                    serialize_empty=serialize_empty or bool(selected_in_group),
                    wraps=meta.wraps or "",
                )

        size += len(self._unknown_fields)
        return size

    # For compatibility with other libraries
    def SerializeToString(self: T) -> bytes:
        """
        Get the binary encoded Protobuf representation of this message instance.

        .. note::
            This is a method for compatibility with other libraries,
            you should really use ``bytes(x)``.

        Returns
        --------
        :class:`bytes`
            The binary encoded Protobuf representation of this message instance
        """
        return bytes(self)

    def __getstate__(self) -> bytes:
        return bytes(self)

    def __setstate__(self: T, pickled_bytes: bytes) -> T:
        return self.parse(pickled_bytes)

    def __reduce__(self) -> Tuple[Any, ...]:
        return (self.__class__.FromString, (bytes(self),))



    @classmethod
    def _cls_for(cls, field: dataclasses.Field, index: int = 0) -> Type:
        """Get the message class for a field from the type hints."""
        pass

    def _get_field_default(self, field_name: str) -> Any:
        with warnings.catch_warnings():
            # ignore warnings when initialising deprecated field defaults
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            return self._betterproto.default_gen[field_name]()


    def _postprocess_single(
        self, wire_type: int, meta: FieldMetadata, field_name: str, value: Any
    ) -> Any:
        """Adjusts values after parsing."""
        if wire_type == WIRE_VARINT:
            if meta.proto_type in (TYPE_INT32, TYPE_INT64):
                bits = int(meta.proto_type[3:])
                value = value & ((1 << bits) - 1)
                signbit = 1 << (bits - 1)
                value = int((value ^ signbit) - signbit)
            elif meta.proto_type in (TYPE_SINT32, TYPE_SINT64):
                # Undo zig-zag encoding
                value = (value >> 1) ^ (-(value & 1))
            elif meta.proto_type == TYPE_BOOL:
                # Booleans use a varint encoding, so convert it to true/false.
                value = value > 0
            elif meta.proto_type == TYPE_ENUM:
                # Convert enum ints to python enum instances
                value = self._betterproto.cls_by_field[field_name].try_value(value)
        elif wire_type in (WIRE_FIXED_32, WIRE_FIXED_64):
            fmt = _pack_fmt(meta.proto_type)
            value = struct.unpack(fmt, value)[0]
        elif wire_type == WIRE_LEN_DELIM:
            if meta.proto_type == TYPE_STRING:
                value = str(value, "utf-8")
            elif meta.proto_type == TYPE_MESSAGE:
                cls = self._betterproto.cls_by_field[field_name]

                if cls == datetime:
                    value = _Timestamp().parse(value).to_datetime()
                elif cls == timedelta:
                    value = _Duration().parse(value).to_timedelta()
                elif meta.wraps:
                    # This is a Google wrapper value message around a single
                    # scalar type.
                    value = _get_wrapper(meta.wraps)().parse(value).value
                else:
                    value = cls().parse(value)
                    value._serialized_on_wire = True
            elif meta.proto_type == TYPE_MAP:
                value = self._betterproto.cls_by_field[field_name]().parse(value)

        return value


    def load(
        self: T,
        stream: "SupportsRead[bytes]",
        size: Optional[int] = None,
    ) -> T:
        """
        Load the binary encoded Protobuf from a stream into this message instance. This
        returns the instance itself and is therefore assignable and chainable.

        Parameters
        -----------
        stream: :class:`bytes`
            The stream to load the message from.
        size: :class:`Optional[int]`
            The size of the message in the stream.
            Reads stream until EOF if ``None`` is given.
            Reads based on a size delimiter prefix varint if SIZE_DELIMITED is given.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        # If the message is delimited, parse the message delimiter
        if size == SIZE_DELIMITED:
            size, _ = load_varint(stream)

        # Got some data over the wire
        self._serialized_on_wire = True
        proto_meta = self._betterproto
        read = 0
        for parsed in load_fields(stream):
            field_name = proto_meta.field_name_by_number.get(parsed.number)
            if not field_name:
                self._unknown_fields += parsed.raw
                continue

            meta = proto_meta.meta_by_field_name[field_name]

            value: Any
            if parsed.wire_type == WIRE_LEN_DELIM and meta.proto_type in PACKED_TYPES:
                # This is a packed repeated field.
                pos = 0
                value = []
                while pos < len(parsed.value):
                    if meta.proto_type in (TYPE_FLOAT, TYPE_FIXED32, TYPE_SFIXED32):
                        decoded, pos = parsed.value[pos : pos + 4], pos + 4
                        wire_type = WIRE_FIXED_32
                    elif meta.proto_type in (TYPE_DOUBLE, TYPE_FIXED64, TYPE_SFIXED64):
                        decoded, pos = parsed.value[pos : pos + 8], pos + 8
                        wire_type = WIRE_FIXED_64
                    else:
                        decoded, pos = decode_varint(parsed.value, pos)
                        wire_type = WIRE_VARINT
                    decoded = self._postprocess_single(
                        wire_type, meta, field_name, decoded
                    )
                    value.append(decoded)
            else:
                value = self._postprocess_single(
                    parsed.wire_type, meta, field_name, parsed.value
                )

            try:
                current = getattr(self, field_name)
            except AttributeError:
                current = self._get_field_default(field_name)
                setattr(self, field_name, current)

            if meta.proto_type == TYPE_MAP:
                # Value represents a single key/value pair entry in the map.
                current[value.key] = value.value
            elif isinstance(current, list) and not isinstance(value, list):
                current.append(value)
            else:
                setattr(self, field_name, value)

            # If we have now loaded the expected length of the message, stop
            if size is not None:
                prev = read
                read += len(parsed.raw)
                if read == size:
                    break
                elif read > size:
                    raise ValueError(
                        f"Expected message of size {size}, can only read "
                        f"either {prev} or {read} bytes - there is no "
                        "message of the expected size in the stream."
                    )

        if size is not None and read < size:
            raise ValueError(
                f"Expected message of size {size}, but was only able to "
                f"read {read} bytes - the stream may have ended too soon,"
                " or the expected size may have been incorrect."
            )

        return self

    def parse(self: T, data: bytes) -> T:
        """
        Parse the binary encoded Protobuf into this message instance. This
        returns the instance itself and is therefore assignable and chainable.

        Parameters
        -----------
        data: :class:`bytes`
            The data to parse the message from.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        with BytesIO(data) as stream:
            return self.load(stream)

    # For compatibility with other libraries.
    @classmethod
    def FromString(cls: Type[T], data: bytes) -> T:
        """
        Parse the binary encoded Protobuf into this message instance. This
        returns the instance itself and is therefore assignable and chainable.

        .. note::
            This is a method for compatibility with other libraries,
            you should really use :meth:`parse`.


        Parameters
        -----------
        data: :class:`bytes`
            The data to parse the protobuf from.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        pass

    def to_dict(
        self, casing: Casing = Casing.CAMEL, include_default_values: bool = False
    ) -> Dict[str, Any]:
        """
        Returns a JSON serializable dict representation of this object.

        Parameters
        -----------
        casing: :class:`Casing`
            The casing to use for key values. Default is :attr:`Casing.CAMEL` for
            compatibility purposes.
        include_default_values: :class:`bool`
            If ``True`` will include the default values of fields. Default is ``False``.
            E.g. an ``int32`` field will be included with a value of ``0`` if this is
            set to ``True``, otherwise this would be ignored.

        Returns
        --------
        Dict[:class:`str`, Any]
            The JSON serializable dict representation of this object.
        """
        pass

    @classmethod
    def _from_dict_init(cls, mapping: Mapping[str, Any]) -> Mapping[str, Any]:
        init_kwargs: Dict[str, Any] = {}
        for key, value in mapping.items():
            field_name = safe_snake_case(key)
            try:
                meta = cls._betterproto.meta_by_field_name[field_name]
            except KeyError:
                continue
            if value is None:
                continue

            if meta.proto_type == TYPE_MESSAGE:
                sub_cls = cls._betterproto.cls_by_field[field_name]
                if sub_cls == datetime:
                    value = (
                        [isoparse(item) for item in value]
                        if isinstance(value, list)
                        else isoparse(value)
                    )
                elif sub_cls == timedelta:
                    value = (
                        [timedelta(seconds=float(item[:-1])) for item in value]
                        if isinstance(value, list)
                        else timedelta(seconds=float(value[:-1]))
                    )
                elif not meta.wraps:
                    value = (
                        [sub_cls.from_dict(item) for item in value]
                        if isinstance(value, list)
                        else sub_cls.from_dict(value)
                    )
            elif meta.map_types and meta.map_types[1] == TYPE_MESSAGE:
                sub_cls = cls._betterproto.cls_by_field[f"{field_name}.value"]
                value = {k: sub_cls.from_dict(v) for k, v in value.items()}
            else:
                if meta.proto_type in INT_64_TYPES:
                    value = (
                        [int(n) for n in value]
                        if isinstance(value, list)
                        else int(value)
                    )
                elif meta.proto_type == TYPE_BYTES:
                    value = (
                        [b64decode(n) for n in value]
                        if isinstance(value, list)
                        else b64decode(value)
                    )
                elif meta.proto_type == TYPE_ENUM:
                    enum_cls = cls._betterproto.cls_by_field[field_name]
                    if isinstance(value, list):
                        value = [enum_cls.from_string(e) for e in value]
                    elif isinstance(value, str):
                        value = enum_cls.from_string(value)
                elif meta.proto_type in (TYPE_FLOAT, TYPE_DOUBLE):
                    value = (
                        [_parse_float(n) for n in value]
                        if isinstance(value, list)
                        else _parse_float(value)
                    )

            init_kwargs[field_name] = value
        return init_kwargs

    @hybridmethod
    def from_dict(cls: type[Self], value: Mapping[str, Any]) -> Self:  # type: ignore
        """
        Parse the key/value pairs into the a new message instance.

        Parameters
        -----------
        value: Dict[:class:`str`, Any]
            The dictionary to parse from.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        self = cls(**cls._from_dict_init(value))
        self._serialized_on_wire = True
        return self

    @from_dict.instancemethod
    def from_dict(self, value: Mapping[str, Any]) -> Self:
        """
        Parse the key/value pairs into the current message instance. This returns the
        instance itself and is therefore assignable and chainable.

        Parameters
        -----------
        value: Dict[:class:`str`, Any]
            The dictionary to parse from.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        self._serialized_on_wire = True
        for field, value in self._from_dict_init(value).items():
            setattr(self, field, value)
        return self

    def to_json(
        self,
        indent: Union[None, int, str] = None,
        include_default_values: bool = False,
        casing: Casing = Casing.CAMEL,
    ) -> str:
        """A helper function to parse the message instance into its JSON
        representation.

        This is equivalent to::

            json.dumps(message.to_dict(), indent=indent)

        Parameters
        -----------
        indent: Optional[Union[:class:`int`, :class:`str`]]
            The indent to pass to :func:`json.dumps`.

        include_default_values: :class:`bool`
            If ``True`` will include the default values of fields. Default is ``False``.
            E.g. an ``int32`` field will be included with a value of ``0`` if this is
            set to ``True``, otherwise this would be ignored.

        casing: :class:`Casing`
            The casing to use for key values. Default is :attr:`Casing.CAMEL` for
            compatibility purposes.

        Returns
        --------
        :class:`str`
            The JSON representation of the message.
        """
        pass

    def from_json(self: T, value: Union[str, bytes]) -> T:
        """A helper function to return the message instance from its JSON
        representation. This returns the instance itself and is therefore assignable
        and chainable.

        This is equivalent to::

            return message.from_dict(json.loads(value))

        Parameters
        -----------
        value: Union[:class:`str`, :class:`bytes`]
            The value to pass to :func:`json.loads`.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        pass

    def to_pydict(
        self, casing: Casing = Casing.CAMEL, include_default_values: bool = False
    ) -> Dict[str, Any]:
        """
        Returns a python dict representation of this object.

        Parameters
        -----------
        casing: :class:`Casing`
            The casing to use for key values. Default is :attr:`Casing.CAMEL` for
            compatibility purposes.
        include_default_values: :class:`bool`
            If ``True`` will include the default values of fields. Default is ``False``.
            E.g. an ``int32`` field will be included with a value of ``0`` if this is
            set to ``True``, otherwise this would be ignored.

        Returns
        --------
        Dict[:class:`str`, Any]
            The python dict representation of this object.
        """
        pass

    def from_pydict(self: T, value: Mapping[str, Any]) -> T:
        """
        Parse the key/value pairs into the current message instance. This returns the
        instance itself and is therefore assignable and chainable.

        Parameters
        -----------
        value: Dict[:class:`str`, Any]
            The dictionary to parse from.

        Returns
        --------
        :class:`Message`
            The initialized message.
        """
        pass

    def is_set(self, name: str) -> bool:
        """
        Check if field with the given name has been set.

        Parameters
        -----------
        name: :class:`str`
            The name of the field to check for.

        Returns
        --------
        :class:`bool`
            `True` if field has been set, otherwise `False`.
        """
        pass



Message.__annotations__ = {}  # HACK to avoid typing.get_type_hints breaking :)

# monkey patch (de-)serialization functions of class `Message`
# with functions from `betterproto-rust-codec` if available
try:
    import betterproto_rust_codec



    Message.parse = __parse_patch
    Message.__bytes__ = __bytes_patch
except ModuleNotFoundError:
    pass


def serialized_on_wire(message: Message) -> bool:
    """
    If this message was or should be serialized on the wire. This can be used to detect
    presence (e.g. optional wrapper message) and is used internally during
    parsing/serialization.

    Returns
    --------
    :class:`bool`
        Whether this message was or should be serialized on the wire.
    """
    pass


def which_one_of(message: Message, group_name: str) -> Tuple[str, Optional[Any]]:
    """
    Return the name and value of a message's one-of field group.

    Returns
    --------
    Tuple[:class:`str`, Any]
        The field name and the value for that field.
    """
    field_name = message._group_current.get(group_name)
    if not field_name:
        return "", None
    return field_name, getattr(message, field_name)


# Circular import workaround: google.protobuf depends on base classes defined above.
from .lib.google.protobuf import (  # noqa
    BoolValue,
    BytesValue,
    DoubleValue,
    Duration,
    EnumValue,
    FloatValue,
    Int32Value,
    Int64Value,
    StringValue,
    Timestamp,
    UInt32Value,
    UInt64Value,
)


class _Duration(Duration):

    def to_timedelta(self) -> timedelta:
        return timedelta(seconds=self.seconds, microseconds=self.nanos / 1e3)



class _Timestamp(Timestamp):

    def to_datetime(self) -> datetime:
        # datetime.fromtimestamp() expects a timestamp in seconds, not microseconds
        # if we pass it as a floating point number, we will run into rounding errors
        # see also #407
        offset = timedelta(seconds=self.seconds, microseconds=self.nanos // 1000)
        return DATETIME_ZERO + offset



def _get_wrapper(proto_type: str) -> Type:
    """Get the wrapper message class for a wrapped type."""

    # TODO: include ListValue and NullValue?
    return {
        TYPE_BOOL: BoolValue,
        TYPE_BYTES: BytesValue,
        TYPE_DOUBLE: DoubleValue,
        TYPE_FLOAT: FloatValue,
        TYPE_ENUM: EnumValue,
        TYPE_INT32: Int32Value,
        TYPE_INT64: Int64Value,
        TYPE_STRING: StringValue,
        TYPE_UINT32: UInt32Value,
        TYPE_UINT64: UInt64Value,
    }[proto_type]
