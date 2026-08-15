import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

interface ScenarioResponsePoint {
  days_forward: number;
  move_pct: number;
  vol_shift: number;
  theoretical_value: number | null;
}

interface ScenarioResponse {
  points: ScenarioResponsePoint[];
}

async function assertChartGeometry(card: Locator, minimumPoints: number) {
  const surface = card.locator('svg.recharts-surface[role="application"]');
  const dots = card.locator("circle.recharts-line-dot");
  await expect(surface).toBeVisible();
  await expect(dots.first()).toBeVisible();
  expect(await dots.count()).toBeGreaterThanOrEqual(minimumPoints);

  const surfaceBox = await surface.boundingBox();
  expect(surfaceBox).not.toBeNull();
  for (const dot of await dots.all()) {
    const dotBox = await dot.boundingBox();
    expect(dotBox).not.toBeNull();
    expect(dotBox!.x).toBeGreaterThanOrEqual(surfaceBox!.x - 1);
    expect(dotBox!.y).toBeGreaterThanOrEqual(surfaceBox!.y - 1);
    expect(dotBox!.x + dotBox!.width).toBeLessThanOrEqual(surfaceBox!.x + surfaceBox!.width + 1);
    expect(dotBox!.y + dotBox!.height).toBeLessThanOrEqual(surfaceBox!.y + surfaceBox!.height + 1);
  }

  const curveBox = await card.locator("path.recharts-line-curve").boundingBox();
  expect(curveBox).not.toBeNull();
  expect(curveBox!.width).toBeGreaterThan(80);
  expect(curveBox!.height).toBeGreaterThan(8);
}

function theoreticalValues(points: ScenarioResponsePoint[], days: number, move: number) {
  return points
    .filter((point) => point.days_forward === days && point.move_pct === move)
    .map((point) => point.theoretical_value)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

async function openDeterministicAnalytics(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "SPY", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "AAPL", exact: true }).click();
  await expect(page.getByRole("heading", { name: "AAPL", level: 1 })).toBeVisible();

  await page.getByLabel("Expiration").selectOption("2026-08-14");
  const contractId = "AAPL-2026-08-14-215.00-C";
  await page.locator(`[data-contract-id="${contractId}"]`).click();
  await expect(page.getByText("AAPL 2026-08-14 215", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Add Long", exact: true }).click();
  await expect(page.getByText("1 leg staged", { exact: true })).toBeVisible();

  const scenarioResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/strategies/scenario-grid") && response.request().method() === "POST"
  );
  await page.getByRole("tab", { name: "Analytics" }).click();
  const scenarioResponse = (await (await scenarioResponsePromise).json()) as ScenarioResponse;
  return scenarioResponse;
}

async function captureAnalyticsEvidence(page: Page, testInfo: TestInfo) {
  const smile = page.getByTestId("smile-skew-card");
  const term = page.getByTestId("term-structure-card");
  const scenarioGrid = page.getByTestId("scenario-grid");

  await expect(smile).toBeVisible();
  await expect(term).toBeVisible();
  await assertChartGeometry(smile, 16);
  await assertChartGeometry(term, 5);
  await expect(smile.getByText("Strike", { exact: true })).toBeVisible();
  await expect(smile.getByText("Implied volatility (%)", { exact: true })).toBeVisible();
  await expect(term.getByText("Days to expiry (DTE)", { exact: true })).toBeVisible();
  await expect(term.getByText("ATM IV (%)", { exact: true })).toBeVisible();

  const smileDots = smile.locator("circle.recharts-line-dot");
  await smileDots.nth(Math.floor((await smileDots.count()) / 2)).hover();
  await expect(smile.getByText(/IV: \d/)).toBeVisible();
  await expect(smile.getByText(/Expiration: 2026-08-14/)).toBeVisible();

  const termDots = term.locator("circle.recharts-line-dot");
  await termDots.nth(2).hover();
  await expect(term.getByText(/DTE: \d+ days/)).toBeVisible();
  await expect(term.getByText(/ATM IV: \d/)).toBeVisible();

  await page.mouse.move(0, 0);
  await smile.screenshot({ path: testInfo.outputPath("smile-skew.png") });
  await term.screenshot({ path: testInfo.outputPath("term-structure.png") });
  await scenarioGrid.screenshot({ path: testInfo.outputPath("scenario-pre-expiry.png") });
  await page
    .locator('[role="tabpanel"][data-state="active"]')
    .evaluate((panel) => {
      panel.scrollTop = 0;
      panel.scrollLeft = 0;
    });
  await page.screenshot({ path: testInfo.outputPath("analytics-workstation.png") });
}

test("deterministic analytics workflow is finite, responsive, and expiry-aware", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const scenarioResponse = await openDeterministicAnalytics(page);
  await expect(page.getByText("Mock / synthetic").first()).toBeVisible();

  const preExpiryValues = theoreticalValues(scenarioResponse.points, 0, 0);
  expect(preExpiryValues).toHaveLength(5);
  expect(
    new Set(preExpiryValues.map((value) => value.toFixed(6))).size,
    `pre-expiry values: ${JSON.stringify(preExpiryValues)}`
  ).toBeGreaterThan(1);

  const exactExpiryPoints = scenarioResponse.points.filter((point) => point.days_forward === 14);
  expect(exactExpiryPoints).toHaveLength(35);
  for (const move of new Set(exactExpiryPoints.map((point) => point.move_pct))) {
    const values = theoreticalValues(exactExpiryPoints, 14, move);
    expect(values).toHaveLength(5);
    expect(new Set(values.map((value) => value.toFixed(8))).size).toBe(1);
  }

  await captureAnalyticsEvidence(page, testInfo);

  const preExpiryCells = page.locator('td[data-scenario-key^="0:0:"]');
  await expect(preExpiryCells).toHaveCount(5);
  expect(new Set(await preExpiryCells.allTextContents()).size).toBeGreaterThan(1);

  await page.getByRole("button", { name: "+14d", exact: true }).click();
  await expect(page.getByTestId("scenario-day-state")).toContainText(
    "At or after expiry: values reflect expiry payoff; volatility shifts have no effect."
  );
  await expect(page.getByRole("columnheader", { name: "Expiry payoff" })).toBeVisible();
  await expect(page.locator('td[data-scenario-key^="14:"]')).toHaveCount(7);
  await page.getByTestId("scenario-grid").screenshot({
    path: testInfo.outputPath("scenario-at-expiry.png"),
  });

  await expect(page.locator("body")).not.toContainText(/NaN|Infinity|-Infinity/);
  const pageOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(pageOverflow).toBeLessThanOrEqual(1);
  expect(consoleErrors).toEqual([]);
});
