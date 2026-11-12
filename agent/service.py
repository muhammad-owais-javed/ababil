import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from control import StopControl
from events import EventHub
from run import run
from sandbox import Sandbox

PORT = 8080
MAX_TASK = 2000
PAGE = Path(__file__).with_name("watch.html")
STOP_MODES = {"after_step", "now"}

hub = EventHub()
lock = threading.Lock()
state = {"status": "idle", "task": None, "stop_mode": None}
control: StopControl | None = None


def start_task(task: str) -> bool:
    global control
    with lock:
        if state["status"] == "running":
            return False
        control = StopControl()
        current = control
        state.update(status="running", task=task, stop_mode=None)
    hub.publish("task", task=task)

    def worker():
        ok, answer = False, ""
        try:
            ok, answer = run(task, hub.publish, current)
        except Exception as error:
            answer = f"agent error: {error}"
            hub.publish("error", message=answer)
        finally:
            with lock:
                state.update(status="done" if ok else "stopped")
            hub.publish("finished", ok=ok, answer=answer)

    threading.Thread(target=worker, daemon=True).start()
    return True


def request_stop(mode: str) -> bool:
    with lock:
        if state["status"] != "running" or control is None:
            return False
        accepted, command_id = control.request(mode)
        if not accepted:
            return False
        state["stop_mode"] = control.mode
    if command_id:
        try:
            Sandbox().cancel(command_id)
        except OSError as error:
            hub.publish("error", message=f"could not cancel the running command: {error}")
    hub.publish("stop_requested", mode=mode)
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("the body must be a JSON object")
        return data

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/state":
            with lock:
                self._json(200, dict(state))
        elif self.path == "/events":
            self._events()
        elif self.path.startswith("/screenshot"):
            self._screenshot()
        else:
            self._json(404, {"error": "unknown path"})

    def do_POST(self):
        if self.path == "/stop":
            try:
                mode = self._read_json().get("mode", "after_step")
            except ValueError:
                return self._json(400, {"error": 'send JSON like {"mode": "now"}'})
            if mode not in STOP_MODES:
                return self._json(400, {"error": "mode must be after_step or now"})
            if request_stop(mode):
                return self._json(202, {"status": "stop requested", "mode": mode})
            return self._json(409, {"error": "nothing to stop, or that stop was already requested"})

        if self.path != "/task":
            return self._json(404, {"error": "unknown path"})
        try:
            task = str(self._read_json().get("task", "")).strip()
        except ValueError:
            return self._json(400, {"error": 'send JSON like {"task": "..."}'})
        if not 0 < len(task) <= MAX_TASK:
            return self._json(400, {"error": f"task must be 1 to {MAX_TASK} characters"})
        if not start_task(task):
            return self._json(409, {"error": "a task is already running"})
        self._json(202, {"status": "started"})

    def _events(self):
        last_seen = int(self.headers.get("Last-Event-ID") or 0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        replay, live = hub.subscribe()
        try:
            for event in replay:
                if event["id"] > last_seen:
                    self._send_event(event)
            while True:
                try:
                    event = live.get(timeout=15)
                    if event["id"] > last_seen:
                        self._send_event(event)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            hub.unsubscribe(live)

    def _send_event(self, event: dict) -> None:
        self.wfile.write(f"id: {event['id']}\ndata: {json.dumps(event)}\n\n".encode())
        self.wfile.flush()

    def _screenshot(self):
        try:
            data = Sandbox().screenshot()
        except OSError as error:
            return self._json(503, {"error": f"sandbox screen unavailable: {error}"})
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"agent service listening on :{PORT}", flush=True)
    server.serve_forever()