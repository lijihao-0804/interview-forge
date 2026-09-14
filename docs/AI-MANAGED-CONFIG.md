# Managed AI configuration

InterviewForge now supports a project-level managed AI configuration database at
`data/ai_config.db`. It is separate from `auth.db` and every user learning
database. The database is ignored by Git and is created lazily.

## Security boundary

Provider API keys are encrypted with authenticated encryption before they are
written to SQLite. Deployments that save a key must set
`INTERVIEW_FORGE_AI_CONFIG_KEY` to a stable secret. If the variable is missing
or changed while encrypted providers exist, the provider remains visible only
as unavailable; the application does not generate a replacement key.

The management API only returns `key_configured` and a short safe hint. There is
no endpoint or UI action that reads the complete key back. Omitting `api_key`
on update preserves the existing key; replacing it requires a new value and
clearing it requires `clear_api_key: true`.

## Configuration layers

The resolver chooses an enabled business profile (`chat`,
`learning_analysis`, or `memory_extraction`) and its Provider/Model first. If
no enabled profile exists, the existing `AI_*` environment variables remain the
fallback, so an ENV-only deployment keeps its previous behavior.

The initial provider protocols are `openai_chat` and `openai_responses`. The
preset registry covers OpenAI, DeepSeek, OpenRouter, SiliconFlow, Kimi,
Qwen-compatible, GLM-compatible, New API, Sub2API and custom
OpenAI-compatible endpoints. Model discovery only consumes a bounded
`GET /models` response; it never makes a paid generation request.

## Admin API

All endpoints below require the existing administrator session:

* `GET /api/admin/ai/provider-presets`
* `GET/POST /api/admin/ai/providers`
* `PUT/DELETE /api/admin/ai/providers/{id}`
* `POST /api/admin/ai/providers/{id}/test`
* `POST /api/admin/ai/providers/{id}/discover-models`
* `GET/POST /api/admin/ai/providers/{id}/models`
* `GET /api/admin/ai/business-profiles`
* `PUT /api/admin/ai/business-profiles/{business_key}`

Provider probes have bounded timeouts, do not follow redirects, cap response
size and model count, and return only an error category rather than upstream
response content.

## Reasoning policy

Business profiles use the provider-neutral modes `off`, `auto`, `effort`, and
`budget`. Unknown model capabilities are conservative: `auto` is accepted,
but explicit reasoning settings require a declared capability or a manual
capability override.

## Rollback

Deleting/ignoring the managed database returns runtime resolution to ENV
configuration. Do not commit `data/ai_config.db` or any deployment secret.
