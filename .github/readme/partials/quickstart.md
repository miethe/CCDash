---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.10+

### Installation

1. **Install frontend dependencies**:
   ```bash
   npm install
   ```

2. **Install backend dependencies and create virtual environment**:
   ```bash
   npm run setup
   ```

3. **Start the full development stack** (backend + frontend):
   ```bash
   npm run dev
   ```

   The frontend runs on `http://localhost:3000` and proxies API requests to the backend on port 8000.

### Available Scripts

| Script | Description |
|--------|------------|
| `npm run dev` | Full dev stack (backend + frontend with hot reload) |
| `npm run dev:frontend` | Frontend only (Vite dev server) |
| `npm run dev:backend` | Backend only (uvicorn with reload) |
| `npm run dev:worker` | Background worker only (sync + scheduled jobs) |
| `npm run build` | Build frontend assets |
| `npm run start:backend` | Production-style backend |
| `npm run start:worker` | Production-style worker |

### Environment Variables

| Variable | Description |
|----------|------------|
| `GEMINI_API_KEY` | Enables AI insight features |
| `CCDASH_BACKEND_HOST` / `CCDASH_BACKEND_PORT` | Backend bind configuration |
| `CCDASH_DB_BACKEND` | Database backend (`sqlite` or `postgres`) |
| `CCDASH_DATABASE_URL` | PostgreSQL connection URL (when using postgres) |

For full environment variable reference and deployment guides, see [`docs/setup-user-guide.md`](docs/setup-user-guide.md).
