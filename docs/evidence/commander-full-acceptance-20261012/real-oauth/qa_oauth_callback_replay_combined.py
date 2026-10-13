#!/usr/bin/env python3
"""Legitimate disposable QA OAuth2+PKCE flow using ZITADEL's official APIs.
No bearer, password, code, PAT or raw response is written to stdout.
Run on Storage through the authorized maintenance executor. State is root-only.
"""
import argparse,base64,datetime,hashlib,json,os,pathlib,secrets,ssl,stat,subprocess,sys,urllib.error,urllib.parse,urllib.request

ISSUER="https://auth.haralabs.com.br"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
PRIVATE=pathlib.Path("/srv/hara/identity/qa/commander-full-acceptance-20261012-real-oauth")
STATE=PRIVATE/"state.json"
PROJECT="392794504962310147"
ORG="391782241182744579"
UA="HARA-Commander-Real-QA-OAuth/1"
AUD_SCOPE="urn:zitadel:iam:org:project:id:"+PROJECT+":aud"

class SafeFailure(Exception):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def emit(event,**fields):
    print(json.dumps({"event":event,"at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),**fields},separators=(",",":")),flush=True)

def private_file(path):
    st=path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=0o600:
        raise SafeFailure("PRIVATE_FILE_HYGIENE")

def read_owner():
    path=pathlib.Path("/srv/hara/identity/secrets/identity-owner.pat");private_file(path)
    return path.read_text().strip()

def read_login():
    data=json.loads(subprocess.run(["docker","inspect","hara-identity-zitadel-login-1"],capture_output=True,text=True,timeout=12,check=True).stdout)[0]
    env=dict(x.split("=",1) for x in data.get("Config",{}).get("Env",[]) if "=" in x)
    dest=env.get("ZITADEL_SERVICE_USER_TOKEN_FILE","")
    for m in sorted(data.get("Mounts",[]),key=lambda x:len(x.get("Destination","")),reverse=True):
        d=m.get("Destination","")
        if dest==d or dest.startswith(d.rstrip("/")+"/"):
            path=pathlib.Path(m.get("Source","")+dest[len(d):])
            if not path.is_file():raise SafeFailure("LOGIN_TOKEN_NOT_REGULAR")
            # Existing login runtime file hygiene is preserved; no ACL change.
            return path.read_text().strip()
    raise SafeFailure("LOGIN_TOKEN_MOUNT_NOT_IDENTIFIED")

def save(s):
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    pst=PRIVATE.stat()
    if pst.st_uid!=0 or stat.S_IMODE(pst.st_mode)!=0o700:raise SafeFailure("PRIVATE_DIRECTORY_HYGIENE")
    temp=PRIVATE/("state."+secrets.token_hex(8)+".tmp")
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as f:json.dump(s,f,separators=(",",":"))
    os.replace(temp,STATE);private_file(STATE)

def load():
    private_file(STATE);return json.loads(STATE.read_text())

def request(url,method="GET",payload=None,token=None,form=None,basic=None,no_redirect=False):
    headers={"Accept":"application/json","User-Agent":UA}
    if token:headers["Authorization"]="Bearer "+token
    if basic:headers["Authorization"]="Basic "+base64.b64encode((basic[0]+":"+basic[1]).encode()).decode()
    body=None
    if payload is not None:body=json.dumps(payload,separators=(",",":")).encode();headers["Content-Type"]="application/json"
    if form is not None:body=urllib.parse.urlencode(form).encode();headers["Content-Type"]="application/x-www-form-urlencoded"
    req=urllib.request.Request(url,data=body,headers=headers,method=method)
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context())) if no_redirect else urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req,timeout=20) as r:status=r.status;raw=r.read();head=r.headers
    except urllib.error.HTTPError as e:
        status=e.code;raw=e.read();head=e.headers
    try:data=json.loads(raw) if raw else {}
    except Exception:data={}
    emit("HTTP",method=method,path=urllib.parse.urlsplit(url).path,http_status=status,safe_error_code=data.get("code") if status>=400 else None)
    return status,data,head

def need(code,ok=(200,201,204)):
    if code not in ok:raise SafeFailure("HTTP_"+str(code))

def require_login(login):
    c,d,h=request(ISSUER+"/auth/v1/permissions/zitadel/me/_search","POST",payload={},token=login);need(c)
    if not all(p in d.get("result",[]) for p in ["session.write","session.link","session.delete"]):raise SafeFailure("LOGIN_CLIENT_PERMISSIONS_MISSING")

