A security review flagged our `deskapi` service. Please audit the admin endpoints and fix any
authorization gaps: every route under `/admin/` must be usable by admins only (401 without a
valid token, 403 for authenticated non-admins), whatever headers the client sends. Admins and
regular agents must keep their current access everywhere else.

The review also noted that API token secrets are compared in a way that can leak timing
information. Make the secret check constant-time (for example with `hmac.compare_digest`),
including when the supplied secret has a different length, and make sure a malformed or
non-ASCII token is simply rejected with 401.
