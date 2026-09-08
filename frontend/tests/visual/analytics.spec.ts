import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

interface ScenarioResponsePoint {
  days_forward: number;
  move_pct: number;
  vol_shift: number;
  theoretical_value: number | null;
}

interface ScenarioResponse {
  points: ScenarioResponsePoint[];
  conditional_settlement: boolean;
  day_states: Array<{
    days_forward: number;
    expiration_state: string;
    message: string | null;
  }>;
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

test("mixed-expiration strategies keep valuation and conditional settlement semantics", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "SPY", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "AAPL", exact: true }).click();
  await expect(page.getByRole("heading", { name: "AAPL", level: 1 })).toBeVisible();

  await page.getByLabel("Expiration").selectOption("2026-08-14");
  await page.locator('[data-contract-id="AAPL-2026-08-14-215.00-C"]').click();
  await expect(page.getByText("AAPL 2026-08-14 215", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Add Short", exact: true }).click();
  await expect(page.getByText("1 leg staged", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Chain" }).click();
  await page.getByLabel("Expiration").selectOption("2026-08-21");
  await page.locator('[data-contract-id="AAPL-2026-08-21-215.00-C"]').click();
  await expect(page.getByText("AAPL 2026-08-21 215", { exact: true })).toBeVisible();

  const mixedPriceResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/strategies/price") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Add Long", exact: true }).click();
  await expect(page.getByText("2 legs staged", { exact: true })).toBeVisible();
  const mixedPriceResponse = await mixedPriceResponsePromise;
  const mixedPrice = await mixedPriceResponse.json();
  expect(mixedPrice.max_profit).toBeNull();
  expect(mixedPrice.max_loss).toBeNull();
  expect(mixedPrice.max_profit_state).toBe("unavailable");
  expect(mixedPrice.max_loss_state).toBe("unavailable");
  expect(mixedPrice.breakevens).toEqual([]);
  expect(mixedPrice.breakeven_intervals).toEqual([]);
  expect(mixedPrice.payoff).toEqual([]);
  expect(mixedPrice.payoff_unavailable_reason).toContain("settlement spots can differ");
  expect(mixedPrice.entry_cost).not.toBeNull();
  expect(mixedPrice.theoretical_value).not.toBeNull();

  const reason = "Exact single-spot expiry payoff, global bounds, and breakevens are unavailable for multiple option expirations because settlement spots can differ.";
  await expect(page.getByText(reason).first()).toBeVisible();
  await expect(page.getByText("Unavailable").first()).toBeVisible();
  await expect(page.getByText("Payoff unavailable", { exact: false })).toHaveCount(0);

  const scenarioResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/strategies/scenario-grid") && response.request().method() === "POST"
  );
  await page.getByRole("tab", { name: "Analytics" }).click();
  const scenarioResponse = await scenarioResponsePromise;
  const scenario = (await scenarioResponse.json()) as ScenarioResponse;
  expect(scenario.conditional_settlement).toBe(true);
  expect(scenario.points.length).toBeGreaterThan(0);
  expect(scenario.day_states.find((state) => state.days_forward === 14)?.expiration_state).toBe("mixed");
  expect(scenario.day_states.find((state) => state.days_forward === 30)?.expiration_state).toBe("at_or_after_expiry");
  expect(scenario.day_states.find((state) => state.days_forward === 30)?.message).toContain(
    "not a global risk bound"
  );

  await expect(page.getByTestId("scenario-conditional-notice")).toBeVisible();
  await page.getByRole("button", { name: "+14d", exact: true }).click();
  await expect(page.getByTestId("scenario-day-state")).toContainText("conditional settlement illustration");
  await page.getByRole("button", { name: "+30d", exact: true }).click();
  await expect(page.getByRole("columnheader", { name: "Conditional settlement" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Expiry payoff" })).toHaveCount(0);
  await expect(page.getByTestId("scenario-day-state")).toContainText("after final expiry");
  await page.getByTestId("scenario-grid").screenshot({ path: testInfo.outputPath("scenario-mixed-final-expiry.png") });

  await page.getByRole("tab", { name: "Strategy" }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const loadButtons = page.getByRole("button", { name: "Load Custom Strategy", exact: true });
  await expect(loadButtons.last()).toBeVisible();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await loadButtons.last().click();
  await expect(page.getByText("2 legs staged", { exact: true })).toBeVisible();
  await expect(page.getByText(reason).first()).toBeVisible();

  await expect(page.locator("body")).not.toContainText(/NaN|Infinity|-Infinity/);
});
