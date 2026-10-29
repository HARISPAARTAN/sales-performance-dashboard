// WCAG 2.x contrast of the replica's colours in both themes (adapted from the portfolio's contrast check to read
// web/kit/tokens.css). Text pairs need 4.5:1; chart and status colours on the card surface need 3:1; the text
// of an attainment cell and of a data bar needs 4.5:1 on the strongest mix the page draws (charts.SHADE_MAX for
// the cells, the share in app.css for the data bar; color-mix in srgb mixes the encoded channels).
// Usage (from the repository root): node tools/checks/contrast.mjs
import fs from 'node:fs';
import { SHADE_MAX } from '../../web/assets/js/charts.js';

const css = fs.readFileSync('web/kit/tokens.css', 'utf8');
const app = fs.readFileSync('web/assets/css/app.css', 'utf8');
const split = css.indexOf(':root[data-theme="light"]');
if (split < 0) throw new Error('web/kit/tokens.css has no :root[data-theme="light"] block');
const vars = (text) =>
  Object.fromEntries([...text.matchAll(/--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b/g)].map((match) => [match[1], match[2]]));
const dark = vars(css.slice(0, split));
const themes = { dark, light: { ...dark, ...vars(css.slice(split)) } };
const bar = /\.dbar i \{[^}]*color-mix\(in srgb, var\(--accent\) (\d+)%, var\(--surface\)\)/.exec(app);
if (!bar) throw new Error('web/assets/css/app.css has no data-bar colour');
const BAR_SHARE = Number(bar[1]);

const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const toHex = (rgb) => `#${rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
const mix = (a, b, share) => toHex(channels(a).map((v, i) => (v * share + channels(b)[i] * (100 - share)) / 100));
function luminance(hex) {
  const [r, g, b] = channels(hex)
    .map((v) => v / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const TEXT = [
  ['text', 'bg'],
  ['text', 'surface'],
  ['text', 'surface-2'],
  ['muted', 'bg'],
  ['muted', 'surface'],
  ['muted', 'surface-2'],
  ['accent', 'bg'],
  ['accent', 'surface'],
  ['accent-fg', 'accent'],
  ['ok', 'surface'],
  ['danger', 'surface'],
];
const DATA = ['chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5', 'chart-6', 'chart-7', 'chart-8', 'ok', 'warn', 'muted', 'accent'];

let checked = 0;
let failed = 0;
function check(mode, label, fg, bg, min) {
  checked += 1;
  const value = fg && bg ? ratio(fg, bg) : 0;
  const pass = value >= min;
  if (!pass) failed += 1;
  console.log(`${pass ? 'ok    ' : 'FAIL  '} ${mode.padEnd(5)} ${label.padEnd(34)} ${fg} / ${bg}  ${value.toFixed(2)}:1 (min ${min})`);
}

for (const [mode, t] of Object.entries(themes)) {
  for (const [fg, bg] of TEXT) check(mode, `--${fg} on --${bg}`, t[fg], t[bg], 4.5);
  for (const name of DATA) check(mode, `--${name} on --surface (data)`, t[name], t.surface, 3);
  for (const status of ['warn', 'ok']) {
    const cell = mix(t[status], t.surface, SHADE_MAX);
    check(mode, `--text on ${SHADE_MAX} % --${status} cell`, t.text, cell, 4.5);
  }
  check(mode, `--text on ${BAR_SHARE} % --accent data bar`, t.text, mix(t.accent, t.surface, BAR_SHARE), 4.5);
}
console.log(failed ? `contrast: ${failed} of ${checked} pairs below the minimum` : `contrast: ${checked} pairs ok`);
process.exit(failed ? 1 : 0);
