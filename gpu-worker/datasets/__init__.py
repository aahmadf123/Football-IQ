"""Offline dataset adapters for pretraining and evaluation.

Everything in this package is **offline pretraining / evaluation tooling**. None
of it runs inside the same-session or nightly production pipeline, and none of it
is wired into the model router (`pipeline.model_router`). It produces local
artifacts that downstream offline model work consumes; it never serves coaches.
"""
