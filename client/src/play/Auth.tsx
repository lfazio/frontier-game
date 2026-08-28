import { useState } from "react";
import { play, Refused } from "../api";

const MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: "That email and password do not match.",
  EMAIL_TAKEN: "That email already has a pilot.",
  CALLSIGN_TAKEN: "That callsign is taken. Pick another.",
};

export function Auth({ onToken }: { onToken: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [callsign, setCallsign] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setRefusal(null);
    try {
      const token =
        mode === "register"
          ? await play.register(email, password, callsign)
          : await play.login(email, password);
      onToken(token);
    } catch (error) {
      // A refusal is an answer, not a failure (UX §5.4): state it plainly, keep the form intact.
      const code = error instanceof Refused ? error.code : "UNREACHABLE";
      setRefusal(MESSAGES[code] ?? "The server could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form className="card" onSubmit={submit}>
        <h1 className="brand">FRONTIER</h1>
        <p className="dim">
          One cycle a day. Spend your Action Points, talk to your team, and leave.
        </p>

        <div className="segmented">
          <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>
            New pilot
          </button>
          <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>
            Returning
          </button>
        </div>

        {mode === "register" && (
          <label>
            Callsign
            <input value={callsign} onChange={(e) => setCallsign(e.target.value)} required minLength={3} />
          </label>
        )}
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </label>

        {refusal && <p className="refusal">{refusal}</p>}

        <button className="primary" disabled={busy}>
          {busy ? "One moment…" : mode === "register" ? "Take a ship" : "Sign in"}
        </button>
        <p className="dim small">
          A new pilot starts independent — no faction, no standing — at a faction home station.
        </p>
      </form>
    </div>
  );
}
