import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from datetime import timedelta

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.pm import PM
from backend.models.schedule import SchedulePlan
from backend.services.notes import generate_not_built_note
from backend.services.scoring import run_scoring_engine
from frontend.components.job_card import render_job_card

st.set_page_config(page_title="Not Built", layout="wide")
st.title("Not Built Workflow")

db = SessionLocal()

# Scheduled jobs that can be marked Not Built
st.subheader("Scheduled Jobs")
scheduled = db.query(Job).filter(Job.bucket == JobBucket.SCHEDULED.value).order_by(Job.date_scheduled).all()

if not scheduled:
    st.info("No scheduled jobs.")
else:
    for job in scheduled:
        with st.container():
            render_job_card(job.__dict__, show_actions=False)

            col1, col2 = st.columns(2)
            with col1:
                reason = st.selectbox(
                    "Not Built Reason",
                    [
                        "Weather -- Pre-Build",
                        "Weather -- Mid-Build",
                        "Scope Change",
                        "Crew Unavailable",
                        "Material Issue",
                        "Customer Related",
                        "Other",
                    ],
                    key=f"reason_{job.id}",
                )
            with col2:
                detail = st.text_input("Detail", key=f"detail_{job.id}")

            # Scope Change: show multi-day options BEFORE confirm
            if reason == "Scope Change":
                st.info("Scope Change detected — this will convert to a multi-day job with crew retention.")
                scope_col1, scope_col2, scope_col3 = st.columns(3)
                with scope_col1:
                    new_duration = st.number_input(
                        "Revised total duration (days)",
                        value=max(job.duration_days, 2),
                        min_value=2,
                        max_value=14,
                        key=f"dur_{job.id}",
                    )
                with scope_col2:
                    retain_crew = st.checkbox(
                        "Retain same crew for Day 2+",
                        value=True,
                        key=f"retain_crew_{job.id}",
                    )
                with scope_col3:
                    if job.date_scheduled:
                        day2_date = job.date_scheduled + timedelta(days=1)
                        st.caption(f"Day 2 would be: {day2_date.strftime('%m/%d (%a)')}")

            if st.button("Mark Not Built", key=f"nb_btn_{job.id}", type="primary"):
                if reason == "Scope Change":
                    # Multi-day conversion with crew retention
                    job.is_multi_day = True
                    job.duration_days = new_duration
                    job.duration_confirmed = False
                    job.multi_day_current = 1  # Day 1 done (partially)

                    # Retain crew and PM for Day 2
                    retained_pm_id = job.assigned_pm_id
                    retained_crew_id = job.assigned_crew_id
                    original_date = job.date_scheduled

                    # Return to queue with elevated priority
                    job.bucket = JobBucket.TO_SCHEDULE.value
                    job.rescheduled_count += 1
                    job.priority_bump += 10.0  # Higher bump for scope change
                    job.not_built_reason = reason
                    job.date_scheduled = None
                    db.commit()

                    # Auto-create Day 2 plan entry if we have PM and date
                    if retain_crew and retained_pm_id and original_date:
                        day2_date = original_date + timedelta(days=1)
                        existing_plan = db.query(SchedulePlan).filter(
                            SchedulePlan.plan_date == day2_date,
                            SchedulePlan.pm_id == retained_pm_id,
                        ).first()

                        if existing_plan:
                            existing_plan.job_ids = existing_plan.job_ids + [job.id]
                        else:
                            new_plan = SchedulePlan(
                                plan_date=day2_date,
                                pm_id=retained_pm_id,
                                job_ids=[job.id],
                                status="draft",
                            )
                            db.add(new_plan)

                        job.bucket = JobBucket.SCHEDULED.value
                        job.date_scheduled = day2_date
                        job.assigned_pm_id = retained_pm_id
                        job.assigned_crew_id = retained_crew_id
                        db.commit()

                        pm = db.query(PM).filter(PM.id == retained_pm_id).first()
                        pm_name = pm.name if pm else "Same PM"
                        st.success(
                            f"Scope Change: Job converted to {new_duration}-day. "
                            f"Day 2 auto-scheduled for {day2_date.strftime('%m/%d')} with {pm_name}."
                        )
                    else:
                        db.commit()
                        st.success(
                            f"Scope Change: Job converted to {new_duration}-day. "
                            f"Returned to queue with elevated priority (+10). Assign Day 2 in Weekly Plan."
                        )
                else:
                    # Standard Not Built flow
                    job.bucket = JobBucket.TO_SCHEDULE.value
                    job.rescheduled_count += 1
                    job.priority_bump += 5.0
                    job.not_built_reason = reason
                    job.date_scheduled = None
                    job.assigned_pm_id = None
                    db.commit()

                # Generate note locally
                scope_detail = detail
                if reason == "Scope Change":
                    scope_detail = f"{detail}. Revised duration: {new_duration} days. Crew retained: {retain_crew}."
                note = generate_not_built_note(db, job, reason, scope_detail)
                st.code(note.note_text, language=None)

                # Auto-recalculate scores
                run_scoring_engine(db)
                st.info("Scores recalculated automatically.")
                st.rerun()

# Multi-day jobs in progress
st.subheader("Multi-Day Jobs In Progress")
multi_day = db.query(Job).filter(
    Job.is_multi_day == True,
    Job.bucket.in_([JobBucket.SCHEDULED.value, JobBucket.TO_SCHEDULE.value]),
).all()

if multi_day:
    for job in multi_day:
        with st.container():
            st.markdown(
                f"📅 **{job.customer_name}** — Day {job.multi_day_current + 1} of {job.duration_days} | "
                f"{'Scheduled' if job.bucket == JobBucket.SCHEDULED.value else 'Needs Scheduling'}"
            )
            if job.assigned_pm_id:
                pm = db.query(PM).filter(PM.id == job.assigned_pm_id).first()
                if pm:
                    st.caption(f"PM: {pm.name} | Scheduled: {job.date_scheduled}")
            render_job_card(job.__dict__, show_actions=False)
else:
    st.caption("No multi-day jobs in progress.")

# Previously Not Built jobs
st.subheader("Recently Not Built")
not_built_jobs = db.query(Job).filter(
    Job.not_built_reason != None,
    Job.bucket == JobBucket.TO_SCHEDULE.value,
    Job.rescheduled_count > 0,
    Job.is_multi_day == False,
).order_by(Job.rescheduled_count.desc()).all()

if not_built_jobs:
    for job in not_built_jobs:
        with st.container():
            st.markdown(f"🔄 **{job.customer_name}** — Rescheduled {job.rescheduled_count}x | Last reason: {job.not_built_reason}")
            if job.rescheduled_count >= 2:
                st.warning("⚠️ Customer communication recommended — rescheduled 2+ times")
            render_job_card(job.__dict__, show_actions=False)
else:
    st.caption("No recently not-built jobs.")

db.close()
