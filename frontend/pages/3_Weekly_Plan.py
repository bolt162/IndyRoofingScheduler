import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import streamlit as st
from datetime import date, timedelta

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.pm import PM
from backend.models.schedule import SchedulePlan
from backend.models.settings import SystemSettings
from backend.services.notes import generate_scheduling_notes
from backend.services.scoring import run_scoring_engine
from backend.services.weather import get_forecast
from frontend.components.weather_badge import render_weather_badge

st.set_page_config(page_title="Weekly Plan", layout="wide")
st.title("Weekly Plan Builder")

db = SessionLocal()


# --- Helper: get blocked weeks ---
def _get_blocked_weeks(db):
    setting = db.query(SystemSettings).filter(SystemSettings.key == "blocked_weeks").first()
    if setting and setting.value:
        return json.loads(setting.value)
    return []


def _is_day_blocked(day_date, blocked_weeks):
    """Check if a day falls within any blocked week (blocked weeks are stored as Monday dates)."""
    for bw in blocked_weeks:
        try:
            block_start = date.fromisoformat(bw)
            block_end = block_start + timedelta(days=6)
            if block_start <= day_date <= block_end:
                return True
        except (ValueError, TypeError):
            continue
    return False


# Week selection
today = date.today()
monday = today - timedelta(days=today.weekday())
week_start = st.date_input("Week starting", value=monday)
week_dates = [week_start + timedelta(days=i) for i in range(7)]

# Check if this week is blocked
blocked_weeks = _get_blocked_weeks(db)
week_is_blocked = _is_day_blocked(week_start, blocked_weeks)
if week_is_blocked:
    st.error("🚫 THIS WEEK IS BLOCKED — No builds should be scheduled.")

# Available PMs
pms = db.query(PM).filter(PM.is_active == True).all()
if not pms:
    st.warning("No PMs configured. Add PMs in Settings first.")
    db.close()
    st.stop()

st.subheader("PM Availability")
available_pms = st.multiselect(
    "Select available PMs for this week",
    options=[(pm.id, pm.name) for pm in pms],
    default=[(pm.id, pm.name) for pm in pms],
    format_func=lambda x: x[1],
)

# Sidebar actions
st.sidebar.header("Actions")
if st.sidebar.button("🔄 Recalculate Scores", type="primary"):
    with st.spinner("Rescoring all jobs..."):
        pm_ids = [p[0] for p in available_pms] if available_pms else None
        result = run_scoring_engine(db, pm_ids=pm_ids)
        st.sidebar.success(f"Rescored {result['job_count']} jobs")
        st.rerun()

# --- Weather Forecast Overlay ---
st.sidebar.header("Weather")
if st.sidebar.button("🌤️ Load Week Forecast"):
    # Use Indianapolis as default center (or first job with coords)
    sample_job = db.query(Job).filter(Job.latitude != None).first()
    lat = sample_job.latitude if sample_job else 39.7684
    lon = sample_job.longitude if sample_job else -86.1581

    forecasts = {}
    for d in week_dates:
        fc = get_forecast(lat, lon, d.isoformat())
        if fc:
            forecasts[d.isoformat()] = fc
    st.session_state["week_forecasts"] = forecasts
    st.sidebar.success(f"Loaded forecast for {len(forecasts)} days")

# Get schedulable jobs (after potential rescore)
to_schedule = db.query(Job).filter(Job.bucket == JobBucket.TO_SCHEDULE.value).order_by(Job.score.desc()).all()

st.subheader(f"Jobs Available: {len(to_schedule)}")

# Weekly grid
st.subheader("Weekly Schedule")
day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
cols = st.columns(7)

week_forecasts = st.session_state.get("week_forecasts", {})

for i, (day_date, col) in enumerate(zip(week_dates, cols)):
    with col:
        # Blocked day highlighting
        day_blocked = _is_day_blocked(day_date, blocked_weeks)
        if day_blocked:
            st.markdown(f"**{day_names[i]}** 🚫")
        else:
            st.markdown(f"**{day_names[i]}**")
        st.caption(day_date.strftime("%m/%d"))

        # Weather overlay for this day
        fc = week_forecasts.get(day_date.isoformat())
        if fc:
            temp_hi = fc.get("temp_max", "?")
            temp_lo = fc.get("temp_min", "?")
            precip = fc.get("precipitation", 0)
            wind = fc.get("wind_max", 0)

            # Color-code weather
            if precip > 0.1 or wind > 25:
                weather_color = "#F44336"  # Red
                weather_icon = "🛑"
            elif precip > 0 or wind > 15:
                weather_color = "#FFC107"  # Yellow
                weather_icon = "⚠️"
            else:
                weather_color = "#4CAF50"  # Green
                weather_icon = "✅"

            st.markdown(
                f"<div style='background:{weather_color}20;border-left:3px solid {weather_color};padding:4px 6px;font-size:0.8em;border-radius:3px;margin-bottom:4px'>"
                f"{weather_icon} {temp_lo:.0f}-{temp_hi:.0f}°F<br>"
                f"💨{wind:.0f}mph 🌧️{precip:.1f}in"
                f"</div>",
                unsafe_allow_html=True,
            )

        if day_blocked:
            st.markdown(
                "<div style='background:#F4433620;padding:4px;border-radius:3px;text-align:center;font-size:0.85em'>BLOCKED</div>",
                unsafe_allow_html=True,
            )

        # Show existing plans for this day
        plans = db.query(SchedulePlan).filter(SchedulePlan.plan_date == day_date).all()
        for plan in plans:
            pm = db.query(PM).filter(PM.id == plan.pm_id).first()
            pm_name = pm.name if pm else "Unassigned"
            status_icon = "✅" if plan.status == "confirmed" else "📋"
            st.markdown(f"{status_icon} {pm_name}")
            st.caption(f"{len(plan.job_ids)} jobs")

        # Capacity indicator
        total_assigned = sum(len(p.job_ids) for p in plans)
        total_capacity = sum(pm.baseline_capacity for pm_id, pm_name in available_pms for pm in pms if pm.name == pm_name)
        if total_capacity > 0:
            st.progress(min(total_assigned / max(total_capacity, 1), 1.0), text=f"{total_assigned}/{total_capacity}")

