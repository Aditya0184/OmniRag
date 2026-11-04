import re
from pathlib import Path

from omnirag.db import connection

STOP_WORDS = set(
    "a an the is are was were be to for from of in on and or what which who how "
    "when where why does do did can could would should tell me please about with".split()
)


def keyword_variants(tokens: list[str]) -> list[str]:
    """Literal plural/singular variants; still exact token matching, not stemming.

    FTS5 has no stemmer, so "internships" never matched "internship". Adding the
    bounded singular keeps keyword search honest (no synonyms, no semantics).
    """
    variants = []
    for token in tokens:
        variants.append(token)
        if token.endswith("ies") and len(token) >= 5:
            variants.append(f"{token[:-3]}y")
        elif token.endswith("s") and not token.endswith("ss") and len(token) >= 4:
            variants.append(token[:-1])
    return list(dict.fromkeys(variants))


def query_expression(question: str) -> str:
    tokens = re.findall(r"[^\W_]+", question.lower(), flags=re.UNICODE)
    tokens = list(dict.fromkeys(t for t in tokens if len(t) > 1 and t not in STOP_WORDS))[:24]
    # Never pass user-supplied FTS operators or column expressions through.
    return " OR ".join(f'"{token}"' for token in keyword_variants(tokens))


def retrieve(path: Path, question: str, document_ids: list[str], limit: int) -> list[dict]:
    expression = query_expression(question)
    if not expression:
        return []
    params: list = [expression]
    scope = ""
    if document_ids:
        scope = f" AND d.id IN ({','.join('?' for _ in document_ids)})"
        params.extend(document_ids)
    params.append(limit)
    with connection(path) as con:
        rows = con.execute(
            """SELECT c.id AS chunk_id, c.document_id, c.page, c.text, d.name AS document_name,
            COALESCE(p.method,'native') AS extraction_method,
            bm25(chunks_fts) AS score FROM chunks_fts
            JOIN chunks c ON c.id=chunks_fts.chunk_id
            JOIN documents d ON d.id=c.document_id
            LEFT JOIN page_extractions p ON p.document_id=c.document_id AND p.page=c.page
            WHERE chunks_fts MATCH ? AND d.status='ready'"""
            + scope
            + " ORDER BY score, c.id LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
