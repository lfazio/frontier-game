import { useCallback, useEffect, useState } from "react";
import { FACTIONS, play, type Me, type Mission, type MissionBoard } from "../api";
import { act, newKey, outcomeText, type Rules } from "./commands";

// Work on offer, and the work you hold (GDD §5.5). An offer states its reward and its deadline
// before it is taken, because taking one spends Action Points.

export function Missions({ token, me, rules, onActed }: {
  token: string;
  me: Me;
  rules: Rules | null;
  onActed: () => void;
}) {
  const [board, setBoard] = useState<MissionBoard | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    play.missions(token).then(setBoard).catch(() => setSaid("Could not read the board."));
  }, [token]);

  useEffect(reload, [reload]);

  if (!board) return <p className="quiet">Reading the board…</p>;

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

  const cost = rules?.ap.cost.mission_stage ?? 1;

  function card(mission: Mission, held: boolean) {
    return (
      <li key={mission.id} className="mission">
        <div className="missionhead">
          <b>{mission.brief}</b>
          <span className="spacer" />
          {mission.faction_id && (
            <span className="tag" style={{ borderColor: FACTIONS[mission.faction_id]?.tint }}>
              {FACTIONS[mission.faction_id]?.name ?? mission.faction_id}
            </span>
          )}
        </div>
        <p className="dim small">
          {mission.kind.replaceAll("_", " ")} · {mission.system_name ?? mission.system} · expires day{" "}
          {mission.expires_on}
        </p>
        <p className="num small">
          {mission.reward_credits} cr
          {mission.reward_reputation > 0 && ` · +${mission.reward_reputation} standing`}
          <span className="dim"> · {cost} AP to {held ? "deliver" : "take"}</span>
        </p>
        <button
          className="go"
          disabled={busy || me.player.ap < cost}
          onClick={() =>
            void run(async () => {
              const outcome = held
                ? await act.completeMission(token, mission.id, newKey())
                : await act.acceptMission(token, mission.id, newKey());
              if (outcome.stopped) return outcomeText(outcome, me.ship.position);
              return held ? `Delivered. ${mission.reward_credits} cr paid.` : "Taken. It is on your board.";
            })
          }
        >
          {held ? "Deliver" : "Take"}
        </button>
      </li>
    );
  }

  return (
    <div className="missions">
      {said && (
        <p className="said" role="status">
          {said} <button className="link" onClick={() => setSaid(null)}>Dismiss</button>
        </p>
      )}

      <h3>Your work</h3>
      {board.mine.length === 0 ? (
        <p className="dim small">You are not carrying any work.</p>
      ) : (
        <ul className="cards">{board.mine.map((mission) => card(mission, true))}</ul>
      )}

      <h3>On offer</h3>
      {board.offers.length === 0 ? (
        <p className="quiet">Nothing on offer. The board fills at the turn of the cycle.</p>
      ) : (
        <ul className="cards">{board.offers.map((mission) => card(mission, false))}</ul>
      )}

      {Object.keys(board.reputation).length > 0 && (
        <p className="dim small">
          Standing:{" "}
          {Object.entries(board.reputation)
            .map(([faction, score]) => `${FACTIONS[Number(faction)]?.name ?? faction} ${score}`)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}
