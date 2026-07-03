from typing import Any, AsyncIterator
from hydra.skills.base import BaseHydraSkill
from hydra.research import search_academic_sources, compose_research_answer, citation_for


class ScholarlyRetrievalSkill(BaseHydraSkill):
    @property
    def skill_identifier(self) -> str:
        return "scholarly_retrieval"

    async def execute(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        query = payload.get("query", "")
        yield {"type": "status", "content": f"Searching academic sources for: {query}"}
        sources = await search_academic_sources(query)
        yield {"type": "status", "content": f"Found {len(sources)} sources."}
        yield {
            "type": "result",
            "sources": sources,
            "answer": compose_research_answer(query, sources),
            "citation_template": citation_for(query, sources[0]) if sources else None
        }
