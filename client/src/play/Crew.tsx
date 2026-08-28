import { useCallback, useEffect, useState } from "react";
import { FACTIONS, play, type Me, type TeamRow } from "../api";
import { act, newKey, outcomeText } from "./commands";

// A player is independent until they join something (GDD §6). This screen is where they stop
// being, and where they can stop being it again.

export function Crew({ token, me, onActed }: { token: string; me: Me; onActed: () => void }) {
  const [rows, setRows] = useState<TeamRow[] | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [faction, setFaction] = useState(1);

  const reload = useCallback(() => {
    play.teams(token).then((body) => setRows(body.teams)).catch(() => setSaid("Could not read the register."));
  }, [token]);

  useEffect(reload, [reload]);

  async function run(what: () => Promise<string>) {
    setBusy(true);
    try {
      setSaid(await what());
      onActed();
      reload();
    } catch {
      setSaid("Could not reach the server. Nothing was sent.");
    } finally {
      setBusy(false);
    }
  }

  const mine = rows?.find((row) => row.id === me.player.team_id) ?? null;

  return (
    <div className="crew">
      {said && (
        <p className="said" role="status">
          {said} <button className="link" onClick={() => setSaid(null)}>Dismiss</button>
        </p>
      )}

      {mine ? (
        <>
          <h3>{mine.name}</h3>
          <p className="dim small">
            {FACTIONS[mine.faction_id]?.name ?? "Unaligned"} · {mine.members}{" "}
            {mine.members === 1 ? "member" : "members"} · founded day {mine.founded_on}
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const outcome = await act.leaveTeam(token, newKey());
                return outcome.stopped
                  ? outcomeText(outcome, me.ship.position)
                  : "You fly alone again.";
              })
            }
          >
            Leave the crew
          </button>
        </>
      ) : (
        <>
          <p className="dim small">
            You are independent. Joining a crew gives you a shared channel and a banner; it does
            not oblige you to anything else.
          </p>

          <h3>Crews</h3>
          {rows === null ? (
            <p className="quiet">Reading the register…</p>
          ) : rows.length === 0 ? (
            <p className="quiet">Nobody has founded one yet. You could be first.</p>
          ) : (
            <ul className="cards">
              {rows.map((row) => (
                <li key={row.id} className="mission">
                  <div className="missionhead">
                    <b>{row.name}</b>
                    <span className="spacer" />
                    <span className="tag" style={{ borderColor: FACTIONS[row.faction_id]?.tint }}>
                      {FACTIONS[row.faction_id]?.name ?? row.faction_id}
                    </span>
                  </div>
                  <p className="dim small">
                    {row.members} {row.members === 1 ? "member" : "members"} · founded day {row.founded_on}
                  </p>
                  <button
                    className="go"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        const outcome = await act.joinTeam(token, row.id, newKey());
                        return outcome.stopped
                          ? outcomeText(outcome, me.ship.position)
                          : `You are one of ${row.name}.`;
                      })
                    }
                  >
                    Join
                  </button>
                </li>
              ))}
            </ul>
          )}

          <h3>Found one</h3>
          <form
            className="found"
            onSubmit={(submit) => {
              submit.preventDefault();
              void run(async () => {
                const outcome = await act.createTeam(token, name.trim(), faction, newKey());
                if (outcome.stopped) return outcomeText(outcome, me.ship.position);
                setName("");
                return `${name.trim()} exists. You are its first member.`;
              });
            }}
          >
            <label>
              <span className="visually-hidden">Crew name</span>
              <input
                value={name}
                minLength={3}
                maxLength={64}
                placeholder="Name your crew"
                onChange={(change) => setName(change.target.value)}
              />
            </label>
            <label>
              <span className="visually-hidden">Banner</span>
              <select value={faction} onChange={(change) => setFaction(Number(change.target.value))}>
                {[1, 2, 3].map((id) => (
                  <option key={id} value={id}>
                    {FACTIONS[id]?.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="go" disabled={busy || name.trim().length < 3}>
              Found
            </button>
          </form>
        </>
      )}
    </div>
  );
}
