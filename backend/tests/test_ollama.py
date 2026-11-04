import json

import httpx
import pytest
from omnirag.generation import (
    AnswerDraft,
    GenerationError,
    OllamaGateway,
    SourceSelection,
    resolve_selection,
    source_excerpts,
    validate_citations,
)

EVIDENCE = [
    {
        "chunk_id": "doc:2:0",
        "document_id": "doc",
        "document_name": "sample.pdf",
        "page": 2,
        "text": "The acceptance review lasts five business days.",
    }
]


def test_structured_ollama_http_contract(settings):
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert payload["stream"] is False
        assert payload["format"]["type"] == "object"
        assert list(payload["format"]["properties"]) == [
            "evidence_assessment",
            "requires_individual_record",
            "individual_record_present",
            "answerable",
            "source_ids",
        ]
        assert payload["format"]["properties"]["evidence_assessment"]["maxLength"] == 240
        assert payload["options"]["num_ctx"] == 4096
        assert payload["options"]["num_predict"] == settings.max_output_tokens
        assert payload["format"]["properties"]["source_ids"]["items"]["enum"] == ["S1"]
        assert json.loads(payload["messages"][1]["content"])["excerpts"] == [
            {"id": "S1", "source_group": "C1", "text": EVIDENCE[0]["text"]}
        ]
        result = {
            "requires_individual_record": False,
            "individual_record_present": False,
            "evidence_assessment": "The source states the requested duration.",
            "answerable": True,
            "source_ids": ["S1"],
        }
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(result)},
                "prompt_eval_count": 50,
                "eval_count": 20,
            },
        )

    gateway = OllamaGateway(settings, httpx.MockTransport(handler))
    draft, usage = gateway.generate("How long is the review?", EVIDENCE)
    assert validate_citations(draft, EVIDENCE)[0]["citations"][0]["page"] == 2
    assert usage["output_tokens"] == 20
    assert draft.claims[0].text == draft.claims[0].citations[0].quote == EVIDENCE[0]["text"]
    assert usage["selected_source_ids"] == ["S1"]


@pytest.mark.parametrize(
    "kind,code",
    [
        ("404", "MODEL_NOT_FOUND"),
        ("invalid", "MODEL_INVALID_OUTPUT"),
        ("timeout", "MODEL_TIMEOUT"),
        ("truncated", "MODEL_TRUNCATED"),
    ],
)
def test_model_errors(settings, kind, code):
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if kind == "404":
            return httpx.Response(404)
        if kind == "truncated":
            return httpx.Response(200, json={"done_reason": "length"})
        return httpx.Response(200, json={"message": {"content": "not JSON"}})

    gateway = OllamaGateway(settings, httpx.MockTransport(handler))
    with pytest.raises(GenerationError) as error:
        gateway.generate("Question", EVIDENCE)
    assert error.value.code == code


def test_readiness_missing_model(settings):
    gateway = OllamaGateway(
        settings, httpx.MockTransport(lambda r: httpx.Response(200, json={"models": []}))
    )
    assert gateway.ready()["reachable"] is True
    assert gateway.ready()["model_available"] is False


def test_whitespace_is_not_a_source_quote():
    draft = AnswerDraft.model_validate(
        {
            "answerable": True,
            "claims": [
                {
                    "text": "An unsupported assertion",
                    "citations": [{"chunk_id": "doc:2:0", "quote": " " * 20}],
                }
            ],
        }
    )
    with pytest.raises(GenerationError) as error:
        validate_citations(draft, EVIDENCE)
    assert error.value.code == "INVALID_CITATION"


def test_excerpts_preserve_source_and_negation_without_truncating():
    source = {
        **EVIDENCE[0],
        "text": (
            "Dr. Rao does not approve early delivery. "
            + "Long policy " * 30
            + "must not be treated as unconditional. "
            + "Delivery requires written authorization."
        ),
    }
    excerpts = source_excerpts([source])
    assert [row["text"] for row in excerpts.values()] == [
        "Dr. Rao does not approve early delivery.",
        "Delivery requires written authorization.",
    ]
    draft = resolve_selection(
        SourceSelection(
            requires_individual_record=False,
            individual_record_present=False,
            evidence_assessment="Supported by the source.",
            answerable=True,
            source_ids=["S1"],
        ),
        excerpts,
    )
    claims = validate_citations(draft, [source], extractive=True)
    assert "does not" in claims[0]["text"]
    assert claims[0]["citations"][0]["chunk_id"] == source["chunk_id"]


