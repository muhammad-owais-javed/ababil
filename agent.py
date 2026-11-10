import base64
import json
import mimetypes
import urllib.request
from pathlib import Path


class Agent:
    """Agent with memory. It knows nothing about the screen it is shown on."""

    def __init__(self, base_url: str, model: str, system_prompt: str) -> None:
        self.base_url = base_url
        self.model = model
        self.history = [{"role": "system", "content": system_prompt}]

    @staticmethod
    def image_part(path: str) -> dict:
        """Turn an image file into a part the vision model can read."""
        file = Path(path)
        mime = mimetypes.guess_type(file.name)[0] or "image/png"
        encoded = base64.b64encode(file.read_bytes()).decode()
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}

    def reply(self, text: str, images: list[dict] | None = None) -> str:
        """Add the user's message, get the model's answer, and remember both.
        If the model call fails, the message is removed so memory stays consistent."""
        if images:
            content = [{"type": "text", "text": text}, *images]
        else:
            content = text

        self.history.append({"role": "user", "content": content})
        try:
            answer = self._call(self.history)
        except Exception:
            self.history.pop()
            raise
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def _call(self, messages: list[dict]) -> str:
        body = {"model": self.model, "messages": messages, "stream": False}
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.load(response)
        return data["choices"][0]["message"]["content"]