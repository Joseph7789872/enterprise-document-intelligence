# EDIP Frontend

A minimal **Next.js 14 (App Router)** reference UI for the Enterprise Document
Intelligence Platform: a landing page, a login screen, and a query page that returns
cited answers. It is intentionally small — a credible demo and deployment target, not a
full product surface.

## Pages

| Route | Purpose |
|---|---|
| `/` | Marketing landing page. |
| `/login` | Signs in via `POST /auth/login`, stores the bearer token client-side. |
| `/app` | Asks a question via `POST /query` and renders the answer + citations. |

## Develop

```bash
npm ci
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL if the backend isn't on :8000
npm run dev                  # http://localhost:3000
```

The backend's CORS allows `http://localhost:3000` by default (`CORS_ALLOW_ORIGINS`).

## Build / Docker

```bash
npm run build                # standalone output in .next/standalone
docker build --build-arg NEXT_PUBLIC_API_URL=https://api.example.com -t edip-frontend .
```

`NEXT_PUBLIC_API_URL` is baked into the client bundle at **build** time, so pass it as a
build arg for production images.

## Notes / limitations

- The token is stored in `localStorage` for demo simplicity. A hardened SPA should use
  httpOnly cookies + token refresh; see the backend `/auth/refresh` endpoint.
- No SSR data fetching, styling is plain CSS (no Tailwind/shadcn yet) — deliberately
  minimal to keep the build fast and dependency-light.
