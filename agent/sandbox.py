import json
import os
import urllib.error
import urllib.request


class Sandbox:
    def __init__(self) -> None:
        self.base_url = os.environ["SANDBOX_URL"].rstrip("/")
        self.token = os.environ["SANDBOX_TOKEN"]

    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Sandbox-Token": self.token},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def exec(self, command: str, timeout: int = 60, exec_id: str | None = None) -> dict:
        payload = {"command": command, "timeout": timeout}
        if exec_id:
            payload["id"] = exec_id
        return self._post("/exec", payload, timeout + 15)

    def cancel(self, exec_id: str) -> bool:
        """Cancel a running command. Returns False if it had already finished."""
        try:
            self._post("/cancel", {"id": exec_id}, 10)
            return True
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return False
            raise

    def screenshot(self) -> bytes:
        request = urllib.request.Request(
            f"{self.base_url}/screenshot", headers={"X-Sandbox-Token": self.token}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()