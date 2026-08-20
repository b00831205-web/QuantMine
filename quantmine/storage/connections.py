from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from sqlalchemy import Engine, create_engine
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

from os import environ

class ConnectionKind(StrEnum):
    """The resource type behind a named data connection"""
    SQLALCHEMY = 'sqlalchemy'
    PARQUET = 'parquet'

@dataclass(frozen=True)
class DataConnectionConfig:
    """Non-secret configuration for one named connection.

    The actual SQL DSN or filesystem root is read from the named environment
    variable at runtime, never persisted in a research-run record.
    """
    kind: ConnectionKind
    url_env: str| None = None
    root_env: str |None = None
    read_only: bool = True

    def __post_init__(self) -> None:
        if self.kind is ConnectionKind.SQLALCHEMY:
            if not self.url_env:
                raise ValueError('A SQLAlchemy connection requires url_env')
            if self.root_env is not None: #防止错配parquet路径
                raise ValueError(
                    'A SQLAlchemy connection must not define root_env'
                )
            return
        if self.kind is ConnectionKind.PARQUET:
                if not self.root_env:
                    raise ValueError("A Parquet connection requires root_env")
                if self.url_env is not None: #防止错配sql路径
                    raise ValueError("A Parquet connection must not define url_env")
                return
        raise ValueError(f'Unsupported connection kind: {self.kind!r}')

class ConnectionRegistry:
    """Resolve named SQLAlchemy or Parquet connections on demand"""

    def __init__(self, configs: Mapping[str, DataConnectionConfig]) -> None:
        self._configs = dict(configs)
        self._engines: dict[str, Any] = {}
        self._lock = Lock()

    @property
    def connection_refs(self) -> tuple[str, ...]:
        """Return configured connection aliases withoud exposing secrets"""

        return tuple(sorted(self._configs))

    def sqlalchemy_engine(self, connection_ref: str) -> Any:
        """Return a cached SQLAlchemy engine for a named SQL connection."""

        config = self._get_config(connection_ref)

        if config.kind is not ConnectionKind.SQLALCHEMY:
            raise ValueError(
                f"Connection {connection_ref!r} is {config.kind.value!r},"
                f'not a SQLAlchemy connection'
            )
        with self._lock:
            engine = self._engines.get(connection_ref)
            if engine is not None:
                return engine

            url = self._environment_value(
                env_name = config.url_env,
                connection_ref = connection_ref
            )

            try:
                from sqlalchemy import create_engine
            except ImportError as error:
                raise RuntimeError(
                    "SQLAlchemy support is not istalled."
                    "Install quantmine with its 'db' extra"
                ) from error
            engine = create_engine(url)
            self._engines[connection_ref] = engine
            return engine
    def parquet_root(self, connection_ref: str)->Path:
        """Return the configured root directory for a Parquet lake."""
        config = self._get_config(connection_ref)
        if config.kind is not ConnectionKind.PARQUET:
            raise ValueError(
                f"connction {connection_ref!r} is {config.kind.value!r},"
                "not a Parquet connection"
            )
        root = Path(
            self._environment_value(
                env_name = config.root_env,
                connection_ref = connection_ref
            )
        ).expanduser()

        if not root.is_dir():
            raise FileNotFoundError(
                f"Parquet root for connection {connection_ref!r}"
                f"does not exist or is not a directory: {root}"
            )
        return root

    def dispose(self) -> None:
        """Release all SQLAlchemy connection pools owned by this registry"""

        with self._lock:
            engines = tuple(self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine.dispose()

    def _get_config(self,connection_ref: str) -> DataConnectionConfig:
        try: 
            return self._configs[connection_ref]
        except KeyError as error:
            available = ",".join(self.connection_refs) or "<none>"
            raise KeyError(
                f"unknwon data connection {connection_ref!r};"
                f"available: {available}"
            ) from error

    @staticmethod
    def _environment_value(
        *,
        env_name: str | None,
        connection_ref: str
    ) -> str:
        if env_name is None:
            raise RuntimeError(
                f"Connection {connection_ref!r} has no environment variable"
            )
        value = environ.get(env_name)
        if not value:
            raise RuntimeError(
                f"Environment variable {env_name!r} for connection"
                f"{connection_ref!r} is not set"
            )
        return value


