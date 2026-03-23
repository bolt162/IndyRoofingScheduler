import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import streamlit as st

from backend.database import SessionLocal
from backend.models.settings import SystemSettings
from backend.models.pm import PM, Crew

st.set_page_config(page_title="Settings", layout="wide")
st.title("Settings")

db = SessionLocal()

# --- PM Roster ---
st.subheader("PM Roster")
pms = db.query(PM).all()
if pms:
    for pm in pms:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        with col1:
            st.text(pm.name)
        with col2:
            new_baseline = st.number_input("Baseline", value=pm.baseline_capacity, min_value=1, max_value=10, key=f"pm_base_{pm.id}")
            if new_baseline != pm.baseline_capacity:
                pm.baseline_capacity = new_baseline
                db.commit()
        with col3:
            new_max = st.number_input("Max", value=pm.max_capacity, min_value=1, max_value=10, key=f"pm_max_{pm.id}")
            if new_max != pm.max_capacity:
                pm.max_capacity = new_max
                db.commit()
        with col4:
            active = st.checkbox("Active", value=pm.is_active, key=f"pm_active_{pm.id}")
            if active != pm.is_active:
                pm.is_active = active
                db.commit()

with st.expander("Add PM"):
    pm_name = st.text_input("PM Name", key="new_pm_name")
    pm_baseline = st.number_input("Baseline capacity", value=3, min_value=1, max_value=10, key="new_pm_baseline")
    pm_max = st.number_input("Max capacity", value=5, min_value=1, max_value=10, key="new_pm_max")
    if st.button("Add PM"):
        if pm_name:
            db.add(PM(name=pm_name, baseline_capacity=pm_baseline, max_capacity=pm_max))
            db.commit()
            st.success(f"Added PM: {pm_name}")
            st.rerun()

st.markdown("---")

# --- Crew Roster ---
st.subheader("Crew Roster")
crews = db.query(Crew).all()
if crews:
    for crew in crews:
        col1, col2, col3 = st.columns([3, 4, 1])
        with col1:
            st.text(crew.name)
        with col2:
            st.caption(f"Specialties: {', '.join(crew.specialties) if crew.specialties else 'General'}")
        with col3:
            active = st.checkbox("Active", value=crew.is_active, key=f"crew_active_{crew.id}")
            if active != crew.is_active:
                crew.is_active = active
                db.commit()

with st.expander("Add Crew"):
    crew_name = st.text_input("Crew Name", key="new_crew_name")
    specialties_text = st.text_input("Specialties (comma-separated)", key="new_crew_specs", placeholder="e.g., framer, slate, TPO")
    if st.button("Add Crew"):
        if crew_name:
            specs = [s.strip() for s in specialties_text.split(",") if s.strip()] if specialties_text else []
            db.add(Crew(name=crew_name, specialties=specs))
            db.commit()
            st.success(f"Added Crew: {crew_name}")
            st.rerun()

st.markdown("---")

# --- Scoring Weights ---
st.subheader("Scoring Weights")
weight_keys = [
    ("weight_days_in_queue", "Days in Queue vs Average"),
    ("weight_payment_type", "Payment Type"),
    ("weight_trade_complexity", "Trade Complexity"),
    ("weight_proximity", "Geographic Proximity"),
    ("weight_material_weather", "Material vs Weather"),
    ("weight_permit_confirmed", "Permit Confirmed"),
    ("weight_duration_confirmed", "Duration Confirmed"),
    ("weight_rescheduled", "Rescheduled Counter"),
]

cols = st.columns(2)
for i, (key, label) in enumerate(weight_keys):
    with cols[i % 2]:
        setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        current = int(setting.value) if setting else 10
        new_val = st.slider(label, 0, 50, current, key=f"sw_{key}")
        if new_val != current and setting:
            setting.value = str(new_val)
            db.commit()

st.markdown("---")

# --- Distance Rules ---
st.subheader("Distance Rules (miles)")
dist_keys = [
    ("cluster_tier_1_miles", "Tight cluster (up to 5 builds)"),
    ("cluster_tier_2_miles", "Close cluster (up to 4 builds)"),
    ("cluster_tier_3_miles", "Standard range (baseline 3)"),
    ("cluster_tier_4_miles", "Extended range (1-2 builds)"),
    ("cluster_tier_5_miles", "Standalone trigger"),
]

for key, label in dist_keys:
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    current = float(setting.value) if setting else 10
    new_val = st.number_input(label, value=current, min_value=0.1, step=0.5, key=f"dist_{key}")
    if new_val != current and setting:
        setting.value = str(new_val)
        db.commit()

