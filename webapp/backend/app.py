import os
import base64
import time
import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ADMIN_TOKENS = [t.strip() for t in os.getenv("ADMIN_TOKENS", "").split(',') if t.strip()]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GITHUB_API = "https://api.github.com"

class EditRequest(BaseModel):
    repo: str  # owner/repo
    path: str  # file path in repo
    description: str  # what change to make
    branch_prefix: Optional[str] = "ai-edit"

async def call_openai_system(user_prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OpenAI key not configured on server")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a code assistant. When asked to modify a file, output ONLY the full new file contents exactly as the file should be (no explanation)."},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 5000,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        try:
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OpenAI API error: {e} - {r.text}")
        data = r.json()

    # Extract assistant content
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(status_code=500, detail="Unexpected OpenAI response format")
    return content

async def github_api_get(path: str, params=None):
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(GITHUB_API + path, headers=headers, params=params)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=f"GitHub GET {path} error: {r.text}")
        return r.json()

async def github_api_post(path: str, payload: dict):
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GITHUB_API + path, headers=headers, json=payload)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=f"GitHub POST {path} error: {r.text}")
        return r.json()

async def github_api_put(path: str, payload: dict):
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.put(GITHUB_API + path, headers=headers, json=payload)
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=f"GitHub PUT {path} error: {r.text}")
        return r.json()

@app.post('/api/ai-edit')
async def ai_edit(req: EditRequest, request: Request):
    # Simple auth: require header Authorization: Bearer <token> where token is in ADMIN_TOKENS
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not ADMIN_TOKENS:
        raise HTTPException(status_code=500, detail="Server ADMIN_TOKENS not configured")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth.split()[1].strip()
    if token not in ADMIN_TOKENS:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    if not OPENAI_API_KEY or not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY or GITHUB_TOKEN not configured on server")

    # Validate repo format
    try:
        owner, repo = req.repo.split("/")
    except Exception:
        raise HTTPException(status_code=400, detail="repo must be in owner/repo format")

    # Get repository info to find default branch
    repo_info = await github_api_get(f"/repos/{owner}/{repo}")
    default_branch = repo_info.get("default_branch", "main")

    # Get file content from default branch
    try:
        file_info = await github_api_get(f"/repos/{owner}/{repo}/contents/{req.path}", params={"ref": default_branch})
    except HTTPException as e:
        # If file not found on default branch, return error
        raise

    if isinstance(file_info, dict) and file_info.get("encoding") == "base64":
        original_content = base64.b64decode(file_info["content"]).decode('utf-8')
        original_sha = file_info.get("sha")
    else:
        raise HTTPException(status_code=500, detail="Could not read file content from GitHub")

    # Build prompt for OpenAI
    prompt = (
        f"You are given the full contents of a single file from a Python project.\n"
        f"File path: {req.path}\n\n"
        f"Original file content begins below:\n````\n{original_content}\n````\n\n"
        f"Task: {req.description}\n\n"
        "Produce ONLY the full, updated file contents (no explanations, no file headers). "
        "Make sure the output is valid UTF-8 text representing the entire file after the change."
    )

    # Call OpenAI to produce new file contents
    new_content = await call_openai_system(prompt)

    # Normalize new_content: strip leading/trailing ``` if present
    if new_content.strip().startswith("```"):
        # remove code fence
        # support ```python or ```
        parts = new_content.split('\n')
        if parts[0].startswith("```"):
            parts = parts[1:]
        if parts[-1].strip().endswith("```"):
            parts = parts[:-1]
        new_content = "\n".join(parts)

    # Create a branch
    branch_name = f"{req.branch_prefix}/{int(time.time())}"

    # Get commit SHA of default branch
    ref_info = await github_api_get(f"/repos/{owner}/{repo}/git/ref/heads/{default_branch}")
    base_sha = ref_info.get("object", {}).get("sha")
    if not base_sha:
        raise HTTPException(status_code=500, detail="Could not determine base commit SHA")

    # Create new ref (branch)
    try:
        await github_api_post(f"/repos/{owner}/{repo}/git/refs", {"ref": f"refs/heads/{branch_name}", "sha": base_sha})
    except HTTPException as e:
        # If branch exists, ignore
        if e.status_code == 422:
            pass
        else:
            raise

    # Update file in the new branch
    content_b64 = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')
    message = f"AI edit: {req.description}"

    update_payload = {
        "message": message,
        "content": content_b64,
        "branch": branch_name,
        "sha": original_sha,
    }

    updated = await github_api_put(f"/repos/{owner}/{repo}/contents/{req.path}", update_payload)

    # Create a Pull Request
    pr_title = message
    pr_body = (
        f"AI generated edit for `{req.path}`\n\nDescription: {req.description}\n\n"
        "Please review the changes."
    )
    pr_payload = {"title": pr_title, "head": branch_name, "base": default_branch, "body": pr_body}
    pr = await github_api_post(f"/repos/{owner}/{repo}/pulls", pr_payload)

    return {
        "status": "ok",
        "pr_url": pr.get("html_url"),
        "branch": branch_name,
        "commit": updated.get("commit", {}).get("sha")
    }

@app.get('/api/status')
async def status():
    return {"status": "ok", "openai": bool(OPENAI_API_KEY), "github": bool(GITHUB_TOKEN), "admin_tokens": len(ADMIN_TOKENS)}
