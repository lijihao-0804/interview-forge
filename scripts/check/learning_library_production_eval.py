"""Check the deployed bookshelf workflow with an explicitly supplied test account."""
import argparse
import json
import re
from pathlib import Path
from uuid import uuid4

import httpx

from scripts.check.learning_agent_live_eval import chat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-file", required=True, type=Path)
    args = parser.parse_args()
    account = json.loads(args.account_file.read_text(encoding="utf-8-sig"))
    with httpx.Client(base_url="https://hot100.xyz", timeout=140) as client:
        client.post("/api/login", json=account).raise_for_status()
        session = client.post("/api/chat/sessions", json={})
        session.raise_for_status()
        base = "/api/chat/sessions/" + session.json()["id"]
        payload = {"message": "请在本站书架用“LRU 双向链表”作为一个查询，找同时涉及这两个概念的三章。",
                   "client_request_id": uuid4().hex}
        first_answer, mid, first = chat(client, base + "/stream", payload)
        sources = first["library_sources"]
        before_rows = client.get(base + "/messages").raise_for_status().json()["items"]
        replay_answer, replay_mid, replay = chat(client, base + "/stream", payload)
        after_rows = client.get(base + "/messages").raise_for_status().json()["items"]
        unclear_answer, _, unclear = chat(client, base + "/stream", {
            "message": "我看到正文和资料卡各有一份书目，顺序不同。我想看第2篇，但记不清指的是哪份。",
            "client_request_id": uuid4().hex,
        })
        second_answer, _, second = chat(client, base + "/stream", {
            "message": "请回读刚才“本轮检索资料”卡片第 2 项，写出这篇的完整标题，并说明当前索引片段涉及的内容。",
            "client_request_id": uuid4().hex,
        })
        rows = client.get(base + "/messages").raise_for_status().json()["items"]
        missing_answer, _, missing = chat(client, base + "/stream", {
            "message": "请打开上一张本轮检索资料卡第 57 项，告诉我它的章节标题。",
            "client_request_id": uuid4().hex,
        })
        expected = sources[1] if len(sources) >= 2 else {}
        checks = {
            "compound_lookup": bool(expected and any(s.get("body_match") for s in sources)),
            "replay": bool(mid and mid == replay_mid and first_answer == replay_answer and not replay["tools"]
                           and before_rows == after_rows and sources == replay["library_sources"]),
            "ambiguous_clarified": bool(not unclear["errors"] and not unclear["library_sources"] and
                                        re.search(r"[？?]|确认|指的是|请.{0,12}(说|提供|告诉|选)", unclear_answer)),
            "previous_card_item": bool(expected and len(second["library_sources"]) == 1 and
                                       second["library_sources"][0]["url"] == expected["url"] and
                                       expected["title"] in second_answer and "search_library" in second["tools"]),
            "persisted": bool(expected and rows[-1]["metadata"].get("library_sources") == second["library_sources"]),
            "missing_without_substitute": bool(not missing["errors"] and not missing["library_sources"] and
                                              re.search(r"没有|不存在|只有|仅有|超出|越界|无法|未找到|找不到|只.{0,3}[1一]", missing_answer)),
        }
        print(json.dumps({"checks": checks, "turns": [first, unclear, second, missing],
                          "clarification": unclear_answer, "out_of_bounds": missing_answer}, ensure_ascii=False))
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
