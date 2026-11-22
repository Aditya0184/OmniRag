import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

async function uploadFresh(page: Page, fixture = "procurement_sample.pdf") {
  const name = `grounded-${randomUUID().slice(0, 8)}-${fixture}`;
  const original = await readFile(path.resolve("../examples", fixture));
  const buffer = Buffer.concat([original, Buffer.from(`\n% ${name}\n`)]);
  const responsePromise = page.waitForResponse(
    (r) => r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByLabel("Upload PDF")
    .setInputFiles({ name, mimeType: "application/pdf", buffer });
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  const uploaded = await response.json();
  const row = page
    .locator(".document")
    .filter({ has: page.getByRole("button", { name, exact: true }) });
  return { name, id: uploaded.document.id as string, row };
}

async function ask(page: Page, question: string) {
  await page.getByLabel("Ask your workspace").fill(question);
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
    { timeout: 180_000 },
  );
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

test("overview question, summary and follow-up in the browser", async ({
  page,
}) => {
  test.skip(
    process.env.OMNIRAG_E2E_MODEL !== "1",
    "Requires actual local Ollama.",
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

  // The overview card appears once the worker generated it; older documents can
  // be summarized on demand, so wait for either state.
  const overview = page.getByLabel("Document overview");
  await expect(overview).toBeVisible();
  const summaryButton = overview.getByRole("button", {
    name: "Summarize document",
  });
  const summaryDone = page.waitForResponse(
    (r) => r.url().endsWith("/summary") && r.request().method() === "POST",
    { timeout: 180_000 },
  );
  await summaryButton.click();
  const summaryResponse = await summaryDone;
  expect(summaryResponse.status(), await summaryResponse.text()).toBe(200);
  await expect(overview).toContainText(/document|policy|sample/i, {
    timeout: 120_000,
  });

  // Overview-style question answered with citations.
  const broad = await ask(page, "What is in this PDF?");
  expect(broad.status).toBe("answered");
  expect(broad.intent).toBe("overview");
  expect(broad.retrieval_mode).toBe("coverage");
  await expect(page.getByLabel("Answer")).toContainText(/procurement|delivery|policy/i);

  // Summarize request uses the document summary.
  const summarized = await ask(page, "Summarize this.");
  expect(summarized.status).toBe("answered");
  expect(summarized.verification).toBe("document_summary");
  await expect(page.getByLabel("Answer")).toContainText(/page|summary/i);

  // Follow-up stays in the same document with conversation context. The 2B
  // model occasionally withholds this paraphrase; both outcomes must be grounded.
  const followUp = await ask(page, "What is the delivery window?");
  expect(followUp.scope.source).toBe("selection");
  if (followUp.status === "answered") {
    expect(JSON.stringify(followUp.claims)).toContain("14 calendar days");
  } else {
    expect(followUp.status).toBe("unsupported_question");
    expect(followUp.claims).toEqual([]);
  }
  expect(errors).toEqual([]);
});

test("clarification flow offers ready documents", async ({ page }) => {
  test.skip(
    process.env.OMNIRAG_E2E_MODEL !== "1",
    "Requires actual local Ollama.",
  );
  test.setTimeout(420_000);
  await page.goto("/");
  const readiness = await (await page.request.get("/api/v1/readiness")).json();
  test.skip(
    (readiness.retrieval?.documents?.ready ?? 0) < 2,
    "Needs at least two ready documents.",
  );
  await page.getByLabel("Ask your workspace").fill("Tell me about this document.");
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const result = (await (await pending).json()) as {
    status: string;
    candidates?: { id: string; name: string }[];
  };
  test.skip(result.status !== "clarification_needed", "No ambiguity in this workspace.");
  await expect(page.getByLabel("Answer")).toContainText("Choose");
  expect(result.candidates!.length).toBeGreaterThan(1);
  const first = result.candidates![0];
  // Choosing a document resets the context, so the card unmounts until the real
  // model answers; await the second query instead of the transient card.
  const chosen = page.waitForResponse(
    (r) => r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
    { timeout: 180_000 },
  );
  await page
    .getByLabel("Answer")
    .getByRole("button", { name: first.name, exact: true })
    .click();
  const followUp = await (await chosen).json();
  expect(followUp.scope.document_ids).toEqual([first.id]);
  await expect(page.getByLabel("Answer")).toBeVisible({ timeout: 30_000 });
});

// Deterministic UI regressions: no inference or live workspace writes.
test("refresh preserves context and clarification uses the chosen document", async ({ page }) => {
  test.setTimeout(30000);
  const docs = ["a", "b"].map(id => ({ id, name: `${id}.pdf`, status: "ready", page_count: 1, vector_status: "ready", warnings: [] }));
  const queries: any[] = [];
  let refreshes = 0;
  await page.route("**/api/v1/documents", route => { refreshes++; return route.fulfill({ json: docs }); });
  await page.route("**/api/v1/history", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/documents/*/summary?*", route => route.fulfill({ json: { status: "ready", created_at: 1, content: { summary: "Overview", key_points: [{ text: "Persistent point", pages: [] }] } } }));
  await page.route("**/api/v1/queries", async route => {
    const body = route.request().postDataJSON(); queries.push(body);
    await route.fulfill({ json: {
      id: `q-${queries.length}`,
      question: body.question,
      status: body.document_ids.length ? "answered" : "clarification_needed",
      reason: body.document_ids.length ? "" : "Choose a document.",
      candidates: docs,
      claims: body.document_ids.length ? [{ text: "Supported answer", citations: [] }] : [],
      evidence: [],
      verification: "grounded_citation_v1",
      model: "test-double",
      retrieval_mode: "hybrid_rerank",
      timings: { retrieval_ms: 1, generation_ms: 1, total_ms: 2 },
      scope: { document_ids: body.document_ids, source: "selection" },
    } });
  });
  await page.goto("/");
  await ask(page, "Tell me about this document.");
  await page.getByRole("group", { name: "Choose a document" }).getByRole("button", { name: "a.pdf" }).click();
  await expect.poll(() => queries.length).toBe(2);
  expect(queries[1].document_ids).toEqual(["a"]);
  expect(queries[1].conversation).toEqual([]);
  await expect(page.getByLabel("Answer")).toContainText("Supported answer");
  await page.getByRole("button", { name: "Show key points" }).click();
  const before = refreshes;
  await expect.poll(() => refreshes, { timeout: 10000 }).toBeGreaterThan(before);
  await expect(page.getByLabel("Document overview")).toContainText("Persistent point");
  await ask(page, "Explain that.");
  expect(queries[2].conversation[0].answer).toBe("Supported answer");
});

test("late summaries cannot overwrite a new document selection", async ({ page }) => {
  test.setTimeout(30000);
  const docs = ["a", "b"].map(id => ({ id, name: `${id}.pdf`, status: "ready", page_count: 1, vector_status: "ready", warnings: [] }));
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route("**/api/v1/documents", route => route.fulfill({ json: docs }));
  await page.route("**/api/v1/history", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/documents/*/summary**", async route => {
    if (route.request().method() === "POST") { started = true; await gate; }
    await route.fulfill({ json: { status: "ready", created_at: 1, content: { summary: route.request().method() === "POST" ? "Stale A summary" : "Current overview", sections: [] } } });
  });
  await page.goto("/");
  await page.getByLabel("Document scope").selectOption("a");
  await page.getByRole("button", { name: "Summarize document" }).click();
  await expect.poll(() => started).toBe(true);
  await page.getByLabel("Document scope").selectOption("b");
  const completed = page.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/summary"));
  release(); await completed;
  await expect(page.getByLabel("Document overview")).toContainText("About b.pdf");
  await expect(page.getByLabel("Document overview")).not.toContainText("Stale A summary");
  await expect(page.getByRole("button", { name: "Summarize document" })).toBeEnabled();
});
