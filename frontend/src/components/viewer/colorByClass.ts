import { CATEGORICAL } from '../quantification/palette';

/** Labels follow the convention `1000 * class + instance_id` (e.g. "1001" ->
 * class 1, instance 1). Returns null when the label isn't a plain number. */
export function classFromLabel(label: string): number | null {
  if (label.trim() === '') return null;
  const n = Number(label);
  if (!Number.isFinite(n)) return null;
  return Math.floor(n / 1000);
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

export function colorForClass(classId: number): string {
  const idx = ((classId % CATEGORICAL.length) + CATEGORICAL.length) % CATEGORICAL.length;
  return CATEGORICAL[idx];
}

export function strokeAndFillForClass(classId: number): { stroke: string; fill: string } {
  const stroke = colorForClass(classId);
  return { stroke, fill: hexToRgba(stroke, 0.18) };
}
