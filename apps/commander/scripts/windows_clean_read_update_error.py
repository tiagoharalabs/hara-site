import importlib.util,json,base64
s=importlib.util.spec_from_file_location("b","/tmp_hara/windows_clean_qga_bridge.py");b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
for name in ("native-phase-update-running.error.private.txt",):
 h=b.call(b.CLONE,{"execute":"guest-file-open","arguments":{"path":b.CLEAN+chr(92)+name,"mode":"rb"}})
 try:r=b.call(b.CLONE,{"execute":"guest-file-read","arguments":{"handle":h,"count":4096}});text=base64.b64decode(r.get("buf-b64","")).decode("utf-8-sig").strip()
 finally:b.call(b.CLONE,{"execute":"guest-file-close","arguments":{"handle":h}})
 print(json.dumps({"phase":"update-running","signed_client_error":text if text.replace("_","").isalnum() and len(text)<160 else "PRIVATE_ERROR_NOT_PUBLIC_IDENTIFIER"}))
