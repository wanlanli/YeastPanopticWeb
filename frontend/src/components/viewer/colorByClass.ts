/** Labels follow the convention `1000 * class + instance_id` (e.g. "1001" ->
 * class 1, instance 1). Returns null when the label isn't a plain number. */
export function classFromLabel(label: string): number | null {
  if (label.trim() === '') return null;
  const n = Number(label);
  if (!Number.isFinite(n)) return null;
  return Math.floor(n / 1000);
}

// Fixed class -> color map (not a cycling palette): each id has a specific
// meaning, so the same class always renders the same color everywhere.
const CLASS_COLORS_RGB: Record<number, [number, number, number]> = {
  0: [1.0, 1.0, 1.0], // background: white
  1: [1.0, 0.1, 0.1], // cell: red
  2: [0.1, 0.8, 0.1], // shmoo: green
  3: [0.1, 0.35, 1.0], // zygote: blue
  4: [1.0, 0.65, 0.05], // tetrad: orange
  5: [0.65, 0.2, 0.9], // lysis: purple
  6: [0.0, 0.75, 0.35], // spore: green
  7: [0.85, 0.0, 0.6], // unknown: magenta
  8: [0.85, 0.15, 0.15], // unknown: red
  9: [0.55, 0.25, 0.85], // unknown: purple
  10: [0.0, 0.75, 0.75], // Merge error: cyan
  11: [0.75, 0.6, 0.0], // Low confidence: mustard
  12: [0.6, 0.3, 0.1], // Unknown / Other: brown
};
const FALLBACK_COLOR: [number, number, number] = [0.6, 0.6, 0.6]; // gray, for anything outside 0-12

export const CLASS_NAMES: Record<number, string> = {
  0: 'background',
  1: 'cell',
  2: 'shmoo',
  3: 'zygote',
  4: 'tetrad',
  5: 'lysis',
  6: 'spore',
  7: 'unknown',
  8: 'unknown',
  9: 'unknown',
  10: 'Merge error',
  11: 'Low confidence',
  12: 'Unknown / Other',
};

export const CLASS_IDS = Object.keys(CLASS_COLORS_RGB).map(Number).sort((a, b) => a - b);

export function classDisplayName(classId: number): string {
  return CLASS_NAMES[classId] ?? `class ${classId}`;
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  const toByte = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 255);
  return `#${[toByte(r), toByte(g), toByte(b)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
}

export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

export function colorForClass(classId: number): string {
  return rgbToHex(CLASS_COLORS_RGB[classId] ?? FALLBACK_COLOR);
}

const DEFAULT_FILL_ALPHA = 0.18;

export function strokeAndFillForClass(
  classId: number,
  fillAlpha: number = DEFAULT_FILL_ALPHA,
): { stroke: string; fill: string } {
  const stroke = colorForClass(classId);
  return { stroke, fill: hexToRgba(stroke, fillAlpha) };
}

/** '#000' or '#fff', whichever reads better against this class's color. */
export function textColorForClass(classId: number): string {
  const [r, g, b] = CLASS_COLORS_RGB[classId] ?? FALLBACK_COLOR;
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance > 0.6 ? '#000' : '#fff';
}
