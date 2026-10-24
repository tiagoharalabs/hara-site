#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
AGENT=ROOT/"apps/commander/public/agent/linux.py"
SOURCE=AGENT.read_text(encoding="utf-8")

def need(ok,code):
    if not ok:
        raise SystemExit(f"COMMANDER_CANONICAL_FUNCTIONS_{code}=FAIL")
    print(f"COMMANDER_CANONICAL_FUNCTIONS_{code}=PASS")

need('tunnel_mode":transport_mode(config)' in SOURCE,"DEVICE_INFO_TRANSPORT_DYNAMIC")
need('SYMLINK_MUTATION_DENIED' in SOURCE,"SYMLINK_MUTATION_GUARD")
need('PATH_VALUE_INVALID' in SOURCE and 'ord(ch)<32' in SOURCE,"PATH_CONTROL_CHARACTER_GUARD")
need('Path(_checked_path_text(cwd)).expanduser().resolve(strict=True)' in SOURCE,"PROCESS_CWD_PATH_GUARD")
need('oversized_line' in SOURCE and 'continuation_safe' in SOURCE,"READ_BYTE_SAFE_CONTINUATION")
need('O_NOFOLLOW' in SOURCE and '_assert_path_matches_preimage' in SOURCE,"NOFOLLOW_AND_REVALIDATION")
need('FILE_PRECONDITION_FAILED' in SOURCE,"SHA_PRECONDITION_GUARD")
need('"has_more":has_more' in SOURCE and '"next_offset"' in SOURCE,"CONTINUATION_METADATA")
need('"transport_mode":str(call.get("_transport")' in SOURCE,"RECEIPT_TRANSPORT_DYNAMIC")
need('operational_authority="HARA_COMMANDER_LOCAL" if local_transport else "HARA_SERVICES"' in SOURCE,"LOCAL_AUTHORITY_DYNAMIC")
need('"CONTRACT":contract' in SOURCE,"FUNCTION_DESCRIBE_CONTRACT")
need('"continuation"' in SOURCE and '"symlink_semantics":"LSTAT_LEAF"' in SOURCE,"FUNCTION_DESCRIBE_SEMANTICS")

ns={"__name__":"hara_agent_canonical_test","__file__":str(AGENT)}
exec(compile(SOURCE,str(AGENT),"exec"),ns)

