import { test, expect, Page } from "@playwright/test";

async function signin(page: Page, role: string) {
  await page.getByLabel("Username", { exact: true }).fill(role);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.AEGIS_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Every change, accounted for." }),
  ).toBeVisible();
}
async function navigate(page: Page, label: string) {
  const menu = page.getByRole("button", { name: "Toggle navigation" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: label, exact: true })
    .click();
}
test("operator recovery, CCB closure, three-person change and responsive console", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await signin(page, "operator");
  await expect(
    page.getByRole("button", { name: "Run scan", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Demonstration controls/ }).click();
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("drift");
  await page.getByRole("button", { name: "Apply scenario" }).click();
  await page.getByRole("button", { name: "Run scan", exact: true }).click();
  await expect(
    page.getByText("File and effective simulator revision verified."),
  ).toBeVisible();
  await page.screenshot({
    path: process.env.AEGIS_QA_SCREENSHOTS
      ? process.env.AEGIS_QA_SCREENSHOTS + "/overview.png"
      : "test-results/overview.png",
    fullPage: true,
  });
  await navigate(page, "Incidents");
  await page
    .getByLabel("Reason / resolution")
    .fill("Examined synthetic parameter drift and restoration evidence");
  await page.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(
    page.getByText("Incident acknowledged", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signin(page, "ccb");
  await navigate(page, "Incidents");
  await page
    .getByLabel("Reason / resolution")
    .fill("CCB reviewed verified recovery and persistent evidence");
  await page.getByRole("button", { name: "Close after review" }).click();
  await expect(
    page.getByText("Incident reviewed and closed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signin(page, "operator");
  await navigate(page, "Change control");
  await page.getByRole("button", { name: "New proposal" }).click();
  const version = "v-ui-" + Date.now();
  await page.getByLabel("Release version").fill(version);
  await page.getByLabel("Synthetic upper heart-rate value").fill("125");
  await page.getByRole("button", { name: "Submit proposal" }).click();
  await expect(
    page.getByText("Configuration proposal submitted", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signin(page, "reviewer");
  await navigate(page, "Change control");
  await page
    .getByLabel("Decision reason")
    .fill("Validated exact synthetic fixture content");
  await page.getByRole("button", { name: "Accept technical review" }).click();
  await expect(
    page.getByText("Technical review accepted", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signin(page, "ccb");
  await navigate(page, "Change control");
  await page
    .getByLabel("Decision reason")
    .fill("Approved scoped deployment for demonstration");
  await page.getByRole("button", { name: "Approve deployment" }).click();
  await page.getByRole("button", { name: "Deploy approved release" }).click();
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
  await navigate(page, "Monitor nodes");
  await expect(page.getByText(version, { exact: true })).toBeVisible();
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await navigate(page, "Overview");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if (width === 320)
      await page.screenshot({
        path: process.env.AEGIS_QA_SCREENSHOTS
          ? process.env.AEGIS_QA_SCREENSHOTS + "/mobile.png"
          : "test-results/mobile.png",
        fullPage: true,
      });
  }
  await navigate(page, "Audit trail");
  await expect(
    page.getByText("Chain consistent", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
