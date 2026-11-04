import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

for (const sample of [
  {
    fixture: "mixed_policy.pdf",
    pages: 2,
    sourcePage: 2,
    methods: ["native", "ocr"],
    years: "7 years",
    question:
      "How long must signed records be retained under Cedar Archives retention policy?",
    history: "How long must signed records",
    unsupported:
      "What fee does Cedar Archives charge for delivering records?",
  },
  {
    fixture: "mixed_content_policy.pdf",
    pages: 1,
    sourcePage: 1,
    methods: ["ocr"],
    years: "13 years",
    question:
      "For how many years does Willow Records retain signed agreements?",
    history: "For how many years does Willow Records",
    unsupported:
      "What fee does Willow Records charge for storing an agreement?",
  },
]) {
  test(`${sample.fixture}: live OCR answer, source and saved citation`, async ({
    page,
    request,
  }) => {
    test.skip(
      process.env.OMNIRAG_E2E_MODEL !== "1",
      "Requires actual local Ollama.",
    );
    test.setTimeout(360_000);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/");
    const name = `ocr-${randomUUID().slice(0, 8)}.pdf`;
    const buffer = Buffer.concat([
      await readFile(path.resolve("../examples", sample.fixture)),
      Buffer.from(`\n% ${name}\n`),
    ]);
    const pending = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/documents") &&
        r.request().method() === "POST",
    );
    await page
      .getByLabel("Upload PDF")
      .setInputFiles({ name, mimeType: "application/pdf", buffer });
    const uploaded = await pending;
    expect(uploaded.status()).toBe(202);
    const id = (await uploaded.json()).document.id;
    const row = page
      .locator(".document")
      .filter({ has: page.getByRole("button", { name, exact: true }) });
    await expect(row).toContainText(`${sample.pages} pages · indexed`, {
      timeout: 120_000,
    });
    await expect(row).toContainText(
      `OCR transcription on pages [${sample.sourcePage}]`,
    );
    await expect(row).toContainText("Semantic index ready", {
      timeout: 120_000,
    });
    const detail = await (await request.get(`/api/v1/documents/${id}`)).json();
    expect(detail.pages.map((p: { method: string }) => p.method)).toEqual(
      sample.methods,
    );
    if (sample.fixture === "mixed_content_policy.pdf") {
      expect(detail.pages[0].ocr_trigger).toBe("sparse_text_large_image");
      expect(detail.pages[0].native_characters).toBeGreaterThanOrEqual(20);
    }
    await page.getByLabel("Document scope").selectOption(id);
    await page.getByLabel("Search method").selectOption("hybrid_rerank");
    const question = sample.question;
    await page.getByLabel("Ask your workspace").fill(question);
    const answerPending = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/queries") && r.request().method() === "POST",
      { timeout: 180_000 },
    );
    await page
      .getByRole("button", { name: "Ask question", exact: true })
      .click();
    const response = await answerPending;
    expect(response.status(), await response.text()).toBe(200);
    const answer = await response.json();
    expect(answer.status).toBe("answered");
    expect(answer.verification).toBe("grounded_citation_v1");
    for (const claim of answer.claims) {
      expect(claim.citations.length).toBeGreaterThan(0);
    }
    await expect(page.getByLabel("Answer")).toContainText(sample.years);
    const citations = answer.claims.flatMap(
      (c: { citations: unknown[] }) => c.citations,
    );
    expect(
      citations.some(
        (c: { page: number; extraction_method: string; document_id: string }) =>
          c.page === sample.sourcePage &&
          c.extraction_method === "ocr" &&
          c.document_id === id,
      ),
    ).toBe(true);
    await page
      .getByRole("button", {
        name: `${name} · p. ${sample.sourcePage} · OCR`,
        exact: true,
      })
      .first()
      .click();
    const viewer = page.getByLabel("Source viewer");
    await expect(viewer).toContainText(
      "OCR transcription. Recognition may contain errors",
    );
    await expect(viewer.locator("iframe")).toHaveAttribute(
      "src",
      `/api/v1/documents/${id}/file#page=${sample.sourcePage}`,
    );
    expect(
      await (await request.get(`/api/v1/documents/${id}/file`)).body(),
    ).toEqual(buffer);
    await page.screenshot({
      path: `test-results/phase6-${sample.fixture}-citation.png`,
      fullPage: true,
    });
    await page.reload();
    await page.getByRole("button", { name: /Query history/ }).click();
    await page
      .getByRole("button", { name: new RegExp(sample.history) })
      .first()
      .click();
    await page
      .getByRole("button", {
        name: `${name} · p. ${sample.sourcePage} · OCR`,
        exact: true,
      })
      .first()
      .click();
    await expect(page.getByLabel("Source viewer")).toContainText(
      "OCR transcription.",
    );
    const unsupported = await request.post("/api/v1/queries", {
      data: {
        question: sample.unsupported,
        document_ids: [id],
        retrieval_mode: "hybrid_rerank",
      },
      timeout: 180_000,
    });
    expect(unsupported.status(), await unsupported.text()).toBe(200);
    const abstention = await unsupported.json();
    expect(abstention.status).toBe("unsupported_question");
    expect(abstention.claims).toEqual([]);
    expect(errors).toEqual([]);
  });
}
