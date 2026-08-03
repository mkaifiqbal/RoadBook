# Roadbook ELD Trip Planner — Frontend

React + Vite frontend for the Django/DRF trip-planning API. It includes account approval, role-based driver/admin workspaces, saved trip records, an annotated Leaflet route map, an HOS stop timeline, and printable SVG daily log sheets.

## Local development

Run the Django API first:

```powershell
cd backend
python manage.py migrate
python manage.py runserver
```

Then run the frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `http://127.0.0.1:8000` during development.

## Accounts and approval

- Driver self-signup creates a **pending** account. An admin must approve it before the driver can sign in.
- Drivers can plan trips, reopen only their own saved trips, and maintain default carrier/truck values. The truck number remains editable on every trip.
- Admins can approve or reject requests, create immediately active drivers, suspend/reactivate accounts, and inspect every driver's saved routes and log sheets.

The migration seeds two assessment-ready demo accounts, also shown as one-click options on the login screen:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@roadbook.demo` | `RoadbookAdmin!2026` |
| Driver | `driver@roadbook.demo` | `RoadbookDriver!2026` |

These public credentials are intentionally included for evaluator access. Remove the `0003_seed_demo_accounts` migration or replace these credentials before using the project in a real deployment.

Create the first admin with Django's standard command:

```powershell
cd backend
python manage.py createsuperuser
```

The superuser signs into the same Roadbook login screen with the email/username used during creation.

## Environment

For a separately hosted backend, copy `.env.example` to `.env` and set:

```env
VITE_API_BASE_URL=https://your-django-api.example.com
```

The Django deployment must include the frontend origin in `CORS_ALLOWED_ORIGINS`.

## Production checks

```powershell
npm run lint
npm run build
```

The production bundle is generated in `frontend/dist/`. For Vercel, use `frontend` as the root directory, `npm run build` as the build command, and `dist` as the output directory.

## Main modules

- `src/App.jsx` — authenticated application shell, planner, results, loading and error states
- `src/components/AuthScreen.jsx` — driver signup and shared admin/driver login
- `src/components/Workspace.jsx` — role-aware navigation, trips, profile, approval, and fleet management
- `src/components/TripForm.jsx` — required inputs and optional log-header metadata
- `src/components/RouteMap.jsx` — route, waypoints, and required-stop markers
- `src/components/LogSheet.jsx` — printable 24-hour SVG log grid and remarks
- `src/api.js` — JWT-aware auth, account, trip, admin, and planner API integration
- `src/styles.css` — Tailwind import plus the responsive visual system and print rules

The SVG log uses the backend's minute-level `entries`, `remarks`, and `totals_hours` values directly; it does not recalculate HOS rules in the browser.

## Map, search, and routing providers

The default development stack is free and requires no API key:

- **Leaflet / React Leaflet** renders the interactive map.
- **OpenStreetMap raster tiles** provide the basemap and are displayed with attribution.
- **Nominatim (OpenStreetMap)** supplies real address/place suggestions and final geocoding through Django. Autocomplete starts after three characters, waits 450 ms between keystrokes, cancels stale requests, and uses an in-process backend cache.
- **OSRM's public demo server** supplies route geometry, road mileage, and estimated drive time.

Nominatim and the public OSRM demo are community services intended here for development and assessment-scale traffic, not a production SLA or heavy use. For production/demo reliability, create a free OpenRouteService key and set `ORS_API_KEY` in `backend/.env`. The backend then automatically uses OpenRouteService geocoding and its `driving-hgv` truck-routing profile. Provider quotas can change, so verify the current free-tier limits before deployment.

Install the backend environment completely with:

```powershell
python -m pip install -r backend/requirements.txt
```

`python-dotenv` is included for `.env` loading. Settings also degrade safely when it has not yet been installed, so Django reports the next genuinely missing package rather than failing immediately on optional environment-file support.