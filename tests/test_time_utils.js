/* Beijing time formatter regression test; run with: node tests/test_time_utils.js */
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "assets", "time-utils.js"), "utf8");

for (const zone of ["UTC", "Asia/Shanghai", "Asia/Tokyo"]) {
  process.env.TZ = zone;
  const vm = require("vm");
  const sandbox = { window: {}, Intl, Date };
  vm.runInNewContext(source, sandbox, { filename: "assets/time-utils.js" });
  const time = sandbox.window.InterviewForgeTime;
  const values = {
    main: time.formatDateTime("2026-09-16T12:00:00+00:00"),
    boundary: time.formatDateTime("2026-09-16T16:30:00+00:00"),
    naiveMinute: time.formatDateTime("2026-09-16T20:00"),
    naiveSecond: time.formatDateTime("2026-09-16T20:00:00"),
    naiveSpace: time.formatDateTime("2026-09-16 20:00:00"),
    businessDate: time.formatDate("2026-09-17")
  };
  assert.strictEqual(values.main, "2026/09/16 20:00", `${zone}: main instant`);
  assert.strictEqual(values.boundary, "2026/09/17 00:30", `${zone}: Beijing midnight boundary`);
  assert.strictEqual(values.naiveMinute, "2026/09/16 20:00", `${zone}: naive minute is Beijing time`);
  assert.strictEqual(values.naiveSecond, "2026/09/16 20:00", `${zone}: naive second is Beijing time`);
  assert.strictEqual(values.naiveSpace, "2026/09/16 20:00", `${zone}: naive space datetime is Beijing time`);
  assert.strictEqual(values.businessDate, "2026/09/17", `${zone}: business date`);
}

console.log("time-utils: UTC/Asia/Shanghai/Asia/Tokyo regression PASS");
