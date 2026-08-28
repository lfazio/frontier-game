import { useCallback, useEffect, useState } from "react";
import { FACTIONS, play, type MarketView, type Me } from "../api";
import { act, newKey, outcomeText, type Rules } from "./commands";

// The station screen (UX §6). The most numeric screen in the game, and the rule is that the
// player never does arithmetic the interface could do: every total, every remainder and both
// sides of the spread are on screen before anything is committed.

type Side = "buy" | "sell";

export function Station({ token, me, rules, onActed }: {
  token: string;
  me: Me;
  rules: Rules | null;
  onActed: () => void;
}) {
  const [view, setView] = useState<MarketView | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [side, setSide] = useState<Side>("buy");
  const [picked, setPicked] = useState<string | null>(null);
  const [qty, setQty] = useState(1);

  const berth = me.ship.docked_at;

  const reload = useCallback(() => {
    if (!berth) return;
    setFailure(null);
    play
      .market(token, berth)
      .then(setView)
      .catch(() => setFailure("That berth is not answering."));
  }, [token, berth]);

  useEffect(reload, [reload]);

  if (!berth) {
    return (
      <div className="station">
        <p className="quiet">You are not docked. Dock at a station to trade and repair.</p>
      </div>
    );
  }
  if (failure) return <p className="quiet">{failure}</p>;
  if (!view) return <p className="quiet">Reading the market…</p>;

  const line = view.commodities.find((c) => c.commodity === picked) ?? null;
  const unit = line ? (side === "buy" ? line.buy : line.sell) : 0;
  const total = unit * qty;
  const free = view.you.hold_max - view.you.hold_used;
  // Both ceilings the player would otherwise work out by hand, one click away.
  const affordable = line ? Math.floor(view.you.credits / line.buy) : 0;
  const most = side === "buy" ? Math.min(affordable, free, line?.stock ?? 0) : (line?.held ?? 0);

  async function run(what: () => Promise<string>) {
    setBusy(true);
    try {
      setSaid(await what());
      onActed();
      reload();
    } catch {
      setSaid("Could not reach the server. Nothing was sent.");
    } finally {
      setBusy(false);
    }
  }

  function trade() {
    if (!line) return;
    const commodity = line.commodity;
    const amount = qty;
    const selling = side === "sell";
    void run(async () => {
      const outcome = selling
        ? await act.sell(token, commodity, amount, newKey())
        : await act.buy(token, commodity, amount, newKey());
      if (outcome.stopped) return outcomeText(outcome, me.ship.position);
      const paid = outcome.events[0]?.payload?.unit_price as number | undefined;
      const each = paid ?? unit;
      return selling
        ? `Sold ${amount} ${commodity} for ${each * amount} cr.`
        : `Bought ${amount} ${commodity} for ${each * amount} cr.`;
    });
  }

  const damaged = view.you.hull < view.you.hull_max;

  return (
    <div className="station">
      <header className="stationhead">
        <b>{view.station.name ?? "Station"}</b>
        {view.station.kind && <span className="dim"> · {view.station.kind.replace("_", " ")}</span>}
        {view.station.controller && (
          <span className="dim"> · {FACTIONS[view.station.controller]?.name}</span>
        )}
        <span className="spacer" />
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const outcome = await act.launch(token, newKey());
              return outcome.stopped ? outcomeText(outcome, me.ship.position) : "Under way.";
            })
          }
        >
          Launch
        </button>
      </header>

      {said && (
        <p className="said" role="status">
          {said} <button className="link" onClick={() => setSaid(null)}>Dismiss</button>
        </p>
      )}

      <div className="marketgrid">
        <table className="market">
          <caption className="dim small">
            {view.station.produces && `Produces ${view.station.produces}`}
            {view.station.consumes && ` · consumes ${view.station.consumes}`}
          </caption>
          <thead>
            <tr>
              <th scope="col">Commodity</th>
              <th scope="col" className="n">Stock</th>
              <th scope="col" className="n">Buy</th>
              <th scope="col" className="n">Sell</th>
              <th scope="col" className="n">Held</th>
              <th scope="col" className="n">Avg paid</th>
            </tr>
          </thead>
          <tbody>
            {view.commodities.map((c) => (
              <tr
                key={c.commodity}
                className={c.commodity === picked ? "on" : ""}
                onClick={() => {
                  setPicked(c.commodity);
                  setQty(1);
                }}
              >
                <th scope="row">
                  <button className="link plain">{c.commodity.replace("_", " ")}</button>
                </th>
                <td className="n num">{c.stock}</td>
                <td className="n num">{c.buy}</td>
                <td className="n num">{c.sell}</td>
                <td className="n num">{c.held || "—"}</td>
                {/* Profit must be visible without a spreadsheet (UX §6). */}
                <td className="n num">{c.avg_paid ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <aside className="ledger">
          <p>
            <span className="dim">Hold</span>{" "}
            <b className="num">
              {view.you.hold_used} / {view.you.hold_max}
            </b>
          </p>
          <p>
            <span className="dim">Credits</span> <b className="num">{view.you.credits}</b>
          </p>
          <p>
            <span className="dim">AP</span>{" "}
            <b className="num">
              {view.you.ap} / {rules?.ap.daily_grant ?? 10}
            </b>
          </p>
          <p>
            <span className="dim">Hull</span>{" "}
            <b className="num">
              {view.you.hull} / {view.you.hull_max}
            </b>
          </p>
          {damaged ? (
            <button
              className="go"
              disabled={busy || view.you.credits < view.you.repair_cost}
              onClick={() =>
                void run(async () => {
                  const outcome = await act.repair(token, newKey());
                  return outcome.stopped
                    ? outcomeText(outcome, me.ship.position)
                    : `Hull repaired for ${view.you.repair_cost} cr.`;
                })
              }
            >
              Repair · {view.you.repair_cost} cr
            </button>
          ) : (
            <p className="dim small">Hull intact.</p>
          )}
        </aside>
      </div>

      <div className="trade">
        {line ? (
          <>
            <div className="sides">
              {(["buy", "sell"] as Side[]).map((option) => (
                <button
                  key={option}
                  className={side === option ? "on" : ""}
                  onClick={() => {
                    setSide(option);
                    setQty(1);
                  }}
                >
                  {option === "buy" ? "Buy" : "Sell"}
                </button>
              ))}
              <b>{line.commodity.replace("_", " ")}</b>
            </div>

            <div className="stepper">
              <button disabled={qty <= 1} onClick={() => setQty(qty - 1)} aria-label="One fewer">
                −
              </button>
              <label>
                <span className="visually-hidden">Quantity</span>
                <input
                  type="number"
                  min={1}
                  value={qty}
                  onChange={(event) => setQty(Math.max(1, Number(event.target.value) || 1))}
                />
              </label>
              <button disabled={qty >= most} onClick={() => setQty(qty + 1)} aria-label="One more">
                +
              </button>
              <button className="link" disabled={most < 1} onClick={() => setQty(most)}>
                {side === "buy" ? `Max ${most}` : `All ${most}`}
              </button>
            </div>

            <p className="cost num">
              {total} cr · {rules?.ap.cost.trade ?? 1} AP
              <span className="dim">
                {"  leaves "}
                {side === "buy" ? view.you.credits - total : view.you.credits + total} cr · hold{" "}
                {side === "buy" ? view.you.hold_used + qty : view.you.hold_used - qty} /{" "}
                {view.you.hold_max}
              </span>
            </p>

            <button className="go" disabled={busy || qty < 1 || qty > most} onClick={trade}>
              {busy ? "…" : side === "buy" ? "Buy" : "Sell"}
            </button>
            {most < 1 && (
              <p className="quiet small">
                {side === "buy"
                  ? free < 1
                    ? "The hold is full."
                    : "Not enough credits, or the station has none to sell."
                  : "You are not carrying any."}
              </p>
            )}
          </>
        ) : (
          <p className="dim small">Pick a commodity to trade.</p>
        )}
      </div>
    </div>
  );
}

export function Hold({ me }: { me: Me }) {
  if (me.cargo.length === 0) return <p className="dim small">The hold is empty.</p>;
  return (
    <ul className="rows" aria-label="Cargo hold">
      {me.cargo.map((item) => (
        <li key={item.commodity} className="row">
          <span className="num">{item.qty}</span> {item.commodity.replace("_", " ")}
          <span className="dim small"> · paid {item.avg_paid} each</span>
        </li>
      ))}
    </ul>
  );
}
