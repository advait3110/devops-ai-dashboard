/*
 * Module 6 - AI Assistant (Google Gemini).
 * The conversation is kept in this browser (localStorage) and the last
 * messages are sent with each question so Gemini remembers the context.
 * "Use live data" attaches a fresh summary of metrics, alerts, containers,
 * pods and pipelines, so answers are based on this system, not guesses.
 */
import { Bot, Eye, Send, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import Markdown from "../components/Markdown";
import { Notice, PageHeader } from "../components/ui";
import usePolling from "../hooks/usePolling";

const STORAGE_KEY = "devops-ai-chat";
const SUGGESTIONS = [
  "Is anything on my system unhealthy right now?",
  "Why could my laptop be slow? Check the top processes.",
  "Write a Dockerfile for a FastAPI app with a non-root user",
  "My pod is in CrashLoopBackOff. How do I debug it step by step?",
  "Explain the difference between a Kubernetes Deployment and a Service",
  "Write a PromQL query for 95th percentile request latency",
];

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

export default function Assistant() {
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState("");
  const [liveData, setLiveData] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [context, setContext] = useState(null);
  const endRef = useRef(null);
  const status = usePolling(() => api.get("/api/ai/status"), 0);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-40)));
    } catch {
      /* storage unavailable: chat still works for this session */
    }
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const send = async (text) => {
    const question = (text ?? input).trim();
    if (!question || busy) return;
    const next = [...messages, { role: "user", content: question }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const r = await api.post("/api/ai/chat", {
        messages: next.map(({ role, content }) => ({ role, content })),
        use_live_data: liveData,
      });
      setMessages([...next, { role: "assistant", content: r.reply, model: r.model, live: r.used_live_data }]);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const showContext = async () => {
    try {
      setContext((await api.get("/api/ai/context")).context);
    } catch (e) {
      setError(e);
    }
  };

  const notReady = status.data && !status.data.configured;

  return (
    <div className="assistant">
      <PageHeader
        title="AI assistant"
        description={status.data?.configured ? `Answers come from Google Gemini (${status.data.model}).` : "Ask anything about your systems and DevOps tools."}
      >
        <label className="switch">
          <input type="checkbox" checked={liveData} onChange={(e) => setLiveData(e.target.checked)} />
          <span>Use live data</span>
        </label>
        <button className="btn ghost sm" onClick={showContext}><Eye size={14} /> What is sent</button>
        <button className="btn ghost sm" onClick={() => setMessages([])} disabled={!messages.length}>
          <Trash2 size={14} /> Clear
        </button>
      </PageHeader>

      {notReady && <Notice error={{ message: "Gemini API key is not configured", hint: status.data.hint, status: 503 }} />}

      {context && (
        <div className="context-box">
          <div className="panel-head">
            <h2>Live data attached to each question</h2>
            <button className="btn ghost sm" onClick={() => setContext(null)}>Hide</button>
          </div>
          <pre>{context}</pre>
        </div>
      )}

      <div className="chat" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-empty">
            <Bot size={28} />
            <p>Ask about errors, commands, configs or the current state of this machine.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)} disabled={notReady}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            {m.role === "assistant" ? (
              <>
                <Markdown>{m.content}</Markdown>
                <div className="msg-meta">{m.model}{m.live ? ", with live data" : ""}</div>
              </>
            ) : (
              <p>{m.content}</p>
            )}
          </div>
        ))}
        {busy && (
          <div className="msg msg-assistant thinking">
            <span className="pulse-dot" /> Thinking{liveData ? " with live data" : ""}…
          </div>
        )}
        {error && <Notice error={error} />}
        <div ref={endRef} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder="Ask DevOps AI, or paste an error message (Enter to send, Shift+Enter for a new line)"
          aria-label="Message"
          disabled={notReady}
        />
        <button className="btn primary" type="submit" disabled={busy || !input.trim() || notReady}>
          <Send size={16} /> Send
        </button>
      </form>
    </div>
  );
}
