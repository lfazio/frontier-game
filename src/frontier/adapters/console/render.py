"""The console's two screens, rendered on the server — ADMIN §3.1, §3.2.

No build step and no second front-end toolchain: an operator console is an internal tool with a
handful of screens, and a page that arrives finished is one less thing to be broken at 4am.
The palette is the player client's, so the two look like one product.
"""

from __future__ import annotations

from html import escape
from typing import Any

INK, DIM, GROUND, PANEL, LINE, ACCENT = "#d7dde4", "#8b96a3", "#0e1216", "#151b21", "#232c35", "#e8c07d"
GOOD, WARN = "#7bbf8a", "#c2603f"

CAPS = "letter-spacing:.1em;text-transform:uppercase"

CSS = f"""
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: {GROUND}; color: {INK};
       font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, sans-serif; }}
a {{ color: {ACCENT}; text-decoration: none; }}
a:hover {{ color: #f0d3a2; }}
.num {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-variant-numeric: tabular-nums; }}
header {{ display: flex; align-items: center; gap: 16px; padding: 10px 18px;
          border-bottom: 1px solid {LINE}; background: {PANEL}; }}
.brand {{ font-weight: 700; letter-spacing: 0.14em; }}
.mode {{ color: {DIM}; font-style: italic; }}
.spacer {{ flex: 1; }}
nav {{ display: flex; gap: 4px; padding: 8px 18px; border-bottom: 1px solid {LINE}; }}
nav a, .pill {{ padding: 4px 10px; border-radius: 4px; font-size: 13px; letter-spacing: 0.06em;
                text-transform: uppercase; color: {DIM}; }}
nav a.on {{ background: {ACCENT}; color: {GROUND}; }}
.pill.world {{ background: #251f14; color: {ACCENT}; border: 1px solid {ACCENT}; text-transform: none; }}
main {{ padding: 18px; display: flex; flex-direction: column; gap: 16px; }}
.card {{ border: 1px solid {LINE}; border-radius: 6px; background: {PANEL}; }}
.card .row {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px; }}
.card .row + .row {{ border-top: 1px solid {LINE}; }}
.tiles {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
.tile {{ border: 1px solid {LINE}; border-radius: 6px; background: {PANEL}; padding: 14px 16px; }}
.tile .big {{ font-size: 26px; line-height: 1.1; }}
.tile .label {{ color: {DIM}; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
.dim {{ color: {DIM}; }}
.small {{ font-size: 12px; }}
.good {{ color: {GOOD}; }}
.warn {{ color: {WARN}; }}
table {{ width: 100%; border-collapse: collapse; }}
td, th {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid #1b222a; font-weight: 400; }}
th {{ color: {DIM}; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; }}
.bar {{ height: 6px; border-radius: 3px; background: #1b222a; overflow: hidden; }}
.bar > i {{ display: block; height: 100%; }}
button, .button {{ background: #1d242c; color: {INK}; border: 1px solid {LINE}; border-radius: 4px;
                   padding: 5px 12px; cursor: pointer; font: inherit; }}
button.go {{ border-color: {ACCENT}; color: {ACCENT}; }}
input {{ background: #0b0f13; color: {INK}; border: 1px solid {LINE}; border-radius: 4px;
         padding: 7px 10px; font: inherit; }}
.quiet {{ color: {DIM}; font-style: italic; }}
"""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)} · Frontier console</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def shell(world: str, worlds: list[str], here: str, body: str, day: int | None, phase: str | None) -> str:
    tabs = "".join(
        f"<a class='{'on' if name == here else ''}' href='/console/{escape(w)}/{name}'>{name}</a>"
        for name in ("overview", "ticks", "history")
        for w in [world]
    )
    picker = "".join(
        f"<a class='pill world' href='/console/{escape(name)}/{here}'>{escape(name)}</a>"
        if name != world
        else f"<span class='pill world'>{escape(name)}</span>"
        for name in worlds
    )
    state = (
        f"<span class='num' style='font-weight:700;letter-spacing:.08em'>DAY {day}</span>"
        f"<span class='{'good' if phase == 'open' else ''}'>{escape(phase or '')}</span>"
        if day is not None
        else "<span class='quiet'>never ticked</span>"
    )
    return page(
        world,
        f"<header><span class='brand'>FRONTIER</span><span class='mode'>console</span>{picker}"
        f"<span class='spacer'></span>{state}"
        f"<a class='button' href='/console/logout'>sign out</a></header>"
        f"<nav>{tabs}</nav><main>{body}</main>",
    )


def _link(world: str, run: dict[str, Any]) -> str:
    return f"/console/{escape(world)}/ticks/{run['world_day']}"


def _outcome(run: dict[str, Any]) -> str:
    return (
        "<span class='good'>finished</span>"
        if run["finished"]
        else "<span class='warn'>did not finish</span>"
    )


def _metrics(metrics: dict[str, Any]) -> str:
    return escape(", ".join(f"{key} {value}" for key, value in sorted(metrics.items())))


