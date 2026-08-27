import type { FeedEvent } from "./api";

const ICONS: Record<string, string> = {
  COMBAT_RESOLVED: "⚔",
  COMBAT_STARTED: "⚔",
  SHIP_DESTROYED: "☠",
  DISCOVERY: "🔭",
  TERRITORY_CHANGE: "🏛",
  MARKET_SHIFT: "💰",
  MISSION_COMPLETED: "🏛",
  HISTORICAL_EVENT: "⚠",
  TEAM_DEFECTED: "🏛",
};

/** Plain wording, no jargon: what a spectator is told about an event they cannot inspect. */
function describe(event: FeedEvent): string {
  switch (event.type) {
    case "DISCOVERY":
      return "Something was charted";
    case "TERRITORY_CHANGE":
      return "Control shifted";
    case "SHIP_DESTROYED":
      return "A ship was lost";
    case "COMBAT_RESOLVED":
      return "Fighting ended";
    case "MISSION_COMPLETED":
      return "Work was finished";
    case "HISTORICAL_EVENT":
      return "The region turned";
    default:
      return event.type.toLowerCase().replaceAll("_", " ");
  }
}

export function Feed({ events }: { events: FeedEvent[] }) {
  if (events.length === 0) {
    // Never an empty box: a quiet galaxy says so (UX §3).
    return <p className="quiet">The frontier is quiet.</p>;
  }
  return (
    <ul className="feed" aria-label="Universe feed">
      {events.map((event) => (
        <li key={event.id}>
          <span className="icon" aria-hidden="true">
            {ICONS[event.type] ?? "·"}
          </span>
          <span className="what">{describe(event)}</span>
          <span className="where">{event.origin}</span>
          <span className="when">day {event.world_day}</span>
        </li>
      ))}
    </ul>
  );
}
