import { useCallback, useEffect, useState } from "react";
import { play, type Me, type Orders as Standing } from "../api";
import { act, newKey, outcomeText } from "./commands";

// What the ship does while nobody is flying it (GDD §4.4). Every interaction has an offline
// path, and this screen is where the player writes theirs — so it opens with what is already
// set, never with a blank form that would quietly replace it.

const POSTURES: { value: Standing["posture"]; label: string; what: string }[] = [
  { value: "evade", label: "Evade", what: "Run. You keep the ship and usually the cargo." },
  { value: "defend", label: "Defend", what: "Fight back if attacked, but never start one." },
  { value: "aggressive", label: "Aggressive", what: "Engage what your orders below allow." },
  { value: "surrender_cargo", label: "Surrender cargo", what: "Hand over the hold rather than fight." },
];

export function Orders({ token, me, onActed }: { token: string; me: Me; onActed: () => void }) {
  const [orders, setOrders] = useState<Standing | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    play.orders(token).then(setOrders).catch(() => setSaid("Could not read your orders."));
  }, [token]);

  useEffect(reload, [reload]);

  if (!orders) return <p className="quiet">Reading your standing orders…</p>;

  const edit = (patch: Partial<Standing>) => setOrders({ ...orders, ...patch });

  async function save() {
    if (!orders) return;
    setBusy(true);
    try {
      const outcome = await act.setOrders(
        token,
        {
          posture: orders.posture,
          engage_hostile: orders.engage_hostile,
          engage_above_cargo: orders.engage_above_cargo,
          retreat_at_hull_pct: orders.retreat_at_hull_pct,
          auto_reply: orders.auto_reply,
        },
        newKey(),
      );
      setSaid(outcome.stopped ? outcomeText(outcome, me.ship.position) : "Orders set.");
      onActed();
      reload();
    } catch {
      setSaid("Could not reach the server. Nothing was sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="orders">
      <p className="dim small">
        These stand whether you are here or not. An absent pilot is resolved from them under the
        same rules as everyone else.
      </p>

      {said && (
        <p className="said" role="status">
          {said} <button className="link" onClick={() => setSaid(null)}>Dismiss</button>
        </p>
      )}

      <fieldset>
        <legend>If something finds you</legend>
        {POSTURES.map((option) => (
          <label key={option.value} className="choice">
            <input
              type="radio"
              name="posture"
              checked={orders.posture === option.value}
              onChange={() => edit({ posture: option.value })}
            />
            <span>
              <b>{option.label}</b>
              <span className="dim small"> — {option.what}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>When you are the one deciding</legend>
        <label className="choice">
          <input
            type="checkbox"
            checked={orders.engage_hostile}
            onChange={(change) => edit({ engage_hostile: change.target.checked })}
          />
          <span>Engage ships already hostile to you</span>
        </label>
        <label className="choice">
          <input
            type="checkbox"
            checked={orders.engage_above_cargo !== null}
            onChange={(change) => edit({ engage_above_cargo: change.target.checked ? 10 : null })}
          />
          <span>Only engage a target carrying at least</span>
        </label>
        {orders.engage_above_cargo !== null && (
          <label className="inline">
            <span className="visually-hidden">Minimum cargo</span>
            <input
              type="number"
              min={0}
              max={10000}
              value={orders.engage_above_cargo}
              onChange={(change) => edit({ engage_above_cargo: Number(change.target.value) || 0 })}
            />
            <span className="dim small">units of cargo</span>
          </label>
        )}
      </fieldset>

      <fieldset>
        <legend>Break off at</legend>
        <label className="inline">
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={orders.retreat_at_hull_pct}
            onChange={(change) => edit({ retreat_at_hull_pct: Number(change.target.value) })}
          />
          <b className="num">{orders.retreat_at_hull_pct}%</b>
          <span className="dim small">hull remaining</span>
        </label>
      </fieldset>

      <fieldset>
        <legend>Say, if hailed</legend>
        <label>
          <span className="visually-hidden">Automatic reply</span>
          <input
            value={orders.auto_reply ?? ""}
            maxLength={200}
            placeholder="Nothing"
            onChange={(change) => edit({ auto_reply: change.target.value || null })}
          />
        </label>
      </fieldset>

      <button className="go" disabled={busy} onClick={() => void save()}>
        {busy ? "…" : "Set orders"}
      </button>
      <span className="dim small"> · free</span>
    </div>
  );
}
