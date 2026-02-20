# Deploying the Integrations Leaderboard

## 1. Push the app to GitHub

From the project folder (`integrations_leaderboard`):

```bash
cd /Users/bt/Desktop/backend/integrations_leaderboard

# Initialize git (if not already)
git init

# Add files (.gitignore excludes .venv and leaderboard.db)
git add .
git commit -m "Integrations leaderboard app"

# Create a new repo on GitHub (github.com → New repository), then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

Use your actual GitHub username and repo name. If you use SSH: `git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git`.

---

## 2. Deploy on Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** (or [streamlit.io/cloud](https://streamlit.io/cloud)).
2. Sign in with **GitHub**.
3. Click **“New app”**.
4. Choose:
   - **Repository**: `YOUR_USERNAME/YOUR_REPO_NAME`
   - **Branch**: `main`
   - **Main file path**: `app.py`
5. Click **Deploy**.

Streamlit will install from `requirements.txt` and run `streamlit run app.py`. Your app will get a URL like `https://your-repo-name-xxxxx.streamlit.app`.

---

## Notes

- **Data**: The app uses a local SQLite file (`leaderboard.db`). On Streamlit Cloud the filesystem is ephemeral, so data is reset when the app restarts or is redeployed. For persistent data you’d need a hosted database later.
- **Secrets**: If you add API keys or secrets later, use Streamlit Cloud’s “Secrets” in the app settings (or a `.streamlit/secrets.toml` file in the repo, with secrets not committed).
- **Redeploy**: Push new commits to `main`; Streamlit can be set to redeploy automatically on push.
