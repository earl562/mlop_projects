# Zoning Research Skill

Use this skill when a user asks about zoning, parcel feasibility, allowed uses,
setbacks, density, max units, site constraints, or ordinance-backed
development potential.

## Workflow

1. Resolve the site address and jurisdiction.
2. Retrieve deterministic parcel/property facts through the existing lookup
   pipeline.
3. Search the ordinance index for the relevant zoning district and questions.
4. Extract allowed uses and dimensional standards from cited source material.
5. Run deterministic feasibility calculations where numeric parameters exist.
6. Return structured output with sources, confidence, open questions, and
   evidence metadata when available.

## Guardrails

- Do not guess zoning district, parcel size, ownership, or allowed uses.
- Treat county GIS/OpenData as district evidence, not the ordinance itself.
- Treat Municode/ordinance chunks as legal source material that must be cited.
- Put unsupported or ambiguous findings into `open_questions`.
- Keep `/api/v1/analyze`, `/api/v1/analyze/stream`, and `/api/v1/chat`
  compatibility intact; this skill wraps the current pipeline rather than
  replacing it.