st.markdown("---")

# --- Weather Thresholds ---
st.subheader("Material Weather Thresholds")
weather_settings = [
    ("weather_asphalt_min_temp", "Asphalt Min Temp (°F)"),
    ("weather_asphalt_max_wind", "Asphalt Max Wind (mph)"),
    ("weather_polymer_min_temp", "Polymer Modified Min Temp (°F)"),
    ("weather_polymer_max_wind", "Polymer Modified Max Wind (mph)"),
    ("weather_tpo_min_temp", "TPO/EPDM Min Temp (°F)"),
    ("weather_tpo_max_wind", "TPO/EPDM Max Wind (mph)"),
    ("weather_tpo_rain_window_hrs", "TPO/EPDM Rain Window (hrs)"),
    ("weather_coating_min_temp", "Coatings Min Temp (°F)"),
    ("weather_coating_rain_window_hrs", "Coatings Rain Window (hrs)"),
    ("weather_siding_max_wind", "Siding Max Wind (mph)"),
]

cols = st.columns(2)
for i, (key, label) in enumerate(weather_settings):
    with cols[i % 2]:
        setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        current = float(setting.value) if setting else 40
        new_val = st.number_input(label, value=current, step=1.0, key=f"wt_{key}")
        if new_val != current and setting:
            setting.value = str(new_val)
            db.commit()

st.markdown("---")

# --- AI Rules ---
st.subheader("AI Rules (Plain English)")
st.caption("Type custom scoring rules in plain English. These are applied to every scoring run by the AI.")
ai_setting = db.query(SystemSettings).filter(SystemSettings.key == "ai_custom_rules").first()
current_rules = ai_setting.value if ai_setting else ""
new_rules = st.text_area(
    "Custom Rules",
    value=current_rules,
    height=200,
    placeholder='Examples:\n- "During storm season, prioritize insurance jobs in zip codes with recent hail activity"\n- "If a job has been sitting more than 90 days, treat it as a cash job for scoring purposes"\n- "Never suggest wood shake jobs between November and February"',
)
if new_rules != current_rules and ai_setting:
    ai_setting.value = new_rules
    db.commit()
    st.success("AI rules updated.")

st.markdown("---")

# --- Secondary Trade Aging ---
st.subheader("Secondary Trade Aging Thresholds")
col1, col2 = st.columns(2)
with col1:
    yellow = db.query(SystemSettings).filter(SystemSettings.key == "secondary_aging_yellow_days").first()
    yellow_val = int(yellow.value) if yellow else 7
    new_yellow = st.number_input("Yellow flag (days)", value=yellow_val, min_value=1)
    if new_yellow != yellow_val and yellow:
        yellow.value = str(new_yellow)
        db.commit()

with col2:
    red = db.query(SystemSettings).filter(SystemSettings.key == "secondary_aging_red_days").first()
    red_val = int(red.value) if red else 14
    new_red = st.number_input("Red flag (days)", value=red_val, min_value=1)
    if new_red != red_val and red:
        red.value = str(new_red)
        db.commit()

st.markdown("---")

# --- Sit Time ---
st.subheader("Sit Time Average")
sit = db.query(SystemSettings).filter(SystemSettings.key == "sit_time_rolling_avg_days").first()
sit_val = int(sit.value) if sit else 38
new_sit = st.number_input("Rolling average days in queue (seed)", value=sit_val, min_value=1)
if new_sit != sit_val and sit:
    sit.value = str(new_sit)
    db.commit()

# --- Blocked Weeks ---
st.subheader("Blocked Weeks")
blocked = db.query(SystemSettings).filter(SystemSettings.key == "blocked_weeks").first()
blocked_weeks = json.loads(blocked.value) if blocked and blocked.value else []
st.caption(f"Currently blocked: {', '.join(blocked_weeks) if blocked_weeks else 'None'}")
new_block = st.date_input("Add blocked week starting", key="new_block_date")
if st.button("Block This Week"):
    blocked_weeks.append(str(new_block))
    if blocked:
        blocked.value = json.dumps(blocked_weeks)
        db.commit()
    st.success(f"Blocked week of {new_block}")
    st.rerun()

# --- BamWx Check Time ---
st.subheader("BamWx Night-Before Check Time")
bamwx = db.query(SystemSettings).filter(SystemSettings.key == "bamwx_check_time").first()
bamwx_val = bamwx.value if bamwx else "20:00"
new_bamwx = st.text_input("Check time (24hr format)", value=bamwx_val)
if new_bamwx != bamwx_val and bamwx:
    bamwx.value = new_bamwx
    db.commit()

db.close()
