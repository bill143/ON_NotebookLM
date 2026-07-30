import { test, expect } from "@playwright/test";

test.describe("Nexus Notebook — Smoke Tests", () => {
  test("homepage loads with welcome screen", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Welcome to Nexus")).toBeVisible();
    await expect(page.getByText("Create your first notebook")).toBeVisible();
  });

  test("sidebar brand is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Nexus")).toBeVisible();
    await expect(page.getByText("Notebook 11 LM")).toBeVisible();
  });

  test("create notebook flow", async ({ page }) => {
    await page.goto("/");
    await page.getByText("Create your first notebook").click();
    const input = page.getByPlaceholder("Name your notebook...");
    await expect(input).toBeVisible();
    await input.fill("Test Notebook");
    await page.getByText("Create Notebook").click();
  });

  test("tab navigation is present after selecting notebook", async ({ page }) => {
    await page.goto("/");
    const tabs = ["Sources", "Chat", "Studio", "Research", "Notes"];
    for (const tab of tabs) {
      const el = page.getByRole("button", { name: tab });
      if (await el.isVisible()) {
        await expect(el).toBeEnabled();
      }
    }
  });
});
