#!/usr/bin/env python3
"""Fail-closed offline review of Commander plugin submission archive.

Does not submit an app, create demo accounts or contact OpenAI.
"""
from __future__ import annotations
import ast
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/"apps/commander/plugin-submission"
FILES=("plugin.json","mcp.json","assets/logo.png","assets/icon.png")
ZIP=BASE/"hara-commander-capivara-v0.2.0-review.zip"
def require(value,code):
    if not value: raise AssertionError(code)

def valid_https(url):
    x=urlsplit(url)
    return x.scheme=="https" and bool(x.hostname) and not x.username and not x.password and not x.fragment

def main():
    plugin=json.loads((BASE/"plugin.json").read_text())
    mcp=json.loads((BASE/"mcp.json").read_text())
    interface=plugin["extensions"]["com.openai"]["interface"]
    review=plugin["extensions"]["com.openai"]["review"]["test_cases"]
    require(re.fullmatch(r"[a-z0-9][a-z0-9-_]{0,63}",plugin["name"]) is not None,"PACKAGE_NAME")
    require(re.fullmatch(r"\d+\.\d+\.\d+",plugin["version"]) is not None,"PACKAGE_SEMVER")
    require(plugin["version"]=="0.2.0","REVIEW_PACKAGE_VERSION")
    release=plugin["extensions"]["com.openai"].get("publication",{})
    require(isinstance(release.get("release_notes"),str)
            and len(release["release_notes"].strip())>=80,"RELEASE_NOTES_REQUIRED")
    require(0<len(interface["displayName"])<=30,"DISPLAY_NAME")
    require(0<len(interface["shortDescription"])<=30,"SHORT_DESCRIPTION")
    require(0<len(interface["longDescription"])<=4000,"LONG_DESCRIPTION")
    require(0<len(interface["developerName"])<=80,"DEVELOPER_NAME")
    require(len(interface["defaultPrompt"])<=3,"PROMPT_LIMIT")
    for key in ("websiteURL","supportURL","privacyPolicyURL","termsOfServiceURL"):
        require(valid_https(interface[key]),"HTTPS_LISTING_"+key)
    require(len(review["positive"])==5 and len(review["negative"])==3,"REVIEW_TEST_COUNT")
    source=(ROOT/"apps/commander/src/customer-mcp-simple.mjs").read_text()
    tool_list=ast.literal_eval(source.split("export const CUSTOMER_MCP_SIMPLE_TOOLS = Object.freeze(",1)[1].split(");",1)[0])
    require(len(tool_list)==33 and len(set(tool_list))==33,"MCP_TOOL_COUNT")
    for test in review["positive"]:
        require(bool(test.get("prompt")) and bool(test.get("expected_behavior")),"POSITIVE_CASE")
        require(test.get("tools_triggered") in tool_list,"UNKNOWN_TRIGGER")
    for test in review["negative"]:
        require(bool(test.get("prompt")) and bool(test.get("expected_behavior")),"NEGATIVE_CASE")
    servers=mcp["mcpServers"]
    require(set(servers)=={"hara-commander"},"ONE_MCP_SERVER")
    server=servers["hara-commander"]
    require(server["type"]=="streamable-http","MCP_TRANSPORT")
    require(server["url"]=="https://commander.haralabs.com.br/api/mcp?profile=simple","PRODUCT_MCP_URL")
    auth=server["extensions"]["com.openai"]["auth"]
    require(auth["type"]=="oauth" and auth["client"]["mode"]=="dcr","OAUTH_DCR")
    require(auth["baseScopes"]==["openid"],"OAUTH_SCOPES")
    require(valid_https(auth["authorizationServerBase"]),"OAUTH_ISSUER")
    require(valid_https(auth["resource"]),"OAUTH_RESOURCE")
    require("annotations: { readOnlyHint, destructiveHint, idempotentHint, openWorldHint }" in source,"EXPLICIT_ANNOTATION_HINTS")
    import struct
    for filename in ("assets/logo.png","assets/icon.png"):
        raw=(BASE/filename).read_bytes()
        require(raw[:8]==bytes([137,80,78,71,13,10,26,10])
                and raw[12:16]==b"IHDR","PNG_ASSET")
        width,height=struct.unpack(">II",raw[16:24])
        require(width==height and 48<=width<=4096,"ICON_DIMENSIONS_INVALID")
    with zipfile.ZipFile(ZIP) as archive:
        names=set(archive.namelist())
        require(names==set(FILES),"ZIP_MEMBERS")
        for filename in FILES:
            require(archive.read(filename)==(BASE/filename).read_bytes(),"ZIP_SOURCE_DRIFT:"+filename)
    report={"schema":"hara.commander-openai-submission-preflight.v1",
        "state":"SOURCE_PACKAGE_PASS","zip_source_matches":True,
        "package_version":plugin["version"],
        "release_notes_present":True,
        "review_demo_video_present":bool(plugin["extensions"]["com.openai"].get("review",{}).get("demo_recording_url")),
        "tools_count":len(tool_list),"positive_cases":5,"negative_cases":3,
        "mcp_oauth_dcr_configured":True,"all_listing_https":True,
        "review_demo_credentials_verified":False,
        "business_verification_verified":False,
        "domain_challenge_verified":False,
        "tool_scan_completed":False,
        "submission_completed":False,
        "openai_approved":False}
    print(json.dumps(report,sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
