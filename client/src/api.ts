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
