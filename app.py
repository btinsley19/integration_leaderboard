"""
Integrations Leaderboard — Streamlit app.
CSMs submit company + integrations; overviews show counts by service and by CSM.
"""

import html
from datetime import datetime, timezone
from uuid import uuid4

import altair as alt
import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

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
# Google Sheets (persistent storage)
# -----------------------------------------------------------------------------

SHEET_HEADERS = ["submission_id", "csm_name", "company_name", "integration_name", "created_at"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _normalize(s: str) -> str:
    return (s or "").strip()


def ensure_sheet_header(worksheet: gspread.Worksheet) -> None:
    values = worksheet.get_all_values()
    if not values:
        worksheet.update("A1:E1", [SHEET_HEADERS])
        return

    header = [c.strip().lower() for c in values[0]]
    if header[: len(SHEET_HEADERS)] != SHEET_HEADERS:
        expected = ", ".join(SHEET_HEADERS)
        actual = ", ".join(values[0])
        raise ValueError(
            f"Google Sheet header row must be: {expected}. Found: {actual}. "
            "Please fix the header row (row 1) and rerun."
        )


@st.cache_resource
def get_worksheet() -> gspread.Worksheet:
    """Authorize and return the target worksheet (cached across reruns)."""
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SHEETS_SCOPES,
    )
    client = gspread.authorize(creds)
    # Prefer root-level GOOGLE_SHEETS_ID, but fall back to nested under gcp_service_account
    sheet_id = st.secrets.get("GOOGLE_SHEETS_ID") or st.secrets["gcp_service_account"].get(
        "GOOGLE_SHEETS_ID"
    )
    worksheet_name = (
        st.secrets.get("GOOGLE_SHEETS_WORKSHEET")
        or st.secrets["gcp_service_account"].get("GOOGLE_SHEETS_WORKSHEET")
        or "data"
    )
    worksheet = client.open_by_key(sheet_id).worksheet(worksheet_name)
    ensure_sheet_header(worksheet)
    return worksheet


def load_df(worksheet: gspread.Worksheet) -> pd.DataFrame:
    """Load all rows from the sheet into a DataFrame."""
    records = worksheet.get_all_records()  # uses row 1 as headers
    if not records:
        return pd.DataFrame(columns=SHEET_HEADERS)

    df = pd.DataFrame(records)
    for col in SHEET_HEADERS:
        if col not in df.columns:
            df[col] = ""

    # Normalize to strings for consistent filtering/joins
    for col in ["submission_id", "csm_name", "company_name", "integration_name", "created_at"]:
        df[col] = df[col].astype(str)
    return df


def submission_exists(df: pd.DataFrame, csm_name: str, company_name: str) -> bool:
    if df.empty:
        return False
    csm = _normalize(csm_name).lower()
    company = _normalize(company_name).lower()
    return bool(
        (
            df["csm_name"].str.strip().str.lower().eq(csm)
            & df["company_name"].str.strip().str.lower().eq(company)
        ).any()
    )


def append_submission(
    worksheet: gspread.Worksheet,
    csm_name: str,
    company_name: str,
    integration_names: list[str],
) -> str:
    submission_id = uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [
        [submission_id, _normalize(csm_name), _normalize(company_name), name, created_at]
        for name in integration_names
    ]
    worksheet.append_rows(rows, value_input_option="RAW")
    return submission_id


def delete_submission(worksheet: gspread.Worksheet, submission_id: str) -> None:
    """Delete all rows matching a submission_id (in reverse order)."""
    values = worksheet.get_all_values()
    if not values:
        return

    header = values[0]
    try:
        col_idx = [h.strip().lower() for h in header].index("submission_id")
    except ValueError:
        raise ValueError("Could not find 'submission_id' column in the Google Sheet header row.")

    rows_to_delete: list[int] = []
    for i, row in enumerate(values[1:], start=2):  # sheet rows are 1-indexed; data starts at row 2
        if len(row) > col_idx and row[col_idx] == submission_id:
            rows_to_delete.append(i)

    for row_num in reversed(rows_to_delete):
        worksheet.delete_rows(row_num)


