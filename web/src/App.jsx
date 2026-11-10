import { useRef, useState } from "react";
import { streamChat, resetChat } from "./api.js";
import "./App.css";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [image, setImage] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef(null);

  function onPickImage(event) {
    const file = event.target.files[0];
    if (!file) {
      setImage(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result); // data:image/...;base64,...
    reader.readAsDataURL(file);
  }

  // Add a piece of text to the assistant message that is currently being written.
  function appendToLastMessage(piece) {
    setMessages((prev) =>
      prev.map((m, i) => (i === prev.length - 1 ? { ...m, text: m.text + piece } : m))
    );
  }

  async function onSubmit(event) {
    event.preventDefault();
    const content = text.trim();
    if ((!content && !image) || busy) return;

    const sentImage = image;
    setMessages((prev) => [
      ...prev,
      { role: "user", text: content, image: sentImage },
      { role: "assistant", text: "" }, // filled in as the stream arrives
    ]);
    setText("");
    setImage(null);
    if (fileInput.current) fileInput.current.value = "";
    setBusy(true);
    setError("");

    try {
      const events = streamChat({
        sessionId,
        text: content || "Describe this image.",
        images: sentImage ? [sentImage] : [],
      });
      for await (const event of events) {
        if (event.session_id) setSessionId(event.session_id);
        if (event.delta) appendToLastMessage(event.delta);
        if (event.error) throw new Error(event.error);
      }
    } catch (err) {
      setError(err.message);
      // Remove the empty assistant placeholder if nothing arrived.
      setMessages((prev) =>
        prev.length && prev[prev.length - 1].role === "assistant" && !prev[prev.length - 1].text
          ? prev.slice(0, -1)
          : prev
      );
    } finally {
      setBusy(false);
    }
  }

  async function onNewChat() {
    if (sessionId) await resetChat(sessionId).catch(() => {});
    setSessionId(null);
    setMessages([]);
    setError("");
  }

  return (
    <div className="app">
      <header>
        <h1>ababil</h1>
        <button onClick={onNewChat} disabled={busy}>New chat</button>
      </header>

      <main className="messages">
        {messages.length === 0 && (
          <p className="empty">Ask anything, or attach an image.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.image && <img src={m.image} alt="attachment" />}
            {m.role === "assistant" && !m.text ? (
              <p className="pending">Thinking…</p>
            ) : (
              m.text && <p>{m.text}</p>
            )}
          </div>
        ))}
      </main>

      {error && <div className="error">{error}</div>}

      <form className="composer" onSubmit={onSubmit}>
        <input
          type="file"
          accept="image/*"
          ref={fileInput}
          onChange={onPickImage}
          disabled={busy}
        />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a message"
          rows={2}
          disabled={busy}
        />
        <button type="submit" disabled={busy}>Send</button>
      </form>
    </div>
  );
}