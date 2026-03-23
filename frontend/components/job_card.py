import streamlit as st
from datetime import datetime


# Duration tier colors
TIER_COLORS = {
    "tier_1": "#4CAF50",   # Green - auto confirmed
    "tier_2": "#FFC107",   # Yellow - soft flag
    "tier_3": "#F44336",   # Red - hard flag
    "low_slope": "#9C27B0", # Purple - pending confirmation
}

TIER_LABELS = {
    "tier_1": "Tier 1 (Auto)",
    "tier_2": "Tier 2 (Unconfirmed)",
    "tier_3": "Tier 3 (UNCONFIRMED)",
    "low_slope": "Low Slope (Pending)",
}

PAYMENT_COLORS = {
    "cash": "#4CAF50",
    "finance": "#2196F3",
    "insurance": "#FF9800",
}

WEATHER_ICONS = {
    "clear": "✅",
    "do_not_build": "🛑",
    "scheduler_decision": "⚠️",
}


def render_job_card(job: dict, show_actions: bool = True, notes: list | None = None):
    """Render a job card in Streamlit.

    Args:
        job: dict of job fields
        show_actions: whether to show action buttons
        notes: optional list of NoteLog dicts for this job
    """
    # Crew requirement is the MOST PROMINENT element
    if job.get("crew_requirement_flag"):
        st.error(f"⚡ CREW REQUIREMENT: {job.get('crew_requirement_note', 'Specialty crew needed')}")

    # Must-Build visual distinction
    if job.get("must_build"):
        st.warning(f"🔴 MUST-BUILD — Deadline: {job.get('must_build_deadline', 'N/A')}")

    col1, col2, col3 = st.columns([3, 2, 2])

    with col1:
        st.markdown(f"**{job.get('customer_name', 'Unknown')}**")
        st.caption(job.get("address", ""))
        if job.get("jn_job_id"):
            st.caption(f"JN ID: {job['jn_job_id']}")

    with col2:
        # Material + Duration tier
        tier = job.get("duration_tier", "")
        tier_color = TIER_COLORS.get(tier, "#757575")
        tier_label = TIER_LABELS.get(tier, tier)
        st.markdown(f"**Material:** {job.get('material_type', 'N/A')}")
        st.markdown(
            f"<span style='background-color:{tier_color};color:white;padding:2px 8px;border-radius:4px;font-size:0.85em'>"
            f"{tier_label}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Sq Ft:** {job.get('square_footage', 'N/A')} | **Duration:** {job.get('duration_days', 1)}d")

    with col3:
        # Payment type
        pt = job.get("payment_type", "unknown")
        pt_color = PAYMENT_COLORS.get(pt, "#757575")
        st.markdown(
            f"<span style='background-color:{pt_color};color:white;padding:2px 8px;border-radius:4px'>"
            f"{pt.upper()}</span>",
            unsafe_allow_html=True,
        )

        # Trade info
        primary = job.get("primary_trade", "N/A")
        secondary_count = len(job.get("secondary_trades") or [])
        st.markdown(f"**Trade:** {primary}" + (f" +{secondary_count} more" if secondary_count else ""))

        # Days in queue
        days = 0
        if job.get("date_entered"):
            if isinstance(job["date_entered"], str):
                try:
                    entered = datetime.fromisoformat(job["date_entered"])
                    days = (datetime.utcnow() - entered).days
                except ValueError:
                    pass
            elif isinstance(job["date_entered"], datetime):
                days = (datetime.utcnow() - job["date_entered"]).days
        st.markdown(f"**Queue:** {days}d")

        # Rescheduled counter
        resched = job.get("rescheduled_count", 0)
        if resched > 0:
            st.markdown(f"🔄 Rescheduled: **{resched}x**")

    # Score
    score = job.get("score", 0)
    st.progress(min(score / 100, 1.0), text=f"Score: {score:.1f}")

    # Weather status
    ws = job.get("weather_status")
    if ws:
        icon = WEATHER_ICONS.get(ws, "❓")
        st.markdown(f"{icon} Weather: {job.get('weather_detail', ws)}")

    # JN notes preview (one-line)
    if job.get("jn_notes_raw"):
        raw = job["jn_notes_raw"].strip()
        preview = raw[:120] + "..." if len(raw) > 120 else raw
        st.caption(f"📝 JN Notes: {preview}")

    # AI note scan result preview
    if job.get("ai_note_scan_result"):
        with st.expander("AI Note Scan"):
            st.text(job["ai_note_scan_result"])

    # Score explanation
    if job.get("score_explanation"):
        with st.expander("Score Breakdown"):
            st.text(job["score_explanation"])

    # Standalone rule
    if job.get("standalone_rule"):
        st.info("📍 Standalone Rule: No cluster partners within 40 miles")

    # Per-job notes history
    if notes:
        with st.expander(f"📋 Notes ({len(notes)})"):
            for note in notes:
                note_type = note.get("note_type", "").replace("_", " ").title()
                created = note.get("created_at")
                if isinstance(created, datetime):
                    ts = created.strftime("%m/%d/%Y %I:%M%p")
                else:
                    ts = str(created) if created else ""

                # Color-code by note type
                type_colors = {
                    "scheduling_decision": "#4CAF50",
                    "not_built": "#F44336",
                    "weather_rollback": "#FF9800",
                    "secondary_trade_alert": "#2196F3",
                    "standalone_rule": "#9C27B0",
                    "night_before_weather": "#607D8B",
                }
                color = type_colors.get(note.get("note_type", ""), "#757575")

                st.markdown(
                    f"<div style='border-left:3px solid {color};padding:8px 12px;margin-bottom:8px;background:rgba(255,255,255,0.05);border-radius:4px'>"
                    f"<strong style='color:{color}'>{note_type}</strong> "
                    f"<span style='color:#aaa;font-size:0.85em'>— {ts}</span>"
                    f"<br><span style='color:#e0e0e0;font-size:0.9em'>{note.get('note_text', '')}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")
