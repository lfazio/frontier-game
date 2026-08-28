import { useCallback, useEffect, useState } from "react";
import { play, type FeedEvent, type Me } from "../api";
import { act, newKey, refusalText } from "./commands";
import { useLive } from "./live";

// One stream, filtered by channel, newest first (UX §7). Live frames and fetched pages are
// merged on event id, so a reconnect that refetches the gap never shows anything twice.

const ICONS: Record<string, string> = {
  MESSAGE: "🚀",
  COMBAT_RESOLVED: "⚔",
  COMBAT_STARTED: "⚔",
  SHIP_DESTROYED: "☠",
  SHIP_ENTERED: "·",
  DISCOVERY: "🔭",
  TERRITORY_CHANGE: "🏛",
  MARKET_SHIFT: "💰",
  TRADE_EXECUTED: "💰",
  MISSION_COMPLETED: "🏛",
  HISTORICAL_EVENT: "⚠",
};

type Channel = "all" | "local" | "system" | "team";

/** What the event says in plain words. A partial sighting stays vague on purpose (UX §7). */
function describe(event: FeedEvent): { who: string; what: string } {
  const p = event.payload as Record<string, unknown>;
  if (event.quality === "partial") {
    return { who: "Unidentified contact", what: "somewhere in this system" };
  }
  switch (event.type) {
    case "MESSAGE":
      return { who: String(p.from ?? "Someone"), what: String(p.text ?? "") };
    case "SHIP_ENTERED":
      return { who: String(p.actor_kind === "npc" ? "A crew" : "A ship"), what: "moved nearby" };
    case "TRADE_EXECUTED":
      return {
        who: "Trade",
        what: `${Number(p.qty) < 0 ? "sold" : "bought"} ${Math.abs(Number(p.qty))} ${p.commodity} at ${p.unit_price}`,
      };
    case "MARKET_SHIFT":
      return { who: String(p.commodity ?? "Prices"), what: "moved" };
    case "COMBAT_RESOLVED":
      return { who: "Combat resolved", what: String(p.outcome ?? "fighting ended") };
    case "SHIP_DESTROYED":
      return { who: "A ship was lost", what: "" };
    case "DISCOVERY":
      return { who: "Charted", what: String(p.name ?? "something new") };
    case "TERRITORY_CHANGE":
      return { who: "Control shifted", what: "" };
    case "MISSION_COMPLETED":
      return { who: "Work finished", what: "" };
    case "SCAN_PERFORMED":
      return { who: "Scan", what: "swept the area" };
    case "AP_GRANTED":
      return { who: "A new cycle", what: "Action Points restored" };
    case "TEAM_JOINED":
      return { who: "A pilot joined a crew", what: "" };
    default:
      return { who: event.type.toLowerCase().replaceAll("_", " "), what: "" };
  }
}

function when(event: FeedEvent, today: number): string {
  if (event.world_day === today) {
    const hours = Math.round((Date.now() - Date.parse(event.occurred_at)) / 3_600_000);
    return hours < 1 ? "now" : `${hours}h`;
  }
  return `day ${event.world_day}`;
}

export function FeedView({ token, me }: { token: string; me: Me }) {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [channel, setChannel] = useState<Channel>("all");
  const [text, setText] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const absorb = useCallback((incoming: FeedEvent[]) => {
    setEvents((have) => {
      const byId = new Map(have.map((e) => [e.id, e]));
      for (const event of incoming) byId.set(event.id, event);
      return [...byId.values()].sort((a, b) => (a.id < b.id ? 1 : -1));
    });
  }, []);

  const link = useLive(token, useCallback((event: FeedEvent) => absorb([event]), [absorb]));

  useEffect(() => {
    play
      .feed(token)
      .then((page) => absorb(page.events))
      .catch(() => undefined);
  }, [token, absorb, link]);

  // The scope a chat message would go to. "all" is a view, not a place to speak from.
  const speakTo = channel === "all" ? "local" : channel;
  const shown = events.filter((event) => channel === "all" || event.channel === channel);

  async function say() {
    const body = text.trim();
    if (!body) return;
    setBusy(true);
    try {
      const outcome = await act.say(token, speakTo, body, newKey());
      if (outcome.stopped) {
        setSaid(refusalText(outcome.stopped.code, outcome.stopped.context));
      } else {
        setText("");
        setSaid(null);
        absorb((outcome.events ?? []) as FeedEvent[]);
      }
    } catch {
      setSaid("Could not reach the server. Nothing was sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="feedview">
      <div className="channels">
        {(["all", "local", "system", "team"] as Channel[]).map((option) => (
          <button
            key={option}
            className={channel === option ? "on" : ""}
            disabled={option === "team" && !me.player.team_id}
            title={option === "team" && !me.player.team_id ? "You are not in a crew" : undefined}
            onClick={() => setChannel(option)}
          >
            {option}
          </button>
        ))}
        <span className="spacer" />
        <span className={`link-state ${link}`}>{link === "live" ? "live" : link}</span>
      </div>

      {shown.length === 0 ? (
        <p className="quiet">Nothing on this channel yet.</p>
      ) : (
        <ul className="feed" aria-label={`Feed, ${channel}`}>
          {shown.map((event) => {
            const said = describe(event);
            return (
              <li key={event.id}>
                <span className="icon" aria-hidden="true">
                  {ICONS[event.type] ?? "·"}
                </span>
                <span className="what">
                  <b>{said.who}</b>
                  {said.what && <> {said.what}</>}
                </span>
                <span className="when">{when(event, me.world_day)}</span>
              </li>
            );
          })}
        </ul>
      )}

      {said && <p className="said">{said}</p>}

      <form
        className="composer"
        onSubmit={(submit) => {
          submit.preventDefault();
          void say();
        }}
      >
        <label className="visually-hidden" htmlFor="say">
          Say something on the {speakTo} channel
        </label>
        <input
          id="say"
          value={text}
          maxLength={500}
          placeholder={me.ship.in_transit ? "In transit — the radio is out of reach" : `Say something on ${speakTo}…`}
          disabled={busy || me.ship.in_transit}
          onChange={(change) => setText(change.target.value)}
        />
        <button className="go" disabled={busy || !text.trim() || me.ship.in_transit}>
          Send
        </button>
      </form>
    </div>
  );
}
