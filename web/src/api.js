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

// Yields each event from the server: { session_id }, { delta }, { done }, or { error }.
export async function* streamChat({ sessionId, text, images }) {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, text, images }),
  });
  if (!response.ok) {
    throw new Error(`Server responded with ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Each event ends with a blank line. Handle every complete event in the buffer.
    let end;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (frame.startsWith("data: ")) {
        yield JSON.parse(frame.slice("data: ".length));
      }
    }
  }
}

export function resetChat(sessionId) {
  return request(`/chat/${sessionId}`, { method: "DELETE" });
}