"""Interactive control for tests that own the dummy executable and its pipes."""

import os
import subprocess
import threading
from collections import deque
from pathlib import Path
from time import monotonic
from typing import Callable, Mapping, Sequence


class DummyServerProcess:
    """Launch a dummy server, drain both pipes, and reap it on context exit."""

    def __init__(
        self,
        binary: str | Path,
        args: Sequence[str] = (),
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        transcript_lines: int = 200,
    ):
        if transcript_lines < 1:
            raise ValueError("transcript_lines must be positive")
        self._command = [str(Path(binary).resolve()), *args]
        self._cwd = cwd
        self._env = {"BSM_DUMMY_STARTUP_DELAY_MS": "0", **(env or {})}
        self._condition = threading.Condition()
        self._output: dict[str, deque[str]] = {
            stream: deque(maxlen=transcript_lines) for stream in ("stdout", "stderr")
        }
        self._transcript: deque[tuple[str, str]] = deque(maxlen=transcript_lines)
        self._closed: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._process: subprocess.Popen[str] | None = None

    def __enter__(self):
        if self._process is not None:
            raise RuntimeError("DummyServerProcess instances are single-use")
        self._process = subprocess.Popen(
            self._command,
            cwd=self._cwd,
            env={**os.environ, **self._env},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
        for stream in ("stdout", "stderr"):
            thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    @property
    def transcript(self) -> tuple[tuple[str, str], ...]:
        with self._condition:
            return tuple(self._transcript)

    def _require_process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise RuntimeError("Enter the process context before using it")
        return self._process

    def _read(self, stream: str) -> None:
        pipe = getattr(self._require_process(), stream)
        try:
            for raw in pipe:
                line = raw.rstrip("\r\n")
                with self._condition:
                    self._output[stream].append(line)
                    self._transcript.append((stream, line))
                    self._condition.notify_all()
        finally:
            with self._condition:
                self._closed.add(stream)
                self._condition.notify_all()

    def send(self, command: str) -> None:
        pipe = self._require_process().stdin
        assert pipe is not None
        pipe.write(command + "\n")
        pipe.flush()

    def wait_for_line(
        self,
        match: str | Callable[[str], bool],
        *,
        stream: str = "stdout",
        timeout: float = 5.0,
    ) -> str:
        """Consume lines through the first match, or raise with recent output."""
        self._require_process()
        predicate = match if callable(match) else lambda line: match in line
        deadline = monotonic() + timeout
        with self._condition:
            pending = self._output[stream]
            while True:
                while pending:
                    line = pending.popleft()
                    if predicate(line):
                        return line
                remaining = deadline - monotonic()
                if remaining <= 0 or stream in self._closed:
                    break
                self._condition.wait(remaining)
            reason = "pipe closed" if stream in self._closed else "deadline expired"
            raise TimeoutError(
                f"{stream} {reason} waiting for {match!r}: {list(self._transcript)!r}"
            )

    def wait(self, timeout: float = 5.0) -> int:
        return self._require_process().wait(timeout=timeout)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        process = self._require_process()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for thread in self._threads:
            thread.join(timeout=5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