def test_adjacent_excerpts_keep_linked_conditions_in_one_quote():
    text = (
        "The review period lasts twelve days. This review period begins after the deposit clears."
    )
    source = {**EVIDENCE[0], "text": text}
    excerpts = source_excerpts([source])
    assert [row["text"] for row in excerpts.values()] == [text]
    draft = resolve_selection(
        SourceSelection(
            evidence_assessment="The policy supplies the duration and starting condition.",
            requires_individual_record=False,
            individual_record_present=False,
            answerable=True,
            source_ids=["S1"],
        ),
        excerpts,
    )
    claims = validate_citations(draft, [source], extractive=True)
    assert len(claims) == 1
    assert claims[0]["text"] == claims[0]["citations"][0]["quote"] == text


def test_adjacent_excerpts_cannot_bridge_chunks_or_discard_long_conditions():
    first = "Standard delivery takes twelve days."
    condition = "This rule does not apply when " + "special restrictions apply " * 12 + "."
    last = "Express delivery requires written permission."
    sources = [
        {**EVIDENCE[0], "text": f"{first} {condition} {last}"},
        {**EVIDENCE[0], "chunk_id": "doc:3:0", "page": 3, "text": first},
    ]
    excerpts = source_excerpts(sources)
    assert [row["text"] for row in excerpts.values()] == [first, last, first]


@pytest.mark.parametrize("separate_chunks", [True, False])
def test_linked_sentences_keep_chunk_and_quote_limits(separate_chunks):
    first = "The review period lasts twelve days."
    second = "This review period begins after authorization."
    if separate_chunks:
        sources = [
            {**EVIDENCE[0], "text": first},
            {**EVIDENCE[0], "chunk_id": "doc:3:0", "text": second},
        ]
    else:
        first = "The review period " + "includes review " * 11 + "and lasts twelve days."
        assert len(first) <= 240 < len(first + " " + second)
        sources = [{**EVIDENCE[0], "text": first + " " + second}]
    assert [row["text"] for row in source_excerpts(sources).values()] == [first, second]


def test_excerpt_presentation_restores_page_order_without_mutating_retrieval():
    sources = [
        {**EVIDENCE[0], "text": "The later page records acceptance."},
        {
            **EVIDENCE[0],
            "document_id": "other",
            "chunk_id": "other:1:0",
            "page": 1,
            "text": "Another document records a separate policy.",
        },
        {
            **EVIDENCE[0],
            "chunk_id": "doc:1:0",
            "page": 1,
            "text": "The first page states the delivery policy.",
        },
    ]
    before = [dict(row) for row in sources]
    excerpts = source_excerpts(sources)
    assert [row["chunk_id"] for row in excerpts.values()] == [
        "doc:1:0",
        "doc:2:0",
        "other:1:0",
    ]
    assert sources == before


@pytest.mark.parametrize("ids", [["invented"], ["S1", "S1"]])
def test_selection_rejects_unknown_or_duplicate_source(settings, ids):
    gateway = OllamaGateway(
        settings,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "requires_individual_record": False,
                                "individual_record_present": False,
                                "evidence_assessment": "Assessment.",
                                "answerable": True,
                                "source_ids": ids,
                            }
                        )
                    }
                },
            )
        ),
    )
    with pytest.raises(GenerationError) as error:
        gateway.generate("How long?", EVIDENCE)
    assert error.value.code == "INVALID_CITATION"


@pytest.mark.parametrize(
    "result",
    [
        {"answerable": True, "source_ids": ["S1", "S2", "S3"]},
        {"answerable": True, "source_ids": ["S1"], "claims": [{"text": "untrusted rewrite"}]},
        {"answerable": True, "source_ids": [1]},
        {"answerable": True, "claims": []},
        {"answerable": True, "source_ids": []},
        {"answerable": False, "source_ids": ["S1"]},
    ],
)
def test_selection_rejects_extra_claim_text_and_malformed_schema(settings, result):
    gateway = OllamaGateway(
        settings,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "requires_individual_record": False,
                                "individual_record_present": False,
                                "evidence_assessment": "Assessment.",
                                **result,
                            }
                        )
                    }
                },
            )
        ),
    )
    with pytest.raises(GenerationError) as error:
        gateway.generate("How long?", EVIDENCE)
    assert error.value.code == "MODEL_INVALID_OUTPUT"


