try:
    from ._compat import expose
except ImportError:
    from _compat import expose

expose(__name__, "scripts.data.extract_lang_solutions")
