"""Shared code between services/api and services/ingestion.

Kept deliberately tiny: just settings loading for now. This is a modular
monolith (API + ingestion workers sharing a common core), not a package
registry — do not grow this into a dumping ground for cross-cutting utils
unless a second real duplication shows up.
"""
