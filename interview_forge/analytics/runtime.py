"""Internal analytics module accessors for split pure helpers."""
from __future__ import annotations


def compiler():
    from interview_forge.analytics import context_compiler

    return context_compiler


def learning():
    from interview_forge.analytics import learning_analytics

    return learning_analytics

