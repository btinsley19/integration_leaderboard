# Integrations Leaderboard — Overview

## Task

Build an internal leaderboard/dashboard for Customer Success Managers (CSMs) to track how many integrations customers have completed. Companies can integrate GitHub, Datadog, Cursor, OpenAI, ClickHouse, etc., and see spend in the product dashboard. CSMs are incentivized to get customers to integrate; this app tracks who has driven the most integrations.

## Goals

- **Data entry**: Each CSM can submit their name, the company name, and which integrations that customer has completed (multi-select).
- **No login**: Simple form submission; no authentication.
- **Single source of truth for integrations**: A maintained list of integration names in the backend; new integrations are added there and automatically appear as options on the frontend.
- **Overview analytics**:
  - **By service**: Total count per integration (e.g. GitHub 12, Datadog 8, Cursor 5).
  - **By CSM**: Count per CSM (e.g. you 15, Manny 10, Kate 8) so the leaderboard/prize is clear.

## How We Will Accomplish It

### Stack

- **Python 3.x** with **Streamlit** for the UI (forms, tables, charts).
- **Google Sheets** for persistence so data survives Streamlit Cloud restarts/sleep.
- **Single app**: One Streamlit app; no separate frontend or API.

### High-Level Architecture

1. **Integrations list**  
   Stored in a config file or a small Python module (e.g. `integrations.txt` or `config.py`). The app reads this list to populate the multi-select on the form. Adding a new integration = adding one line; the form options update automatically.

2. **Data model**  
   - **Submissions**: One row per company–CSM pair: CSM name, company name, list of integration names (or a normalized table linking submission → integration).  
   - **Integrations catalog**: Names of all allowed integrations (used for dropdown + for aggregations).

3. **App structure**  
   - **Form page/section**: Fields for CSM name, company name, and multi-select for integrations (options from the backend list). Submit writes to Google Sheets.  
   - **Overview section(s)**:
     - **By service**: For each integration, count how many times it appears across submissions (or how many companies have it). Display as table and/or bar chart.  
     - **By CSM**: For each CSM, count submissions (companies) and/or total integration instances. Display as table and/or bar chart (leaderboard).

4. **Deployment**  
   Run locally with `streamlit run app.py` or deploy to Streamlit Community Cloud (or similar) when ready.

### Deliverables (Planned)

| Item | Description |
|------|-------------|
| `OVERVIEW.md` | This document — task and plan. |
| `requirements.txt` | Python dependencies (Streamlit, etc.). |
| Virtual environment | Isolated env so packages are not installed globally. |
| Integrations list | Backend list of integration names (file or module). |
| Google Sheets backing store | Sheet used as the database (service account auth via Streamlit secrets). |
| Streamlit app | Form + “By service” and “By CSM” overviews. |

### Success Criteria

- CSMs can submit their name, company, and completed integrations from a single form.
- New integrations added to the backend list show up as form options without code changes to the UI.
- Overview shows correct counts by integration (service) and by CSM.
- No login required; data persisted in Google Sheets.

---

## Setup (this project)

- **Virtual environment**: All dependencies live in the project’s `.venv` so you don’t need them installed globally.
- **Activate** (optional; you can also call the venv’s Python/pip directly):
  - macOS/Linux: `source .venv/bin/activate`
  - Windows: `.venv\Scripts\activate`
- **Install/refresh dependencies**:  
  `pip install -r requirements.txt` (run this inside the activated venv, or use `.venv/bin/pip install -r requirements.txt` from the project root).
- **Run the app** (once the Streamlit app exists):  
  `streamlit run app.py` (or `.venv/bin/streamlit run app.py` if the venv isn’t activated).

---

*Last updated: Feb 2025*
