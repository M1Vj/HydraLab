# 03 Web Shell Research Workspace

## Feature branch

`feature/ur01-03-web-shell-research-workspace`

## Requirement mapping

Web-first modular research UI shell.

## Priority

P0

## Assigned to

Senior Lead Developer

## Mission

Build Hydra-native modular workbench interface inspired by OpenPrism, VS Code, and Obsidian.

## Full Context

OpenPrism and VS Code inspire the core workbench layout: activity bar, sidebars, editor tabs, split panes, and bottom panel. T3 Code provides secondary inspiration for lightweight agent-chat. Hydra must own all components and styling.

## Research Findings / Implementation Direction

Use a dynamic, modular workbench layout. Users should be able to open many components side by side (chat, notes, PDFs, LaTeX editor, Kanban).

## Requirements

- Add app shell and route structure supporting a modular workbench.
- Add VS Code-style layout: activity bar, sidebar, splittable editor tabs, bottom panel, status bar.
- Add responsive desktop-first layout with usable mobile fallback.
- Add empty states for chat, notes, sources, and tasks.
- Keep accessibility basics: landmarks, keyboard focus, semantic controls.

## Atomic Steps

1. Inspect frontend stack.
2. Build shell with existing design system (workbench layout).
3. Connect shell to placeholder local state for pane management.
4. Add visual states and responsive checks.
5. Run lint and UI smoke test.

## Key Files

- Future web app layout and pane management files

## Verification

- Lint.
- App starts with `npm run dev` or repo equivalent.
- Browser visual check for split panes and desktop/mobile widths.

## Git Branching

Branch from `develop` after branch 02 merges.

## Definition of Done

Workbench renders, pane splitting works, layout is responsive and no upstream UI code is copied.
