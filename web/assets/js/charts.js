// ECharts options of the replica: pure functions from a view of model.js and the colour tokens to an option
// object (no DOM access), plus a small host that draws them with the kit's chart themes. Amounts arrive in
// cents and are shown in euros; every number goes through the kit's fmt helpers, never Intl compact notation.
import { fmt } from '../../kit/kit.js';
import { MONTH_NAMES, monthYear } from './model.js';

const MONO = '"JetBrains Mono", Consolas, monospace';
const euro = (cents) => (cents === null || cents === undefined ? null : cents / 100);
export const axisEuro = (value) => `€ ${fmt.compact(value)}`;
export const moneyText = (cents) => (cents === null || cents === undefined ? fmt.int(null) : fmt.money(cents / 100));
const escape = (text) => String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);

// Month axis labels: "Jan" while every month lies in one year, "Jan 2024" otherwise.
export function monthLabels(months) {
  const years = new Set(months.map((m) => monthYear(m).year));
  return months.map((m) => {
    const { year, month } = monthYear(m);
    return years.size > 1 ? `${MONTH_NAMES[month - 1]} ${year}` : MONTH_NAMES[month - 1];
  });
}

function base(c, motion) {
  return {
    animation: motion,
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', confine: true },
    textStyle: { fontFamily: 'Inter, system-ui, sans-serif' },
    color: c.chart,
  };
}

function axisTooltip(rows) {
  return (params) => {
    const list = Array.isArray(params) ? params : [params];
    const head = escape(list[0]?.axisValueLabel ?? list[0]?.name ?? '');
    const lines = list.map((p) => `${p.marker}${escape(p.seriesName)}: <b>${rows(p)}</b>`);
    return [head, ...lines].join('<br>');
  };
}

const valueAxis = (formatter, extra = {}) => ({ type: 'value', axisLabel: { formatter, hideOverlap: true }, ...extra });

// Overview: revenue by month, current vs previous year (Current accent, PY muted and dashed).
export function revenuePy(months, c, motion = true) {
  return {
    ...base(c, motion),
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((p) => moneyText(p.value === null ? null : p.value * 100)) },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])), boundaryGap: false },
    yAxis: valueAxis(axisEuro),
    series: [
      { name: 'Current', type: 'line', data: months.map((r) => euro(r[1])), lineStyle: { width: 2.5, color: c.accent }, itemStyle: { color: c.accent }, symbol: 'circle', symbolSize: 6 },
      { name: 'PY', type: 'line', data: months.map((r) => euro(r[2])), lineStyle: { width: 2, type: 'dashed', color: c.muted }, itemStyle: { color: c.muted }, symbol: 'none' },
    ],
  };
}

// Overview: revenue columns and gross margin % on the secondary axis.
export function revenueMargin(months, c, motion = true) {
  return {
    ...base(c, motion),
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: axisTooltip((p) => (p.seriesIndex === 0 ? moneyText(p.value === null ? null : p.value * 100) : fmt.pct(p.value))),
    },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])) },
    yAxis: [valueAxis(axisEuro), valueAxis((v) => fmt.pct(v, 1), { splitLine: { show: false }, scale: true })],
    series: [
      { name: 'Revenue', type: 'bar', data: months.map((r) => euro(r[1])), barMaxWidth: 28, itemStyle: { color: c.chart[0], borderRadius: [4, 4, 0, 0] } },
      { name: 'Gross margin %', type: 'line', yAxisIndex: 1, data: months.map((r) => r[3]), lineStyle: { width: 2.5, color: c.chart[1] }, itemStyle: { color: c.chart[1] }, symbol: 'circle', symbolSize: 6 },
    ],
  };
}

// Horizontal revenue bars ([label, cents, margin]); `selected` dims the other bars while a cross-filter or
// drill is active on this chart.
export function revenueBars(rows, c, { selected = null, motion = true } = {}) {
  return {
    ...base(c, motion),
    grid: { left: 8, right: 72, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p) => `${escape(p.name)}<br>Revenue: <b>${moneyText(rows[p.dataIndex][1])}</b><br>Gross margin %: <b>${fmt.pct(rows[p.dataIndex][2])}</b>`,
    },
    xAxis: valueAxis(axisEuro),
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r[0]) },
    series: [
      {
        name: 'Revenue',
        type: 'bar',
        barMaxWidth: 34,
        cursor: 'pointer',
        data: rows.map((r) => ({
          value: euro(r[1]),
          itemStyle: { color: c.chart[0], opacity: selected === null || selected === r[0] ? 1 : 0.35, borderRadius: [0, 4, 4, 0] },
        })),
        label: { show: true, position: 'right', color: c.text, fontFamily: MONO, formatter: (p) => axisEuro(p.value) },
      },
    ],
  };
}

