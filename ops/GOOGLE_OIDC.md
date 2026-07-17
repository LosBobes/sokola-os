# Google OIDC setup

SOKOLA uses Google as an external identity provider (OpenID Connect,
Authorization Code flow). SOKOLA stores only the identity link (Google `sub` →
Person) and issues its own signed session cookie. No passwords are ever stored.

## 1. Create a Google OAuth client

1. Go to <https://console.cloud.google.com/apis/credentials>.
2. Configure the **OAuth consent screen** (External), add the `openid`, `email`,
   and `profile` scopes, and add your test users.
3. **Create Credentials → OAuth client ID → Web application**.
4. Under **Authorized redirect URIs**, add exactly:
   - Local dev: `http://localhost:5173/api/auth/google/callback`
   - Production: `https://<your-domain>/api/auth/google/callback`
5. Copy the **Client ID** and **Client secret**.

## 2. Configure the API

Set these environment variables (see `apps/api/.env.example`):

```bash
SOKOLA_GOOGLE_CLIENT_ID=<client id>
SOKOLA_GOOGLE_CLIENT_SECRET=<client secret>
SOKOLA_SESSION_SECRET=<long random string>          # e.g. `openssl rand -hex 32`
SOKOLA_OIDC_REDIRECT_URL=http://localhost:5173/api/auth/google/callback
SOKOLA_WEB_POST_LOGIN_URL=http://localhost:5173/
# In production also set: SOKOLA_ALLOW_INSECURE_DEV_AUTH=false
```

Restart the API. `GET /auth/config` will now report `{"google_enabled": true}`,
and the web app shows **"Prijava Google nalogom"**.

## 3. Flow

1. Web → `GET /api/auth/google/login` (full-page redirect).
2. API → Google authorization endpoint (scope `openid email profile`).
3. Google → `GET /api/auth/google/callback?code=…`.
4. API exchanges the code, validates the ID token (signature via JWKS, issuer,
   audience, expiry, nonce — all handled by Authlib), then:
   - maps the Google `sub` to a Person, creating one on first login (JIT), and
   - stores `person_id` in a signed, httpOnly session cookie.
5. API redirects the browser to `SOKOLA_WEB_POST_LOGIN_URL`; the SPA calls `/me`
   and resolves the person's organization/role contexts.

## Notes

- The person still selects (or is routed to) an organization/role context; the
  server re-checks it on every request.
- First-time Google users are provisioned with `identity_status = VERIFIED` but
  have **no** organization roles until they create or are invited to a school.
- Production hardening still to do (Part 11): token-revocation handling,
  provider-outage behavior, and CSRF hardening for cookie-authenticated
  mutations (currently mitigated by `SameSite=Lax`).
