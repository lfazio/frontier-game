// Coordinate rulers around a hex board. One implementation, used by both boards, so the region
// chart and the system board always label the same way.
//
// The layout is flat-top axial: x depends only on q, so a column of constant q is a straight
// vertical line and its label sits above it. A row of constant r is *not* horizontal — y depends
// on q as well — so the r ruler follows the left edge of the board and slants with it. That is
// the honest picture of axial coordinates, not a defect in the drawing.

export const GUTTER = 22;

// The same minus sign the address format uses, so a ruler and an address agree.
const label = (n: number) => String(n);

export function drawAxes(
  context: CanvasRenderingContext2D,
  cells: readonly { q: number; r: number }[],
  at: (q: number, r: number) => { x: number; y: number },
  size: number,
): void {
  if (cells.length === 0) return;

  // A board can hold hundreds of hexes; label every one only when there is room to read them.
  const stride = size >= 15 ? 1 : size >= 9 ? 2 : 4;

  context.save();
  context.fillStyle = "#6d7a87";
  context.font = `${Math.max(9, Math.min(11, Math.round(size * 0.5)))}px ui-monospace, monospace`;
  context.textAlign = "center";
  context.textBaseline = "middle";

  // Both rulers sit outside the board's own bounding box. A hex disc has diagonal edges, so the
  // first hex of a row is not necessarily on the left edge — anchoring to the row itself would
  // drop the label on top of a neighbouring hex.
  const columnX = new Map<number, number>();
  const rowY = new Map<number, number>();
  let left = Infinity;
  let top = Infinity;
  for (const cell of cells) {
    const { x, y } = at(cell.q, cell.r);
    left = Math.min(left, x);
    top = Math.min(top, y);
    columnX.set(cell.q, x);
    const known = rowY.get(cell.r);
    if (known === undefined || y < known) rowY.set(cell.r, y);
  }

  for (const [q, x] of columnX) {
    if (q % stride !== 0) continue;
    context.fillText(label(q), x, top - size - 7);
  }

  context.textAlign = "right";
  for (const [r, y] of rowY) {
    if (r % stride !== 0) continue;
    context.fillText(label(r), left - size - 5, y);
  }

  context.restore();
}

/** One hex, written the way the address format writes a level: `2:-4`. */
export function coords(cell: { q: number; r: number }): string {
  return `${cell.q}:${cell.r}`;
}
