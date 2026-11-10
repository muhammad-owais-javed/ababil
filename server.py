import os
import urllib.error
from uuid import uuid4

from fastapi import FastAPI, HTTPException
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or uuid4().hex
    agent = sessions.get(session_id)
    if agent is None:
        agent = Agent(base_url=OLLAMA_URL, model=MODEL, system_prompt=SYSTEM_PROMPT)
        sessions[session_id] = agent

    images = [{"type": "image_url", "image_url": {"url": url}} for url in request.images]
    try:
        reply = agent.reply(request.text, images)
    except OSError as error:
        raise HTTPException(status_code=503, detail=f"Model engine unreachable: {error}") from error

    return ChatResponse(session_id=session_id, reply=reply)


@app.delete("/chat/{session_id}")
def reset(session_id: str) -> dict:
    sessions.pop(session_id, None)
    return {"status": "cleared"}