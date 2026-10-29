// Screenshots and browser checks of the replica (umbrella section 12): every tab at 1440 x 900 and 390 x 844,
// in the dark and the light theme, plus the interactions of docs/screenshots/SHOTLIST.md. A built-in static
// server serves web/ on 127.0.0.1; the run fails on any request that leaves that server, on a console error or
// page error, and on horizontal scrolling of the page. With URL=<address of the published page> it checks that page
// instead of the local copy (requests must then stay on that address).
// Usage (from the repository root, Node 22; Playwright is not a dependency of this repository):
//   PLAYWRIGHT_FROM=<package.json of a folder that has playwright installed> OUT=<folder outside the repository> \
//     node tools/checks/shots.mjs
// It also writes thumb-1440.jpg (the Overview at 1440 x 900, dark) for the portfolio hub; THUMB_QUALITY sets the
// JPEG quality (default 80).
// Chrome comes from the local installation (channel "chrome"); nothing is downloaded.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const ROOT = path.resolve('web');
const REPO = path.resolve('.');
const FROM = process.env.PLAYWRIGHT_FROM;
const OUT = process.env.OUT ? path.resolve(process.env.OUT) : null;
if (!FROM || !OUT) {
  console.error('shots: set PLAYWRIGHT_FROM (a package.json path) and OUT (a folder outside the repository)');
  process.exit(2);
}
if (OUT === REPO || OUT.startsWith(REPO + path.sep)) {
  console.error('shots: OUT must lie outside the repository');
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });
const { chromium } = createRequire(FROM)('playwright');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
};
const server = http.createServer((req, res) => {
  const route = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = path.join(ROOT, route.endsWith('/') ? `${route}index.html` : route);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404);
    res.end('not found');
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
const LIVE = process.env.URL ? process.env.URL.replace(/\/+$/, '') : null;
if (!LIVE) await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const BASE = LIVE ?? `http://127.0.0.1:${server.address().port}`;

const TABS = ['overview', 'trends', 'products', 'regions', 'customers', 'targets'];
const SIZES = [[1440, 900], [390, 844]];
const problems = [];
let shots = 0;

async function open(browser, theme, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await context.addInitScript((mode) => {
    try {
      localStorage.setItem('hh-theme', mode);
    } catch {
      /* storage blocked: the theme falls back to the system preference */
    }
  }, theme);
  const page = await context.newPage();
  const where = `${theme} ${width}`;
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`${where}: console error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`${where}: page error: ${err.message}`));
  page.on('request', (req) => {
    const url = req.url();
    if (!url.startsWith(BASE) && !url.startsWith('data:') && !url.startsWith('blob:')) problems.push(`${where}: external request ${url}`);
  });
  return { context, page, where };
}

async function load(page, tab) {
  await page.goto(`${BASE}/index.html?view=${tab}#${tab}`);
  await page.waitForSelector('#app[data-state="ready"]', { timeout: 20000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(250);
}

async function shot(page, where, name, options = {}) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 1) problems.push(`${where}: ${name} scrolls sideways by ${overflow} px`);
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true, ...options });
  shots += 1;
}

const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  for (const theme of ['dark', 'light']) {
    for (const size of SIZES) {
      const { context, page, where } = await open(browser, theme, size);
      for (const tab of TABS) {
        await load(page, tab);
        await shot(page, where, `${theme}-${size[0]}-${tab}`);
      }
      await context.close();
    }
  }
  // interactions, dark, 1440 px
  const { context, page, where } = await open(browser, 'dark', SIZES[0]);
  try {
    await load(page, 'overview');
    await shot(page, where, '09-replica', { fullPage: false });
    // the hub thumbnail: 1440 x 900, JPEG (THUMB_QUALITY, default 80)
    await page.screenshot({ path: path.join(OUT, 'thumb-1440.jpg'), type: 'jpeg', quality: Number(process.env.THUMB_QUALITY ?? 80) });
    await page.click('#analyse-by button:has-text("Region")');
    await page.waitForTimeout(250);
    await shot(page, where, 'dark-1440-overview-analyse-region');
    await load(page, 'products');
    await page.selectOption('#drill-select', 'Tents');
    await page.waitForTimeout(250);
    await page.focus('#table-products .sku');
    await page.waitForSelector('#tip:not([hidden])', { timeout: 5000 });
    await shot(page, where, 'dark-1440-products-drill-tooltip', { fullPage: false });
    const drilled = await page.textContent('#crumbs');
    if (!drilled.includes('Tents')) problems.push(`${where}: the drill did not reach Tents`);
    await load(page, 'customers');
    await page.fill('#customer-search', 'zzzz-no-such-customer');
    if (!(await page.textContent('#table-customers')).includes('No customer matches the search')) {
      problems.push(`${where}: the customer search did not filter`);
    }
    await page.click('#about-open');
    await page.waitForSelector('#about[open]');
    await shot(page, where, 'dark-1440-about', { fullPage: false });
    await page.keyboard.press('Escape');
    await page.click('#reset');
    const stored = await page.evaluate(() => localStorage.getItem('pf.sales-performance-dashboard.v1'));
    if (!stored || JSON.parse(stored).years.join() !== '2025') problems.push(`${where}: Reset did not store the default year`);
  } catch (error) {
    problems.push(`${where}: interaction failed: ${error.message.split('\n')[0]}`);
  }
  await context.close();
} finally {
  await browser.close();
  if (!LIVE) server.close();
}

for (const problem of problems) console.log(`FAIL ${problem}`);
console.log(`shots: ${shots} screenshots of ${LIVE ?? 'web/'} in ${OUT}, ${problems.length} problems`);
process.exit(problems.length ? 1 : 0);