def prepare():
    owner=read_owner();login=read_login();require_login(login)
    if STATE.exists():raise SafeFailure("QA_STATE_ALREADY_EXISTS_USE_RESUME_OR_CLEANUP")
    s={"run_id":"hara-commander-real-oauth-"+secrets.token_hex(8),"issuer":ISSUER,"project_id":PROJECT,"organization_id":ORG,"created_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"audited_steps":[]}
    c,discovery,h=request(ISSUER+"/.well-known/openid-configuration");need(c)
    s["endpoints"]={key:discovery[key] for key in ["authorization_endpoint","token_endpoint","userinfo_endpoint","introspection_endpoint","revocation_endpoint"]}
    if any(not url.startswith(ISSUER+"/") for url in s["endpoints"].values()):raise SafeFailure("OIDC_ENDPOINT_ISSUER_MISMATCH")
    save(s)
    redirect=DEV+"/auth/qa-oauth-callback"
    payload={"client_name":"HARA Commander Disposable QA "+s["run_id"],"application_type":"web","redirect_uris":[redirect],"response_types":["code"],"grant_types":["authorization_code"],"token_endpoint_auth_method":"none"}
    c,d,h=request(ISSUER+"/oauth/v2/register","POST",payload=payload);need(c,(200,201))
    if not d.get("client_id") or not d.get("registration_access_token") or not d.get("registration_client_uri"):raise SafeFailure("DCR_CLEANUP_BINDING_MISSING")
    s["client"]=d;s["redirect_uri"]=redirect;save(s)
    emit("DCR_CLIENT_CREATED",client_id=d["client_id"],public_pkce_client=d.get("token_endpoint_auth_method")=="none")
    username="hara-qa-"+secrets.token_hex(8)
    s["password"]="Qa9!"+secrets.token_urlsafe(30);s["username"]=username;save(s)
    payload={"username":username,"organization":{"orgId":ORG},"profile":{"givenName":"HARA","familyName":"Disposable QA","displayName":"HARA Commander Disposable QA","preferredLanguage":"en"},"email":{"email":username+"@qa.invalid","returnCode":{}},"password":{"password":s["password"],"changeRequired":False}}
    c,d,h=request(ISSUER+"/v2/users/human","POST",payload=payload,token=owner);need(c)
    if not d.get("userId"):raise SafeFailure("QA_USER_ID_MISSING")
    s["user_id"]=d["userId"];s["email_code"]=d.get("emailCode");save(s)
    emit("QA_USER_CREATED",subject_id=s["user_id"],no_email_requested=True,global_roles_added=False)
    if not s["email_code"]:raise SafeFailure("RETURNED_EMAIL_CODE_MISSING")
    c,d,h=request(ISSUER+"/v2/users/"+s["user_id"]+"/email/verify","POST",payload={"verificationCode":s["email_code"]},token=owner);need(c)
    s.pop("email_code",None);save(s)
    c,d,h=request(ISSUER+"/v2/sessions","POST",payload={"checks":{"user":{"userId":s["user_id"]},"password":{"password":s["password"]}},"lifetime":"600s"},token=login);need(c)
    if not d.get("sessionId") or not d.get("sessionToken"):raise SafeFailure("QA_SESSION_BINDING_MISSING")
    s["session_id"]=d["sessionId"];s["session_token"]=d["sessionToken"];save(s)
    c,d,h=request(ISSUER+"/v2/sessions/"+s["session_id"],token=login);need(c)
    factors=d.get("session",{}).get("factors",{})
    if str(factors.get("user",{}).get("id"))!=str(s["user_id"]) or not factors.get("password",{}).get("verifiedAt"):raise SafeFailure("QA_PASSWORD_FACTOR_NOT_VERIFIED")
    s["password_verified_at"]=factors["password"]["verifiedAt"];save(s)
    emit("QA_PASSWORD_SESSION_VERIFIED",subject_id=s["user_id"],password_verified=True,lifetime_seconds=600)
    issue(s,login)

def issue(s,login):
    client=s["client"];verifier=secrets.token_urlsafe(48);challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=");state=secrets.token_urlsafe(24)
    q={"client_id":client["client_id"],"redirect_uri":s["redirect_uri"],"response_type":"code","scope":"openid email profile "+AUD_SCOPE,"code_challenge":challenge,"code_challenge_method":"S256","state":state,"prompt":"login"}
    c,d,h=request(s["endpoints"]["authorization_endpoint"]+"?"+urllib.parse.urlencode(q),no_redirect=True)
    if c not in (302,303):raise SafeFailure("AUTHORIZE_DID_NOT_REDIRECT")
    loc=h.get("Location","");query=urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query);rid=(query.get("authRequest") or query.get("authRequestId") or [""])[0]
    if not rid.startswith("V2_"):raise SafeFailure("OIDC_AUTH_REQUEST_ID_MISSING")
    s["auth_request_id"]=rid;save(s)
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
    s["tokens"]=t;s["token_issued_at_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat();save(s)
    c,u,h=request(s["endpoints"]["userinfo_endpoint"],token=t["access_token"]);need(c)
    if str(u.get("sub"))!=str(s["user_id"]):raise SafeFailure("OAUTH_SUBJECT_MISMATCH")
    icp=pathlib.Path("/srv/hara/identity/secrets/mcp-introspection-client.json");private_file(icp);ic=json.loads(icp.read_text())
    c,it,h=request(s["endpoints"]["introspection_endpoint"],"POST",form={"token":t["access_token"],"token_type_hint":"access_token"},basic=(ic["client_id"],ic["client_secret"]));need(c)
    aud=it.get("aud",[]);aud=[aud] if isinstance(aud,str) else aud
    if not it.get("active") or str(it.get("sub"))!=str(s["user_id"]) or PROJECT not in aud or str(ic["client_id"]) not in aud or str(client["client_id"]) not in aud:raise SafeFailure("OAUTH_INTROSPECTION_BINDING_MISMATCH")
    if it.get("iss")!=ISSUER:raise SafeFailure("OAUTH_INTROSPECTION_ISSUER_MISMATCH")
    proof={"state":"PASS_REAL_OAUTH_PKCE_QA","subject_id":s["user_id"],"client_id":client["client_id"],"issuer":ISSUER,"audiences":aud,"scopes":it.get("scope"),"token_format":"JWT" if t["access_token"].count(".")==2 else "OPAQUE","email_notification_requested":False,"password_factor_verified":True,"global_policy_changed":False,"global_roles_added":False,"credential_values_exposed":False}
    s["public_proof"]=proof;save(s);emit("REAL_OAUTH_PROOF",**proof)

def probe(endpoint):
    s=load()
    if not s.get("tokens",{}).get("access_token"):raise SafeFailure("QA_TOKEN_NOT_PREPARED")
    if not endpoint.startswith(DEV+"/api/"):raise SafeFailure("PROBE_NOT_DEV")
    body={"jsonrpc":"2.0","id":"real-oauth-qa-tools","method":"tools/list","params":{}}
    c,d,h=request(endpoint,"POST",payload=body,token=s["tokens"]["access_token"])
    tool_names=[str(x.get("name")) for x in d.get("result",{}).get("tools",[]) if isinstance(x,dict)]
    result={"schema":"hara.real-oauth.dev-mcp.probe.v1","http_status":c,"subject_id":s["user_id"],"client_id":s["client"]["client_id"],"method":"tools/list","tool_count":len(tool_names),"tool_names":tool_names,"jsonrpc_error_code":d.get("error",{}).get("code") if isinstance(d.get("error"),dict) else None,"safe_error_code":d.get("error_code") or d.get("code"),"credential_values_exposed":False}
    emit("REAL_OAUTH_MCP_PROBE",**result)
    return 0 if c==200 and len(tool_names)>0 else 1

def cleanup():
    if not STATE.exists():emit("CLEANUP",state="NO_QA_STATE");return 0
    s=load();owner=read_owner();okay=True
    if s.get("tokens",{}).get("access_token") and s.get("client",{}).get("client_id"):
        c,d,h=request(s.get("endpoints",{}).get("revocation_endpoint",ISSUER+"/oauth/v2/revoke"),"POST",form={"token":s["tokens"]["access_token"],"token_type_hint":"access_token","client_id":s["client"]["client_id"]})
        okay=okay and c in (200,204)
    if s.get("session_id"):
        c,d,h=request(ISSUER+"/v2/sessions/"+s["session_id"],"DELETE",token=owner);okay=okay and c in (200,204,404)
    if s.get("user_id"):
        c,d,h=request(ISSUER+"/v2/users/"+s["user_id"],"DELETE",token=owner);okay=okay and c in (200,204,404)
    client=s.get("client",{})
    if client.get("registration_client_uri") and client.get("registration_access_token"):
        uri=client["registration_client_uri"]
        if not uri.startswith(ISSUER+"/oauth/v2/register/"):raise SafeFailure("REGISTRATION_CLEANUP_URI_MISMATCH")
        c,d,h=request(uri,"DELETE",token=client["registration_access_token"]);okay=okay and c in (200,204,404)
    if okay:
        STATE.unlink();emit("CLEANUP",state="PASS_QA_RESOURCES_REMOVED",credential_state_file_removed=True)
    else:
        emit("CLEANUP",state="INCOMPLETE_STATE_PRESERVED");return 1
    return 0

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--stage",choices=["prepare","probe","cleanup"],required=True);ap.add_argument("--endpoint",default=DEV+"/api/mcp?profile=simple");a=ap.parse_args()
    os.umask(0o077)
    try:
        if a.stage=="prepare":prepare();return 0
        if a.stage=="probe":return probe(a.endpoint)
        return cleanup()
    except SafeFailure as e:
        emit("SAFE_FAILURE",code=str(e),stage=a.stage,credential_values_exposed=False,private_state_preserved=STATE.exists());return 1
    except Exception as e:
        emit("SAFE_FAILURE",code=type(e).__name__,stage=a.stage,credential_values_exposed=False,private_state_preserved=STATE.exists());return 1


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
