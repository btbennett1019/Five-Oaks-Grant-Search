from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from rfp_core import STAGES, list_opportunities, run_daily, run_scan, scan_log_rows, update_opportunities

st.set_page_config(page_title="Five Oaks RFP Tracker", page_icon="🦆", layout="wide")

CSS = """
<style>
:root { --green:#143526; --green2:#1f4d37; --gold:#c69a3c; --cream:#f7f3e9; --muted:#6d766e; --red:#9a3412; --blue:#1d4f74; }
.stApp { background: linear-gradient(180deg,#f7f3e9 0%,#f3efe5 38%,#ffffff 100%); }
.block-container { padding-top: 1.15rem; padding-bottom: 3rem; max-width: 1500px; }
[data-testid="stSidebar"] { background:#122e22; }
[data-testid="stSidebar"] * { color:#f7f3e9 !important; }
[data-testid="stSidebar"] .stButton button { background:#c69a3c; color:#1b1b1b !important; border:0; font-weight:850; border-radius:12px; }
.hero { background:linear-gradient(135deg,#143526 0%,#1f4d37 52%,#665222 100%); color:white; border-radius:26px; padding:32px 36px; box-shadow:0 18px 48px rgba(20,53,38,.24); margin-bottom:20px; border:1px solid rgba(255,255,255,.14); }
.eyebrow { color:#e8c979; text-transform:uppercase; letter-spacing:.16em; font-size:.78rem; font-weight:900; }
.title { font-size:2.6rem; line-height:1.05; font-weight:950; margin:8px 0; }
.subtitle { color:#f3ead2; font-size:1.04rem; max-width:1050px; }
.card { background:rgba(255,255,255,.95); border:1px solid rgba(20,53,38,.10); border-radius:18px; padding:18px 20px; box-shadow:0 10px 30px rgba(20,53,38,.08); }
.metric-label { color:#6d766e; font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; font-weight:850; }
.metric-value { color:#143526; font-size:2rem; font-weight:950; margin-top:3px; }
.metric-note { color:#6d766e; font-size:.86rem; }
.opp-card { background:#fff; border:1px solid rgba(20,53,38,.11); border-left:6px solid #c69a3c; border-radius:18px; padding:18px 19px; margin:10px 0; box-shadow:0 10px 25px rgba(20,53,38,.07); }
.opp-title { font-size:1.06rem; font-weight:900; color:#143526; margin-bottom:6px; }
.opp-meta { color:#697268; font-size:.88rem; }
.badge { display:inline-block; padding:4px 9px; border-radius:999px; font-size:.75rem; font-weight:850; margin-right:6px; }
.badge-fit { background:#eaf3ec; color:#1f4d37; }
.badge-urgent { background:#fff1e8; color:#9a3412; }
.badge-stage { background:#eef1f3; color:#334155; }
.badge-blue { background:#e6efff; color:#1d4f74; }
.section-head { color:#143526; font-size:1.28rem; font-weight:950; margin-top:18px; margin-bottom:4px; }
.small-note { color:#6d766e; font-size:.88rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def days_until(close_date: str) -> int | None:
    if not close_date:
        return None
    try:
        d = datetime.fromisoformat(str(close_date)[:10]).date()
        return (d - date.today()).days
    except Exception:
        return None


def deadline_badge(close_date: str) -> str:
    d = days_until(close_date)
    if d is None:
        return '<span class="badge badge-stage">No deadline</span>'
    if d < 0:
        return '<span class="badge badge-stage">Closed</span>'
    if d <= 14:
        return f'<span class="badge badge-urgent">Due in {d} days</span>'
    if d <= 45:
        return f'<span class="badge badge-urgent">Due in {d} days</span>'
    return f'<span class="badge badge-stage">Due in {d} days</span>'


def fit_badge(score: int) -> str:
    return f'<span class="badge badge-fit">Fit {score}</span>'


def stage_badge(stage: str) -> str:
    return f'<span class="badge badge-stage">{stage or "New"}</span>'


st.markdown("""
<div class="hero">
  <div class="eyebrow">Five Oaks Ag Research and Education Center</div>
  <div class="title">RFP & Grant Opportunity Tracker</div>
  <div class="subtitle">A professional dashboard that searches for relevant funding opportunities, tracks deadlines, scores fit, and keeps your grant pipeline organized.</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🦆 RFP Tracker")
    st.caption("Daily scan + grant pipeline")
    if st.button("Run scan now", type="primary", use_container_width=True):
        with st.spinner("Searching Grants.gov and monitored RFP pages..."):
            new_rows = run_scan()
        st.success(f"Scan complete. New opportunities: {len(new_rows)}")
        st.rerun()
    if st.button("Run daily workflow", use_container_width=True):
        with st.spinner("Running scan and optional email alerts..."):
            result = run_daily()
        st.success(f"Done. New: {result['new_count']} | Email sent: {result['email_sent']}")
        st.rerun()
    st.divider()
    st.markdown("### Daily automation")
    st.write("Use `INSTALL_DAILY_SCAN_WINDOWS.bat` to schedule the daily scan at 7:00 AM.")

