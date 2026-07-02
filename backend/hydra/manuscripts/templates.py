"""Venue/template registry for manuscript exporters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    label: str
    venue_type: str = "generic"
    citation_style: str = "apa"
    description: str = ""


class TemplateRegistry:
    def __init__(self, templates: list[TemplateSpec] | None = None) -> None:
        self._templates: dict[str, TemplateSpec] = {}
        for template in templates or []:
            self.register(template)

    def register(self, template: TemplateSpec) -> None:
        if not template.id.strip():
            raise ValueError("template id is required")
        self._templates[template.id] = template

    def get(self, template_id: str | None) -> TemplateSpec:
        key = template_id or "generic-academic"
        if key in self._templates:
            return self._templates[key]
        return self._templates["generic-academic"]

    def list(self) -> list[TemplateSpec]:
        return [self._templates[key] for key in sorted(self._templates)]

    def ids(self) -> list[str]:
        return [template.id for template in self.list()]


def default_template_registry() -> TemplateRegistry:
    return TemplateRegistry(
        [
            TemplateSpec(
                id="generic-academic",
                label="Generic academic manuscript",
                venue_type="generic",
                citation_style="apa",
                description="Default article-style manuscript template.",
            )
        ]
    )
