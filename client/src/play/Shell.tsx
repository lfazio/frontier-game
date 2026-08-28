import { useCallback, useEffect, useState } from "react";
import { play, Refused, type Me } from "../api";
import type { Rules } from "./commands";
import { MapView } from "./MapView";
import { Overview } from "./Overview";
import { Crew } from "./Crew";
import { FeedView } from "./FeedView";
import { Missions } from "./Missions";
import { Hold, Station } from "./Station";

const POLL_MS = 10000;
const LABEL: Record<string, string> = {
  overview: "Overview",
  map: "Map",
  hold: "Hold",
  feed: "Feed",
  missions: "Work",
  crew: "Crew",
};
type Where = "overview" | "map" | "station" | "hold" | "feed" | "missions" | "crew";

export function Shell({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [where, setWhere] = useState<Where>("overview");
  const [failure, setFailure] = useState<string | null>(null);
  // Costs are balance data, so the client reads them rather than knowing them (GDD §10.4 C4).
  const [rules, setRules] = useState<Rules | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMe(await play.me(token));
      setFailure(null);
    } catch (error) {
      if (error instanceof Refused && error.status === 401) return onSignOut();
      setFailure("Cannot reach the server.");
    }
  }, [token, onSignOut]);

  useEffect(() => {
    play.rules(token).then(setRules).catch(() => setRules(null));
  }, [token]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!me) return <div className="gate">{failure ?? "Reading your day…"}</div>;

  return (
    <div className="shell">
      <header>
        <span className="brand">FRONTIER</span>
        <span className="dim">{me.player.callsign}</span>
        <span className="spacer" />
        {/* AP is never hidden and never behind a hover (UX §2). */}
        <span className="ap" title={`${me.player.ap} of 10 Action Points`}>
          <span className="label">AP</span>
          <span className="pips">
            {Array.from({ length: 10 }, (_, i) => (
              <i key={i} className={i < me.player.ap ? "on" : ""} />
            ))}
          </span>
          <b className="num">
            {me.player.ap} / 10
          </b>
        </span>
        {me.unread > 0 && <span className="tag warn">{me.unread} new</span>}
        <span className="day num">DAY {me.world_day}</span>
        <button onClick={onSignOut}>Sign out</button>
      </header>

      <main className="play">
        <nav className="rail">
          {(["overview", "map", "feed", "missions", "station", "hold", "crew"] as Where[]).map((item) => (
            <button
              key={item}
              className={where === item ? "on" : ""}
              // The berth is named rather than greyed out: a disabled control with no reason is
              // worse than one that says what it is waiting for (UX §5.4).
              title={item === "station" && !me.ship.docked ? "Dock at a station first" : undefined}
              onClick={() => setWhere(item)}
            >
              {item === "station" ? (me.ship.docked ? "Station" : "Station · undocked") : LABEL[item]}
            </button>
          ))}
        </nav>
        <section className="panel">
          {where === "overview" && <Overview me={me} />}
          {where === "map" && (
            <MapView token={token} me={me} rules={rules} onActed={() => void refresh()} />
          )}
          {where === "station" && (
            <Station token={token} me={me} rules={rules} onActed={() => void refresh()} />
          )}
          {where === "hold" && <Hold me={me} />}
          {where === "feed" && <FeedView token={token} me={me} />}
          {where === "missions" && (
            <Missions token={token} me={me} rules={rules} onActed={() => void refresh()} />
          )}
          {where === "crew" && <Crew token={token} me={me} onActed={() => void refresh()} />}
        </section>
      </main>

      <footer className="statusbar">
        <code className="num">{me.ship.position}</code>
        <span className="dim">·</span>
        <span>{me.ship.in_transit ? "in transit" : me.ship.docked ? "docked" : "in flight"}</span>
        <span className="dim">·</span>
        <span className="num">{me.ship.fuel} fuel</span>
        <span className="dim">·</span>
        <span className="num">hull {me.ship.hull}/{me.ship.hull_max}</span>
        <span className="dim">·</span>
        <span className="num">hold {me.cargo.reduce((sum, c) => sum + c.qty, 0)}/{me.ship.cargo_max}</span>
        <span className="dim">·</span>
        <span className="num">{me.player.credits} cr</span>
        <span className="spacer" />
        {failure && <span className="hurt">{failure}</span>}
      </footer>
    </div>
  );
}
