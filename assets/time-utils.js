(function (global) {
  "use strict";

  var TIME_ZONE = "Asia/Shanghai";
  var DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
  var WEEKDAYS = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  var cache = Object.create(null);
  var partsFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE, year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", second: "numeric", weekday: "short", hourCycle: "h23"
  });

  function dateOnly(value) {
    var match = DATE_ONLY_RE.exec(String(value == null ? "" : value).trim());
    return match ? { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) } : null;
  }
  function instant(value) {
    if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
    if (typeof value === "number") { var numeric = new Date(value); return isNaN(numeric.getTime()) ? null : numeric; }
    var text = String(value == null ? "" : value).trim();
    if (!text || DATE_ONLY_RE.test(text)) return null;
    var parsed = new Date(text.replace(" ", "T"));
    return isNaN(parsed.getTime()) ? null : parsed;
  }
  function formatter(options) {
    var merged = Object.assign({}, options || {}, { timeZone: TIME_ZONE });
    var key = JSON.stringify(merged);
    if (!cache[key]) cache[key] = new Intl.DateTimeFormat("zh-CN", merged);
    return cache[key];
  }
  function weekdayForDate(value) {
    var date = dateOnly(value);
    if (!date) return null;
    return new Date(Date.UTC(date.year, date.month - 1, date.day, 12)).getUTCDay();
  }
  function parts(value) {
    var businessDate = dateOnly(value);
    if (businessDate) return Object.assign(businessDate, { hour: 0, minute: 0, second: 0, weekday: weekdayForDate(value) });
    var date = instant(value);
    if (!date) return null;
    var values = { weekday: 0 };
    partsFormatter.formatToParts(date).forEach(function (item) {
      if (item.type === "weekday") values.weekday = WEEKDAYS[item.value] == null ? 0 : WEEKDAYS[item.value];
      else if (item.type !== "literal") values[item.type] = Number(item.value);
    });
    return values;
  }
  function formatDate(value, options) {
    var businessDate = dateOnly(value);
    if (businessDate) return formatter(Object.assign({ year: "numeric", month: "2-digit", day: "2-digit" }, options || {})).format(new Date(Date.UTC(businessDate.year, businessDate.month - 1, businessDate.day, 12)));
    var date = instant(value);
    return date ? formatter(Object.assign({ year: "numeric", month: "2-digit", day: "2-digit" }, options || {})).format(date) : "—";
  }
  function formatTime(value, options) {
    var date = instant(value);
    return date ? formatter(Object.assign({ hour: "2-digit", minute: "2-digit", hour12: false, hourCycle: "h23" }, options || {})).format(date) : "—";
  }
  function formatDateTime(value, options) {
    var date = instant(value);
    if (!date) return dateOnly(value) ? formatDate(value, options) : "—";
    return formatter(Object.assign({ year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, hourCycle: "h23" }, options || {})).format(date);
  }
  global.InterviewForgeTime = {
    timeZone: TIME_ZONE,
    formatDateTime: formatDateTime,
    formatTime: formatTime,
    formatDate: formatDate,
    nowParts: function () { return parts(new Date()); },
    parts: parts,
    weekdayForDate: weekdayForDate
  };
}(window));
