"""Internal AI facade lookup used by split AI modules.

This is deliberately narrower than the old server bridge: AI implementation
modules may call the AI coach facade for legacy patch points, but never import
the HTTP assembly or resolve its runtime state.
"""
from __future__ import annotations


def facade():
    from interview_forge.ai import ai_coach

    return ai_coach

