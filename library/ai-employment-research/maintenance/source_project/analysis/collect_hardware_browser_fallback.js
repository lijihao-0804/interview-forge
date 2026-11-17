"use strict";

// Browser-context collection for official public endpoints that did not return
// usable list payloads to plain requests. A fresh headless Edge profile is used;
// this script performs no login, verification bypass, or signature reconstruction.
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.resolve(__dirname, "..", ".cache", "npm", "_npx",
  "31e32ef8478fbf80", "node_modules", "playwright"));

const ROOT = path.resolve(__dirname, "..");
const ARCHIVES = path.join(ROOT, "archives");
const HUAWEI_URL = "https://career.huawei.com/cn/social-recruitment-job-list";
const HUAWEI_API = "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/recruitmentPosition/pub/getJobPage";
const HUAWEI_ID = "app_000000035886";
const XIAOMI_URL = "https://hr.xiaomi.com/website/opportunities.html";
const XIAOMI_API = "https://hr.xiaomi.com/website/api/agent/searchJobPage";
const HONOR_SUITE = "5ff669649b0d78e6f4296c9a";
const HONOR_URL = `https://career.honor.com/SU${HONOR_SUITE}/pb/social.html#/`;
const HONOR_LIST = `https://career.honor.com/wecruit/positionInfo/listPosition/SU${HONOR_SUITE}`;
const HONOR_DETAIL = `https://career.honor.com/wecruit/positionInfo/listPositionDetail/SU${HONOR_SUITE}`;

function mkdir(folder) { fs.mkdirSync(folder, { recursive: true }); }
function writeJson(file, data) {
  mkdir(path.dirname(file));
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), "utf8");
  fs.renameSync(tmp, file);
}
function appendJsonl(file, data) {
  mkdir(path.dirname(file));
  fs.appendFileSync(file, JSON.stringify(data) + "\n", "utf8");
}
function timeIso() { return new Date().toISOString(); }
function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function fetchInPage(page, url, method = "GET", body = undefined, headers = {}) {
  return await page.evaluate(async ({ url, method, body, headers }) => {
    try {
      const response = await fetch(url, {
        method, body, headers, credentials: "same-origin", cache: "no-store",
      });
      const text = await response.text();
      let json = null;
      try { json = JSON.parse(text); } catch (_) {}
      return { httpStatus: response.status, ok: response.ok, responseUrl: response.url,
        contentType: response.headers.get("content-type"), text, json };
    } catch (error) {
      return { fetchError: `${error.name}: ${error.message}` };
    }
  }, { url, method, body, headers });
}

function writePageCapture(company, pageNo, capture, endpoint, requestParams, rows, reported, size) {
  const root = path.join(ARCHIVES, company);
  const rawPath = path.join(root, "pages", `page_${String(pageNo).padStart(4, "0")}.json`);
  writeJson(rawPath, capture.json);
  appendJsonl(path.join(root, "browser_capture_log.jsonl"), {
    page: pageNo, at: timeIso(), endpoint, request_params: requestParams,
    http_status: capture.httpStatus, content_type: capture.contentType,
    returned_rows: rows.length, reported_total: reported, page_size: size,
    raw_response_archive: path.relative(ROOT, rawPath).replaceAll("\\", "/"),
    capture_method: "anonymous Edge page-context fetch",
  });
}

