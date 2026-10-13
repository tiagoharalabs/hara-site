#!/usr/bin/env python3
"""Normal Streamable HTTP MCP probes with genuine OAuth; secret output is forbidden."""
import http.cookiejar
def save_customer_context(ctx):
    state=load();state["portal"]["mcp_context"]=ctx;save(state)

def issue_customer(s,login):
    client=s["client"];verifier=secrets.token_urlsafe(48);challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=");state=secrets.token_urlsafe(24)
    q={"client_id":client["client_id"],"redirect_uri":s["redirect_uri"],"response_type":"code","scope":"openid email profile "+AUD_SCOPE,"code_challenge":challenge,"code_challenge_method":"S256","state":state,"prompt":"login"}
    c,d,h=request(s["endpoints"]["authorization_endpoint"]+"?"+urllib.parse.urlencode(q),no_redirect=True)
    if c not in (302,303):raise SafeFailure("AUTHORIZE_DID_NOT_REDIRECT")
    loc=h.get("Location","");query=urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query);rid=(query.get("authRequest") or query.get("authRequestId") or [""])[0]
    if not rid.startswith("V2_"):raise SafeFailure("OIDC_AUTH_REQUEST_ID_MISSING")
    s["auth_request_id"]=rid;save_customer_context(s)
    c,d,h=request(ISSUER+"/v2/oidc/auth_requests/"+urllib.parse.quote(rid,safe=""),token=login);need(c)
    auth=d.get("authRequest",{})
    if str(auth.get("clientId"))!=str(client["client_id"]):raise SafeFailure("AUTH_REQUEST_CLIENT_MISMATCH")
    c,d,h=request(ISSUER+"/v2/oidc/auth_requests/"+urllib.parse.quote(rid,safe=""),"POST",payload={"session":{"sessionId":s["session_id"],"sessionToken":s["session_token"]}},token=login);need(c)
    callback=d.get("callbackUrl","");cb=urllib.parse.urlsplit(callback);params=urllib.parse.parse_qs(cb.query)
    if urllib.parse.urlunsplit((cb.scheme,cb.netloc,cb.path,"",""))!=s["redirect_uri"] or (params.get("state") or [""])[0]!=state:raise SafeFailure("OAUTH_CALLBACK_BINDING_MISMATCH")
    code=(params.get("code") or [""])[0]
    if not code:raise SafeFailure("OAUTH_AUTHORIZATION_CODE_MISSING")
    c,t,h=request(s["endpoints"]["token_endpoint"],"POST",form={"grant_type":"authorization_code","client_id":client["client_id"],"redirect_uri":s["redirect_uri"],"code":code,"code_verifier":verifier});need(c)
    if not t.get("access_token"):raise SafeFailure("OAUTH_ACCESS_TOKEN_MISSING")
    s["tokens"]=t;s["token_issued_at_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat();save_customer_context(s)
    c,u,h=request(s["endpoints"]["userinfo_endpoint"],token=t["access_token"]);need(c)
    if str(u.get("sub"))!=str(s["user_id"]):raise SafeFailure("OAUTH_SUBJECT_MISMATCH")
    icp=pathlib.Path("/srv/hara/identity/secrets/mcp-introspection-client.json");private_file(icp);ic=json.loads(icp.read_text())
    c,it,h=request(s["endpoints"]["introspection_endpoint"],"POST",form={"token":t["access_token"],"token_type_hint":"access_token"},basic=(ic["client_id"],ic["client_secret"]));need(c)
    aud=it.get("aud",[]);aud=[aud] if isinstance(aud,str) else aud
    if not it.get("active") or str(it.get("sub"))!=str(s["user_id"]) or PROJECT not in aud or str(ic["client_id"]) not in aud or str(client["client_id"]) not in aud:raise SafeFailure("OAUTH_INTROSPECTION_BINDING_MISMATCH")
    if it.get("iss")!=ISSUER:raise SafeFailure("OAUTH_INTROSPECTION_ISSUER_MISMATCH")
    proof={"state":"PASS_REAL_OAUTH_PKCE_QA","subject_id":s["user_id"],"client_id":client["client_id"],"issuer":ISSUER,"audiences":aud,"scopes":it.get("scope"),"token_format":"JWT" if t["access_token"].count(".")==2 else "OPAQUE","email_notification_requested":False,"password_factor_verified":True,"global_policy_changed":False,"global_roles_added":False,"credential_values_exposed":False}
    s["public_proof"]=proof;save_customer_context(s);emit("REAL_OAUTH_PROOF",**proof)

def issue_qa2():
    s=load();p=s.get("portal",{});login=read_login();require_login(login)
    if not p.get("user_id"):raise SafeFailure("QA2_NOT_CREATED")
    c,d,h=request(ISSUER+"/v2/sessions","POST",payload={"checks":{"user":{"userId":p["user_id"]},"password":{"password":p["password"]}},"lifetime":"600s"},token=login);need(c)
    sid=d.get("sessionId");stok=d.get("sessionToken")
    if not sid or not stok:raise SafeFailure("QA2_SESSION_BINDING_MISSING")
    p["sessions"].append({"session_id":sid,"session_token":stok});save(s)
    c,d,h=request(ISSUER+"/v2/sessions/"+sid,token=login);need(c)
    f=d.get("session",{}).get("factors",{})
    if str(f.get("user",{}).get("id"))!=str(p["user_id"]) or not f.get("password",{}).get("verifiedAt"):raise SafeFailure("QA2_PASSWORD_FACTOR_INVALID")
    ctx={"client":s["client"],"redirect_uri":s["redirect_uri"],"endpoints":s["endpoints"],"user_id":p["user_id"],"session_id":sid,"session_token":stok,"password_verified_at":f["password"]["verifiedAt"]}
    save_customer_context(ctx);issue_customer(ctx,login)

def parse_mcp_response(raw):
    if not raw:return {}
    try:return json.loads(raw)
    except Exception:pass
    found=[]
    for block in raw.decode("utf-8","replace").replace("\r\n","\n").split("\n\n"):
        lines=[line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
        if not lines:continue
        try:found.append(json.loads("\n".join(lines)))
        except Exception:continue
    return found[-1] if found else {}

def mcp_http(ctx,body,headers_extra=None):
    url=DEV+"/api/mcp?profile=simple"
    headers={"Accept":"application/json, text/event-stream","Content-Type":"application/json","User-Agent":UA,"Authorization":"Bearer "+ctx["tokens"]["access_token"]}
    if headers_extra:headers.update(headers_extra)
    req=urllib.request.Request(url,data=json.dumps(body,separators=(",",":")).encode(),method="POST",headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=25,context=ssl.create_default_context()) as r:code=r.status;raw=r.read();h=r.headers
    except urllib.error.HTTPError as e:code=e.code;raw=e.read();h=e.headers
    data=parse_mcp_response(raw)
    emit("MCP_HTTP",http_status=code,method=body.get("method"),request_id=body.get("id"),jsonrpc_error_code=data.get("error",{}).get("code") if isinstance(data.get("error"),dict) else None,credential_values_exposed=False)
    return code,data,h

def mcp_protocol(which):
    s=load();ctx=s if which=="qa1" else s["portal"]["mcp_context"]
    if not ctx.get("tokens",{}).get("access_token"):raise SafeFailure("REAL_QA_TOKEN_MISSING")
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":"qa-init","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"HARA Real OAuth QA","version":"1.0.0"}}});need(c)
    version=d.get("result",{}).get("protocolVersion")
    if not version:raise SafeFailure("MCP_INITIALIZE_RESULT_MISSING")
    headers={"MCP-Protocol-Version":version}
    if h.get("Mcp-Session-Id"):headers["Mcp-Session-Id"]=h.get("Mcp-Session-Id")
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","method":"notifications/initialized","params":{}},headers);need(c,(200,202,204))
    c,d,h=mcp_http(ctx,{"jsonrpc":"2.0","id":"qa-tools","method":"tools/list","params":{}},headers);need(c)
    tools=d.get("result",{}).get("tools",[]);names=[str(t.get("name")) for t in tools if isinstance(t,dict)]
    if not names:raise SafeFailure("MCP_TOOLS_EMPTY")
    proof={"schema":"hara.real-oauth.customer-mcp.protocol.v1","state":"PASS_REAL_OAUTH_CUSTOMER_MCP","qa":which,"subject_id":ctx["user_id"],"client_id":ctx["client"]["client_id"],"endpoint":DEV+"/api/mcp?profile=simple","protocol_version":version,"tool_count":len(names),"tool_names":names,"mcp_session_header_present":"Mcp-Session-Id" in headers,"seeded_d1_identity":which=="qa1","credential_values_exposed":False}
    if which=="qa1":s["mcp_protocol_proof"]=proof
    else:s["portal"]["mcp_protocol_proof"]=proof
    save(s);emit("CUSTOMER_MCP_PROTOCOL_PASS",**proof)

