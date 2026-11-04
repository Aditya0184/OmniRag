import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

test("hybrid methods retrieve scoped evidence without generating an answer", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const readiness = await (await request.get("/api/v1/readiness")).json();
  test.skip(
    !readiness.retrieval?.enabled,
    "Phase 2 semantic search must be enabled.",
  );
  await expect(page.getByLabel("Search method")).toHaveValue("hybrid_rerank");
  const documents = await (await request.get("/api/v1/documents")).json();
  const doc = documents.find(
    (item: { name: string; status: string; vector_status: string }) =>
      item.name.endsWith("procurement_sample.pdf") &&
      item.status === "ready" &&
      item.vector_status === "ready",
  );
  expect(doc).toBeTruthy();
  const history = await (await request.get("/api/v1/history")).json();
  for (const mode of ["bm25", "dense", "hybrid", "hybrid_rerank"]) {
    await page.getByLabel("Search method").selectOption(mode);
    const response = await request.post("/api/v1/search", {
      data: {
        question: "What is the delivery window?",
        document_ids: [doc.id],
        retrieval_mode: mode,
      },
    });
    expect(response.status(), await response.text()).toBe(200);
    const result = await response.json();
    expect(result.retrieval_mode).toBe(mode);
    expect(result.evidence.length).toBeGreaterThan(0);
    expect(
      result.evidence.every(
        (row: { document_id: string }) => row.document_id === doc.id,
      ),
    ).toBe(true);
  }
  expect(await (await request.get("/api/v1/history")).json()).toEqual(history);
});

test("fresh PDF reaches hybrid indexing and produces a real cited answer", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.OMNIRAG_E2E_MODEL !== "1",
    "Requires actual local Ollama.",
  );
  test.setTimeout(420_000);
  await page.goto("/");
  const readiness = await (await request.get("/api/v1/readiness")).json();
  test.skip(!readiness.retrieval?.enabled, "Requires Phase 2 semantic search.");
  const original = await readFile(
    path.resolve("../examples/procurement_sample.pdf"),
  );
  const name = `hybrid-${randomUUID().slice(0, 8)}.pdf`;
  const buffer = Buffer.concat([original, Buffer.from(`\n% ${name}\n`)]);
  const uploaded = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByLabel("Upload PDF")
    .setInputFiles({ name, mimeType: "application/pdf", buffer });
  const doc = (await (await uploaded).json()).document;
  const row = page
    .locator(".document")
    .filter({ has: page.getByRole("button", { name, exact: true }) });
  await expect(row).toContainText("Semantic index ready", { timeout: 120_000 });
  await page.getByLabel("Document scope").selectOption(doc.id);
  await page.getByLabel("Search method").selectOption("hybrid_rerank");
  await page
    .getByLabel("Ask your workspace")
    .fill("What is the standard delivery window for Orion Supplies?");
  const answerResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
    { timeout: 180_000 },
  );
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const response = await answerResponse;
  expect(response.status(), await response.text()).toBe(200);
  const answer = await response.json();
  expect(answer.retrieval_mode).toBe("hybrid_rerank");
  expect(answer.retrieval_collection).toMatch(/^chunks_/);
  expect(answer.status).toBe("answered");
  await expect(page.getByLabel("Answer")).toContainText("14 calendar days");
  await page
    .getByRole("button", { name: `${name} · p. 1`, exact: true })
    .first()
    .click();
  await expect(
    page.getByLabel("Source viewer").locator("blockquote"),
  ).toContainText("14 calendar days");
  expect(
    await (await request.get(`/api/v1/documents/${doc.id}/file`)).body(),
  ).toEqual(buffer);
  await page.screenshot({
    path: "test-results/phase2-hybrid-answer.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close source" }).click();
  await page.reload();
  await page.getByRole("button", { name: /Query history/ }).click();
  await page
    .getByRole("button", {
      name: /What is the standard delivery window for Orion Supplies/,
    })
    .first()
    .click();
  await expect(page.getByLabel("Answer")).toContainText("Hybrid + reranking");
  await expect(page.getByLabel("Search method")).toHaveValue("hybrid_rerank");
});

test("policy paraphrase is answered while personal shipment status abstains", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.OMNIRAG_E2E_MODEL !== "1",
    "Requires actual local Ollama.",
  );
  test.setTimeout(240_000);
  const documents = await (await request.get("/api/v1/documents")).json();
  const doc = documents.find(
    (item: { name: string; vector_status: string }) =>
      item.name === "procurement_sample.pdf" && item.vector_status === "ready",
  );
  expect(doc).toBeTruthy();
  await page.goto("/");
  await page.getByLabel("Document scope").selectOption(doc.id);
  await page.getByLabel("Search method").selectOption("hybrid_rerank");
  const question = "How long until my purchased goods arrive?";
  await page.getByLabel("Ask your workspace").fill(question);
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
    { timeout: 180_000 },
  );
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  const answer = await response.json();
  // This loose paraphrase sits at the 2B model's limit: it answers in most runs
  // (see the quality fixture, 10/10) but may honestly withhold on a weak pass.
  // Either way the reply must stay grounded; a fabricated value must never appear.
  expect(["answered", "unsupported_question"]).toContain(answer.status);
  expect(answer.verification).toBe("grounded_citation_v1");
  expect(JSON.stringify(answer)).not.toContain("evidence_assessment");
  if (answer.status === "answered") {
    const claim = answer.claims[0];
    expect(claim.citations.length).toBeGreaterThan(0);
    expect(claim.citations[0].document_id).toBe(doc.id);
    expect(claim.citations[0].page).toBe(1);
    await expect(page.getByLabel("Answer")).toContainText("14 calendar days");
    await page
      .getByRole("button", { name: `${doc.name} · p. 1`, exact: true })
      .first()
      .click();
    await expect(
      page.getByLabel("Source viewer").locator("blockquote"),
    ).toHaveText(claim.citations[0].quote);
  } else {
    expect(answer.claims).toEqual([]);
    expect(answer.reason.length).toBeGreaterThan(10);
  }
  await page.screenshot({
    path: "test-results/phase7-paraphrase.png",
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("button", { name: /Query history/ }).click();
  await page
    .getByRole("button", { name: /How long until my purchased goods arrive/ })
    .first()
    .click();
  await expect(page.getByLabel("Answer")).toContainText("14 calendar days");
  const unsupported = await request.post("/api/v1/queries", {
    data: {
      question: "Has my Orion Supplies order O-517 arrived today?",
      document_ids: [doc.id],
      retrieval_mode: "hybrid_rerank",
    },
    timeout: 180_000,
  });
  expect(unsupported.status(), await unsupported.text()).toBe(200);
  expect((await unsupported.json()).status).toBe("unsupported_question");
  expect((await unsupported.json()).claims).toEqual([]);
});