def get_submissions(
    df: pd.DataFrame,
    csm_filter: str | None = None,
    company_filter: str | None = None,
    integration_filter: list[str] | None = None,
) -> list[dict]:
    """Return submissions with integrations list from the sheet-backed DataFrame."""
    if df.empty:
        return []

    filt = df
    if csm_filter:
        filt = filt[filt["csm_name"].str.strip().str.lower() == csm_filter.strip().lower()]
    if company_filter:
        needle = company_filter.strip().lower()
        filt = filt[filt["company_name"].str.strip().str.lower().str.contains(needle, na=False)]
    if integration_filter:
        filt = filt[filt["integration_name"].isin(integration_filter)]

    if filt.empty:
        return []

    out: list[dict] = []
    for submission_id, g in filt.groupby("submission_id", sort=False):
        integrations = (
            g["integration_name"]
            .dropna()
            .astype(str)
            .map(str.strip)
            .loc[lambda s: s != ""]
            .unique()
            .tolist()
        )
        integrations = sorted(integrations, key=lambda s: s.lower())
        out.append(
            {
                "submission_id": submission_id,
                "csm_name": g["csm_name"].iloc[0],
                "company_name": g["company_name"].iloc[0],
                "integrations": integrations,
                "created_at": g["created_at"].iloc[0],
            }
        )

    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def get_distinct_csms(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    csms = (
        df["csm_name"]
        .dropna()
        .astype(str)
        .map(str.strip)
        .loc[lambda s: s != ""]
        .unique()
        .tolist()
    )
    return sorted(csms, key=lambda s: s.lower())


def get_counts_by_service(df: pd.DataFrame) -> list[tuple[str, int]]:
    if df.empty:
        return []
    counts = df["integration_name"].value_counts()
    return [(str(name), int(count)) for name, count in counts.items()]


def get_counts_by_csm(df: pd.DataFrame) -> list[tuple[str, int, int]]:
    if df.empty:
        return []
    integrations = df.groupby("csm_name")["integration_name"].size()
    companies = df.groupby("csm_name")["company_name"].nunique()
    merged = (
        pd.DataFrame({"companies": companies, "integrations": integrations})
        .fillna(0)
        .astype(int)
        .reset_index()
        .sort_values(["integrations", "companies", "csm_name"], ascending=[False, False, True])
    )
    return [(row["csm_name"], int(row["companies"]), int(row["integrations"])) for _, row in merged.iterrows()]


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Integrations Leaderboard", layout="wide")

# Company color theme: buttons, accents, table, pills
st.markdown(
    f"""
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
    .company-title-wrap {{
        border-bottom: 4px solid {GREEN};
        padding-bottom: 0.25rem;
        display: inline-block;
        margin-bottom: 0.5rem;
    }}
</style>
""",
    unsafe_allow_html=True,
)

# Support GOOGLE_SHEETS_ID either at the root level of secrets or nested under
# [gcp_service_account] (some users put it there by mistake).
has_sa = "gcp_service_account" in st.secrets
root_sheets_id = st.secrets.get("GOOGLE_SHEETS_ID")
nested_sheets_id = (
    st.secrets["gcp_service_account"].get("GOOGLE_SHEETS_ID")
    if has_sa and isinstance(st.secrets["gcp_service_account"], dict)
    else None
)
effective_sheets_id = root_sheets_id or nested_sheets_id

if not has_sa or not effective_sheets_id:
    st.error(
        "Missing Streamlit secrets for Google Sheets. You need:\n"
        "- `gcp_service_account` (service account JSON fields)\n"
        "- `GOOGLE_SHEETS_ID` (from the sheet URL)\n"
        "- optional `GOOGLE_SHEETS_WORKSHEET` (tab name, default: `data`)\n"
    )
    st.stop()

try:
    worksheet = get_worksheet()
except Exception as e:
    st.error(f"Could not connect to Google Sheets: {e}")
    st.stop()

df = load_df(worksheet)

st.markdown(
    '<p class="company-title-wrap"><span style="font-size:2.25rem; font-weight:700;">Pump Integrations Leaderboard</span></p>',
    unsafe_allow_html=True,
)
st.caption("Track which CSMs have gotten customers to complete integrations.")

# ----- Form -----
# Use a form key that changes after submit so the form re-mounts and clears.
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
        legend_html = " ".join(
            f'<span style="background:{INTEGRATION_COLORS[name]}; color:#0a0a0a; padding:2px 8px; border-radius:999px; margin:2px; font-size:0.8rem; display:inline-block;">{html.escape(name)}</span>'
            for name in INTEGRATIONS
        )
        st.markdown(
            f'<div style="margin-top:6px; margin-bottom:8px;"><span style="font-size:0.85rem; color:#666;">Integration colors:</span> {legend_html}</div>',
            unsafe_allow_html=True,
        )
        submitted = st.form_submit_button("Submit", type="primary")
        if submitted:
            if not csm_name or not company_name:
                st.error("Please enter both CSM name and company name.")
            elif not selected:
                st.error("Please select at least one integration.")
            elif submission_exists(df, csm_name, company_name):
                st.error(
                    f"A submission for **{company_name}** by **{csm_name}** already exists. "
                    "Use the table below to delete it if needed."
                )
            else:
                append_submission(worksheet, csm_name, company_name, selected)
                st.session_state["form_clear_key"] = st.session_state["form_clear_key"] + 1
                st.toast(f"Recorded {company_name} for {csm_name}.")
                st.rerun()

# ----- Submissions table (filter + delete) -----
st.divider()
st.markdown(
    f'<h3 style="border-left: 4px solid {BLUE}; padding-left: 12px; margin-top: 0;">Submissions</h3>',
    unsafe_allow_html=True,
)
st.caption("Filter and delete submissions. Duplicate CSM + company are blocked on submit.")
distinct_csms = get_distinct_csms(df)
filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    csm_filter = st.selectbox(
        "Filter by CSM",
        options=[None] + distinct_csms,
        format_func=lambda x: "All" if x is None else x,
        key="filter_csm",
    )
with filter_col2:
    company_filter = st.text_input("Filter by company (substring)", key="filter_company", placeholder="e.g. Acme")
with filter_col3:
    integration_filter = st.multiselect(
        "Filter by integration (has any of)",
        options=INTEGRATIONS,
        key="filter_integration",
    )
    integration_filter = integration_filter or None

submissions = get_submissions(
    df,
    csm_filter=csm_filter,
    company_filter=company_filter or None,
    integration_filter=integration_filter,
)
if not submissions:
    st.info(
        "No submissions match the filters."
        if (csm_filter or company_filter or integration_filter)
        else "No submissions yet."
    )
else:
    st.markdown(
        f"""
        <style>
        .lb-header-bar {{ display: flex; background: {GREEN}; color: #0a0a0a; padding: 12px 16px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; margin-bottom: 28px; gap: 0; align-items: center; }}
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
        """,
        unsafe_allow_html=True,
    )
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
            if st.button("Delete", key=f"del_{row['submission_id']}", type="secondary"):
                delete_submission(worksheet, row["submission_id"])
                st.rerun()
    st.caption(f"Showing {len(submissions)} submission(s).")

# ----- Overviews -----
st.divider()
st.markdown(
    f'<h3 style="border-left: 4px solid {BLUE}; padding-left: 12px; margin-top: 0;">Overview</h3>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### By service (integration count)")
    by_service = get_counts_by_service(df)
    if by_service:
        st.dataframe(
            [{"Integration": name, "Count": count} for name, count in by_service],
            width="stretch",
            hide_index=True,
            column_config={"Count": {"alignment": "left"}},
        )
        df_svc = pd.DataFrame([{"Integration": r[0], "Count": r[1]} for r in by_service])
        domain_svc = [r[0] for r in by_service]
        range_svc = [INTEGRATION_COLORS.get(name, GREEN) for name in domain_svc]
        chart_svc = (
            alt.Chart(df_svc)
            .mark_bar()
            .encode(
                x=alt.X("Integration", sort="-y"),
                y="Count",
                color=alt.Color(
                    "Integration",
                    scale=alt.Scale(domain=domain_svc, range=range_svc),
                    legend=None,
                ),
            )
            .properties(height=280)
        )
        st.altair_chart(chart_svc, use_container_width=True)
    else:
        st.info("No data yet. Add a submission above.")

with col2:
    st.markdown("#### By CSM (leaderboard)")
    by_csm = get_counts_by_csm(df)
    if by_csm:
        st.dataframe(
            [{"CSM": row[0], "Companies": row[1], "Total integrations": row[2]} for row in by_csm],
            width="stretch",
            hide_index=True,
            column_config={
                "Companies": {"alignment": "left"},
                "Total integrations": {"alignment": "left"},
            },
        )
        df_csm = pd.DataFrame([{"CSM": r[0], "Total integrations": r[2]} for r in by_csm])
        chart_csm = (
            alt.Chart(df_csm)
            .mark_bar()
            .encode(
                x=alt.X("CSM", sort="-y"),
                y="Total integrations",
                color=alt.Color("CSM", scale=alt.Scale(range=INTEGRATION_PALETTE * 10), legend=None),
            )
            .properties(height=280)
        )
        st.altair_chart(chart_csm, use_container_width=True)
    else:
        st.info("No data yet. Add a submission above.")
