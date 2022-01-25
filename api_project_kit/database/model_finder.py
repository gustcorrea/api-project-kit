import importlib
import inspect
from pathlib import Path
from typing import Any, Generic, Iterable, Optional, TypeVar

from sqlalchemy import MetaData, Table

T = TypeVar("T", bound=object)


def get_import(value: str):
    if value.startswith("_"):
        return f'{value} as {value.removeprefix("_")}'
    return value


def get_relative_from(key: str):
    return key.rsplit(".", 1)[-1]


class _ModuleMapping(Generic[T]):
    def __init__(self) -> None:
        self._mapping = {}

    def __setitem__(self, key: str, val: tuple[str, Any]):
        import_source, value = val
        if isinstance(self._mapping.get(import_source), dict):
            self._mapping[import_source][key] = val
        else:
            self._mapping[import_source] = {key: value}

    def __getitem__(self, key: str) -> dict[str, T]:
        return self._mapping.__getitem__(key)

    def values(self) -> Iterable[dict[str, T]]:
        return self._mapping.values()

    def keys(self) -> Iterable[str]:
        return self._mapping.keys()

    def as_dict(self) -> dict[str, dict[str, T]]:
        return self._mapping.copy()

    def _generate_absolute_imports(self):
        for key in self.keys():
            yield "from {} import {}".format(
                key, ", ".join(get_import(value) for value in self[key].keys())
            )

    def _generate_relative_imports(self):
        for key in self.keys():
            yield "from .{} import {}".format(
                get_relative_from(key),
                ", ".join(get_import(value) for value in self[key].keys()),
            )

    def generate_import_string(self, relative: bool = True):
        if relative:
            return list(self._generate_relative_imports())
        return list(self._generate_absolute_imports())

    def all_keys(self):
        for value in self.values():
            yield from value.keys()


class ModelFinder(Generic[T]):
    def __init__(
        self,
        path: Path,
        root: Path = None,
    ):
        self.path = path
        self.mapping = _ModuleMapping()
        self.root = root or path
        self.child_of = Table

    def get_findings(self) -> _ModuleMapping[T]:
        return self.mapping

    def find(self):
        if self.path.is_dir():
            self.find_from_dir()
        else:
            self.find_from_file()

    def find_from_dir(self, path: Optional[Path] = None):
        if path is None:
            path = self.path
        if "pycache" in path.name or ".pyc" in path.name:
            return
        for item in path.iterdir():
            if item.is_dir():
                self.find_from_dir(item)
                continue
            if ".py" in path.name and path.name != "__init__.py":
                continue
            self.find_from_file(item)

    def _save_child_of(self, name: str, import_source: str, obj: Any):
        if inspect.isclass(obj) and (
            issubclass(obj, self.child_of)
            and name != self.child_of.__qualname__
            and obj.__module__ == import_source
        ):
            self.mapping[name] = (import_source, obj)

    def find_from_file(self, path: Optional[Path] = None):
        if path is None:
            path = self.path
        if not path.is_file():
            return
        if "__init__" in path.name:
            return
        import_source = self.get_import(path)
        mod = importlib.import_module(import_source)
        for name, obj in inspect.getmembers(mod):
            self._save_child_of(name, import_source, obj)

    def get_import(self, target: Path):
        target_str = target.as_posix()
        return (
            target_str.replace(self.root.as_posix(), self.root.name)
            .replace("/", ".")
            .replace(".py", "")
        )

    def preload_metadata(self, metadata: MetaData):
        self.find()
        return metadata
