import Editor from "@monaco-editor/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { jobsLiveApi } from "../api/client";
import "../invite-flow.css";

type Role = "recruiter" | "candidate";

interface LiveInterviewRoomProps {
  token: string;
  role: Role;
  displayName?: string;
}

export default function LiveInterviewRoom({
  token,
  role,
  displayName,
}: LiveInterviewRoomProps) {
  const [title, setTitle] = useState("Live interview");
  const [meetUrl, setMeetUrl] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState("");
  const [tests, setTests] = useState<
    Array<{ stdin: string; expected_stdout: string }>
  >([]);
  const [chat, setChat] = useState<Array<{ from: string; text: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [presence, setPresence] = useState<Record<string, string>>({});
  const [runResult, setRunResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const applyingRemote = useRef(false);
  const name = displayName || (role === "recruiter" ? "Recruiter" : "Candidate");

  useEffect(() => {
    jobsLiveApi
      .getLiveRoom(token)
      .then((res) => {
        setTitle(res.data.title);
        setMeetUrl(res.data.meet_url);
        setProblem(res.data.problem_text);
        setLanguage(res.data.language || "python");
        setCode(res.data.starter_code || "");
        setTests(res.data.public_tests || []);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Room unavailable"),
      );
  }, [token]);

  useEffect(() => {
    const url = jobsLiveApi.liveWsUrl(token, role, name);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "hello" && msg.state) {
          if (msg.state.code) {
            applyingRemote.current = true;
            setCode(msg.state.code);
          }
          if (msg.state.language) setLanguage(msg.state.language);
          if (msg.state.chat) setChat(msg.state.chat);
          if (msg.state.presence) setPresence(msg.state.presence);
        }
        if (msg.type === "code" && msg.from !== role) {
          applyingRemote.current = true;
          setCode(msg.code || "");
          if (msg.language) setLanguage(msg.language);
        }
        if (msg.type === "chat" && msg.message) {
          setChat((prev) => [...prev, msg.message]);
        }
        if (msg.type === "presence") {
          setPresence(msg.presence || {});
        }
      } catch {
        /* ignore */
      }
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [token, role, name]);

  const presenceLabel = useMemo(() => {
    const parts = Object.entries(presence).map(([r, n]) => `${r}: ${n}`);
    return parts.length ? parts.join(" · ") : "Waiting for peers…";
  }, [presence]);

  function broadcastCode(next: string, lang: string) {
    if (applyingRemote.current) {
      applyingRemote.current = false;
      return;
    }
    wsRef.current?.send(
      JSON.stringify({ type: "code", code: next, language: lang }),
    );
  }

  async function runTests() {
    setRunning(true);
    setRunResult(null);
    try {
      const res = await jobsLiveApi.runLiveTests(token, {
        language,
        source: code,
        public_tests: tests,
      });
      const data = res.data as {
        passed?: number;
        total?: number;
        error?: string;
      };
      setRunResult(
        data.error
          ? data.error
          : `Passed ${data.passed ?? 0}/${data.total ?? 0} public tests`,
      );
    } catch (err) {
      setRunResult(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  function sendChat(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    wsRef.current?.send(JSON.stringify({ type: "chat", text: chatInput.trim() }));
    setChatInput("");
  }

  async function endRoom() {
    if (role !== "recruiter") return;
    try {
      await jobsLiveApi.endLiveRoom(token, { final_code: code });
      setError("Room ended.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not end room");
    }
  }

  return (
    <div className="invite-flow live-room">
      <div className="invite-card" style={{ maxWidth: "1100px" }}>
        <h1>{title}</h1>
        <p className="rp-muted-small">{presenceLabel}</p>
        {meetUrl && (
          <p>
            Video:{" "}
            <a href={meetUrl} target="_blank" rel="noreferrer">
              Open Meet / Zoom
            </a>
          </p>
        )}
        {error && <p className="invite-error">{error}</p>}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1.2fr",
            gap: "1rem",
          }}
        >
          <div>
            <h3>Problem</h3>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
              {problem}
            </pre>
            <h3>Chat / notes</h3>
            <div
              style={{
                maxHeight: "180px",
                overflow: "auto",
                border: "1px solid #333",
                padding: "0.5rem",
                marginBottom: "0.5rem",
              }}
            >
              {chat.map((m, i) => (
                <p key={i} style={{ margin: "0.25rem 0" }}>
                  <strong>{m.from}:</strong> {m.text}
                </p>
              ))}
            </div>
            <form onSubmit={sendChat} className="invite-details-form">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Message"
              />
              <button type="submit" className="invite-primary">
                Send
              </button>
            </form>
          </div>
          <div>
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                alignItems: "center",
                marginBottom: "0.5rem",
              }}
            >
              <select
                value={language}
                onChange={(e) => {
                  setLanguage(e.target.value);
                  broadcastCode(code, e.target.value);
                }}
              >
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="java">Java</option>
                <option value="cpp">C++</option>
                <option value="c">C</option>
              </select>
              <button
                type="button"
                className="invite-primary"
                disabled={running}
                onClick={() => void runTests()}
              >
                {running ? "Running…" : "Run public tests"}
              </button>
              {role === "recruiter" && (
                <button type="button" className="rp-secondary" onClick={() => void endRoom()}>
                  End room
                </button>
              )}
            </div>
            <div style={{ height: "420px", border: "1px solid #333" }}>
              <Editor
                height="100%"
                theme="vs-dark"
                language={language === "cpp" ? "cpp" : language}
                value={code}
                onChange={(v) => {
                  const next = v ?? "";
                  setCode(next);
                  broadcastCode(next, language);
                }}
                options={{ minimap: { enabled: false }, fontSize: 14 }}
              />
            </div>
            {runResult && <p style={{ marginTop: "0.5rem" }}>{runResult}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
