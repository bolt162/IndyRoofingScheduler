import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from datetime import datetime

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.note_log import NoteLog
from backend.services.jobnimbus import sync_jobs_from_jn
from backend.services.scoring import run_scoring_engine
from backend.services.note_scanner import scan_all_unscanned_jobs
from frontend.components.job_card import render_job_card

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

db = SessionLocal()

# --- JN Sync Section ---
st.sidebar.header("JobNimbus Sync")
if st.sidebar.button("🔄 Sync from JobNimbus", type="primary"):
    with st.spinner("Syncing jobs from JobNimbus..."):
        try:
            result = sync_jobs_from_jn(db)
            st.sidebar.success(f"Synced! Created: {result['created']}, Updated: {result['updated']}")
            if result["errors"]:
                st.sidebar.warning(f"{len(result['errors'])} errors during sync")
                for err in result["errors"]:
                    st.sidebar.caption(f"  {err['jn_id']}: {err['error']}")
            st.session_state["last_sync"] = result["synced_at"]
        except Exception as e:
            st.sidebar.error(f"Sync failed: {str(e)}")

last_sync = st.session_state.get("last_sync", "Never")
st.sidebar.caption(f"Last sync: {last_sync}")

# --- AI Note Scanner ---
st.sidebar.header("AI Tools")
if st.sidebar.button("🔍 Scan Job Notes (AI)"):
    with st.spinner("Scanning notes with Claude..."):
        result = scan_all_unscanned_jobs(db)
        st.sidebar.success(f"Scanned: {result['scanned']}, Failed: {result['failed']}")

# --- Scoring Section ---
st.sidebar.header("Scoring")
if st.sidebar.button("🧠 Run Scoring Engine"):
    with st.spinner("Running AI scoring engine..."):
        result = run_scoring_engine(db)
        st.sidebar.success(f"Scored {result['job_count']} jobs")
        st.session_state["scoring_result"] = result

# --- Bucket Summary ---
st.subheader("Job Queue Summary")
buckets = [
    ("To Schedule", JobBucket.TO_SCHEDULE.value),
    ("Scheduled", JobBucket.SCHEDULED.value),
    ("Pending Confirmation", JobBucket.PENDING_CONFIRMATION.value),
    ("Primary Complete", JobBucket.PRIMARY_COMPLETE.value),
    ("Waiting on Trades", JobBucket.WAITING_ON_TRADES.value),
    ("Review for Completion", JobBucket.REVIEW_FOR_COMPLETION.value),
]

cols = st.columns(len(buckets))
for i, (label, bucket_val) in enumerate(buckets):
    count = db.query(Job).filter(Job.bucket == bucket_val).count()
    cols[i].metric(label, count)

# --- Must-Build Jobs (surfaced at top) ---
must_builds = db.query(Job).filter(Job.must_build == True, Job.bucket == JobBucket.TO_SCHEDULE.value).all()
if must_builds:
    st.subheader(f"🔴 Must-Build Jobs ({len(must_builds)})")
    for job in must_builds:
        render_job_card(job.__dict__)

# --- Job List by Bucket ---
st.subheader("All Jobs")
selected_bucket = st.selectbox(
    "Filter by bucket",
    ["all"] + [b.value for b in JobBucket],
    format_func=lambda x: x.replace("_", " ").title() if x != "all" else "All Buckets",
)

if selected_bucket == "all":
    jobs = db.query(Job).order_by(Job.score.desc()).all()
else:
    jobs = db.query(Job).filter(Job.bucket == selected_bucket).order_by(Job.score.desc()).all()

if not jobs:
    st.info("No jobs found. Sync from JobNimbus to get started.")
else:
    st.caption(f"Showing {len(jobs)} jobs")
    for job in jobs:
        # Fetch notes for this job
        job_notes = db.query(NoteLog).filter(NoteLog.job_id == job.id).order_by(NoteLog.created_at.desc()).all()
        notes_dicts = [
            {"note_type": n.note_type, "note_text": n.note_text, "created_at": n.created_at}
            for n in job_notes
        ] if job_notes else None

        with st.container():
            render_job_card(job.__dict__, notes=notes_dicts)

            # Action buttons
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if not job.must_build and job.bucket == JobBucket.TO_SCHEDULE.value:
                    if st.button("Set Must-Build", key=f"mb_{job.id}"):
                        job.must_build = True
                        db.commit()
                        st.rerun()
            with col2:
                if job.bucket == JobBucket.SCHEDULED.value:
                    if st.button("Mark Not Built", key=f"nb_{job.id}"):
                        st.session_state[f"not_built_{job.id}"] = True
            with col3:
                if not job.duration_confirmed:
                    if st.button("Confirm Duration", key=f"cd_{job.id}"):
                        job.duration_confirmed = True
                        db.commit()
                        st.rerun()

            # Not Built reason selection
            if st.session_state.get(f"not_built_{job.id}"):
                reason = st.selectbox(
                    "Reason",
                    ["Weather -- Pre-Build", "Weather -- Mid-Build", "Scope Change",
                     "Crew Unavailable", "Material Issue", "Customer Related", "Other"],
                    key=f"nbr_{job.id}",
                )
                detail = st.text_input("Detail (optional)", key=f"nbd_{job.id}")
                if st.button("Confirm Not Built", key=f"nbc_{job.id}"):
                    from backend.services.notes import generate_not_built_note
                    job.bucket = JobBucket.TO_SCHEDULE.value
                    job.rescheduled_count += 1
                    job.priority_bump += 5.0
                    job.not_built_reason = reason
                    db.commit()
                    generate_not_built_note(db, job, reason, detail)
                    del st.session_state[f"not_built_{job.id}"]
                    st.rerun()

# --- Notes Review Panel ---
st.subheader("📝 System Notes (Recent)")
st.caption("These notes are generated automatically by the scheduling system. Review for accuracy before finalizing.")
all_recent_notes = db.query(NoteLog).order_by(NoteLog.created_at.desc()).limit(30).all()
if all_recent_notes:
    # Group by note type for easy scanning
    note_types = sorted(set(n.note_type for n in all_recent_notes))
    filter_type = st.selectbox(
        "Filter by type",
        ["all"] + note_types,
        format_func=lambda x: x.replace("_", " ").title() if x != "all" else "All Types",
        key="note_filter",
    )

    filtered = all_recent_notes if filter_type == "all" else [n for n in all_recent_notes if n.note_type == filter_type]

    for note in filtered:
        # Find the job name for context
        job_for_note = db.query(Job).filter(Job.id == note.job_id).first()
        job_label = job_for_note.customer_name if job_for_note else f"Job #{note.job_id}"

        type_label = note.note_type.replace("_", " ").title()
        ts = note.created_at.strftime("%m/%d/%Y %I:%M%p") if note.created_at else ""

        with st.expander(f"{type_label} — {job_label} — {ts}"):
            st.code(note.note_text, language=None)
            if note.jn_job_id:
                st.caption(f"JN ID: {note.jn_job_id}")
else:
    st.caption("No notes generated yet. Run scoring or confirm a weekly plan to generate notes.")

# --- Scoring Result ---
if "scoring_result" in st.session_state:
    result = st.session_state["scoring_result"]
    st.subheader("Last Scoring Result")
    st.markdown(f"**AI Explanation:** {result.get('ai_explanation', 'N/A')}")
    st.caption(f"Jobs scored: {result.get('job_count', 0)} | PMs available: {result.get('pm_count', 0)}")

db.close()
