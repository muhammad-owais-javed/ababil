import json

from chat import ask

MAX_ATTEMPTS = 3

PLANNER_PROMPT = """You are a planner. Break the user's goal into initiatives.
Each initiative has a title and a list of steps. Each step has a title and a done_when
sentence that says how to tell the step is finished.

Reply with ONLY a JSON object in this exact shape, no prose and no markdown:
{"initiatives": [{"title": "...", "steps": [{"title": "...", "done_when": "..."}]}]}"""

GENERATOR_PROMPT = (
    "You are a Python developer. Follow the plan exactly. "
    "Output one complete Python code block and nothing else."
)


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a reply, even if the model wrapped it in a code fence."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the reply")
    return json.loads(text[start : end + 1])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_plan(data: dict) -> dict:
    """Check the shape the rest of the pipeline depends on. Raises ValueError on problems."""
    require(isinstance(data, dict), "top level must be a JSON object")
    initiatives = data.get("initiatives")
    require(isinstance(initiatives, list) and initiatives, "'initiatives' must be a non-empty list")

    for i, initiative in enumerate(initiatives, 1):
        require(isinstance(initiative, dict), f"initiative {i} must be an object")
        require(isinstance(initiative.get("title"), str) and initiative["title"].strip(),
                f"initiative {i} needs a non-empty 'title'")
        steps = initiative.get("steps")
        require(isinstance(steps, list) and steps, f"initiative {i} needs a non-empty 'steps' list")

        for j, step in enumerate(steps, 1):
            require(isinstance(step, dict), f"initiative {i}, step {j} must be an object")
            require(isinstance(step.get("title"), str) and step["title"].strip(),
                    f"initiative {i}, step {j} needs a non-empty 'title'")
            require(isinstance(step.get("done_when"), str) and step["done_when"].strip(),
                    f"initiative {i}, step {j} needs a non-empty 'done_when'")

    return data


def get_plan(goal: str) -> dict:
    """Ask the planner for a plan. If the reply is invalid, tell the model why and retry."""
    messages = [
        {"role": "system", "content": PLANNER_PROMPT},
        {"role": "user", "content": goal},
    ]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        reply = ask(messages, json_mode=True)
        try:
            return validate_plan(extract_json(reply))
        except (ValueError, json.JSONDecodeError) as error:
            print(f"[attempt {attempt}] invalid plan: {error}")
            print(f"[raw reply]\n{reply}\n")  # to see exactly what the model wrote
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError("planner failed to produce a valid plan") from error
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": f"Your reply was rejected: {error}. "
                           "Reply again with only the JSON object in the required shape.",
            })


def main() -> None:
    goal = input("goal> ").strip()

    plan = get_plan(goal)
    print("\n--- PLAN (validated) ---")
    print(json.dumps(plan, indent=2))

    # The generator receives the validated plan as JSON, not as free text.
    code_request = f"Goal: {goal}\n\nPlan:\n{json.dumps(plan, indent=2)}"
    code = ask([
        {"role": "system", "content": GENERATOR_PROMPT},
        {"role": "user", "content": code_request},
    ])
    print("\n--- CODE (generator output) ---")
    print(code)


if __name__ == "__main__":
    main()