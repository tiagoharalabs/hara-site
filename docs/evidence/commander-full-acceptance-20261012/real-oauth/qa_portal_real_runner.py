#!/usr/bin/env python3
"""Portal QA2 additions; combined with the reviewed OAuth runner as private code input.
The first QA DCR client remains disposable. The portal's real client is never deleted.
"""
import http.cookiejar,io
base_main=main

def portal_user():
    s=load();owner=read_owner()
    if s.get("portal",{}).get("user_id"):raise SafeFailure("PORTAL_QA_ALREADY_CREATED")
    p={"username":"hara-portal-qa-"+secrets.token_hex(8),"password":"Qa9!"+secrets.token_urlsafe(30),"sessions":[]}
    s["portal"]=p;save(s)
    payload={"username":p["username"],"organization":{"orgId":ORG},"profile":{"givenName":"HARA","familyName":"Portal Disposable QA","displayName":"HARA Commander Portal QA","preferredLanguage":"en"},"email":{"email":p["username"]+"@qa.invalid","returnCode":{}},"password":{"password":p["password"],"changeRequired":False}}
    c,d,h=request(ISSUER+"/v2/users/human","POST",payload=payload,token=owner);need(c)
    if not d.get("userId"):raise SafeFailure("PORTAL_QA_USER_ID_MISSING")
    p["user_id"]=d["userId"];p["email_code"]=d.get("emailCode");save(s)
    emit("PORTAL_QA_USER_CREATED",subject_id=p["user_id"],no_email_requested=True,global_roles_added=False,d1_seed_performed=False)
    if not p["email_code"]:raise SafeFailure("PORTAL_EMAIL_RETURN_CODE_MISSING")
    c,d,h=request(ISSUER+"/v2/users/"+p["user_id"]+"/email/verify","POST",payload={"verificationCode":p["email_code"]},token=owner);need(c)
    p.pop("email_code",None);save(s)
    emit("PORTAL_QA_READY_FOR_ALLOWLIST",subject_id=p["user_id"],no_email_requested=True,d1_seed_performed=False)

def portal_request(opener,url,method="GET",payload=None):
    req=urllib.request.Request(url,data=json.dumps(payload,separators=(",",":")).encode() if payload is not None else None,method=method,headers={"Accept":"application/json","User-Agent":UA,"Content-Type":"application/json"})
    try:
        with opener.open(req,timeout=20) as r:status=r.status;raw=r.read();headers=r.headers
    except urllib.error.HTTPError as e:status=e.code;raw=e.read();headers=e.headers
    try:d=json.loads(raw) if raw else {}
    except Exception:d={}
    emit("PORTAL_HTTP",method=method,path=urllib.parse.urlsplit(url).path,http_status=status,safe_error_code=d.get("code") or d.get("error_code") if status>=400 else None)
    return status,d,headers

