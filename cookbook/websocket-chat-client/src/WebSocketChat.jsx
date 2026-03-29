import { useState, useEffect, useRef, useCallback } from "react";

// ── WebSocket Hook ──────────────────────────────────────────────────
const WS_STATES = { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 };

function useWebSocket(url, {
  reconnect = true,
  reconnectInterval = 2000,
  maxReconnectAttempts = 10,
  onMessage,
  onOpen,
  onClose,
  onError,
  protocols,
} = {}) {
  const wsRef = useRef(null);
  const reconnectCount = useRef(0);
  const reconnectTimer = useRef(null);
  const intentionalClose = useRef(false);
  const [readyState, setReadyState] = useState(WS_STATES.CLOSED);

  const connect = useCallback(() => {
    if (!url) return;
    intentionalClose.current = false;
    try {
      const ws = protocols ? new WebSocket(url, protocols) : new WebSocket(url);
      wsRef.current = ws;
      setReadyState(WS_STATES.CONNECTING);

      ws.onopen = (e) => {
        setReadyState(WS_STATES.OPEN);
        reconnectCount.current = 0;
        onOpen?.(e);
      };

      ws.onmessage = (e) => {
        onMessage?.(e);
      };

      ws.onclose = (e) => {
        setReadyState(WS_STATES.CLOSED);
        onClose?.(e);
        if (reconnect && !intentionalClose.current && reconnectCount.current < maxReconnectAttempts) {
          const delay = reconnectInterval * Math.pow(1.5, reconnectCount.current);
          reconnectTimer.current = setTimeout(() => {
            reconnectCount.current += 1;
            connect();
          }, Math.min(delay, 30000));
        }
      };

      ws.onerror = (e) => {
        onError?.(e);
      };
    } catch (err) {
      console.error("WebSocket connection error:", err);
    }
  }, [url, protocols, reconnect, reconnectInterval, maxReconnectAttempts, onMessage, onOpen, onClose, onError]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WS_STATES.OPEN) {
      wsRef.current.send(typeof data === "string" ? data : JSON.stringify(data));
      return true;
    }
    return false;
  }, []);

  const disconnect = useCallback(() => {
    intentionalClose.current = true;
    clearTimeout(reconnectTimer.current);
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      intentionalClose.current = true;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { send, disconnect, reconnect: connect, readyState, ws: wsRef };
}

// ── Chat Component ──────────────────────────────────────────────────
const STATUS_LABELS = {
  [WS_STATES.CONNECTING]: "Connecting",
  [WS_STATES.OPEN]: "Connected",
  [WS_STATES.CLOSING]: "Closing",
  [WS_STATES.CLOSED]: "Disconnected",
};

const STATUS_COLORS = {
  [WS_STATES.CONNECTING]: "#e8a317",
  [WS_STATES.OPEN]: "#22c55e",
  [WS_STATES.CLOSING]: "#e8a317",
  [WS_STATES.CLOSED]: "#ef4444",
};

export default function WebSocketChat() {
  const [wsUrl, setWsUrl] = useState("wss://echo.websocket.org");
  const [activeUrl, setActiveUrl] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [jsonMode, setJsonMode] = useState(false);
  const scrollRef = useRef(null);

  const addMessage = useCallback((role, content, meta = {}) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role, content, ts: Date.now(), ...meta },
    ]);
  }, []);

  const { send, disconnect, reconnect, readyState } = useWebSocket(
    activeUrl || null,
    {
      onOpen: () => addMessage("system", "Connection established."),
      onClose: (e) => addMessage("system", `Connection closed (code ${e.code}).`),
      onError: () => addMessage("system", "Connection error."),
      onMessage: (e) => {
        let content = e.data;
        let parsed = null;
        try { parsed = JSON.parse(content); } catch {}
        addMessage("server", parsed ? JSON.stringify(parsed, null, 2) : content, {
          isJson: !!parsed,
        });
      },
    }
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleConnect = () => {
    if (activeUrl) disconnect();
    setMessages([]);
    setActiveUrl(wsUrl);
  };

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    if (jsonMode) {
      try {
        const obj = JSON.parse(trimmed);
        send(JSON.stringify(obj));
        addMessage("client", JSON.stringify(obj, null, 2), { isJson: true });
      } catch {
        addMessage("system", "Invalid JSON. Check syntax and retry.");
        return;
      }
    } else {
      send(trimmed);
      addMessage("client", trimmed);
    }
    setInput("");
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isOpen = readyState === WS_STATES.OPEN;

  return (
    <div style={styles.root}>
      {/* ── Header ── */}
      <div style={styles.header}>
        <div style={styles.titleRow}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>
            <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>
            <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>
            <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
          </svg>
          <span style={styles.title}>WebSocket Client</span>
          <span style={{ ...styles.badge, background: STATUS_COLORS[readyState] + "22", color: STATUS_COLORS[readyState], border: `1px solid ${STATUS_COLORS[readyState]}44` }}>
            <span style={{ ...styles.dot, background: STATUS_COLORS[readyState] }} />
            {STATUS_LABELS[readyState]}
          </span>
        </div>

        {/* URL bar */}
        <div style={styles.urlBar}>
          <input
            style={styles.urlInput}
            value={wsUrl}
            onChange={(e) => setWsUrl(e.target.value)}
            placeholder="wss://your-server/ws"
            spellCheck={false}
          />
          <button
            style={{ ...styles.btn, ...(activeUrl && isOpen ? styles.btnDanger : styles.btnPrimary) }}
            onClick={activeUrl && isOpen ? () => { disconnect(); setActiveUrl(""); } : handleConnect}
          >
            {activeUrl && isOpen ? "Disconnect" : "Connect"}
          </button>
        </div>
      </div>

      {/* ── Messages ── */}
      <div ref={scrollRef} style={styles.messagePane}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            <span style={styles.emptyIcon}>↕</span>
            <span>Enter a WebSocket URL and connect to begin.</span>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} style={{ ...styles.msgRow, justifyContent: m.role === "client" ? "flex-end" : "flex-start" }}>
            <div style={{
              ...styles.bubble,
              ...(m.role === "client" ? styles.bubbleClient : m.role === "server" ? styles.bubbleServer : styles.bubbleSystem),
            }}>
              <div style={styles.msgMeta}>
                <span style={styles.msgRole}>{m.role}</span>
                <span style={styles.msgTime}>{new Date(m.ts).toLocaleTimeString()}</span>
              </div>
              <pre style={styles.msgContent}>{m.content}</pre>
            </div>
          </div>
        ))}
      </div>

      {/* ── Input ── */}
      <div style={styles.inputArea}>
        <div style={styles.inputControls}>
          <label style={styles.toggle}>
            <input type="checkbox" checked={jsonMode} onChange={(e) => setJsonMode(e.target.checked)} style={{ display: "none" }} />
            <span style={{ ...styles.toggleTrack, background: jsonMode ? "#6366f1" : "#3f3f46" }}>
              <span style={{ ...styles.toggleKnob, transform: jsonMode ? "translateX(16px)" : "translateX(2px)" }} />
            </span>
            <span style={styles.toggleLabel}>JSON</span>
          </label>
          <span style={styles.hint}>Shift+Enter for newline</span>
        </div>
        <div style={styles.compose}>
          <textarea
            style={styles.textarea}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={jsonMode ? '{"type": "ping"}' : "Type a message..."}
            disabled={!isOpen}
          />
          <button style={{ ...styles.sendBtn, opacity: isOpen && input.trim() ? 1 : 0.35 }} onClick={handleSend} disabled={!isOpen || !input.trim()}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────
