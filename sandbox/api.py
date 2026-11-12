import hmac
import json
import logging
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ["SANDBOX_TOKEN"]
PORT = 8001
MAX_OUTPUT = 20_000
MAX_TIMEOUT = 300
DESKTOP_ENV = {**os.environ, "DISPLAY": ":1"}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("sandbox")


def record(event: str, **details) -> None:
    """One JSON line per action. This is the audit trail: docker logs sandbox-service."""
    log.info(json.dumps({"event": event, **details}))


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return value[-MAX_OUTPUT:]


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
        if self.path != "/exec":
            return self._json(404, {"error": "unknown path"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            command = str(body.get("command", "")).strip()
            if not command:
                return self._json(400, {"error": "command is required"})
            timeout = min(int(body.get("timeout", 60)), MAX_TIMEOUT)
            record("exec", command=command, timeout=timeout)
            result = self._exec(command, timeout)
        except Exception as error:
            record("error", error=str(error))
            return self._json(500, {"error": str(error)})
        self._json(200, result)

    def _exec(self, command: str, timeout: int) -> dict:
        try:
            proc = subprocess.run(
                ["bash", "-c", command],
                capture_output=True, text=True, timeout=timeout, env=DESKTOP_ENV,
            )
            return {"exit_code": proc.returncode, "timed_out": False,
                    "stdout": as_text(proc.stdout), "stderr": as_text(proc.stderr)}
        except subprocess.TimeoutExpired as expired:
            return {"exit_code": None, "timed_out": True,
                    "stdout": as_text(expired.stdout), "stderr": as_text(expired.stderr)}

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
        record("screenshot", bytes=len(data))
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    record("started", port=PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()