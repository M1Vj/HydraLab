"""HydraLab code fixer (branch 03-05).

Applies approved ``app_code`` category self-evolution diffs specifically, driving
``checkpoint → apply → verify → rollback`` against the 03-01 autonomy shell. It is
a thin specialization over :class:`hydra.self_evolution.service.SelfEvolutionService`
— it never forks a parallel checkpoint/apply/verify implementation, and a
protected-target diff (skill capability field or a protected context file) is
routed to the Review Inbox by the shared risk classifier, never applied.
"""

from __future__ import annotations

from hydra.code_fixer.service import CodeFixerError, CodeFixerService

__all__ = ["CodeFixerError", "CodeFixerService"]
