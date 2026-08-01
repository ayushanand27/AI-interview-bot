import Editor from "@monaco-editor/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { jobsLiveApi } from "../api/client";
import "../live-room.css";

type Role = "recruiter" | "candidate";

/** Keep in sync with app/services/coding_judge.py LANGUAGE_STARTERS */
const LANGUAGE_STARTERS: Record<string, string> = {
  python:
    "# Read from stdin, write to stdout\ndef solve():\n    pass\n\nif __name__ == '__main__':\n    solve()\n",
  javascript:
    "const fs = require('fs');\nconst input = fs.readFileSync(0, 'utf8').trim();\n// Read from stdin, write to stdout\nconsole.log(input);\n",
  java:
    "import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        // Read from stdin, write to stdout\n    }\n}\n",
  cpp:
    "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    // Read from stdin, write to stdout\n    return 0;\n}\n",
  c:
    "#include <stdio.h>\n\nint main(void) {\n    /* Read from stdin, write to stdout */\n    return 0;\n}\n",
};

const LANG_OPTIONS = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
  { value: "java", label: "Java" },
  { value: "cpp", label: "C++" },
  { value: "c", label: "C" },
] as const;

type CaseResult = {
  passed: boolean;
  status?: string;
  stdin?: string;
  expected_stdout?: string;
  actual_stdout?: string;
  stderr?: string;
};

type RunPayload = {
  passed?: number;
  total?: number;
  error?: string | null;
  cases?: CaseResult[];
};

interface LiveInterviewRoomProps {
  token: string;
  role: Role;
  displayName?: string;
}

function monacoLang(lang: string): string {
  if (lang === "cpp") return "cpp";
  if (lang === "javascript") return "javascript";
  return lang;
}

function isStarterOrEmpty(code: string, lang: string): boolean {
  const trimmed = code.trim();
  if (!trimmed) return true;
  const starter = LANGUAGE_STARTERS[lang];
  if (!starter) return false;
  return trimmed === starter.trim();
}

