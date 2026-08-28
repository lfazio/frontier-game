// Reading a fight back to the player (UX §5). The server resolves it; this only says what
// happened, and says plainly when the answer will not arrive until the cycle turns.

interface Happened {
  type: string;
  payload: Record<string, unknown>;
}

export function describeCombat(events: Happened[]): string {
  const resolved = events.find((event) => event.type === "COMBAT_RESOLVED");
  if (resolved) {
    const rounds = resolved.payload.rounds;
    const outcome = String(resolved.payload.outcome ?? "it ended");
    return `${outcome}${rounds ? ` after ${rounds} rounds` : ""}.`;
  }
  if (events.some((event) => event.type === "SHIP_DESTROYED")) return "The ship was destroyed.";
  // A fight with another player is queued and resolved for both sides at the tick, so that
  // neither is punished for being the one who was asleep.
  return "Engaged. It resolves when the cycle turns.";
}
