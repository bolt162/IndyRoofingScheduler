import folium
import streamlit as st
from streamlit_folium import st_folium


# Pin colors by bucket
BUCKET_COLORS = {
    "to_schedule": "blue",
    "scheduled": "green",
    "not_built": "orange",
    "primary_complete": "purple",
    "waiting_on_trades": "lightblue",
    "review_for_completion": "darkgreen",
    "pending_confirmation": "gray",
}

# PM assignment colors
PM_COLORS = [
    "red", "blue", "green", "purple", "orange",
    "darkred", "lightgreen", "darkblue", "cadetblue", "pink",
]


def render_job_map(
    jobs: list[dict],
    clusters: list[dict] | None = None,
    pm_assignments: dict[int, str] | None = None,
    center: tuple = (39.7684, -86.1581),
    zoom: int = 10,
):
    """
    Render an interactive map with job pins and cluster highlighting.

    Args:
        jobs: list of job dicts with latitude, longitude, etc.
        clusters: optional cluster data from clustering service
        pm_assignments: optional dict mapping pm_id -> pm_name for coloring by PM
        center: map center coordinates
        zoom: initial zoom level
    """
    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")

    # Build PM color lookup if assignments provided
    pm_color_map = {}
    if pm_assignments:
        for i, (pm_id, pm_name) in enumerate(pm_assignments.items()):
            pm_color_map[pm_id] = PM_COLORS[i % len(PM_COLORS)]

    # Cluster colors for grouping
    cluster_colors = PM_COLORS

    # If we have clusters, color-code by cluster
    if clusters:
        for i, cluster in enumerate(clusters):
            color = cluster_colors[i % len(cluster_colors)]
            cluster_jobs = cluster.get("jobs", [])

            for cj in cluster_jobs:
                lat, lng = cj.get("lat"), cj.get("lng")
                if not lat or not lng:
                    continue

                # Must-Build gets a special icon
                if cj.get("must_build"):
                    icon = folium.Icon(color="red", icon="star", prefix="fa")
                else:
                    icon = folium.Icon(color=color, icon="home", prefix="fa")

                popup_html = f"""
                <b>{cj.get('customer_name', 'Unknown')}</b><br>
                {cj.get('address', '')}<br>
                Material: {cj.get('material_type', 'N/A')}<br>
                Score: {cj.get('score', 0):.1f}<br>
                Cluster: {cluster.get('cluster_id', 'N/A')} ({cluster.get('tier', 'N/A')})
                """

                folium.Marker(
                    location=[lat, lng],
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=cj.get("customer_name", "Job"),
                    icon=icon,
                ).add_to(m)

            # Draw cluster boundary if multiple jobs
            if len(cluster_jobs) > 1:
                coords = [(j["lat"], j["lng"]) for j in cluster_jobs if j.get("lat") and j.get("lng")]
                if len(coords) > 1:
                    folium.PolyLine(
                        coords + [coords[0]],
                        color=color,
                        weight=2,
                        opacity=0.5,
                        dash_array="5",
                    ).add_to(m)
    else:
        # Plot all jobs — color by PM if assignments exist, else by bucket
        for job in jobs:
            lat, lng = job.get("latitude"), job.get("longitude")
            if not lat or not lng:
                continue

            # Determine pin color
            pm_id = job.get("assigned_pm_id")
            if pm_assignments and pm_id and pm_id in pm_color_map:
                color = pm_color_map[pm_id]
                pm_label = pm_assignments.get(pm_id, "")
            else:
                bucket = job.get("bucket", "to_schedule")
                color = BUCKET_COLORS.get(bucket, "blue")
                pm_label = ""

            bucket = job.get("bucket", "to_schedule")
            if job.get("must_build"):
                icon = folium.Icon(color="red", icon="star", prefix="fa")
            elif bucket == "scheduled":
                icon = folium.Icon(color=color, icon="check", prefix="fa")
            elif job.get("standalone_rule"):
                icon = folium.Icon(color="orange", icon="exclamation-triangle", prefix="fa")
            else:
                icon = folium.Icon(color=color, icon="home", prefix="fa")

            pm_line = f"PM: {pm_label}<br>" if pm_label else ""
            bucket_label = bucket.replace("_", " ").title()
            popup_html = f"""
            <b>{job.get('customer_name', 'Unknown')}</b><br>
            {job.get('address', '')}<br>
            {pm_line}Material: {job.get('material_type', 'N/A')}<br>
            Payment: {job.get('payment_type', 'N/A')}<br>
            Score: {job.get('score', 0):.1f}<br>
            Status: <b>{bucket_label}</b>
            """

            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=job.get("customer_name", "Job"),
                icon=icon,
            ).add_to(m)

    # Add PM legend if assignments are shown
    if pm_assignments and pm_color_map:
        legend_html = '<div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;padding:10px;border:1px solid #ccc;border-radius:5px;font-size:13px;">'
        legend_html += "<b>PM Legend</b><br>"
        for pm_id, pm_name in pm_assignments.items():
            c = pm_color_map[pm_id]
            legend_html += f'<i style="background:{c};width:12px;height:12px;display:inline-block;margin-right:5px;border-radius:50%;"></i> {pm_name}<br>'
        legend_html += "</div>"
        m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=None, height=600, returned_objects=[])
