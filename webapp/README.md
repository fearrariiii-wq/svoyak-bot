# webapp/README

This is a skeleton mini-app for editing code via an AI backend. Important security notes:
- Never store OpenAI or GitHub tokens in the frontend. Keep them as environment variables on Railway (or another secure host).
- The frontend is served as a Telegram Web App. Configure MINIAPP_URL to point to the deployed frontend.

Deployment steps (high level):
1. Deploy webapp/backend (FastAPI) to Railway. Set environment variables OPENAI_API_KEY and GITHUB_TOKEN in Railway project settings.
2. Deploy webapp/frontend as static site (Railway, Vercel, or serve it from backend).
3. Set MINIAPP_URL to the frontend URL in your bot environment variables.
4. Add a GitHub App or PAT with repo permissions to allow server to commit changes.
