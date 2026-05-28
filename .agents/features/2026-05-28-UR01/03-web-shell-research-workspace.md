# 03 Web Shell Research Workspace

## Feature branch

`feature/ur01-03-web-shell-research-workspace`

## Requirement mapping

Web-first research UI shell.

## Priority

P0

## Assigned to

Senior Lead Developer

## Mission

Build Hydra-native workspace layout for chat, notes, tasks and status without copying T3 Code.

## Full Context

T3 Code may inspire broad layout patterns only. Hydra must own all components and styling.

## Research Findings / Implementation Direction

Use dense research-workspace layout: navigation, chat/note main area, task side panel and status strip.

## Requirements

- Add app shell and route structure.
- Add responsive desktop-first layout with usable mobile fallback.
- Add empty states for chat, notes and tasks.
- Keep accessibility basics: landmarks, keyboard focus, semantic controls.

## Atomic Steps

1. Inspect frontend stack.
2. Build shell with existing design system.
3. Connect shell to placeholder local state.
4. Add visual states and responsive checks.
5. Run lint and UI smoke test.

## Key Files

- Future web app layout and component files

## Verification

- Lint.
- App starts with `npm run dev` or repo equivalent.
- Browser visual check for desktop and mobile widths.

## Git Branching

Branch from `develop` after branch 02 merges.

## Definition of Done

Workspace renders, navigation works, layout is responsive and no upstream UI code is copied.
