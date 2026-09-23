// Headless Playwright check: load the built F1Grid site (served from web/dist,
// configured with VITE_API_BASE pointing at the running API container) and confirm
// it renders REAL predictions - not the synthetic fallback, not an empty table.
//
// Usage: SITE_URL=http://localhost:4173 node web/tests/playwright_check.mjs
// Exits non-zero on any failed assertion.
import { chromium } from "playwright";

const SITE = process.env.SITE_URL || "http://localhost:4173";
const MIN_ROWS = 15; // a real F1 grid has ~20 drivers; require a full-looking field

function fail(msg) {
  console.error("  FAIL: " + msg);
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

try {
  console.log("Loading " + SITE);
  // Wait on concrete elements, not networkidle: the app polls the API during a
  // cold start and animates continuously, so the network is rarely fully idle.
  await page.goto(SITE, { waitUntil: "domcontentloaded", timeout: 60000 });

  // The header must render.
  await page.waitForSelector("h1.display-title", { timeout: 15000 });

  // Real predictions must populate the timing tower (allow for an API cold start).
  await page.waitForSelector('[data-testid="timing-row"]', { timeout: 90000 });
  const rows = await page.locator('[data-testid="timing-row"]').count();
  if (rows < MIN_ROWS) fail(`only ${rows} timing rows rendered (expected >= ${MIN_ROWS})`);

  // The synthetic-data warning banner must be ABSENT (proves is_real_data true).
  const banner = await page.getByText("Running on synthetic demo data").count();
  if (banner !== 0) fail("synthetic-data banner is present -> not real data");

  // A win-probability percentage must be shown for the top driver.
  const towerText = await page.locator('[data-testid="timing-tower"]').innerText();
  if (!/\d+\.\d%/.test(towerText)) fail("no win-probability percentage rendered");

  // Capture the leader for the log.
  const firstDriver = await page
    .locator('[data-testid="timing-row"]')
    .first()
    .getAttribute("data-driver");

  if (errors.length) fail("page console errors: " + JSON.stringify(errors));

  console.log(`  PASS: ${rows} drivers rendered, leader=${firstDriver}, real data (no synthetic banner)`);
  await browser.close();
  process.exit(0);
} catch (e) {
  console.error(e && e.stack ? e.stack : String(e));
  await browser.close();
  process.exit(1);
}
