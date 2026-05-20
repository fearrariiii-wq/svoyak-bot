# Deployment and setup

This document lists what to set and how to deploy the backend and frontend. I implemented Telegram init_data verification and a short‑lived JWT flow.

Required environment variables (backend):
- OPENAI_API_KEY  - OpenAI API key
- GITHUB_TOKEN    - GitHub PAT with repo access to create branches/files/PRs
- TELEGRAM_BOT_TOKEN - Telegram bot token (for init_data verification)
- ADMIN_JWT_SECRET - secret to sign the admin JWTs (change from default)
- JWT_EXPIRE_MINUTES - how long the JWTs are valid (in minutes). Defaults to 60.
- ADMIN_TOKENS (optional) - comma-separated static admin tokens that bypass JWT (useful for quick testing)
- OPENAI_MODEL (optional) - e.g. gpt-4o-mini

Notes:
- The admin panel is intentionally open for this project: any valid Telegram WebApp init_data will receive a short-lived JWT. Do NOT expose the WebApp publicly if you are concerned about access.

Quick local test:
1. Set env vars (example):

   export OPENAI_API_KEY="sk_..."
   export GITHUB_TOKEN="ghp_..."
   export TELEGRAM_BOT_TOKEN="..."
   export ADMIN_JWT_SECRET="someverysecret"
   export JWT_EXPIRE_MINUTES="60"

2. Start backend:
   python -m venv venv
   source venv/bin/activate
   pip install -r webapp/backend/requirements.txt
   uvicorn webapp.backend.app:app --host 0.0.0.0 --port 8000

3. Serve frontend (for testing you can use a simple static server):
   python -m http.server 3000 --directory webapp/frontend

4. Open frontend in browser (http://localhost:3000) and paste WebApp init_data from Telegram Web App.


Deployment to Railway (recommended):
- Create a new project on Railway and link this GitHub repo.
- Add the required environment variables in Railway (see above).
- Deploy the backend as a service (choose Python, run uvicorn webapp.backend.app:app --host 0.0.0.0 --port $PORT).
- Serve frontend as static site (Railway static service) or host on Vercel/Netlify and set its origin as the webapp host.

If you want, I can continue and automate the Railway deploy via GitHub Actions; I will need a RAILWAY_TOKEN in GitHub Secrets or you can add the Railway GitHub App to the repository.
