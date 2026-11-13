/* Pure output checkers shared by single-case and full-suite execution. */
(function (root) {
  'use strict';
  function normalize(value) {
    return String(value == null ? '' : value).replace(/\r\n?/g, '\n')
      .split('\n').map(function (line) { return line.replace(/[ \t]+$/g, ''); })
      .join('\n').replace(/\n+$/g, '');
  }
  function tokens(value) { return String(value).trim().match(/\S+/g) || []; }
  function floatTokens(value) {
    // Keep punctuation while separating numbers from brackets/semicolons.
    // NumPy's padding before ']' is presentation, not a different value.
    return String(value).match(/[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[A-Za-z_]\w*|[^\s]/g) || [];
  }
  function close(a, b, spec) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
    var absolute = spec.abs_tol == null ? 0 : spec.abs_tol;
    var relative = spec.rel_tol == null ? 0 : spec.rel_tol;
    return Math.abs(a - b) <= absolute + relative * Math.abs(b);
  }
  function sameJson(a, b, spec) {
    if (typeof a === 'number' && typeof b === 'number') return close(a, b, spec);
    if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return a === b;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    var keys = Object.keys(b);
    return Object.keys(a).length === keys.length && keys.every(function (key) {
      return Object.prototype.hasOwnProperty.call(a, key) && sameJson(a[key], b[key], spec);
    });
  }
  function semantic(actual, mode, input) {
    var data = tokens(input || '');
    if (!data.every(function (s) { return /^\d+$/.test(s); })) return null;
    if (mode === 'max-digit-sum') {
      var cases = Number(data[0]), answers = tokens(actual);
      if (!Number.isSafeInteger(cases) || cases < 1 || data.length !== cases + 1) return null;
      if (answers.length !== cases) return false;
      return data.slice(1).every(function (x, index) {
        var y = answers[index];
        if (!/^\d+$/.test(y)) return false;
        y = y.replace(/^0+(?=\d)/, '');
        x = x.replace(/^0+(?=\d)/, '');
        if (y.length > x.length || (y.length === x.length && y >= x)) return false;
        var prefix = 0, best = -1;
        for (var at = 0; at < x.length; at++) {
          var digit = Number(x[at]);
          if (digit) best = Math.max(best, prefix + digit - 1 + 9 * (x.length - at - 1));
          prefix += digit;
        }
        return y.split('').reduce(function (sum, digit) { return sum + Number(digit); }, 0) === best;
      });
    }
    var n = Number(data[0]);
    if (!Number.isSafeInteger(n) || n < 1 || n > 1000000) return null;
    if (mode === 'window-distinct') {
      var distance = Number(data[1]);
      if (!Number.isSafeInteger(distance) || distance < 1 || distance > n || data.length !== n + 2) return null;
      var counts = new Map();
      data.slice(2).forEach(function (s) { var value = Number(s); counts.set(value, (counts.get(value) || 0) + 1); });
      var peak = Array.from(counts.values()).reduce(function (best, count) { return Math.max(best, count); }, 0);
      var tied = Array.from(counts.values()).filter(function (count) { return count === peak; }).length;
      var outputValues = tokens(actual);
      if (outputValues.length === 1 && outputValues[0] === '-1') return (peak - 1) * distance + tied > n;
      if (outputValues.length !== n) return false;
      var last = new Map();
      return outputValues.every(function (s, index) {
        if (!/^\d+$/.test(s)) return false;
        var value = Number(s);
        if (!counts.get(value) || (last.has(value) && index - last.get(value) < distance)) return false;
        counts.set(value, counts.get(value) - 1); last.set(value, index); return true;
      });
    }
    if (mode === 'balanced-intervals') {
      var count = Number(data[1]);
      if (!Number.isSafeInteger(count) || count < 0 || data.length !== 2 + 2 * count) return null;
      var output = String(actual).trim();
      if (output.length !== n || !/^[01]+$/.test(output)) return false;
      var prefix = new Int32Array(n + 1);
      for (var i = 0; i < n; i++) prefix[i + 1] = prefix[i] + (output[i] === '1' ? 1 : -1);
      for (var j = 0; j < count; j++) {
        var left = Number(data[2 + 2 * j]), right = Number(data[3 + 2 * j]);
        if (left < 1 || right > n || right < left || (right - left + 1) % 2) return null;
        if (prefix[right] !== prefix[left - 1]) return false;
      }
      return true;
    }
    if (data.length !== 1) return null;
    var values = tokens(actual);
    if (values.length !== n + 1 || !values.every(function (s) { return /^\d+$/.test(s); })) return false;
    var used = new Uint8Array(n + 1), weights = [], sum = 0n;
    for (var k = 0; k < n; k++) {
      var value = Number(values[k + 1]);
      if (!Number.isSafeInteger(value) || value < 1 || value > n || used[value]) return false;
      used[value] = 1;
      var weight = (k + 1) * (n - k);
      weights.push(weight);
      sum += BigInt(value) * BigInt(weight);
    }
    weights.sort(function (a, b) { return a - b; });
    var optimum = weights.reduce(function (total, weight, index) { return total + BigInt(index + 1) * BigInt(weight); }, 0n);
    return sum === optimum && BigInt(values[0]) === optimum % 1000000007n;
  }
  function check(actual, expected, spec, input) {
    spec = spec || { mode: 'exact' };
    var mode = spec.mode || 'exact';
    if (mode === 'manual') return { verdict: 'review', message: spec.reason || '多解输出需人工核对' };
    var ok = false;
    if (['permutation-sum', 'balanced-intervals', 'window-distinct', 'max-digit-sum'].indexOf(mode) >= 0) {
      var result = semantic(actual, mode, input);
      if (result === null) return { verdict: 'review', message: '当前输入无法进行可靠的构造校验，请核对题意' };
      ok = result;
    } else if (mode === 'exact') ok = normalize(actual) === normalize(expected);
    else if (mode === 'json') {
      try { ok = sameJson(JSON.parse(actual), JSON.parse(expected), spec); }
      catch (_) { ok = false; }
    } else if (mode === 'tokens' || mode === 'float') {
      var left = mode === 'float' ? floatTokens(actual) : tokens(actual);
      var right = mode === 'float' ? floatTokens(expected) : tokens(expected);
      var numeric = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
      ok = left.length === right.length && right.every(function (value, index) {
        if (mode === 'tokens' || !numeric.test(value)) return left[index] === value;
        return numeric.test(left[index]) && close(Number(left[index]), Number(value), spec);
      });
    } else return { verdict: 'review', message: '未配置可靠的输出校验方式' };
    return { verdict: ok ? 'pass' : 'fail', message: ok ? '输出符合用例' : '输出与期望不符' };
  }
  var api = { check: check, normalize: normalize };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.InterviewForgePracticeChecker = api;
})(typeof window !== 'undefined' ? window : globalThis);
