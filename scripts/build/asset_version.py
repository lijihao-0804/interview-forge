"""Single source of truth for generated static asset cache versions."""

# Increment this value whenever generated pages reference changed CSS/JS.
# The service worker has its own JavaScript constant because it cannot import
# Python, but the two values intentionally share the same release date.
ASSET_VERSION = "20260929-study-ux"
SERVICE_WORKER_VERSION = "hot100-v11-20260929"
