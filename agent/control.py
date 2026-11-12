import threading


class StopControl:
    """Stop requests for one task.
    'after_step' halts when the current step ends.
    'now' also cancels the command that is running."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode: str | None = None
        self._command_id: str | None = None

    @property
    def mode(self) -> str | None:
        with self._lock:
            return self._mode

    def request(self, mode: str) -> tuple[bool, str | None]:
        """Returns (accepted, id of the running command to cancel, if any)."""
        if mode not in ("after_step", "now"):
            raise ValueError(f"unknown stop mode {mode!r}")
        with self._lock:
            if self._mode == "now" or (mode == "after_step" and self._mode is not None):
                return False, None
            self._mode = mode
            return True, (self._command_id if mode == "now" else None)

    def begin_command(self, command_id: str) -> bool:
        """Returns False if a 'now' stop was already requested, so no new command starts."""
        with self._lock:
            if self._mode == "now":
                return False
            self._command_id = command_id
            return True

    def end_command(self) -> None:
        with self._lock:
            self._command_id = None