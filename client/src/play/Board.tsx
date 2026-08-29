import { useEffect, useRef, useState } from "react";
import { formatAddress, hexDistance, tipOf, type Contact, type SystemView } from "../api";
import { GUTTER, coords, drawAxes } from "../axes";

// The system board: a top-down view centred on the ship and bounded by how far it can see
// (UX §4.1). Three layers, kept visibly distinct — in sight, charted, and nothing at all.

const MAX_SIZE = 26;
const STATION = "#5fb0a6";
const STATION_CHARTED = "#3d6b66";
const SQRT3 = Math.sqrt(3);

function toPixel(q: number, r: number, size: number) {
  return { x: size * 1.5 * q, y: size * SQRT3 * (r + q / 2) };
}

/** The whole system has to fit, so the hex size follows the system's radius, not a constant. */
function sizeFor(radius: number, width: number, height: number) {
  const across = 2 * radius + 1;
  const room = { w: Math.max(40, width - GUTTER * 2), h: Math.max(40, height - GUTTER * 2) };
  return Math.max(3, Math.min(MAX_SIZE, Math.min(room.w / (across * 1.6), room.h / (across * SQRT3))));
}

function hexPath(context: CanvasRenderingContext2D, x: number, y: number, size: number) {
  context.beginPath();
  for (let corner = 0; corner < 6; corner += 1) {
    const angle = (Math.PI / 180) * (60 * corner);
    const px = x + size * Math.cos(angle);
    const py = y + size * Math.sin(angle);
    corner === 0 ? context.moveTo(px, py) : context.lineTo(px, py);
  }
  context.closePath();
}

interface Cell {
  q: number;
  r: number;
  steps: number;
}

