# H.A.R.A. Commander Product Hardening & Launch — Successor Handoff

**Timestamp:** 2026-09-26T03:31Z  
**Repository:** `tiagoharalabs/hara-site`  
**Front name:** **Commander Product Hardening & Launch**  
**Primary product-security owner:** #189 — Pre-public-launch adversarial hardening  
**Parallel transport owner:** #163 — Commander Scale V2 / Event V2  
**Sibling product owners:** #168 re-enroll UX; #167 human/session cost; hara-platform#1533 Commander NOC  
**Visual state:** **FROZEN / DO NOT REOPEN WITHOUT BUG, REGRESSION, ACCESSIBILITY OR STRATEGIC CHANGE**  
**PROD Event V2 cutover:** **DENY**

---

## 1. Executive state

This front leaves Commander in a materially different state from the beginning of the work.

```text
COMMANDER_V1_PROD_HOMOLOGATION=PASS
COMMANDER_V1_PROD_HOMOLOGATION_OWNER=#65_CLOSED
PUBLIC_SITE_PRESENTATION=PRODUCTION_READY
PUBLIC_SITE_MOBILE=PRODUCTION_READY
COMMANDER_UX_PRESENTATION=PRODUCTION_READY
PUBLIC_VISUAL_FREEZE=TRUE
COMMANDER_VISUAL_FREEZE=TRUE

SECURITY_HARDENING_OWNER=#189
SECURITY_MULTITENANT_LIVE_DEV=PASS
SECURITY_PAIRING_CONCURRENCY=PASS
NEXT_SECURITY_GATE=RATE_LIMIT_BRUTE_FORCE_RESILIENCE

EVENT_V2_OWNER=#163
LINUX_EVENT_V2_DEV_CANARY=PASS
LINUX_EVENT_V2_RC=LIVE_PROVEN
WINDOWS_EVENT_V2_RC_SOURCE=READY_UNPROVEN
NEXT_EVENT_V2_GATE=WINDOWS_HARA_OWNED_RC_LIVE_CANARY
CROSS_PLATFORM_EVENT_V2_PARITY=FALSE
EVENT_V2_PROD_CUTOVER=DENY

REENROLL_UX_OWNER=#168
HUMAN_SCALE_COST_OWNER=#167
COMMANDER_NOC_OWNER=hara-platform#1533
```

The successor should **not** return to aesthetic iteration. The public surfaces have now been reviewed repeatedly on desktop and mobile and are intentionally frozen.

The next value-bearing work is:
1. adversarial security hardening;
2. Event V2 Windows RC proof / cross-platform parity;
3. device lifecycle usability;
4. operational/NOC readiness;
5. human/session scale and cost;
6. release/launch acceptance.

---

## 2. Fresh live state at handoff

Readback immediately before this handoff:

```text
HARA_SITE_MAIN=ab75f86458f3bfed88193a11c05af27fa17996aa

PUBLIC_SITE=https://www.haralabs.com.br/
PUBLIC_SITE_CSS=v16.3.16
PUBLIC_SITE_LAST_VISUAL_VERSION=92ecdd9f-f9c0-4ead-b31f-43fae7c7f570

COMMANDER=https://commander.haralabs.com.br/
COMMANDER_CSS=20260925-neon7
COMMANDER_PROD_VERSION=f7466457-301d-43ff-99eb-9f8e0c7494b5
COMMANDER_HEALTH=PASS
```

The main branch advanced after the visual work with Event V2/security source work. This is expected. Do not infer that Event V2 has been promoted to PROD from the main branch state.

---

## 3. What this front delivered

### 3.1 Commander functional baseline / homologation

The functional V1 baseline was completed before the visual freeze and remains authoritative.

```text
GATE_0=PASS
GATE_1=PASS
GATE_2=PASS
GATE_3=PASS
GATE_4=PASS
GATE_5=PASS
GATE_6=PASS
GATE_7=PASS
GATE_8=PASS
COMMANDER_V1_PROD_HOMOLOGATION=PASS
```

Five-tool product surface already proven:
- `hara.health`
- `hara.functions.list`
- `hara.functions.describe`
- `hara.functions.invoke`
- `hara.receipts.get`

Already proven negative/security behavior includes:
- unauthenticated MCP denied;
- invalid token denied;
- arbitrary shell denied;
- arbitrary filesystem read denied;
- offline selected device execution denied;
- tampered receipt denied;
- quota double charge prevented;
- modern TLS/header baseline;
- hash-only pairing/device credential storage;
- local secret custody 0600/0700;
- receipt/runtime sensitive-field scan with zero hits.

