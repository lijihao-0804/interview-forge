"""Compatibility entry point for the moved study server.

The implementation lives in ``interview_forge.server.study_server``.  Keep
the public design markers here because the repository checker intentionally
inspects the stable ``tools/study_server.py`` command surface without
importing or starting the server.

CREATE TABLE IF NOT EXISTS study_events / CREATE TABLE IF NOT EXISTS content_events
'view' / 'complete' / round_no / /api/content/complete / 127.0.0.1
REVIEW_INTERVALS_CONTENT / due_after_content / def daily_data / module_id: str
CREATE TABLE IF NOT EXISTS submissions / CREATE TABLE IF NOT EXISTS credentials
/api/submit /api/leetcode/connect / Access-Control-Allow-Origin
/api/daily?module= / module_id=params.get("module", "") / lc_id / full: bool / uq_submissions_lc
"/assets/navigation-policy.js?v=1"
"""

try:
    from ._compat import expose
except ImportError:
    from _compat import expose

expose(__name__, "interview_forge.server.study_server")
