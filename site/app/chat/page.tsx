"use client";

import { useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = [
  "What are today's closest approaches?",
  "Has the ISS maneuvered recently?",
  "Show me Starlink conjunctions",
  "Any deorbit burns?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const history = messages.slice(-6);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, history }),
      });
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { role: "assistant", content: data.answer ?? "(no answer)" },
      ]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "Something went wrong reaching the copilot." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <section className="hero" style={{ paddingBottom: 12 }}>
        <p>
          Ask about anything in today&rsquo;s feed. The copilot answers only
          from screened events and detected maneuvers — grounded in the numbers
          the pipeline computed, never invented.
        </p>
      </section>

      <div className="chat">
        {messages.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} className="chip">
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content.split("\n").map((line, j) => (
              <p key={j}>{line}</p>
            ))}
          </div>
        ))}
        {busy && <div className="bubble assistant thinking">…</div>}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a satellite, a conjunction, a maneuver…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>

      <style>{`
        .chat { display: flex; flex-direction: column; gap: 12px; min-height: 300px; padding-bottom: 12px; }
        .suggestions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
        .chip { background: var(--panel); border: 1px solid var(--border); color: var(--muted); border-radius: 999px; padding: 8px 14px; font-size: 13px; cursor: pointer; }
        .chip:hover { border-color: var(--accent-dim); color: var(--text); }
        .bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.6; }
        .bubble p { margin: 0 0 6px; }
        .bubble p:last-child { margin-bottom: 0; }
        .bubble.user { align-self: flex-end; background: var(--accent-dim); border: 1px solid var(--accent-dim); }
        .bubble.assistant { align-self: flex-start; background: var(--panel); border: 1px solid var(--border); color: #c6d2e6; }
        .bubble.thinking { color: var(--muted); letter-spacing: 3px; }
        .composer { display: flex; gap: 10px; padding: 14px 0 60px; position: sticky; bottom: 0; background: linear-gradient(180deg, transparent, var(--bg) 30%); }
        .composer input { flex: 1; background: var(--bg-elev); border: 1px solid var(--border); color: var(--text); border-radius: 10px; padding: 12px 14px; font-size: 14px; }
        .composer input:focus { outline: none; border-color: var(--accent); }
        .composer button { background: var(--accent); color: #04101f; border: none; border-radius: 10px; padding: 0 20px; font-weight: 600; cursor: pointer; }
        .composer button:disabled { opacity: 0.5; cursor: default; }
      `}</style>
    </main>
  );
}
