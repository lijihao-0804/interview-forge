import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class NavigationPolicyTests(unittest.TestCase):
    def test_policy_runtime_modes_and_preference_persistence(self):
        policy_path = (ROOT / "assets" / "navigation-policy.js").as_posix()
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const store = new Map();
function makeSandbox(matchMedia) {
  return {
    URL,
    matchMedia,
    localStorage: { getItem: key => store.has(key) ? store.get(key) : null,
      setItem: (key, value) => store.set(key, String(value)) },
    location: { origin: 'http://localhost:8765' },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    document: { baseURI: 'http://localhost:8765/cockpit.html', documentElement: {},
      querySelectorAll: () => [], addEventListener: () => {} },
    window: { addEventListener: () => {} }
  };
}
const desktopSandbox = makeSandbox(undefined);
vm.runInNewContext(source, desktopSandbox, { filename: 'navigation-policy.js' });
const policy = desktopSandbox.window.ForgeNavigationPolicy;
if (!policy) throw new Error('policy not exposed');
if (policy.key !== 'learningContentOpenMode') throw new Error('preference key');
if (policy.getPreference() !== 'new-tab') throw new Error('default preference');
if (policy.resolveNavigationMode('same-tab', 'new-tab') !== 'same-tab') throw new Error('same-tab override');
if (policy.resolveNavigationMode('user-preference', 'new-tab') !== 'new-tab') throw new Error('new-tab preference');
policy.setPreference('same-tab');
if (policy.getPreference() !== 'same-tab') throw new Error('persisted preference');
if (policy.resolveNavigationMode('user-preference', policy.getPreference()) !== 'same-tab') throw new Error('same-tab preference');

// 移动/触屏默认同页打开（触屏没有中键/Ctrl，新标签无选择权）
store.clear();
const coarse = q => ({ matches: q.indexOf('pointer:coarse') >= 0 || q.indexOf('max-width:760px') >= 0 });
const mobileSandbox = makeSandbox(coarse);
vm.runInNewContext(source, mobileSandbox, { filename: 'navigation-policy.js' });
if (mobileSandbox.window.ForgeNavigationPolicy.getPreference() !== 'same-tab') throw new Error('mobile default same-tab');

function anchor(href, attrs, classes) {
  const data = Object.assign({ href }, attrs || {});
  return {
    href,
    matches: selector => selector.indexOf('.problem-nav-btn') >= 0 && (classes || []).includes('problem-nav-btn'),
    hasAttribute: name => Object.prototype.hasOwnProperty.call(data, name),
    getAttribute: name => data[name] == null ? null : data[name],
    setAttribute: (name, value) => { data[name] = String(value); },
    removeAttribute: name => { delete data[name]; },
    attr: data
  };
}
function applyWith(policyApi, one) { policyApi.apply({ querySelectorAll: () => [one] }); return one; }
const external = applyWith(policy, anchor('https://example.com/a'));
if (external.attr.target !== '_blank' || external.attr.rel !== 'noopener noreferrer') throw new Error('external safety');
const continuous = applyWith(policy, anchor('/books/hot100/next.html', { target: '_blank', rel: 'noopener noreferrer' }, ['problem-nav-btn']));
if ('target' in continuous.attr || 'rel' in continuous.attr) throw new Error('continuous must stay same-tab');
policy.setPreference('new-tab');
const independent = applyWith(policy, anchor('/books/hot100/one.html', { 'data-navigation-policy': 'user-preference' }, []));
if (independent.attr.target !== '_blank' || independent.attr.rel !== 'noopener noreferrer') throw new Error('default independent mode');
policy.setPreference('same-tab');
const independentSame = applyWith(policy, anchor('/books/hot100/one.html', { 'data-navigation-policy': 'user-preference' }, []));
if ('target' in independentSame.attr || 'rel' in independentSame.attr) throw new Error('same-tab independent mode');
process.stdout.write(JSON.stringify({ ok: true }));
"""
        result = subprocess.run(
            ["node", "-e", script, policy_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(json.loads(result.stdout), {"ok": True})

    def test_policy_is_loaded_and_does_not_intercept_native_navigation(self):
        policy = (ROOT / "assets" / "navigation-policy.js").read_text(encoding="utf-8")
        study_server = (ROOT / "tools" / "study_server.py").read_text(encoding="utf-8")
        self.assertIn('"/assets/navigation-policy.js?v=2"', study_server)
        self.assertNotIn("preventDefault", policy)
        self.assertNotIn("window.open", policy)
        self.assertIn("MutationObserver", policy)
        self.assertIn("learningContentOpenMode", policy)

    def test_existing_continuous_and_primary_navigation_markers_are_present(self):
        cockpit = (ROOT / "cockpit.html").read_text(encoding="utf-8")
        dashboard = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="entry"', cockpit)
        self.assertIn('class="dashboard-nav"', dashboard)
        self.assertIn(".problem-nav-btn", (ROOT / "assets" / "navigation-policy.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
