"""Streaming official-age boundary that never writes plaintext payloads to disk."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from .adapters import is_age_envelope as is_age_envelope

_AGE_RECIPIENT = re.compile(r"^age1[0-9a-z]{58}$")


class AgeStreamUnavailable(RuntimeError):
    pass


class AgeStreamError(RuntimeError):
    pass


class OfficialAgeStream:
    """Pump bytes through the official age CLI using bounded chunks and pipes."""

    def __init__(self, age_binary: str | None = None, *, chunk_size: int = 64 * 1024) -> None:
        resolved = age_binary or shutil.which("age")
        if resolved is None:
            raise AgeStreamUnavailable("official age binary is required")
        if chunk_size < 4096 or chunk_size > 1024 * 1024:
            raise ValueError("age stream chunk size is outside the allowed range")
        self._age_binary = resolved
        self._chunk_size = chunk_size

    def encrypt_stream(self, recipient: str, source: BinaryIO, sink: BinaryIO) -> None:
        if _AGE_RECIPIENT.fullmatch(recipient) is None:
            raise AgeStreamError("age recipient is invalid")
        self._run(
            (self._age_binary, "--encrypt", "--recipient", recipient),
            source,
            sink,
        )

    def decrypt_stream(
        self,
        identity_path: Path,
        source: BinaryIO,
        sink: BinaryIO,
        *,
        allowed_tmpfs_roots: Iterable[Path] = (Path("/dev/shm"),),
    ) -> None:
        identity = _require_protected_identity(identity_path, allowed_tmpfs_roots)
        self._run(
            (self._age_binary, "--decrypt", "--identity", os.fspath(identity)),
            source,
            sink,
        )

    def _run(self, arguments: tuple[str, ...], source: BinaryIO, sink: BinaryIO) -> None:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            process.wait()
            raise AgeStreamError("age pipe setup failed")
        process_stdin = process.stdin
        process_stdout = process.stdout
        process_stderr = process.stderr

        failures: list[BaseException] = []

        def feed_stdin() -> None:
            try:
                while True:
                    chunk = source.read(self._chunk_size)
                    if not chunk:
                        break
                    process_stdin.write(chunk)
            except BaseException as exc:  # propagate worker failures without diagnostics
                failures.append(exc)
                process.kill()
            finally:
                try:
                    process_stdin.close()
                except OSError:
                    pass

        def drain_stderr() -> None:
            try:
                while process_stderr.read(self._chunk_size):
                    pass
            except BaseException as exc:
                failures.append(exc)
                process.kill()

        input_thread = threading.Thread(target=feed_stdin, name="moomooau-age-input")
        error_thread = threading.Thread(target=drain_stderr, name="moomooau-age-stderr")
        input_thread.start()
        error_thread.start()
        main_failure: BaseException | None = None
        try:
            while True:
                chunk = process_stdout.read(self._chunk_size)
                if not chunk:
                    break
                sink.write(chunk)
        except BaseException as exc:
            main_failure = exc
            process.kill()
        finally:
            process_stdout.close()
            return_code = process.wait()
            input_thread.join()
            error_thread.join()
            process_stderr.close()
        if isinstance(main_failure, (KeyboardInterrupt, SystemExit)):
            raise main_failure
        if main_failure is not None or failures or return_code != 0:
            raise AgeStreamError("age streaming operation failed with redacted diagnostics")


def _require_protected_identity(identity_path: Path, roots: Iterable[Path]) -> Path:
    if identity_path.is_symlink():
        raise AgeStreamError("age identity must not be a symlink")
    try:
        identity = identity_path.resolve(strict=True)
    except OSError as exc:
        raise AgeStreamError("age identity is unavailable") from exc
    if not identity.is_file() or identity.stat().st_mode & 0o077:
        raise AgeStreamError("age identity permissions are not private")
    resolved_roots: list[Path] = []
    for root in roots:
        try:
            resolved_roots.append(root.resolve(strict=True))
        except OSError:
            continue
    if not any(identity.is_relative_to(root) for root in resolved_roots):
        raise AgeStreamError("age identity is outside an approved tmpfs root")
    return identity
