import { useEffect, useState } from "react";
import { FACTIONS, parentOf, play, type Me, type SystemView, type Tile, type TileEntry } from "../api";
import { HexMap } from "../HexMap";
import { Board, contactLine } from "./Board";

// One map, three magnifications (UX §4). Zoom changes resolution, never mode: galaxy and
// region come from tiles, and the system is the sight-bounded board.

type Cell = { q: number; r: number; steps: number };

export function MapView({ token, me }: { token: string; me: Me }) {
  const systemPath = parentOf(me.ship.position) ?? "";
  const [path, setPath] = useState(systemPath);
  const [tile, setTile] = useState<Tile | null>(null);
  const [view, setView] = useState<SystemView | null>(null);
  const [chosen, setChosen] = useState<TileEntry | null>(null);
  const [cell, setCell] = useState<Cell | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const depth = path.split("/").length; // 1 galaxy · 2 region · 3 system
  const inSystem = depth >= 3;

  useEffect(() => {
    setFailure(null);
    if (!inSystem) {
      play.tile(token, path).then(setTile).catch(() => setFailure("Could not read the chart."));
      return;
    }
    // A system is looked inside by id, and the chart of its region is where the id comes from.
    const region = parentOf(path);
    if (!region) return;
    play
      .tile(token, region)
      .then((chart) => {
        const entry = chart.entries.find((e) => e.path === path);
        if (!entry) {
          setFailure("Not surveyed. Scan from within the system to chart it.");
          return;
        }
        return play.system(token, entry.id).then(setView);
      })
      .catch(() => setFailure("You are not in that system."));
  }, [path, token, inSystem]);

  const crumbs: string[] = [];
  for (let cut = 1; cut <= Math.min(depth, 3); cut += 1) {
    crumbs.push(path.split("/").slice(0, cut).join("/"));
  }

  return (
    <div className="mapview">
      <div className="crumbs">
        {["galaxy", "region", "system"].map((label, i) => (
          <button
            key={label}
            className={i === depth - 1 ? "on" : ""}
            disabled={i >= crumbs.length}
            onClick={() => setPath(crumbs[i] ?? path)}
          >
            {label}
          </button>
        ))}
        <code className="dim">{path}</code>
        <span className="spacer" />
        <button onClick={() => setPath(systemPath)}>Centre on me</button>
      </div>

      {failure && <p className="quiet">{failure}</p>}

      {inSystem ? (
        view && (
          <div className="map">
            <Board view={view} selected={cell} onSelect={setCell} />
            <div className="chart">
              <h3>
                {view.system.name ?? "This system"}
                {view.system.controller && (
                  <span className="dim"> · {FACTIONS[view.system.controller]?.name}</span>
                )}
              </h3>
              <p className="dim small">
                Sight {view.you.sensor_range} hexes · {view.contacts.length}{" "}
                {view.contacts.length === 1 ? "contact" : "contacts"}
              </p>

              {/* The map as text: the only way a canvas can be perceived by a screen reader. */}
              <ul aria-label="What is in range, nearest first">
                {view.contacts.map((c, i) => (
                  <li key={`c${i}`} className="row">
                    <span className="tag warn">contact</span> {contactLine(c)}
                  </li>
                ))}
                {view.bodies.map((b) => (
                  <li key={b.id} className="row">
                    <span className={b.in_sight ? "tag" : "tag dim"}>
                      {b.in_sight ? "in sight" : `charted d${b.charted_on ?? "?"}`}
                    </span>{" "}
                    {b.name ?? b.kind}
                  </li>
                ))}
              </ul>

              <div className="selected">
                {cell ? (
                  <>
                    <b>{cell.steps === 0 ? "Your hex" : `${cell.steps} hexes out`}</b>
                    <p className="dim small">
                      Selecting costs nothing. Flying is a separate, deliberate action.
                    </p>
                  </>
                ) : (
                  <p className="dim small">Click a hex inside the sight boundary.</p>
                )}
              </div>
            </div>
          </div>
        )
      ) : (
        <>
          <HexMap tile={tile} onSelect={setChosen} selected={chosen?.path ?? null} />
          {chosen && (
            <div className="detail">
              <b>{chosen.name ?? chosen.kind}</b> · {chosen.kind} · <code>{chosen.path}</code>
              {chosen.kind === "system" && (
                <button onClick={() => setPath(chosen.path)}>Look inside</button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
