import { useCallback, useEffect, useMemo, useState } from "react";
import { FACTIONS, parentOf, play, tipOf, type Me, type SystemView, type Tile, type TileEntry } from "../api";
import { HexMap } from "../HexMap";
import { ActionBar, PlanPanel, type Plan } from "./Act";
import { Board, contactLine } from "./Board";
import { act, jumpCost, line, newKey, outcomeText, siblingOf, type Rules } from "./commands";

// One map, three magnifications (UX §4). Zoom changes resolution, never mode: galaxy and
// region come from tiles, and the system is the sight-bounded board.

type Cell = { q: number; r: number; steps: number };
type Pending = { plan: Plan; run: () => Promise<string> };

export function MapView({ token, me, rules, onActed }: {
  token: string;
  me: Me;
  rules: Rules | null;
  onActed: () => void;
}) {
  const systemPath = parentOf(me.ship.position) ?? "";
  const [path, setPath] = useState(systemPath);
  const [tile, setTile] = useState<Tile | null>(null);
  const [view, setView] = useState<SystemView | null>(null);
  const [chosen, setChosen] = useState<TileEntry | null>(null);
  const [cell, setCell] = useState<Cell | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);

  const depth = path.split("/").length; // 1 galaxy · 2 region · 3 system
  const inSystem = depth >= 3;
  const here = tipOf(me.ship.position);

  const reload = useCallback(() => {
    setFailure(null);
    if (!inSystem) {
      play.tile(token, path).then(setTile).catch(() => setFailure("Could not read the chart."));
      return;
    }
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

  useEffect(reload, [reload, me.ship.position]);

  // The drawn path and the submitted path are the same list, produced by the server's own rule.
  const route = useMemo(
    () => (cell && cell.steps > 0 && !me.ship.docked ? line(here, cell) : undefined),
    [cell, here.q, here.r, me.ship.docked],
  );

  async function commit(pendingAction: Pending) {
    setBusy(true);
    try {
      setSaid(await pendingAction.run());
      setPending(null);
      setCell(null);
      onActed();
      reload();
    } catch {
      setSaid("Could not reach the server. Nothing was sent.");
    } finally {
      setBusy(false);
    }
  }

  function planRoute() {
    if (!route || !rules) return;
    const hops = route.slice(1).map((hop) => ({ to: siblingOf(me.ship.position, hop), idempotency_key: newKey() }));
    const steps = hops.length;
    setPending({
      plan: {
        title: `Route · ${steps} ${steps === 1 ? "hex" : "hexes"}`,
        steps,
        ap: steps * (rules.ap.cost.move_hex ?? 0),
        fuel: steps * rules.world.fuel_per_hex,
        verb: "Fly",
      },
      // Keys are minted here, once per intent, so a retry finishes the route rather than repeating it.
      run: async () => {
        const outcome = await act.route(token, hops);
        const landed = await play.me(token);
        return outcomeText(outcome, landed.ship.position);
      },
    });
  }

  function planJump(target: TileEntry) {
    if (!rules) return;
    const cost = jumpCost(rules, systemPath, target.path);
    setPending({
      plan: {
        title: `Jump · ${target.name ?? "system"} · ${cost.ly} ly`,
        steps: 0,
        ap: cost.ap,
        fuel: cost.fuel,
        verb: "Jump",
      },
      run: async () => {
        const outcome = await act.jump(token, target.path, newKey());
        if (outcome.stopped) return outcomeText(outcome, me.ship.position);
        return "Jump laid in. You arrive at the next cycle.";
      },
    });
  }

  const stationHere =
    view?.bodies.find((b) => b.kind === "station" && b.q === here.q && b.r === here.r) ?? null;

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
      {said && (
        <p className="said" role="status">
          {said} <button className="link" onClick={() => setSaid(null)}>Dismiss</button>
        </p>
      )}

      {inSystem ? (
        view && (
          <div className="map">
            <Board view={view} selected={cell} onSelect={setCell} route={route} />
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

              <ActionBar
                actions={[
                  {
                    label: `Scan · ${rules?.ap.cost.scan ?? "?"} AP`,
                    disabled: busy || !rules,
                    hint: "Chart what is in range",
                    onClick: () =>
                      commit({
                        plan: { title: "Scan", steps: 0, ap: rules?.ap.cost.scan ?? 0, fuel: 0, verb: "Scan" },
                        run: async () => {
                          const outcome = await act.scan(token, newKey());
                          return outcome.stopped
                            ? outcomeText(outcome, me.ship.position)
                            : "Scanned. The chart is up to date.";
                        },
                      }),
                  },
                  me.ship.docked
                    ? {
                        label: "Launch",
                        disabled: busy,
                        onClick: () =>
                          commit({
                            plan: { title: "Launch", steps: 0, ap: 0, fuel: 0, verb: "Launch" },
                            run: async () => {
                              const outcome = await act.launch(token, newKey());
                              return outcome.stopped ? outcomeText(outcome, me.ship.position) : "Under way.";
                            },
                          }),
                      }
                    : {
                        label: "Dock",
                        disabled: busy || !stationHere,
                        hint: stationHere ? `Dock at ${stationHere.name ?? "the station"}` : "No station in this hex",
                        onClick: () =>
                          stationHere &&
                          commit({
                            plan: { title: "Dock", steps: 0, ap: 0, fuel: 0, verb: "Dock" },
                            run: async () => {
                              const outcome = await act.dock(token, stationHere.id, newKey());
                              return outcome.stopped
                                ? outcomeText(outcome, me.ship.position)
                                : `Docked at ${stationHere.name ?? "the station"}.`;
                            },
                          }),
                      },
                ]}
              />

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
                {pending ? (
                  <PlanPanel
                    plan={pending.plan}
                    ap={me.player.ap}
                    fuel={me.ship.fuel}
                    busy={busy}
                    onGo={() => void commit(pending)}
                    onCancel={() => setPending(null)}
                  />
                ) : cell && cell.steps > 0 ? (
                  <>
                    <b>{cell.steps} hexes out</b>
                    <p className="dim small">Selecting costs nothing.</p>
                    <button className="go" disabled={me.ship.docked || !rules} onClick={planRoute}>
                      {me.ship.docked ? "Docked — launch first" : "Plot route"}
                    </button>
                  </>
                ) : (
                  <p className="dim small">Click a hex inside the sight boundary to plot a route.</p>
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
                <>
                  <button onClick={() => setPath(chosen.path)}>Look inside</button>
                  {chosen.path !== systemPath && (
                    <button className="go" disabled={!rules || me.ship.docked} onClick={() => planJump(chosen)}>
                      Jump here
                    </button>
                  )}
                </>
              )}
            </div>
          )}
          {pending && (
            <PlanPanel
              plan={pending.plan}
              ap={me.player.ap}
              fuel={me.ship.fuel}
              busy={busy}
              onGo={() => void commit(pending)}
              onCancel={() => setPending(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
