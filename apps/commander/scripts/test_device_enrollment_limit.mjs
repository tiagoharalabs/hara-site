#!/usr/bin/env node
// Exercises the exact SQL used by the Worker on isolated SQLite, including
// simultaneous transactions from independent connections to one database.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import {
  DEVICE_ENROLL_INSERT_SQL, DEVICE_ENROLL_CONSUME_SQL, DEVICE_ENROLL_LIMIT_SQL,
} from "../src/device-enrollment.mjs";

const AT = "2026-10-20T18:00:00.000Z";
const AFTER = "2026-10-21T18:00:00.000Z";

function open(file) {
  const db = new DatabaseSync(file);
  db.exec("PRAGMA busy_timeout=10000");
  return db;
}

function attempt(db, token, id) {
  db.exec("BEGIN IMMEDIATE");
  try {
    const inserted = db.prepare(DEVICE_ENROLL_INSERT_SQL).run(
      id, id, "LINUX", "x86_64", "0.3.43", "hash-" + id,
      AT, AT, "ASK_EVERY_ACTION", token, AT, AT, AT,
    );
    const consumed = db.prepare(DEVICE_ENROLL_CONSUME_SQL).run(AT, token, AT, id);
    const atLimit = inserted.changes ? null
      : db.prepare(DEVICE_ENROLL_LIMIT_SQL).get(token, AT, AT, AT);
    db.exec("COMMIT");
    assert.equal(Number(consumed.changes), Number(inserted.changes));
    return inserted.changes ? "ENROLLED" : (atLimit ? "DEVICE_LIMIT_REACHED" : "DEVICE_PAIRING_INVALID");
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

if (!isMainThread) {
  const db = open(workerData.file);
  parentPort.postMessage({ ready: true });
  parentPort.once("message", () => {
    try { parentPort.postMessage({ state: attempt(db, workerData.token, workerData.id) }); }
    catch (error) { parentPort.postMessage({ error: String(error) }); }
    finally { db.close(); }
  });
} else {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "commander-device-limit-"));
  const file = path.join(temporary, "product.sqlite");
  const db = open(file);
  try {
    db.exec(`
      PRAGMA journal_mode=WAL;
      CREATE TABLE plans (plan_code TEXT PRIMARY KEY,display_name TEXT,meter_id TEXT,
        period_kind TEXT,unit_limit INTEGER,state TEXT);
      CREATE TABLE entitlements (tenant_id TEXT,plan_code TEXT,state TEXT,
        valid_from_utc TEXT,valid_until_utc TEXT);
      CREATE TABLE device_pairing_tokens (pairing_id TEXT PRIMARY KEY,token_hash TEXT UNIQUE,
        tenant_id TEXT,subject_id TEXT,consumed_at_utc TEXT,superseded_at_utc TEXT,
        expires_at_utc TEXT);
      CREATE TABLE commander_devices (device_id TEXT PRIMARY KEY,pairing_id TEXT UNIQUE,
        tenant_id TEXT,enrolled_by_subject_id TEXT,device_name TEXT,platform TEXT,
        architecture TEXT,agent_version TEXT,tunnel_mode TEXT,credential_hash TEXT UNIQUE,
        state TEXT,created_at_utc TEXT,last_seen_at_utc TEXT,revoked_at_utc TEXT,
        approval_mode TEXT);
      INSERT INTO plans VALUES
        ('TRIAL','Free','HARA_COMMANDER_GOVERNED_INVOKE','CALENDAR_MONTH',10000,'ACTIVE'),
        ('STANDARD','Pro','HARA_COMMANDER_GOVERNED_INVOKE','NONE',NULL,'ACTIVE'),
        ('FOUNDER_INTERNAL','Founder','HARA_COMMANDER_GOVERNED_INVOKE','NONE',NULL,'ACTIVE');
    `);
    db.exec(fs.readFileSync(new URL("../migrations/0036_commander_prelaunch_commercial_terms.sql", import.meta.url), "utf8"));
    const entitlement = db.prepare("INSERT INTO entitlements VALUES (?,?,'ACTIVE',?,NULL)");
    entitlement.run("A", "TRIAL", AT);
    entitlement.run("B", "STANDARD", AT);
    entitlement.run("F", "FOUNDER_INTERNAL", AT);
    const pairing = db.prepare("INSERT INTO device_pairing_tokens VALUES (?,?,?,?,NULL,NULL,?)");
    const token = (tenant, n) => `${tenant}-${n}`;
    const addPair = (tenant, n) => pairing.run(token(tenant, n), token(tenant, n), tenant, "S-" + tenant, AFTER);
    const count = tenant => Number(db.prepare("SELECT COUNT(*) AS n FROM commander_devices WHERE tenant_id=? AND state='ACTIVE' AND revoked_at_utc IS NULL").get(tenant).n);

    for (let n = 1; n <= 5; n++) {
      addPair("A", n);
      assert.equal(attempt(db, token("A", n), `A-${n}`), "ENROLLED");
    }
    assert.equal(count("A"), 5);
    addPair("A", 6);
    assert.equal(attempt(db, token("A", 6), "A-6"), "DEVICE_LIMIT_REACHED");
    assert.equal(db.prepare("SELECT consumed_at_utc FROM device_pairing_tokens WHERE pairing_id=?").get(token("A", 6)).consumed_at_utc, null);
    db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id='A-5'").run(AT);
    assert.equal(attempt(db, token("A", 6), "A-6"), "ENROLLED");
    assert.equal(count("A"), 5);
    assert.equal(attempt(db, token("A", 6), "A-replay"), "DEVICE_PAIRING_INVALID");
    console.log("DEVICE_LIMIT_FIFTH_SIXTH_REVOKE_REPLACE=PASS");

    for (let n = 1; n <= 5; n++) {
      addPair("B", n);
      assert.equal(attempt(db, token("B", n), `B-${n}`), "ENROLLED");
    }
    addPair("B", 6);
    assert.equal(attempt(db, token("B", 6), "B-6"), "DEVICE_LIMIT_REACHED");
    assert.equal(count("B"), 5);
    for (let n = 1; n <= 8; n++) {
      addPair("F", n);
      assert.equal(attempt(db, token("F", n), `F-${n}`), "ENROLLED");
    }
    assert.equal(count("F"), 8);
    console.log("DEVICE_LIMIT_TENANT_ISOLATION_AND_FOUNDER=PASS");

    db.prepare("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id='A-4'").run(AT);
    addPair("A", 7);
    addPair("A", 8);
    const racers = [7, 8].map(n => new Worker(new URL(import.meta.url), {
      workerData: { file, token: token("A", n), id: `A-${n}` },
    }));
    await Promise.all(racers.map(worker => new Promise((resolve, reject) => {
      worker.once("error", reject);
      worker.once("message", message => {
        if (message.ready) resolve();
        else reject(new Error("WORKER_READY_REQUIRED"));
      });
    })));
    const states = await Promise.all(racers.map(worker => new Promise((resolve, reject) => {
      worker.on("error", reject);
      worker.on("message", message => {
        if (message.error) reject(new Error(message.error));
        else resolve(message.state);
      });
      worker.postMessage("start");
    })));
    assert.deepEqual(states.sort(), ["DEVICE_LIMIT_REACHED", "ENROLLED"]);
    assert.equal(count("A"), 5);
    console.log("DEVICE_LIMIT_CONCURRENT_ENROLLMENT=PASS");
  } finally {
    db.close();
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}