def normal_pairing():
    s=load();p=s.get("portal",{});cf=pathlib.Path(p.get("cookie_file",""))
    private_file(cf)
    jar=http.cookiejar.MozillaCookieJar(str(cf));jar.load(ignore_discard=True,ignore_expires=True)
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req=urllib.request.Request(DEV+"/api/portal/devices/pairing",data=b"{}",method="POST",headers={"Origin":DEV,"Sec-Fetch-Site":"same-origin","User-Agent":UA,"Accept":"application/json","Content-Type":"application/json"})
    try:
        with opener.open(req,timeout=20) as r:c=r.status;d=json.load(r)
    except urllib.error.HTTPError as e:c=e.code;d={}
    emit("PORTAL_PAIRING_HTTP",http_status=c,normal_portal_cookie_used=True,credential_values_exposed=False);need(c,(201,))
    if not d.get("pairing_token") or not d.get("pairing_id"):raise SafeFailure("NORMAL_PAIRING_RESULT_MISSING")
    handoff={"dev_origin":DEV,"pairing_token":d["pairing_token"],"pairing_id":d["pairing_id"],"expires_at_utc":d.get("expires_at_utc"),"tenant_id":"HARA-TENANT-BNRKHV5P7_1SBJSL8FZ_HYYR","subject_id":"HARA-SUBJECT-NECJJGQPSMLXM5NBYEU","idp_subject_id":p["user_id"],"source":"NORMAL_PORTAL_PAIRING_API"}
    target=PRIVATE/"qa2-portal-pairing.json";fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w") as f:json.dump(handoff,f,separators=(",",":"))
    private_file(target);p["pairing"]=d;p["private_pairing_file"]=str(target);save(s)
    emit("NORMAL_PORTAL_PAIRING_CREATED",pairing_id=d["pairing_id"],expires_at_utc=d.get("expires_at_utc"),one_time=d.get("one_time"),private_file_mode="0600",d1_seed_performed=False,credential_values_exposed=False)

def customer_main():
    ap=argparse.ArgumentParser();ap.add_argument("--customer-stage",choices=["qa1-mcp","qa2-issue","qa2-mcp","qa2-pair"],required=True);a=ap.parse_args();os.umask(0o077)
    try:
        if a.customer_stage=="qa1-mcp":mcp_protocol("qa1")
        elif a.customer_stage=="qa2-issue":issue_qa2()
        elif a.customer_stage=="qa2-mcp":mcp_protocol("qa2")
        else:normal_pairing()
        return 0
    except SafeFailure as e:emit("SAFE_FAILURE",code=str(e),stage=a.customer_stage,private_state_preserved=STATE.exists(),credential_values_exposed=False);return 1
    except Exception as e:emit("SAFE_FAILURE",code=type(e).__name__,stage=a.customer_stage,private_state_preserved=STATE.exists(),credential_values_exposed=False);return 1
if __name__=="__main__":sys.exit(customer_main())
