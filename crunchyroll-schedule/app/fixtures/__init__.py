"""Sample-data fixtures for offline/demo mode.

These are NOT real Crunchyroll data. They exist so the app renders a populated,
working weekly calendar without a token or network access, and to exercise the
full normalization pipeline (CR filtering, sub->raw fallback detection,
last/next, multi-episode drops, delays, null-datetime sentinel).

Field casing is PascalCase, matching the evidence from the er-azh/go-animeschedule
and MolotovCherry/anime-schedule-rs wrappers (Go default JSON unmarshalling
requires the tag to match the wire format), i.e. the live API's most likely
shape. The parser stays casing-tolerant regardless.
"""
