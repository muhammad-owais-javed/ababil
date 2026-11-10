import json
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from agent import Agent

SYSTEM_PROMPT = "You are a helpful assistant. Answer briefly and clearly."
MODEL = os.environ["LLM_MODELS"].split(",")[0].strip()
OLLAMA_URL = os.environ["OLLAMA_URL"]

app = FastAPI(title="ababil agent server")

# One agent per chat session, kept in memory. A restart clears all chats.
sessions: dict[str, Agent] = {}


class ChatRequest(BaseModel):
    session_id: str | None = None
    text: str = Field(min_length=1, max_length=8000)
    images: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("images")
    @classmethod
    def must_be_image_data_urls(cls, images: list[str]) -> list[str]:
        for image in images:
            if not image.startswith("data:image/"):
                raise ValueError("each image must be a data:image/... URL")
        return images


class ChatResponse(BaseModel):
    session_id: str
    reply: str


def get_agent(session_id: str | None) -> tuple[str, Agent]:
    """Return the session's agent, creating a new session if needed."""
    session_id = session_id or uuid4().hex
    agent = sessions.get(session_id)
    if agent is None:
        agent = Agent(base_url=OLLAMA_URL, model=MODEL, system_prompt=SYSTEM_PROMPT)
        sessions[session_id] = agent
    return session_id, agent


def to_image_parts(images: list[str]) -> list[dict]:
    return [{"type": "image_url", "image_url": {"url": url}} for url in images]


def sse(payload: dict) -> str:
    """Format one Server-Sent Event: a 'data:' line followed by a blank line."""
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id, agent = get_agent(request.session_id)
    try:
        reply = agent.reply(request.text, to_image_parts(request.images))
    except OSError as error:
        raise HTTPException(status_code=503, detail=f"Model engine unreachable: {error}") from error
    return ChatResponse(session_id=session_id, reply=reply)


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    session_id, agent = get_agent(request.session_id)
    images = to_image_parts(request.images)

    def events():
        # First event tells the browser which session this is.
        yield sse({"session_id": session_id})
        try:
            for piece in agent.stream(request.text, images):
                yield sse({"delta": piece})
            yield sse({"done": True})
        except OSError as error:
            yield sse({"error": f"Model engine unreachable: {error}"})
        except Exception as error:
            yield sse({"error": f"Unexpected error: {error}"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.delete("/chat/{session_id}")
def reset(session_id: str) -> dict:
    sessions.pop(session_id, None)
    return {"status": "cleared"}