// Trends: Current (accent) and PY (muted, dashed) per month on the left axis, R12 (chart-2) on the right axis,
// because the rolling sum is about twelve times a month; rows are [m, ...seven items].
export function trend(rows, c, motion = true) {
  const pick = (i) => rows.map((r) => euro(r[i]));
  return {
    ...base(c, motion),
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((p) => moneyText(p.value === null ? null : p.value * 100)) },
    xAxis: { type: 'category', data: monthLabels(rows.map((r) => r[0])), boundaryGap: false },
    yAxis: [valueAxis(axisEuro), valueAxis(axisEuro, { splitLine: { show: false }, scale: true })],
    series: [
      { name: 'Current', type: 'line', data: pick(1), lineStyle: { width: 2.5, color: c.accent }, itemStyle: { color: c.accent }, symbol: 'circle', symbolSize: 5 },
      { name: 'PY', type: 'line', data: pick(2), lineStyle: { width: 2, type: 'dashed', color: c.muted }, itemStyle: { color: c.muted }, symbol: 'none' },
      { name: 'R12', type: 'line', yAxisIndex: 1, data: pick(7), lineStyle: { width: 2, color: c.chart[1] }, itemStyle: { color: c.chart[1] }, symbol: 'none' },
    ],
  };
}

// Stacked columns per month: rows are [m, [value per member]]; `money` switches the axis to euros.
export function stacked(rows, members, c, { money = false, motion = true } = {}) {
  const show = money ? (v) => moneyText(v === null ? null : v * 100) : (v) => fmt.int(v);
  return {
    ...base(c, motion),
    legend: { type: 'scroll', bottom: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10 },
    grid: { left: 8, right: 16, top: 16, bottom: 36, containLabel: true },
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((p) => show(p.value)) },
    xAxis: { type: 'category', data: monthLabels(rows.map((r) => r[0])) },
    yAxis: valueAxis(money ? axisEuro : (v) => fmt.compact(v)),
    series: members.map((name, i) => ({
      name,
      type: 'bar',
      stack: 'total',
      barMaxWidth: 28,
      itemStyle: { color: c.chart[i % c.chart.length] },
      data: rows.map((r) => (money ? euro(r[1][i]) : r[1][i])),
    })),
  };
}

// Products: top 40 by revenue with the cumulative share on the secondary axis (0 to 100 %, line at 80 %).
export function pareto(rows, c, motion = true) {
  return {
    ...base(c, motion),
    grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: axisTooltip((p) => (p.seriesIndex === 0 ? moneyText(p.value === null ? null : p.value * 100) : fmt.pct(p.value))),
    },
    xAxis: { type: 'category', data: rows.map((r) => r[0]), axisLabel: { show: false }, axisTick: { show: false } },
    yAxis: [valueAxis(axisEuro), valueAxis((v) => fmt.pct(v, 0), { min: 0, max: 1, splitLine: { show: false } })],
    series: [
      { name: 'Revenue', type: 'bar', data: rows.map((r) => euro(r[1])), barCategoryGap: '25%', itemStyle: { color: c.chart[0], borderRadius: [3, 3, 0, 0] } },
      {
        name: 'Cumulative %',
        type: 'line',
        yAxisIndex: 1,
        data: rows.map((r) => r[2]),
        symbol: 'none',
        lineStyle: { width: 2.5, color: c.chart[1] },
        itemStyle: { color: c.chart[1] },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: c.muted, type: 'dashed' }, label: { color: c.muted, position: 'insideStartTop', formatter: fmt.pct(0.8, 0) }, data: [{ yAxis: 0.8 }] },
      },
    ],
  };
}

// Regions: current (chart-1) and PY (muted) per region; rows are [name, current, py].
export function regionBars(rows, c, { selected = null, motion = true } = {}) {
  const dim = (name) => (selected === null || selected === name ? 1 : 0.35);
  return {
    ...base(c, motion),
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', confine: true, axisPointer: { type: 'shadow' }, formatter: axisTooltip((p) => moneyText(p.value === null ? null : p.value * 100)) },
    xAxis: valueAxis(axisEuro),
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r[0]) },
    series: [
      { name: 'Current', type: 'bar', cursor: 'pointer', barMaxWidth: 18, data: rows.map((r) => ({ value: euro(r[1]), itemStyle: { color: c.chart[0], opacity: dim(r[0]) } })) },
      { name: 'PY', type: 'bar', cursor: 'pointer', barMaxWidth: 18, data: rows.map((r) => ({ value: euro(r[2]), itemStyle: { color: c.muted, opacity: dim(r[0]) } })) },
    ],
  };
}

