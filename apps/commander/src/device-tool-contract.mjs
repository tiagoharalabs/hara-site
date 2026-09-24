export const DEVICE_FUNCTION_ID = "device.info";

function fail(code) {
  throw new Error(code);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expected) {
  if (!isObject(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length
    && actual.every((key, index) => key === wanted[index]);
}

function requireFunctionId(value) {
  if (typeof value !== "string" || value.trim() !== DEVICE_FUNCTION_ID) {
    fail("DEVICE_CALL_FUNCTION_DENIED");
  }
  return DEVICE_FUNCTION_ID;
}

export function canonicalDeviceToolPayload(toolId, payload) {
  const body = payload ?? {};
  if (!isObject(body)) fail("DEVICE_CALL_PAYLOAD_INVALID");

  if (toolId === "hara.health" || toolId === "hara.functions.list") {
    if (!exactKeys(body, [])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return {};
  }

  if (toolId === "hara.functions.describe") {
    if (!exactKeys(body, ["function_id"])) fail("DEVICE_CALL_PAYLOAD_INVALID");
    return { function_id: requireFunctionId(body.function_id) };
  }

  if (toolId === "hara.functions.invoke") {
    if (!exactKeys(body, ["function_id", "arguments"])) {
      fail("DEVICE_CALL_PAYLOAD_INVALID");
    }
    const functionId = requireFunctionId(body.function_id);
    const args = body.arguments;
    if (!exactKeys(args, ["argv"]) || !Array.isArray(args.argv) || args.argv.length !== 0) {
      fail("DEVICE_CALL_PAYLOAD_INVALID");
    }
    return { function_id: functionId, arguments: { argv: [] } };
  }

  if (toolId === "hara.receipts.get") {
    if (!exactKeys(body, ["receipt_id_or_sha256"])) {
      fail("DEVICE_CALL_PAYLOAD_INVALID");
    }
    const receipt = String(body.receipt_id_or_sha256 || "").trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(receipt)) {
      fail("DEVICE_CALL_RECEIPT_INVALID");
    }
    return { receipt_id_or_sha256: receipt };
  }

  fail("DEVICE_CALL_TOOL_DENIED");
}
