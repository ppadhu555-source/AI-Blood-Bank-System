import os
import sys
import hashlib
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as nn_st
from datetime import datetime, date, timedelta
from sqlalchemy import text

# Add parent directory to path and define BASE_DIR
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
from database.db_manager import SessionLocal, engine
from expiry.expiry_tracker import get_expiry_alerts
from allocation.allocation_engine import generate_transfer_recommendations, process_allocation_transfer, check_stock_shortages
from forecasting.demand_forecast import generate_forecasts_for_range
from reports.reports import get_report_data, generate_pdf_report

# Streamlit App Configuration
nn_st.set_page_config(
    page_title="AI Blood Bank & Smart Allocation Dashboard",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Design Aesthetics
nn_st.markdown("""
<style>
    /* Global Styling */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .main {
        background-color: #f7f9fc;
    }
    
    /* Premium Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #2b0c11 !important;
        color: #ffffff !important;
    }
    
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label {
        color: #ffffff !important;
    }
    
    /* Header Card Banner */
    .banner-container {
        background: linear-gradient(135deg, #800020 0%, #3a0007 100%);
        padding: 30px;
        border-radius: 15px;
        color: white;
        margin-bottom: 25px;
        box-shadow: 0 4px 20px rgba(128, 0, 32, 0.25);
    }
    
    .banner-title {
        font-size: 32px;
        font-weight: 700;
        margin: 0;
    }
    
    .banner-subtitle {
        font-size: 16px;
        font-weight: 300;
        opacity: 0.85;
        margin-top: 5px;
    }
    
    /* Glassmorphism Metric Cards */
    .metric-card {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(220, 220, 220, 0.6);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 32px 0 rgba(128, 0, 32, 0.1);
    }
    
    .metric-title {
        font-size: 14px;
        color: #707070;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .metric-value {
        font-size: 36px;
        font-weight: 700;
        color: #800020;
        margin-top: 5px;
    }
    
    .metric-desc {
        font-size: 12px;
        color: #909090;
        margin-top: 5px;
    }
    
    /* Custom buttons */
    div.stButton > button:first-child {
        background-color: #800020;
        color: white;
        border-radius: 8px;
        padding: 8px 16px;
        border: none;
        font-weight: 600;
        transition: background-color 0.3s ease;
    }
    
    div.stButton > button:first-child:hover {
        background-color: #a30029;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Anchor Date for Simulation
ANCHOR_DATE = date(2026, 7, 5)

# --- Authentication Logic ---
def get_sha256(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def check_login(username, password):
    session = SessionLocal()
    try:
        query = text("SELECT user_id, username, password_hash, role, hospital_id FROM users WHERE username = :u")
        user = session.execute(query, {"u": username}).fetchone()
        if user and user.password_hash == get_sha256(password):
            return {
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role,
                "hospital_id": user.hospital_id
            }
        return None
    finally:
        session.close()

def page_login():
    nn_st.markdown("<div style='height: 80px'></div>", unsafe_allow_html=True)
    col1, col2, col3 = nn_st.columns([1, 2, 1])
    with col2:
        nn_st.markdown("""
        <div style='background-color: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); border-top: 6px solid #800020;'>
            <h2 style='text-align: center; color: #800020; margin-bottom: 5px;'>🩸 RedFlow AI</h2>
            <p style='text-align: center; color: #666666; font-size: 14px; margin-bottom: 25px;'>Blood Bank Demand Forecasting & Allocation System</p>
        </div>
        """, unsafe_allow_html=True)
        
        with nn_st.form("login_form"):
            username = nn_st.text_input("Username")
            password = nn_st.text_input("Password", type="password")
            submitted = nn_st.form_submit_button("Sign In", use_container_width=True)
            
            if submitted:
                user_info = check_login(username, password)
                if user_info:
                    nn_st.session_state.authenticated = True
                    nn_st.session_state.user = user_info
                    nn_st.success("Successfully logged in!")
                    nn_st.rerun()
                else:
                    nn_st.error("Invalid username or password.")

# --- Database Query Helpers ---
def run_query(sql, params=None):
    session = SessionLocal()
    try:
        res = session.execute(text(sql), params or {})
        if res.returns_rows:
            return pd.DataFrame([dict(r._mapping) for r in res.fetchall()])
        return pd.DataFrame()
    finally:
        session.close()

def get_hospitals():
    return run_query("SELECT * FROM hospitals")

def get_components():
    return run_query("SELECT * FROM blood_components")

# --- UI Page Components ---

def render_banner(title, subtitle):
    nn_st.markdown(f"""
    <div class="banner-container">
        <div class="banner-title">{title}</div>
        <div class="banner-subtitle">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

def card_metric(title, value, description):
    return f"""
    <div class="metric-card">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-desc">{description}</div>
    </div>
    """

def page_dashboard():
    render_banner("Overview Dashboard", "Real-time key performance indicators and status of the regional blood supply network.")
    
    # Hospital specific filter if hospital staff
    hosp_filter = ""
    params = {}
    if nn_st.session_state.user["role"] == "Hospital Staff":
        h_id = nn_st.session_state.user["hospital_id"]
        hosp_filter = " AND hospital_id = :h_id "
        params = {"h_id": h_id}
        hosp_name = run_query("SELECT name FROM hospitals WHERE hospital_id = :h_id", {"h_id": h_id}).iloc[0]['name']
        nn_st.subheader(f"Hospital Scope: {hosp_name}")
        
    # KPIs calculations
    # 1. Total Stock
    stock_df = run_query(f"SELECT SUM(units_available) as tot FROM blood_inventory WHERE 1=1 {hosp_filter} AND status IN ('Available', 'Expiring')", params)
    total_stock = int(stock_df.iloc[0]['tot']) if not stock_df.empty and stock_df.iloc[0]['tot'] else 0
    
    # 2. Expiring Units (within 5 days)
    expiring_df = run_query(f"SELECT SUM(units_available) as tot FROM blood_inventory WHERE 1=1 {hosp_filter} AND status = 'Expiring'", params)
    expiring_stock = int(expiring_df.iloc[0]['tot']) if not expiring_df.empty and expiring_df.iloc[0]['tot'] else 0
    
    # 3. Active Shortage Alerts
    alert_filter = ""
    if nn_st.session_state.user["role"] == "Hospital Staff":
        alert_filter = " WHERE hospital_id = :h_id AND alert_type = 'Shortage'"
    else:
        alert_filter = " WHERE alert_type = 'Shortage'"
    shortage_df = run_query(f"SELECT COUNT(*) as count FROM alerts {alert_filter}", params)
    shortages_count = int(shortage_df.iloc[0]['count']) if not shortage_df.empty else 0
    
    # 4. Total Donations (Current Period)
    donations_df = run_query(f"SELECT SUM(units_donated) as tot FROM blood_donations WHERE 1=1 {hosp_filter}", params)
    total_donations = int(donations_df.iloc[0]['tot']) if not donations_df.empty and donations_df.iloc[0]['tot'] else 0

    col1, col2, col3, col4 = nn_st.columns(4)
    with col1:
        nn_st.markdown(card_metric("Total Stock (Units)", f"{total_stock}", "Active usable inventory units"), unsafe_allow_html=True)
    with col2:
        nn_st.markdown(card_metric("Expiring Units", f"{expiring_stock}", "Units expiring in <= 5 days"), unsafe_allow_html=True)
    with col3:
        nn_st.markdown(card_metric("Active Shortages", f"{shortages_count}", "Hospitals with stock below safety margin"), unsafe_allow_html=True)
    with col4:
        nn_st.markdown(card_metric("Total Donations", f"{total_donations}", "Accumulated blood donations"), unsafe_allow_html=True)

    nn_st.markdown("<div style='height: 25px'></div>", unsafe_allow_html=True)
    
    # Stock Distribution Charts
    c1, c2 = nn_st.columns(2)
    with c1:
        nn_st.subheader("Blood Group Distribution")
        bg_stock = run_query(f"SELECT blood_group, SUM(units_available) as units FROM blood_inventory WHERE 1=1 {hosp_filter} AND status IN ('Available', 'Expiring') GROUP BY blood_group", params)
        if not bg_stock.empty:
            fig = px.pie(bg_stock, values='units', names='blood_group', color_discrete_sequence=px.colors.sequential.RdBu)
            nn_st.plotly_chart(fig, use_container_width=True)
        else:
            nn_st.write("No stock data available.")
            
    with c2:
        nn_st.subheader("Component Stock Breakdown")
        comp_stock = run_query(f"SELECT c.name as component, SUM(i.units_available) as units FROM blood_inventory i JOIN blood_components c ON i.component_id = c.component_id WHERE 1=1 {hosp_filter.replace('hospital_id', 'i.hospital_id')} AND i.status IN ('Available', 'Expiring') GROUP BY c.name", params)
        if not comp_stock.empty:
            fig = px.bar(comp_stock, x='component', y='units', color='component', color_discrete_sequence=px.colors.qualitative.Pastel)
            nn_st.plotly_chart(fig, use_container_width=True)
        else:
            nn_st.write("No component data available.")

def page_hospitals():
    render_banner("Regional Hospital Network", "Overview of the regional hospitals, bed capacities, and coordinates.")
    hosp_df = get_hospitals()
    
    # Map coordinates
    nn_st.subheader("Geographical Distribution")
    map_df = hosp_df.rename(columns={'latitude': 'lat', 'longitude': 'lon'})
    nn_st.map(map_df)
    
    nn_st.subheader("Hospital Summary Details")
    nn_st.dataframe(hosp_df, use_container_width=True)

def page_inventory():
    render_banner("Blood Inventory & Donation Logging", "Track available inventory units and record incoming donations.")
    
    # Tabs for viewing stock and logging donations
    tab1, tab2 = nn_st.tabs(["Current Stock", "Log Donation Manually"])
    
    with tab1:
        # Filters
        hosp_df = get_hospitals()
        comp_df = get_components()
        
        c1, c2, c3 = nn_st.columns(3)
        with c1:
            hosp_list = ["All"] + list(hosp_df['name'])
            sel_hosp = nn_st.selectbox("Select Hospital Filter", hosp_list)
        with c2:
            comp_list = ["All"] + list(comp_df['name'])
            sel_comp = nn_st.selectbox("Select Component Filter", comp_list)
        with c3:
            sel_bg = nn_st.selectbox("Select Blood Group Filter", ["All", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
            
        # SQL construct
        conditions = ["units_available > 0", "status != 'Transferred'"]
        sql_params = {}
        if sel_hosp != "All":
            conditions.append("h.name = :h_name")
            sql_params["h_name"] = sel_hosp
        if sel_comp != "All":
            conditions.append("c.name = :c_name")
            sql_params["c_name"] = sel_comp
        if sel_bg != "All":
            conditions.append("i.blood_group = :bg")
            sql_params["bg"] = sel_bg
            
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT i.inventory_id, h.name as hospital_name, c.name as component_name, 
                   i.blood_group, i.units_available, i.received_date, i.expiry_date, i.status
            FROM blood_inventory i
            JOIN hospitals h ON i.hospital_id = h.hospital_id
            JOIN blood_components c ON i.component_id = c.component_id
            WHERE {where_clause}
            ORDER BY i.expiry_date ASC
        """
        
        inv_data = run_query(query, sql_params)
        nn_st.dataframe(inv_data, use_container_width=True)
        
    with tab2:
        nn_st.subheader("Record Donation Batch")
        
        with nn_st.form("donation_form"):
            hosp_df = get_hospitals()
            comp_df = get_components()
            
            # If hospital staff, pre-select and disable hospital selection
            if nn_st.session_state.user["role"] == "Hospital Staff":
                staff_hosp_id = nn_st.session_state.user["hospital_id"]
                staff_hosp_name = hosp_df[hosp_df['hospital_id'] == staff_hosp_id].iloc[0]['name']
                don_hosp = nn_st.selectbox("Hospital", [staff_hosp_name], disabled=True)
                don_hosp_id = staff_hosp_id
            else:
                don_hosp = nn_st.selectbox("Select Hospital", hosp_df['name'])
                don_hosp_id = int(hosp_df[hosp_df['name'] == don_hosp].iloc[0]['hospital_id'])
                
            don_name = nn_st.text_input("Donor Name", value="Anonymous Donor")
            don_bg = nn_st.selectbox("Donor Blood Group", ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
            don_comp = nn_st.selectbox("Component Type", comp_df['name'])
            don_comp_id = int(comp_df[comp_df['name'] == don_comp].iloc[0]['component_id'])
            don_units = nn_st.number_input("Units Donated", min_value=1, max_value=10, value=1)
            don_date = nn_st.date_input("Donation Date", value=ANCHOR_DATE)
            
            submitted = nn_st.form_submit_button("Register Donation Batch")
            
            if submitted:
                # Calculate expiry date
                shelf_life = int(comp_df[comp_df['component_id'] == don_comp_id].iloc[0]['shelf_life_days'])
                exp_date = don_date + timedelta(days=shelf_life)
                
                # Write to Database
                session = SessionLocal()
                try:
                    # 1. Write to blood_donations
                    session.execute(
                        text("""
                            INSERT INTO blood_donations (hospital_id, donor_name, blood_group, component_id, units_donated, donation_date, expiry_date)
                            VALUES (:h_id, :name, :bg, :c_id, :units, :don_date, :exp_date)
                        """),
                        {
                            "h_id": don_hosp_id, "name": don_name, "bg": don_bg, "c_id": don_comp_id, 
                            "units": don_units, "don_date": don_date, "exp_date": exp_date
                        }
                    )
                    
                    # 2. Write to blood_inventory
                    session.execute(
                        text("""
                            INSERT INTO blood_inventory (hospital_id, component_id, blood_group, units_available, received_date, expiry_date, status)
                            VALUES (:h_id, :c_id, :bg, :units, :don_date, :exp_date, 'Available')
                        """),
                        {
                            "h_id": don_hosp_id, "c_id": don_comp_id, "bg": don_bg, 
                            "units": don_units, "don_date": don_date, "exp_date": exp_date
                        }
                    )
                    session.commit()
                    nn_st.success(f"Donation registered! Expiry date set to: {exp_date}")
                except Exception as e:
                    session.rollback()
                    nn_st.error(f"Error registering donation: {e}")
                finally:
                    session.close()

def page_forecast():
    render_banner("AI Demand Forecasting", "Machine learning predictions for blood unit demand at different planning horizons.")
    
    # Allow user to run forecasts dynamically
    nn_st.sidebar.subheader("Forecast Operations")
    if nn_st.sidebar.button("Run/Update Predictions (7 Days)"):
        with nn_st.spinner("Recalculating predictions via ML model..."):
            success, msg = generate_forecasts_for_range(ANCHOR_DATE + timedelta(days=1), ANCHOR_DATE + timedelta(days=7))
            if success:
                nn_st.sidebar.success("Predictions updated in DB!")
                nn_st.rerun()
            else:
                nn_st.sidebar.error(msg)
                
    hosp_df = get_hospitals()
    comp_df = get_components()
    
    # Dynamic Prediction View Filters
    c1, c2, c3 = nn_st.columns(3)
    with c1:
        hosp_list = ["All"] + list(hosp_df['name'])
        sel_hosp = nn_st.selectbox("Forecast Hospital Filter", hosp_list)
    with c2:
        comp_list = ["All"] + list(comp_df['name'])
        sel_comp = nn_st.selectbox("Forecast Component Filter", comp_list)
    with c3:
        sel_bg = nn_st.selectbox("Forecast Blood Group Filter", ["All", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
        
    conditions = []
    sql_params = {}
    if sel_hosp != "All":
        conditions.append("h.name = :h_name")
        sql_params["h_name"] = sel_hosp
    if sel_comp != "All":
        conditions.append("c.name = :c_name")
        sql_params["c_name"] = sel_comp
    if sel_bg != "All":
        conditions.append("p.blood_group = :bg")
        sql_params["bg"] = sel_bg
        
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT p.prediction_date, h.name as hospital_name, c.name as component_name, 
               p.blood_group, p.predicted_demand, p.confidence_interval_low, p.confidence_interval_high
        FROM predictions p
        JOIN hospitals h ON p.hospital_id = h.hospital_id
        JOIN blood_components c ON p.component_id = c.component_id
        {where_clause}
        ORDER BY p.prediction_date ASC, p.predicted_demand DESC
    """
    
    pred_data = run_query(query, sql_params)
    
    if not pred_data.empty:
        # Aggregated Timeline Line Chart
        nn_st.subheader("Forecasted Regional Demand Trend")
        timeline = pred_data.groupby('prediction_date')['predicted_demand'].sum().reset_index()
        fig = px.line(timeline, x='prediction_date', y='predicted_demand', 
                      title="Total Predicted Regional Daily Demand",
                      labels={'prediction_date': 'Date', 'predicted_demand': 'Total Forecast Units'},
                      color_discrete_sequence=['crimson'])
        nn_st.plotly_chart(fig, use_container_width=True)
        
        nn_st.subheader("Predictions Table")
        nn_st.dataframe(pred_data, use_container_width=True)
    else:
        nn_st.warning("No predictions found in the database. Use the sidebar operation 'Run/Update Predictions' to generate forecasts.")

def page_expiry():
    render_banner("Expiry Risk Tracker", "Detect expired blood units and track batches approaching shelf life limit.")
    
    # Operation to check alerts
    if nn_st.sidebar.button("Run Expiry Check"):
        get_expiry_alerts(ANCHOR_DATE)
        nn_st.sidebar.success("Checked and updated alerts table!")
        nn_st.rerun()
        
    alerts = get_expiry_alerts(ANCHOR_DATE)
    
    if alerts:
        alerts_df = pd.DataFrame(alerts)
        
        # Display summary counts
        c1, c2 = nn_st.columns(2)
        with c1:
            expired_units = alerts_df[alerts_df['days_remaining'] < 0]['units'].sum()
            nn_st.error(f"🔴 Expired Stock: {expired_units} Units")
        with c2:
            expiring_units = alerts_df[alerts_df['days_remaining'] >= 0]['units'].sum()
            nn_st.warning(f"🟡 Expiring Stock (<7 Days): {expiring_units} Units")
            
        nn_st.markdown("<div style='height: 15px'></div>", unsafe_allow_html=True)
        
        # Display alerts table
        nn_st.subheader("Detailed Expiry Alert Logs")
        display_df = alerts_df[['severity', 'message', 'units', 'expiry_date', 'days_remaining']]
        
        # Styled dataframe or colored list
        for idx, row in display_df.iterrows():
            badge = "🔴" if row['severity'] == "Critical" else "🟡"
            nn_st.markdown(f"**{badge} {row['severity'].upper()}:** {row['message']}")
    else:
        nn_st.success("Green Status: No active expiry risk alerts detected.")

def page_shortages():
    render_banner("Stock Shortage Alerts", "Identifies locations where current inventory is insufficient relative to predicted demand.")
    
    # Operation to run shortage check
    if nn_st.sidebar.button("Run Shortage Analysis"):
        check_stock_shortages(ANCHOR_DATE)
        nn_st.sidebar.success("Analyzed stocks against demand!")
        nn_st.rerun()
        
    shortages = check_stock_shortages(ANCHOR_DATE)
    
    if shortages:
        shortages_df = pd.DataFrame(shortages)
        
        c1, c2 = nn_st.columns(2)
        with c1:
            critical_count = len(shortages_df[shortages_df['status'] == 'Critical'])
            nn_st.error(f"🚨 Critical Shortages: {critical_count} Alert(s)")
        with c2:
            medium_count = len(shortages_df[shortages_df['status'] == 'Medium Risk'])
            nn_st.warning(f"⚠️ Medium Risk Shortages: {medium_count} Alert(s)")
            
        nn_st.markdown("<div style='height: 15px'></div>", unsafe_allow_html=True)
        
        # Display shortages table
        nn_st.subheader("Shortage Alert Details")
        nn_st.dataframe(shortages_df[['hospital_name', 'component_name', 'blood_group', 'available_units', 'safety_threshold', 'status']], use_container_width=True)
    else:
        nn_st.success("Green Status: All hospitals are fully stocked above safety margins.")

def page_allocation():
    render_banner("Smart Blood Allocation & Transfers", "Algorithmic recommendations for blood unit transfers to resolve regional shortages.")
    
    recs = generate_transfer_recommendations(ANCHOR_DATE)
    
    if recs:
        recs_df = pd.DataFrame(recs)
        nn_st.subheader("Top Transfer Recommendations")
        
        # Add action table
        for idx, row in recs_df.iterrows():
            with nn_st.container():
                nn_st.markdown(f"""
                <div style='background-color: white; padding: 20px; border-radius: 10px; border-left: 5px solid #800020; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>
                    <div style='display: flex; justify-content: space-between;'>
                        <strong style='font-size: 16px; color: #800020;'>Recommendation #{idx+1} (Match Score: {row['transfer_score']})</strong>
                        <span style='color: #666666;'>Distance: {row['distance_miles']} miles</span>
                    </div>
                    <p style='margin-top: 10px; font-size: 14px;'>{row['reason']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Transfer Action Button
                btn_key = f"trans_{row['source_hospital_id']}_{row['destination_hospital_id']}_{row['component_id']}_{row['source_blood_group']}_{idx}"
                
                btn_label = f"Approve Transfer ({row['units_to_transfer']} units of {row['source_blood_group']} {row['component_name']})"
                if nn_st.button(btn_label, key=btn_key):
                    success, msg = process_allocation_transfer(
                        int(row['source_hospital_id']), 
                        int(row['destination_hospital_id']), 
                        int(row['component_id']), 
                        row['source_blood_group'], 
                        row['target_blood_group'], 
                        int(row['units_to_transfer']),
                        ANCHOR_DATE
                    )
                    if success:
                        nn_st.success(msg)
                        nn_st.balloons()
                        # Refresh forecasts/alerts and rerun
                        check_stock_shortages(ANCHOR_DATE)
                        get_expiry_alerts(ANCHOR_DATE)
                        nn_st.rerun()
                    else:
                        nn_st.error(msg)
    else:
        nn_st.success("Green Status: Regional stocks are balanced. No transfers recommended.")

def page_analytics():
    render_banner("Advanced Systems Analytics", "Detailed graphs, features, correlations, and distributions of the system.")
    
    tab1, tab2 = nn_st.tabs(["Static Report Visuals", "Interactive Exploration"])
    
    with tab1:
        nn_st.subheader("System Static Visualizations (Saved for PDF Reports)")
        
        c1, c2 = nn_st.columns(2)
        with c1:
            nn_st.image(os.path.join(BASE_DIR, "graphs", "daily_demand.png"), caption="Daily Demand Trend Timeline")
            nn_st.image(os.path.join(BASE_DIR, "graphs", "blood_group_distribution.png"), caption="Blood Group Demand Distribution")
        with c2:
            nn_st.image(os.path.join(BASE_DIR, "graphs", "hospital_wise_demand.png"), caption="Total Historical Demand by Hospital")
            nn_st.image(os.path.join(BASE_DIR, "graphs", "correlation_matrix.png"), caption="ML Feature Correlation Matrix")
            
        c3, c4 = nn_st.columns(2)
        with c3:
            nn_st.image(os.path.join(BASE_DIR, "graphs", "monthly_demand.png"), caption="Aggregate Monthly Seasonal Demand")
            nn_st.image(os.path.join(BASE_DIR, "graphs", "component_distribution.png"), caption="Component Demand Distribution")
        with c4:
            nn_st.image(os.path.join(BASE_DIR, "graphs", "hospital_wise_stock.png"), caption="Current Hospital Stock Levels")
            nn_st.image(os.path.join(BASE_DIR, "graphs", "expiry_trend.png"), caption="Upcoming Expirations (15-Day Outlook)")
            
    with tab2:
        nn_st.subheader("Interactive Database Query & Plotting")
        
        # Plotly plot of historical requests
        requests_df = run_query("SELECT request_date, units_requested, priority FROM blood_requests")
        if not requests_df.empty:
            requests_df['request_date'] = pd.to_datetime(requests_df['request_date'])
            req_agg = requests_df.groupby(['request_date', 'priority'])['units_requested'].sum().reset_index()
            fig = px.area(req_agg, x='request_date', y='units_requested', color='priority', 
                          title="Interactive Historical Demand Area Plot",
                          color_discrete_map={'Emergency': 'crimson', 'Urgent': 'orange', 'Routine': 'blue'})
            nn_st.plotly_chart(fig, use_container_width=True)

def page_reports():
    render_banner("System Reports Generator", "Compile official summaries for auditing, analysis, and clinical logs. Exportable to PDF and CSV.")
    
    report_type = nn_st.selectbox("Select Report Category", ["Demand", "Expiry", "Allocation", "Emergency"])
    
    c1, c2 = nn_st.columns(2)
    with c1:
        start_date = nn_st.date_input("Start Date", value=ANCHOR_DATE - timedelta(days=30))
    with c2:
        end_date = nn_st.date_input("End Date", value=ANCHOR_DATE)
        
    if nn_st.button("Compile Report"):
        summary, df = get_report_data(report_type, start_date, end_date)
        
        nn_st.session_state.compiled_report = {
            "type": report_type,
            "summary": summary,
            "data": df,
            "start": start_date,
            "end": end_date
        }
        
    if "compiled_report" in nn_st.session_state and nn_st.session_state.compiled_report["type"] == report_type:
        report = nn_st.session_state.compiled_report
        
        nn_st.subheader(f"Compiled {report['type']} Summary")
        
        # Display KPI card data
        c1, c2 = nn_st.columns([1, 2])
        with c1:
            for k, v in report['summary'].items():
                nn_st.write(f"**{k}:** {v}")
        with c2:
            nn_st.dataframe(report['data'].head(20), use_container_width=True)
            
        # Download buttons
        nn_st.markdown("<div style='height: 15px'></div>", unsafe_allow_html=True)
        
        # 1. Download CSV Button
        csv_data = report['data'].to_csv(index=False).encode('utf-8')
        
        # 2. Download PDF Button
        # We generate a PDF on disk and read it
        pdf_filename = f"{report['type'].lower()}_report.pdf"
        pdf_path = generate_pdf_report(report['type'], report['summary'], report['data'].head(50), pdf_filename)
        
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        col_down1, col_down2 = nn_st.columns(2)
        with col_down1:
            nn_st.download_button(
                label="Download Report as CSV",
                data=csv_data,
                file_name=f"{report['type'].lower()}_report.csv",
                mime='text/csv',
                use_container_width=True
            )
        with col_down2:
            nn_st.download_button(
                label="Download Report as PDF (Official)",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime='application/pdf',
                use_container_width=True
            )

# --- Main App Execution ---
def main():
    # Session State Initialization
    if "authenticated" not in nn_st.session_state:
        nn_st.session_state.authenticated = False
        nn_st.session_state.user = None
        
    if not nn_st.session_state.authenticated:
        page_login()
    else:
        # Sidebar Navigation
        nn_st.sidebar.markdown(f"""
        <div style='padding: 10px; background-color: #3d141b; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #800020;'>
            <strong>User:</strong> {nn_st.session_state.user['username']}<br/>
            <strong>Role:</strong> {nn_st.session_state.user['role']}<br/>
        </div>
        """, unsafe_allow_html=True)
        
        pages = {
            "Dashboard": page_dashboard,
            "Regional Hospitals": page_hospitals,
            "Blood Inventory": page_inventory,
            "Demand Forecast": page_forecast,
            "Expiry Alerts": page_expiry,
            "Shortage Alerts": page_shortages,
            "Smart Allocation": page_allocation,
            "Analytics View": page_analytics,
            "Reports Center": page_reports
        }
        
        selected_page = nn_st.sidebar.radio("Navigate System", list(pages.keys()))
        
        # Sign Out Button
        if nn_st.sidebar.button("Sign Out", use_container_width=True):
            nn_st.session_state.authenticated = False
            nn_st.session_state.user = None
            nn_st.rerun()
            
        # Execute Page function
        pages[selected_page]()

if __name__ == "__main__":
    main()
