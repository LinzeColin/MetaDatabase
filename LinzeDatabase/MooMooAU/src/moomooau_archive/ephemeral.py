"""In-memory plaintext arena with unconditional zeroing on every exit path."""

from __future__ import annotations

from types import TracebackType


class EphemeralPlaintextError(RuntimeError):
    pass


class EphemeralPlaintextArena:
    """Own mutable plaintext buffers; never exposes a filesystem persistence API."""

    __slots__ = ("_buffers", "_closed", "_allocated_bytes")

    def __init__(self) -> None:
        self._buffers: list[bytearray] = []
        self._closed = False
        self._allocated_bytes = 0

    def __repr__(self) -> str:
        return (
            "EphemeralPlaintextArena(buffers=<redacted>, "
            f"closed={self._closed}, outstanding_bytes=<redacted>)"
        )

    def __enter__(self) -> EphemeralPlaintextArena:
        if self._closed:
            raise EphemeralPlaintextError("closed plaintext arena cannot be reused")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def outstanding_bytes(self) -> int:
        return 0 if self._closed else sum(len(item) for item in self._buffers)

    @property
    def allocated_bytes(self) -> int:
        return self._allocated_bytes

    def allocate(self, value: bytes) -> memoryview:
        if self._closed or not value:
            raise EphemeralPlaintextError("plaintext allocation is not permitted")
        buffer = bytearray(value)
        self._buffers.append(buffer)
        self._allocated_bytes += len(buffer)
        return memoryview(buffer)

    def close(self) -> None:
        if self._closed:
            return
        for buffer in self._buffers:
            for index in range(len(buffer)):
                buffer[index] = 0
        self._buffers.clear()
        self._closed = True