rows = list_opportunities(include_archived=False)
df = pd.DataFrame(rows) if rows else pd.DataFrame()

if df.empty:
    c1, c2 = st.columns([2, 1])
    with c1:
        st.info("No opportunities yet. Click **Run scan now** in the sidebar to begin.")
    with c2:
        st.markdown("<div class='card'><div class='metric-label'>System status</div><div class='metric-value'>Ready</div><div class='metric-note'>Database initialized after first scan.</div></div>", unsafe_allow_html=True)
    st.stop()

for col in ["fit_score", "is_archived"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

urgent_count = 0
for cd in df.get("closing_date", pd.Series(dtype=str)).fillna(""):
    d = days_until(cd)
    if d is not None and 0 <= d <= 30:
        urgent_count += 1
high_fit_count = int((df["fit_score"] >= 60).sum())
in_motion_count = int(df["stage"].fillna("New").isin(["Concepting", "Writing", "Submitted"]).sum())

m1, m2, m3, m4 = st.columns(4)
metrics = [
    (m1, "Active records", len(df), "Current non-archived opportunities"),
    (m2, "High-fit", high_fit_count, "Fit score ≥ 60"),
    (m3, "Due ≤ 30 days", urgent_count, "Needs decision or action"),
    (m4, "In motion", in_motion_count, "Concepting, writing, or submitted"),
]
for col, label, value, note in metrics:
    col.markdown(f"<div class='card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div><div class='metric-note'>{note}</div></div>", unsafe_allow_html=True)

st.markdown("<div class='section-head'>Top Priority Opportunities</div>", unsafe_allow_html=True)
for _, row in df.sort_values(["fit_score", "closing_date"], ascending=[False, True]).head(5).iterrows():
    rd = row.to_dict()
    st.markdown(
        f"""
        <div class="opp-card">
          <div class="opp-title">{rd.get('title','')}</div>
          <div>{fit_badge(int(rd.get('fit_score',0) or 0))}{deadline_badge(rd.get('closing_date',''))}{stage_badge(rd.get('stage','New'))}</div>
          <div class="opp-meta">{rd.get('funder','')} • {rd.get('source','')} • {rd.get('fit_reason','')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

tab_pipeline, tab_detail, tab_calendar, tab_export, tab_log = st.tabs(["Pipeline", "Opportunity Detail", "Deadline View", "Export", "Scan History"])

with tab_pipeline:
    st.markdown("### Grant Pipeline")
    f1, f2, f3, f4 = st.columns(4)
    min_fit = f1.slider("Minimum fit score", 0, 100, 0)
    stages = sorted(df["stage"].fillna("New").unique().tolist())
    selected_stages = f2.multiselect("Stage", stages, default=stages)
    sources = sorted(df["source"].fillna("").unique().tolist())
    selected_sources = f3.multiselect("Source", sources, default=sources)
    urgent_only = f4.checkbox("Due in 45 days")

    filtered = df[(df["fit_score"] >= min_fit) & (df["stage"].fillna("New").isin(selected_stages)) & (df["source"].fillna("").isin(selected_sources))].copy()
    if urgent_only:
        filtered = filtered[filtered["closing_date"].fillna("").apply(lambda x: (days_until(x) is not None and 0 <= days_until(x) <= 45))]

    editable_cols = [
        "id", "fit_score", "stage", "title", "funder", "source", "opening_date", "closing_date",
        "owner", "project_idea", "notes", "award_amount", "match_required", "eligibility", "url", "is_archived",
    ]
    edited = st.data_editor(
        filtered[[c for c in editable_cols if c in filtered.columns]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("ID"),
            "fit_score": st.column_config.ProgressColumn("Fit", min_value=0, max_value=100),
            "stage": st.column_config.SelectboxColumn("Stage", options=STAGES),
            "title": st.column_config.TextColumn("Title", width="large"),
            "url": st.column_config.LinkColumn("URL"),
            "project_idea": st.column_config.TextColumn("Project Idea", width="large"),
            "notes": st.column_config.TextColumn("Notes", width="large"),
            "is_archived": st.column_config.CheckboxColumn("Archive"),
        },
        disabled=["id", "fit_score", "title", "funder", "source", "opening_date", "closing_date", "url"],
    )
    if st.button("Save pipeline changes", type="primary"):
        update_opportunities(edited.to_dict(orient="records"))
        st.success("Saved.")
        st.rerun()

with tab_detail:
    st.markdown("### Opportunity Detail")
    selected_id = st.selectbox("Select opportunity", df["id"].tolist(), format_func=lambda x: df.loc[df["id"] == x, "title"].iloc[0])
    row = df[df["id"] == selected_id].iloc[0].to_dict()
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"#### {row.get('title','')}")
        st.write(f"**Funder:** {row.get('funder','')}")
        st.write(f"**Source:** {row.get('source','')}")
        st.write(f"**Opening date:** {row.get('opening_date') or 'Not detected'}")
        st.write(f"**Closing date:** {row.get('closing_date') or 'Not detected'}")
        st.write(f"**Fit score:** {row.get('fit_score','')}")
        st.write(f"**Fit reason:** {row.get('fit_reason','')}")
        if row.get("url"):
            st.link_button("Open RFP / source page", row["url"])
    with c2:
        st.markdown("#### Recommended angle")
        st.write(row.get("project_idea") or "Review for Five Oaks fit.")
        st.markdown("#### Current stage")
        st.write(row.get("stage") or "New")
    st.markdown("#### Summary")
    st.write(row.get("summary") or "No summary available.")
    st.markdown("#### Internal Notes")
    st.write(row.get("notes") or "No notes yet. Add notes in the Pipeline tab.")

with tab_calendar:
    st.markdown("### Deadline View")
    cal = df.copy()
    cal["days_until_close"] = cal["closing_date"].fillna("").apply(days_until)
    cal = cal.sort_values(["days_until_close", "fit_score"], ascending=[True, False], na_position="last")
    show_cols = ["title", "funder", "stage", "fit_score", "opening_date", "closing_date", "days_until_close", "owner", "url"]
    st.dataframe(cal[[c for c in show_cols if c in cal.columns]], use_container_width=True, hide_index=True)

with tab_export:
    st.markdown("### Export Grant Tracker")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv, file_name="five_oaks_rfp_tracker.csv", mime="text/csv")

with tab_log:
    st.markdown("### Scan History")
    log_df = pd.DataFrame(scan_log_rows())
    st.dataframe(log_df, use_container_width=True, hide_index=True)
