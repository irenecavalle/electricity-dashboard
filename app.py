import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import numpy as np
import glob
import os
from io import StringIO
import re

st.set_page_config(page_title="Electricity Demand Dashboard", layout="wide")
st.title(f"Electricity Demand Dashboard – {date.today().year}")

st.markdown("""
This dashboard was inspired by the April 2025 blackout that affected many areas.
It supports analysts and decision-makers by visualizing electricity demand, highlighting risk, and exploring energy generation mix.
""")

with st.expander("How to Use This App"):
    st.markdown("""
    1. Click **Start Analysis** to load demand and generation data.
    2. Use **Detailed Demand Data** to view raw trends and changes.
    3. Use **Trend Visualization** to compare real vs forecasted demand.
    4. Review **Key Performance Metrics** to assess volatility and risk.
    5. Explore **Generation Breakdown** to understand energy source contributions.
    """)

def get_base_path(subfolder):
    return os.path.join("sample_data", subfolder)

@st.cache_data(ttl=3600)
def load_demand_data():
    base_path = get_base_path("demand")
    files = glob.glob(os.path.join(base_path, "Custom-Report-2025-??-??-Seguimiento de la demanda de energía eléctrica (MW).csv"))
    all_data = []
    for file_path in files:
        try:
            df = pd.read_csv(file_path, encoding="ISO-8859-1", sep=";", on_bad_lines='skip')
            raw_lines = df.iloc[:, 0].tolist()
            clean_lines = [line.strip() for line in raw_lines if "," in line]
            parsed = pd.read_csv(StringIO("\n".join(clean_lines)), sep=",", quotechar='"')
            parsed.reset_index(inplace=True)
            parsed.rename(columns={"index": "Datetime"}, inplace=True)
            parsed["Datetime"] = pd.to_datetime(parsed["Datetime"], errors='coerce')
            parsed.dropna(subset=["Datetime"], inplace=True)
            parsed.set_index("Datetime", inplace=True)
            if not all(col in parsed.columns for col in ["Real", "Prevista"]):
                continue
            parsed = parsed[["Real", "Prevista"]]
            all_data.append(parsed)
        except Exception as e:
            st.warning(f"Could not load {file_path}: {e}")
    if not all_data:
        return pd.DataFrame()
    df_all = pd.concat(all_data).sort_index()
    df_all["Daily Change"] = df_all["Real"].pct_change()
    df_all["Rolling Avg (30d)"] = df_all["Real"].rolling(window=30, min_periods=1).mean()
    return df_all

@st.cache_data(ttl=3600)
def load_generation_data():
    base_path = get_base_path("generation")
    files = glob.glob(os.path.join(base_path, "Custom-Report-2025-??-??-Estructura de generación (MW).csv"))
    all_data = []
    for file_path in files:
        try:
            filename = os.path.basename(file_path)
            match = re.search(r"2025-(\d{2})-(\d{2})", filename)
            if not match:
                continue
            report_date = f"2025-{match.group(1)}-{match.group(2)}"
            df = pd.read_csv(file_path, encoding="ISO-8859-1", sep=";", on_bad_lines='skip')
            raw_lines = df.iloc[:, 0].tolist()
            clean_lines = [line.strip() for line in raw_lines if "," in line]
            gen_df = pd.read_csv(StringIO("\n".join(clean_lines)))
            if "Hora" not in gen_df.columns:
                continue
            if not gen_df["Hora"].astype(str).str.contains(":").any():
                gen_df["Hora"] = gen_df["Hora"].astype(str).str.zfill(4).str[:2] + ":" + gen_df["Hora"].astype(str).str[2:]
            gen_df["Hora"] = pd.to_datetime(report_date + " " + gen_df["Hora"].astype(str), errors="coerce")
            for col in gen_df.columns[1:]:
                gen_df[col] = pd.to_numeric(gen_df[col].astype(str).str.replace('"', ''), errors="coerce")
            all_data.append(gen_df)
        except Exception as e:
            st.warning(f"Error processing {file_path}: {e}")
    if not all_data:
        return pd.DataFrame()
    return pd.concat(all_data).dropna(subset=["Hora"]).sort_values("Hora")

if "dashboard_active" not in st.session_state:
    st.session_state.dashboard_active = False

if not st.session_state.dashboard_active:
    if st.button("Start Analysis"):
        st.session_state.dashboard_active = True

