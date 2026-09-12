# Fixes applied

Seven bugs. The first four made the app non-functional end to end — the
frontend and backend were wired to two different API surfaces.

## 1. Frontend and backend spoke different URLs
`frontend/src/api/client.ts` used `baseURL: '/'`, but every backend route is
mounted under `/api` and the Vite proxy only forwards `/api`. Every request
hit the dev server and came back as `index.html`. Set to `/api`, and fixed the
token-refresh call, which used a bare `axios.post` that bypassed baseURL.

## 2. Three routers were never registered
`portfolio.py`, `scenarios.py` and `market.py` existed but were missing from
`routers/__init__.py` — and they are exactly the routes the frontend calls
(`/portfolio/simulate`, `/scenarios/`, `/market/quotes`). Registered all three.

## 3. Registration payload didn't match the schema
The form sent `is_us_citizen`; the backend required `citizenship_attested`,
`age_attested` and `terms_attested`. The age and terms checkboxes were
collected and then discarded. Every signup would have 422'd. Fixed in
`RegisterPage.tsx` and the `RegisterData` type.

## 4. Missing driver: aiosqlite
`DATABASE_URL` defaults to `sqlite+aiosqlite:///./dev.db` but `aiosqlite` was
not in `requirements.txt`. The backend could not start without Postgres.

## 5. Broken SQLAlchemy relationship — 500 on register
`Scenario.user` declared `back_populates="scenarios"`, but `User` had no
`scenarios` relationship. Mapper configuration raised `KeyError: 'scenarios'`
on the first ORM query, so registration returned 500. Added the relationship.
Also added `Scenario` to `models/__init__.py` — without it `create_all` never
created the table.

## 6. Settings referenced keys it never declared
`market_data.py` reads `settings.POLYGON_KEY` and `settings.ALPHA_VANTAGE_KEY`;
neither existed on the `Settings` class, so every quote refresh threw
`AttributeError`. Declared both with safe defaults (blank = yfinance only).

## 7. No theme toggle
The dark/light requirement was never implemented. Added:
- `src/store/theme.ts` — dark / light / system, persisted to localStorage,
  listens for OS changes while set to system
- `src/components/ui/ThemeToggle.tsx` — cycles the three states, in the navbar
- Light palette in `index.css`. Components use Tailwind's grey ramp directly
  (`bg-gray-900`, `text-white`), so instead of rewriting every component the
  light theme remaps the ramp itself. One CSS block themes the whole app and
  new components inherit it automatically.
- Inline script in `index.html` sets the attribute before first paint, so
  there's no white flash on load in dark mode.
- `prefers-reduced-motion` respected.

## Verified
- `python test_engine.py` — 20/20, engine files still byte-identical
- Backend boots clean, zero tracebacks
- Register, login, refresh, me, questions, questionnaire, savings, simulate,
  compare, scenarios save/list, universe — all return real data
- Unauthenticated `/api/auth/me` returns 401
- Invalid input returns structured per-field errors, not a stack trace
- `npx tsc --noEmit` clean; `npm run build` succeeds

## Not fixed — your call
- `SECRET_KEY` in `backend/.env` is still `change_me_in_production...`.
  Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- JS bundle is 857 kB. Fine for a demo; code-split if you care.
- `/api/portfolio/*` and `/api/allocate` are duplicate implementations of the
  same thing. Both work. Pick one before this grows.
