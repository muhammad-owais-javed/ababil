import json
import os
import urllib.request

OLLAMA_URL = os.environ["OLLAMA_URL"]

MODEL = os.environ["LLM_MODELS"].split(",")[0].strip()


def ask(question: str) -> str:
    
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
    }).encode()

    request = urllib.request.Request(
        f"{OLLAMA_URL}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)

    
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    print(ask("Say hello in five words."))