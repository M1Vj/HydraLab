"""Built-in Phase-2 recipes composed over the orchestrator stage engine."""

from hydra.recipes.idea_generation import (
    DEFAULT_RUBRIC_CRITERIA,
    DEFAULT_STAGE_TOGGLES,
    IDEA_RECIPE_ID,
    IDEA_SLASH_COMMANDS,
    IdeaPromotionService,
    IdeaRecipeResult,
    IdeaRunInput,
    RubricResult,
    resolve_parallelism,
    resolve_slash_command,
    run_idea_recipe,
    unresolved_evidence_links,
)
from hydra.recipes.paper_critique import PAPER_CRITIQUE_RECIPE_ID, paper_critique_recipe
from hydra.recipes.related_work import RELATED_WORK_RECIPE_ID, related_work_recipe

__all__ = [
    "PAPER_CRITIQUE_RECIPE_ID",
    "RELATED_WORK_RECIPE_ID",
    "paper_critique_recipe",
    "related_work_recipe",
    "DEFAULT_RUBRIC_CRITERIA",
    "DEFAULT_STAGE_TOGGLES",
    "IDEA_RECIPE_ID",
    "IDEA_SLASH_COMMANDS",
    "IdeaPromotionService",
    "IdeaRecipeResult",
    "IdeaRunInput",
    "RubricResult",
    "resolve_parallelism",
    "resolve_slash_command",
    "run_idea_recipe",
    "unresolved_evidence_links",
]