**Do not reopen #65.**

### 3.2 Quota reliability

PR #187 — `f5ffa530bca18a34e7193b164c6bf5d3c61b1965`

Fixed ambiguous quota authorize timeout reconciliation and proved:

```text
QUOTA_RESERVE=PASS
QUOTA_RELEASE=PASS
QUOTA_RELEASE_REPLAY=DENIED
QUOTA_NET_USAGE=ZERO
DOUBLE_CHARGE=FALSE
```

### 3.3 Commander product UX

PR #186 — `a23992643f3139cd715e7dad0c6798ea737bcd09`

Delivered the compact device workspace and navigation baseline:
- Dispositivos / Conectar novo split;
- Ativos / Histórico lifecycle tabs;
- onboarding hidden under explicit connect action;
- compact device rows;
- selected device state `Em uso`;
- improved sidebar/header legibility.

PR #176 — revoked devices moved to History.  
PR #182 — History UI cache/static currentness.  
PR #183 — Linux installer release-manifest parity.  
PR #178 — explicit/reproducible Linux doctor heartbeat.

### 3.4 Public positioning / Products information architecture

PR #192 — `94a0b8a9f51cf18e7eb349ba6bd2a6657d7235de`

Security-led Commander pre-launch positioning:
- `IA que age. Controle que continua seu.`
- security by design;
- verified controls without claiming external certification;
- intentionally restrained public detail.

PR #193 — `bb55bf79948411c4ee885b6287ef6acb3d925a03`

Introduced:
- `Produtos` in primary navigation;
- `/produtos/` portfolio;
- Commander as Product 01;
- Commander detail nested under the product portfolio;
- sitemap updates.

### 3.5 Typography / title / glow cleanup

PR #194 — simplified title hierarchy, typography and button glow.  
PR #197 — restored public CSS parity for low-glow controls.  
PR #199 — removed redundant title bars and restrained control glow.

The product/UI rule is now:

```text
EACH_INFORMATION_ONCE_AT_THE_CORRECT_HIERARCHY=TRUE
DUPLICATE_PAGE_TITLE_BANDS=DENY
PERMANENT_NEON_BY_DEFAULT=DENY
```

### 3.6 Canonical Neon appearance system

The Neon control became a product-wide appearance principle rather than an ad hoc effect.

Key PR ledger:
- #200 — opt-in Neon appearance mode;
- #201 — bolt-only Neon control;
- #204 — expressive ON / glow-free OFF;
- #210 — light blue / dark gold theme contract;
- #212 — stronger light identity/navigation glow;
- #214 — canonical capybara full glow coverage;
- #216 — architecture runner + Commander glow consolidation;
- #219 — Commander light mode unified around blue;
- #222 — selected Commander navigation surface locked independent of Neon.

Canonical law:

```text
NEON_OFF=ZERO_GLOW
LIGHT_NEON_ON=HARA_CYAN_BLUE
DARK_NEON_ON=HARA_GOLD
IDENTITY_NAVIGATION_PRIORITY=TRUE
```

Commander-specific final law:

```text
LIGHT_THEME_ACTION_SELECTION=BLUE
LIGHT_THEME_TRUE_WARNING=GOLD_ALLOWED
DARK_THEME_IDENTITY_ACTION=GOLD

LIGHT_ACTIVE_NAV_SURFACE=dark_blue
NEON_OFF_ACTIVE_NAV_HALO=none
NEON_ON_ACTIVE_NAV_HALO=blue_cyan
ACTIVE_TEXT=white
ACTIVE_ICON=cyan
```

The Neon toggle changes **expression**, not the selected menu surface.

### 3.7 Public-site desktop/mobile visual completion

Key PR ledger:
- #208 — make orbit motion visible on mobile;
- #211 — visible mobile orbit runner;
- #214 — all H.A.R.A capybaras inherit Neon;
- #216 — architecture orbit motion visible desktop + mobile;
- #218 — restore rich system visuals on mobile;
- #228 — final mobile hero connector geometry.

PR #228 merge:
`ac633072ee6487181e50aee0bcb1283203ac9332`

Final mobile fix:
- desktop SVG preserved;
- mobile receives dedicated normalized connector SVG;
- four connector endpoints and dots share the same mobile coordinate system;
- non-scaling stroke preserves visual weight;
- no more desktop path geometry squeezed against repositioned mobile cards.

Final acceptance after user live review:

