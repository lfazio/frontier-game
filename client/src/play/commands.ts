// Submitting intents (UX §5). The client never computes an outcome: it plots, shows what the
// server's own rule data says a thing costs, submits, and renders what comes back.

import { Refused, hexDistance, tipOf } from "../api";

export interface Rules {
  version: string;
  ap: {
    daily_grant: number;
    carry_over_fraction: number;
    carry_ceiling: number;
    cost: Record<string, number>;
  };
  world: {
    fuel_per_hex: number;
    fuel_per_jump_ly: number;
    jump_range_default_ly: number;
    sensor_range_base: number;
    hull_repair_cost_per_point: number;
  };
}

export interface Outcome {
  requested: number;
  accepted: number;
  stopped: { code: string; context: Record<string, unknown>; at_step: number } | null;
  events: { type: string; payload: Record<string, unknown> }[];
}

// --- the hex line -----------------------------------------------------------
// A port of the server's rule (`domain/hex/geometry.line`), nudge included, so the path drawn
// is the path flown. Half-to-even matches Python's round(); the nudge means ties should never
// arise, and if the two ever disagreed the player would watch a route they did not plot.

function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const rest = value - floor;
  if (rest > 0.5) return floor + 1;
  if (rest < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

function roundCube(x: number, y: number, z: number): { q: number; r: number } {
  let rx = roundHalfEven(x);
  let ry = roundHalfEven(y);
  const rz = roundHalfEven(z);
  const dx = Math.abs(rx - x);
  const dy = Math.abs(ry - y);
  const dz = Math.abs(rz - z);
  if (dx > dy && dx > dz) rx = -ry - rz;
  else if (dy > dz) ry = -rx - rz;
  return { q: rx, r: ry };
}

export function line(a: { q: number; r: number }, b: { q: number; r: number }): { q: number; r: number }[] {
  const steps = hexDistance(a, b);
  if (steps === 0) return [a];
  const [ax, ay, az] = [a.q + 1e-6, a.r + 1e-6, -a.q - a.r - 2e-6];
  const [bx, by, bz] = [b.q, b.r, -b.q - b.r];
  const out: { q: number; r: number }[] = [];
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    out.push(roundCube(ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t));
  }
  return out;
}

/** Replace a path's last hex, keeping its level prefix: a sibling of where you are. */
export function siblingOf(path: string, at: { q: number; r: number }): string {
  const steps = path.split("/");
  const prefix = (steps[steps.length - 1] ?? "").slice(0, 2);
  const write = (n: number) => (n < 0 ? `n${-n}` : String(n));
  steps[steps.length - 1] = `${prefix}${write(at.q)}_${write(at.r)}`;
  return steps.join("/");
}

/** Light years for a jump, by the server's rule — hexes within a region, region-hops times six. */
export function lightYears(from: string, to: string): number {
  const fromRegion = from.split("/").slice(0, -1).join("/");
  const toRegion = to.split("/").slice(0, -1).join("/");
  if (fromRegion === toRegion) return hexDistance(tipOf(from), tipOf(to));
  return hexDistance(tipOf(fromRegion), tipOf(toRegion)) * 6;
}

export function jumpCost(rules: Rules, from: string, to: string) {
  const sameRegion = from.split("/").slice(0, -1).join("/") === to.split("/").slice(0, -1).join("/");
  const ly = lightYears(from, to);
  return {
    ly,
    ap: rules.ap.cost[sameRegion ? "jump_intra_region" : "jump_inter_region"] ?? 0,
    fuel: rules.world.fuel_per_jump_ly * Math.max(1, ly),
  };
}

// --- refusals ---------------------------------------------------------------
// A 409 is an answer, not a failure (UX §5.4): state the fact, then the remedy, never blame.

