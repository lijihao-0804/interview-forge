# Account security rollout review

This change is a separate account feature release. Do not enable it as part of a
content-only update. Tests use synthetic accounts and mocked mail delivery.

## Three compatible identity tiers

The database and legacy JSON `role` remain `user`/`admin`. Server-derived
`effective_role` is `user`, `admin`, or `super_admin`; `role_label` is 用户,
管理员, or 超级管理员. `core.roles` is the authority: only the exact configured
permanent-admin username, with an active account and an actual `admin` database
role, qualifies as `super_admin`. Missing configuration, missing active status,
client fields, forged cookies and a stored/custom `super_admin` role do not qualify.
Old clients checking `role == admin` retain the same administrator functionality.

The initializer no longer promotes an account based on its configured name.
No account, role, or service configuration is changed by adding these labels.
Ordinary administrators retain existing management permissions but cannot modify
the reserved administrator's role, password, nickname, or active status, and cannot
access any private teaching resource. Normal public registration always creates
a user. There is no endpoint for granting `super_admin`.

Before activation, verify the configured permanent administrator is already active
and has the database admin role, without printing the identity. A missing or
inconsistent account is a deployment gate; do not repair/elevate it automatically.

## User-visible behavior

| Situation | Behavior |
|---|---|
| Guest | Existing public reading/search stay public; favorites, history and account settings still require sign-in. |
| Registration | A normalized email address and purpose-scoped six-digit code are required; reserved permanent-admin usernames cannot self-register. |
| Login | Exact username, an unambiguous case variant, or the bound email address can authenticate. A legacy case-colliding username fails closed, including when an email is used. Disabled accounts remain blocked. |
| Existing account with no email | Username/password and existing valid sessions still work. Sign in and bind an address using the current password plus an emailed code before using email login/recovery. No email is inferred or backfilled. |
| Password recovery | Unknown addresses receive the same generic acknowledgement. A valid reset code changes the password and revokes all that account's sessions. Without a bound email, recovery requires the existing administrator support process; this release adds no bypass. |
| Email change | Requires a signed-in account, current password and a code bound to that account and purpose. Another account's address cannot be taken. |
| Private teaching site | Every resource still requires the configured permanent administrator. An ordinary administrator remains forbidden. This feature does not create or elevate identities. |

## Turnstile configuration

Both keys absent explicitly disables the optional check. Both keys present enables
server-side validation. Either key alone returns `503 captcha_unavailable` from
configuration and anonymous code-send endpoints, before quota reservation or mail
delivery. A failed verification provider also fails closed. Public forms display a
service-unavailable message and disable code sending when configuration cannot be
confirmed; they do not interpret an HTTP error as a disabled check. Existing login,
public reading and already-issued code redemption remain available.

No real key, provider call or SMTP send is required for offline tests. Live provider
and mail-delivery verification requires a separately approved deployment check.

Recovery requests reserve the same SQLite quota for every normalized recipient,
then queue delivery on the email worker pool. The public acknowledgement does not
wait for account lookup or SMTP and does not disclose whether delivery succeeded.
Known and unknown addresses therefore have identical response bodies/statuses even
when SMTP is unavailable. CAPTCHA and quota failures still fail closed before
delivery. Queued requests are not durable across restarts; after the existing
cooldown the user can request a fresh code. Stop all workers, including delivery
workers, before migration or rollback.

Anonymous search keeps the deployed cross-process SQLite limits; this release does
not adopt the earlier WIP's per-process counters. Known-route wrong-method requests
return 405 with Allow; valid private operations retain their authentication gates.

## Database upgrade

Stop all writers and take a consistent SQLite backup of the current auth database
outside every web root. Preserve per-user study databases separately; this change
does not migrate or rewrite them. Retain the prior application SHA and service
configuration. Do not run an old worker and a new worker against the same database.

The upgrade adds recipient-domain and purpose fields to send attempts, and purpose
and account fields to codes. Existing rows default to registration with no account
binding. The old per-address active-code unique index is replaced by a scoped
index. The migration does not bind email addresses or change passwords. Existing
startup housekeeping remains in place. Legacy hashed recipient attempts cannot be
backfilled into recipient-domain buckets; the original global/IP/address limits
still apply. Repeated initialization is tested.

Before production rollout, independently verify migration success on an approved
private snapshot and inspect aggregate integrity/uniqueness failures without
logging addresses or credentials. Schema validation failures are a rollout gate;
do not delete conflicting rows or manufacture an identity to make startup succeed.

## Rollback after the new version has served traffic

Simply restoring old code is unsafe: multiple active code purposes for the same
address can violate the old startup index. Restoring the pre-upgrade database is
also unsafe after traffic: it would undo new passwords, email bindings and accounts
and could resurrect revoked sessions.

1. Stop all writers. Keep a consistent snapshot of the latest database as the
   pre-rollback backup, with the current per-user data preserved separately.
2. On that private snapshot, run `python -m scripts.prepare_account_rollback`
   with `--source`, a new `--destination` outside the repository and all web roots,
   and `--writers-stopped`. The tool never replaces its source or an existing file.
3. It invalidates **all** pending/active verification codes, regardless of purpose,
   and restores the old per-address index. This prevents both index conflicts and
   cross-purpose redemption by old code. Users must request fresh registration
   codes after rollback. Passwords, email bindings, accounts, quotas and session
   revocations are retained; additive columns/tables remain readable by old code.
4. Check the prepared copy's integrity and old-code authentication in isolation.
   With writers still stopped, switch application code and database together,
   preserving private ownership/permissions and ensuring old WAL/SHM sidecars
   cannot be reused. Service/database installation is an explicit operator step,
   not performed by this preparation tool.
5. Verify health, existing login, rejected old passwords/revoked sessions, and
   anonymous/ordinary-admin rejection at private teaching routes. Retain both
   snapshots; re-upgrade is supported and reinstates the scoped index.

The previous application automatically promoted the configured permanent-admin
name at initialization. Before reverting to that version, confirm the configured
account is still an active database administrator (or the setting is absent).
If it is not, stop the downgrade; old startup would otherwise change privileges.
Do not change the configured name or an account's privileges merely to pass this
check. The new role fields themselves require no schema migration.

A pre-upgrade snapshot may be restored only if the upgrade has accepted no user
writes and no security changes have occurred since that snapshot. Otherwise use
the state-preserving rollback above.

## Outstanding production gates

Real SMTP delivery/encryption, provider settings, production data migration,
OS-specific permissions and a normally authenticated permanent-admin browser check
are **not** proven by offline tests. Do not read production secrets, send real
emails, migrate real accounts or manufacture sessions to complete those tests.
