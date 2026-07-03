
## Picking the right models for workflows and subagents

Rankings, higher = better. Cost reflects what I actually pay, not list price. Intelligence is how hard a problem you can hand the model unsupervised. Taste covers UI/UX, code quality, API design, and copy.

| model    | cost | intelligence | taste |
| -------- | ---- | ------------ | ----- |
| gpt-5.5  | 9    | 8            | 5     |
| sonnet-5 | 5    | 5            | 7     |
| opus-4.8 | 4    | 7            | 8     |
| fable-5  | 2    | 9            | 9     |

How to apply:

* These are defaults, not limits. You have standing permission to override them: if a cheaper model's output doesn't meet the bar, rerun or redo the work with a smarter model without asking. Judge the output, not the price tag. Escalating costs less than shipping mediocre work.
* Cost is a tie-breaker only; when axes conflict for anything that ships, intelligence > taste > cost.
* Bulk/mechanical work such as clear-spec implementation, data analysis, and migrations: use `gpt-5.5`.
* Anything user-facing, including UI, copy, and API design, needs taste ≥ 7.
* Reviews of plans or implementations: use `fable-5` or `opus-4.8`, optionally with `gpt-5.5` as an extra independent perspective.
* Never use Haiku.
* Mechanics: `gpt-5.5` is only reachable through the Codex CLI — `codex exec` / `codex review`. Use the `codex-implementation`, `codex-review`, and `codex-computer-use` skills. For work they do not cover, such as investigation or data analysis, run `codex exec -s read-only` directly with a self-contained prompt.
* Claude models such as `sonnet-5`, `opus-4.8`, and `fable-5` run via the Agent/Workflow model parameter.

Using `gpt-5.5` inside workflows and subagents:

The model parameter only takes Claude models, so use a wrapper.

* Spawn a thin Claude wrapper agent with `model: 'sonnet'` and `effort: 'low'`.
* Its prompt should instruct it to:

  1. Write a self-contained Codex prompt.
  2. Run `codex exec` through Bash.
  3. Return the result.
* Use this wrapper when the main agent should orchestrate but not spend expensive reasoning tokens on mechanical work.
* Use wrapper delegation for implementation, verification, UI/UX checks, computer use, broad codebase inspection, and other token-heavy tasks.
* Keep the main agent focused on planning, taste-sensitive decisions, final review, and deciding when to escalate.
* If the delegated result is weak, incomplete, or unsafe, escalate to a stronger model without asking.