```text
PUBLIC_DESKTOP_VISUAL=ACCEPTED
PUBLIC_MOBILE_VISUAL=ACCEPTED
PUBLIC_NEON=ACCEPTED
MOBILE_HERO_CONNECTORS=ACCEPTED
PUBLIC_VISUAL_FREEZE=TRUE
```

---

## 4. Visual freeze / anti-regression rule

The H.A.R.A Labs public site and Commander presentation must now be treated as a stable product surface.

```text
DO_NOT_REOPEN_PUBLIC_VISUAL_FOR_PREFERENCE=TRUE
DO_NOT_REOPEN_COMMANDER_VISUAL_FOR_PREFERENCE=TRUE
ALLOW_VISUAL_CHANGE_IF=BUG|REGRESSION|ACCESSIBILITY|STRATEGIC_PRODUCT_CHANGE
```

Aesthetic exploration is no longer an active workstream.

Before touching public CSS/Commander visual CSS, the successor must identify a concrete defect or product requirement.

---

## 5. Security hardening state — #189

#189 is the primary next product-hardening owner.

Completed so far:

### Gate 1 — multi-tenant isolation

Source/model + isolated live DEV proof blocked cross-tenant:
- device enumeration;
- device selection;
- device revoke;
- call enqueue;
- quota read override;
- caller-supplied tenant override.

DEV fixtures were cleaned and re-read as zero.

### Gate 2 — pairing concurrency/replay race

Live DEV campaign:

```text
LIVE_PAIRING_RACE_HTTP=201,401
LIVE_PAIRING_CONCURRENT_WINNERS=1
LIVE_PAIRING_CONCURRENT_LOSERS=1
LIVE_PAIRING_REPLAY=DENIED
LIVE_PAIRING_SUPERSEDED=DENIED
LIVE_PAIRING_EXPIRED=DENIED
LIVE_PAIRING_DEVICE_COUNT=1
LIVE_PAIRING_FIXTURE_CLEANUP=PASS
PAIRING_CONCURRENCY=PASS
PROD_MUTATION=FALSE
```

PRs:
- #230 — multi-tenant isolation model/live source;
- #232 — pairing race proof.

### Next security gate

```text
NEXT_SECURITY_GATE=RATE_LIMIT_BRUTE_FORCE_RESILIENCE
```

Exercise bounded, non-destructive campaigns against:
- pairing attempts;
- login/auth initiation;
- enrollment;
- internal MCP authorization where ownership permits;
- portal mutation endpoints.

Then continue:
- browser/session negative matrix;
- external web/TLS/header scan;
- OWASP ASVS 5.0 mapping;
- independent pentest scope;
- remediation/retest.

Do not interfere with #163-owned Event V2 DEV secrets or canary credentials.

---

## 6. Event V2 state — #163

Event V2 already has a dedicated successor handoff:

`docs/handoffs/HARA_COMMANDER_EVENT_V2_SUCCESSOR_HANDOFF_20260926T0316Z.md`

**Read it before any Event V2 work.**

Current boundary:

```text
LINUX_EVENT_V2_DEV_CANARY=PASS
LINUX_RC_LIVE_PROVEN=TRUE
PRACTICAL_1K_PATH=HARDENED
WINDOWS_EVENT_V2_RC_SOURCE=READY_UNPROVEN
NEXT_GATE=WINDOWS_HARA_OWNED_RC_LIVE_CANARY
CROSS_PLATFORM_EVENT_V2_PARITY=FALSE
PROD_CUTOVER=DENY
```

Latest Windows source work already on main:
- #229 — Windows Event V2 RC contract;
- #231 — Windows Event V2 adapter;
- #233 — reversible Windows RC installer.

Do not open a second Event V2 implementation owner.

---

## 7. Remaining real product owners

### #168 — explicit device re-enrollment

Current secure revoke behavior is correct. UX remains incomplete.

Need:
- explicit `re-enroll` flow;
- fresh pairing token mandatory;
- revoked credential never resurrected;
- actionable installer/portal copy;
- one discoverable user flow.

### #167 — human/session scale and cost

Owner for:
- 10k registered users;
- human/session/Identity cost;
- login burst;
- Identity storage/application scale;
- existing-fleet-first scale-out.

Do not mix device Event V2 scaling into #167.

### hara-platform#1533 — Commander NOC

Continue privacy-first NOC:
- health;
- latency;
- reconnect;
- queues;
- versions;
- quota/cost;
- no customer prompt/command/result/file content in routine telemetry;
- no high-cardinality customer IDs in Prometheus.

### #25 and #190 — recensus before work

