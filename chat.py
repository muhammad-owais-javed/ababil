import json
import os
import urllib.request

OLLAMA_URL = os.environ["OLLAMA_URL"]
MODEL = os.environ["LLM_MODELS"].split(",")[0].strip()

# The system prompt is the instruction the model follows for the whole conversation.
SYSTEM_PROMPT = "You are a helpful assistant. Answer briefly and clearly."


def ask(messages: list[dict]) -> str:
    """Send the full message list to the model and return its reply text."""
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
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


def main() -> None:
    # This list is the conversation's memory. The list is sent on every turn.
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Chatting with {MODEL}. Type 'exit' to quit.\n")

    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_text:
            continue
        if user_text.lower() in ("exit", "quit"):
            break

        history.append({"role": "user", "content": user_text})
        reply = ask(history)
        history.append({"role": "assistant", "content": reply})

        print(f"bot> {reply}\n")


if __name__ == "__main__":
    main()