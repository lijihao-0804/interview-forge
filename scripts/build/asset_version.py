"""Single source of truth for generated static asset cache versions."""

# Increment this value whenever generated pages reference changed CSS/JS.
# The service worker has its own JavaScript constant because it cannot import
# Python, but the two values intentionally share the same release date.
ASSET_VERSION = "20261031-glossary-audit"
SITE_JS_VERSION = "20261014-code-block-visibility"
SERVICE_WORKER_VERSION = "hot100-v14-20261031"
