from copy import deepcopy

import pytest
from omnirag import generation


def row(doc, page, text):
    return {"document_id": doc, "chunk_id": f"{doc}:{page}:0", "page": page, "text": text}


@pytest.fixture
def evidence():
    return [
        row("oak", 1, "Oak Rentals lends tools for 4 days."),
        row("elm", 1, "Elm Rentals lends tools for 11 days."),
        row("oak", 2, "Tools must be returned with the charger."),
    ]


def test_named_subject_retains_document_context_without_mutating_retrieval(evidence):
    original = deepcopy(evidence)
    result = generation.scoped_evidence("What is Oak Rentals return rule?", evidence)
    assert result == [evidence[0], evidence[2]]
    assert evidence == original
    assert result[0] is evidence[0]


@pytest.mark.parametrize(
    "question",
    [
        "What is Elm Rentals loan term?",
        "What is elm rentals loan term?",
        "What is ELM RENTALS loan term?",
    ],
)
def test_name_case_and_missing_source(question, evidence):
    assert generation.scoped_evidence(question, evidence) == [evidence[1]]
    assert generation.scoped_evidence(question, [evidence[0]]) == []


def test_unknown_named_subject_cannot_reuse_other_company(evidence):
    assert generation.scoped_evidence("What is Ash Rentals loan term?", evidence) == []


def test_unnamed_question_preserves_all_source_order(evidence):
    assert generation.scoped_evidence("What must I return with the tool?", evidence) == evidence


@pytest.mark.parametrize(
    "question", ["Was ticket Z-718's fee refunded?", "Was ticket Z-718 refunded?"]
)
def test_record_identifier_possessive_and_word_boundary(question):
    matching = row("record", 1, "Ticket Z-718 was refunded on 2 July 2026.")
    decoy = row("other", 1, "Ticket Z-7180 was refunded on 3 July 2026.")
    assert generation.scoped_evidence(question, [matching, decoy]) == [matching]
    assert generation.scoped_evidence(question, [decoy]) == []


def test_question_openers_and_days_do_not_become_entity_constraints():
    source = row("museum", 1, "Maple Museum opens on Saturdays at 10:00.")
    assert generation.scoped_evidence("What are the Saturday hours at Maple Museum?", [source]) == [
        source
    ]
    assert generation.scoped_evidence("Under what condition is entry allowed?", [source]) == [
        source
    ]


def test_missing_person_cannot_reuse_named_record():
    source = row("record", 1, "Ticket Z-718 was collected by Leah Moss.")
    assert generation.scoped_evidence("Who collected ticket Z-718?", [source]) == [source]
    assert generation.scoped_evidence("Did Noel Reed collect ticket Z-718?", [source]) == []


def test_no_source_short_circuits_network():
    gateway = generation.OllamaGateway(generation.Settings())
    draft, usage = gateway.generate(
        "What happened to ticket Z-719?",
        [row("record", 1, "Ticket Z-718 was collected by Leah Moss.")],
    )
    assert not draft.answerable and usage["model_called"] is False


def test_aliases_and_multi_document_comparisons_are_conservative():
    source = row("oak", 1, "Oak Rentals is open on weekdays.")
    assert generation.scoped_evidence("When is Oak Hire open?", [source]) == []
    other = row("elm", 1, "Elm Rentals is open on weekends.")
    assert (
        generation.scoped_evidence("Compare Oak Rentals with Elm Rentals.", [source, other]) == []
    )


def test_scope_metadata_distinguishes_a_missing_subject_from_quote_length():
    gateway = generation.OllamaGateway(generation.Settings())
    draft, usage = gateway.generate(
        "What happened to ticket Z-719?",
        [row("record", 1, "Ticket Z-718 was collected by Leah Moss.")],
    )
    assert not draft.answerable
    assert usage["subject_scope_withheld"] is True
    assert usage["scope_excluded_chunks"] == 1
    assert usage["selection_attempts"] == 0


def test_interrogative_possessive_does_not_become_a_name_constraint():
    source = row("permit", 1, "Access requires written permission from the director.")
    assert generation.scoped_evidence("Whose permission is needed?", [source]) == [source]


@pytest.mark.parametrize("question", ["Question", "Unknown birthday?", "Did my review pass?"])
def test_sentence_initial_single_word_does_not_imply_a_named_subject(question):
    source = row("review", 1, "Reviews normally take five days.")
    assert generation.scoped_evidence(question, [source]) == [source]