export function Board({ view, onSelect, selected, route }: {
  view: SystemView;
  onSelect: (cell: Cell | null) => void;
  selected: Cell | null;
  route?: { q: number; r: number }[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [focus, setFocus] = useState<Cell | null>(null);

  const me = tipOf(view.you.position);
  const reach = view.you.sensor_range;

  // The whole system is drawn, out to its rim: a board that showed only the sight circle gave
  // the player no idea where in the system they were. What sight decides is how a hex is drawn,
  // not whether it exists — and nothing beyond the rim is drawn, because nothing is there.
  const span = view.system.radius;
  const cells: Cell[] = [];
  for (let q = -span; q <= span; q += 1) {
    for (let r = Math.max(-span, -q - span); r <= Math.min(span, -q + span); r += 1) {
      cells.push({ q, r, steps: hexDistance({ q, r }, me) });
    }
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const ratio = window.devicePixelRatio || 1;
    const { width, height } = canvas.getBoundingClientRect();
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    // The system is centred, not the ship: the board is a picture of the whole system now, and
    // where the ship sits inside it is one of the things it shows.
    const size = sizeFor(span, width, height);
    const ox = width / 2 + GUTTER / 2;
    const oy = height / 2 + GUTTER / 2;
    const shipAt = toPixel(me.q, me.r, size);
    const centreX = shipAt.x + ox;
    const centreY = shipAt.y + oy;

    // The sight boundary is drawn, so the player can see where their knowledge stops.
    context.beginPath();
    context.arc(centreX, centreY, size * SQRT3 * (reach + 0.5), 0, Math.PI * 2);
    context.fillStyle = "#101821";
    context.fill();
    context.setLineDash([3, 4]);
    context.strokeStyle = "#e8c07d66";
    context.stroke();
    context.setLineDash([]);

    for (const cell of cells) {
      const { x, y } = toPixel(cell.q, cell.r, size);
      const isSelected = selected?.q === cell.q && selected?.r === cell.r;
      const isFocus = focus?.q === cell.q && focus?.r === cell.r;
      // Out of sight is still a place — it is drawn, and drawn plainly as unwatched.
      const seen = cell.steps <= reach;
      hexPath(context, x + ox, y + oy, size);
      context.fillStyle = isSelected ? "#1d242c" : seen ? "#131a21" : "#0f1318";
      context.fill();
      context.lineWidth = isSelected ? 2 : 1;
      context.strokeStyle = isSelected
        ? "#e8c07d"
        : isFocus
          ? "#7f8c99"
          : seen
            ? "#232c35"
            : "#1a2027";
      context.stroke();
    }

    // The path is drawn before it is flown, and this is the path submitted (UX §5.3).
    if (route && route.length > 1) {
      context.beginPath();
      route.forEach((hop, i) => {
        const { x, y } = toPixel(hop.q, hop.r, size);
        i === 0 ? context.moveTo(x + ox, y + oy) : context.lineTo(x + ox, y + oy);
      });
      context.strokeStyle = "#e8c07d";
      context.lineWidth = 2;
      context.stroke();
      for (const hop of route.slice(1)) {
        const { x, y } = toPixel(hop.q, hop.r, size);
        context.beginPath();
        context.arc(x + ox, y + oy, 3, 0, Math.PI * 2);
        context.fillStyle = "#e8c07d";
        context.fill();
      }
    }

    for (const body of view.bodies) {
      const { x, y } = toPixel(body.q, body.r, size);
      const px = x + ox;
      const py = y + oy;
      const station = body.kind === "station";
      // A station is the only body you can do anything with, so it carries its own colour and
      // keeps it once charted. Everything else is terrain, in grey.
      const tint = station ? (body.in_sight ? STATION : STATION_CHARTED) : body.in_sight ? "#8b96a3" : "#4b5560";

      context.beginPath();
      context.arc(px, py, station ? 8 : 6, 0, Math.PI * 2);
      // Charted-but-unseen is hollow: remembered terrain, not a live sighting.
      context.fillStyle = body.in_sight && station ? "#14302c" : "transparent";
      context.fill();
      context.lineWidth = station ? 2 : 1.4;
      context.strokeStyle = tint;
      context.stroke();

      // A berth is marked, not merely outlined, so it is findable at a glance.
      if (station) {
        context.beginPath();
        context.arc(px, py, 3, 0, Math.PI * 2);
        context.fillStyle = tint;
        context.fill();
      }
    }

    for (const contact of view.contacts) {
      if (contact.quality !== "full") continue;
      const at = tipOf(contact.position);
      const { x, y } = toPixel(at.q, at.r, size);
      context.beginPath();
      context.moveTo(x + ox, y + oy - 8);
      context.lineTo(x + ox + 7, y + oy + 6);
      context.lineTo(x + ox - 7, y + oy + 6);
      context.closePath();
      context.strokeStyle = "#c2603f";
      context.lineWidth = 1.4;
      context.stroke();
    }

    drawAxes(
      context,
      cells,
      (q, r) => {
        const { x, y } = toPixel(q, r, size);
        return { x: x + ox, y: y + oy };
      },
      size,
    );

    // You, last, so nothing is drawn over the one mark that must always be findable.
    context.beginPath();
    const mark = Math.max(5, size * 0.36);
    context.moveTo(centreX, centreY - mark);
    context.lineTo(centreX + mark * 0.78, centreY + mark * 0.78);
    context.lineTo(centreX, centreY + mark * 0.33);
    context.lineTo(centreX - mark * 0.78, centreY + mark * 0.78);
    context.closePath();
    context.fillStyle = "#e8c07d";
    context.fill();
  }, [view, selected, focus, cells, route, me.q, me.r, reach, span]);

  function pick(index: number) {
    const cell = cells[index];
    if (cell) {
      setFocus(cell);
      onSelect(cell);
    }
  }

  const index = focus ? cells.findIndex((c) => c.q === focus.q && c.r === focus.r) : 0;

  return (
    <canvas
      ref={canvasRef}
      className="board"
      tabIndex={0}
      role="application"
      aria-label={`System board, ${cells.length} hexes, you at ${coords(me)}, sight ${reach} hexes, ${view.contacts.length} contacts`}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          event.preventDefault();
          pick(Math.min(index + 1, cells.length - 1));
        } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          event.preventDefault();
          pick(Math.max(index - 1, 0));
        } else if (event.key === "Escape") {
          setFocus(null);
          onSelect(null);
        }
      }}
      onClick={(event) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const box = canvas.getBoundingClientRect();
        const px = event.clientX - box.left;
        const py = event.clientY - box.top;
        const size = sizeFor(span, box.width, box.height);
        const ox = box.width / 2 + GUTTER / 2;
        const oy = box.height / 2 + GUTTER / 2;
        let best = -1;
        let bestDistance = size * size;
        cells.forEach((cell, i) => {
          const { x, y } = toPixel(cell.q, cell.r, size);
          const dx = x + ox - px;
          const dy = y + oy - py;
          if (dx * dx + dy * dy < bestDistance) {
            bestDistance = dx * dx + dy * dy;
            best = i;
          }
        });
        best >= 0 ? pick(best) : onSelect(null);
      }}
    />
  );
}

export function contactLine(contact: Contact): string {
  return contact.quality === "full"
    ? `${contact.name ?? contact.kind ?? "ship"} · ${formatAddress(contact.position)}`
    : `Unidentified contact · somewhere in this system`;
}
