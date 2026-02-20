"""
Integrations Leaderboard — Streamlit app.
CSMs submit company + integrations; overviews show counts by service and by CSM.
"""

import html
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from config import INTEGRATIONS

# Company colors (same order used for integrations: by index in INTEGRATIONS)
GREEN = "#2FFF61"
BLUE = "#14E8FF"
YELLOW = "#ECFF31"
LAVENDER = "#AB6BFF"
ORANGE = "#FFA424"
INTEGRATION_PALETTE = [GREEN, BLUE, YELLOW, LAVENDER, ORANGE]
# Fixed color per integration (by order in config) — used in form legend, table pills, and chart
INTEGRATION_COLORS = {name: INTEGRATION_PALETTE[i % len(INTEGRATION_PALETTE)] for i, name in enumerate(INTEGRATIONS)}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

DB_PATH = Path(__file__).resolve().parent / "leaderboard.db"


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            csm_name TEXT NOT NULL,
            company_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS submission_integrations (
            submission_id INTEGER NOT NULL,
            integration_name TEXT NOT NULL,
            PRIMARY KEY (submission_id, integration_name),
            FOREIGN KEY (submission_id) REFERENCES submissions(id)
        );
    """)
    conn.commit()


def submission_exists(conn, csm_name: str, company_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM submissions WHERE csm_name = ? AND company_name = ?",
        (csm_name.strip(), company_name.strip()),
    )
    return cur.fetchone() is not None


def insert_submission(conn, csm_name: str, company_name: str, integration_names: list[str]):
    cur = conn.execute(
        "INSERT INTO submissions (csm_name, company_name) VALUES (?, ?)",
        (csm_name.strip(), company_name.strip()),
    )
    submission_id = cur.lastrowid
    for name in integration_names:
        conn.execute(
            "INSERT INTO submission_integrations (submission_id, integration_name) VALUES (?, ?)",
            (submission_id, name),
        )
    conn.commit()


def delete_submission(conn, submission_id: int):
    conn.execute("DELETE FROM submission_integrations WHERE submission_id = ?", (submission_id,))
    conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
    conn.commit()


def get_submissions(
    conn,
    csm_filter: str | None = None,
    company_filter: str | None = None,
    integration_filter: list[str] | None = None,
) -> list[dict]:
    """Return submissions with integrations list. Optional filters (case-insensitive, substring for company)."""
    query = """
        SELECT s.id, s.csm_name, s.company_name, s.created_at
        FROM submissions s
    """
    params: list = []
    if integration_filter:
        query += """
            INNER JOIN submission_integrations si ON s.id = si.submission_id
            AND si.integration_name IN ({})
        """.format(",".join("?" * len(integration_filter)))
        params.extend(integration_filter)
    query += " WHERE 1=1"
    if csm_filter:
        query += " AND LOWER(s.csm_name) = LOWER(?)"
        params.append(csm_filter)
    if company_filter:
        query += " AND LOWER(s.company_name) LIKE ?"
        params.append(f"%{company_filter.strip().lower()}%")
    if integration_filter:
        query += " GROUP BY s.id"
    query += " ORDER BY s.created_at DESC"
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    out = []
    for (sid, csm, company, created) in rows:
        cur2 = conn.execute(
            "SELECT integration_name FROM submission_integrations WHERE submission_id = ? ORDER BY integration_name",
            (sid,),
        )
        integrations = [r[0] for r in cur2.fetchall()]
        out.append({"id": sid, "csm_name": csm, "company_name": company, "integrations": integrations, "created_at": created})
    return out


def get_distinct_csms(conn) -> list[str]:
    cur = conn.execute("SELECT DISTINCT csm_name FROM submissions ORDER BY csm_name")
    return [r[0] for r in cur.fetchall()]


def get_counts_by_service(conn):
    cur = conn.execute("""
        SELECT integration_name, COUNT(*) AS count
        FROM submission_integrations
        GROUP BY integration_name
        ORDER BY count DESC
    """)
    return cur.fetchall()


def get_counts_by_csm(conn):
    cur = conn.execute("""
        SELECT
            s.csm_name,
            COUNT(DISTINCT s.id) AS companies,
            COUNT(si.integration_name) AS integrations
        FROM submissions s
        LEFT JOIN submission_integrations si ON s.id = si.submission_id
        GROUP BY s.csm_name
        ORDER BY integrations DESC, companies DESC
    """)
    return cur.fetchall()


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Integrations Leaderboard", layout="wide")

# Company color theme: buttons, accents, table, pills
st.markdown(f"""
<style>
    /* Primary button = green */
    .stButton > button[kind="primary"] {{
        background-color: {GREEN} !important;
        color: #0a0a0a !important;
        border: none !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: #28e055 !important;
        color: #0a0a0a !important;
    }}
    /* Title accent */
    .company-title-wrap {{ border-bottom: 4px solid {GREEN}; padding-bottom: 0.25rem; display: inline-block; margin-bottom: 0.5rem; }}