const mono = "'SF Mono', 'Cascadia Code', 'Fira Code', 'JetBrains Mono', Menlo, Consolas, monospace";
const sans = "'DM Sans', 'Satoshi', system-ui, -apple-system, sans-serif";

const styles = {
  root: {
    display: "flex", flexDirection: "column", height: "100vh", width: "100%",
    background: "#0c0c0e", color: "#e4e4e7", fontFamily: sans, overflow: "hidden",
  },
  header: {
    padding: "14px 16px 12px", borderBottom: "1px solid #1e1e24",
    background: "linear-gradient(180deg, #111114 0%, #0c0c0e 100%)",
  },
  titleRow: { display: "flex", alignItems: "center", gap: 8, marginBottom: 10, color: "#a1a1aa" },
  title: { fontWeight: 600, fontSize: 15, color: "#fafafa", letterSpacing: "-0.01em" },
  badge: {
    marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5,
    fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 20, letterSpacing: "0.02em",
  },
  dot: { width: 6, height: 6, borderRadius: "50%" },
  urlBar: { display: "flex", gap: 8 },
  urlInput: {
    flex: 1, background: "#18181b", border: "1px solid #27272a", borderRadius: 8,
    color: "#fafafa", fontFamily: mono, fontSize: 13, padding: "8px 12px", outline: "none",
  },
  btn: {
    border: "none", borderRadius: 8, padding: "8px 16px", fontWeight: 600, fontSize: 13,
    cursor: "pointer", letterSpacing: "0.01em", transition: "all .15s",
  },
  btnPrimary: { background: "#6366f1", color: "#fff" },
  btnDanger: { background: "#dc2626", color: "#fff" },

  messagePane: {
    flex: 1, overflowY: "auto", padding: "12px 16px", display: "flex", flexDirection: "column", gap: 6,
  },
  empty: {
    margin: "auto", display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
    color: "#52525b", fontSize: 13,
  },
  emptyIcon: { fontSize: 28, opacity: 0.5 },
  msgRow: { display: "flex" },
  bubble: { maxWidth: "80%", borderRadius: 10, padding: "8px 12px" },
  bubbleClient: { background: "#312e81", borderBottomRightRadius: 3 },
  bubbleServer: { background: "#1c1c22", border: "1px solid #27272a", borderBottomLeftRadius: 3 },
  bubbleSystem: { background: "transparent", padding: "4px 0", maxWidth: "100%" },
  msgMeta: { display: "flex", alignItems: "center", gap: 8, marginBottom: 3 },
  msgRole: { fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#71717a" },
  msgTime: { fontSize: 10, color: "#52525b" },
  msgContent: {
    margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word",
    fontFamily: mono, fontSize: 13, lineHeight: 1.55, color: "#d4d4d8",
  },

  inputArea: { padding: "8px 16px 14px", borderTop: "1px solid #1e1e24", background: "#0c0c0e" },
  inputControls: { display: "flex", alignItems: "center", gap: 12, marginBottom: 8 },
  toggle: { display: "flex", alignItems: "center", gap: 6, cursor: "pointer" },
  toggleTrack: {
    width: 32, height: 18, borderRadius: 10, position: "relative", transition: "background .2s",
  },
  toggleKnob: {
    position: "absolute", top: 2, width: 14, height: 14, borderRadius: "50%",
    background: "#fff", transition: "transform .2s",
  },
  toggleLabel: { fontSize: 11, fontWeight: 600, color: "#71717a", fontFamily: mono },
  hint: { marginLeft: "auto", fontSize: 11, color: "#3f3f46" },
  compose: { display: "flex", gap: 8, alignItems: "flex-end" },
  textarea: {
    flex: 1, background: "#18181b", border: "1px solid #27272a", borderRadius: 10,
    color: "#fafafa", fontFamily: mono, fontSize: 13, padding: "10px 12px",
    resize: "none", outline: "none", lineHeight: 1.5,
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: 10, border: "none",
    background: "#6366f1", color: "#fff", cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
    transition: "opacity .15s",
  },
};
