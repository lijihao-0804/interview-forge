try:
    from ._compat import expose
except ImportError:
    from _compat import expose

expose(__name__, "interview_forge.ai.ai_coach")
