import json
import sys
import threading
import time
import uuid
from typing import Callable

from control import StopControl
from llm import chat
from sandbox import Sandbox

MAX_STEPS = 8
MAX_REPEATS = 3          # the same command this many times in a row stops the run
MAX_INVALID = 3          # invalid replies in a row stop the run
MAX_OUTPUT = 3000        # characters of command output sent back to the model
EVENT_OUTPUT = 4000      # characters of command output sent to viewers
WAIT_BEAT = 5            # seconds between "still waiting" updates

SYSTEM_PROMPT = """You control a Linux computer by running shell commands, one action per turn.
Reply with ONLY one JSON object, in one of these two forms:
{"action": "exec", "command": "<bash command>"}
{"action": "done", "answer": "<final answer for the user>"}

Rules:
- Run one command per turn. You will receive its exit code, stdout and stderr.
- You are root. To install software: apt-get update && apt-get install -y <package>
- Use commands that finish without waiting for input.
- Do not repeat a command whose output you already have. If the output answers the task, use done.
- Use done only after you have seen the output that proves the answer.
- If something failed, say so in the answer. Never invent results.

Example.
Task: "Tell me the current user."
{"action": "exec", "command": "whoami"}
Result: exit_code=0, stdout "root"
{"action": "done", "answer": "The current user is root."}"""

Emit = Callable[..., object]


def print_event(kind: str, **data) -> None:
    print(f"[{kind}] {json.dumps(data, default=str)[:300]}", flush=True)


def parse(reply: str) -> dict:
    """Check one action. Each error message tells the model how to fix its next reply."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("the reply was not a JSON object")
    action = json.loads(reply[start : end + 1])
    if not isinstance(action, dict):
        raise ValueError("the reply must be a single JSON object")

    kind = action.get("action")
    if kind == "exec":
        command = str(action.get("command", "")).strip()
        if not command:
            raise ValueError("exec needs a non-empty 'command' field")
        return {"action": "exec", "command": command}
    if kind == "done":
        answer = str(action.get("answer", "")).strip()
        if not answer:
            raise ValueError("done needs a non-empty 'answer' field")
        return {"action": "done", "answer": answer}
    raise ValueError(f"unknown action {kind!r}. Use exec or done")


def clip(text: str, limit: int = MAX_OUTPUT) -> str:
    return text[-limit:]


def ask_model(messages: list[dict], step: int, emit: Emit,
              control: StopControl | None) -> tuple[str | None, str | None]:
    """Ask the model without blocking the stop logic.

    The request runs in a background thread. While it runs, this function reports
    progress every few seconds and watches for a 'stop now' request.
    Returns (reply, None), or (None, reason) if the call was abandoned or failed."""
    box: dict = {}
    finished = threading.Event()

    def call():
        try:
            box["reply"] = chat(messages)
        except Exception as error:
            box["error"] = error
        finally:
            finished.set()

    threading.Thread(target=call, daemon=True).start()
    started = time.monotonic()
    last_beat = -WAIT_BEAT

    while not finished.wait(timeout=1):
        elapsed = int(time.monotonic() - started)
        if control is not None and control.mode == "now":
            return None, "stopped now while waiting for the model. Its reply was discarded"
        if elapsed - last_beat >= WAIT_BEAT:
            emit("waiting", step=step, seconds=elapsed)
            last_beat = elapsed

    if "error" in box:
        return None, f"model call failed: {box['error']}"
    return box["reply"], None


def stop_message(mode: str, result: dict | None) -> str:
    if mode == "after_step":
        return "stopped after this step"
    if result and result.get("cancelled"):
        return "stopped now; the running command was cancelled"
    return "stopped now"


def run(task: str, emit: Emit = print_event, control: StopControl | None = None) -> tuple[bool, str]:
    sandbox = Sandbox()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}"},
    ]
    invalid = 0
    last_command, repeats = None, 0

    for step in range(1, MAX_STEPS + 1):
        if control is not None and control.mode is not None:
            return False, "stopped before the next step"

        emit("step", step=step, max_steps=MAX_STEPS)
        started = time.monotonic()
        reply, problem = ask_model(messages, step, emit, control)
        if problem:
            emit("error", message=problem)
            return False, problem
        emit("model", text=reply, seconds=round(time.monotonic() - started, 1))
        messages.append({"role": "assistant", "content": reply})

        try:
            action = parse(reply)
        except ValueError as error:
            invalid += 1
            emit("invalid", error=str(error))
            if invalid >= MAX_INVALID:
                return False, f"stopped after {invalid} invalid replies. Last error: {error}"
            messages.append({"role": "user", "content": f"Invalid reply: {error}. Reply with exactly one JSON action."})
            continue
        invalid = 0

        if action["action"] == "done":
            return True, action["answer"]

        command = action["command"]
        repeats = repeats + 1 if command == last_command else 1
        last_command = command
        if repeats >= MAX_REPEATS:
            message = f"stopped: the same command ran {repeats} times in a row: {command}"
            emit("error", message=message)
            return False, message

        command_id = uuid.uuid4().hex
        if control is not None and not control.begin_command(command_id):
            return False, "stopped now before the command started"

        emit("command", command=command)
        result = None
        try:
            result = Sandbox().exec(command, exec_id=command_id)
        except OSError as error:
            emit("error", message=f"sandbox error: {error}")
            messages.append({"role": "user", "content": f"The sandbox could not run the command: {error}. Choose another action."})
        finally:
            if control is not None:
                control.end_command()

        if result is not None:
            emit("result", exit_code=result["exit_code"], timed_out=result["timed_out"],
                 cancelled=result["cancelled"],
                 stdout=clip(result["stdout"], EVENT_OUTPUT), stderr=clip(result["stderr"], EVENT_OUTPUT))
            messages.append({"role": "user", "content": (
                f"Command finished. exit_code={result['exit_code']} timed_out={result['timed_out']} "
                f"cancelled={result['cancelled']}\n"
                f"stdout:\n{clip(result['stdout'])}\nstderr:\n{clip(result['stderr'])}"
            )})

        # Checked after the step is complete, so the result is always recorded before stopping.
        if control is not None and control.mode is not None:
            return False, stop_message(control.mode, result)

    message = f"stopped after {MAX_STEPS} steps without an answer"
    emit("error", message=message)
    return False, message


if __name__ == "__main__":
    task_text = " ".join(sys.argv[1:]) or input("task> ").strip()
    ok, result = run(task_text)
    print("\n=== RESULT ===", flush=True)
    print(("" if ok else "[not completed] ") + result, flush=True)