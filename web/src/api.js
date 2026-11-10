const BASE = "/api";

async function request(path, options) {
  const response = await fetch(`${BASE}${path}`, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      // the error body wasn't JSON; keep the status text
    }
    throw new Error(detail);
  }
  return response.json();
}

export function sendChat({ sessionId, text, images }) {
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, text, images }),
  });
}

export function resetChat(sessionId) {
  return request(`/chat/${sessionId}`, { method: "DELETE" });
}