def portal_login():
    s=load();p=s.get("portal",{})
    if not p.get("user_id"):raise SafeFailure("PORTAL_QA_NOT_PREPARED")
    login=read_login();require_login(login)
    jar=http.cookiejar.MozillaCookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    c,d,h=portal_request(opener,DEV+"/auth/login?return_to=/");need(c,(302,303))
    authorize=h.get("Location","");a=urllib.parse.urlsplit(authorize);q=urllib.parse.parse_qs(a.query)
    if not authorize.startswith(ISSUER+"/oauth/v2/authorize?") or (q.get("redirect_uri") or [""])[0]!=DEV+"/auth/callback" or (q.get("code_challenge_method") or [""])[0]!="S256" or not q.get("nonce") or not q.get("state"):raise SafeFailure("PORTAL_OIDC_PARAMETERS_INVALID")
    portal_state=q["state"][0];p["portal_client_id"]=q.get("client_id",[""])[0]
    if not any(x.name=="hara_commander_oidc_tx" for x in jar):raise SafeFailure("PORTAL_STATE_COOKIE_MISSING")
    c,d,h=portal_request(opener,authorize);need(c,(302,303))
    rid=(urllib.parse.parse_qs(urllib.parse.urlsplit(h.get("Location","")).query).get("authRequest") or [""])[0]
    if not rid.startswith("V2_"):raise SafeFailure("PORTAL_AUTH_REQUEST_ID_MISSING")
    c,d,h=request(ISSUER+"/v2/oidc/auth_requests/"+rid,token=login);need(c)
    if str(d.get("authRequest",{}).get("clientId"))!=p["portal_client_id"]:raise SafeFailure("PORTAL_AUTH_REQUEST_CLIENT_MISMATCH")
    c,d,h=request(ISSUER+"/v2/sessions","POST",payload={"checks":{"user":{"userId":p["user_id"]},"password":{"password":p["password"]}},"lifetime":"600s"},token=login);need(c)
    if not d.get("sessionId") or not d.get("sessionToken"):raise SafeFailure("PORTAL_QA_SESSION_MISSING")
    sid=d["sessionId"];stok=d["sessionToken"];p["sessions"].append({"session_id":sid,"session_token":stok});save(s)
    c,d,h=request(ISSUER+"/v2/sessions/"+sid,token=login);need(c)
    factors=d.get("session",{}).get("factors",{})
    if str(factors.get("user",{}).get("id"))!=str(p["user_id"]) or not factors.get("password",{}).get("verifiedAt"):raise SafeFailure("PORTAL_PASSWORD_FACTOR_INVALID")
    c,d,h=request(ISSUER+"/v2/oidc/auth_requests/"+rid,"POST",payload={"session":{"sessionId":sid,"sessionToken":stok}},token=login);need(c)
    callback=d.get("callbackUrl","");cb=urllib.parse.urlsplit(callback);params=urllib.parse.parse_qs(cb.query)
    if urllib.parse.urlunsplit((cb.scheme,cb.netloc,cb.path,"",""))!=DEV+"/auth/callback" or (params.get("state") or [""])[0]!=portal_state or not params.get("code"):raise SafeFailure("PORTAL_CALLBACK_BINDING_INVALID")
    c,d,h=portal_request(opener,callback);p["portal_callback_http_status"]=c
    p["portal_session_cookie_present"]=any(x.name=="hara_commander_session" and bool(x.value) for x in jar)
    cookie_file=PRIVATE/"portal-cookie.jar"
    jar.save(str(cookie_file),ignore_discard=True,ignore_expires=True);os.chmod(cookie_file,0o600);private_file(cookie_file)
    p["cookie_file"]=str(cookie_file);save(s)
    if c not in (302,303) or not p["portal_session_cookie_present"]:raise SafeFailure("PORTAL_CALLBACK_FAILED")
    emit("PORTAL_NORMAL_CALLBACK_PASS",subject_id=p["user_id"],portal_client_id=p["portal_client_id"],callback_http_status=c,state_cookie_preserved=True,server_pkce_nonce_used=True,portal_session_cookie_present=True,d1_seed_performed=False,credential_values_exposed=False)
    for endpoint in ["/api/portal/session","/api/portal/bootstrap"]:
        c,d,h=portal_request(opener,DEV+endpoint)
        if c==200:
            # Emit only selected identity/plan metadata; never profiles, cookies or tokens.
            p["portal_authenticated_endpoint"]=endpoint
            selected={}
            for k in ["authenticated","tenant_id","subject_id","plan_code","state"]:
                if k in d:selected[k]=d[k]
            for group in ["session","identity","user","account","plan","entitlement","tenant","subject"]:
                if isinstance(d.get(group),dict):
                    selected[group]={k:v for k,v in d[group].items() if k in ["tenant_id","subject_id","plan_code","state","authenticated"]}
            p.setdefault("portal_readback",{})[endpoint]=selected;save(s);emit("PORTAL_AUTHENTICATED_READBACK",endpoint=endpoint,metadata=selected)
        elif endpoint=="/api/portal/session":raise SafeFailure("PORTAL_AUTHENTICATED_SESSION_READ_FAILED")

def portal_cleanup():
    s=load();p=s.get("portal",{});owner=read_owner();okay=True
    if p.get("cookie_file") and pathlib.Path(p["cookie_file"]).exists():
        cf=pathlib.Path(p["cookie_file"]);private_file(cf)
        jar=http.cookiejar.MozillaCookieJar(str(cf));jar.load(ignore_discard=True,ignore_expires=True)
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        c,d,h=portal_request(opener,DEV+"/auth/logout","POST")
        okay=okay and c in (200,302,303,404,405)
        # A non-existent logout endpoint must be reported; QA D1 cleanup is owned separately.
        p["portal_logout_http_status"]=c;save(s)
    for x in p.get("sessions",[]):
        c,d,h=request(ISSUER+"/v2/sessions/"+x["session_id"],"DELETE",token=owner);okay=okay and c in (200,204,404)
    if p.get("user_id"):
        c,d,h=request(ISSUER+"/v2/users/"+p["user_id"],"DELETE",token=owner);okay=okay and c in (200,204,404)
    if okay:
        if p.get("cookie_file"):pathlib.Path(p["cookie_file"]).unlink(missing_ok=True)
        p.clear();p["state"]="REMOVED";save(s)
        emit("PORTAL_QA_IDP_CLEANUP",state="PASS_QA2_REMOVED",private_cookie_file_removed=True,portal_real_client_untouched=True)
    else:emit("PORTAL_QA_IDP_CLEANUP",state="INCOMPLETE_STATE_PRESERVED")
    return 0 if okay else 1

def portal_main():
    ap=argparse.ArgumentParser();ap.add_argument("--portal-stage",choices=["user","login","cleanup"],required=True);a=ap.parse_args();os.umask(0o077)
    try:
        if a.portal_stage=="user":portal_user();return 0
        if a.portal_stage=="login":portal_login();return 0
        return portal_cleanup()
    except SafeFailure as e:emit("SAFE_FAILURE",code=str(e),portal_stage=a.portal_stage,private_state_preserved=STATE.exists(),credential_values_exposed=False);return 1
    except Exception as e:emit("SAFE_FAILURE",code=type(e).__name__,portal_stage=a.portal_stage,private_state_preserved=STATE.exists(),credential_values_exposed=False);return 1
if __name__=="__main__":sys.exit(portal_main())
