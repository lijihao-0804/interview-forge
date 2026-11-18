"""Single source of truth for generated static asset cache versions."""

# Increment this value whenever generated pages reference changed CSS/JS.
# The service worker has its own JavaScript constant because it cannot import
# Python, but the two values intentionally share the same release date.
ASSET_VERSION = "20261112-guest-python"
SITE_CSS_VERSION = "20261118-reader-layout"
SOLUTION_PROGRESS_VERSION = "20261118-reader-progress"
SITE_JS_VERSION = "20261118-code-wrap"
DELIVERED_ASSET_VERSIONS = {
    "site.css": SITE_CSS_VERSION,
    "site.js": SITE_JS_VERSION,
    "solution-progress.js": SOLUTION_PROGRESS_VERSION,
    "auth-widget.js": "9",
    "feedback-widget.js": "6",
    "guest-auth.js": "3",
    "ai-launcher.js": "5",
    "shelf-filters.js": "3",
}
SERVICE_WORKER_VERSION = "hot100-v47-20261118-embedded-navigation"
