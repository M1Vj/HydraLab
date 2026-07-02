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

__all__ = [
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