async function collectHuawei(page) {
  const company = "huawei";
  await page.goto(HUAWEI_URL, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForFunction(() => document.body.innerText.includes("在招职位"), { timeout: 60000 });
  await delay(1200);
  const root = path.join(ARCHIVES, company);
  let total = 0, pages = 0, size = 100, fetched = 0;
  const rows = [];
  const failures = [];
  for (let currentPage = 1; currentPage <= 10000; currentPage++) {
    const params = new URLSearchParams({ "X-HW-ID": HUAWEI_ID });
    const body = { curPage: currentPage, pageSize: 10, jobType: "SR" };
    const capture = await fetchInPage(page, `${HUAWEI_API}?${params}`,
      "POST", JSON.stringify(body), {
        "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
        "X-HW-ID": HUAWEI_ID, "X-CSRF-Token": "", "X-Jalor-TenantAlias": "hcm",
        "X-Referer": "https://career.huawei.com/cn", "X-ALB-Gray": "prod", "X-Language": "zh_CN",
      });
    if (capture.fetchError || !capture.json || capture.httpStatus < 200 || capture.httpStatus >= 300 || capture.json.status !== "SUCCESS") {
      const err = { page: currentPage, at: timeIso(), fetch_error: capture.fetchError,
        http_status: capture.httpStatus, response_sample: (capture.text || "").slice(0, 1000),
        endpoint: HUAWEI_API, request_params: { ...body, "X-HW-ID": HUAWEI_ID },
        capture_method: "anonymous Edge page-context fetch" };
      failures.push(err); appendJsonl(path.join(root, "browser_capture_log.jsonl"), err); break;
    }
    const data = capture.json.data || {};
    const pageVO = data.pageVO || {};
    const pageRows = data.result || [];
    total = Number(pageVO.totalRows || total || 0);
    pages = Number(pageVO.totalPages || pages || 0);
    size = Number(pageVO.pageSize || size);
    writePageCapture(company, currentPage, capture, HUAWEI_API,
      { ...body, "X-HW-ID": HUAWEI_ID }, pageRows, total, size);
    rows.push(...pageRows); fetched += 1;
    if (currentPage >= pages || pageRows.length === 0) break;
    await delay(220);
  }
  return { company: "华为", reported_total: total, pages_expected: pages,
    pages_fetched: fetched, raw_rows: rows.length, unique_ids: new Set(rows.map(x => String(x.jobId || x.advertisementsIntegrationId || ""))).size,
    failures };
}

async function collectXiaomiSnapshot(page) {
  const company = "xiaomi";
  await page.goto(XIAOMI_URL, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForFunction(() => document.body.innerText.includes("个职位"), { timeout: 60000 });
  await delay(1200);
  const snapshotFolder = path.join(ARCHIVES, company, "snapshot_02");
  mkdir(path.join(snapshotFolder, "pages"));
  const logPath = path.join(snapshotFolder, "page_log.jsonl");
  if (fs.existsSync(logPath)) fs.unlinkSync(logPath);
  let total = 0, pages = 0, size = 100, fetched = 0;
  const rows = [];
  const failures = [];
  for (let pageNum = 1; pageNum <= 10000; pageNum++) {
    const url = `${XIAOMI_API}?${new URLSearchParams({ keyword: "", cityZhNames: "", pageSize: "100", pageNum: String(pageNum) })}`;
    const capture = await fetchInPage(page, url, "GET", undefined, { "Accept": "application/json, text/plain, */*" });
    if (capture.fetchError || !capture.json || capture.httpStatus < 200 || capture.httpStatus >= 300 || Number(capture.json.code) !== 0) {
      const err = { page: pageNum, at: timeIso(), fetch_error: capture.fetchError,
        http_status: capture.httpStatus, response_sample: (capture.text || "").slice(0, 1000), endpoint: url };
      failures.push(err); appendJsonl(logPath, err); break;
    }
    const data = capture.json.data || {};
    const pageRows = data.list || [];
    total = Number(data.total || total || 0);
    pages = Number(data.pageTotal || pages || 0);
    size = Number(data.pageSize || size);
    const rawPath = path.join(snapshotFolder, "pages", `page_${String(pageNum).padStart(4, "0")}.json`);
    writeJson(rawPath, capture.json);
    appendJsonl(logPath, { page: pageNum, at: timeIso(), endpoint: XIAOMI_API,
      request_params: { keyword: "", cityZhNames: "", pageSize: 100, pageNum },
      http_status: capture.httpStatus, returned_rows: pageRows.length, reported_total: total,
      page_size: size, raw_response_archive: path.relative(ROOT, rawPath).replaceAll("\\", "/"),
      capture_method: "anonymous Edge page-context fetch" });
    rows.push(...pageRows); fetched += 1;
    if (pageNum >= pages || pageRows.length === 0) break;
    await delay(220);
  }
  const ids = rows.map(x => String(x.jobPostId || x.jobId || x.id || ""));
  return { company: "小米", snapshot: "02", reported_total: total, pages_expected: pages,
    pages_fetched: fetched, raw_rows: rows.length, unique_ids: new Set(ids.filter(Boolean)).size,
    duplicate_rows: ids.filter(Boolean).length - new Set(ids.filter(Boolean)).size, failures };
}

async function honorListPage(page, currentPage, pageSize = 15) {
  const params = new URLSearchParams({ iSaJAx: "isAjax", request_locale: "zh_CN", t: String(Date.now()) });
  const body = new URLSearchParams({ isFrompb: "true", recruitType: "2",
    pageSize: String(pageSize), currentPage: String(currentPage) }).toString();
  const capture = await fetchInPage(page, `${HONOR_LIST}?${params}`, "POST", body,
    { "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json, text/plain, */*" });
  return { capture, body, params: Object.fromEntries(params.entries()) };
}

async function collectHonor(page) {
  const company = "honor";
  await page.goto(HONOR_URL, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForFunction(() => document.body.innerText.includes("在招职位"), { timeout: 60000 });
  await delay(1500);
  const root = path.join(ARCHIVES, company);
  const rows = [];
  const failures = [];
  let total = 0, pages = 0, pageSize = 15, fetched = 0;
  for (let currentPage = 1; currentPage <= 10000; currentPage++) {
    const { capture, body, params } = await honorListPage(page, currentPage, pageSize);
    if (capture.fetchError || !capture.json || capture.httpStatus < 200 || capture.httpStatus >= 300 || capture.json.state !== "200") {
      const err = { page: currentPage, at: timeIso(), fetch_error: capture.fetchError,
        http_status: capture.httpStatus, response_sample: (capture.text || "").slice(0, 1000),
        endpoint: HONOR_LIST, request_params: { ...params, body },
        capture_method: "anonymous Edge page-context fetch" };
      failures.push(err); appendJsonl(path.join(root, "browser_capture_log.jsonl"), err); break;
    }
    const data = capture.json.data || {};
    const form = data.pageForm || {};
    const pageRows = form.pageData || [];
    total = Number(data.dataCount || total || 0);
    pages = Number(form.totalPage || pages || 0);
    pageSize = Number(form.pageSize || pageSize);
    writePageCapture(company, currentPage, capture, HONOR_LIST,
      { ...params, body }, pageRows, total, pageSize);
    rows.push(...pageRows); fetched += 1;
    if (currentPage >= pages || pageRows.length === 0) break;
    await delay(220);
  }
  const detailFailures = [];
  const detailLog = path.join(root, "browser_detail_capture_log.jsonl");
  let index = 0, success = 0;
  async function worker() {
    while (true) {
      const position = index++;
      if (position >= rows.length) return;
      const row = rows[position];
      const postId = String(row.postId || "");
      if (!postId) {
        const err = { post_id: "", detail_status: "failed", error: "list row lacks postId", at: timeIso() };
        detailFailures.push(err); appendJsonl(detailLog, err); continue;
      }
      const fileName = postId.replace(/[^A-Za-z0-9_-]/g, "_") + ".json";
      const rawPath = path.join(root, "details", fileName);
      try {
        let payload = null, lastError = null;
        for (let attempt = 1; attempt <= 3; attempt++) {
          const params = new URLSearchParams({ iSaJAx: "isAjax", request_locale: "zh_CN", t: String(Date.now()) });
          const body = new URLSearchParams({ postId, recruitType: "2" }).toString();
          const capture = await fetchInPage(page, `${HONOR_DETAIL}?${params}`, "POST", body,
            { "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json, text/plain, */*" });
          if (!capture.fetchError && capture.json && capture.httpStatus >= 200 && capture.httpStatus < 300 &&
              capture.json.state === "200" && capture.json.type === "success") {
            payload = capture.json;
            writeJson(rawPath, payload);
            success += 1;
            appendJsonl(detailLog, { post_id: postId, attempt, at: timeIso(), http_status: capture.httpStatus,
              detail_status: "retrieved", raw_detail_archive: path.relative(ROOT, rawPath).replaceAll("\\", "/"),
              capture_method: "anonymous Edge page-context fetch" });
            lastError = null;
            break;
          }
          lastError = { fetch_error: capture.fetchError, http_status: capture.httpStatus,
            response_sample: (capture.text || "").slice(0, 400) };
          await delay(500 * attempt);
        }
        if (!payload) {
          const err = { post_id: postId, detail_status: "failed", error: lastError, at: timeIso() };
          detailFailures.push(err); appendJsonl(detailLog, err);
        }
      } catch (error) {
        const err = { post_id: postId, detail_status: "failed", error: `${error.name}: ${error.message}`, at: timeIso() };
        detailFailures.push(err); appendJsonl(detailLog, err);
      }
      await delay(250);
    }
  }
  await Promise.all([worker(), worker(), worker()]);
  const ids = rows.map(x => String(x.postId || ""));
  return { company: "荣耀", reported_total: total, pages_expected: pages,
    pages_fetched: fetched, raw_rows: rows.length, unique_ids: new Set(ids.filter(Boolean)).size,
    detail_attempted: rows.length, detail_success: success, detail_failures: detailFailures,
    list_failures: failures };
}

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true,
    args: ["--disable-gpu"] });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(90000);
  page.setDefaultNavigationTimeout(90000);
  const results = [];
  try {
    results.push(await collectHuawei(page));
    results.push(await collectXiaomiSnapshot(page));
    results.push(await collectHonor(page));
  } finally {
    await context.close();
    await browser.close();
  }
  const report = { started_at: timeIso(), method: "anonymous public APIs fetched from fresh headless Edge page contexts",
    results };
  writeJson(path.join(ARCHIVES, "browser_fallback_run.json"), report);
  process.stdout.write(JSON.stringify(report) + "\n");
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