def _count(value: int) -> str:
    """A thin space between thousands: 3 221 reads as one number, 3,221 reads as two."""
    return f"{value:,}".replace(",", "\u2009")


def _when(run: dict[str, Any]) -> str:
    return escape(str(run["finished_at"] or run["started_at"] or ""))[:19]


def _secs(value: float | None) -> str:
    return f"{value:.2f} s" if value is not None else "—"


def overview(body: dict[str, Any]) -> str:
    last, hist, counts = body["last_tick"], body["history"], body["counts"]

    if last["world_day"] is None:
        tick_card = (
            "<div class='card'><div class='row'><span class='quiet'>"
            "This world has never ticked. Nothing has happened in it yet.</span></div></div>"
        )
    else:
        verdict = (
            "<span class='good'>all stages</span>"
            if last["finished"]
            else "<span class='warn'>did not finish</span>"
        )
        asked = " · <span class='dim small'>retry requested</span>" if last["retry_requested"] else ""
        tick_card = (
            "<div class='card'>"
            f"<div class='row'><b style='letter-spacing:.08em'>LAST TICK</b>"
            f"<span class='num dim'>day {last['world_day']}</span><span class='spacer'></span>"
            f"<span class='num dim'>{_when(last)}</span>"
            f"<span class='num'>{_secs(last['seconds'])}</span>{verdict}{asked}"
            f" <a class='button' href='/console/{{world}}/ticks/{last['world_day']}'>look</a></div>"
            "</div>"
        )

    tiles = "".join(
        f"<div class='tile'><div class='big num'>{_count(value)}</div><div class='label'>{label}</div></div>"
        for label, value in (
            ("systems", counts["systems"]),
            ("pilots", counts["pilots"]),
            ("crews", counts["crews"]),
            ("hexes of empty space", counts["empty_space"]),
        )
    )

    soon = hist["soonest_expiry_in"]
    condition = (
        f"<div class='card'><div class='row' style='flex-direction:column;align-items:flex-start;gap:8px'>"
        f"<div class='dim small' style='{CAPS}'>The world's condition</div>"
        f"<div><span style='color:{ACCENT};font-size:18px'>{escape(hist['era'] or 'no era yet')}</span>"
        + (f" <span class='num dim small'>began day {hist['era_began_on']}</span>" if hist["era"] else "")
        + "</div>"
        f"<div><b class='num'>{hist['open_crises']}</b> crises open"
        + (f" <span class='dim small'>soonest expires in {soon} days</span>" if soon is not None else "")
        + "</div>"
        f"<div><b class='num {'warn' if hist['incursion_hulls'] else ''}'>{hist['incursion_hulls']}</b>"
        " incursion hulls under way</div></div></div>"
    )
    return tick_card + f"<div class='tiles'>{tiles}</div>" + condition


def ticks(world: str, runs: list[dict[str, Any]]) -> str:
    if not runs:
        return (
            "<div class='card'><div class='row'><span class='quiet'>No tick has run yet.</span></div></div>"
        )
    rows = "".join(
        "<tr>"
        f"<td class='num'><a href='{_link(world, r)}'>day {r['world_day']}</a></td>"
        f"<td class='num dim'>{escape(str(r['started_at'] or ''))[:19]}</td>"
        f"<td class='num'>{_secs(r['seconds'])}</td>"
        f"<td>{_outcome(r)}"
        + (" <span class='dim small'>· retry requested</span>" if r["retry_requested"] else "")
        + "</td></tr>"
        for r in runs
    )
    return (
        "<div class='card'><table><tr><th>run</th><th>started</th><th>elapsed</th><th>outcome</th></tr>"
        f"{rows}</table></div>"
    )


def tick(world: str, body: dict[str, Any], may_retry: bool) -> str:
    stopped = body["stopped_after"]
    head = (
        f"<div class='card'><div class='row'><b class='num'>DAY {body['world_day']}</b>"
        f"<span class='spacer'></span><span class='num'>{_secs(body['seconds'])}</span>"
        + (
            "<span class='good'>finished</span>"
            if body["finished"]
            else f"<span class='warn'>stopped after {escape(str(stopped))}</span>"
        )
        + (
            f" <form method='post' style='display:inline' "
            f"action='/console/{escape(world)}/ticks/{body['world_day']}/retry'>"
            "<button class='go'>Ask for a retry</button></form>"
            if (not body["finished"] and may_retry and not body["retry_requested"])
            else ""
        )
        + (" <span class='dim small'>retry already requested</span>" if body["retry_requested"] else "")
        + "</div></div>"
    )

    rows = "".join(
        "<tr>"
        f"<td>{escape(s['stage'])}</td>"
        f"<td class='num' style='text-align:right'>{_secs(s['seconds'])}</td>"
        f"<td style='width:40%'><div class='bar'><i style='width:{s['share'] * 100:.0f}%;"
        f"background:{ACCENT if s['share'] >= 0.4 else '#3f7fc2'}'></i></div></td>"
        f"<td class='num dim small'>{_metrics(s['metrics'])}</td>"
        "</tr>"
        for s in body["stages"]
    )
    table = (
        "<div class='card'><table><tr><th>stage</th><th style='text-align:right'>took</th>"
        f"<th>share</th><th>what it did</th></tr>{rows}</table></div>"
    )
    note = (
        "<p class='dim small'>The console does not run a tick — the worker does. Asking for a retry "
        "leaves a request on the run; a failed tick resumes from the stage that broke, not from the "
        "beginning.</p>"
    )
    return head + table + note


