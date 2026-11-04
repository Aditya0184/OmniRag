import { test, expect } from "@playwright/test";
import path from "node:path";

test("real upload, worker indexing and source viewer", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Discover your documents." }),
  ).toBeVisible();
  await page
    .getByLabel("Upload PDF")
    .setInputFiles(path.resolve("../examples/procurement_sample.pdf"));
  await expect(page.getByText("2 pages · indexed").first()).toBeVisible({
    timeout: 120_000,
  });
  // Clicking the name selects the document as the question scope.
  await page
    .getByRole("button", { name: "procurement_sample.pdf", exact: true })
    .click();
  await expect(page.getByLabel("Document scope")).toHaveValue(
    (await page.getByLabel("Document scope").inputValue()) || "",
  );
  // The dedicated view button opens the original PDF in the source panel.
  await page
    .getByRole("button", { name: "View PDF of procurement_sample.pdf" })
    .click();
  await expect(page.getByLabel("Source viewer")).toBeVisible();
  const link = await page
    .getByRole("link", { name: "Open PDF" })
    .getAttribute("href");
  const source = await request.get(link!);
  expect(source.ok()).toBeTruthy();
  expect(source.headers()["content-type"]).toContain("application/pdf");
  await page.getByRole("button", { name: "Close source" }).click();
  await page.screenshot({
    path: "test-results/workspace-desktop.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("mobile layout does not overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Discover your documents." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
