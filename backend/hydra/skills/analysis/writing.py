from typing import Any, AsyncIterator
from hydra.skills.base import BaseHydraSkill
from hydra.writing import review_text


class DraftReviewSkill(BaseHydraSkill):
    @property
    def skill_identifier(self) -> str:
        return "draft_review"

    async def execute(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        text = payload.get("text", "")
        yield {"type": "status", "content": "Analyzing draft text for clarity, tone, and claims..."}
        result = review_text(text)
        yield {
            "type": "result",
            "rewrite": result.get("rewrite"),
            "critique": result.get("critique"),
            "unsupported_claims": result.get("unsupported_claims"),
            "categories": result.get("categories")
        }
