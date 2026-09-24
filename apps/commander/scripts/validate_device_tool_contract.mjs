#!/usr/bin/env node
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import {
  DEVICE_FUNCTION_ID,
  canonicalDeviceToolPayload,
} from "../src/device-tool-contract.mjs";

function need(ok, code) {
  if (!ok) throw new Error("COMMANDER_DEVICE_TOOL_CONTRACT_" + code + "=FAIL");
  console.log("COMMANDER_DEVICE_TOOL_CONTRACT_" + code + "=PASS");
}

function expectError(label, expectedCode, fn) {
  try {
    fn();
  } catch (error) {
    need(error instanceof Error && error.message === expectedCode, label);
    return;
  }
  throw new Error("COMMANDER_DEVICE_TOOL_CONTRACT_" + label + "=FAIL_ALLOWED");
}

need(DEVICE_FUNCTION_ID === "device.info", "FUNCTION_ID");
need(
  JSON.stringify(canonicalDeviceToolPayload("hara.health", {})) === "{}",
  "HEALTH_EMPTY_PAYLOAD",
);
need(
  JSON.stringify(canonicalDeviceToolPayload("hara.functions.list", {})) === "{}",
  "LIST_EMPTY_PAYLOAD",
);
need(
  canonicalDeviceToolPayload("hara.functions.describe", {
    function_id: "device.info",
  }).function_id === "device.info",
  "DESCRIBE_CANONICAL",
);

const invokePayload = canonicalDeviceToolPayload("hara.functions.invoke", {
  function_id: "device.info",
  arguments: { argv: [] },
});
need(
  invokePayload.function_id === "device.info"
    && Array.isArray(invokePayload.arguments.argv)
    && invokePayload.arguments.argv.length === 0,
  "INVOKE_CANONICAL",
);

const receipt = canonicalDeviceToolPayload("hara.receipts.get", {
  receipt_id_or_sha256: "A".repeat(64),
});
need(
  receipt.receipt_id_or_sha256 === "a".repeat(64),
  "RECEIPT_CANONICAL",
);

expectError(
  "UNKNOWN_TOOL_DENIED",
  "DEVICE_CALL_TOOL_DENIED",
  () => canonicalDeviceToolPayload("shell.run", {}),
);
expectError(
  "HEALTH_EXTRA_DENIED",
  "DEVICE_CALL_PAYLOAD_INVALID",
  () => canonicalDeviceToolPayload("hara.health", { extra: true }),
);
expectError(
  "LIST_EXTRA_DENIED",
  "DEVICE_CALL_PAYLOAD_INVALID",
  () => canonicalDeviceToolPayload("hara.functions.list", { extra: true }),
);
expectError(
  "DESCRIBE_WRONG_FUNCTION_DENIED",
  "DEVICE_CALL_FUNCTION_DENIED",
  () => canonicalDeviceToolPayload("hara.functions.describe", {
    function_id: "shell.run",
  }),
);
expectError(
  "DESCRIBE_EXTRA_DENIED",
  "DEVICE_CALL_PAYLOAD_INVALID",
  () => canonicalDeviceToolPayload("hara.functions.describe", {
    function_id: "device.info",
    extra: true,
  }),
);
expectError(
  "INVOKE_WRONG_FUNCTION_DENIED",
  "DEVICE_CALL_FUNCTION_DENIED",
  () => canonicalDeviceToolPayload("hara.functions.invoke", {
    function_id: "shell.run",
    arguments: { argv: [] },
  }),
);
expectError(
  "INVOKE_ARGV_DENIED",
  "DEVICE_CALL_PAYLOAD_INVALID",
  () => canonicalDeviceToolPayload("hara.functions.invoke", {
    function_id: "device.info",
    arguments: { argv: ["whoami"] },
  }),
);
expectError(
  "INVOKE_EXTRA_DENIED",
  "DEVICE_CALL_PAYLOAD_INVALID",
  () => canonicalDeviceToolPayload("hara.functions.invoke", {
    function_id: "device.info",
    arguments: { argv: [] },
    extra: true,
  }),
);
expectError(
  "RECEIPT_INVALID_DENIED",
  "DEVICE_CALL_RECEIPT_INVALID",
  () => canonicalDeviceToolPayload("hara.receipts.get", {
    receipt_id_or_sha256: "not-a-receipt",
  }),
);
expectError(
  "RECEIPT_EXTRA_DENIED",
  "DEVICE_CALL_PAYLOAD_INVALID",
  () => canonicalDeviceToolPayload("hara.receipts.get", {
    receipt_id_or_sha256: "a".repeat(64),
    extra: true,
  }),
);

const scriptDir = fileURLToPath(new URL(".", import.meta.url));
const worker = fs.readFileSync(
  new URL("../src/worker.js", import.meta.url),
  "utf8",
);
need(
  worker.includes("canonicalDeviceToolPayload(toolId, body.payload)"),
  "WORKER_ENQUEUE_GUARD",
);
need(
  worker.includes("if (functionId !== DEVICE_FUNCTION_ID)")
    && worker.indexOf("if (functionId !== DEVICE_FUNCTION_ID)")
      < worker.indexOf(".reserve(requestId, context.subject_id"),
  "QUOTA_FUNCTION_GUARD_BEFORE_RESERVE",
);

console.log("COMMANDER_DEVICE_TOOL_CONTRACT=PASS");
