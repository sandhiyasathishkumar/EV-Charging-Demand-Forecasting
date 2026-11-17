import streamlit as st
import pandas as pd
import requests
import re
from pathlib import Path
from io import BytesIO

# =====================================================
# 1. PAGE CONFIGURATION
# =====================================================
st.set_page_config(
    page_title="EV Nexus | Smart Charging Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# 2. FUTURISTIC DARK THEME
# =====================================================
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #07111f, #0b1427, #15132e);
    color: #e8f2ff;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #081323, #10152b);
    border-right: 1px solid #21465e;
}
h1, h2, h3 { color: #55e6ff !important; }
p, label, li { color: #dce8f7; }
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #111f35, #171b38);
    border: 1px solid #21465e;
    padding: 16px;
    border-radius: 14px;
}
[data-testid="stMetricValue"] { color: #57e7ff; }
.stButton > button {
    background: linear-gradient(90deg, #00bcd4, #6366f1);
    color: white;
    border: none;
    border-radius: 10px;
    font-weight: 600;
}
.ev-header {
    padding: 22px;
    border-radius: 18px;
    background: linear-gradient(110deg, #10243a, #191b3c);
    border: 1px solid #28506a;
    margin-bottom: 22px;
}
.ev-subtitle { color: #b6c9df; font-size: 15px; }
.ev-note {
    background: #101f32;
    border-left: 4px solid #31d9f5;
    padding: 12px 16px;
    border-radius: 8px;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# 3. SETTINGS
# =====================================================
CSV_PATH = Path(__file__).parent / "ev_forecast_results.csv"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:3b"

# =====================================================
# 4. LOAD FORECAST DATA
# =====================================================
@st.cache_data
def load_forecast(path):
    file_path = Path(path)
    if not file_path.exists():
        return None

    data = pd.read_csv(file_path)
    required = ["timestamp", "site_id", "predicted_demand_kwh"]
    if not all(column in data.columns for column in required):
        return None

    data["site_id"] = pd.to_numeric(data["site_id"], errors="coerce")
    data["predicted_demand_kwh"] = pd.to_numeric(
        data["predicted_demand_kwh"], errors="coerce"
    )
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data = data.dropna(subset=["site_id", "predicted_demand_kwh"])
    data["site_id"] = data["site_id"].astype(int)

    return data.sort_values(
        "predicted_demand_kwh", ascending=False
    ).reset_index(drop=True)


df = load_forecast(str(CSV_PATH))


# =====================================================
# 4A. LOAD STATION LOCATIONS FOR THE MAP
# =====================================================
@st.cache_data
def load_station_locations(file_bytes):
    """Read station coordinates from the 'sites' sheet of an Excel workbook."""
    try:
        sites = pd.read_excel(BytesIO(file_bytes), sheet_name="sites")
    except Exception as error:
        return None, f"Could not read the 'sites' sheet: {error}"

    required = ["site_id", "longitude", "latitude"]
    missing_columns = [column for column in required if column not in sites.columns]
    if missing_columns:
        return None, (
            "The 'sites' sheet is missing these required columns: "
            + ", ".join(missing_columns)
        )

    for column in ["site_id", "longitude", "latitude"]:
        sites[column] = pd.to_numeric(sites[column], errors="coerce")

    sites = sites.dropna(subset=["site_id", "longitude", "latitude"]).copy()
    sites = sites[
        sites["longitude"].between(-180, 180)
        & sites["latitude"].between(-90, 90)
    ].copy()

    if sites.empty:
        return None, "No valid station coordinates were found in the 'sites' sheet."

    sites["site_id"] = sites["site_id"].astype(int)
    sites = sites.drop_duplicates(subset=["site_id"]).reset_index(drop=True)
    return sites, None

def station_name(site_id):
    return f"Station {int(site_id)}"

def forecast_date():
    if df is None or df.empty:
        return "date unavailable"
    dates = df["timestamp"].dropna()
    if dates.empty:
        return "date unavailable"
    return dates.max().strftime("%d %B %Y")

# =====================================================
# 5. DIRECT ANSWERS ABOUT FORECAST STATIONS
# =====================================================
def get_station_answer(question):
    q = question.lower().strip()
    q = re.sub(r"[?!.,]+$", "", q)

    if re.fullmatch(
        r"(hi|hello|hey|hai|good morning|good afternoon|good evening)"
        r"(\s+there)?", q
    ):
        return (
            "Hey! 😊 I'm doing great, thanks for asking! "
            "How about you? Feel free to ask me about EV charging!"
        )

    if any(x in q for x in ["how are you", "how are you doing", "how's it going"]):
        return "I'm doing great, thank you! 😊 How are you doing?"

    if any(x in q for x in [
        "what can you do", "how can you help", "what can i ask", "your features"
    ]):
        return (
            "I can help compare charging stations, check predicted demand, "
            "explain forecasting, and discuss resource optimization. ⚡"
        )

    if df is None or df.empty:
        return None

    if any(x in q for x in [
        "highest charging demand", "highest demand", "busiest station",
        "most busy station", "maximum demand", "most demanded station"
    ]):
        row = df.loc[df["predicted_demand_kwh"].idxmax()]
        return (
            f"⚡ **{station_name(row['site_id'])}** has the highest predicted "
            f"demand: **{row['predicted_demand_kwh']:.2f} kWh** for "
            f"{forecast_date()}. This is a forecast, not a live measurement."
        )

    if any(x in q for x in [
        "lowest charging demand", "lowest predicted demand", "lowest demand",
        "least demand", "minimum demand", "least busy station"
    ]):
        row = df.loc[df["predicted_demand_kwh"].idxmin()]
        return (
            f"🔋 **{station_name(row['site_id'])}** has the lowest predicted "
            f"demand: **{row['predicted_demand_kwh']:.2f} kWh** for "
            f"{forecast_date()}. Lower predicted demand does not guarantee "
            "that a charger is available."
        )

    if any(x in q for x in [
        "which charging station should i choose", "which station should i choose",
        "recommend a station", "station with lower demand",
        "find a station with lower demand"
    ]):
        low = df.nsmallest(min(3, len(df)), "predicted_demand_kwh")
        choices = ", ".join(
            f"{station_name(r['site_id'])} ({r['predicted_demand_kwh']:.2f} kWh)"
            for _, r in low.iterrows()
        )
        return (
            f"Based on the forecast, consider: **{choices}**. 😊 "
            "Please check a charging network app for live charger availability."
        )

    match = re.search(r"(?:station|site)\s*#?\s*(\d+)", q)
    if match and any(x in q for x in ["demand", "forecast", "predict", "energy", "kwh"]):
        sid = int(match.group(1))
        result = df[df["site_id"] == sid]
        if result.empty:
            return f"I couldn't find Station {sid} in the forecast data."
        row = result.iloc[0]
        return (
            f"📍 The predicted demand for **Station {sid}** is "
            f"**{row['predicted_demand_kwh']:.2f} kWh** for {forecast_date()}."
        )

    if any(x in q for x in [
        "need more charging resources", "more resources",
        "high demand stations", "stations with high demand"
    ]):
        top = df.nlargest(min(5, len(df)), "predicted_demand_kwh")
        details = "\n".join(
            f"- {station_name(r['site_id'])}: {r['predicted_demand_kwh']:.2f} kWh"
            for _, r in top.iterrows()
        )
        return "Stations with the highest predicted demand:\n\n" + details

    if any(x in q for x in [
        "likely to be busy", "station busy", "is it busy",
        "waiting time", "wait too long", "avoid waiting"
    ]):
        row = df.loc[df["predicted_demand_kwh"].idxmax()]
        return (
            "I can compare predicted demand, but cannot confirm live crowding "
            "or waiting times because live occupancy is not connected. "
            f"{station_name(row['site_id'])} has the highest predicted demand "
            f"({row['predicted_demand_kwh']:.2f} kWh)."
        )
    return None

# =====================================================
# 6. LOCAL OLLAMA AI
# =====================================================
def ask_local_ai(question):
    if df is not None and not df.empty:
        station_context = df[
            ["site_id", "predicted_demand_kwh"]
        ].to_string(index=False)
    else:
        station_context = "Forecast data is currently unavailable."

    system_prompt = f"""
You are EV Nexus, a friendly conversational AI assistant.
Answer the user's actual question first, in simple and warm English.
Do not turn every conversation into a project explanation.
The project forecasts EV charging demand and explores resource allocation.
The available forecast date is {forecast_date()}.
The app has no live charger availability, live waiting times, live weather,
or individual vehicle battery information.
The resource allocation page is a simplified simulation.
Never invent live data or claim a charger is currently free or busy.
Use these forecast records when relevant:
{station_context}
"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                "stream": False
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json().get("message", {}).get(
            "content", "Sorry! I couldn't generate an answer. Please try again."
        )
    except requests.exceptions.ConnectionError:
        return (
            "I can't connect to the local AI right now. Please make sure "
            "Ollama is running and qwen2.5:3b is installed."
        )
    except requests.exceptions.Timeout:
        return "The AI is taking longer than expected. Please try again."
    except Exception as error:
        return f"Something went wrong while contacting the AI: {error}"
        
def ask_local_ai(question):
    return (
        "The AI Chat Assistant's local Ollama service is not available "
        "in the online version yet. You can still use the dashboard, "
        "station comparison, performance analysis, resource optimization, "
        "station map, and dataset management features."
    )
def answer_question(question):
    direct = get_station_answer(question)
    return direct if direct is not None else ask_local_ai(question)

# =====================================================
# 7. SIDEBAR NAVIGATION
# =====================================================
with st.sidebar:
    st.markdown("# ⚡ EV NEXUS")
    st.caption("Smart Charging Intelligence")
    st.markdown("---")
    page = st.radio(
        "NAVIGATION",
        [
            "🏠 Dashboard",
            "📊 Station Comparison",
            "📈 Station Performance Analysis",
            "⚙️ Resource Optimization",
            "🤖 AI Chat Assistant",
            "🗺️ EV Station Map",
            "🗂️ Dataset Management"
        ]
    )
    st.markdown("---")
    st.caption("Machine Learning • Forecasting • Optimization")
    st.caption(f"Forecast date: {forecast_date()}")

# =====================================================
# 8. DASHBOARD
# =====================================================
if page == "🏠 Dashboard":
    st.markdown("""
    <div class="ev-header">
        <h1>⚡ EV Charging Intelligence Dashboard</h1>
        <div class="ev-subtitle">
            Charging demand forecasting and multi-station resource optimization
        </div>
    </div>
    """, unsafe_allow_html=True)

    if df is None or df.empty:
        st.error("Forecast data is unavailable. Check the forecast CSV file.")
    else:
        total_stations = df["site_id"].nunique()
        average_demand = df["predicted_demand_kwh"].mean()
        highest_demand = df["predicted_demand_kwh"].max()
        total_demand = df["predicted_demand_kwh"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Charging Stations", f"{total_stations}")
        c2.metric("Average Demand", f"{average_demand:.2f} kWh")
        c3.metric("Highest Demand", f"{highest_demand:.2f} kWh")
        c4.metric("Total Predicted Demand", f"{total_demand:.2f} kWh")

        st.markdown("### 📈 Predicted Demand by Station")
        chart = df.copy()
        chart["Station"] = chart["site_id"].apply(station_name)
        chart = chart.sort_values("predicted_demand_kwh", ascending=False)
        st.bar_chart(
            chart.set_index("Station")["predicted_demand_kwh"],
            color="#22D3EE"
        )

        left, right = st.columns(2)
        with left:
            st.markdown("### 🔥 Top 5 High-Demand Stations")
            top = df.nlargest(5, "predicted_demand_kwh").copy()
            top["Station"] = top["site_id"].apply(station_name)
            top = top.rename(columns={
                "predicted_demand_kwh": "Predicted Demand (kWh)"
            })
            st.dataframe(
                top[["Station", "Predicted Demand (kWh)"]],
                hide_index=True, width="stretch"
            )
        with right:
            st.markdown("### 🔋 Top 5 Low-Demand Stations")
            low = df.nsmallest(5, "predicted_demand_kwh").copy()
            low["Station"] = low["site_id"].apply(station_name)
            low = low.rename(columns={
                "predicted_demand_kwh": "Predicted Demand (kWh)"
            })
            st.dataframe(
                low[["Station", "Predicted Demand (kWh)"]],
                hide_index=True, width="stretch"
            )

        st.markdown(
            f'<div class="ev-note">Forecast date: {forecast_date()}. '
            'These values are model predictions, not live measurements.</div>',
            unsafe_allow_html=True
        )

# =====================================================
# 9. STATION COMPARISON
# =====================================================
elif page == "📊 Station Comparison":
    st.markdown("""
    <div class="ev-header">
        <h1>📊 Station Comparison</h1>
        <div class="ev-subtitle">Compare predicted charging demand across stations</div>
    </div>
    """, unsafe_allow_html=True)

    if df is None or df.empty:
        st.error("Forecast data is unavailable.")
    else:
        station_ids = sorted(df["site_id"].unique().tolist())
        selected = st.selectbox(
            "Select a charging station", station_ids,
            format_func=station_name
        )
        row = df[df["site_id"] == selected].iloc[0]
        st.markdown(f"### 📍 {station_name(selected)}")

        a, b, c = st.columns(3)
        a.metric("Predicted Demand", f"{row['predicted_demand_kwh']:.2f} kWh")
        ranks = df["predicted_demand_kwh"].rank(method="min", ascending=False)
        rank = int(ranks[df["site_id"] == selected].iloc[0])
        b.metric("Demand Rank", f"{rank} / {len(df)}")
        average = df["predicted_demand_kwh"].mean()
        c.metric(
            "Difference from Average",
            f"{row['predicted_demand_kwh'] - average:+.2f} kWh"
        )

        st.markdown("### 📈 Compare All Stations")
        comparison = df[["site_id", "predicted_demand_kwh"]].copy()
        comparison["Station"] = comparison["site_id"].apply(station_name)
        st.bar_chart(
            comparison.set_index("Station")["predicted_demand_kwh"],
            color="#8B5CF6"
        )

        st.markdown("### 📋 All Forecast Results")
        table = df[["site_id", "timestamp", "predicted_demand_kwh"]].copy()
        table["Station"] = table["site_id"].apply(station_name)
        table = table.rename(columns={
            "timestamp": "Forecast Timestamp",
            "predicted_demand_kwh": "Predicted Demand (kWh)"
        })
        st.dataframe(
            table[["Station", "Forecast Timestamp", "Predicted Demand (kWh)"]],
            hide_index=True, width="stretch"
        )


# =====================================================
# 10. STATION PERFORMANCE ANALYSIS
# =====================================================
elif page == "📈 Station Performance Analysis":
    st.markdown("""
    <div class="ev-header">
        <h1>📈 Station Performance Analysis</h1>
        <div class="ev-subtitle">
            Analyze and rank stations using the available predicted charging demand
        </div>
    </div>
    """, unsafe_allow_html=True)

    if df is None or df.empty:
        st.error("Forecast data is unavailable. Check the forecast CSV file.")
    else:
        performance = df[["site_id", "predicted_demand_kwh"]].copy()
        performance["predicted_demand_kwh"] = pd.to_numeric(
            performance["predicted_demand_kwh"], errors="coerce"
        )
        performance = performance.dropna(
            subset=["site_id", "predicted_demand_kwh"]
        )
        performance = performance.drop_duplicates(
            subset=["site_id"], keep="first"
        )

        if performance.empty:
            st.warning("No valid station demand records are available.")
        else:
            average_demand = performance["predicted_demand_kwh"].mean()
            median_demand = performance["predicted_demand_kwh"].median()
            highest_row = performance.loc[
                performance["predicted_demand_kwh"].idxmax()
            ]
            lowest_row = performance.loc[
                performance["predicted_demand_kwh"].idxmin()
            ]
            total_demand = performance["predicted_demand_kwh"].clip(lower=0).sum()

            st.caption(
                f"Forecast snapshot: {forecast_date()} • "
                f"{len(performance)} stations included"
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Stations Analyzed", f"{len(performance)}")
            m2.metric("Average Predicted Demand", f"{average_demand:.2f} kWh")
            m3.metric(
                "Highest Demand",
                f"{highest_row['predicted_demand_kwh']:.2f} kWh",
                help=station_name(highest_row["site_id"])
            )
            m4.metric(
                "Lowest Demand",
                f"{lowest_row['predicted_demand_kwh']:.2f} kWh",
                help=station_name(lowest_row["site_id"])
            )

            performance["Station"] = performance["site_id"].apply(station_name)
            performance["Difference from Average (kWh)"] = (
                performance["predicted_demand_kwh"] - average_demand
            )
            performance["Demand Share (%)"] = (
                performance["predicted_demand_kwh"].clip(lower=0)
                / total_demand * 100
                if total_demand > 0 else 0.0
            )
            performance["Demand Category"] = performance[
                "predicted_demand_kwh"
            ].apply(
                lambda value: "Above average"
                if value > average_demand
                else ("Below average" if value < average_demand else "Average")
            )

            st.markdown("### 📊 Predicted Demand Ranking")
            ranked = performance.sort_values(
                "predicted_demand_kwh", ascending=False
            ).copy()
            chart_data = ranked.set_index("Station")[
                ["predicted_demand_kwh"]
            ].rename(columns={
                "predicted_demand_kwh": "Predicted Demand (kWh)"
            })
            st.bar_chart(chart_data, color="#22D3EE")

            st.markdown("### 🔍 Compare a Station with the Overall Average")
            station_options = sorted(performance["site_id"].astype(int).tolist())
            selected_station = st.selectbox(
                "Select a station",
                station_options,
                format_func=station_name,
                key="performance_selected_station"
            )
            selected_row = performance[
                performance["site_id"] == selected_station
            ].iloc[0]

            a, b, c = st.columns(3)
            a.metric(
                "Station Predicted Demand",
                f"{selected_row['predicted_demand_kwh']:.2f} kWh"
            )
            b.metric(
                "Difference from Average",
                f"{selected_row['Difference from Average (kWh)']:+.2f} kWh"
            )
            c.metric(
                "Demand Share",
                f"{selected_row['Demand Share (%)']:.2f}%"
            )
            st.info(
                f"{station_name(selected_station)} is "
                f"**{selected_row['Demand Category'].lower()}** compared "
                f"with the average predicted demand."
            )

            st.markdown("### 📋 Station Performance Report")
            category_filter = st.selectbox(
                "Filter stations",
                ["All stations", "Above average", "Below average", "Average"],
                key="performance_category_filter"
            )
            report = ranked.copy()
            if category_filter != "All stations":
                report = report[
                    report["Demand Category"] == category_filter
                ]

            report = report.rename(columns={
                "site_id": "Station ID",
                "predicted_demand_kwh": "Predicted Demand (kWh)"
            })
            report_columns = [
                "Station", "Predicted Demand (kWh)",
                "Difference from Average (kWh)", "Demand Share (%)",
                "Demand Category"
            ]
            st.dataframe(
                report[report_columns].round(2),
                hide_index=True,
                width="stretch"
            )

            csv_report = report[report_columns].to_csv(
                index=False
            ).encode("utf-8-sig")
            st.download_button(
                "⬇️ Download Station Performance Report",
                data=csv_report,
                file_name="ev_station_performance_report.csv",
                mime="text/csv",
                key="download_station_performance_report"
            )

            st.markdown(
                '<div class="ev-note">Important: this analysis uses the '
                'available forecast snapshot only. It compares predicted '
                'demand between stations; it does not measure historical '
                'operational performance or live charger availability.</div>',
                unsafe_allow_html=True
            )

# =====================================================
# 10. RESOURCE OPTIMIZATION
# =====================================================
elif page == "⚙️ Resource Optimization":
    st.markdown("""
    <div class="ev-header">
        <h1>⚙️ Resource Optimization</h1>
        <div class="ev-subtitle">
            Explore how limited resources can be allocated based on predicted demand
        </div>
    </div>
    """, unsafe_allow_html=True)

    if df is None or df.empty:
        st.error("Forecast data is unavailable.")
    else:
        st.write(
            "Adjust the hypothetical resource settings to compare "
            "demand-based allocation with equal allocation."
        )
        col1, col2 = st.columns(2)
        with col1:
            units = st.slider("Available resource units", 1, 50, 10)
        with col2:
            unit_capacity = st.slider("Capacity per unit (kWh)", 1, 100, 10)

        simulation = df[["site_id", "predicted_demand_kwh"]].copy()
        simulation["Demand (kWh)"] = simulation["predicted_demand_kwh"].clip(lower=0)
        total_capacity = units * unit_capacity
        total = simulation["Demand (kWh)"].sum()

        if total > 0:
            simulation["Demand-Based Allocation (kWh)"] = (
                simulation["Demand (kWh)"] / total
            ) * total_capacity
        else:
            simulation["Demand-Based Allocation (kWh)"] = 0.0

        simulation["Equal Allocation (kWh)"] = total_capacity / len(simulation)
        simulation["Unmet Demand - Demand-Based (kWh)"] = (
            simulation["Demand (kWh)"]
            - simulation["Demand-Based Allocation (kWh)"]
        ).clip(lower=0)
        simulation["Unmet Demand - Equal (kWh)"] = (
            simulation["Demand (kWh)"] - simulation["Equal Allocation (kWh)"]
        ).clip(lower=0)

        unmet_demand_based = simulation[
            "Unmet Demand - Demand-Based (kWh)"
        ].sum()
        unmet_equal = simulation["Unmet Demand - Equal (kWh)"].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Simulated Capacity", f"{total_capacity:.2f} kWh")
        m2.metric("Unmet Demand: Demand-Based", f"{unmet_demand_based:.2f} kWh")
        m3.metric("Unmet Demand: Equal", f"{unmet_equal:.2f} kWh")

        st.markdown("### 📊 Allocation Comparison")
        allocation_chart = simulation.set_index("site_id")[
            [
                "Demand (kWh)",
                "Demand-Based Allocation (kWh)",
                "Equal Allocation (kWh)"
            ]
        ].copy()
        allocation_chart.index = [
            station_name(sid) for sid in allocation_chart.index
        ]
        st.bar_chart(allocation_chart)

        st.markdown("### 📋 Allocation Details")
        st.dataframe(
            simulation.rename(columns={"site_id": "Station ID"}),
            hide_index=True, width="stretch"
        )
        st.markdown(
            '<div class="ev-note">This is a simplified simulation, not a live '
            'resource management system. Real-world results depend on charger '
            'capacity, availability, and operational constraints.</div>',
            unsafe_allow_html=True
        )

# =====================================================
# 11. AI CHAT ASSISTANT
# =====================================================
elif page == "🤖 AI Chat Assistant":
    st.markdown("""
    <div class="ev-header">
        <h1>🤖 EV Nexus AI Assistant</h1>
        <div class="ev-subtitle">
            Ask natural questions about EV charging, demand forecasting,
            and resource optimization
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 💬 What would you like to know?")
    with st.expander("💬 Questions You Can Ask Me"):
        st.markdown("#### 👋 General Questions")
        st.markdown("- Hi, how are you?\n- What can you do?")
        st.markdown("#### 🚗 EV Charging Questions")
        st.markdown(
            "- Which charging station should I choose?\n"
            "- Which station has the highest charging demand?\n"
            "- Which station has the lowest charging demand?\n"
            "- Is a charging station likely to be busy?\n"
            "- How much energy might I need to charge my EV?\n"
            "- How can I find a station with lower demand?\n"
            "- How can I avoid waiting too long at a charging station?"
        )
        st.markdown("#### ⚡ Demand Forecasting Questions")
        st.markdown(
            "- What is the predicted demand for Station 21?\n"
            "- Why is charging demand higher at some stations?\n"
            "- Which station has the lowest predicted demand?\n"
            "- How is charging demand predicted?\n"
            "- Can charging demand change throughout the day?\n"
            "- How does weather affect EV charging demand?\n"
            "- How accurate is the predicted charging demand?"
        )
        st.markdown("#### 🔋 Resource Optimization Questions")
        st.markdown(
            "- Which stations need more charging resources?\n"
            "- How can charging stations manage high demand?\n"
            "- What happens when charging demand exceeds available resources?\n"
            "- How can charging stations use their resources efficiently?"
        )

    if "ev_chat_history" not in st.session_state:
        st.session_state.ev_chat_history = []

    for message in st.session_state.ev_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Type your question here...")
    if question:
        st.session_state.ev_chat_history.append({
            "role": "user", "content": question
        })
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking... ⚡"):
                answer = answer_question(question)
            st.markdown(answer)
        st.session_state.ev_chat_history.append({
            "role": "assistant", "content": answer
        })

    if st.button("🗑️ Clear Chat History"):
        st.session_state.ev_chat_history = []
        st.rerun()

    st.markdown(
        '<div class="ev-note">Station answers use your saved forecast data. '
        'General conversation uses your local Ollama model. Live charger '
        'availability and live weather are not connected.</div>',
        unsafe_allow_html=True
    )


# =====================================================
# 12. INTERACTIVE EV STATION MAP
# =====================================================
elif page == "🗺️ EV Station Map":
    st.markdown("""
    <div class="ev-header">
        <h1>🗺️ EV Charging Station Map</h1>
        <div class="ev-subtitle">
            Explore the recorded locations and basic details of charging stations
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        "Upload the original Excel workbook. The map reads station coordinates "
        "from its **sites** sheet and does not modify your workbook."
    )

    map_file = st.file_uploader(
        "Upload EV_dataset.xlsx",
        type=["xlsx", "xls"],
        key="station_map_workbook",
        help="The workbook must contain a sheet named 'sites' with site_id, longitude, and latitude."
    )

    if map_file is None:
        st.info(
            "Please upload your original EV_dataset.xlsx file to display the "
            "47 station locations."
        )
    else:
        station_data, map_error = load_station_locations(map_file.getvalue())

        if map_error:
            st.error(map_error)
        else:
            st.success(
                f"Loaded {len(station_data)} station locations from the 'sites' sheet."
            )

            # The source workbook's information sheet identifies Johannesburg.
            st.warning(
                "Geographic source: Johannesburg, South Africa. These are the "
                "locations recorded in the original dataset, not Tamil Nadu stations."
            )

            map_col1, map_col2, map_col3 = st.columns(3)
            map_col1.metric("Mapped Stations", f"{len(station_data)}")
            map_col2.metric(
                "Stations with Coordinates",
                f"{station_data[['longitude', 'latitude']].drop_duplicates().shape[0]}"
            )
            if "charger_num" in station_data.columns:
                charger_total = pd.to_numeric(
                    station_data["charger_num"], errors="coerce"
                ).sum()
                map_col3.metric("Recorded Chargers", f"{charger_total:,.0f}")
            else:
                map_col3.metric("Coordinate Columns", "2")

            st.markdown("### 📍 Station Locations")
            map_points = station_data.rename(
                columns={"latitude": "latitude", "longitude": "longitude"}
            )
            st.map(
                map_points,
                latitude="latitude",
                longitude="longitude",
                size=80
            )

            st.markdown("### 🔎 Station Details")
            available_ids = sorted(station_data["site_id"].unique().tolist())
            selected_site = st.selectbox(
                "Choose a station",
                available_ids,
                format_func=station_name,
                key="map_selected_site"
            )
            selected_row = station_data[
                station_data["site_id"] == selected_site
            ].iloc[0]

            detail1, detail2, detail3 = st.columns(3)
            detail1.metric("Station", station_name(selected_site))
            detail2.metric("Longitude", f"{selected_row['longitude']:.6f}")
            detail3.metric("Latitude", f"{selected_row['latitude']:.6f}")

            optional_details = [
                column for column in
                ["charger_num", "total_duration", "total_volume", "avg_power", "perimeter", "area"]
                if column in station_data.columns
            ]
            if optional_details:
                st.markdown("#### Recorded site information")
                st.dataframe(
                    selected_row[optional_details].to_frame("Value"),
                    width="stretch"
                )

            st.markdown("### 📋 All Mapped Stations")
            display_columns = [
                column for column in
                ["site_id", "longitude", "latitude", "charger_num",
                 "total_duration", "total_volume", "avg_power"]
                if column in station_data.columns
            ]
            st.dataframe(
                station_data[display_columns].sort_values("site_id"),
                hide_index=True,
                width="stretch"
            )

            st.markdown(
                '<div class="ev-note">This map displays saved station coordinates '
                'from the uploaded workbook. It does not show live charger '
                'availability, occupancy, or real-time station status.</div>',
                unsafe_allow_html=True
            )

# =====================================================
# 13. DATASET MANAGEMENT
# =====================================================
elif page == "🗂️ Dataset Management":
    st.markdown("""
    <div class="ev-header">
        <h1>🗂️ Dataset Management</h1>
        <div class="ev-subtitle">
            Upload, inspect, clean, and download CSV or Excel datasets
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 1. Upload a dataset")
    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Your uploaded file is processed in this app session."
    )

    if uploaded_file is not None:
        try:
            file_name = uploaded_file.name.lower()

            if file_name.endswith(".csv"):
                uploaded_df = pd.read_csv(uploaded_file)
            else:
                excel_file = pd.ExcelFile(uploaded_file)
                sheet_names = excel_file.sheet_names

                selected_sheet = st.selectbox(
                    "Choose an Excel sheet",
                    sheet_names,
                    key="dataset_excel_sheet"
                )
                uploaded_df = pd.read_excel(
                    uploaded_file,
                    sheet_name=selected_sheet
                )

            st.session_state["dataset_original"] = uploaded_df.copy()
            st.session_state["dataset_cleaned"] = uploaded_df.copy()
            st.session_state["dataset_filename"] = uploaded_file.name

        except Exception as error:
            st.error(f"Could not read this file: {error}")

    if "dataset_cleaned" in st.session_state:
        original_df = st.session_state["dataset_original"]
        working_df = st.session_state["dataset_cleaned"]

        st.markdown("---")
        st.markdown("### 2. Dataset overview")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Rows", f"{working_df.shape[0]:,}")
        r2.metric("Columns", f"{working_df.shape[1]:,}")
        r3.metric("Missing Cells", f"{int(working_df.isna().sum().sum()):,}")
        r4.metric("Duplicate Rows", f"{int(working_df.duplicated().sum()):,}")

        st.markdown("### 3. Preview dataset")
        # Adjust the preview control to the size of the selected dataset.
        # A slider needs min_value < max_value, so use a simple preview
        # when the sheet contains 5 or fewer rows.
        if len(working_df) > 5:
            preview_rows = st.slider(
                "Number of rows to preview",
                min_value=5,
                max_value=min(100, len(working_df)),
                value=min(10, len(working_df)),
                key="dataset_preview_rows"
            )
        else:
            preview_rows = len(working_df)
            st.caption(f"Showing all {preview_rows} available rows.")

        st.dataframe(
            working_df.head(preview_rows),
            width="stretch",
            hide_index=True
        )

        st.markdown("### 4. Missing-value analysis")
        missing_report = pd.DataFrame({
            "Column": working_df.columns,
            "Missing Values": working_df.isna().sum().values,
            "Missing Percentage (%)": (
                working_df.isna().mean().values * 100
            ).round(2)
        })
        missing_report = missing_report.sort_values(
            "Missing Values", ascending=False
        )
        st.dataframe(missing_report, hide_index=True, width="stretch")

        st.markdown("### 5. Duplicate analysis")
        duplicate_count = int(working_df.duplicated().sum())
        if duplicate_count:
            st.warning(f"Found {duplicate_count} duplicate rows.")
            if st.checkbox("Show duplicate rows", key="show_dataset_duplicates"):
                st.dataframe(
                    working_df[working_df.duplicated(keep=False)],
                    hide_index=True,
                    width="stretch"
                )
        else:
            st.success("No duplicate rows found.")

        st.markdown("### 6. Clean dataset")
        st.caption(
            "Choose how to handle missing values. Cleaning changes the "
            "working copy; the original uploaded data remains available "
            "until you reset or upload another file."
        )

        missing_action = st.selectbox(
            "Missing-value treatment",
            [
                "Keep missing values",
                "Remove rows containing missing values",
                "Fill numeric columns with their median",
                "Fill numeric columns with 0",
                "Fill all missing values with a custom value"
            ],
            key="dataset_missing_action"
        )

        custom_fill = ""
        if missing_action == "Fill all missing values with a custom value":
            custom_fill = st.text_input(
                "Enter replacement value",
                value="Unknown",
                key="dataset_custom_fill"
            )

        remove_duplicates = st.checkbox(
            "Remove duplicate rows",
            value=True,
            key="dataset_remove_duplicates"
        )

        if st.button("🧹 Apply Cleaning", key="apply_dataset_cleaning"):
            cleaned = working_df.copy()

            if missing_action == "Remove rows containing missing values":
                cleaned = cleaned.dropna()
            elif missing_action == "Fill numeric columns with their median":
                numeric_cols = cleaned.select_dtypes(include="number").columns
                for column in numeric_cols:
                    median_value = cleaned[column].median()
                    cleaned[column] = cleaned[column].fillna(median_value)
            elif missing_action == "Fill numeric columns with 0":
                numeric_cols = cleaned.select_dtypes(include="number").columns
                cleaned[numeric_cols] = cleaned[numeric_cols].fillna(0)
            elif missing_action == "Fill all missing values with a custom value":
                cleaned = cleaned.fillna(custom_fill)

            if remove_duplicates:
                cleaned = cleaned.drop_duplicates()

            st.session_state["dataset_cleaned"] = cleaned.reset_index(drop=True)
            st.success("Cleaning applied successfully!")
            st.rerun()

        st.markdown("### 7. Download cleaned dataset")
        cleaned_df = st.session_state["dataset_cleaned"]
        csv_bytes = cleaned_df.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="⬇️ Download Cleaned CSV",
            data=csv_bytes,
            file_name="cleaned_ev_dataset.csv",
            mime="text/csv",
            key="download_cleaned_dataset"
        )

        if st.button("↩️ Reset to Original Uploaded Dataset"):
            st.session_state["dataset_cleaned"] = original_df.copy()
            st.success("Dataset reset to the original uploaded version.")
            st.rerun()

        st.markdown(
            '<div class="ev-note">Dataset cleaning is performed on the '
            'uploaded copy in this session. It does not overwrite your '
            'original file or change the model forecast CSV.</div>',
            unsafe_allow_html=True
        )
    else:
        st.info(
            "Upload a CSV or Excel file to begin. Your existing EV forecast "
            "and machine-learning pages are not changed by this tool."
        )
