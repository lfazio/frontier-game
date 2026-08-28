import { useCallback, useEffect, useState } from "react";
import { session } from "./session";
import { Auth } from "./play/Auth";
import { Shell } from "./play/Shell";
import { api, parentOf, type FeedEvent, type Overview, type Tile, type TileEntry } from "./api";
import { Feed } from "./Feed";
import { HexMap } from "./HexMap";

const POLL_MS = 5000;

export function App() {
  // Two audiences, one codebase (UX §1): a spectator needs no account, a pilot needs a token.
  const [token, setToken] = useState<string | null>(session.token());
  const [watching, setWatching] = useState(!session.token());

  if (token && !watching) {
    return (
      <Shell
        token={token}
        onSignOut={() => {
          session.end();
          setToken(null);
          setWatching(true);
        }}
      />
    );
  }
  if (!watching) {
    return (
      <Auth
        onToken={(next) => {
          session.begin(next);
          setToken(next);
        }}
      />
    );
  }
  return <Watch onPlay={() => setWatching(false)} />;
}

function Watch({ onPlay }: { onPlay: () => void }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [tile, setTile] = useState<Tile | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [selected, setSelected] = useState<TileEntry | null>(null);
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [failure, setFailure] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [next, feed] = await Promise.all([api.overview(), api.feed()]);
      setOverview(next);
      setEvents(feed.events);
      setFailure(null);
      setPath((current) => current ?? next.galaxy);
    } catch (error) {
      setFailure(String(error));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!path) return;
    void api
      .tile(path)
      .then(setTile)
      .catch((error) => setFailure(String(error)));
  }, [path, overview?.world_day]);

  const parent = path ? parentOf(path) : null;

  return (
    <div className="shell">
      <header>
        <span className="brand">FRONTIER</span>
        <span className="mode">watching</span>
        <button onClick={onPlay}>Play</button>
        <span className="spacer" />
        {overview && (
          <>
            <span className="stat">
              <b>{overview.systems}</b> systems
            </span>
            <span className="stat">
              <b>{overview.pilots}</b> pilots
            </span>
            <span className="stat">
              <b>{overview.crews}</b> crews
            </span>
            <span className="day">DAY {overview.world_day}</span>
            <span className={overview.phase === "ticking" ? "phase turning" : "phase"}>
              {overview.phase === "ticking" ? "the galaxy is turning" : "live"}
            </span>
          </>
        )}
      </header>

      <main>
        <section className="panel">
          <div className="crumbs">
            <button disabled={!parent} onClick={() => parent && setPath(parent)}>
              ‹ out
            </button>
            <code>{path ?? "…"}</code>
            <button
              disabled={!selected || selected.kind === "system" ? false : true}
              onClick={() => selected && setPath(selected.path)}
            >
              in ›
            </button>
          </div>
          <HexMap tile={tile} onSelect={setSelected} selected={selected?.path ?? null} />
          <footer className="detail">
            {selected ? (
              <>
                <b>{selected.name ?? selected.kind}</b> · {selected.kind} ·{" "}
                <code>{selected.path}</code>
              </>
            ) : (
              "Select a place to see what is known about it."
            )}
          </footer>
        </section>

        <aside className="rail">
          <h2>Universe feed</h2>
          <Feed events={events} />
          <p className="note">
            A spectator has no ship and no sensors, so this view shows the star chart, who holds
            it, and events that already carry across a whole system. Nothing else.
          </p>
        </aside>
      </main>

      {failure && <div className="failure">Cannot reach the server. {failure}</div>}
    </div>
  );
}
