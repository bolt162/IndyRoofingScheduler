import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.pm import PM
from backend.services.clustering import cluster_jobs
from backend.services.notes import generate_standalone_rule_note
from frontend.components.map_component import render_job_map

st.set_page_config(page_title="Map View", layout="wide")
st.title("Map View — Job Clusters")

db = SessionLocal()

# Sidebar controls
st.sidebar.header("Map Controls")
show_clusters = st.sidebar.checkbox("Show clusters", value=True)
show_pm_overlay = st.sidebar.checkbox("Color by PM assignment", value=False)

selected_bucket = st.sidebar.selectbox(
    "Filter bucket",
    ["to_schedule", "scheduled", "all"],
    format_func=lambda x: x.replace("_", " ").title(),
)

# Get jobs
if selected_bucket == "all":
    jobs = db.query(Job).filter(Job.latitude != None, Job.longitude != None).all()
else:
    jobs = db.query(Job).filter(
        Job.bucket == selected_bucket,
        Job.latitude != None,
        Job.longitude != None,
    ).all()

if not jobs:
    st.info("No jobs with coordinates found. Sync from JN to get started.")
else:
    st.caption(f"Showing {len(jobs)} jobs on map")

    # Build PM assignment map if overlay is on
    pm_assignments = None
    if show_pm_overlay:
        pm_ids = set(j.assigned_pm_id for j in jobs if j.assigned_pm_id)
        if pm_ids:
            pms = db.query(PM).filter(PM.id.in_(pm_ids)).all()
            pm_assignments = {pm.id: pm.name for pm in pms}

    # Cluster if requested
    clusters = None
    if show_clusters and not show_pm_overlay:
        clusters = cluster_jobs(db)
        if clusters:
            st.subheader("Cluster Summary")
            for c in clusters:
                job_count = len(c["jobs"])
                tier = c["tier"]
                standalone = c["is_standalone"]
                emoji = "📍" if standalone else "🏘️"
                st.markdown(
                    f"{emoji} **{c['cluster_id']}** — {tier.title()} | "
                    f"{job_count} job{'s' if job_count > 1 else ''} | "
                    f"Suggested PM capacity: {c['suggested_pm_capacity']}"
                )
                if c["distances"]:
                    dists = [d["miles"] for d in c["distances"]]
                    st.caption(f"  Distances: {min(dists):.1f} - {max(dists):.1f} mi")

    # Render map
    job_dicts = [j.__dict__ for j in jobs]
    render_job_map(job_dicts, clusters=clusters, pm_assignments=pm_assignments)

    # Standalone jobs alert + Rule UI
    if clusters:
        standalones = [c for c in clusters if c["is_standalone"]]
        if standalones:
            st.warning(f"⚠️ {len(standalones)} standalone job(s) — no cluster partners within range. Standalone Rule applies.")
            for s in standalones:
                job_info = s["jobs"][0]
                job_obj = db.query(Job).filter(Job.id == job_info["job_id"]).first()
                st.markdown(f"  - **{job_info['customer_name']}** ({job_info['address']}) — Score: {job_info['score']:.1f}")

                if job_obj:
                    current_option = job_obj.standalone_option or ""
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        option = st.selectbox(
                            "Standalone Option",
                            ["", "saturday_build", "sales_rep_managed"],
                            index=["", "saturday_build", "sales_rep_managed"].index(current_option) if current_option in ["", "saturday_build", "sales_rep_managed"] else 0,
                            format_func=lambda x: {"": "Select...", "saturday_build": "Saturday Build", "sales_rep_managed": f"Sales Rep Managed ({job_obj.sales_rep or 'TBD'})"}[x],
                            key=f"standalone_opt_{job_obj.id}",
                        )
                    with col2:
                        if current_option:
                            label = "Saturday Build" if current_option == "saturday_build" else "Sales Rep Managed"
                            st.success(f"Current: {label}")
                    with col3:
                        if option and option != current_option:
                            if st.button("Apply", key=f"standalone_apply_{job_obj.id}"):
                                job_obj.standalone_option = option
                                job_obj.standalone_rule = True
                                db.commit()
                                generate_standalone_rule_note(db, job_obj, option)
                                st.success(f"Standalone option set to {option.replace('_', ' ').title()}")
                                st.rerun()

db.close()
