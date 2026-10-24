#!/usr/bin/env python3
"""Read-only Cloudflare Durable Objects analytics discovery/measurement probe."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GRAPHQL_ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
DEV_ACCOUNT_ID = "c8631a3ac0ac5a043af08903b8308227"
DEV_NAMESPACES = {
    "DeviceChannel": "acc93b344b4a42218a4a3267f88e16ac",
    "TenantQuota": "5592b173171943ecb93d0f8182e44ef8",
}
DATASETS = (
    "durableObjectsInvocationsAdaptiveGroups",
    "durableObjectsPeriodicGroups",
    "durableObjectsStorageGroups",
    "durableObjectsSubrequestsAdaptiveGroups",
)
HEX32 = re.compile(r"^[0-9a-f]{32}$")

class ProbeError(RuntimeError):
    pass


def read_secret(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ProbeError("DO_ANALYTICS_TOKEN_FILE_UNSAFE") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProbeError("DO_ANALYTICS_TOKEN_FILE_UNSAFE")
        if os.name != "nt":
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ProbeError("DO_ANALYTICS_TOKEN_FILE_OWNER")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ProbeError("DO_ANALYTICS_TOKEN_FILE_PERMISSIONS")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as handle:
            fd = -1
            secret = handle.read().strip()
    finally:
        if fd >= 0:
            os.close(fd)
    if len(secret) < 32:
        raise ProbeError("DO_ANALYTICS_TOKEN_INVALID")
    return secret

def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps(
        {"query": query, "variables": variables or {}},
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        GRAPHQL_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "authorization": "Bearer " + token,
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "HARA-Commander-DO-Analytics/1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise ProbeError("DO_ANALYTICS_HTTP_" + str(exc.code)) from None
    except (URLError, TimeoutError) as exc:
        raise ProbeError("DO_ANALYTICS_NETWORK_ERROR") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProbeError("DO_ANALYTICS_RESPONSE_INVALID") from exc
    if result.get("errors"):
        raise ProbeError("DO_ANALYTICS_GRAPHQL_ERROR")
    return result.get("data") or {}

TYPE_REF = """kind name ofType { kind name ofType { kind name ofType { kind name } } }"""

ACCOUNT_INTROSPECTION = """
query HaraDoAccountIntrospection {
  __type(name: "Account") {
    fields(includeDeprecated: true) {
      name
      isDeprecated
      deprecationReason
      args { name type { %s } }
      type { %s }
    }
  }
}
""" % (TYPE_REF, TYPE_REF)


def unwrap_type(ref: dict | None) -> str | None:
    current = ref or {}
    while current and not current.get("name"):
        current = current.get("ofType") or {}
    return current.get("name")


def account_dataset_fields(data: dict) -> dict[str, dict]:
    fields = ((data.get("__type") or {}).get("fields") or [])
    return {row["name"]: row for row in fields if row.get("name") in DATASETS}

def introspect_type(token: str, name: str) -> dict:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ProbeError("DO_ANALYTICS_SCHEMA_TYPE_INVALID")
    query = """query HaraType($name: String!) {
      __type(name: $name) {
        name kind
        fields(includeDeprecated: true) {
          name isDeprecated deprecationReason
          type { %s }
        }
        inputFields { name type { %s } }
      }
    }""" % (TYPE_REF, TYPE_REF)
    return (graphql(token, query, {"name": name}).get("__type") or {})


def discover(token: str) -> dict:
    account = account_dataset_fields(graphql(token, ACCOUNT_INTROSPECTION))
    missing = sorted(set(DATASETS) - set(account))
    if missing:
        raise ProbeError("DO_ANALYTICS_DATASET_MISSING:" + ",".join(missing))
    result = {}
    for dataset, field in account.items():
        group_type = unwrap_type(field.get("type"))
        if not group_type:
            raise ProbeError("DO_ANALYTICS_GROUP_TYPE_MISSING:" + dataset)
        group = introspect_type(token, group_type)
        args = {arg["name"]: unwrap_type(arg.get("type")) for arg in field.get("args", [])}
        filter_type = args.get("filter")
        filter_meta = introspect_type(token, filter_type) if filter_type else {}
        result[dataset] = {
            "deprecated": bool(field.get("isDeprecated")),
            "group_type": group_type,
            "args": args,
            "filter_fields": sorted(x["name"] for x in filter_meta.get("inputFields") or []),
            "group_fields": sorted(x["name"] for x in group.get("fields") or []),
        }
    return result

def bounded_window(minutes: int) -> tuple[datetime, datetime]:
    if minutes < 1 or minutes > 1440:
        raise ProbeError("DO_ANALYTICS_WINDOW_INVALID")
    end = datetime.now(timezone.utc).replace(microsecond=0)
    return end - timedelta(minutes=minutes), end


def filter_shape(
    meta: dict,
    namespace_id: str,
    start: datetime,
    end: datetime,
) -> tuple[dict, str]:
    fields = set(meta["filter_fields"])
    if "namespaceId" not in fields:
        raise ProbeError("DO_ANALYTICS_NAMESPACE_FILTER_MISSING")
    result: dict[str, str] = {"namespaceId": namespace_id}
    pairs = (
        ("datetime_geq", "datetime_leq", "datetime", lambda x: x.isoformat().replace("+00:00", "Z")),
        ("datetimeHour_geq", "datetimeHour_leq", "hour", lambda x: x.isoformat().replace("+00:00", "Z")),
        ("date_geq", "date_leq", "date", lambda x: x.date().isoformat()),
    )
    for lower, upper, granularity, encode in pairs:
        if lower in fields and upper in fields:
            result[lower] = encode(start)
            result[upper] = encode(end)
            return result, granularity
    raise ProbeError("DO_ANALYTICS_TIME_FILTER_MISSING")


def gql_literal(value: object) -> str:
    if isinstance(value, dict):
        return "{" + ",".join(k + ":" + gql_literal(v) for k, v in value.items()) + "}"
    if isinstance(value, str):
        return json.dumps(value)
    raise ProbeError("DO_ANALYTICS_LITERAL_INVALID")

AGGREGATE_CANDIDATES = {
    "sum": (
        "requests", "responseBodySize", "cpuTime", "duration", "wallTime",
        "webSocketMessages", "subrequests",
    ),
    "max": ("storedBytes",),
    "quantiles": (
        "memoryUsageBytesP50", "memoryUsageBytesP95",
        "memoryUsageBytesP99", "memoryUsageBytesP999",
    ),
}


def aggregate_fields(token: str, group_type: str) -> dict[str, list[str]]:
    group = introspect_type(token, group_type)
    group_fields = {row["name"]: row for row in group.get("fields") or []}
    selected: dict[str, list[str]] = {}
    for aggregate, candidates in AGGREGATE_CANDIDATES.items():
        field = group_fields.get(aggregate)
        if not field:
            continue
        nested_name = unwrap_type(field.get("type"))
        nested = introspect_type(token, nested_name) if nested_name else {}
        available = {row["name"] for row in nested.get("fields") or []}
        chosen = [name for name in candidates if name in available]
        if chosen:
            selected[aggregate] = chosen
    if "count" in group_fields:
        selected["count"] = []
    return selected


def measurement_query(dataset: str, filters: dict, aggregates: dict[str, list[str]]) -> str:
    selections = []
    if "count" in aggregates:
        selections.append("count")
    for aggregate, fields in aggregates.items():
        if aggregate == "count" or not fields:
            continue
        selections.append(aggregate + "{" + " ".join(fields) + "}")
    if not selections:
        raise ProbeError("DO_ANALYTICS_METRICS_UNAVAILABLE:" + dataset)
    return """query HaraDoMeasurement {
      viewer { accounts(filter:{accountTag:$ACCOUNT}) {
        DATASET(filter:FILTER, limit:10000) { SELECTIONS }
      }}
    }""".replace("$ACCOUNT", json.dumps(DEV_ACCOUNT_ID)).replace(
        "DATASET", dataset
    ).replace("FILTER", gql_literal(filters)).replace("SELECTIONS", " ".join(selections))

def measure(token: str, account_id: str, namespaces: dict[str, str], minutes: int) -> dict:
    if not HEX32.fullmatch(account_id):
        raise ProbeError("DO_ANALYTICS_ACCOUNT_ID_INVALID")
    if account_id != DEV_ACCOUNT_ID:
        raise ProbeError("DO_ANALYTICS_NON_DEV_ACCOUNT_DENIED")
    for namespace_id in namespaces.values():
        if not HEX32.fullmatch(namespace_id):
            raise ProbeError("DO_ANALYTICS_NAMESPACE_ID_INVALID")

    schema = discover(token)
    aggregate_schema = {
        dataset: aggregate_fields(token, schema[dataset]["group_type"])
        for dataset in DATASETS
    }
    start, end = bounded_window(minutes)
    output = {"schema": "hara.commander-do-analytics.v1", "environment": "DEV", "minutes": minutes, "namespaces": {}}
    for label, namespace_id in namespaces.items():
        per_namespace = {}
        for dataset in DATASETS:
            meta = schema[dataset]
            filters, granularity = filter_shape(meta, namespace_id, start, end)
            aggregates = aggregate_schema[dataset]
            query = measurement_query(dataset, filters, aggregates)
            accounts = (((graphql(token, query).get("viewer") or {}).get("accounts")) or [])
            rows = (accounts[0].get(dataset) if accounts else []) or []
            per_namespace[dataset] = {
                "aggregates": aggregates,
                "filter_granularity": granularity,
                "rows": rows,
            }
        output["namespaces"][label] = per_namespace
    return output

def self_check() -> None:
    assert HEX32.fullmatch(DEV_ACCOUNT_ID)
    assert all(HEX32.fullmatch(value) for value in DEV_NAMESPACES.values())
    assert len(DATASETS) == 4
    start, end = bounded_window(5)
    assert end > start
    sample = {
        "filter_fields": ["namespaceId", "datetime_geq", "datetime_leq"],
    }
    shaped, granularity = filter_shape(
        sample,
        DEV_NAMESPACES["DeviceChannel"],
        start,
        end,
    )
    assert granularity == "datetime"
    assert shaped["namespaceId"] == DEV_NAMESPACES["DeviceChannel"]
    query = measurement_query(
        DATASETS[0],
        shaped,
        {"count": [], "sum": ["requests"]},
    )
    assert DEV_ACCOUNT_ID in query
    assert DEV_NAMESPACES["DeviceChannel"] in query
    assert "Bearer" not in query
    print("COMMANDER_DO_ANALYTICS_PROBE_SOURCE=PASS")
    print("COMMANDER_DO_ANALYTICS_ENDPOINT=GRAPHQL_READ_ONLY")
    print("COMMANDER_DO_ANALYTICS_TOKEN_OUTPUT=ABSENT")
    print("COMMANDER_DO_ANALYTICS_ENV=DEV_ONLY")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--minutes", type=int, default=15)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.check:
        self_check()
        return 0
    if not args.token_file:
        raise ProbeError("DO_ANALYTICS_TOKEN_FILE_REQUIRED")
    token = read_secret(Path(args.token_file))
    try:
        if args.discover:
            result = {
                "schema": "hara.commander-do-analytics-discovery.v1",
                "datasets": discover(token),
            }
        elif args.measure:
            result = measure(token, DEV_ACCOUNT_ID, DEV_NAMESPACES, args.minutes)
        else:
            raise ProbeError("DO_ANALYTICS_MODE_REQUIRED")
    finally:
        token = ""

    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
        print("COMMANDER_DO_ANALYTICS_OUTPUT_WRITTEN=TRUE")
    else:
        print(encoded, end="")
    print("COMMANDER_DO_ANALYTICS_TOKEN_EXPOSED=FALSE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as exc:
        print("COMMANDER_DO_ANALYTICS=FAIL:" + str(exc))
        raise SystemExit(1)
