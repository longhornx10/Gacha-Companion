"""Research layer (M6) + change monitoring (M19).

Search abstraction stays pluggable (SearXNG today, Open WebUI passthrough
later). Claims carry explicit claim_type + evidence; source checks record
hash-based changes for review — nothing mutates canonical state silently.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import ChangeRecord, ResearchSource
from game_companion.db.repositories import ResearchRepository
from game_companion.errors import SearchNotConfiguredError, ValidationError
from game_companion.utils import to_iso, utcnow

# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]: ...


class SearXNGProvider:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        response = httpx.get(
            f"{self._base}/search", params={"q": query, "format": "json"}, timeout=20
        )
        response.raise_for_status()
        hits = []
        for entry in response.json().get("results", [])[:limit]:
            hits.append(
                SearchHit(
                    title=entry.get("title", ""),
                    url=entry.get("url", ""),
                    snippet=entry.get("content", "") or "",
                )
            )
        return hits


class NullProvider:
    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        raise SearchNotConfiguredError()


def provider_from_settings(settings) -> SearchProvider:
    if settings.searxng_base_url:
        return SearXNGProvider(settings.searxng_base_url)
    return NullProvider()


def fetch_text(url: str, max_chars: int = 6000) -> str:
    response = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "gacha-companion/0.1 (local research tool)"},
    )
    response.raise_for_status()
    text = response.text
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text))
    return text[:max_chars]


# --------------------------------------------------------------------------- #
# Structured research answer
# --------------------------------------------------------------------------- #

class ResearchAnswer(BaseModel):
    answer: str
    claim_type: str = Field(
        description="one of: official_fact, mechanics, build_recommendation, community_consensus, speculation"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    citations: list[dict] = Field(default_factory=list)  # [{url, quote}]


class ResearchService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.repo = ResearchRepository(session)

    # sources -----------------------------------------------------------------

    def seed_sources(self) -> list[ResearchSource]:
        seeded = []
        for source in self.adapter.source_registry():
            seeded.append(
                self.repo.upsert_source(
                    game_id=self.adapter.game_id,
                    key=source.key,
                    name=source.name,
                    url=source.url,
                    category=source.category,
                    trust=source.trust,
                    notes=source.notes,
                )
            )
        return seeded

    def source_by_key(self, key: str | None) -> ResearchSource | None:
        if not key:
            return None
        return self.repo.find_by_key(self.adapter.game_id, key)

    # claims ------------------------------------------------------------------

    def add_claim(
        self, *, subject: str, claim_type: str, content: str,
        source_key: str | None, confidence: float | None, evidence: Sequence[dict],
    ):
        from game_companion.db.models.research import CLAIM_TYPES

        if claim_type not in CLAIM_TYPES:
            raise ValidationError(f"claim_type must be one of {CLAIM_TYPES}")
        source = self.source_by_key(source_key)
        return self.repo.add_claim(
            game_id=self.adapter.game_id,
            source_id=source.id if source else None,
            subject=subject,
            claim_type=claim_type,
            content=content,
            confidence=confidence,
            retrieved_at=utcnow(),
            evidence=list(evidence),
        )

    def cross_check(self, subject: str) -> dict:
        """Group claims by type; flag when sources disagree instead of inventing consensus."""
        claims = self.repo.claims(self.adapter.game_id, subject=subject)
        by_type: dict[str, list[dict]] = {}
        for claim in claims:
            src = self.session.get(ResearchSource, claim.source_id) if claim.source_id else None
            by_type.setdefault(claim.claim_type, []).append({
                "content": claim.content,
                "source": src.name if src else None,
                "source_id": claim.source_id,
                "trust": src.trust if src else None,
                "retrieved_at": to_iso(claim.retrieved_at),
                "confidence": claim.confidence,
            })
        disagreements = []
        for claim_type, entries in by_type.items():
            contents = {e["content"].strip().lower() for e in entries}
            if len(contents) > 1:
                disagreements.append({
                    "claim_type": claim_type,
                    "detail": "sources differ — no consensus claimed",
                    "entries": entries,
                })
        return {
            "subject": subject,
            "claims_by_type": by_type,
            "disagreements": disagreements,
            "note": (
                "Claims are typed (official fact / mechanics / build recommendation / "
                "consensus / speculation) and carry evidence. Patch-sensitive advice "
                "should prefer official_fact and recent retrievals."
            ),
        }

    # research query (search + fetch + LLM, all fail loud) ----------------------

    def query(
        self, *, question: str, subject: str | None, provider: SearchProvider, llm
    ) -> dict:
        if not getattr(llm, "configured", False):
            from game_companion.errors import LLMNotConfiguredError

            raise LLMNotConfiguredError()
        hits = provider.search(f"{self.adapter.display_name} {question}", limit=4)
        if not hits:
            raise SearchNotConfiguredError("search provider returned no results")
        fetched: list[dict] = []
        for hit in hits[:3]:
            try:
                fetched.append({"url": hit.url, "title": hit.title, "text": fetch_text(hit.url)})
            except httpx.HTTPError:
                fetched.append({"url": hit.url, "title": hit.title, "text": ""})
        context = json.dumps(
            [
                {"url": f["url"], "title": f["title"], "extract": f["text"][:3000]}
                for f in fetched
            ],
            ensure_ascii=False,
        )
        instruction = (
            f"Question about {self.adapter.display_name}: {question}\n\n"
            "Fetched page extracts follow. Answer ONLY from these extracts. "
            "Quote the exact sentence(s) you rely on. If the extracts do not answer "
            "the question, set answer to what is known and lower confidence. "
            "Classify claim_type conservatively (speculation if unsure)."
            f"\n\nEXTRACTS:\n{context}"
        )
        answer = llm.extract_structured(ResearchAnswer, instruction, temperature=0.0)
        evidence = [
            {"url": c.get("url"), "quote": c.get("quote"), "retrieved_at": to_iso(utcnow())}
            for c in answer.citations
            if c.get("url")
        ]
        claim = self.add_claim(
            subject=subject or "global",
            claim_type=answer.claim_type,
            content=answer.answer,
            source_key=None,
            confidence=answer.confidence,
            evidence=evidence or [{"url": f["url"], "quote": None, "retrieved_at": to_iso(utcnow())} for f in fetched],
        )
        return {"answer": answer.answer, "claim_type": answer.claim_type, "confidence": answer.confidence, "claim_id": claim.id, "citations": evidence}

    # change monitoring (M19) ---------------------------------------------------

    def check_sources(self, llm=None) -> dict:
        """Hash-based watch of registry sources. Detect -> record -> review."""
        results = []
        for source in self.repo.list_all(game_id=self.adapter.game_id):
            try:
                text = fetch_text(source.url, max_chars=20000)
            except httpx.HTTPError as exc:
                results.append({"source": source.key, "error": f"fetch failed: {type(exc).__name__}"})
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            previous_hash = source.content_hash
            source.last_checked_at = utcnow()
            source.content_hash = digest
            if previous_hash and previous_hash != digest:
                self.repo.add_change(
                    game_id=self.adapter.game_id,
                    entity_type="source_content",
                    entity_key=source.key,
                    detected_at=utcnow(),
                    previous_value={"content_hash": previous_hash},
                    proposed_value={"content_hash": digest},
                    source_id=source.id,
                    evidence=[{"url": source.url}],
                    confidence=0.9,
                )
                results.append({"source": source.key, "changed": True})
            else:
                results.append({"source": source.key, "changed": False})
            self.session.flush()
        return {
            "checked": len(results),
            "results": results,
            "note": "changes become pending change_records for review — nothing auto-applies",
        }

    def decide_change(self, change_id: str, approve: bool) -> dict:
        change = self.session.get(ChangeRecord, change_id)
        if change is None or change.game_id != self.adapter.game_id:
            from game_companion.errors import NotFoundError

            raise NotFoundError("change record not found")
        if change.review_status != "pending":
            from game_companion.errors import ValidationError

            raise ValidationError(f"change already '{change.review_status}'")
        change.review_status = "approved" if approve else "rejected"
        change.reviewed_at = utcnow()
        self.session.flush()
        return {"change_id": change.id, "review_status": change.review_status}