def test_empty_selection_is_abstention(settings):
    gateway = OllamaGateway(
        settings,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "requires_individual_record": False,
                                "individual_record_present": False,
                                "evidence_assessment": "Missing fact.",
                                "answerable": False,
                                "source_ids": [],
                            }
                        )
                    }
                },
            )
        ),
    )
    draft, usage = gateway.generate("Unknown birthday?", EVIDENCE)
    assert not draft.answerable and draft.claims == [] and usage["model_called"]


def test_no_eligible_excerpts_never_calls_ollama(settings):
    def unexpected(_):
        raise AssertionError("No HTTP call is allowed without eligible excerpts")

    gateway = OllamaGateway(settings, httpx.MockTransport(unexpected))
    draft, usage = gateway.generate("How long?", [{**EVIDENCE[0], "text": "Long policy " * 30}])
    assert not draft.answerable and not usage["model_called"]


@pytest.mark.parametrize("record_present", [False, True])
def test_individual_record_gate_and_assessment_not_returned(settings, record_present):
    def respond(_):
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "requires_individual_record": True,
                            "individual_record_present": record_present,
                            "evidence_assessment": "PRIVATE assessment is not an answer.",
                            "answerable": True,
                            "source_ids": ["S1"],
                        }
                    )
                }
            },
        )

    draft, usage = OllamaGateway(settings, httpx.MockTransport(respond)).generate(
        "Has a particular event happened?", EVIDENCE
    )
    assert draft.answerable == record_present
    assert usage["record_gate_withheld"] == (not record_present)
    assert usage["selected_source_ids"] == (["S1"] if record_present else [])
    assert "PRIVATE" not in json.dumps([draft.model_dump(), usage])
    if record_present:
        assert draft.claims[0].text == EVIDENCE[0]["text"]
    else:
        assert draft.claims == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("requires_individual_record", None),
        ("individual_record_present", None),
        ("evidence_assessment", ""),
        ("evidence_assessment", "x" * 241),
    ],
)
def test_assessment_schema_rejects_invalid_fields(settings, field, value):
    result = {
        "requires_individual_record": False,
        "individual_record_present": False,
        "evidence_assessment": "Supported fact.",
        "answerable": True,
        "source_ids": ["S1"],
        field: value,
    }
    gateway = OllamaGateway(
        settings,
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"message": {"content": json.dumps(result)}})
        ),
    )
    with pytest.raises(GenerationError) as error:
        gateway.generate("Question", EVIDENCE)
    assert error.value.code == "MODEL_INVALID_OUTPUT"


def test_record_gate_does_not_bypass_source_validation():
    result = SourceSelection(
        requires_individual_record=True,
        individual_record_present=False,
        evidence_assessment="No record.",
        answerable=True,
        source_ids=["invented"],
    )
    with pytest.raises(GenerationError) as error:
        resolve_selection(result, source_excerpts(EVIDENCE))
    assert error.value.code == "INVALID_CITATION"


def test_valid_quote_cannot_support_different_extractive_claim():
    draft = AnswerDraft.model_validate(
        {
            "answerable": True,
            "claims": [
                {
                    "text": "The code AX-724 indicates a low battery.",
                    "citations": [{"chunk_id": "doc:2:0", "quote": EVIDENCE[0]["text"]}],
                }
            ],
        }
    )
    # Historical behavior validates provenance only; new extractive path also binds claim text.
    assert validate_citations(draft, EVIDENCE)
    with pytest.raises(GenerationError) as error:
        validate_citations(draft, EVIDENCE, extractive=True)
    assert error.value.code == "INVALID_CITATION"


def test_identical_text_on_different_pages_keeps_selected_provenance():
    sources = [
        EVIDENCE[0],
        {
            **EVIDENCE[0],
            "chunk_id": "another:8:0",
            "document_id": "another",
            "page": 8,
            "extraction_method": "ocr",
        },
    ]
    draft = resolve_selection(
        SourceSelection(
            requires_individual_record=False,
            individual_record_present=False,
            evidence_assessment="Supported by the source.",
            answerable=True,
            source_ids=["S2"],
        ),
        source_excerpts(sources),
    )
    citation = validate_citations(draft, sources, extractive=True)[0]["citations"][0]
    assert citation["document_id"] == "another" and citation["page"] == 8
    assert citation["extraction_method"] == "ocr"
