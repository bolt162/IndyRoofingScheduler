import streamlit as st

st.set_page_config(
    page_title="Indy Roof Scheduler",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Indy Roof & Restoration — Scheduling Intelligence System")
st.markdown("---")

st.markdown("""
### Quick Navigation
- **Dashboard** — View all jobs by bucket, sync from JobNimbus, see scoring results
- **Map View** — Interactive map with job clusters and proximity groupings
- **Weekly Plan** — Build and confirm weekly schedules with PM assignments
- **Settings** — Configure PM roster, weather thresholds, AI rules, and more
- **Not Built** — Manage jobs returned to queue with reason tracking
""")

st.info("This system is READ-ONLY for JobNimbus. Notes are generated locally and displayed here — they are NOT pushed to JN until explicitly enabled.")
