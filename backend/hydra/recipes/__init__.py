"""Built-in bounded recipe descriptors and local recipe runners."""

from hydra.recipes.paper_critique import PAPER_CRITIQUE_RECIPE_ID, paper_critique_recipe
from hydra.recipes.related_work import RELATED_WORK_RECIPE_ID, related_work_recipe

__all__ = [
    "PAPER_CRITIQUE_RECIPE_ID",
    "RELATED_WORK_RECIPE_ID",
    "paper_critique_recipe",
    "related_work_recipe",
]