def _pips(severity: int) -> str:
    """Severity as marks, not only as a number: five of five reads at a glance."""
    return "".join(
        f"<i style='display:inline-block;width:7px;height:13px;border-radius:2px;margin-right:3px;"
        f"background:{ACCENT if n <= severity else LINE}'></i>"
        for n in range(1, 6)
    )


def _countdown(days: int | None) -> str:
    if days is None:
        return "<span class='dim'>—</span>"
    # Nearer the expiry, warmer the colour: it is a countdown to an invasion, not a date.
    colour = WARN if days <= 5 else (ACCENT if days <= 11 else DIM)
    word = "expires today" if days == 0 else (f"{days} days left" if days > 0 else "overdue")
    return f"<span class='num' style='color:{colour}'>{word}</span>"


def history(body: dict[str, Any]) -> str:
    era = body["era"]
    head = (
        "<div class='card'><div class='row'>"
        f"<span class='dim small' style='{CAPS}'>Era</span>"
        + (
            f"<span style='color:{ACCENT};font-size:20px'>{escape(era['name'])}</span>"
            f"<span class='num dim small'>began day {era['began_on']}</span>"
            if era
            else "<span class='quiet'>No age has been named yet.</span>"
        )
        + "<span class='spacer'></span>"
        f"<span class='dim small'>an age closes when a crisis of severity "
        f"{body['era_threshold']} or worse is resolved</span>"
        "</div></div>"
    )

    if not body["open"]:
        crises = (
            "<div class='card'><div class='row'><span class='quiet'>"
            "Nothing is straining. The model expects what it is seeing.</span></div></div>"
        )
    else:
        rows = "".join(
            "<tr>"
            f"<td class='num dim'>{escape(c['region'])}</td>"
            f"<td>{escape(c['variable'].replace('_', ' '))}</td>"
            f"<td>{_pips(c['severity'])}</td>"
            f"<td class='num dim small'>opened {c['opened_on']}</td>"
            f"<td style='text-align:right'>{_countdown(c['days_left'])}</td>"
            "</tr>"
            for c in body["open"]
        )
        crises = (
            f"<div class='card'><table><tr><th>region</th><th>variable</th><th>severity</th>"
            f"<th>opened</th><th style='text-align:right'>expiry</th></tr>{rows}</table></div>"
            "<p class='dim small'>Every crisis that expires unresolved brings an incursion. "
            "Severity decides how many hulls, never whether they come.</p>"
        )

    raised = [c for c in body["answered"] if c["incursion"]]
    if not raised:
        incursions = (
            "<div class='card'><div class='row'><span class='quiet'>"
            "No incursion has been raised in this world.</span></div></div>"
        )
    else:
        cards = "".join(
            "<div class='card' style='margin-bottom:10px'><div class='row'>"
            f"<b class='warn'>{escape(c['incursion']['region'] or c['region'])}</b>"
            f"<span class='num warn'>{c['incursion']['still_flying']} of "
            f"{c['incursion']['hulls']} hulls still flying</span>"
            "<span class='spacer'></span>"
            f"<span class='dim small'>raised day {c['incursion']['raised_on']} from a "
            f"{escape(c['variable'].replace('_', ' '))} crisis of severity {c['severity']}</span>"
            "</div></div>"
            for c in raised
        )
        incursions = cards

    return (
        head
        + f"<div class='dim small' style='{CAPS}'>Open crises</div>"
        + crises
        + f"<div class='dim small' style='{CAPS}'>Incursions</div>"
        + incursions
    )


def login(message: str = "") -> str:
    warn = f"<p class='warn small'>{escape(message)}</p>" if message else ""
    return page(
        "Sign in",
        "<main style='max-width:360px;margin:12vh auto'>"
        "<div style='font-weight:700;letter-spacing:.14em;margin-bottom:4px'>FRONTIER</div>"
        "<div class='dim' style='font-style:italic;margin-bottom:18px'>operator console</div>"
        f"{warn}"
        "<form method='post' action='/console/login' style='display:flex;flex-direction:column;gap:10px'>"
        "<input name='email' placeholder='operator' autocomplete='username'>"
        "<input name='password' type='password' placeholder='password' autocomplete='current-password'>"
        "<button class='go'>Sign in</button></form>"
        "<p class='dim small' style='margin-top:18px'>Permission comes from another operator. "
        "There is no way to give it to yourself.</p></main>",
    )