with tempfile.TemporaryDirectory(prefix="hara-canonical-functions-") as td:
    root=Path(td)
    data=root/"data"
    config_dir=root/"config/hara-commander"
    config_dir.mkdir(parents=True)
    data.mkdir()
    cfg=config_dir/"device.env"
    cfg.write_text(
        "HARA_COMMANDER_URL=https://example.invalid\n"
        "HARA_DEVICE_ID=HARA-CANONICAL-TEST\n"
        "HARA_DEVICE_TOKEN=TEST_TOKEN\n"
        "HARA_DEVICE_ARCH=x86_64\n"
        "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n"
        "HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL\n",
        encoding="utf-8",
    )
    os.chmod(cfg,0o600)

    ns["CONFIG_FILE"]=cfg
    ns["DATA_DIR"]=data
    ns["RECEIPT_DIR"]=data/"receipts"
    ns["PREIMAGE_DIR"]=data/"preimages"
    ns["OPERATIONS_DB_FILE"]=data/"operations.sqlite3"
    ns["CONSOLE_EVENTS_FILE"]=data/"console-events.jsonl"
    ns["SESSION_FILE"]=data/"operator-session.json"
    config=ns["load_config"]()

    # Dynamic transport truth.
    info=ns["device_info"](config)
    need(info["tunnel_mode"]=="LOCAL_TUNNEL","DEVICE_INFO_LOCAL_TUNNEL")
    desc=ns["describe"]("filesystem.read")
    need(desc["CONTRACT"]["continuation"]["output"]=="next_offset","FUNCTION_DESCRIBE_READ_CONTINUATION")
    cat=ns["catalog"]()
    need(cat["registered_function_count"]==13 and all("domain" in row and "risk_class" in row for row in cat["functions"]),"FUNCTION_CATALOG_METADATA")

    # Symlink information is not silently resolved.
    target=root/"target.txt"
    target.write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n",encoding="utf-8")
    link=root/"link.txt"
    link.symlink_to(target.name)
    finfo=ns["filesystem_info"](str(link))
    need(finfo["type"]=="symlink" and finfo["is_symlink"] is True,"FILE_INFO_SYMLINK")
    need(finfo["symlink_target"]==target.name and finfo["resolved_path"]==str(target.resolve()),"FILE_INFO_SYMLINK_TARGET")

    call={"call_id":"canonical-test","request_id":"canonical-test","tool_id":"hara.files.delete","payload":{},"_transport":"LOCAL_MCP"}
    for label,fn in (
        ("DELETE",lambda:ns["filesystem_delete"](call,str(link))),
        ("WRITE",lambda:ns["filesystem_write"](call,str(link),"x","rewrite")),
        ("EDIT",lambda:ns["filesystem_edit"](call,str(link),"alpha","omega",False)),
        ("COPY",lambda:ns["filesystem_copy"](str(link),str(root/"copy.txt"))),
    ):
        try:
            fn()
            raise AssertionError(label+" symlink mutation accepted")
        except ValueError as exc:
            need(str(exc)=="SYMLINK_MUTATION_DENIED","SYMLINK_"+label+"_DENIED")
    need(target.read_text(encoding="utf-8").startswith("alpha"),"SYMLINK_TARGET_UNCHANGED")

    try:
        ns["filesystem_info"](str(root/"bad\nname"))
        raise AssertionError("control-character path accepted")
    except ValueError as exc:
        need(str(exc)=="PATH_VALUE_INVALID","PATH_CONTROL_CHARACTER_DENIED")
    try:
        ns["_read_regular_nofollow"](moved if False else link,2*1024*1024)
        raise AssertionError("nofollow symlink accepted")
    except ValueError as exc:
        need(str(exc)=="SYMLINK_MUTATION_DENIED","NOFOLLOW_SYMLINK_DENIED")

    # Moving a symlink moves the link itself, never its target.
    moved=root/"moved-link.txt"
    move=ns["filesystem_move"](str(link),str(moved))
    need(move["source_type"]=="symlink" and move["symlink_preserved"] is True,"SYMLINK_MOVE_PRESERVED")
    need(moved.is_symlink() and target.is_file(),"SYMLINK_MOVE_TARGET_UNCHANGED")

    race_file=root/"race.txt"
    race_file.write_text("before\n",encoding="utf-8")
    race_preimage=ns["_store_preimage"](race_file,"race-test","hara.files.edit")
    race_file.write_text("after\n",encoding="utf-8")
    try:
        ns["_assert_path_matches_preimage"](race_file,race_preimage)
        raise AssertionError("changed file matched stale preimage")
    except ValueError as exc:
        need(str(exc)=="FILE_PRECONDITION_FAILED","TOCTOU_REVALIDATION_DENY")

    # Optimistic concurrency for write/edit/delete.
    file1=root/"precondition.txt"
    file1.write_text("one\n",encoding="utf-8")
    sha1=hashlib.sha256(file1.read_bytes()).hexdigest()
    good=ns["filesystem_write"](call,str(file1),"two\n","rewrite",sha1)
    need(good["precondition_checked"] is True and good["previous_sha256"]==sha1,"WRITE_SHA_PRECONDITION_PASS")
    sha2=good["sha256"]
    snapshot=file1.read_bytes()
    try:
        ns["filesystem_write"](call,str(file1),"bad\n","rewrite","0"*64)
        raise AssertionError("wrong write SHA accepted")
    except ValueError as exc:
        need(str(exc)=="FILE_PRECONDITION_FAILED","WRITE_SHA_PRECONDITION_DENY")
    need(file1.read_bytes()==snapshot,"WRITE_PRECONDITION_NO_MUTATION")

    edit=ns["filesystem_edit"](call,str(file1),"two","three",False,sha2)
    need(edit["previous_sha256"]==sha2 and edit["sha256"]!=sha2,"EDIT_SHA_PRECONDITION_PASS")
    before_delete=file1.read_bytes()
    try:
        ns["filesystem_delete"](call,str(file1),"f"*64)
        raise AssertionError("wrong delete SHA accepted")
    except ValueError as exc:
        need(str(exc)=="FILE_PRECONDITION_FAILED","DELETE_SHA_PRECONDITION_DENY")
    need(file1.read_bytes()==before_delete,"DELETE_PRECONDITION_NO_MUTATION")
    final_sha=hashlib.sha256(file1.read_bytes()).hexdigest()
    deleted=ns["filesystem_delete"](call,str(file1),final_sha)
    need(deleted["deleted"] is True and deleted["deleted_sha256"]==final_sha,"DELETE_SHA_PRECONDITION_PASS")

    # Read continuation.
    read1=ns["filesystem_read"](str(target),0,2)
    need(read1["line_count"]==2 and read1["has_more"] is True and read1["next_offset"]==2 and read1["eof"] is False,"READ_PAGE1")
    read2=ns["filesystem_read"](str(target),read1["next_offset"],2)
    need(read2["line_count"]==2 and read2["next_offset"]==4,"READ_PAGE2")
    read3=ns["filesystem_read"](str(target),read2["next_offset"],2)
    need(read3["line_count"]==1 and read3["eof"] is True and read3["next_offset"] is None,"READ_EOF")

    huge=root/"huge-line.txt"
    huge.write_text("x"*70000+"\nsmall\n",encoding="utf-8")
    huge_read=ns["filesystem_read"](str(huge),0,10)
    need(huge_read["content_truncated"] is True and huge_read["oversized_line"] is True,"READ_OVERSIZED_LINE_FLAG")
    need(huge_read["continuation_safe"] is False and huge_read["next_offset"] is None,"READ_OVERSIZED_LINE_NO_UNSAFE_SKIP")
    normal=root/"byte-bounded.txt"
    normal.write_text(("a"*20000+"\n")*5,encoding="utf-8")
    bounded=ns["filesystem_read"](str(normal),0,10)
    need(bounded["content_truncated"] is False and bounded["continuation_safe"] is True and bounded["has_more"] is True,"READ_BYTE_BOUNDARY_SAFE")
    need(bounded["line_count"]==3 and bounded["next_offset"]==3,"READ_BYTE_BOUNDARY_NEXT_OFFSET")
    try:
        ns["process_start"]("pwd",str(root/"bad\nwork"),100)
        raise AssertionError("process cwd control chars accepted")
    except ValueError as exc:
        need(str(exc)=="PATH_VALUE_INVALID","PROCESS_CWD_CONTROL_CHARACTER_DENIED")

    # Directory pagination is deterministic.
    listroot=root/"list"; listroot.mkdir()
    for name in ("a.txt","b.txt","c.txt","d.txt","e.txt"):
        (listroot/name).write_text(name,encoding="utf-8")
    page1=ns["filesystem_list"](str(listroot),2,1,0)
    page2=ns["filesystem_list"](str(listroot),2,1,page1["next_offset"])
    page3=ns["filesystem_list"](str(listroot),2,1,page2["next_offset"])
    names=[x["name"] for x in page1["entries"]+page2["entries"]+page3["entries"]]
    need(names==["a.txt","b.txt","c.txt","d.txt","e.txt"],"LIST_PAGINATION_DETERMINISTIC")
    need(page1["has_more"] and page2["has_more"] and not page3["has_more"],"LIST_PAGINATION_FLAGS")

    # Search pagination is deterministic.
    search1=ns["filesystem_search"](str(listroot),"files",".txt",2,False,True,"",0)
    search2=ns["filesystem_search"](str(listroot),"files",".txt",2,False,True,"",search1["next_offset"])
    search3=ns["filesystem_search"](str(listroot),"files",".txt",2,False,True,"",search2["next_offset"])
    found=[x["path"] for x in search1["matches"]+search2["matches"]+search3["matches"]]
    need(found==["a.txt","b.txt","c.txt","d.txt","e.txt"],"SEARCH_PAGINATION_DETERMINISTIC")
    need(search1["has_more"] and search2["has_more"] and not search3["has_more"],"SEARCH_PAGINATION_FLAGS")

    # Process list tells the caller whether it was truncated.
    plist=ns["process_list"](1)
    need(plist["returned_count"]==1 and plist["available_count"]>=1 and isinstance(plist["truncated"],bool),"PROCESS_LIST_BOUNDS_METADATA")

    # Local receipt and result authority are truthful.
    ns["RECEIPT_DIR"].mkdir(parents=True,exist_ok=True)
    ping_call={
        "call_id":"local-ping",
        "request_id":"local-ping",
        "tool_id":"hara.ping",
        "payload":{},
        "_transport":"LOCAL_MCP",
    }
    result=ns["execute_tool"](config,ping_call)
    need(result["operational_authority"]=="HARA_COMMANDER_LOCAL","LOCAL_RESULT_AUTHORITY")
    receipt=ns["read_receipt"](result["bridge_receipt_sha256"])
    need(receipt["transport_mode"]=="LOCAL_MCP" and receipt["operational_authority"]=="HARA_COMMANDER_LOCAL","LOCAL_RECEIPT_AUTHORITY")

print("COMMANDER_CANONICAL_FUNCTIONS_HARDENING=PASS")
