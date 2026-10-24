import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import vm from "node:vm";

const source = readFileSync(new URL("../src/worker.js", import.meta.url), "utf8");
// Exercise the actual response helpers without importing Worker-only runtime
// bindings or substituting a second implementation.
const headersStart = source.indexOf("const SECURITY_HEADERS =");
const helpersEnd = source.indexOf("function rateLimitedJson(", headersStart);
assert(headersStart >= 0 && helpersEnd > headersStart);
const context = vm.createContext({ Response });
vm.runInContext(source.slice(headersStart, helpersEnd), context);
const publicJson = vm.runInContext("json", context);
const privateJson = vm.runInContext("internalJson", context);
const expectedOriginal = "H.A.R.A. Commander 0.3.49\nHomologação Windows: ação aprovada.\nEtapa: escrita inicial\n";
const samples = [
  ["ascii", "plain ASCII\nexact LF\n"],
  ["accents", expectedOriginal],
  ["emoji_cjk", "UTF8 🚀 日本 €\n"],
];
let assertions = 0;
function check(value, message) { assert(value, message); assertions += 1; }
const sha = bytes => createHash("sha256").update(bytes).digest("hex");
for (const [helperName, helper] of [["public", publicJson], ["internal", privateJson]]) {
  for (const [name, text] of samples) {
    const label = helperName + "/" + name;
    const payload = { arguments: { content: text } };
    const response = helper(payload, 201);
    check(response.status === 201, label + ": status");
    const contentType = response.headers.get("content-type");
    check(/^application\/json;\s*charset=utf-8$/i.test(contentType), label + ": explicit UTF8 charset");
    check(response.headers.get("cache-control") === "no-store", label + ": cache guard");
    check(response.headers.get("x-content-type-options") === "nosniff", label + ": sniff guard");
    const actualBytes = Buffer.from(await response.arrayBuffer());
    const expectedBytes = Buffer.from(JSON.stringify(payload), "utf8");
    check(actualBytes.equals(expectedBytes), label + ": exact wire bytes");
    const decoded = JSON.parse(actualBytes.toString("utf8"));
    check(decoded.arguments.content === text, label + ": exact Unicode text");
  }
}
const defaultJson = Response.json({ arguments: { content: expectedOriginal } });
check(defaultJson.headers.get("content-type") === "application/json", "regression control: default Response.json omits charset");
const latin1Decoded = JSON.parse(Buffer.from(await defaultJson.arrayBuffer()).toString("latin1"));
const corruptedFile = Buffer.from(latin1Decoded.arguments.content, "utf8");
check(Buffer.byteLength(expectedOriginal, "utf8") === 89, "original input has 89 bytes");
check(sha(Buffer.from(expectedOriginal, "utf8")) === "d2db30144965bb9c1e6fb0674af17e2099908f4d115f52b137face8f64a98655", "original expected SHA");
check(corruptedFile.length === 97, "Latin1 misdecode reproduces observed 97 bytes");
check(sha(corruptedFile) === "426adfb6fb5153082316592e27f758dfb5afa29c5767a517193b850bcc58b6c1", "Latin1 misdecode reproduces exact observed SHA");
const fixedResponse = publicJson({ arguments: { content: expectedOriginal } });
const fixedBytes = Buffer.from(await fixedResponse.arrayBuffer());
const received = JSON.parse(fixedBytes.toString("utf8")).arguments.content;
check(Buffer.from(received, "utf8").equals(Buffer.from(expectedOriginal, "utf8")), "independent expected bytes survive corrected response");
check(source.includes('return json(call);'), "calls/next uses tested public helper");
console.log(JSON.stringify({
  schema: "hara.commander.json-utf8-response-test.v1",
  state: "PASS",
  assertions,
  corpus: samples.map(([name]) => name),
  observed_corruption_sha256: sha(corruptedFile),
  expected_file_sha256: sha(Buffer.from(expectedOriginal, "utf8")),
  production_mutation: false,
}));
