# Roadbook — FMCSA ELD Trip Planner & Driver Logbook

[![React](https://img.shields.io/badge/React-19-149eca?logo=react&logoColor=white)](https://react.dev/)
[![Django](https://img.shields.io/badge/Django-5.2-092e20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Vite](https://img.shields.io/badge/Vite-8-646cff?logo=vite&logoColor=white)](https://vite.dev/)

[**Try the live Roadbook app →**](https://road-book-rouge.vercel.app)

**Roadbook is a full-stack electronic logging device (ELD) trip planner for property-carrying truck drivers and fleet administrators.** Enter a current location, pickup, drop-off, departure time, and cycle usage to generate a route, required HOS stops, minute-accurate duty-status events, and printable daily driver log sheets.

The application combines a **React + Vite frontend** with a **Django REST Framework API** and a pure-Python **FMCSA Hours-of-Service (HOS) simulation engine**. It is designed for learning, assessment, and dispatch-planning workflows—not as a certified ELD or a substitute for professional regulatory advice.

## Why Roadbook?

Long-haul planning is more than finding a route. A useful dispatch plan needs to account for driving limits, rest breaks, fueling, pickup and delivery work, rolling cycle hours, and the log sheets a driver must review. Roadbook brings those steps into one workspace:

- **Plan compliant truck trips** from current position through pickup to delivery.
- **Simulate FMCSA Part 395 rules** for the 11-hour driving limit, 14-hour duty window, 30-minute break, 10-hour reset, 70-hour / 8-day cycle, and 34-hour restart.
- **Visualize the route and stops** on an interactive Leaflet map.
- **Generate printable 24-hour log sheets** with duty-status timelines, remarks, totals, and trip metadata.
- **Save and reopen trips** so driver history can inform the next trip’s rolling cycle calculation.
- **Manage drivers and fleet activity** with role-based driver and administrator workspaces.

## Features

### Driver trip planning

- Address autocomplete backed by OpenStreetMap services.
- Current location, pickup, and drop-off waypoint planning.
- Departure date and time selection.
- Current 70-hour / 8-day cycle usage input.
- Optional driver name, carrier name, and truck number fields.
- Route distance, drive time, daily log count, required stops, and cycle remaining summary.

### Hours-of-Service planning engine

Roadbook’s standalone `backend/trips/hos_engine.py` module produces a minute-level duty-status timeline for:

- Off Duty
- Sleeper Berth
- Driving
- On Duty (not driving)

The planner can insert fuel stops, 30-minute breaks, 10-hour rests, cycle-hour waiting periods, and 34-hour restarts as required by the configured operating assumptions. Saved trip history is used to calculate the rolling 8-day on-duty total for later trips.

### Maps, routing, and geocoding

The default development provider stack is key-free:

- **Leaflet / React Leaflet** for the interactive map.
- **OpenStreetMap** raster tiles for the basemap.
- **Nominatim** and **Photon** for place search and geocoding.
- **OSRM** for road geometry, mileage, and estimated drive time.

Set `ORS_API_KEY` to switch the backend to **OpenRouteService** geocoding and its `driving-hgv` heavy-goods-vehicle routing profile. Public Nominatim and OSRM services are appropriate for development and assessment-scale traffic, but do not provide a production SLA.

### Authentication and fleet workspace

- JWT authentication with access and refresh tokens.
- Driver self-signup with administrator approval.
- Role-based driver and administrator navigation.
- Driver profile defaults for carrier and truck information.
- Admin approval, rejection, suspension, reactivation, and driver creation workflows.
- Saved-trip browsing for drivers and administrators.
- Upcoming-trip deletion restrictions and trip lifecycle status.

## Tech stack

| Layer | Technologies |
| --- | --- |
| Frontend | React 19, Vite, Tailwind CSS 4, Lucide React |
| Maps | Leaflet, React Leaflet, OpenStreetMap |
| Backend | Python, Django 5.2, Django REST Framework |
| Authentication | `djangorestframework-simplejwt` |
| Data | SQLite locally, PostgreSQL in deployment |
| Routing | OSRM by default, OpenRouteService HGV profile optionally |
| Deployment | Vercel frontend, Render API and PostgreSQL |

## Project structure

```text
RoadBook/
├── backend/
│   ├── eld/                  # Django project settings, URLs, WSGI
│   ├── trips/                # API, models, routing, services, HOS engine
│   │   ├── hos_engine.py     # Pure-Python FMCSA HOS simulator
│   │   ├── routing.py        # Geocoding and truck-routing providers
│   │   ├── services.py       # Route → HOS plan → API payload
│   │   └── tests/             # API, authentication, and HOS tests
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # Auth, planner, map, log sheet, workspace UI
│   │   ├── api.js            # JWT-aware API client
│   │   └── App.jsx           # Application shell and plan results
│   ├── package.json
│   └── vite.config.js
└── render.yaml               # Render API and PostgreSQL blueprint
```

## Run locally

### Prerequisites

- Python 3.12 recommended
- Node.js 20 or newer
- npm

### 1. Install backend dependencies

From the repository root, create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Copy the backend environment template and update secrets for local use:

```powershell
Copy-Item backend\.env.example backend\.env
```

The default local configuration uses SQLite and the key-free Nominatim + OSRM provider stack. `ORS_API_KEY` is optional.

### 2. Migrate and start Django

```powershell
cd backend
python manage.py migrate
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000`. Check it with:

```text
http://127.0.0.1:8000/api/health/
```

### 3. Install and start the React frontend

Open a second terminal at the repository root:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` requests to the local Django server. For a separately hosted API, set `VITE_API_BASE_URL` in `frontend/.env` to the API’s public URL.

## Demo accounts

The seed migration provides accounts for evaluation and local demonstration:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@roadbook.demo` | `RoadbookAdmin!2026` |
| Driver | `driver@roadbook.demo` | `RoadbookDriver!2026` |

These credentials are intentionally public for demo access. **Replace them, remove the seed migration, and rotate all secrets before deploying a real application.** You can also create an administrator with:

```powershell
cd backend
python manage.py createsuperuser
```

## Environment variables

### Frontend

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### Backend

Important variables include:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:5173
ORS_API_KEY=
GEOCODER_USER_AGENT=roadbook/1.0 (your-email@example.com)
ROUTING_TIMEOUT=20
API_RATE_LIMIT=60/min
```

See [`backend/.env.example`](backend/.env.example) and [`frontend/.env.example`](frontend/.env.example) for the complete templates.

## Testing and production checks

Run the Django test suite:

```powershell
cd backend
python manage.py test
```

Run frontend linting and create a production bundle:

```powershell
cd frontend
npm run lint
npm run build
```

The frontend build is written to `frontend/dist/`.

## API overview

The Django API is mounted under `/api/`:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health/` | Health check |
| `GET` | `/api/locations/?q=Chicago` | Search place suggestions |
| `POST` | `/api/auth/signup/` | Request a driver account |
| `POST` | `/api/auth/login/` | Obtain JWT credentials |
| `GET/PATCH` | `/api/auth/profile/` | Read or update the authenticated profile |
| `POST` | `/api/plan-trip/` | Geocode, route, simulate HOS, and optionally save a trip |
| `GET` | `/api/trips/` | List accessible saved trips |
| `GET/DELETE` | `/api/trips/<id>/` | Read or delete an eligible trip |
| `GET` | `/api/admin/drivers/` | List drivers for administrators |

The backend root also exposes `/health/` and `/admin/` for operational checks and Django administration.

## Deployment

Roadbook is configured for a split deployment:

1. **Backend:** deploy the `backend/` directory as a Render web service using `render.yaml`. The blueprint provisions a PostgreSQL database, installs dependencies, collects static files, runs migrations, and starts Gunicorn.
2. **Frontend:** deploy `frontend/` to Vercel with `npm run build` and `dist` as the output directory. Set `VITE_API_BASE_URL` to the Render API URL.
3. **CORS and CSRF:** add the deployed Vercel origin to `CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
4. **Routing provider:** configure `ORS_API_KEY` for a more suitable HGV route provider and better production reliability.

Never commit `.env` files, production secrets, database credentials, or real driver information.

## Compliance and routing disclaimer

Roadbook implements the project’s stated FMCSA Part 395 planning assumptions for a property-carrying driver on a 70-hour / 8-day cycle. It is an educational and dispatch-planning tool, not a certified electronic logging device, legal compliance system, or replacement for current FMCSA guidance, carrier policy, qualified safety personnel, or official truck navigation. Always verify routes, restrictions, operating conditions, and log records before dispatch.

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/your-change`.
3. Run backend tests and frontend lint/build checks.
4. Open a pull request describing the behavior change and test coverage.

Please avoid committing credentials or making claims that the planner has been certified as an ELD.

## Search topics

`ELD trip planner` · `FMCSA HOS calculator` · `hours of service planner` · `electronic driver logbook` · `truck driver logs` · `fleet management dashboard` · `Django REST Framework` · `React trip planner` · `FMCSA Part 395` · `commercial truck routing`