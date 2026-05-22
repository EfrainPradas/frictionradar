import type { HeatmapMode } from '../../../data/mockHeatmap';

const PRESSURE_RAMP = [
  '#f8fafc',
  '#fef3e8',
  '#fde0bf',
  '#f9c089',
  '#ed9856',
  '#d97333',
  '#b85420',
];

const OPPORTUNITY_RAMP = [
  '#fafaf7',
  '#f5edd6',
  '#ecdca2',
  '#d6b97a',
  '#b8932f',
  '#8a6f1e',
];

function pick(ramp: string[], t: number): string {
  if (t <= 0) return ramp[0];
  if (t >= 1) return ramp[ramp.length - 1];
  const idx = t * (ramp.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  const k = idx - lo;
  return mix(ramp[lo], ramp[hi], k);
}

function mix(a: string, b: string, t: number): string {
  const pa = parseHex(a);
  const pb = parseHex(b);
  const r = Math.round(pa[0] + (pb[0] - pa[0]) * t);
  const g = Math.round(pa[1] + (pb[1] - pa[1]) * t);
  const bl = Math.round(pa[2] + (pb[2] - pa[2]) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

function parseHex(h: string): [number, number, number] {
  const s = h.replace('#', '');
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}

export function colorForIntensity(value: number): string {
  return pick(PRESSURE_RAMP, Math.max(0, Math.min(1, value / 100)));
}

export function colorForOpportunity(value: number): string {
  return pick(OPPORTUNITY_RAMP, Math.max(0, Math.min(1, value / 100)));
}

export function colorForVelocity(value: number): string {
  const t = Math.max(-1, Math.min(1, value));
  if (t > 0) return pick(['#f1f5f9', '#fde0bf', '#ed9856', '#b85420'], t);
  if (t < 0) return pick(['#f1f5f9', '#d9efdf', '#86c79a', '#1e7f3a'], -t);
  return '#f1f5f9';
}

export function colorForCell(mode: HeatmapMode, intensity: number, velocity: number, opportunity: number): string {
  if (mode === 'intensity') return colorForIntensity(intensity);
  if (mode === 'velocity') return colorForVelocity(velocity);
  return colorForOpportunity(opportunity);
}

export function textInkFor(bg: string): string {
  const rgb = bg.match(/\d+/g);
  if (!rgb) return '#0f172a';
  const [r, g, b] = rgb.map(Number);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.62 ? '#0f172a' : '#ffffff';
}
