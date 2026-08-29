import { useEffect, useRef, useState } from "react";
import { formatAddress, hexDistance, tipOf, type Contact, type SystemView } from "../api";
import { GUTTER, coords, drawAxes } from "../axes";

// The system board: a top-down view centred on the ship and bounded by how far it can see
// (UX §4.1). Three layers, kept visibly distinct — in sight, charted, and nothing at all.

const SIZE = 26;
const STATION = "#5fb0a6";
const STATION_CHARTED = "#3d6b66";
const SQRT3 = Math.sqrt(3);

function toPixel(q: number, r: number) {
  return { x: SIZE * 1.5 * q, y: SIZE * SQRT3 * (r + q / 2) };
}

function hexPath(context: CanvasRenderingContext2D, x: number, y: number, size = SIZE) {
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

  // Only hexes inside sight are cells at all. Charted places outside it are marks, not cells:
  // the player may know a station is there, but not what is standing on it. Sight is also
  // clipped to the system's own rim — past it there is no place to fly to, so none is offered.
  const cells: Cell[] = [];
  for (let dq = -reach; dq <= reach; dq += 1) {
    for (let dr = Math.max(-reach, -dq - reach); dr <= Math.min(reach, -dq + reach); dr += 1) {
      const at = { q: me.q + dq, r: me.r + dr };
      if (hexDistance(at, { q: 0, r: 0 }) > view.system.radius) continue;
      cells.push({ ...at, steps: hexDistance({ q: 0, r: 0 }, { q: dq, r: dr }) });
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

    const origin = toPixel(me.q, me.r);
    // Shifted by half a gutter so the rulers have room without moving the ship off centre.
    const ox = width / 2 - origin.x + GUTTER / 2;
    const oy = height / 2 - origin.y + GUTTER / 2;

    // The sight boundary is drawn, so the player can see where their knowledge stops.
    const centreX = width / 2 + GUTTER / 2;
    const centreY = height / 2 + GUTTER / 2;
    context.beginPath();
    context.arc(centreX, centreY, SIZE * SQRT3 * (reach + 0.5), 0, Math.PI * 2);
    context.fillStyle = "#101821";
    context.fill();
    context.setLineDash([3, 4]);
    context.strokeStyle = "#e8c07d66";
    context.stroke();
    context.setLineDash([]);

    for (const cell of cells) {
      const { x, y } = toPixel(cell.q, cell.r);
      const isSelected = selected?.q === cell.q && selected?.r === cell.r;
      const isFocus = focus?.q === cell.q && focus?.r === cell.r;
      hexPath(context, x + ox, y + oy);
      context.fillStyle = isSelected ? "#1d242c" : "#131a21";
      context.fill();
      context.lineWidth = isSelected ? 2 : 1;
      context.strokeStyle = isSelected ? "#e8c07d" : isFocus ? "#7f8c99" : "#232c35";
      context.stroke();
    }

    // The path is drawn before it is flown, and this is the path submitted (UX §5.3).
    if (route && route.length > 1) {
      context.beginPath();
      route.forEach((hop, i) => {
        const { x, y } = toPixel(hop.q, hop.r);
        i === 0 ? context.moveTo(x + ox, y + oy) : context.lineTo(x + ox, y + oy);
      });
      context.strokeStyle = "#e8c07d";
      context.lineWidth = 2;
      context.stroke();
      for (const hop of route.slice(1)) {
        const { x, y } = toPixel(hop.q, hop.r);
        context.beginPath();
        context.arc(x + ox, y + oy, 3, 0, Math.PI * 2);
        context.fillStyle = "#e8c07d";
        context.fill();
      }
    }

    for (const body of view.bodies) {
      const { x, y } = toPixel(body.q, body.r);
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
      const { x, y } = toPixel(at.q, at.r);
      context.beginPath();
      context.moveTo(x + ox, y + oy - 8);
      context.lineTo(x + ox + 7, y + oy + 6);
      context.lineTo(x + ox - 7, y + oy + 6);
      context.closePath();
      context.strokeStyle = "#c2603f";
      context.lineWidth = 1.4;
      context.stroke();
    }

    drawAxes(context, cells, (q, r) => {
      const { x, y } = toPixel(q, r);
      return { x: x + ox, y: y + oy };
    }, SIZE);

    // You, last, so nothing is drawn over the one mark that must always be findable.
    context.beginPath();
    context.moveTo(centreX, centreY - 9);
    context.lineTo(centreX + 7, centreY + 7);
    context.lineTo(centreX, centreY + 3);
    context.lineTo(centreX - 7, centreY + 7);
    context.closePath();
    context.fillStyle = "#e8c07d";
    context.fill();
  }, [view, selected, focus, cells, route, me.q, me.r, reach]);

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
      aria-label={`System board centred on ${coords(me)}, sight ${reach} hexes, ${view.contacts.length} contacts`}
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
        const origin = toPixel(me.q, me.r);
        const ox = box.width / 2 - origin.x + GUTTER / 2;
        const oy = box.height / 2 - origin.y + GUTTER / 2;
        let best = -1;
        let bestDistance = SIZE * SIZE;
        cells.forEach((cell, i) => {
          const { x, y } = toPixel(cell.q, cell.r);
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