export function refusalText(code: string, context: Record<string, unknown> = {}): string {
  const need = context.need as number | undefined;
  const have = context.have as number | undefined;
  switch (code) {
    case "INSUFFICIENT_AP":
      return need === undefined
        ? "Not enough Action Points. More at the next cycle."
        : `Not enough Action Points — ${need} needed. More at the next cycle.`;
    case "INSUFFICIENT_FUEL":
      return have === undefined
        ? "Not enough fuel. Refuel at a station."
        : `Not enough fuel — ${need} needed, ${have} in the tank. Refuel at a station.`;
    case "INSUFFICIENT_CREDITS":
      return "Not enough credits.";
    case "NOT_ADJACENT":
      return "Too far for one move. Plot a route instead.";
    case "BEYOND_JUMP_RANGE":
      return `Beyond this ship's jump range — ${context.distance_ly} ly away, range ${context.range_ly} ly.`;
    case "MUST_LAUNCH_FIRST":
      return "You are docked. Launch first.";
    case "ALREADY_DOCKED":
      return "You are already docked here.";
    case "NOT_DOCKED":
      return "You need to be docked for that.";
    case "IN_TRANSIT":
      return "The ship is between systems. It arrives at the next cycle.";
    case "CARGO_FULL":
      return context.free === undefined
        ? "The hold is full."
        : `The hold is full — room for ${context.free} more.`;
    case "INSUFFICIENT_STOCK":
      return `The station has only ${have ?? "a few"} to sell.`;
    case "INSUFFICIENT_CARGO":
      return `You are carrying ${have ?? "fewer"}, not ${need ?? "that many"}.`;
    case "COMMODITY_UNAVAILABLE":
      return "This station does not deal in that.";
    case "TARGET_NOT_VISIBLE":
      return "Nothing there now. Your last sighting is older than the world.";
    case "TARGET_UNKNOWN":
      return "You have no chart for that. Scan, or fly somewhere it is known from.";
    case "UNKNOWN_DESTINATION":
      return "There is nothing at those coordinates.";
    case "SCALE_MISMATCH":
      return "That is not a place you can move to from here.";
    case "WORLD_TICKING":
      return "The galaxy is turning. A moment.";
    default:
      return "That is not possible right now.";
  }
}

// --- submitting -------------------------------------------------------------

export const newKey = (): string =>
  crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`.padEnd(36, "0");

async function send(url: string, token: string, body: unknown, retried = false): Promise<Outcome> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });

  // A tick is not a refusal. The keys are already minted, so one retry is safe and silent.
  if (response.status === 503 && !retried) {
    await new Promise((wake) => setTimeout(wake, 1200));
    return send(url, token, body, true);
  }

  const payload = await response.json().catch(() => ({}));
  if (response.status === 409) {
    return { requested: 1, accepted: 0, events: [], stopped: { code: payload.code ?? "REFUSED", context: payload.context ?? {}, at_step: 0 } };
  }
  if (!response.ok) throw new Refused(response.status, payload.code ?? String(response.status));
  return "accepted" in payload
    ? (payload as Outcome)
    : { requested: 1, accepted: 1, stopped: null, events: payload.events ?? [] };
}

export const act = {
  /** One decision for the player, a sequence for the server (UX §5.3). */
  route: (token: string, hops: { to: string; idempotency_key: string }[]) =>
    send("/v1/commands:batch", token, {
      commands: hops.map((hop) => ({ action: "move", ...hop })),
    }),
  jump: (token: string, to_system: string, key: string) =>
    send("/v1/commands", token, { action: "jump", to_system, idempotency_key: key }),
  scan: (token: string, key: string) =>
    send("/v1/commands", token, { action: "scan", idempotency_key: key }),
  dock: (token: string, station_id: string, key: string) =>
    send("/v1/commands", token, { action: "dock", station_id, idempotency_key: key }),
  launch: (token: string, key: string) =>
    send("/v1/commands", token, { action: "launch", idempotency_key: key }),
  buy: (token: string, commodity: string, qty: number, key: string) =>
    send("/v1/commands", token, { action: "buy", commodity, qty, idempotency_key: key }),
  sell: (token: string, commodity: string, qty: number, key: string) =>
    send("/v1/commands", token, { action: "sell", commodity, qty, idempotency_key: key }),
  repair: (token: string, key: string) =>
    send("/v1/commands", token, { action: "repair", idempotency_key: key }),
};

export function outcomeText(outcome: Outcome, arrivedAt: string): string {
  if (outcome.stopped && outcome.accepted === 0) {
    return refusalText(outcome.stopped.code, outcome.stopped.context);
  }
  if (outcome.stopped) {
    const why = refusalText(outcome.stopped.code, outcome.stopped.context);
    return `Stopped after ${outcome.accepted} of ${outcome.requested} hexes. ${why} You are at ${arrivedAt}.`;
  }
  return outcome.requested > 1 ? `Arrived at ${arrivedAt}.` : "Done.";
}
