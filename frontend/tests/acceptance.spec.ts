import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

async function uploadFresh(page: Page, fixture = "procurement_sample.pdf") {
  const name = `browser-${randomUUID().slice(0, 8)}-${fixture}`;
  const original = await readFile(path.resolve("../examples", fixture));
  // A trailing PDF comment gives each run new bytes, exercising ingestion rather than dedup.
  const buffer = Buffer.concat([original, Buffer.from(`\n% ${name}\n`)]);
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByLabel("Upload PDF")
    .setInputFiles({ name, mimeType: "application/pdf", buffer });
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  const uploaded = await response.json();
  expect(uploaded.duplicate).toBe(false);
  const row = page
    .locator(".document")
    .filter({ has: page.getByRole("button", { name, exact: true }) });
  return { name, buffer, id: uploaded.document.id as string, row };
}

async function ask(page: Page, question: string) {
  await page.getByLabel("Ask your workspace").fill(question);
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
    { timeout: 180_000 },
  );
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

test("fresh browser upload, no-match abstention and saved history", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const doc = await uploadFresh(page);
  await expect(doc.row.getByText("2 pages · indexed")).toBeVisible({
    timeout: 120_000,
  });
  await page.getByLabel("Document scope").selectOption(doc.id);
  await page.getByLabel("Search method").selectOption("bm25");
  const question = "Quasizorb nebular xenobiology?";
  const result = await ask(page, question);
  expect(result.status).toBe("no_relevant_passage");
  expect(result.evidence).toEqual([]);
  expect(result.model).toBeNull();
  expect(result.timings.generation_ms).toBe(0);
  await expect(page.getByLabel("Answer")).toContainText(
    "Keyword search found no passage",
  );
  const source = await request.get(`/api/v1/documents/${doc.id}/file`);
  expect(await source.body()).toEqual(doc.buffer);
  await page.reload();
  await page.getByRole("button", { name: /Query history/ }).click();
  await page
    .getByRole("button", { name: new RegExp(question.replace("?", "\\?")) })
    .first()
    .click();
  await expect(page.getByLabel("Answer")).toContainText(
    "No relevant passage",
  );
});

test("image-only PDF is indexed with OCR provenance", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const doc = await uploadFresh(page, "scanned_sample.pdf");
  await expect(
    doc.row.getByText("1 pages · indexed", { exact: true }),
  ).toBeVisible({
    timeout: 120_000,
  });
  await expect(doc.row).toContainText("OCR transcription on pages [1].");
  const response = await request.get(`/api/v1/documents/${doc.id}`);
  const detail = await response.json();
  expect(detail.pages[0].method).toBe("ocr");
  expect(detail.pages[0].engine).toContain("tesseract");
});

test("actual Ollama answers, page citations and keyword-overlap abstention", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.OMNIRAG_E2E_MODEL !== "1",
    "Set OMNIRAG_E2E_MODEL=1 with local Ollama running.",
  );
  test.setTimeout(420_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  const doc = await uploadFresh(page);
  await expect(doc.row.getByText("2 pages · indexed")).toBeVisible({
    timeout: 120_000,
  });
  await page.getByLabel("Document scope").selectOption(doc.id);
  await page.getByLabel("Search method").selectOption("bm25");
  for (const item of [
    {
      question: "What is the standard delivery window for Orion Supplies?",
      value: "14 calendar days",
      page: 1,
    },
    {
      question: "How long must the acceptance review take?",
      value: "5 business days",
      page: 2,
    },
  ]) {
    const result = await ask(page, item.question);
    expect(result.status).toBe("answered");
    expect(result.verification).toBe("grounded_citation_v1");
    for (const claim of result.claims) {
      expect(claim.citations.length).toBeGreaterThan(0);
      expect(claim.citations[0].quote.length).toBeGreaterThan(11);
    }
    await expect(page.getByLabel("Answer")).toContainText("Answer");
    await expect(page.getByLabel("Answer")).toContainText(item.value);
    const citation = result.claims
      .flatMap((c: { citations: unknown[] }) => c.citations)
      .find((c: { page: number }) => c.page === item.page);
    expect(citation.document_id).toBe(doc.id);
    await page
      .getByRole("button", {
        name: `${doc.name} · p. ${item.page}`,
        exact: true,
      })
      .first()
      .click();
    const viewer = page.getByLabel("Source viewer");
    await expect(viewer.locator("blockquote")).toHaveText(citation.quote);
    await expect(viewer.locator("iframe")).toHaveAttribute(
      "src",
      `/api/v1/documents/${doc.id}/file#page=${item.page}`,
    );
    const link = viewer.getByRole("link", { name: "Open PDF" });
    await expect(link).toHaveAttribute(
      "href",
      `/api/v1/documents/${doc.id}/file#page=${item.page}`,
    );
    expect(
      await (await request.get((await link.getAttribute("href"))!)).body(),
    ).toEqual(doc.buffer);
    await page.screenshot({
      path: `test-results/live-citation-page-${item.page}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Close source" }).click();
  }
  const unsupported = await ask(
    page,
    "What is the CEO's birthday at Orion Supplies?",
  );
  expect(unsupported.evidence.length).toBeGreaterThan(0);
  // The model decides the document lacks the fact; the abstention explains itself.
  expect(unsupported.status).toBe("unsupported_question");
  expect(unsupported.claims).toEqual([]);
  expect(unsupported.reason.length).toBeGreaterThan(10);
  expect(errors).toEqual([]);
});
