#!/usr/bin/env python3
"""One legitimate QA2 portal login followed by one rejected callback replay.
Uses an independent cookie jar; preserves the original QA2 portal session cookie.
"""
import http.cookiejar
def replay_main():
    s=load();p=s["portal"];login=read_login();require_login(login)
    jar=http.cookiejar.CookieJar();op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    def call_portal(url,cookie=None):
        headers={"Accept":"application/json","User-Agent":UA}
        if cookie is not None:headers["Cookie"]=cookie
        req=urllib.request.Request(url,headers=headers)
        try:
            with op.open(req,timeout=20) as r:c=r.status;raw=r.read();h=r.headers
        except urllib.error.HTTPError as e:c=e.code;raw=e.read();h=e.headers
        try:d=json.loads(raw) if raw else {}
        except Exception:d={}
        emit("REPLAY_HTTP",path=urllib.parse.urlsplit(url).path,http_status=c,safe_code=d.get("code"),credential_values_exposed=False)
        return c,d,h
    c,d,h=call_portal(DEV+"/auth/login?return_to=/");need(c,(302,303))
    authorize=h.get("Location","");q=urllib.parse.parse_qs(urllib.parse.urlsplit(authorize).query)
    if not authorize.startswith(ISSUER+"/oauth/v2/authorize?") or q.get("code_challenge_method")!=["S256"] or not q.get("nonce"):raise SafeFailure("REPLAY_LOGIN_PARAMETERS_INVALID")
    tx=next((x.value for x in jar if x.name=="hara_commander_oidc_tx"),None)
    if not tx:raise SafeFailure("REPLAY_TX_COOKIE_MISSING")
    state=q.get("state",[""])[0];cid=q.get("client_id",[""])[0]
    c,d,h=call_portal(authorize);need(c,(302,303))
    rid=(urllib.parse.parse_qs(urllib.parse.urlsplit(h.get("Location","")).query).get("authRequest") or [""])[0]
    if not rid.startswith("V2_"):raise SafeFailure("REPLAY_AUTH_REQUEST_MISSING")
    c,d,h=request(ISSUER+"/v2/oidc/auth_requests/"+rid,token=login);need(c)
    if d.get("authRequest",{}).get("clientId")!=cid:raise SafeFailure("REPLAY_AUTH_REQUEST_CLIENT_MISMATCH")
    c,d,h=request(ISSUER+"/v2/sessions","POST",payload={"checks":{"user":{"userId":p["user_id"]},"password":{"password":p["password"]}},"lifetime":"600s"},token=login);need(c)
    sid=d.get("sessionId");stok=d.get("sessionToken")
    if not sid or not stok:raise SafeFailure("REPLAY_SESSION_MISSING")
    p["sessions"].append({"session_id":sid,"session_token":stok});save(s)
    c,d,h=request(ISSUER+"/v2/sessions/"+sid,token=login);need(c)
    f=d.get("session",{}).get("factors",{})
    if f.get("user",{}).get("id")!=p["user_id"] or not f.get("password",{}).get("verifiedAt"):raise SafeFailure("REPLAY_PASSWORD_NOT_VERIFIED")
    c,d,h=request(ISSUER+"/v2/oidc/auth_requests/"+rid,"POST",payload={"session":{"sessionId":sid,"sessionToken":stok}},token=login);need(c)
    callback=d.get("callbackUrl","");cb=urllib.parse.urlsplit(callback);params=urllib.parse.parse_qs(cb.query)
    if urllib.parse.urlunsplit((cb.scheme,cb.netloc,cb.path,"",""))!=DEV+"/auth/callback" or params.get("state")!=[state] or not params.get("code"):raise SafeFailure("REPLAY_CALLBACK_BINDING_MISMATCH")
    c,d,h=call_portal(callback);need(c,(302,303))
    if not any(x.name=="hara_commander_session" and x.value for x in jar):raise SafeFailure("REPLAY_FIRST_CALLBACK_NO_SESSION")
    c2,d2,h2=call_portal(callback,cookie="hara_commander_oidc_tx="+tx)
    safe=d2.get("code")
    if safe!="OIDC_STATE_REPLAYED":
        loc=h2.get("Location","");pq=urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)
        candidate=(pq.get("auth_error") or pq.get("error") or [""])[0]
        if candidate=="OIDC_STATE_REPLAYED":safe=candidate
    new_session=any(x.startswith("hara_commander_session=") and not x.startswith("hara_commander_session=;") for x in h2.get_all("Set-Cookie",[]))
    proof={"schema":"hara.real-portal-oauth.callback-replay.v1","state":"PASS_REPLAY_REJECTED" if safe=="OIDC_STATE_REPLAYED" and not new_session else "REPLAY_RESULT_NOT_PROVEN","subject_id":p["user_id"],"initial_callback_http_status":c,"replayed_callback_http_status":c2,"safe_rejection_code":safe,"new_session_cookie_on_replay":new_session,"original_portal_cookie_file_preserved":True,"credential_values_exposed":False}
    s=load();s["portal"]["oauth_callback_replay_proof"]=proof;save(s);emit("OAUTH_CALLBACK_REPLAY_PROOF",**proof)
    # Revoke only the temporary independent portal session; the original stays active.
    req=urllib.request.Request(DEV+"/auth/logout",data=b"",method="POST",headers={"Origin":DEV,"Sec-Fetch-Site":"same-origin","Accept":"application/json","User-Agent":UA})
    try:
        with op.open(req,timeout=20) as r:logout=r.status
    except urllib.error.HTTPError as e:logout=e.code
    emit("TEMPORARY_REPLAY_PORTAL_LOGOUT",http_status=logout,original_cookie_file_untouched=True,credential_values_exposed=False)
    return 0 if proof["state"]=="PASS_REPLAY_REJECTED" else 1
if __name__=="__main__":
    try:sys.exit(replay_main())
    except SafeFailure as e:emit("SAFE_FAILURE",code=str(e),credential_values_exposed=False);sys.exit(1)
    except Exception as e:emit("SAFE_FAILURE",code=type(e).__name__,credential_values_exposed=False);sys.exit(1)
