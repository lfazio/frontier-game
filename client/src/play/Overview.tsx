import type { Me } from "../api";

const NAMES: Record<string, string> = {
  SHIP_ENTERED: "ships entered your hex",
  MESSAGE: "messages",
  TRADE_EXECUTED: "trades",
  COMBAT_RESOLVED: "fights resolved",
  SCAN_PERFORMED: "scans",
  DISCOVERY: "discoveries",
  AP_GRANTED: "Action Points granted",
  JOURNEY_COMPLETED: "journeys completed",
};

export function Overview({ me }: { me: Me }) {
  const lines = Object.entries(me.digest?.events ?? {});

  return (
    <div className="overview">
      <div className="daybar">
        <h1 className="day">DAY {me.world_day}</h1>
        <span className="spacer" />
        <span className="dim">{me.phase === "ticking" ? "the galaxy is turning" : "live"}</span>
      </div>

      <section>
        <h2>While you were away</h2>
        {lines.length === 0 ? (
          // Never an empty box — a quiet cycle says so in words (UX §3).
          <p className="quiet">The frontier was quiet.</p>
        ) : (
          <ul className="digest">
            {lines.map(([type, count]) => (
              <li key={type}>
                <span className="count">{count}</span>
                <span>{NAMES[type] ?? type.toLowerCase().replaceAll("_", " ")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="cards">
        <section className="card">
          <h2>You</h2>
          <dl>
            <dt>AP</dt>
            <dd className="num">{me.player.ap} / 10</dd>
            <dt>Credits</dt>
            <dd className="num">{me.player.credits.toLocaleString("en-GB").replaceAll(",", " ")}</dd>
            <dt>Knowledge</dt>
            <dd className="num">{me.player.knowledge}</dd>
            <dt>Hull</dt>
            <dd className="num">
              {me.ship.hull} / 100 {me.ship.hull < 100 && <span className="hurt">damaged</span>}
            </dd>
            <dt>Fuel</dt>
            <dd className="num">{me.ship.fuel} / 60</dd>
          </dl>
        </section>

        <section className="card">
          <h2>Where</h2>
          <dl>
            <dt>Position</dt>
            <dd className="num break">{me.ship.position}</dd>
            <dt>State</dt>
            <dd>{me.ship.docked ? "docked" : "in flight"}</dd>
            <dt>Unread</dt>
            <dd className="num">{me.unread}</dd>
          </dl>
        </section>
      </div>
    </div>
  );
}
