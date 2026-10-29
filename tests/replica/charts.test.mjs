// The chart options of web/assets/js/charts.js: series colours and styles of the spec, axes, the attainment
// rule, the cell shades and the kit's number formats (never Intl compact notation).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as charts from '../../web/assets/js/charts.js';
import { createModel, defaultState } from '../../web/assets/js/model.js';

const root = new URL('../../', import.meta.url);
const model = createModel(JSON.parse(readFileSync(new URL('web/assets/data/replica.json', root), 'utf8')));
const C = {
  text: '#E6EDF3', muted: '#93A1B0', border: '#1F2A36', surface: '#121820', accent: '#F2A93B', ok: '#3DDC97', warn: '#FACC15',
  chart: ['#C38102', '#058DB5', '#02AB70', '#AB6FE5', '#CA445C', '#77A304', '#028E7F', '#7A84EF'],
};
const state = defaultState();

test('current vs PY: Current in the accent, PY muted and dashed, euros on the axis', () => {
  const option = charts.revenuePy(model.view(state, 'overview').months, C);
  const [current, py] = option.series;
  assert.equal(current.lineStyle.color, C.accent);
  assert.equal(py.lineStyle.color, C.muted);
  assert.equal(py.lineStyle.type, 'dashed');
  assert.equal(option.xAxis.data[0], 'Jan');
  assert.equal(option.xAxis.data.length, 9);
  assert.equal(current.data[0], 762948.07); // January 2025 in euros
});

test('trends: R12 on the secondary axis in chart-2', () => {
  const option = charts.trend(model.view(state, 'trends').rows, C);
  const r12 = option.series.find((s) => s.name === 'R12');
  assert.equal(r12.yAxisIndex, 1);
  assert.equal(r12.lineStyle.color, C.chart[1]);
  assert.equal(option.yAxis.length, 2);
});

test('pareto: 40 bars, the cumulative share on a 0 to 100 % axis with the line at 80 %', () => {
  const option = charts.pareto(model.view(state, 'products').pareto, C);
  assert.equal(option.series[0].data.length, 40);
  assert.deepEqual([option.yAxis[1].min, option.yAxis[1].max], [0, 1]);
  assert.deepEqual(option.series[1].markLine.data, [{ yAxis: 0.8 }]);
  const cumulative = option.series[1].data;
  assert.ok(cumulative.every((v, i) => i === 0 || v >= cumulative[i - 1]));
});

test('attainment: ok at 100 % and above, warning below, a line at 100 %', () => {
  const option = charts.attainment([['A', 1.02], ['B', 0.97], ['C', 1], ['D', null]], C);
  assert.deepEqual(option.series[0].data.map((d) => d.itemStyle.color), [C.ok, C.warn, C.ok, C.warn]);
  assert.deepEqual(option.series[0].markLine.data, [{ xAxis: 1 }]);
  assert.ok(option.xAxis.min <= 0.8 && option.xAxis.max >= 1.1);
});

test('a cross-filter dims the other bars', () => {
  const rows = model.view(state, 'overview').analyse;
  const option = charts.revenueBars(rows, C, { selected: rows[1][0] });
  assert.deepEqual(option.series[0].data.map((d) => d.itemStyle.opacity), rows.map((_, i) => (i === 1 ? 1 : 0.35)));
  assert.ok(charts.revenueBars(rows, C).series[0].data.every((d) => d.itemStyle.opacity === 1));
});

test('targets: the target line is not the colour of the revenue bars', () => {
  const option = charts.targetCombo(model.view(state, 'targets').months, C);
  assert.notEqual(option.series[0].itemStyle.color, option.series[1].lineStyle.color);
  assert.equal(option.series[0].data.length, 12);
  assert.equal(option.series[0].data[11], null); // December 2025 shows the target only
});

test('reduced motion turns the animation off', () => {
  assert.equal(charts.revenuePy([], C, false).animation, false);
  assert.equal(charts.revenueBars([], C, { motion: false }).animation, false);
});

test('labels use the kit formats', () => {
  assert.equal(charts.axisEuro(1250000), '€ 1.3m');
  assert.equal(charts.axisEuro(988500), '€ 988.5k');
  assert.equal(charts.moneyText(230838), '€2,308');
  assert.equal(charts.moneyText(null), '–');
  assert.deepEqual(charts.monthLabels([24, 25]), ['Dec 2024', 'Jan 2025']);
  assert.deepEqual(charts.monthLabels([25, 26]), ['Jan', 'Feb']);
});

test('attainment cells shade up to SHADE_MAX per cent of the status colour', () => {
  assert.equal(charts.SHADE_MAX, 35);
  assert.equal(charts.cellShade(1), 'color-mix(in srgb, var(--ok) 0%, var(--surface))');
  assert.equal(charts.cellShade(0.85), 'color-mix(in srgb, var(--warn) 35%, var(--surface))');
  assert.equal(charts.cellShade(1.05), 'color-mix(in srgb, var(--ok) 18%, var(--surface))');
  assert.equal(charts.cellShade(null), '');
});
