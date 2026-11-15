# PeopleforPeople – Campaign API

Backend for campaigns, small-business promotions and admin moderation.
ACS WIL Group 5 · Developer: Suraj Shrestha · Jira: KAN-23 (spec), KAN-31, KAN-40, KAN-49

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL (Neon) · pytest
**Works with:** Aftab's auth service (`auth-backend`, login cookie `sid`) and the same Neon database.

---

## 1. Run it on your computer

```bash
cd campaign-api
python -m venv .venv
# Windows: .venv\Scripts\activate      Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.seed          # adds 6 sample approved campaigns (local SQLite file)
uvicorn app.main:app --reload   # starts on http://localhost:8000
```

Open **http://localhost:8000/docs** – interactive docs where you can try every endpoint.

Locally the API runs in `AUTH_MODE=dev`: there is no real login, you pretend to be a user by sending a header:

| Header | Acts as |
|---|---|
| `X-Dev-User: 1:user` | normal user with id 1 |
| `X-Dev-User: 99:admin` | administrator with id 99 |

(In `/docs` you can add this header with a browser extension, or use curl / Postman / Thunder Client.)

```bash
curl http://localhost:8000/api/campaigns
curl -X POST http://localhost:8000/api/campaigns/1/join -H "X-Dev-User: 5:user"
```

Dev mode refuses to start when `APP_ENV=production`.

## 2. Run the tests

```bash
pip install -r requirements-dev.txt
pytest
```

31 tests covering section 8 of the KAN-23 spec (visibility, validation, status flow, permissions, XSS stripping, moderation log), the joined-campaign fix, and both login modes.

---

## 3. Endpoints

Base path `/api`. JSON in and out. Full details at `/docs`.

| Method | Path | Who | Purpose | Jira |
|---|---|---|---|---|
| GET | `/campaigns` | Public | Approved, active campaigns. Query: `type`, `category`, `search`, `page`, `page_size` (≤50), `sort` = `newest` \| `ending_soon` | KAN-31 |
| GET | `/campaigns/featured` | Public | Up to 6 for the homepage | KAN-31 |
| GET | `/campaigns/{id}` | Public* | Details (*owner/admin can also see non-approved) | KAN-31 |
| POST | `/campaigns` | User | Create (starts as `DRAFT`) | KAN-40 |
| PUT | `/campaigns/{id}` | Owner | Edit while `DRAFT` or `REJECTED` | KAN-40 |
| POST | `/campaigns/{id}/submit` | Owner | Send for review → `PENDING` | KAN-40 |
| GET | `/me/campaigns` | User | My campaigns, all statuses, with rejection reason | KAN-40 |
| GET | `/admin/campaigns` | Admin | Moderation queue (`status` defaults to `PENDING`) | KAN-40 |
| POST | `/admin/campaigns/{id}/approve` | Admin | `PENDING` → `APPROVED` | KAN-40 |
| POST | `/admin/campaigns/{id}/reject` | Admin | `PENDING` → `REJECTED`, body `{"reason": "..."}` (10–500 chars) | KAN-40 |
| POST | `/campaigns/{id}/archive` | Owner/Admin | `APPROVED` → `ARCHIVED` | KAN-49 |
| GET | `/admin/campaigns/{id}/history` | Admin | Moderation log | KAN-49 |
| POST | `/campaigns/{id}/join` | User | Join a campaign | KAN-26 fix |
| DELETE | `/campaigns/{id}/join` | User | Leave a campaign | KAN-26 fix |
| GET | `/me/joined` | User | Campaigns I joined | KAN-26 fix |
| GET | `/health` | Public | Health check | |

**Status flow**

```
DRAFT --submit--> PENDING --approve--> APPROVED --archive--> ARCHIVED
                     |
                     +--reject (reason)--> REJECTED --edit + submit--> PENDING
```

Any other change returns `409 INVALID_STATUS_TRANSITION`.

**Errors** always look like:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Some fields are missing or invalid.",
             "details": [ { "field": "title", "message": "Field required" } ] } }
