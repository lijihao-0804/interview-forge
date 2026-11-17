"""Check the real module projection, migration compatibility and cross-bank isolation."""

import csv
import io
import json
from contextlib import closing
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.runtime import server_runtime as rt
from interview_forge.services import hot200
from interview_forge.services.leetcode import leetcode_sync
from interview_forge.services.study import complete_content, set_mark


def test_hot200_rounds_and_sync_keep_banks_separate(tmp_path):
    db = tmp_path / "learning.db"
    pid, key = 186, hot200.content_key(186)
    with closing(rt.connect(db)) as con:
        con.execute(
            """INSERT INTO content_events(module_id,content_id,action,studied_at,study_date,round_no)
                       VALUES ('hot200-extra',?,'complete','2024-01-02T10:00:00+08:00','2024-01-02',1)""",
            (key,),
        )
        con.execute(
            "INSERT INTO study_events(problem_id,action,studied_at,study_date,round_no) VALUES (1,'complete','2024-01-02','2024-01-02',1)"
        )
        con.commit()
    for lang in ("python", "java"):
        complete_content(hot200.MODULE, key, db, 3, 0.9, language=lang)
    set_mark("content", key, "weak", db)
    hot200.pin(db, pid)
    ts = int(datetime.fromisoformat("2024-01-04T10:01:00+08:00").timestamp())
    payloads = [
        {"user_name": "test", "stat_status_pairs": []},
        {
            "submissions_dump": [
                {
                    "id": 2011,
                    "is_pending": "Not Pending",
                    "title": hot200.catalog()[pid]["title"],
                    "timestamp": str(ts),
                    "status_display": "Accepted",
                    "lang": "python3",
                },
                {
                    "id": 2012,
                    "is_pending": "Not Pending",
                    "title": "两数之和",
                    "timestamp": str(ts),
                    "status_display": "Accepted",
                    "lang": "python3",
                },
            ]
        },
    ]
    for added in (1, 0):
        with patch.dict(
            rt._values,
            {
                "_fetch_json_with_retry": Mock(side_effect=payloads),
                "get_fsrs_desired_retention": lambda: 0.9,
            },
        ):
            sync = leetcode_sync(
                {"leetcode_session": "test"}, db, module="hot200-extra"
            )
        assert sync["submissions_added"] == added
    detail = hot200.progress(db, pid)
    assert (
        detail["rounds"] == 3 and detail["ac_submits"] == 1 and detail["mark"] == "weak"
    )
    assert {k: v["rounds"] for k, v in detail["by_language"].items()} == {
        "unknown": 1,
        "python": 2,
        "java": 1,
    }
    assert {r["action"] for r in detail["history"]} == {"ac", "complete"}
    boot = hot200.snapshot(db)
    assert (
        boot["pinnedTomorrow"] == {"186": True}
        and boot["dashboard"]["summary"]["completed_problems"] == 1
    )
    assert {
        item["id"]
        for item in hot200.mock(db, {"scope": "unseen", "count": 20})["problems"]
    } <= set(hot200.catalog()) - {pid}
    assert pid in [item["id"] for item in hot200.plan(db, False)["items"]]
    exported = json.loads(hot200.export(db, "records")[0])
    assert len(exported["submissions"]) == 1 and all(
        r["module_id"] == hot200.MODULE for r in exported["content_events"]
    )
    anki = list(csv.reader(io.StringIO(hot200.export(db, "anki")[0].lstrip("\ufeff"))))
    assert len(anki) == 101 and all(
        row[2] and row[3] and row[4].startswith("/library/hot200-extra/")
        for row in anki[1:]
    )
    with closing(rt.connect(db)) as con:
        assert con.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM study_events").fetchone()[0] == 1


def test_hot200_api_requires_auth_and_returns_account_state(tmp_path):
    db = tmp_path / "learning.db"
    with (
        TestClient(app) as client,
        patch("interview_forge.api.support.current_user", return_value=None),
    ):
        assert client.get("/api/hot200-extra/bootstrap").status_code == 401
    user = {"id": 8, "username": "example", "role": "user"}
    with (
        TestClient(app) as client,
        patch("interview_forge.api.support.current_user", return_value=user),
        patch("interview_forge.api.routers.study.user_db", return_value=db),
    ):
        for path in (
            "bootstrap",
            "plan",
            "mock?count=2",
            "problem/186/progress",
            "export?kind=weekly",
        ):
            response = client.get("/api/hot200-extra/" + path)
            assert response.status_code == 200, response.text
        assert client.get("/api/hot200-extra/problem/1/progress").status_code == 400
        assert (
            client.post(
                "/api/hot200-extra/plan/pin", json={"problem_id": 1}
            ).status_code
            == 400
        )
