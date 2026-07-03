## Summary

<!-- What does this PR do, and why? -->

## Linked issue

<!-- e.g. Closes #123. Write "None" if there is no related issue. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] Tests / CI
- [ ] Other (describe below)

## Testing done

<!-- Check each gate you ran locally. All four must be green before review. -->

- [ ] `uv run --project backend pytest backend/tests -q`
- [ ] `bun test apps/web/src`
- [ ] `bun run typecheck`
- [ ] `bun run build`

<!-- Note any manual testing performed (e.g. ran `bun run dev` and verified the flow in the browser). -->

## Checklist

- [ ] PR title follows Conventional Commits (e.g. `feat(scope): description`)
- [ ] Branched off `develop` (no squash merge)
- [ ] `ATTRIBUTION.md` updated if dependencies were added or changed, and the license gate passes (no AGPL/GPL in bundled deps)
- [ ] Docs updated where behavior changed
- [ ] All gates above are green
- [ ] Preserves privacy and honesty invariants: no fabricated citations, no data leaves the machine without explicit user action, secrets only via the OS keychain