```

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Missing/invalid field, page_size > 50, short reject reason |
| `NOT_AUTHENTICATED` | 401 | No valid login cookie |
| `FORBIDDEN` | 403 | Logged in but not owner / not admin |
| `NOT_FOUND` | 404 | Doesn't exist, or hidden from this user |
| `INVALID_STATUS_TRANSITION` / `NOT_EDITABLE` | 409 | Change not allowed in the current status |
| `AUTH_UNAVAILABLE` | 503 | Remote auth service unreachable (remote mode only) |

**Campaign card** (list, featured) vs **detail** (details page, my campaigns, admin): cards leave out `description`, `status` and review fields. Both include `participants` (join count) and `joined` (true when the logged-in user has joined).

### Changes from the KAN-23 spec

- **Added join endpoints** so "joined" is stored in the database and survives logout/login (Sagar's KAN-26 test, issue 2).
- **Auth uses Aftab's `sid` cookie**, not a Bearer token. The spec assumed a token; the auth service uses an HttpOnly session cookie.
- `participants` and `joined` added to campaign responses.

---

## 4. How login works with the auth service

Aftab's service stores `sha256(sid)` in its `sessions` table. With `AUTH_MODE=db` this API reads the `sid` cookie, hashes it the same way and looks it up in **the same Neon database** – no extra network call, so no Render cold-start delay.

`AUTH_MODE=remote` instead forwards the cookie to `AUTH_BASE_URL/auth/me` (use this only if the two services can't share a database).

### Important: the browser must send the cookie to this API

A cookie only goes back to the site that set it. If the auth service is on `auth-backend-xxx.onrender.com` and this API is on `campaign-api-xxx.onrender.com`, the browser **won't** send `sid` here.

Fix: the frontend calls both services through **its own domain**, using a proxy. Then the cookie belongs to the frontend's domain and is sent to both.

**Vite (local dev)** – `vite.config.js`:

```js
export default defineConfig({
  server: {
    proxy: {
      "/auth":  { target: "https://auth-backend-lb6o.onrender.com", changeOrigin: true },
      "/admin/users": { target: "https://auth-backend-lb6o.onrender.com", changeOrigin: true },
      "/api":   { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
```

**Vercel / Netlify (deployed frontend)** – `vercel.json`:

```json
{ "rewrites": [
  { "source": "/auth/:path*", "destination": "https://auth-backend-lb6o.onrender.com/auth/:path*" },
  { "source": "/api/:path*",  "destination": "https://YOUR-CAMPAIGN-API.onrender.com/api/:path*" }
] }
```

Then in React call relative URLs with `credentials: "include"`:

```js
const res = await fetch("/api/campaigns?page=1", { credentials: "include" });
const { items, total } = await res.json();

await fetch(`/api/campaigns/${id}/join`, { method: "POST", credentials: "include" });
```

Public endpoints (list, featured, details) work **without** login, so the homepage can show campaigns before the proxy is set up.

---

## 5. Deploy (Render, next to the auth service)

New **Web Service** from this repo folder:

| Setting | Value |
|---|---|
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Root directory | `campaign-api` (if inside the shared repo) |

Environment variables:

| Name | Value |
|---|---|
| `DATABASE_URL` | Same Neon connection string as the auth service |
| `AUTH_MODE` | `db` |
| `APP_ENV` | `production` |
| `CORS_ORIGINS` | Frontend URL(s), comma-separated, e.g. `https://peopleforpeople.vercel.app` |
| `PYTHON_VERSION` | `3.12.8` |

Tables are created automatically on first start (`AUTO_CREATE_TABLES=true`). `schema.sql` has the same tables for review in the Neon SQL editor. Then run `python -m scripts.seed` once (Render Shell) for demo data.

---

## 6. Project layout

```
app/
  main.py          app setup, CORS, routers, /health
  config.py        environment settings
  db.py            database connection
  models.py        tables: campaigns, campaign_moderation_log, campaign_joins
  schemas.py       request/response models + validation + HTML stripping
  services.py      visibility rules, status transitions, moderation log
  auth.py          login-cookie check (db / remote / dev)
  errors.py        consistent error format
  routers/
    campaigns.py   public, owner and join endpoints
    admin.py       moderation endpoints
scripts/seed.py    demo campaigns
tests/             pytest suite
schema.sql         PostgreSQL DDL for the tables above
```

## 7. Environment variables (all)

See `.env.example`.

| Name | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./campaigns.db` | Neon URL in staging/production |
| `AUTH_MODE` | `dev` | `db`, `remote` or `dev` |
| `AUTH_BASE_URL` | `https://auth-backend-lb6o.onrender.com` | Only for `remote` |
| `SESSION_COOKIE` | `sid` | Cookie name used by the auth service |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |
| `APP_ENV` | `development` | `production` blocks dev mode |
| `AUTO_CREATE_TABLES` | `true` | Create missing tables on start |

## Deploying on Render

1. New → Web Service → Public Git Repository → this repo's URL.
2. Build command: `pip install -r requirements.txt`
3. Start command: `python -m scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment: `APP_ENV=production`, `AUTH_MODE=remote`, `AUTH_BASE_URL=https://auth-backend-lb6o.onrender.com`,
   `CORS_ORIGINS=https://peopleforpeople-sigma.vercel.app`, `PYTHON_VERSION=3.12.8`, and optionally `DATABASE_URL` (Neon).
5. In the frontend's `vercel.json`, add a rewrite so the login cookie reaches the API:
   `{ "source": "/api/:path*", "destination": "https://<your-service>.onrender.com/api/:path*" }`
