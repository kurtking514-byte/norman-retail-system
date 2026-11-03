# Norman Cellphone Center — Retail System

A staff dashboard and an AI Messenger assistant for **Norman Cellphone Center & Accessories**, a phone and electronics shop at Maddela Public Market, Maddela, Quirino.

Customers message the shop's Facebook page and an AI assistant answers right away with real prices and stock, takes reservations, and hands the chat to a staff member when a person is needed. Staff run the shop from one dashboard: inventory, reservations, repairs and customer chats.

## Links

| | |
|---|---|
| **Staff dashboard** (live) | https://norman-retail-system-dashboard.onrender.com |
| Backend API | https://norman-retail-system.onrender.com (opening it takes you to the dashboard) |
| API docs | https://norman-retail-system.onrender.com/docs |

> [!NOTE]
> The dashboard is for shop staff, so it opens on a sign-in page.
> It runs on Render's free plan, so if nobody has used it for a while the **first load can take up to a minute** while the server wakes up. After that it's fast.

## What it does

**Messenger AI assistant**
- Answers customers in English or Taglish with live prices, stock, discounts and installment plans (Home Credit, Skyro)
- Reserves items for pickup and quotes common repairs
- Hands the chat to staff when it can't help, and staff can reply from the dashboard

**Staff dashboard**
- **Dashboard** — what needs attention today: chat handoffs, reservations about to expire, open repairs, low stock
- **Inventory** — products, specs, prices and stock by unit, with spreadsheet import
- **Reservations** — holds for customers, with expiry dates
- **Repairs** — quick intake form, color-coded stages (In line → Being repaired → Waiting for pickup → Picked up) and a Paid / Unpaid tag
- **Live Chat** — every Messenger conversation, with a switch to turn the AI off and reply yourself

## Built with

| Part | Tools |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy (async), Alembic, pytest |
| Database | PostgreSQL on Neon (SQLite for local development) |
| Frontend | React 18, Vite, Tailwind CSS |
| AI | DeepSeek for chat replies, Gemini for photo-based product lookups |
| Messaging | Facebook Messenger Platform (webhook + Send API) |
| Hosting | Render (backend web service + static dashboard), GitHub Actions |

## Project layout

```
norman-retail-system/
├── backend/                 FastAPI app
│   ├── app/
│   │   ├── api/v1/          API routes (products, repairs, webhook, ...)
│   │   ├── models/          Database tables
│   │   ├── schemas/         Request / response shapes
│   │   └── services/        Messenger and AI logic
│   ├── alembic/             Database migrations
│   ├── tests/               pytest suite
│   └── .env.example         Every setting the backend needs
├── frontend/                React staff dashboard
│   ├── src/pages/           One file per dashboard page
│   ├── src/components/      Shared pieces (layout, banner, inventory panel)
│   └── dist/                Built dashboard that Render serves
├── .github/workflows/       Keep-awake pinger and its reminder
└── ecosystem.config.js      pm2 setup for running everything locally
```

## Run it locally

You need **Python 3.10+** and **Node.js 18+**.

**Backend** (always start it from inside `backend/`):

```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1        # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # then fill in the values (macOS/Linux: cp)
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The API runs at http://localhost:8000 and its docs at http://localhost:8000/docs.

**Dashboard:**

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs at http://localhost:5173.

To start the backend, dashboard and an ngrok tunnel together with auto-restart, use pm2 from the repo root: `pm2 start ecosystem.config.js` (`pm2 logs` to watch, `pm2 stop all` to stop).

### Settings

All settings are listed in [`backend/.env.example`](backend/.env.example). The main ones:

| Variable | What it's for |
|---|---|
| `DATABASE_URL` | Database connection (SQLite by default) |
| `JWT_SECRET_KEY` | Signs staff sign-in tokens |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` | Staff login (the password is stored as a bcrypt hash) |
| `DEEPSEEK_API_KEY`, `GEMINI_API_KEY` | AI replies and photo lookups |
| `MESSENGER_VERIFY_TOKEN`, `MESSENGER_PAGE_ACCESS_TOKEN`, `META_APP_SECRET` | Facebook Messenger connection |
| `FRONTEND_ORIGINS` | Dashboard addresses allowed to call the API |
| `STAFF_HANDOFF_ENABLED` | `True` lets the AI reply; `False` means staff reply manually |

## Tests

```bash
cd backend
python -m pytest -q
```

## Deployment

- Every push to `main` redeploys both the backend and the dashboard on Render.
- The dashboard is served from the committed `frontend/dist`, so run `npm run build` before committing frontend changes.
- Production settings live in Render's **Environment** tab, and logs in its **Logs** tab.
- New database columns are added automatically when the backend starts; matching Alembic migrations are in `backend/alembic/versions`.
- The Messenger webhook is set in Meta's App Dashboard to `https://norman-retail-system.onrender.com/api/v1/webhook`.
- A GitHub Actions workflow pings `/health` to keep the free Render server from sleeping. GitHub runs scheduled jobs irregularly, so an outside uptime monitor pinging the same address every 5 minutes is more reliable.

## License

MIT — see [LICENSE](LICENSE).
