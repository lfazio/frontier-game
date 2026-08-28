import type { Rules } from "./play/commands";

// Everything the watch view is allowed to ask for. A spectator has no account and no ship, so
// this is the whole surface: the star chart, who holds it, and public events (UX §9).

export interface Overview {
  world_day: number;
  phase: string;
  galaxy: string;
  systems: number;
  pilots: number;
  crews: number;
}

export interface TileEntry {
  id: string;
  path: string;
  kind: string;
  name: string | null;
  q: number;
  r: number;
  controller?: number;
}

export interface Tile {
  path: string;
  level: number;
  world_day: number;
  entries: TileEntry[];
}

export interface FeedEvent {
  id: string;
  world_day: number;
  occurred_at: string;
  type: string;
  origin: string;
  scope: number;
  quality: string;
  channel: string;
  payload: Record<string, unknown>;
}

async function get<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return (await response.json()) as T;
}

export const api = {
  overview: () => get<Overview>("/v1/watch/overview"),
  tile: (path: string) => get<Tile>(`/v1/watch/map?path=${encodeURIComponent(path)}`),
  feed: () => get<{ events: FeedEvent[] }>("/v1/watch/feed"),
};

/** `ga0_0/re1_0/sy4_2` -> the path one level up, or null at the galaxy. */
export function parentOf(path: string): string | null {
  const steps = path.split("/");
  return steps.length > 1 ? steps.slice(0, -1).join("/") : null;
}

export const FACTIONS: Record<number, { name: string; letter: string; tint: string }> = {
  1: { name: "Empire", letter: "E", tint: "#c2603f" },
  2: { name: "Republic", letter: "R", tint: "#3f7fc2" },
  3: { name: "Pirates", letter: "P", tint: "#8a6bbf" },
};

// ---------------------------------------------------------------------------
// Signed-in surface (UX §10). Everything below needs a token.

export interface Me {
  world_day: number;
  phase: string;
  unread: number;
  digest: { events: Record<string, number>; total: number } | null;
  player: {
    id: string;
    callsign: string;
    ap: number;
    credits: number;
    knowledge: number;
    faction_id: number | null;
    team_id: string | null;
    team_name: string | null;
  };
  ship: {
    id: string;
    position: string;
    hull: number;
    fuel: number;
    docked: boolean;
    docked_at: string | null;
    jump_range_ly: number;
    in_transit: boolean;
    hull_max: number;
    shields: number;
    shields_max: number;
    sensor_range: number;
    fuel_max: number;
    cargo_max: number;
  };
  cargo: CargoItem[];
}

export interface Body {
  id: string;
  path: string;
  kind: string;
  name: string | null;
  q: number;
  r: number;
  in_sight: boolean;
  charted_on: number | null;
}

export interface Contact {
  quality: "full" | "partial";
  ship_id: string | null;
  position: string;
  name: string | null;
  kind: string | null;
  docked: boolean | null;
}

export interface Orders {
  posture: "evade" | "defend" | "aggressive" | "surrender_cargo";
  engage_hostile: boolean;
  engage_above_cargo: number | null;
  retreat_at_hull_pct: number;
  auto_reply: string | null;
}

export interface SystemView {
  system: { id: string; path: string; name: string | null; controller: number | null; radius: number };
  you: { position: string; sensor_range: number; docked_at: string | null };
  bodies: Body[];
  contacts: Contact[];
}

export interface MarketLine {
  commodity: string;
  stock: number;
  buy: number;
  sell: number;
  held: number;
  avg_paid: number | null;
}

export interface CargoItem {
  commodity: string;
  qty: number;
  avg_paid: number;
}

export interface MarketView {
  station: {
    id: string;
    name: string | null;
    kind: string | null;
    produces: string | null;
    consumes: string | null;
    controller: number | null;
  };
  you: {
    docked: boolean;
    credits: number;
    ap: number;
    hold_used: number;
    hold_max: number;
    hull: number;
    hull_max: number;
    repair_cost: number;
  };
  commodities: MarketLine[];
  cargo: CargoItem[];
}

export interface Mission {
  id: string;
  kind: string;
  faction_id: number;
  brief: string;
  system: string;
  system_name: string | null;
  reward_credits: number;
  reward_reputation: number;
  expires_on: number;
}

export interface MissionBoard {
  faction_id: number | null;
  reputation: Record<number, number>;
  mine: Mission[];
  offers: Mission[];
}

export interface TeamRow {
  id: string;
  name: string;
  faction_id: number;
  founded_on: number;
  members: number;
  defected_on: number | null;
}

export class Refused extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(code);
  }
}

async function authed<T>(url: string, token: string): Promise<T> {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Refused(response.status, body.code ?? String(response.status));
  }
  return (await response.json()) as T;
}

export const play = {
  register: async (email: string, password: string, callsign: string): Promise<string> =>
    post("/v1/auth/register", { email, password, callsign }),
  login: async (email: string, password: string): Promise<string> =>
    post("/v1/auth/login", { email, password }),
  me: (token: string) => authed<Me>("/v1/me", token),
  tile: (token: string, path: string) =>
    authed<Tile>(`/v1/map/tiles?path=${encodeURIComponent(path)}`, token),
  system: (token: string, id: string) => authed<SystemView>(`/v1/systems/${id}`, token),
  rules: (token: string) => authed<Rules>("/v1/rules", token),
  market: (token: string, stationId: string) =>
    authed<MarketView>(`/v1/stations/${stationId}/market`, token),
  feed: (token: string, after?: string) =>
    authed<{ events: FeedEvent[]; cursor: string | null }>(
      after ? `/v1/feed?after=${after}` : "/v1/feed",
      token,
    ),
  missions: (token: string) => authed<MissionBoard>("/v1/missions", token),
  teams: (token: string) => authed<{ yours: string | null; teams: TeamRow[] }>("/v1/teams", token),
  orders: (token: string) => authed<Orders>("/v1/orders", token),
};

async function post(url: string, body: unknown): Promise<string> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Refused(response.status, payload.detail ?? payload.code ?? "FAILED");
  return payload.access_token as string;
}

/** `ga0_0/re1_0/sy4_2/pl3_1` -> its axial pair. */
export function tipOf(path: string): { q: number; r: number } {
  const last = path.split("/").pop() ?? "";
  const [q, r] = last.slice(2).split("_").map((n) => (n.startsWith("n") ? -Number(n.slice(1)) : Number(n)));
  return { q, r };
}

export function hexDistance(a: { q: number; r: number }, b: { q: number; r: number }): number {
  return (Math.abs(a.q - b.q) + Math.abs(a.r - b.r) + Math.abs(a.q + a.r - b.q - b.r)) / 2;
}
