# Installation Guide

Follow these steps to run Synod locally for development. The platform is divided into a Python/FastAPI backend and a Next.js frontend.

## Prerequisites
- **Python:** 3.11 or later
- **Node.js:** v18 or later
- **PostgreSQL Database:** We recommend using [Supabase](https://supabase.com) as it provides both Postgres and the required Authentication/JWKS out of the box.

---

## 1. Supabase Setup
Synod's security relies on Supabase Authentication and Row-Level Security (RLS).
1. Create a new Supabase project.
2. Under **Authentication -> Providers**, ensure Email/Password login is enabled.
3. Retrieve your **Project URL**, **Anon Key**, and **Service Role Key** (found in Project Settings -> API).
4. Run the SQL migrations (found in the backend's `alembic` setup) against your Supabase database string.
5. Enable RLS on the `council_sessions` and `provider_keys` tables in the Supabase SQL editor.

---

## 2. Backend Setup

### Environment Preparation
Navigate to the repository root directory:
```bash
cd d:\synod-ai
```

Create a virtual environment and activate it:
```bash
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On MacOS/Linux
source venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

### Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate `.env` with:
- `DATABASE_URL`: The direct PostgreSQL connection string (asyncpg format: `postgresql+asyncpg://...`).
- `SUPABASE_URL`: Your Supabase project URL.
- `SUPABASE_ANON_KEY`: Your Supabase public anon key.
- `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key (backend-only).
- `CREDENTIAL_ENCRYPTION_KEY`: A 32-byte URL-safe base64 encryption key (generated via the python snippet below).
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `LANGSMITH_TRACING` & `LANGSMITH_API_KEY`: Tracing credentials (optional).

### Database Migrations
Initialize the database tables:
```bash
alembic upgrade head
```

### Run the Backend Server
```bash
uvicorn app.main:app --reload
```
The backend will run at `http://localhost:8000`. 
*(Swagger UI available at `http://localhost:8000/docs`)*

---

## 3. Frontend Setup

### Environment Preparation
Navigate to the frontend directory:
```bash
cd d:\synod-ai\frontend
```

Install NPM packages:
```bash
npm install
```

### Environment Variables
Create a `.env.local` file in the `frontend/` directory:
```env
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Run the Frontend Server
```bash
npm run dev
```
The application will be accessible at `http://localhost:3000`.

---

## 4. Platform Configuration
1. Open `http://localhost:3000` in your browser.
2. Sign up / Login using the Supabase auth flow.
3. Navigate to **Settings -> Providers**.
4. Enter your personal **OpenRouter** or **NVIDIA NIM** API keys.
5. (Optional) Navigate to **Settings -> Integrations** and provide a **Tavily** API key for live web research capabilities.
6. Begin a new Council Session from the home dashboard!
