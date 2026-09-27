import { DurableObject } from "cloudflare:workers";
import { fixedWindowDecision } from "./security-rate-limit.mjs";

export class SecurityRateLimit extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ctx = ctx;
    this.ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS strict_rate_window (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          window_start_ms INTEGER NOT NULL,
          count INTEGER NOT NULL
        );
      `);
    });
  }

  async limit(limit, periodSeconds) {
    const safeLimit = Number(limit);
    const safePeriodSeconds = Number(periodSeconds);
    if (!Number.isInteger(safeLimit) || safeLimit <= 0) {
      throw new Error("STRICT_RATE_LIMIT_LIMIT_INVALID");
    }
    if (!Number.isInteger(safePeriodSeconds) || safePeriodSeconds <= 0) {
      throw new Error("STRICT_RATE_LIMIT_PERIOD_INVALID");
    }

    const nowMs = Date.now();
    const periodMs = safePeriodSeconds * 1000;
    const row = [...this.ctx.storage.sql.exec(
      "SELECT window_start_ms, count FROM strict_rate_window WHERE id = 1"
    )][0] || null;
    const decision = fixedWindowDecision(row, safeLimit, periodMs, nowMs);

    if (decision.success) {
      this.ctx.storage.sql.exec(
        `INSERT INTO strict_rate_window (id, window_start_ms, count)
         VALUES (1, ?, ?)
         ON CONFLICT(id) DO UPDATE SET
           window_start_ms = excluded.window_start_ms,
           count = excluded.count`,
        decision.window_start_ms,
        decision.count,
      );
    }

    return {
      success: decision.success,
      limit: safeLimit,
      period_seconds: safePeriodSeconds,
      count: decision.count,
      retry_after_ms: decision.retry_after_ms,
    };
  }
}
