---
id: draft-outline
name: Draft Outline
version: "1.0.0"
scope: builtin
description: Draft a structured outline suggestion from the researcher's notes and prompt.
enabled_by_default: false
allowed_capabilities:
  - read_context
  - suggest
risk_level: low
requires_approval: false
tags:
  - writing
  - outline
---

# Purpose
Draft a structured outline as a suggestion the researcher can accept or reject.

# When To Use
Use when the researcher asks for an outline or structure for a section.

# Inputs
The active file, current selection, or explicitly attached notes.

# Workflow
Read the provided context and propose a hierarchical outline as a suggestion.

# Outputs
A Markdown outline presented as a suggestion.

# Safety
Never write files directly; outline is a suggestion only.

# References
HydraLab User Requirements Section 20.