# Job assignment
st.subheader("Assign Jobs")
if to_schedule:
    assign_col1, assign_col2 = st.columns(2)
    with assign_col1:
        selected_day = st.selectbox(
            "Day",
            week_dates,
            format_func=lambda d: f"{'🚫 ' if _is_day_blocked(d, blocked_weeks) else ''}{day_names[d.weekday()]} {d.strftime('%m/%d')}",
        )
    with assign_col2:
        selected_pm = st.selectbox("PM", [(pm.id, pm.name) for pm in pms if (pm.id, pm.name) in available_pms], format_func=lambda x: x[1])

    # Warn if assigning to blocked day
    if _is_day_blocked(selected_day, blocked_weeks):
        st.warning("⚠️ This day is in a blocked week. Are you sure you want to schedule here?")

    available_jobs = [(j.id, f"{j.customer_name} — {j.address} (Score: {j.score:.1f})") for j in to_schedule]
    selected_jobs = st.multiselect("Jobs to assign", available_jobs, format_func=lambda x: x[1])

    if st.button("Add to Plan", type="primary"):
        if selected_jobs and selected_pm:
            job_ids = [j[0] for j in selected_jobs]
            plan = SchedulePlan(
                plan_date=selected_day,
                pm_id=selected_pm[0],
                job_ids=job_ids,
                status="draft",
            )
            db.add(plan)
            # Update job statuses
            for jid in job_ids:
                job = db.query(Job).filter(Job.id == jid).first()
                if job:
                    job.bucket = JobBucket.SCHEDULED.value
                    job.date_scheduled = selected_day
                    job.assigned_pm_id = selected_pm[0]
            db.commit()
            st.success(f"Added {len(job_ids)} jobs to {day_names[selected_day.weekday()]} for {selected_pm[1]}")
            # Auto-recalculate scores after assignment
            run_scoring_engine(db, pm_ids=[p[0] for p in available_pms] if available_pms else None)
            st.rerun()
else:
    st.info("No jobs in To Schedule queue.")

# Remove jobs from draft plans
st.subheader("Remove Jobs from Plan")
draft_plans = db.query(SchedulePlan).filter(
    SchedulePlan.plan_date.between(week_dates[0], week_dates[-1]),
    SchedulePlan.status == "draft",
).all()

if draft_plans:
    for plan in draft_plans:
        pm = db.query(PM).filter(PM.id == plan.pm_id).first()
        pm_name = pm.name if pm else "N/A"
        plan_jobs = db.query(Job).filter(Job.id.in_(plan.job_ids)).all()

        if plan_jobs:
            with st.expander(f"📋 {plan.plan_date} — {pm_name} ({len(plan_jobs)} jobs)"):
                for job in plan_jobs:
                    rcol1, rcol2 = st.columns([3, 1])
                    with rcol1:
                        st.markdown(f"**{job.customer_name}** — {job.address} (Score: {job.score:.1f})")
                    with rcol2:
                        if st.button("Remove", key=f"rm_{plan.id}_{job.id}"):
                            new_ids = [jid for jid in plan.job_ids if jid != job.id]
                            plan.job_ids = new_ids
                            job.bucket = JobBucket.TO_SCHEDULE.value
                            job.date_scheduled = None
                            job.assigned_pm_id = None
                            db.commit()
                            if not new_ids:
                                db.delete(plan)
                                db.commit()
                            # Auto-recalculate after removal
                            run_scoring_engine(db, pm_ids=[p[0] for p in available_pms] if available_pms else None)
                            st.success(f"Removed {job.customer_name} — returned to queue. Scores recalculated.")
                            st.rerun()
else:
    st.caption("No draft plans to edit.")

# Confirm week
st.subheader("Confirm Plan")
confirmable = db.query(SchedulePlan).filter(
    SchedulePlan.plan_date.between(week_dates[0], week_dates[-1]),
    SchedulePlan.status == "draft",
).all()

if confirmable:
    st.markdown(f"**{len(confirmable)} draft plan(s) for this week**")
    for plan in confirmable:
        pm = db.query(PM).filter(PM.id == plan.pm_id).first()
        st.markdown(f"- {plan.plan_date} | {pm.name if pm else 'N/A'} | {len(plan.job_ids)} jobs")

    if st.button("✅ Confirm Week", type="primary"):
        total_notes = 0
        for plan in confirmable:
            plan.status = "confirmed"
            notes = generate_scheduling_notes(db, plan)
            total_notes += len(notes)
        db.commit()
        st.success(f"Week confirmed! {total_notes} scheduling notes generated (local only — not pushed to JN).")
        st.rerun()
else:
    st.caption("No draft plans for this week.")

db.close()
