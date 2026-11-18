"""Account and language behavior of the ACM links on both published dashboards."""
import json
import mimetypes
import os
import shutil
import subprocess
from contextlib import closing
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.api.routers import practice
from interview_forge.core import default_runtime
from interview_forge.core.problem_catalog import LEETCODE_SLUGS
from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import create_session, create_user, user_db_path
from interview_forge.services import hot200, study

ROOT = Path(__file__).resolve().parents[1]
API = "/api/practice/hot100"


def test_both_dashboards_link_to_their_registered_acm_and_original_problems():
    client = TestClient(app)
    seen = set()
    slugs = {**LEETCODE_SLUGS, **{row["id"]: row["slug"]
             for row in json.loads((ROOT / "data/hot200-extra.json").read_bytes())}}
    for bank, dashboard in (("hot100", "index.html"), ("hot200", "library/hot200-extra/index.html")):
        markup = (ROOT / dashboard).read_text(encoding="utf-8")
        cards = json.JSONDecoder().raw_decode(markup.split("const problems=", 1)[1].lstrip())[0]
        assert len(cards) == 100
        assert f"const acmBank='{bank}'" in markup
        assert 'href="${esc(problem.original)}"' in markup
        assert 'href="/books/ai-exam/acm-playground.html?id=${acmBank}-${problem.id}' in markup
        for card in cards:
            pid = card["id"]
            assert pid not in seen
            seen.add(pid)
            original = urlsplit(card["original"])
            assert original.hostname == "leetcode.cn" and original.path.rstrip("/") == "/problems/" + slugs[pid]
            key = f"{bank}-{pid}"
            registered = client.get(f"{API}/problem/{key}")
            assert registered.status_code == 200 and registered.json()["id"] == key
            assert registered.json()["title"] == card["title"]
            assert (ROOT / registered.json()["solution_url"].lstrip("/")).is_file()
    assert (ROOT / "books/ai-exam/acm-playground.html").is_file()


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(server_runtime, "_values", {})
    monkeypatch.setattr(server_runtime, "_provider", lambda: default_runtime)
    monkeypatch.setattr(default_runtime, "_AUTH_READY", False)
    monkeypatch.setattr(default_runtime, "_LAST_SESSION_PURGE", 0)
    monkeypatch.setattr(default_runtime, "AUTH_DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(default_runtime, "USERS_DIR", tmp_path / "users")
    clients = []
    for username in ("AcmAlpha", "AcmBeta"):
        account = create_user(username, "test-password-123")
        client = TestClient(app)
        client.cookies.set("forge_session", create_session(int(account["id"])))
        clients.append(client)
    yield clients
    for client in clients:
        client.close()


def test_wa_to_ac_is_per_account_and_problem_across_languages(accounts, monkeypatch):
    alice, bob = accounts
    assert TestClient(app).get(f"{API}/status").status_code == 401
    assert alice.get(f"{API}/status").json() == {"statuses": {}, "username": "AcmAlpha"}
    assert bob.get(f"{API}/status").json() == {"statuses": {}, "username": "AcmBeta"}

    # Stub the external sandbox only. Authentication, judging individual cases,
    # writes, status aggregation and private history all use production code.
    for bank, pid in (("hot100", "1"), ("hot200", "186")):
        key = f"{bank}-{pid}"
        samples = alice.get(f"{API}/problem/{key}").json()["samples"]
        expected = {sample["input"]: sample["expected"] for sample in samples}
        def runner(payload):
            assert payload["language"] in ("java", "python")
            output = expected[payload["stdin"]] if payload["code"] == "correct" else "null"
            return 200, {"status": "ok", "stdout": output}
        monkeypatch.setattr(practice, "_call_runner", runner)
        for lang, code, result, cumulative in (
            ("python", "wrong", False, "attempted"),
            ("java", "correct", True, "accepted"),
            ("python", "wrong", False, "accepted"),
        ):
            response = alice.post(f"{API}/submit", json={"id": key, "language": lang, "code": code})
            assert response.status_code == 200 and response.json()["accepted"] is result
            assert alice.get(f"{API}/status").json()["statuses"][pid] == cumulative
            assert bob.get(f"{API}/status").json()["statuses"] == {}
        history_url = f"{API}/history/{key}"
        records = alice.get(history_url).json()["submissions"]
        assert [(r["language"], r["accepted"]) for r in records] == [
            ("python", False), ("java", True), ("python", False),
        ]
        assert bob.get(history_url).json()["submissions"] == []
        assert bob.get(f"{history_url}/{records[1]['id']}").status_code == 404
    assert alice.get(f"{API}/status").json()["statuses"] == {"1": "accepted", "186": "accepted"}


def test_existing_native_receipts_count_ac_days_per_bank_and_language(accounts):
    alice, bob = accounts
    db = user_db_path("AcmAlpha")
    with closing(server_runtime.connect(db)) as conn, conn:
        for key in ("hot100-1", "hot200-186"):
            # Midnight in China splits the first two receipts. Repeating the same
            # day and the latest WA must preserve two rounds, including on upgrade.
            for stamp, accepted in (("2026-11-12 15:59:59", 1), ("2026-11-12 16:00:00", 1),
                                    ("2026-11-13 08:00:00", 1), ("2026-11-13 08:00:01", 0)):
                conn.execute("INSERT INTO acm_submissions(problem_key,language,code,accepted,submitted_at) "
                             "VALUES(?,'java','',?,?)", (key, accepted, stamp))
        # A provider AC on an already practised day adds an attempt, not a round.
        conn.execute("INSERT INTO submissions(problem_id,status,lang,submitted_at) "
                     "VALUES(1,'ac','Java','2026-11-13T08:00:00+08:00')")
    result = alice.get(f"{API}/status?details=1").json()["progress"]
    for key in ("hot100-1", "hot200-186"):
        assert result[key] == {"rounds": 2, "status": "accepted",
                               "by_language": {"java": {"rounds": 2, "status": "accepted"}}}
    for row in (study.problem_progress(1, db), study.dashboard_data(db)["problems"]["1"],
                hot200.progress(db, 186), hot200.snapshot(db)["dashboard"]["problems"]["186"]):
        assert row["rounds"] == row["by_language"]["java"]["rounds"] == 2
        assert "python" not in row["by_language"]
    assert bob.get(f"{API}/status?details=1").json()["progress"] == {}
    with closing(server_runtime.connect(db)) as conn, conn:
        conn.execute("INSERT INTO acm_submissions(problem_key,language,code,accepted,submitted_at) "
                     "VALUES('hot100-1','python','',1,'2026-11-12 16:01:00'),"
                     "('hot200-186','python','',0,'2026-11-12 16:01:00')")
    result = alice.get(f"{API}/status?details=1").json()["progress"]
    assert result["hot100-1"]["rounds"] == result["hot200-186"]["rounds"] == 2
    assert result["hot100-1"]["by_language"]["python"] == {"rounds": 1, "status": "accepted"}
    assert result["hot200-186"]["by_language"]["python"] == {"rounds": 0, "status": "attempted"}


@pytest.mark.skipif(os.getenv("FORGE_ACM_BROWSER_ACCEPTANCE") != "1", reason="optional Chrome and JDK acceptance")
def test_playground_and_dashboard_follow_real_submissions(accounts, monkeypatch, tmp_path):
    """Browser requests use isolated app sessions; the runner accepts only these two trusted programs."""
    from playwright.sync_api import expect, sync_playwright
    import sys

    wrong = "print('null')"
    java = """import java.util.*;
public class Main {
  public static void main(String[] args) {
    String s = new Scanner(System.in).nextLine();
    String[] words = s.substring(1, s.length()-1).split(" ");
    Collections.reverse(Arrays.asList(words));
    System.out.println("\\\"" + String.join(" ", words) + "\\\"");
  }
}"""
    source = tmp_path / "Main.java"
    source.write_text(java, encoding="utf-8")
    subprocess.run([shutil.which("javac"), str(source)], check=True, timeout=20, capture_output=True)
    commands = {("python", wrong): [sys.executable, "-I", "-c", wrong],
                ("java", java): [shutil.which("java"), "-cp", str(tmp_path), "Main"]}

    def trusted_runner(payload):
        result = subprocess.run(commands[payload["language"], payload["code"]], input=payload["stdin"],
                                capture_output=True, text=True, check=True, timeout=15)
        return 200, {"status": "ok", "stdout": result.stdout}

    monkeypatch.setattr(practice, "_call_runner", trusted_runner)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        for account_index, client in enumerate(accounts):
            context = browser.new_context(service_workers="block")
            context.add_init_script("localStorage.setItem('learningContentOpenMode','same-tab')")
            def local(route):
                request = route.request
                url = urlsplit(request.url)
                if url.hostname != "localhost":
                    return route.abort()
                if url.path.startswith("/api/") or url.path.endswith(".html"):
                    # The real HTML route injects the account widget used to authorize submissions.
                    response = client.request(request.method, url.path + ("?" + url.query if url.query else ""),
                                              content=request.post_data_buffer, headers={"content-type": "application/json"})
                    return route.fulfill(status=response.status_code, body=response.content,
                                         content_type=response.headers.get("content-type", "application/json"))
                path = (ROOT / unquote(url.path).lstrip("/")).resolve()
                if path.is_dir():
                    path = path / "index.html"
                if not path.is_relative_to(ROOT) or not path.is_file():
                    return route.fulfill(status=404, body="Not found")
                return route.fulfill(path=path, content_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream")
            context.route("**/*", local)
            page = context.new_page()
            page.set_default_timeout(8000)
            for bank, entry, pid in (("hot100", "/index.html", 1), ("hot200", "/library/hot200-extra/index.html", 186)):
                page.goto("http://localhost" + entry)
                page.locator("#showAll").click()
                cards = page.locator(".practice-links")
                expect(cards).to_have_count(100)
                page.locator("#progressLanguage").select_option("")
                ids = cards.locator('a:has-text("本站 ACM")').evaluate_all("(xs) => xs.map(x => x.href)")
                assert len(set(ids)) == 100 and all(f"id={bank}-" in link for link in ids)
                assert all(link.startswith("https://leetcode.cn/problems/") for link in
                           cards.locator('a:has-text("力扣原题")').evaluate_all("(xs) => xs.map(x => x.href)"))
                badge = page.locator(f'[data-acm-problem="{pid}"]')
                expect(badge).to_have_text("ACM 未提交")
                link = badge.locator("..").get_by_text("本站 ACM")
                page.locator("#progressLanguage").select_option("java")
                link.click()
                playground = page
                expect(playground.locator("#language-select")).to_have_value("java")
                chip = playground.locator("#native-progress")
                expect(chip).to_contain_text("未做")
                if bank == "hot100":
                    continue
                page = context.new_page()
                page.goto("http://localhost" + entry)
                badge = page.locator(f'[data-acm-problem="{pid}"]')
                if account_index == 0:
                    for lang, program, status in (("python", wrong, "已尝试"), ("java", java, "已通过"),
                                                   ("python", wrong, "已尝试")):
                        page.locator("#progressLanguage").select_option(lang)
                        playground.locator("#language-select").select_option(lang)
                        playground.locator("#code-editor").fill(program)
                        with playground.expect_response(lambda r: r.url.endswith(API + "/submit")) as submitted:
                            playground.locator("#judge-all-btn").click()
                        assert submitted.value.ok and submitted.value.json()["accepted"] == (lang == "java")
                        expect(chip).to_contain_text(status)
                        page.evaluate("window.dispatchEvent(new Event('focus'))")
                        expect(badge).to_contain_text(f"ACM {lang.title()} {status}")
            context.close()
        browser.close()