</style>
""", unsafe_allow_html=True)

conn = get_connection()
init_db(conn)

try:
    st.markdown('<p class="company-title-wrap"><span style="font-size:2.25rem; font-weight:700;">Pump Integrations Leaderboard</span></p>', unsafe_allow_html=True)
    st.caption("Track which CSMs have gotten customers to complete integrations.")

    # ----- Form -----
    # Use a form key that changes after submit so the form re-mounts and clears (Streamlit
    # doesn't allow assigning to widget session state keys, so we can't clear inputs directly).
    if "form_clear_key" not in st.session_state:
        st.session_state["form_clear_key"] = 0
    with st.expander("Add a submission (CSM name, company, integrations)", expanded=False):
        with st.form("submission_form_" + str(st.session_state["form_clear_key"])):
            csm_name = st.text_input("CSM name", placeholder="e.g. Manny")
            company_name = st.text_input("Company name", placeholder="e.g. Acme Inc.")
            selected = st.multiselect(
                "Integrations this customer has completed",
                options=INTEGRATIONS,
                help="Select all that apply.",
            )
            # Legend: same colors as table and chart
            legend_html = " ".join(
                f'<span class="lb-pill" style="background:{INTEGRATION_COLORS[name]}; color:#0a0a0a; padding:2px 8px; border-radius:999px; margin:2px; font-size:0.8rem;">{html.escape(name)}</span>'
                for name in INTEGRATIONS
            )
            submitted = st.form_submit_button("Submit")
            if submitted:
                if not csm_name or not company_name:
                    st.error("Please enter both CSM name and company name.")
                elif not selected:
                    st.error("Please select at least one integration.")
                elif submission_exists(conn, csm_name, company_name):
                    st.error(f"A submission for **{company_name}** by **{csm_name}** already exists. Use the table below to edit or delete it.")
                else:
                    insert_submission(conn, csm_name, company_name, selected)
                    st.session_state["form_clear_key"] = st.session_state["form_clear_key"] + 1
                    st.toast(f"Recorded {company_name} for {csm_name}.")
                    st.rerun()

    # ----- Submissions table (filter + delete) -----
    st.divider()
    st.markdown(f'<h3 style="border-left: 4px solid {BLUE}; padding-left: 12px; margin-top: 0;">Submissions</h3>', unsafe_allow_html=True)
    st.caption("Filter and delete submissions. Duplicate CSM + company are blocked on submit.")
    distinct_csms = get_distinct_csms(conn)
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        csm_filter = st.selectbox("Filter by CSM", options=[None] + distinct_csms, format_func=lambda x: "All" if x is None else x, key="filter_csm")
    with filter_col2:
        company_filter = st.text_input("Filter by company (substring)", key="filter_company", placeholder="e.g. Acme")
    with filter_col3:
        integration_filter = st.multiselect("Filter by integration (has any of)", options=INTEGRATIONS, key="filter_integration")
        integration_filter = integration_filter or None
    submissions = get_submissions(conn, csm_filter=csm_filter, company_filter=company_filter or None, integration_filter=integration_filter)
    if not submissions:
        st.info("No submissions match the filters." if (csm_filter or company_filter or integration_filter) else "No submissions yet.")
    else:
        # Single continuous green header bar (no gaps) and pills
        st.markdown(f"""
        <style>
        .lb-header-bar {{ display: flex; background: {GREEN}; color: #0a0a0a; padding: 12px 16px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; margin-bottom: 24px; gap: 0; align-items: center; }}
        .lb-header-bar span {{ flex: 1; min-width: 0; }}
        .lb-header-bar .c1 {{ flex: 1.4; }}
        .lb-header-bar .c2 {{ flex: 1.8; }}
        .lb-header-bar .c3 {{ flex: 2.2; }}
        .lb-header-bar .c4 {{ flex: 0.9; }}
        .lb-pill {{ display: inline-block; color: #0a0a0a; padding: 4px 10px; border-radius: 999px; margin: 2px 4px 2px 0; font-size: 0.85rem; font-weight: 500; }}
        </style>
        <div class="lb-header-bar">
            <span class="c1">CSM</span>
            <span class="c2">Company</span>
            <span class="c3">Integrations</span>
            <span class="c4">&nbsp;</span>
        </div>
        """, unsafe_allow_html=True)
        for row in submissions:
            cols = st.columns([1.4, 1.8, 2.2, 0.9])
            with cols[0]:
                st.text(row["csm_name"])
            with cols[1]:
                st.text(row["company_name"])
            with cols[2]:
                if row["integrations"]:
                    pills_html = " ".join(
                        f'<span class="lb-pill" style="background:{INTEGRATION_COLORS.get(name, GREEN)};">{html.escape(name)}</span>'
                        for name in row["integrations"]
                    )
                    st.markdown(pills_html, unsafe_allow_html=True)
                else:
                    st.text("—")
            with cols[3]:
                if st.button("Delete", key=f"del_{row['id']}", type="secondary"):
                    delete_submission(conn, row["id"])
                    st.rerun()
        st.caption(f"Showing {len(submissions)} submission(s).")

    # ----- Overviews -----
    st.divider()
    st.markdown(f'<h3 style="border-left: 4px solid {BLUE}; padding-left: 12px; margin-top: 0;">Overview</h3>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### By service (integration count)")
        by_service = get_counts_by_service(conn)
        if by_service:
            st.dataframe(
                [{"Integration": name, "Count": count} for name, count in by_service],
                width="stretch",
                hide_index=True,
                column_config={"Count": {"alignment": "left"}},
            )
            # Bar chart with same integration colors as table and form
            df_svc = pd.DataFrame([{"Integration": r[0], "Count": r[1]} for r in by_service])
            domain_svc = [r[0] for r in by_service]
            range_svc = [INTEGRATION_COLORS.get(name, GREEN) for name in domain_svc]
            chart_svc = alt.Chart(df_svc).mark_bar().encode(
                x=alt.X("Integration", sort="-y"),
                y="Count",
                color=alt.Color("Integration", scale=alt.Scale(domain=domain_svc, range=range_svc), legend=None),
            ).properties(height=280)
            st.altair_chart(chart_svc, use_container_width=True)
        else:
            st.info("No data yet. Add a submission above.")

    with col2:
        st.markdown("#### By CSM (leaderboard)")
        by_csm = get_counts_by_csm(conn)
        if by_csm:
            st.dataframe(
                [
                    {"CSM": row[0], "Companies": row[1], "Total integrations": row[2]}
                    for row in by_csm
                ],
                width="stretch",
                hide_index=True,
            )
            df_csm = pd.DataFrame([{"CSM": r[0], "Total integrations": r[2]} for r in by_csm])
            chart_csm = alt.Chart(df_csm).mark_bar().encode(
                x=alt.X("CSM", sort="-y"),
                y="Total integrations",
                color=alt.Color("CSM", scale=alt.Scale(range=[GREEN, BLUE, YELLOW] * 5), legend=None),
            ).properties(height=280)
            st.altair_chart(chart_csm, use_container_width=True)
        else:
            st.info("No data yet. Add a submission above.")

finally:
    conn.close()
