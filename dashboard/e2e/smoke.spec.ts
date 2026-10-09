import { expect, test } from "@playwright/test";

test("live → incident → session → action shows the gateway's reasoning", async ({ page }) => {
  await page.goto("/live");
  const card = page.getByTestId("incident-card").first();
  await expect(card).toContainText("Data exfiltration");
  await card.click();
  await expect(page.getByRole("heading", { name: /Run the test suite/ })).toBeVisible();
  await page.getByTestId("timeline-row").filter({ hasText: "ALPHA_MARKER" }).first().click();
  const gateway = page.getByTestId("verdict-gateway");
  await expect(gateway).toContainText("Out of scope");
  await expect(gateway).toContainText("The user asked to run and fix the tests.");
});

for (const width of [390, 768, 1440]) {
  test(`all pages fit at ${width}px without browser errors`, async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.setViewportSize({width, height: 900});
    for (const route of ["live", "sessions", "sessions/claude_code/demo-claude-1", "sessions/claude_code/demo-claude-1?action=1", "incidents", "explore", "evaluation", "rules"]) {
      await page.goto(`/${route}`);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator("main").getByRole("status")).toHaveCount(0);
      await page.waitForTimeout(250);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
    expect(errors).toEqual([]);
  });
}

test("action detail traps focus, closes with Escape and restores the trigger", async ({page}) => {
  await page.goto("/sessions/claude_code/demo-claude-1");
  const trigger = page.getByTestId("timeline-row").filter({hasText: "ALPHA_MARKER"}).first();
  await expect(trigger).toBeVisible();
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("close")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("link").last()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});
