# Offline related-work excerpts

The existing **Related Work** recipe now prepares a reviewable collection of saved quotations instead of a generic sentence listing paper titles. It runs locally, including when offline-only mode is on and provider consent is off. It does not call an LLM, search the web, download a source or synthesize a research conclusion.

## Use the existing workflow

1. Save sources, citations and quotation evidence with locators in the current project.
2. Run **Related Work** in the Agent Runs panel. The recipe's `source_scope` accepts a list of saved source IDs. An empty list uses the current project's library.
3. Send the result to the writing panel and review the inline suggestion. The existing accept/reject step still controls manuscript insertion.

The existing API also supports the recipe:

```json
{
  "project_id": "default",
  "recipe_id": "related-work",
  "recipe_inputs": {
    "draft_or_source": {"text": "My working draft"},
    "target_venue_style": "",
    "source_scope": ["saved-source-id"]
  }
}
```

Post this to `/api/orchestrator/runs` on the local HydraLab server. Source IDs in this example are placeholders, not invented bibliography records.

## What the draft contains

- Up to three sources, preserving the recipe's existing source limit, in deterministic title/ID order. For each source, use its newest eligible saved quotation, with evidence ID breaking timestamp ties.
- The original quotation in `evidence_excerpts[].quote`, plus source, citation, evidence and claim IDs, the exact saved locator, and the saved evidence relation and review status.
- A single paragraph envelope containing all selected excerpts, so the existing writing-panel handoff carries every selected source and its trace links. The text explicitly labels the output as excerpts for review and includes each evidence record's relation/review status.
- Markdown/HTML syntax escaped in the presentation text. Raw quotations remain unchanged in the structured artifact; copied links, images, citation syntax and instructions are not executed. The current lightweight Markdown preview can display escape backslashes or entities literally; this change does not replace that renderer.
- Notices when the scope is malformed, no eligible quotations exist, or more than three sources are available. Narrow the scope to inspect other sources.

Only live, unmerged, non-trashed sources with a live citation explicitly referenced by their evidence record are eligible. Evidence must be a nonblank quotation with a nonempty locator object and a live claim in the same project. Sources, citations and claims are all project-scoped in the same joined SQL snapshot. Revalidation refreshes cached ORM objects so another session's committed edits are not missed. Legacy records with a null project ID remain in the default project only. Malformed scopes never expand the search.

## Interpretation and review boundaries

This is an **extractive preparation tool**, not a synthesis or semantic relevance ranker. The working draft and venue do not drive a model or automatic source relevance selection. Use the explicit source scope to choose papers relevant to your manuscript.

An artifact paragraph marked `supported` means its entire rendered text, raw quotations, evidence state and trace links match eligible saved records at the recipe's validation stage. It does not establish that an original paper is correct, that a manually saved quotation was transcribed accurately, or that a research claim follows from it. Weak or contradictory evidence remains visibly labeled with its stored status; the recipe never promotes a claim or changes an evidence review decision. Requested claims remain researcher-review notes even if the words occur in a quotation.

Validation rejects changed quotations, locators, statuses, missing/trashed records, cross-project references and prose fabricated around real IDs. Re-run the recipe after editing evidence: saved artifacts are snapshots, and the existing writing accept action is not a live revalidation service.

No schema, dependency, provider-consent setting, agent mode, manuscript approval gate or other recipe is changed. Provider-capable recipes retain their existing offline and consent checks. The local run still records stages/artifacts and honors the existing run budget.
