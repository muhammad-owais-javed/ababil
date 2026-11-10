import { useRef, useState } from "react";
import { sendChat, resetChat } from "./api.js";
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

  async function onSubmit(event) {
    event.preventDefault();
    const content = text.trim();
    if ((!content && !image) || busy) return;

    const outgoing = { role: "user", text: content, image };
    setMessages((prev) => [...prev, outgoing]);
    setText("");
    setImage(null);
    if (fileInput.current) fileInput.current.value = "";
    setBusy(true);
    setError("");

    try {
      const data = await sendChat({
        sessionId,
        text: content || "Describe this image.",
        images: outgoing.image ? [outgoing.image] : [],
      });
      setSessionId(data.session_id);
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply }]);
    } catch (err) {
      setError(err.message);
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
            {m.text && <p>{m.text}</p>}
          </div>
        ))}
        {busy && <div className="bubble assistant pending">Thinking…</div>}
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