These owners contain substantial scope already delivered:
- #25 customer portal/login/usage/onboarding;
- #190 Commander pre-launch security teaser.

Do **not** blindly continue them. Reconcile acceptance against current product state and close/re-scope only after a fresh census.

---

## 8. Explicit DO NOT REPLAY

```text
DO_NOT_REOPEN=#65_V1_PROD_HOMOLOGATION
DO_NOT_REPLAY=D1_MIGRATION_0010
DO_NOT_REPLAY=D1_MIGRATION_0011
DO_NOT_REPEAT=LINUX_EVENT_V2_DEV_CANARY
DO_NOT_REINTRODUCE=2S_IDLE_POLLING
DO_NOT_REINTRODUCE=30S_HTTP_HEARTBEAT_ON_EVENT_PATH
DO_NOT_REINTRODUCE=300MS_EVENT_V2_TERMINAL_SETTLE_WITHOUT_NEW_EVIDENCE
DO_NOT_ROUTE=CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES
DO_NOT_MUTATE=PUBLIC_AGENT_0_3_7_UNTIL_RC_ACCEPTANCE
DO_NOT_CUTOVER_EVENT_V2_PROD=UNTIL_CROSS_PLATFORM_RC_PARITY_AND_ACCEPTANCE
DO_NOT_REOPEN=PUBLIC_SITE_VISUAL_WITHOUT_DEFECT
DO_NOT_REOPEN=COMMANDER_VISUAL_WITHOUT_DEFECT
```

---

## 9. Successor execution order

### P0 — fresh currentness

1. Read this handoff.
2. Read fresh main.
3. Read #189.
4. Read the #163 Event V2 successor handoff.
5. Read #168, #167 and hara-platform#1533 only if taking those owners.
6. Revalidate PROD Commander health without mutating PROD.

### P1 — #189 security

Resume at:

```text
RATE_LIMIT_BRUTE_FORCE_RESILIENCE
```

Do not replay multi-tenant or pairing race campaigns unless a regression/change requires fresh proof.

### P2 — #163 Event V2 sibling owner

Only if explicitly acting as #163 successor:
- HARA-owned Windows target;
- stable 0.3.7 preserved;
- RC inert install;
- DEV-only activation;
- real connection attestation;
- five-tool / receipt / quota proof;
- clean shutdown;
- manual rollback;
- failed-activation automatic rollback.

### P3 — lifecycle / operation

Then advance:
- #168 re-enroll;
- hara-platform#1533 NOC;
- #167 human/session scale/cost.

### P4 — launch readiness

When #189 and the selected release transport are terminal:
- recensus #25 / #190;
- define controlled external beta/reviewer path;
- support/runbook;
- release acceptance;
- only then broader launch.

---

## 10. Successor front name

Use:

```text
Commander Product Hardening & Launch
```

This front is responsible for taking the already-homologated, visually-frozen Commander from **working product** to **externally defensible and operable product**.

It must not become a second Event V2 implementation lane.

---

## 11. Successor first message / operational prompt

Copy this into the new front:

```text
Commander Product Hardening & Launch

Read first:
docs/handoffs/HARA_COMMANDER_PRODUCT_HARDENING_LAUNCH_SUCCESSOR_HANDOFF_20260926T0331Z.md

Then read fresh hara-site main and issue #189.

For Event V2, also read:
docs/handoffs/HARA_COMMANDER_EVENT_V2_SUCCESSOR_HANDOFF_20260926T0316Z.md
and hara-site#163.

Do not reopen #65.
Do not replay D1 migrations 0010/0011.
Do not repeat the Linux Event V2 DEV canary.
Do not reintroduce 2s polling, 30s HTTP heartbeat or 300ms terminal settle.
Do not route customer traffic through HARA Services.
Do not alter public Agent 0.3.7 before RC acceptance.
Do not reopen public-site or Commander aesthetic work without a real defect.

Public H.A.R.A Labs desktop/mobile and Commander UX/Neon are accepted and frozen.

Primary next product gate:
#189 RATE_LIMIT_BRUTE_FORCE_RESILIENCE

Event V2 remains a sibling owner under #163:
NEXT_GATE=WINDOWS_HARA_OWNED_RC_LIVE_CANARY
CROSS_PLATFORM_EVENT_V2_PARITY=FALSE
PROD_CUTOVER=DENY

After security/Event V2 gates, continue real product gaps:
#168 re-enroll
hara-platform#1533 Commander NOC
#167 human/session scale and cost

Keep Git evidence current and avoid concurrent ownership.
```