// Regions: one bubble per country, x discount %, y gross margin %, size by revenue, one series per region (the
// card title names the axes).
export function scatter(countries, regions, c, motion = true) {
  const top = Math.max(1, ...countries.map((r) => r[2]));
  return {
    ...base(c, motion),
    legend: { type: 'scroll', bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10 },
    grid: { left: 8, right: 24, top: 16, bottom: 40, containLabel: true },
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p) => `${escape(p.data.name)} (${escape(p.seriesName)})<br>Discount %: <b>${fmt.pct(p.data.value[0])}</b><br>Gross margin %: <b>${fmt.pct(p.data.value[1])}</b><br>Revenue: <b>${moneyText(p.data.cents)}</b>`,
    },
    xAxis: valueAxis((v) => fmt.pct(v, 0), { scale: true }),
    yAxis: valueAxis((v) => fmt.pct(v, 0), { scale: true }),
    series: regions.map((region, i) => ({
      name: region,
      type: 'scatter',
      itemStyle: { color: c.chart[i % c.chart.length], opacity: 0.85 },
      data: countries.filter((r) => r[1] === region).map((r) => ({ name: r[0], value: [r[4], r[3]], cents: r[2], symbolSize: 10 + 30 * Math.sqrt(r[2] / top) })),
      symbolSize: (value, p) => p.data.symbolSize,
    })),
  };
}

// Targets: revenue columns (chart-1) and the target line (chart-2) on one scale; months without sales show the
// target only. The accent is not used here: in the light theme it equals chart-1.
export function targetCombo(months, c, motion = true) {
  return {
    ...base(c, motion),
    tooltip: { trigger: 'axis', confine: true, formatter: axisTooltip((p) => moneyText(p.value === null ? null : p.value * 100)) },
    xAxis: { type: 'category', data: monthLabels(months.map((r) => r[0])) },
    yAxis: valueAxis(axisEuro),
    series: [
      { name: 'Revenue', type: 'bar', data: months.map((r) => euro(r[1])), barMaxWidth: 26, itemStyle: { color: c.chart[0], borderRadius: [4, 4, 0, 0] } },
      { name: 'Target', type: 'line', data: months.map((r) => euro(r[2])), lineStyle: { width: 2.5, color: c.chart[1] }, itemStyle: { color: c.chart[1] }, symbol: 'circle', symbolSize: 5 },
    ],
  };
}

// Targets: attainment by region in ok (at least 100 %) or warning colours, with the line at 100 %.
export function attainment(rows, c, motion = true) {
  const values = rows.map((r) => r[1]).filter((v) => v !== null);
  const low = Math.min(0.8, ...values.map((v) => Math.floor(v * 20) / 20));
  const high = Math.max(1.1, ...values.map((v) => Math.ceil(v * 20) / 20));
  return {
    ...base(c, motion),
    grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `${escape(p.name)}: <b>${fmt.pct(p.value)}</b>` },
    xAxis: valueAxis((v) => fmt.pct(v, 0), { min: low, max: high }),
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r[0]) },
    series: [
      {
        name: 'Target attainment %',
        type: 'bar',
        barMaxWidth: 26,
        data: rows.map((r) => ({ value: r[1], itemStyle: { color: r[1] !== null && r[1] >= 1 ? c.ok : c.warn, borderRadius: [0, 4, 4, 0] } })),
        label: { show: true, position: 'right', color: c.text, fontFamily: MONO, formatter: (p) => fmt.pct(p.value) },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: c.text, width: 1.5 }, label: { show: false }, data: [{ xAxis: 1 }] },
      },
    ],
  };
}

// Background of an attainment cell: warning below 100 %, ok above, growing to SHADE_MAX % of the colour at 90 %
// and 110 %, so the cell text keeps 4.5:1 in both themes (tools/checks/contrast.mjs checks the extremes).
export const SHADE_MAX = 35;

export function cellShade(value) {
  if (value === null || value === undefined) return '';
  const d = Math.max(-0.1, Math.min(0.1, value - 1));
  const share = Math.round((Math.abs(d) / 0.1) * SHADE_MAX);
  return `color-mix(in srgb, var(${d < 0 ? '--warn' : '--ok'}) ${share}%, var(--surface))`;
}

// Draws options into elements with the kit's themes; charts are created on first use, re-created after a
// theme switch and resized with their element.
export function createChartHost(echarts, themes, mode) {
  const charts = new Map();
  let current = mode;
  const observer = typeof ResizeObserver === 'function'
    ? new ResizeObserver((entries) => entries.forEach((e) => charts.get(e.target)?.resize()))
    : null;
  return {
    draw(el, option, onClick) {
      let chart = charts.get(el);
      if (!chart) {
        chart = echarts.init(el, themes[current], { renderer: 'svg' });
        charts.set(el, chart);
        observer?.observe(el);
      }
      chart.setOption(option, { notMerge: true });
      chart.off('click');
      if (onClick) chart.on('click', onClick);
      chart.resize();
      return chart;
    },
    setMode(next) {
      if (next === current) return;
      current = next;
      for (const [el, chart] of charts) {
        observer?.unobserve(el);
        chart.dispose();
      }
      charts.clear();
    },
  };
}
