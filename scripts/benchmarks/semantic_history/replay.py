"""Replay the frozen case(s) against an installed checkout and a disposable local study database."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

from score import fixture


def native_modules(repo):
    if not (repo/"interview_forge/ai/chat/service.py").is_file():
        raise ValueError("Select an Interview Forge checkout with its normal Python dependencies")
    sys.path.insert(0,str(repo.resolve()))
    from interview_forge.ai.chat.service import ChatService
    from interview_forge.ai.tools.builtins.history import RecallChatHistoryArgs, recall_chat_history
    from interview_forge.ai.tools.contracts import ToolExecutionContext
    return ChatService, RecallChatHistoryArgs, recall_chat_history, ToolExecutionContext


def seed(service,db,rows,other_chat):
    sid=service.create_session(user_db=db)["id"]
    other=service.create_session(user_db=db)["id"]
    t0=datetime(2025,11,3,9,tzinfo=timezone.utc)
    with closing(sqlite3.connect(db)) as conn,conn:
        conn.executemany("INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)", (
            (sid,role,text,(t0+timedelta(minutes=i)).isoformat(timespec="seconds")) for i,(role,text) in enumerate(rows)))
        conn.execute("INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                     (other,"user",other_chat,t0.isoformat(timespec="seconds")))
    return sid


async def managed_turn(service,db,sid,question):
    # The checkout supplies the normal model, tool set, request budget and context policy.
    # No feedback or gold label is included in any model or retrieval input.
    service.preflight()
    answer,done,errors=[],{},[]
    start=time.perf_counter()
    async for item in service.stream_reply(user_db=db,session_id=sid,message=question):
        event,data=item["event"],item["data"]
        if event=="message.delta":
            answer.append(data["delta"])
        elif event=="message.done":
            done=data
        elif event in ("error","tool.error"):
            errors.append(data.get("code"))
    wall_ms=round((time.perf_counter()-start)*1000,3)
    if service._background_memory_tasks:
        await asyncio.gather(*list(service._background_memory_tasks),return_exceptions=True)
    if not done:
        raise RuntimeError(f"Chat did not finish, categories {errors}")
    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory=sqlite3.Row
        turns=[dict(x) for x in conn.execute(
            "SELECT round_index,model,status,input_tokens,output_tokens,duration_ms FROM ai_trace_events "
            "WHERE session_id=? AND trace_id=? AND name='model_round' ORDER BY id", (sid,done["message_id"]))]
        tools=[dict(x) for x in conn.execute(
            "SELECT tool_name,arguments_json,status,duration_ms,result_meta_json FROM chat_tool_runs "
            "WHERE session_id=? AND turn_id=? ORDER BY rowid", (sid,done["message_id"]))]
    return {"answer":"".join(answer).strip(),"wall_ms":wall_ms,"tools":tools,"model_rounds":turns,
            "history_sources":done.get("history_sources",[]),"errors":errors}


def main(args):
    fixed=fixture(args.suite)
    service_class,arg_class,search,context_class=native_modules(args.repo)
    selected=([args.case] if args.case else fixed["design"]["run_order"])
    known={c["case"]:c for c in fixed["cases"]}
    if any(key not in known for key in selected):
        raise ValueError("Unknown case")
    with tempfile.TemporaryDirectory(prefix="forge-history-evaluation-") as root:
        for case_id in selected:
            case=known[case_id]
            service=service_class()
            db=Path(root)/(case_id+".sqlite")
            sid=seed(service,db,fixed["corpus"],fixed["other_chat"])
            if args.mode=="agent":
                out=asyncio.run(managed_turn(service,db,sid,case["question"]))
            else:
                ctx=context_class(user_db=db,session_id=sid,turn_id="0"*32,
                                  user_message_id=fixed["design"]["history_rows"]+2,current_query=case["question"])
                probes=([{"mode":"semantic","query":case["query"]}] if args.mode=="semantic"
                        else [{"query":term,"oldest_first":case["kind"]=="earliest"} for term in case["literal_terms"]])
                out=[]
                for probe in probes:
                    start=time.perf_counter()
                    result=search(ctx,arg_class.model_validate(probe))
                    out.append({"args":probe,"data":result.data,"wall_ms":round((time.perf_counter()-start)*1000,3)})
            print(json.dumps({"case":case_id,"mode":args.mode,"result":out},ensure_ascii=True),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("literal","semantic","agent"))
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument("--case",help="Only run one named frozen case")
    parser.add_argument("--suite",choices=("primary","holdout"),default="primary")
    main(parser.parse_args())
