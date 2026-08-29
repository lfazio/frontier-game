import { useEffect, useRef, useState } from "react";
import { FACTIONS, type Tile, type TileEntry } from "./api";
import { GUTTER, drawAxes } from "./axes";

// Canvas rather than SVG (UX §8.4): a region view holds hundreds of marks and a system board
// holds 217, which is more layout work than the DOM should be asked for while panning.
// Canvas has no accessibility tree, so the textual list below the board is not a courtesy —
// it is the only way a screen reader can perceive the map at all.

const MAX_SIZE = 26;
const SQRT3 = Math.sqrt(3);

/** Flat-top axial to pixels. The same layout the design assumes throughout. */
function toPixel(q: number, r: number, size: number): { x: number; y: number } {
  return { x: size * 1.5 * q, y: size * SQRT3 * (r + q / 2) };
}

function hexPath(context: CanvasRenderingContext2D, x: number, y: number, size: number): void {
  context.beginPath();
  for (let corner = 0; corner < 6; corner += 1) {
    const angle = (Math.PI / 180) * (60 * corner);
    const px = x + size * Math.cos(angle);
    const py = y + size * Math.sin(angle);
    corner === 0 ? context.moveTo(px, py) : context.lineTo(px, py);
  }
  context.closePath();
}

/** A region is a filled disc whose radius is rule data, so the hex size has to follow it. */
function layoutFor(entries: TileEntry[], width: number, height: number) {
  const span = entries.reduce(
    (most, e) => Math.max(most, (Math.abs(e.q) + Math.abs(e.r) + Math.abs(e.q + e.r)) / 2),
    0,
  );
  const across = 2 * span + 1;
  // The rulers need room, so the board is fitted inside them rather than under them.
  const room = { w: Math.max(40, width - GUTTER * 2), h: Math.max(40, height - GUTTER * 2) };
  const size = Math.max(3, Math.min(MAX_SIZE, Math.min(room.w / (across * 1.6), room.h / (across * SQRT3))));

  const points = entries.map((e) => toPixel(e.q, e.r, size));
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return {
    size,
    offsetX: width / 2 - (Math.min(...xs) + Math.max(...xs)) / 2 + GUTTER / 2,
    offsetY: height / 2 - (Math.min(...ys) + Math.max(...ys)) / 2 + GUTTER / 2,
  };
}

interface Props {
  tile: Tile | null;
  onSelect: (entry: TileEntry) => void;
  selected: string | null;
}

export function HexMap({ tile, onSelect, selected }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [focus, setFocus] = useState(0);
  const entries = tile?.entries ?? [];
  const places = entries.filter((entry) => entry.kind !== "void");
  const empties = entries.length - places.length;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const ratio = window.devicePixelRatio || 1;
    const { width, height } = canvas.getBoundingClientRect();
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    if (entries.length === 0) {
      context.fillStyle = "#6b7280";
      context.font = "14px ui-sans-serif, system-ui, sans-serif";
      context.textAlign = "center";
      context.fillText("Nothing charted here.", width / 2, height / 2);
      return;
    }

    // Centre whatever the tile contains, whatever its coordinates happen to be.
    const { size, offsetX, offsetY } = layoutFor(entries, width, height);

    entries.forEach((entry, index) => {
      const { x, y } = toPixel(entry.q, entry.r, size);
      const cx = x + offsetX;
      const cy = y + offsetY;
      const faction = entry.controller ? FACTIONS[entry.controller] : undefined;
      // Empty space is drawn, not omitted: it is somewhere, and the chart is continuous.
      const empty = entry.kind === "void";

      hexPath(context, cx, cy, size);
      context.fillStyle = empty ? "#11161b" : faction ? `${faction.tint}44` : "#1b2129";
      context.fill();
      context.lineWidth = entry.path === selected ? 3 : 1;
      context.strokeStyle =
        entry.path === selected ? "#e8c07d" : index === focus ? "#7f8c99" : empty ? "#1c232a" : "#2c343d";
      context.stroke();

      if (empty || size < 9) return;
      context.fillStyle = "#d7dde4";
      context.font = `${Math.round(size * 0.42)}px ui-sans-serif, system-ui, sans-serif`;
      context.textAlign = "center";
      // Control is a letter as well as a tint: never colour alone (UX §8.3).
      context.fillText(faction ? faction.letter : "·", cx, cy + size * 0.15);
    });

    drawAxes(context, entries, (q, r) => {
      const { x, y } = toPixel(q, r, size);
      return { x: x + offsetX, y: y + offsetY };
    }, size);
  }, [entries, selected, focus]);

  function pick(index: number): void {
    const entry = entries[index];
    if (entry) {
      setFocus(index);
      onSelect(entry);
    }
  }

  return (
    <div className="map">
      <canvas
        ref={canvasRef}
        className="board"
        tabIndex={0}
        role="application"
        aria-label={`Star chart, ${places.length} places in ${entries.length} hexes`}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            event.preventDefault();
            pick(Math.min(focus + 1, entries.length - 1));
          } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
            event.preventDefault();
            pick(Math.max(focus - 1, 0));
          } else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            pick(focus);
          }
        }}
        onClick={(event) => {
          const canvas = canvasRef.current;
          if (!canvas || entries.length === 0) return;
          const box = canvas.getBoundingClientRect();
          const px = event.clientX - box.left;
          const py = event.clientY - box.top;
          const { size, offsetX, offsetY } = layoutFor(entries, box.width, box.height);
          let best = -1;
          let bestDistance = Infinity;
          entries.forEach((entry, index) => {
            const point = toPixel(entry.q, entry.r, size);
            const dx = point.x + offsetX - px;
            const dy = point.y + offsetY - py;
            const distance = dx * dx + dy * dy;
            if (distance < bestDistance && distance < size * size) {
              bestDistance = distance;
              best = index;
            }
          });
          if (best >= 0) pick(best);
        }}
      />
      {/* The map as text, for anyone who cannot see a canvas. Empty space is summarised rather
          than listed hex by hex: hundreds of identical entries would bury the places that matter. */}
      <ul className="chart" aria-label="Places on this chart">
        {places.map((entry) => (
          <li key={entry.id}>
            <button
              className={entry.path === selected ? "chosen" : ""}
              onClick={() => onSelect(entry)}
            >
              {entry.name ?? entry.kind}
              <span className="dim">
                {" "}
                {entry.kind}
                {entry.controller ? ` · ${FACTIONS[entry.controller]?.name}` : " · contested"}
              </span>
            </button>
          </li>
        ))}
        {empties > 0 && (
          <li className="dim small">
            and {empties} hexes of empty space between them
          </li>
        )}
      </ul>
    </div>
  );
}
