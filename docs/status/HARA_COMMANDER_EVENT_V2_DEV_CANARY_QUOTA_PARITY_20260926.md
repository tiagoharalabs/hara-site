# Commander Event V2 DEV canary — quota parity evidence

Owner: #163  
Environment: DEV only  
Device: HARA-owned `nucleo-a`

## Result

```text
COMMANDER_EVENT_V2_QUOTA_PARITY=PASS
COMMANDER_EVENT_V2_QUOTA_RELEASE_REPLAY=TERMINAL
COMMANDER_EVENT_V2_QUOTA_COMMIT=COMMITTED
COMMANDER_EVENT_V2_QUOTA_COMMIT_IDEMPOTENT=TRUE
COMMANDER_EVENT_V2_QUOTA_DOUBLE_CHARGE=FALSE
COMMANDER_EVENT_V2_QUOTA_RECEIPT_BOUND=TRUE
COMMANDER_EVENT_V2_QUOTA_AUTHORITY=HARA_COMMANDER
COMMANDER_EVENT_V2_QUOTA_TOKEN_EXPOSED=FALSE
```

## Proven laws

1. reserve -> release -> replay is terminal `RELEASED`;
2. reserve -> real Event V2 invoke -> receipt -> commit reaches `COMMITTED`;
3. repeating commit with the same receipt returns the existing committed state;
4. consumed units do not increase on the idempotent commit;
5. authorize replay returns the same committed receipt binding;
6. release after commit is denied as `RESERVATION_NOT_ACTIVE` while preserving `COMMITTED`;
7. the customer command path remains `HARA_COMMANDER / EVENT_V2`;
8. the isolated DEV canary token is never printed.

## Boundary

```text
PROD_MUTATION=FALSE
PROD_AGENT_0_3_7=PRESERVED
CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=FALSE
DEV_ONLY=TRUE
```

This completes the remaining quota-parity gate for the DEV Event V2 canary.
