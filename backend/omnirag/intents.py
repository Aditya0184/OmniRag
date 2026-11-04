"""Question intent classification and document-scope resolution.

Conservative English patterns, evaluated against the Phase 12 fixtures. The intent
only chooses how evidence is gathered (retrieval, widened retrieval or coverage
sampling) and whether a clarification is preferable to guessing a document.
"""

import re

OVERVIEW_PATTERNS = (
    r"what(?:'s| is| are) (?:in|inside) (?:this|that|the) (?:pdf|document|file|doc)\b",
    r"what(?:'s| is) (?:this|that|the) (?:pdf|document|file|doc) about",
    r"what does (?:this|that|the) (?:pdf|document|file|doc) (?:say|contain|cover|describe|include)",
    r"tell me about (?:this|that|the) (?:pdf|document|file|doc)\b",
    r"describe (?:this|that|the) (?:pdf|document|file|doc)\b",
    r"what is this about\b",
    r"document overview\b",
)

SUMMARIZE_PATTERN = re.compile(r"summar|\btl;?dr\b|^summary\b", re.IGNORECASE)
KEY_POINTS_PATTERN = re.compile(
    r"key points|main points|takeaways|highlights|key facts|what are the main", re.IGNORECASE
)
LIST_PATTERN = re.compile(
    r"^(which|what) .*\b(listed|list|options|types|kinds|categories|items)\b"
    r"|^list (all|the|every)\b",
    re.IGNORECASE,
)
DEMONSTRATIVE_PATTERN = re.compile(
    r"\b(?:this|that|the) (?:pdf|document|file|doc)\b|\b(?:it|they|them)\b",
    re.IGNORECASE,
)

# Action requests are not document questions. Deliberately narrow: an imperative
# verb with no question mark. "Summarize this." and overview intents are excluded,
# and a question mark keeps genuine questions such as "Write access for whom?".
ACTION_REQUEST_PATTERN = re.compile(
    r"^(?:transfer|send|give|delete|remove|generate|reveal|execute|run|pay|email|"
    r"move|ignore|export|show me your|tell me your)\b",
    re.IGNORECASE,
)


def is_action_request(question: str) -> bool:
    text = question.strip()
    return bool(ACTION_REQUEST_PATTERN.match(text)) and "?" not in text


def classify_intent(question: str) -> dict:
    text = question.casefold()
    demonstrative = bool(DEMONSTRATIVE_PATTERN.search(text))
    if SUMMARIZE_PATTERN.search(text):
        return {"kind": "summarize", "demonstrative": demonstrative}
    if KEY_POINTS_PATTERN.search(text):
        return {"kind": "key_points", "demonstrative": demonstrative}
    if any(re.search(pattern, text) for pattern in OVERVIEW_PATTERNS):
        return {"kind": "overview", "demonstrative": demonstrative}
    if LIST_PATTERN.search(text):
        return {"kind": "list", "demonstrative": demonstrative}
    return {"kind": "factual", "demonstrative": demonstrative}


OVERVIEW_KINDS = {"overview", "summarize", "key_points"}
