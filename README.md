# Norman Cellphone Center and Accessories — Retail System

Admin dashboard + AI-assisted Messenger storefront for a phone retail and repair shop.
Customers can browse products, reserve items, and request repairs through a Facebook Messenger bot
powered by AI (DeepSeek + Gemini). Shop staff manage inventory, reservations, repairs, and customer
conversations through a React admin dashboard with JWT-based authentication.

## Prerequisites

- **Python** 3.10+ (the backend targets modern async syntax and `pydantic-settings`)
- **Node.js** 18+ (the frontend uses Vite 5 with React 18; Node 18+ is recommended)
- **Git** (for cloning the repo)

## Project Structure

```
norman-retail-system/
├── backend/
│   ├── app/                  # FastAPI application
│   ├── alembic/              # DB migrations
│   ├── tests/                # pytest test suite
│   ├── requirements.txt      # Python dependencies
│   ├── alembic.ini           # Alembic configuration
│   └── .env.example          # Environment variable template
├── frontend/                 # Vite + React admin dashboard
│   └── package.json
└── README.md
```

## Backend Setup

From the **repo root**:

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv

# On Linux/macOS:
source venv/bin/activate

# On Windows (PowerShell):
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Copy the environment template and fill in real values
copy .env.example .env          # Windows
# cp .env.example .env           # Linux/macOS

# Run database migrations
python -m alembic upgrade head
```

> [!IMPORTANT]
> **Always run uvicorn from the `backend/` directory**, not from the repo root.
> Although `.env` path resolution is now anchored to an absolute path internally,
> the standing project convention is to launch from `backend/` — this keeps the
> SQLite database file (`norman_shop.db`) and all relative paths consistent.

```bash
# Start the development server (must be inside backend/)
uvicorn app.main:app --reload --port 8000
```

The API is now running at http://localhost:8000.

- Health check: http://localhost:8000/health
- Interactive docs: http://localhost:8000/docs

## Frontend Setup

From the **repo root**:

```bash
cd frontend

npm install
npm run dev
```

The admin dashboard is now running at http://localhost:5173.

## Environment Variables

All environment variables are documented in `backend/.env.example`.
Copy it to `backend/.env` and fill in every value before starting the server.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Database connection string (default: SQLite) |
| `DEEPSEEK_API_KEY` | AI chat responses (platform.deepseek.com) |
| `GEMINI_API_KEY` | Image-based product lookups (aistudio.google.com) |
| `MESSENGER_VERIFY_TOKEN` | Meta webhook verification token |
| `MESSENGER_PAGE_ACCESS_TOKEN` | Meta Page Access Token for Send API |
| `META_APP_SECRET` | Validates webhook signatures |
| `JWT_SECRET_KEY` | Signs admin auth tokens |
| `ADMIN_USERNAME` | Admin dashboard login username |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash of the admin password |
| `ENVIRONMENT` | `development` or `production` |
| `PORT` | Port for Uvicorn (default: 8000) |
| `STAFF_HANDOFF_ENABLED` | `True` = AI auto-replies; `False` = manual-only |

## Messenger Webhook

The Messenger webhook is exposed at:

```
POST /api/v1/webhook
GET  /api/v1/webhook
```

When configuring Meta's App Dashboard, set the **Callback URL** to your public endpoint
(e.g. an ngrok tunnel forwarding to `localhost:8000`) with the path `/api/v1/webhook`.
The **Verify Token** must match `MESSENGER_VERIFY_TOKEN` in your `.env` file.

## Running Tests

```bash
cd backend
python -m pytest backend/tests/ -q --tb=line
```

- `-q` keeps output quiet (project convention — do not use `-v`).
- `--tb=line` shows one line per failure for fast scanning.

## Deployment (Render)

**Live URL** — [https://norman-retail-system.onrender.com](https://norman-retail-system.onrender.com)

**Auto-deploy** — Every push to the `main` branch on GitHub triggers a new Render deploy automatically. No manual deploy step is needed for routine changes.

**Production environment variables** — On Render, these are stored directly in Render's dashboard under the **Environment** tab for the web service. The list of required variables is kept in sync with `backend/.env.example` whenever a new variable is added to the app.

**Logs** — Production logs are available in the Render dashboard under the **Logs** tab for the service.

**Known current limitations**

- **Free-tier spin-down**: The service is currently on Render's free instance tier, which **spins down after ~15 minutes of inactivity**. On the first request after a spin-down, the instance cold-starts, causing delayed responses (up to ~50 seconds). This will be resolved once the service is upgraded to the paid **Starter** tier.
- **Database (SQLite, no persistent disk yet)**: The app currently uses SQLite with **no persistent disk** attached on Render, meaning **the database is reset on every redeploy**. Do NOT store real customer data here until a persistent disk is added and `DATABASE_URL` is updated to point to a path on that disk. This is an open item — not yet resolved.

**Messenger webhook (production)** — Meta's Messenger webhook is already configured in Meta's App Dashboard as:
```
https://norman-retail-system.onrender.com/api/v1/webhook
```
This is already set up and does not need to be reconfigured.

---

## Running the System (pm2 — local development only)

**The pm2 setup described in this section is for local development only.** Production runs on Render (see the Deployment section above).

A single pm2 command starts the backend, frontend, and ngrok tunnel together, auto-restarting any process that crashes. From the **repo root**:

```bash
# Start everything
pm2 start ecosystem.config.js

# Stop everything
pm2 stop all

# Restart everything
pm2 restart all

# View live logs (all processes)
pm2 logs

# View process status
pm2 status
```

### Boot persistence (Windows)

The process list auto-restarts when the machine reboots:

```bash
pm2 save                    # snapshot the running process list
pm2-startup install         # register pm2 as a Windows startup task
```

> [!NOTE]
> **No static ngrok domain is configured.** The public tunnel URL changes on
> every restart, requiring manual re-confirmation of the Meta webhook
> Callback URL. To fix this, reserve a free static domain at
> https://dashboard.ngrok.com/cloud-edge/domains and update the `norman-ngrok`
> args in `ecosystem.config.js` to:
> `"http --domain=<your-static-domain> 8000 --log stdout"`.

## API Overview

| Endpoint | Description |
|---|---|
| `POST /api/v1/auth/login` | Admin login (returns JWT) |
| `GET /api/v1/products` | List products |
| `POST /api/v1/products` | Create a product (auth required) |
| `GET /api/v1/inventory` | List inventory entries |
| `GET /api/v1/reservations` | List reservations |
| `POST /api/v1/reservations` | Create a reservation (auth required) |
| `GET /api/v1/repairs` | List repair jobs |
| `POST /api/v1/repairs` | Create a repair job (auth required) |
| `GET /api/v1/webhook` | Meta webhook verification |
| `POST /api/v1/webhook` | Receive Messenger events |
| `GET /api/v1/conversations` | List customer conversations (auth required) |
| `GET /api/v1/notifications` | List staff notifications (auth required) |

Full interactive documentation is available at http://localhost:8000/docs when the server is running.

## License

MIT — see [LICENSE](./LICENSE) for details.