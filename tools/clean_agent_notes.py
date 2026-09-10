try:
    from ._compat import expose
except ImportError:
    from _compat import expose

expose(__name__, "scripts.maintenance.clean_agent_notes")
