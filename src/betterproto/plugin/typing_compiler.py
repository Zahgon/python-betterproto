import abc
from collections import defaultdict
from dataclasses import (
    dataclass,
    field,
)
from typing import (
    Dict,
    Iterator,
    Optional,
    Set,
)


class TypingCompiler(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def optional(self, type: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def list(self, type: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def dict(self, key: str, value: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def union(self, *types: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def iterable(self, type: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def async_iterable(self, type: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def async_iterator(self, type: str) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def imports(self) -> Dict[str, Optional[Set[str]]]:
        """
        Returns either the direct import as a key with none as value, or a set of
        values to import from the key.
        """
        raise NotImplementedError()



@dataclass
class DirectImportTypingCompiler(TypingCompiler):
    _imports: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def optional(self, type: str) -> str:
        self._imports["typing"].add("Optional")
        return f"Optional[{type}]"



    def union(self, *types: str) -> str:
        self._imports["typing"].add("Union")
        return f"Union[{', '.join(types)}]"






@dataclass
class TypingImportTypingCompiler(TypingCompiler):
    _imported: bool = False

    def optional(self, type: str) -> str:
        self._imported = True
        return f"typing.Optional[{type}]"



    def union(self, *types: str) -> str:
        self._imported = True
        return f"typing.Union[{', '.join(types)}]"






@dataclass
class NoTyping310TypingCompiler(TypingCompiler):
    _imports: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    @staticmethod
    def _fmt(type: str) -> str:  # for now this is necessary till 3.14
        if type.startswith('"'):
            return type[1:-1]
        return type

    def optional(self, type: str) -> str:
        return f'"{self._fmt(type)} | None"'



    def union(self, *types: str) -> str:
        return f'"{" | ".join(map(self._fmt, types))}"'




