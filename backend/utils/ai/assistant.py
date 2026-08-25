"""
AI Partnership Assistant — single-turn, grounded Q&A.

Not a multi-turn chat with a tool-calling loop (out of scope for this pass —
see plan). Instead: the caller (routers/assistant.py) resolves whatever real
DB rows are relevant to the query (a specific campaign's creators/matches, or
a general roster snapshot) and passes them here as `context`. Gemini is
instructed to answer using ONLY that context and to say so when the context
doesn't contain the answer. Without GEMINI_API_KEY, a deterministic
data-dump fallback is returned instead of prose — still grounded, just not
narrated.
"""

import asyncio
import logging
import os
from typing import Any, Dict

import google.generativeai as genai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type(Exception),
)
def _gemini_generate(prompt: str) -> str:
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


def _deterministic_answer(query: str, context: Dict[str, Any]) -> str:
    lines = [f"(No GEMINI_API_KEY configured — showing raw grounded data for: \"{query}\")"]
    campaigns = context.get("campaigns") or []
    creators = context.get("creators") or []
    if campaigns:
        lines.append("Campaigns:")
        for c in campaigns:
            lines.append(f"  - {c}")
    if creators:
        lines.append("Creators:")
        for c in creators:
            lines.append(f"  - {c}")
    if not campaigns and not creators:
        lines.append("No matching data found in the workspace for this query.")
    return "\n".join(lines)


async def answer_query(*, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Returns {"answer": str, "source": "gemini"|"deterministic_fallback"}."""
    if not GEMINI_API_KEY:
        return {"answer": _deterministic_answer(query, context), "source": "deterministic_fallback"}

    prompt = f"""
You are a creator-partnerships assistant. Answer the user's question using
ONLY the DATA below. If the data doesn't contain the answer, say so plainly
instead of guessing. Never invent follower counts, engagement numbers,
campaign results, or revenue that are not present in DATA.

QUESTION: {query}

DATA (JSON):
{context}

Answer in 2-5 sentences, plain text (no markdown, no JSON).
""".strip()

    try:
        text = await asyncio.to_thread(_gemini_generate, prompt)
        return {"answer": text.strip(), "source": "gemini"}
    except Exception as e:
        logger.warning("Assistant: Gemini failed, using deterministic fallback: %s: %s",
                        type(e).__name__, e)
        return {"answer": _deterministic_answer(query, context), "source": "deterministic_fallback"}
