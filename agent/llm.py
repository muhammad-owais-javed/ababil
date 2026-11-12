import json
import os
import urllib.request

OLLAMA_URL = os.environ["OLLAMA_URL"]              # for example http://ollama-engine:11434
MODEL = os.environ["LLM_MODELS"].split(",")[0].strip()
NUM_CTX = int(os.environ.get("AGENT_NUM_CTX", "4096"))
TIMEOUT = float(os.environ.get("AGENT_MODEL_TIMEOUT", "90"))

# Ollama constrains the reply to this shape, so the model can't invent other action names.
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["exec", "done"]},
        "command": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["action"],
}


def chat(messages: list[dict]) -> str:
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "format": ACTION_SCHEMA,
        "options": {"temperature": 0.1, "num_ctx": NUM_CTX},
    }).encode()
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)["message"]["content"]