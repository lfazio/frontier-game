// The commitment step (UX §5): what it costs, what it leaves, and one deliberate confirm.
// Nothing here changes local state — the caller renders whatever the server sends back.

export interface Plan {
  title: string;
  steps: number;
  ap: number;
  fuel: number;
  verb: string;
}

export function PlanPanel({ plan, ap, fuel, busy, onGo, onCancel }: {
  plan: Plan;
  ap: number;
  fuel: number;
  busy: boolean;
  onGo: () => void;
  onCancel: () => void;
}) {
  const apAfter = ap - plan.ap;
  const fuelAfter = fuel - plan.fuel;
  const short = apAfter < 0 || fuelAfter < 0;

  return (
    <div className="plan">
      <b>{plan.title}</b>
      {plan.steps > 0 && (
        <div className="beads" aria-hidden="true">
          {Array.from({ length: Math.min(plan.steps, 12) }, (_, i) => (
            <i key={i} />
          ))}
        </div>
      )}
      <p className="cost num">
        <span className={apAfter < 0 ? "hurt" : ""}>{plan.ap} AP</span>
        {plan.fuel > 0 && <> · <span className={fuelAfter < 0 ? "hurt" : ""}>{plan.fuel} fuel</span></>}
        <span className="dim">
          {"  leaves "}
          {Math.max(apAfter, 0)} AP{plan.fuel > 0 && ` · ${Math.max(fuelAfter, 0)} fuel`}
        </span>
      </p>
      {/* Stated before commitment, so the refusal is never a surprise. */}
      {short && <p className="quiet small">Not enough for this. More Action Points at the next cycle.</p>}
      <div className="buttons">
        <button className="go" disabled={busy || short} onClick={onGo}>
          {busy ? "…" : plan.verb}
        </button>
        <button disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export function ActionBar({ actions }: {
  actions: { label: string; hint?: string; disabled?: boolean; onClick: () => void }[];
}) {
  return (
    <div className="actions">
      {actions.map((action) => (
        <button key={action.label} disabled={action.disabled} title={action.hint} onClick={action.onClick}>
          {action.label}
        </button>
      ))}
    </div>
  );
}
