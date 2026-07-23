"""Redacted wrappers for credentials that must never enter diagnostics."""

from __future__ import annotations

from types import TracebackType


class SecretDestroyedError(RuntimeError):
    """Raised when code attempts to reuse a deliberately destroyed secret."""


class SecretBytes:
    """Mutable secret buffer with redacted representations and best-effort zeroing.

    Python cannot promise complete process-memory erasure because callers and libraries may
    create copies. This class only guarantees that its owned bytearray is overwritten.
    """

    __slots__ = ("_buffer", "_destroyed")

    def __init__(self, value: bytes | bytearray | memoryview) -> None:
        if not value:
            raise ValueError("secret value must not be empty")
        self._buffer = bytearray(value)
        self._destroyed = False

    def __repr__(self) -> str:
        return "SecretBytes(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    def __enter__(self) -> SecretBytes:
        self._require_active()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.destroy()

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def reveal(self) -> bytes:
        """Return a short-lived copy for an explicitly authorized boundary call."""

        self._require_active()
        return bytes(self._buffer)

    def destroy(self) -> None:
        if self._destroyed:
            return
        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        self._buffer.clear()
        self._destroyed = True

    def _require_active(self) -> None:
        if self._destroyed:
            raise SecretDestroyedError("secret has already been destroyed")


class SecretText:
    """UTF-8 text credential backed by a redacted mutable buffer."""

    __slots__ = ("_secret",)

    def __init__(self, value: str) -> None:
        if not value:
            raise ValueError("secret value must not be empty")
        self._secret = SecretBytes(value.encode("utf-8"))

    def __repr__(self) -> str:
        return "SecretText(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    @property
    def destroyed(self) -> bool:
        return self._secret.destroyed

    def reveal(self) -> str:
        return self._secret.reveal().decode("utf-8")

    def destroy(self) -> None:
        self._secret.destroy()
