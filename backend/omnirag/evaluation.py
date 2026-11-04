"""Transparent fixture metrics, not semantic grading or an LLM judge."""

import re
import unicodedata
from itertools import chain


def canonical_text(text):
    """Keep case and punctuation for OCR; normalize Unicode and whitespace only."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def edit_distance(reference, observed):
    previous = list(range(len(observed) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(observed, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual))
            )
        previous = current
    return previous[-1]


def transcription_metrics(reference, observed):
    reference, observed = canonical_text(reference), canonical_text(observed)
    characters = len(reference)
    words = len(reference.split())
    character_edits = edit_distance(reference, observed)
    word_edits = edit_distance(reference.split(), observed.split())
    return {
        "reference_characters": characters,
        "reference_words": words,
        "character_edits": character_edits,
        "word_edits": word_edits,
        "cer": character_edits / characters if characters else None,
        "wer": word_edits / words if words else None,
    }


def contains_phrase(text, phrase):
    """Whole token sequence; 14 must not match 114. This does not detect negation."""
    tokens = re.findall(r"\w+", canonical_text(text).casefold())
    wanted = re.findall(r"\w+", canonical_text(phrase).casefold())
    return bool(wanted) and any(
        tokens[i : i + len(wanted)] == wanted for i in range(len(tokens) - len(wanted) + 1)
    )


ABSTENTION_STATUSES = {
    "insufficient_evidence",  # Legacy Phase 1-11 status.
    "no_relevant_passage",  # Retrieval found nothing usable.
    "unsupported_question",  # Evidence retrieved, but the model found no support.
}


def score_answer(query, response, names, *, error=None):
    claims = response.get("claims", [])
    summary = response.get("summary") or {}
    point_texts = [point.get("text", "") for point in summary.get("key_points", [])]
    summary_text = " ".join([summary.get("summary", ""), *point_texts])
    answered = response.get("status") == "answered" and bool(claims) and not error
    citations = [citation for claim in claims for citation in claim.get("citations", [])]
    cited = {(names.get(c["document_id"], c["document_id"]), c["page"]) for c in citations}
    relevant = {tuple(key) for key in query["relevant"]}
    # The application has checked quotes; an error/withheld answer must never count as abstention.
    abstained = (
        response.get("status") in ABSTENTION_STATUSES and not claims and not error
    )
    expected_status = query.get("expected_status")
    fact_texts = (
        [summary_text] if query.get("kind") == "summary" else [claim["text"] for claim in claims]
    )
    facts = [
        any(
            contains_phrase(text, alternative)
            for text in fact_texts
            for alternative in alternatives
        )
        for alternatives in query["expected_facts"]
    ]
    facts_on_reference_pages = [
        any(
            contains_phrase(claim["text"], alternative)
            and any(
                (names.get(c["document_id"], c["document_id"]), c["page"]) in relevant
                for c in claim.get("citations", [])
            )
            for claim in claims
            for alternative in alternatives
        )
        for alternatives in query["expected_facts"]
    ]
    forbidden_absent = not any(
        contains_phrase(claim["text"], phrase)
        for claim in claims
        for phrase in query.get("forbidden", [])
    )
    page_precision = len(cited & relevant) / len(cited) if cited else None
    page_recall = len(cited & relevant) / len(relevant) if relevant else None
    expected_answer = query["answerable"]
    # Summaries cite the pages their key points came from; requiring every
    # reference page would penalize honest partial citations, so summaries need
    # one reference page cited and may not cite outside their document.
    scope_documents = {key for key, _page in relevant}
    citations_in_scope = all(document in scope_documents for document, _page in cited)
    if expected_status:
        contract = bool(
            response.get("status") == expected_status
            and not claims
            and not error
        )
    elif query.get("kind") == "summary" or query.get("citation") == "loose":
        # Summaries and whole-document overviews legitimately cite several pages.
        # They need the facts, at least one reference page cited, no citations
        # outside their scope, and no forbidden phrase.
        contract = bool(
            answered
            and all(facts)
            and relevant
            and bool(cited & relevant)
            and citations_in_scope
            and forbidden_absent
        )
        if query.get("expect_partial") is not None:
            coverage = (response.get("coverage") or {}).get("complete")
            contract = contract and (coverage is not query.get("expect_partial"))
    else:
        # The claims that state the expected facts must cite reference pages. Whole-
        # answer page precision stays a reported metric: a correct answer that adds
        # another true, cited fact is still correct, while an answer drawn from the
        # wrong page or document still fails here.
        wanted = query["expected_facts"]
        fact_bearing_in_scope = all(
            not any(
                contains_phrase(claim["text"], alternative)
                for alternative in chain.from_iterable(wanted)
            )
            or any(
                (names.get(c["document_id"], c["document_id"]), c["page"]) in relevant
                for c in claim.get("citations", [])
            )
            for claim in claims
        )
        contract = bool(
            answered
            and all(facts_on_reference_pages)
            and fact_bearing_in_scope
            and citations_in_scope
            and forbidden_absent
            if expected_answer
            else abstained
        )
    return {
        "answered": bool(answered),
        "abstained": bool(abstained),
        "expected_facts_match": bool(answered and all(facts)) if expected_answer else None,
        "fact_matches": facts,
        "facts_cite_reference_pages": bool(answered and all(facts_on_reference_pages))
        if expected_answer
        else None,
        "forbidden_absent": forbidden_absent,
        "citation_page_precision": page_precision,
        "citation_page_recall": page_recall,
        "correct_abstention": bool(abstained)
        if not expected_answer and not expected_status
        else None,
        "status_matches_expected": bool(response.get("status") == expected_status)
        if expected_status
        else None,
        "contract_pass": contract,
    }


def summarize_answers(rows):
    """Denominators include every scheduled answer, including operational failures."""
    answerable = [r for r in rows if r["answerable"]]
    unsupported = [r for r in rows if not r["answerable"]]
    scored = [r for r in rows if r.get("metrics") is not None]
    answered = [r for r in scored if r["metrics"].get("answered")]
    precisions = [
        r["metrics"]["citation_page_precision"]
        for r in answered
        if r["metrics"].get("citation_page_precision") is not None
    ]

    def rate(group, field):
        if not group or len(scored) != len(rows):
            return None
        return sum(bool(r.get("metrics", {}).get(field)) for r in group) / len(group)

    return {
        "scheduled": len(rows),
        "scored": len(scored),
        "errors": sum(r.get("error") is not None for r in rows),
        "answerable": len(answerable),
        "unsupported": len(unsupported),
        "answer_fact_match_rate": rate(answerable, "expected_facts_match"),
        "unsupported_abstention_rate": rate(unsupported, "correct_abstention"),
        "contract_pass_rate": rate(rows, "contract_pass"),
        "answered_with_citations": len(precisions),
        "mean_citation_page_precision_when_answered": sum(precisions) / len(precisions)
        if precisions
        else None,
    }
