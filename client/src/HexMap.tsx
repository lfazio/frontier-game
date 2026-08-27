import { useEffect, useRef, useState } from "react";
import { FACTIONS, type Tile, type TileEntry } from "./api";

// Canvas rather than SVG (UX §8.4): a region view holds hundreds of marks and a system board
// holds 217, which is more layout work than the DOM should be asked for while panning.
// Canvas has no accessibility tree, so the textual list below the board is not a courtesy —
// it is the only way a screen reader can perceive the map at all.

const SIZE = 26;
const SQRT3 = Math.sqrt(3);

/** Flat-top axial to pixels. The same layout the design assumes throughout. */
function toPixel(q: number, r: number): { x: number; y: number } {
  return { x: SIZE * 1.5 * q, y: SIZE * SQRT3 * (r + q / 2) };
}

function hexPath(context: CanvasRenderingContext2D, x: number, y: number): void {
  context.beginPath();
  for (let corner = 0; corner < 6; corner += 1) {
    const angle = (Math.PI / 180) * (60 * corner);
    const px = x + SIZE * Math.cos(angle);
    const py = y + SIZE * Math.sin(angle);
    corner === 0 ? context.moveTo(px, py) : context.lineTo(px, py);
  }
  context.closePath();
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
    const points = entries.map((e) => toPixel(e.q, e.r));
    const minX = Math.min(...points.map((p) => p.x));
    const maxX = Math.max(...points.map((p) => p.x));
    const minY = Math.min(...points.map((p) => p.y));
    const maxY = Math.max(...points.map((p) => p.y));
    const offsetX = width / 2 - (minX + maxX) / 2;
    const offsetY = height / 2 - (minY + maxY) / 2;

    entries.forEach((entry, index) => {
      const { x, y } = toPixel(entry.q, entry.r);
      const cx = x + offsetX;
      const cy = y + offsetY;
      const faction = entry.controller ? FACTIONS[entry.controller] : undefined;

      hexPath(context, cx, cy);
      context.fillStyle = faction ? `${faction.tint}44` : "#1b2129";
      context.fill();
      context.lineWidth = entry.path === selected ? 3 : 1;
      context.strokeStyle =
        entry.path === selected ? "#e8c07d" : index === focus ? "#7f8c99" : "#2c343d";
      context.stroke();

      context.fillStyle = "#d7dde4";
      context.font = "11px ui-sans-serif, system-ui, sans-serif";
      context.textAlign = "center";
      // Control is a letter as well as a tint: never colour alone (UX §8.3).
      context.fillText(faction ? faction.letter : "·", cx, cy + 4);
    });
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
        aria-label={`Star chart, ${entries.length} places`}
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
          const points = entries.map((e) => toPixel(e.q, e.r));
          const minX = Math.min(...points.map((p) => p.x));
          const maxX = Math.max(...points.map((p) => p.x));
          const minY = Math.min(...points.map((p) => p.y));
          const maxY = Math.max(...points.map((p) => p.y));
          const offsetX = box.width / 2 - (minX + maxX) / 2;
          const offsetY = box.height / 2 - (minY + maxY) / 2;
          let best = -1;
          let bestDistance = Infinity;
          points.forEach((point, index) => {
            const dx = point.x + offsetX - px;
            const dy = point.y + offsetY - py;
            const distance = dx * dx + dy * dy;
            if (distance < bestDistance && distance < SIZE * SIZE) {
              bestDistance = distance;
              best = index;
            }
          });
          if (best >= 0) pick(best);
        }}
      />
      {/* The map as text, for anyone who cannot see a canvas. Same data, same order. */}
      <ul className="chart" aria-label="Places on this chart">
        {entries.map((entry) => (
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
      </ul>
    </div>
  );
}
