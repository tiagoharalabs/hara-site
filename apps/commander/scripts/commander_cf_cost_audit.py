#!/usr/bin/env python3
"""Read-only Commander PROD cost evidence. No client content or token is exported.

Costs are observed aggregate usage at public marginal list rates, BEFORE shared
monthly allowances. They are not an invoice or a per-tenant attribution. Missing
metrics remain unknown. Storage gauges are not misrepresented as GB-month usage.
Uses the existing canonical Wrangler OAuth flow; does not change permissions.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import urllib.request
import urllib.error
import commander_prod_cf_efficiency_probe as cf

SCHEMA = 'hara.commander-observed-cloud-cost.v1'
PRICING_DATE = '2026-10-11'
PRICING_SOURCES = [
 'https://developers.cloudflare.com/workers/platform/pricing/',
 'https://developers.cloudflare.com/d1/platform/pricing/',
 'https://developers.cloudflare.com/durable-objects/platform/pricing/',
 'https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/',
]
# Rate per single unit (not per million). CPU input is microseconds, converted
# to milliseconds BEFORE pricing. DO duration already arrives in GB-seconds.
RATES = {'worker_request':Decimal('0.00000030'),
 'worker_cpu_ms':Decimal('0.00000002'),
 'd1_row_read':Decimal('0.000000001'), 'd1_row_written':Decimal('0.000001'),
 'do_request':Decimal('0.00000015'), 'do_gb_s':Decimal('0.00001250'),
 'do_sql_row_read':Decimal('0.000000001'), 'do_sql_row_written':Decimal('0.000001'),
 'do_kv_read_unit':Decimal('0.00000020'), 'do_kv_write_unit':Decimal('0.000001'),
 'do_kv_delete':Decimal('0.000001')}

def api_get_suffix(suffix: str) -> dict:
    if suffix != '/workers/durable_objects/namespaces':
        raise ValueError('API_ROUTE_NOT_ALLOWLISTED')
    token=cf.auth_token()
    try:
        request=urllib.request.Request('https://api.cloudflare.com/client/v4/accounts/'+cf.CF_ACCOUNT_ID+suffix,
          headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
        with urllib.request.urlopen(request,timeout=20) as response:
            data=json.load(response)
        if not data.get('success'): raise RuntimeError('NAMESPACE_METADATA_UNAVAILABLE')
        return data
    except urllib.error.HTTPError as exc:
        raise RuntimeError('NAMESPACE_HTTP_'+str(exc.code)) from None
    finally: token=''

def prod_namespaces() -> list[dict]:
    data=api_get_suffix('/workers/durable_objects/namespaces')
    rows=[{k:r.get(k) for k in ('id','name','script','class')}
          for r in data.get('result',[]) if r.get('script') == cf.WORKER_NAME]
    if not rows or any(not re.fullmatch(r'[0-9a-f]{32}',r['id'] or '') for r in rows):
        raise RuntimeError('PROD_NAMESPACE_SCOPE_UNAVAILABLE')
    return rows

def prod_database() -> str:
    text=(cf.APP/'wrangler.jsonc').read_text()
    ids=re.findall(r'"database_id"\s*:\s*"([0-9a-f-]{36})"',text)
    if len(ids)!=1: raise RuntimeError('PROD_DATABASE_SCOPE_AMBIGUOUS')
    return ids[0]

def window(start: str,end: str) -> tuple[datetime,datetime]:
    a,b=cf.utc(start),cf.utc(end)
    if not timedelta(minutes=1)<=b-a<=timedelta(days=31):raise ValueError('WINDOW_OUT_OF_BOUNDS')
    if b>datetime.now(timezone.utc)-timedelta(minutes=2):raise ValueError('WINDOW_NOT_FINALIZED')
    return a,b

def literal(value):return json.dumps(value,separators=(',',':'))

def make_queries(start: str,end: str,db: str,namespaces: list[dict]) -> dict[str,str]:
    when='datetime_geq:'+literal(start)+',datetime_lt:'+literal(end)
    wf=when+',scriptName:'+literal(cf.WORKER_NAME)
    df=when+',databaseId:'+literal(db)
    nf=when+',namespaceId_in:'+literal([x['id'] for x in namespaces])
    parts={
      'worker':f'workersInvocationsAdaptive(limit:100,filter:{{{wf}}}){{sum{{requests errors subrequests cpuTimeUs}} avg{{sampleInterval}}}}',
      'd1':f'd1AnalyticsAdaptiveGroups(limit:100,filter:{{{df}}}){{sum{{rowsRead rowsWritten readQueries writeQueries}} avg{{sampleInterval queryBatchTimeMs}}}}',
      'd1_storage':f'd1StorageAdaptiveGroups(limit:100,filter:{{{df}}}){{max{{databaseSizeBytes}}}}',
      'do_invocations':f'durableObjectsInvocationsAdaptiveGroups(limit:1000,filter:{{{nf}}}){{dimensions{{namespaceId type status}} sum{{requests errors}} avg{{sampleInterval}}}}',
      'do_periodic':f'durableObjectsPeriodicGroups(limit:1000,filter:{{{nf}}}){{dimensions{{namespaceId}} sum{{duration cpuTime activeTime inboundWebsocketMsgCount outboundWebsocketMsgCount rowsRead rowsWritten storageReadUnits storageWriteUnits storageDeletes}} avg{{sampleInterval}}}}',
    }
    return {k:'query {viewer {accounts(filter:{accountTag:'+literal(cf.CF_ACCOUNT_ID)+'}) {metric:'+v+'}}}' for k,v in parts.items()}

def total(raw: dict,group: str,field: str):
    entry=raw.get(group,{})
    rows=entry.get('rows')
    if entry.get('state')!='MEASURED' or not rows:return None
    values=[row.get('sum',{}).get(field) for row in rows]
    if any(v is None for v in values):return None
    result=sum((Decimal(str(v)) for v in values),Decimal(0))
    if not result.is_finite() or result<0:raise ValueError('INVALID_METRIC')
    return result

def calculate(raw: dict) -> dict:
    mapped={
      'worker_requests':('worker','requests','worker_request',Decimal(1)),
      'worker_cpu':('worker','cpuTimeUs','worker_cpu_ms',Decimal('0.001')),
      'd1_reads':('d1','rowsRead','d1_row_read',Decimal(1)),
      'd1_writes':('d1','rowsWritten','d1_row_written',Decimal(1)),
      'do_duration':('do_periodic','duration','do_gb_s',Decimal(1)),
      'do_sql_reads':('do_periodic','rowsRead','do_sql_row_read',Decimal(1)),
      'do_sql_writes':('do_periodic','rowsWritten','do_sql_row_written',Decimal(1)),
      'do_kv_reads':('do_periodic','storageReadUnits','do_kv_read_unit',Decimal(1)),
      'do_kv_writes':('do_periodic','storageWriteUnits','do_kv_write_unit',Decimal(1)),
      'do_kv_deletes':('do_periodic','storageDeletes','do_kv_delete',Decimal(1)),
    }
    items={};subtotal=Decimal(0);missing=[]
    for label,(group,field,rate,scale) in mapped.items():
        value=total(raw,group,field)
        if value is None:
            items[label]={'state':'UNKNOWN','usd':None};missing.append(label);continue
        value*=scale;cost=value*RATES[rate];subtotal+=cost
        items[label]={'state':'MEASURED_USAGE_LIST_RATE','units':float(value),'unit_rate_usd':str(RATES[rate]),'usd':float(cost)}
    # Analytics counts are NOT billing request units. Hibernating WS messages
    # are also invocations; do not discount the complete invocation count 20:1.
    inv=total(raw,'do_invocations','requests')
    messages=total(raw,'do_periodic','inboundWebsocketMsgCount')
    bound=None
    if inv is not None and messages is not None:
        bound=(inv+messages)*RATES['do_request']
    return {'currency':'USD','items':items,
      'measured_component_subtotal_usd':float(subtotal),
      'do_requests_conservative_list_rate_upper_bound_usd':float(bound) if bound is not None else None,
      'variable_list_rate_upper_estimate_usd':float(subtotal+bound) if bound is not None and not missing else None,
      'missing_components':missing,
      'monthly_allowances_applied':False,'invoice_verified':False,'billed_total_usd':None,
      'excluded':['stored GB-months','account subscription','Workers logs','other products','Identity/tunnel hosts','taxes/FX'],
      'do_request_note':'Upper estimate charges every recorded invocation and periodic inbound message at a full request; actual WS message billing is 20:1 and can be lower. Long-lived open connections may not yet have complete request metrics.'}

def collect(start: str,end: str) -> dict:
    window(start,end)
    namespaces=prod_namespaces();db=prod_database();raw={}
    for label,q in make_queries(start,end,db,namespaces).items():
        try:
            data=cf.request_graphql(q)
            accounts=(data.get('data',{}).get('viewer') or {}).get('accounts') or []
            if len(accounts)!=1:raise RuntimeError('ACCOUNT_SCOPE_UNAVAILABLE')
            rows=accounts[0].get('metric')
            if rows is None:raise RuntimeError('METRIC_UNAVAILABLE')
            if len(rows)>= (1000 if label.startswith('do_') else 100):raise RuntimeError('METRIC_POSSIBLY_TRUNCATED')
            intervals=[r.get('avg',{}).get('sampleInterval') for r in rows]
            intervals=[x for x in intervals if x is not None]
            raw[label]={'state':'MEASURED','rows':rows,'sample_interval_max':max(intervals) if intervals else None}
        except (RuntimeError,ValueError,KeyError) as exc:
            # Only our fixed symbolic error codes escape; no tokens/SQL/content.
            code=str(exc)
            raw[label]={'state':'UNAVAILABLE','code':code if re.fullmatch('[A-Z0-9_]+',code) else 'METRIC_QUERY_FAILED','rows':None}
    return {'schema':SCHEMA,'collected_at_utc':cf.iso(datetime.now(timezone.utc)),
      'scope':'COMMANDER_PROD_AGGREGATE_NOT_SINGLE_TENANT','worker':cf.WORKER_NAME,
      'window':{'start_utc':start,'end_utc':end,'closed_open':True},
      'database_id':db,'namespaces':namespaces,'metrics':raw,'cost':calculate(raw),
      'pricing_date':PRICING_DATE,'pricing_sources':PRICING_SOURCES,
      'account_plan_verified':False,'new_polling_or_scheduled_job_installed':False,
      'usage_semantics':'Provider analytics, possibly adaptively sampled; not an invoice. Request pricing bound is not a statistical confidence bound.',
      'production_versions_in_window':'May contain multiple deployed versions; not a causal before/after experiment',
      'customer_content_collected':False,'credentials_exported':False}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--start',required=True);p.add_argument('--end',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=collect(a.start,a.end);cf.save_protected(a.output,r)
    print(json.dumps({'window':r['window'],'datasets':{k:v['state'] for k,v in r['metrics'].items()},'cost':r['cost']},indent=2))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        # External exceptions may contain request paths; print a class, not secrets.
        print('COMMANDER_COST_AUDIT_FAILED:'+type(exc).__name__);raise SystemExit(1)