if st.session_state.dashboard_active:
    with st.spinner("Loading data..."):
        data = load_demand_data()
        gen_df = load_generation_data()

    if data.empty or gen_df.empty:
        st.error("No valid data found. Please check dataset folders.")
        st.stop()

    st.markdown("## Detailed Demand Data")
    with st.expander("Show Data Table"):
        styled = data.copy().dropna()
        styled['Daily Change (%)'] = styled['Daily Change'] * 100
        styled['Daily Change (%)'] = styled['Daily Change (%)'].map(lambda x: f"{x:.2f}%")
        styled = styled.reset_index()[['Datetime', 'Real', 'Prevista', 'Daily Change (%)']]

        def highlight(val):
            try:
                return f"color: {'green' if float(val.replace('%','')) >= 0 else 'red'}"
            except:
                return ""

        st.data_editor(styled.style.applymap(highlight, subset=['Daily Change (%)']), use_container_width=True)

    st.markdown("## Trend Visualization")
    unique_dates = sorted(list(set(data.index.date)))
    start_day, end_day = st.date_input("Select day range:", value=(min(unique_dates), max(unique_dates)), min_value=min(unique_dates), max_value=max(unique_dates))
    range_data = data[(data.index.date >= start_day) & (data.index.date <= end_day)]

    if not range_data.empty:
        fig = px.line(range_data.reset_index(), x="Datetime", y=["Real", "Prevista"],
                      color_discrete_sequence=["#1f77b4", "#2ca02c"],
                      labels={"value": "MW", "Datetime": "Time", "variable": "Type"},
                      title=f"Demand from {start_day} to {end_day}",
                      template="plotly_white")

        blackout_date = pd.to_datetime("2025-04-27")
        if blackout_date >= start_day and blackout_date <= end_day:
            fig.add_vline(x=blackout_date, line_dash="dash", line_color="red",
                          annotation_text="Blackout", annotation_position="top left")

        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Daily Total Demand")
        st.caption("Total real electricity demand per day within the selected date range.")
        daily_totals = range_data.resample('D').sum(numeric_only=True)
        fig_bar_total = px.bar(daily_totals.reset_index(), x="Datetime", y="Real",
                               title="Total Daily Demand (MW)",
                               labels={"Real": "Total MW", "Datetime": "Date"},
                               template="plotly_white")
        st.plotly_chart(fig_bar_total, use_container_width=True)

        st.markdown("### Download Filtered Demand Data")
        st.caption("Export the data shown above for external use.")
        csv_download = range_data.reset_index().to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV",
            data=csv_download,
            file_name=f"electricity_demand_{start_day}_to_{end_day}.csv",
            mime='text/csv')

    st.markdown("## Key Performance Metrics")
    day_data = data[data.index.date == end_day]
    latest = float(day_data['Real'].iloc[-1]) if not day_data.empty else float("nan")
    daily_change = day_data['Daily Change'].mean() if not day_data.empty else float("nan")
    volatility = day_data['Daily Change'].std() if not day_data.empty else float("nan")
    max_drop = (day_data['Real'].max() - day_data['Real'].min()) / day_data['Real'].max() if not day_data.empty else float("nan")
    var_95 = day_data['Daily Change'].quantile(0.05) if not day_data.empty else float("nan")

    metrics = ["Latest Demand", "Volatility", "Maximum Drop", "VaR (95%)"]
    selected = st.multiselect("Choose metrics to display:", metrics, default=metrics)
    cols = st.columns(len(selected))
    for i, m in enumerate(selected):
        if m == "Latest Demand":
            cols[i].metric(m, f"{latest:,.0f} MW")
        elif m == "Volatility":
            cols[i].metric(m, f"{volatility*100:.2f}%")
        elif m == "Maximum Drop":
            cols[i].metric(m, f"{max_drop*100:.2f}%")
        elif m == "VaR (95%)":
            cols[i].metric(m, f"{var_95*100:.2f}%")

    st.markdown("## Generation Breakdown")
    gen_df["Date"] = gen_df["Hora"].dt.date
    selected_gen_date = st.selectbox("Select Date:", sorted(gen_df["Date"].unique()), index=len(gen_df["Date"].unique()) - 1)
    mix = ["Eólica", "Nuclear", "Carbón", "Ciclo combinado", "Solar fotovoltaica", "Solar térmica",
           "Térmica renovable", "Motores diésel", "Turbina de gas", "Turbina de vapor",
           "Generación auxiliar", "Cogeneración y residuos"]
    daily = gen_df[gen_df["Date"] == selected_gen_date]
    avg_mix = daily[mix].mean().to_frame(name="MW")
    avg_mix = avg_mix[avg_mix["MW"] > 0]

    tab1, tab2 = st.tabs(["Pie Chart", "Bar Chart"])
    with tab1:
        fig_pie = px.pie(avg_mix, values="MW", names=avg_mix.index,
                         color_discrete_sequence=px.colors.sequential.Blues,
                         title=f"Generation Mix – {selected_gen_date}", hole=0.3)
        fig_pie.update_traces(textinfo='percent+label', hoverinfo='label+value+percent')
        st.plotly_chart(fig_pie, use_container_width=True)

    with tab2:
        fig_bar = px.bar(avg_mix.reset_index(), x="index", y="MW",
                         title=f"Generation Mix – {selected_gen_date} (Bar)", labels={"index": "Source"}, template="plotly_white")
        st.plotly_chart(fig_bar, use_container_width=True)
