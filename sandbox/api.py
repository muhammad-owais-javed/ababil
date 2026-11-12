import hmac
import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ["SANDBOX_TOKEN"]
PORT = 8001
MAX_OUTPUT = 20_000
MAX_TIMEOUT = 300
DESKTOP_ENV = {**os.environ, "DISPLAY": ":1", "DEBIAN_FRONTEND": "noninteractive"}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("sandbox")

# Commands running right now, by id, so they can be cancelled.
running: dict[str, subprocess.Popen] = {}
cancelled: set[str] = set()
running_lock = threading.Lock()


def record(event: str, **details) -> None:
    log.info(json.dumps({"event": event, **details}))


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return value[-MAX_OUTPUT:]


def kill_group(proc: subprocess.Popen) -> None:
    """Kill the command and everything it started. Each command has its own process group."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_command(command: str, timeout: int, command_id: str) -> dict:
    proc = subprocess.Popen(
        ["bash", "-c", command],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=DESKTOP_ENV, start_new_session=True,
    )
    with running_lock:
        running[command_id] = proc
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group(proc)
        out, err = proc.communicate()
    finally:
        with running_lock:
            running.pop(command_id, None)
            was_cancelled = command_id in cancelled
            cancelled.discard(command_id)
    stopped_early = timed_out or was_cancelled
    return {
        "exit_code": None if stopped_early else proc.returncode,
        "timed_out": timed_out,
        "cancelled": was_cancelled,
        "stdout": as_text(out),
        "stderr": as_text(err),
    }


def cancel_command(command_id: str) -> bool:
    with running_lock:
        proc = running.get(command_id)
        if proc is None:
            return False
        cancelled.add(command_id)
    kill_group(proc)
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # record() logs the actions instead

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-Sandbox-Token", ""), TOKEN)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("the body must be a JSON object")
        return data

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"status": "ok"})
        if not self._authorized():
            return self._json(401, {"error": "missing or wrong token"})
        if self.path == "/screenshot":
            return self._screenshot()
        self._json(404, {"error": "unknown path"})

    def do_POST(self):
        if not self._authorized():
            return self._json(401, {"error": "missing or wrong token"})
        if self.path == "/exec":
            return self._exec()
        if self.path == "/cancel":
            return self._cancel()
        self._json(404, {"error": "unknown path"})

    def _exec(self):
        try:
            body = self._read_json()
            command = str(body.get("command", "")).strip()
            if not command:
                return self._json(400, {"error": "command is required"})
            timeout = min(int(body.get("timeout", 60)), MAX_TIMEOUT)
            command_id = str(body.get("id") or uuid.uuid4().hex)[:64]
        except (ValueError, TypeError) as error:
            return self._json(400, {"error": f"bad request: {error}"})

        record("exec", id=command_id, command=command, timeout=timeout)
        try:
            result = run_command(command, timeout, command_id)
        except Exception as error:
            record("error", id=command_id, error=str(error))
            return self._json(500, {"error": str(error)})
        record("exec_done", id=command_id, exit_code=result["exit_code"],
               cancelled=result["cancelled"], timed_out=result["timed_out"])
        self._json(200, result)

    def _cancel(self):
        try:
            body = self._read_json()
        except ValueError as error:
            return self._json(400, {"error": f"bad request: {error}"})
        command_id = str(body.get("id", ""))
        if cancel_command(command_id):
            record("cancel", id=command_id)
            return self._json(200, {"cancelled": True})
        self._json(404, {"error": "no running command with that id"})

    def _screenshot(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            subprocess.run(["scrot", "-o", path], env=DESKTOP_ENV,
                           check=True, capture_output=True, timeout=15)
            with open(path, "rb") as f:
                data = f.read()
        finally:
            os.remove(path)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    record("started", port=PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()