export default function LiveInterviewRoom({
  token,
  role,
  displayName,
}: LiveInterviewRoomProps) {
  const [title, setTitle] = useState("Live interview");
  const [status, setStatus] = useState("active");
  const [meetUrl, setMeetUrl] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState("");
  const [tests, setTests] = useState<
    Array<{ stdin: string; expected_stdout: string }>
  >([]);
  const [chat, setChat] = useState<Array<{ from: string; text: string; role?: string }>>(
    [],
  );
  const [chatInput, setChatInput] = useState("");
  const [presence, setPresence] = useState<Record<string, string>>({});
  const [runResult, setRunResult] = useState<RunPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [sideTab, setSideTab] = useState<"problem" | "chat">("problem");
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const applyingRemote = useRef(false);
  const languageRef = useRef(language);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const name = displayName || (role === "recruiter" ? "Recruiter" : "Candidate");

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  useEffect(() => {
    jobsLiveApi
      .getLiveRoom(token)
      .then((res) => {
        const lang = res.data.language || "python";
        setTitle(res.data.title);
        setMeetUrl(res.data.meet_url);
        setProblem(res.data.problem_text);
        setLanguage(lang);
        setCode(res.data.starter_code || LANGUAGE_STARTERS[lang] || "");
        setTests(res.data.public_tests || []);
        setStatus(res.data.status || "active");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Room unavailable"),
      );
  }, [token]);

  useEffect(() => {
    const url = jobsLiveApi.liveWsUrl(token, role, name);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "hello" && msg.state) {
          if (msg.state.code != null && msg.state.code !== "") {
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

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat, sideTab]);

  const presenceLabel = useMemo(() => {
    const parts = Object.entries(presence).map(([r, n]) => `${r}: ${n}`);
    return parts.length ? parts.join(" · ") : "Waiting for peers…";
  }, [presence]);

  // Clear the remote-apply guard after React/Monaco settle so the next local
  // keystroke is broadcast (do not consume it inside broadcastCode).
  useEffect(() => {
    if (!applyingRemote.current) return;
    const timer = window.setTimeout(() => {
      applyingRemote.current = false;
    }, 50);
    return () => window.clearTimeout(timer);
  }, [code, language]);

  function broadcastCode(next: string, lang: string) {
    if (applyingRemote.current) {
      return;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: "code", code: next, language: lang }),
      );
    }
  }

  function changeLanguage(nextLang: string) {
    const prevLang = languageRef.current;
    let nextCode = code;
    if (isStarterOrEmpty(code, prevLang)) {
      nextCode = LANGUAGE_STARTERS[nextLang] || "";
      setCode(nextCode);
    }
    setLanguage(nextLang);
    broadcastCode(nextCode, nextLang);
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
      setRunResult(res.data as RunPayload);
    } catch (err) {
      setRunResult({
        error: err instanceof Error ? err.message : "Run failed",
        passed: 0,
        total: 0,
        cases: [],
      });
    } finally {
      setRunning(false);
    }
  }

  function sendChat(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: "chat", text: chatInput.trim() }),
      );
    }
    setChatInput("");
    setSideTab("chat");
  }

  async function endRoom() {
    if (role !== "recruiter") return;
    if (!window.confirm("End this live room for everyone?")) return;
    try {
      await jobsLiveApi.endLiveRoom(token, { final_code: code });
      setStatus("ended");
      setError("Room ended.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not end room");
    }
  }

  const consoleSummary = useMemo(() => {
    if (!runResult) return null;
    if (runResult.error) return { text: runResult.error, ok: false };
    const passed = runResult.passed ?? 0;
    const total = runResult.total ?? 0;
    return {
      text: `Passed ${passed}/${total} public tests`,
      ok: total > 0 && passed === total,
    };
  }, [runResult]);

  return (
    <div className="live-room-shell">
      <header className="live-room-header">
        <div className="live-room-header-left">
          <h1 className="live-room-title">{title}</h1>
          <span
            className={`live-room-badge ${
              role === "recruiter" ? "is-recruiter" : "is-candidate"
            }`}
          >
            {role}
          </span>
          <span className="live-room-status">
            <span
              className={`live-room-status-dot ${
                wsConnected && status !== "ended" ? "" : "is-idle"
              }`}
            />
            {status === "ended" ? "Ended" : presenceLabel}
          </span>
        </div>
        <div className="live-room-header-actions">
          {meetUrl ? (
            <a
              className="live-room-btn live-room-btn-meet"
              href={meetUrl}
              target="_blank"
              rel="noreferrer"
            >
              Join Meet / Zoom
            </a>
          ) : (
            <span className="live-room-status">No video link set</span>
          )}
        </div>
      </header>

      <p className="live-room-honesty" role="status">
        Live collaborative rooms are not proctored — Meet/Zoom handles video.
        Async assessments (invite links) are proctored.
      </p>

      {error && <p className="live-room-error">{error}</p>}

      <div className="live-room-body">
        <aside className="live-room-side">
          <div className="live-room-panel-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={sideTab === "problem"}
              className={`live-room-panel-tab ${
                sideTab === "problem" ? "is-active" : ""
              }`}
              onClick={() => setSideTab("problem")}
            >
              Problem
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={sideTab === "chat"}
              className={`live-room-panel-tab ${
                sideTab === "chat" ? "is-active" : ""
              }`}
              onClick={() => setSideTab("chat")}
            >
              Chat{chat.length ? ` (${chat.length})` : ""}
            </button>
          </div>
          <div className="live-room-panel-body">
            {sideTab === "problem" ? (
              <pre className="live-room-problem">
                {problem || "No problem statement for this room."}
              </pre>
            ) : (
              <div className="live-room-chat">
                <div className="live-room-chat-log">
                  {chat.length === 0 && (
                    <p className="live-room-console-empty">
                      No messages yet. Coordinate with your peer here.
                    </p>
                  )}
                  {chat.map((m, i) => (
                    <div key={`${m.from}-${i}`} className="live-room-chat-item">
                      <strong>{m.from}</strong>
                      <span>{m.text}</span>
                    </div>
                  ))}
                  <div ref={chatEndRef} />
                </div>
                <form onSubmit={sendChat} className="live-room-chat-form">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder="Type a message…"
                    aria-label="Chat message"
                  />
                  <button type="submit" className="live-room-btn live-room-btn-primary">
                    Send
                  </button>
                </form>
              </div>
            )}
          </div>
        </aside>

        <section className="live-room-main">
          <div className="live-room-toolbar">
            <label htmlFor="live-lang">Language</label>
            <select
              id="live-lang"
              className="live-room-lang"
              value={language}
              disabled={status === "ended"}
              onChange={(e) => changeLanguage(e.target.value)}
            >
              {LANG_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="live-room-btn live-room-btn-primary"
              disabled={running || status === "ended"}
              onClick={() => void runTests()}
            >
              {running ? "Running…" : "Run public tests"}
            </button>
            {role === "recruiter" && (
              <button
                type="button"
                className="live-room-btn live-room-btn-danger"
                disabled={status === "ended"}
                onClick={() => void endRoom()}
              >
                End room
              </button>
            )}
          </div>

          <div className="live-room-editor">
            <Editor
              height="100%"
              theme="vs-dark"
              language={monacoLang(language)}
              value={code}
              onChange={(v) => {
                const next = v ?? "";
                setCode(next);
                broadcastCode(next, language);
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                readOnly: status === "ended",
                scrollBeyondLastLine: false,
                automaticLayout: true,
                padding: { top: 8 },
              }}
            />
          </div>

          <div className="live-room-console" aria-live="polite">
            <div className="live-room-console-head">
              <span>Test results</span>
              {consoleSummary && (
                <span
                  className={`live-room-console-summary ${
                    consoleSummary.ok ? "is-pass" : "is-fail"
                  }`}
                >
                  {consoleSummary.text}
                </span>
              )}
            </div>
            <div className="live-room-console-body">
              {!runResult && (
                <p className="live-room-console-empty">
                  Run public tests to see stdin / expected / actual output here.
                </p>
              )}
              {runResult?.error && (
                <div className="live-room-case is-fail">
                  <div className="live-room-case-title">Error</div>
                  <pre>{runResult.error}</pre>
                </div>
              )}
              {(runResult?.cases || []).map((c, i) => (
                <div
                  key={i}
                  className={`live-room-case ${c.passed ? "is-pass" : "is-fail"}`}
                >
                  <div className="live-room-case-title">
                    Case {i + 1}: {c.passed ? "PASS" : "FAIL"}
                    {c.status ? ` · ${c.status}` : ""}
                  </div>
                  <div>
                    stdin:
                    <pre>{c.stdin || "(empty)"}</pre>
                  </div>
                  <div>
                    expected:
                    <pre>{c.expected_stdout ?? ""}</pre>
                  </div>
                  <div>
                    actual:
                    <pre>{c.actual_stdout ?? ""}</pre>
                  </div>
                  {c.stderr ? (
                    <div>
                      stderr:
                      <pre>{c.stderr}</pre>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
