import os

from agent import Agent

agent = Agent(
    base_url=os.environ["OLLAMA_URL"],
    model=os.environ["LLM_MODELS"].split(",")[0].strip(),
    system_prompt="You are a helpful assistant. Answer briefly and clearly.",
)


def main() -> None:
    images: list[dict] = []
    print(f"Chatting with {agent.model}.")
    print("Commands: /image <path> attaches an image to your next message. 'exit' quits.\n")

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break
        if text.startswith("/image "):
            path = text[len("/image "):].strip()
            try:
                images.append(Agent.image_part(path))
                print(f"[attached {path}]")
            except OSError as error:
                print(f"[could not read {path}: {error}]")
            continue

        answer = agent.reply(text, images)
        images.clear()
        print(f"bot> {answer}\n")


if __name__ == "__main__":
    main()