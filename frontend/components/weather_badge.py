import streamlit as st


def render_weather_badge(status: str | None, detail: str | None = None):
    """Render a weather status badge."""
    if not status:
        st.markdown("🌤️ Weather: Not checked")
        return

    if status == "clear":
        st.success(f"✅ Clear to Build — {detail or 'Conditions favorable'}")
    elif status == "do_not_build":
        st.error(f"🛑 Do Not Build — {detail or 'Conditions unfavorable'}")
    elif status == "scheduler_decision":
        st.warning(f"⚠️ Scheduler Decision Required — {detail or 'Marginal conditions'}")
    else:
        st.info(f"❓ Weather: {detail or status}")
