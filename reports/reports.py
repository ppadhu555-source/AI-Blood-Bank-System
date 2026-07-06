import os
import sys
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import text
from fpdf import FPDF

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import SessionLocal

# Ensure outputs folder exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

class PremiumReportPDF(FPDF):
    def __init__(self, title_text, subtitle_text):
        super().__init__()
        self.title_text = title_text
        self.subtitle_text = subtitle_text
        
    def header(self):
        # Premium Deep Red / Crimson theme
        self.set_fill_color(139, 0, 0) # Dark red
        self.rect(0, 0, 210, 40, 'F')
        
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 20)
        self.cell(0, 10, self.title_text, ln=True, align='L')
        self.set_font('Helvetica', 'I', 11)
        self.cell(0, 5, self.subtitle_text, ln=True, align='L')
        self.ln(12)
        
    def footer(self):
        self.set_y(-15)
        self.set_text_color(128, 128, 128)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f"Page {self.page_no()} | AI-Powered Blood Bank Allocation System | Confidential", align='C')

def generate_pdf_report(report_type, summary_data, table_df, filename):
    """
    Creates a styled PDF report with title, KPIs, and data table.
    """
    pdf = PremiumReportPDF(
        title_text=f"{report_type.upper()} REPORT",
        subtitle_text=f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    pdf.add_page()
    
    # 1. KPI Cards / Summary Info
    pdf.set_text_color(50, 50, 50)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, "Executive Summary", ln=True)
    pdf.line(10, 50, 200, 50)
    pdf.ln(2)
    
    pdf.set_font('Helvetica', '', 10)
    for key, val in summary_data.items():
        pdf.write(6, f"{key}: ")
        pdf.set_font('Helvetica', 'B', 10)
        pdf.write(6, f"{val}\n")
        pdf.set_font('Helvetica', '', 10)
        
    pdf.ln(8)
    
    # 2. Main Data Table
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, "Detailed Breakdown", ln=True)
    pdf.ln(2)
    
    # Set headers
    pdf.set_fill_color(200, 200, 200)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', 'B', 9)
    
    # Dynamically calculate cell widths based on column count
    num_cols = len(table_df.columns)
    col_width = 190 / num_cols
    
    for col in table_df.columns:
        # Capitalize and format header names
        hdr = str(col).replace("_", " ").title()
        pdf.cell(col_width, 8, hdr, border=1, align='C', fill=True)
    pdf.ln()
    
    # Rows
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(60, 60, 60)
    
    for idx, row in table_df.iterrows():
        # Zebra striping
        fill = (idx % 2 == 0)
        if fill:
            pdf.set_fill_color(245, 245, 245)
        else:
            pdf.set_fill_color(255, 255, 255)
            
        for col in table_df.columns:
            val = str(row[col])
            # Truncate string if too long for the column
            if len(val) > 22:
                val = val[:19] + "..."
            pdf.cell(col_width, 7, val, border=1, align='C', fill=True)
        pdf.ln()
        
    filepath = os.path.join(OUTPUTS_DIR, filename)
    pdf.output(filepath)
    return filepath

def get_report_data(report_type, start_date=None, end_date=None):
    """
    Queries relevant SQL tables depending on the report type and date ranges.
    Returns (summary_dict, detailed_dataframe).
    """
    if start_date is None:
        start_date = date(2026, 6, 5) # Default to past month
    if end_date is None:
        end_date = date(2026, 7, 5)
        
    session = SessionLocal()
    summary = {}
    df = pd.DataFrame()
    
    try:
        if report_type == "Demand":
            query = text("""
                SELECT r.request_date, h.name as hospital, c.name as component, 
                       r.blood_group, r.units_requested, r.status, r.priority
                FROM blood_requests r
                JOIN hospitals h ON r.hospital_id = h.hospital_id
                JOIN blood_components c ON r.component_id = c.component_id
                WHERE r.request_date >= :start_date AND r.request_date <= :end_date
                ORDER BY r.request_date DESC
            """)
            rows = session.execute(query, {"start_date": start_date, "end_date": end_date}).fetchall()
            if rows:
                df = pd.DataFrame([dict(r._mapping) for r in rows])
                summary = {
                    "Total Requests": len(df),
                    "Total Units Requested": int(df['units_requested'].sum()),
                    "Fulfilled Requests": len(df[df['status'] == 'Fulfilled']),
                    "Emergency Requests": len(df[df['priority'] == 'Emergency']),
                    "Average Request Size": f"{df['units_requested'].mean():.2f} units",
                    "Date Range": f"{start_date} to {end_date}"
                }
                
        elif report_type == "Expiry":
            query = text("""
                SELECT i.expiry_date, h.name as hospital, c.name as component, 
                       i.blood_group, i.units_available, i.status
                FROM blood_inventory i
                JOIN hospitals h ON i.hospital_id = h.hospital_id
                JOIN blood_components c ON i.component_id = c.component_id
                WHERE i.status IN ('Expired', 'Expiring') AND i.units_available > 0
                ORDER BY i.expiry_date ASC
            """)
            rows = session.execute(query).fetchall()
            if rows:
                df = pd.DataFrame([dict(r._mapping) for r in rows])
                # Ensure data type is datetime or string for comparison
                df['expiry_date_parsed'] = pd.to_datetime(df['expiry_date'])
                today = pd.Timestamp(2026, 7, 5)
                
                expired_count = df[df['expiry_date_parsed'] < today]['units_available'].sum()
                expiring_count = df[df['expiry_date_parsed'] >= today]['units_available'].sum()
                
                summary = {
                    "Active Expired Units": int(expired_count),
                    "Units Expiring Soon (<5 Days)": int(expiring_count),
                    "Hospitals Impacted": df['hospital'].nunique(),
                    "Expiry Check Date": "2026-07-05 (Simulation Anchor)"
                }
                df.drop(columns=['expiry_date_parsed'], inplace=True, errors='ignore')
                
        elif report_type == "Allocation":
            query = text("""
                SELECT a.transfer_date, sh.name as source_hospital, dh.name as dest_hospital,
                       c.name as component, a.blood_group, a.units_transferred, a.status
                FROM allocation_history a
                JOIN hospitals sh ON a.source_hospital_id = sh.hospital_id
                JOIN hospitals dh ON a.destination_hospital_id = dh.hospital_id
                JOIN blood_components c ON a.component_id = c.component_id
                WHERE a.transfer_date >= :start_date AND a.transfer_date <= :end_date
                ORDER BY a.transfer_date DESC
            """)
            rows = session.execute(query, {"start_date": start_date, "end_date": end_date}).fetchall()
            if rows:
                df = pd.DataFrame([dict(r._mapping) for r in rows])
                summary = {
                    "Total Allocations": len(df),
                    "Total Units Transferred": int(df['units_transferred'].sum()),
                    "Completed Transfers": len(df[df['status'] == 'Completed']),
                    "Active Sharing Partnerships": f"{df['source_hospital'].nunique()} source(s) -> {df['dest_hospital'].nunique()} destination(s)",
                    "Date Range": f"{start_date} to {end_date}"
                }
                
        elif report_type == "Emergency":
            query = text("""
                SELECT r.request_date, h.name as hospital, c.name as component, 
                       r.blood_group, r.units_requested, r.priority, r.event_type
                FROM blood_requests r
                JOIN hospitals h ON r.hospital_id = h.hospital_id
                JOIN blood_components c ON r.component_id = c.component_id
                WHERE r.priority = 'Emergency' AND r.request_date >= :start_date AND r.request_date <= :end_date
                ORDER BY r.request_date DESC
            """)
            rows = session.execute(query, {"start_date": start_date, "end_date": end_date}).fetchall()
            if rows:
                df = pd.DataFrame([dict(r._mapping) for r in rows])
                summary = {
                    "Total Emergency Requests": len(df),
                    "Total Units Requested": int(df['units_requested'].sum()),
                    "Average Reaction Size": f"{df['units_requested'].mean():.2f} units",
                    "Mass Casualty/Accident Flags": len(df[df['event_type'] != 'None']),
                    "Date Range": f"{start_date} to {end_date}"
                }
                
        # Fill in defaults if no records returned
        if df.empty:
            df = pd.DataFrame(columns=["Info"])
            df.loc[0] = ["No records found for the selected period."]
            summary = {"Status": "No data available"}
            
        return summary, df
    except Exception as e:
        logger.error(f"Error fetching report data: {e}")
        return {"Error": str(e)}, pd.DataFrame()
    finally:
        session.close()

if __name__ == "__main__":
    # Test generation
    s, d = get_report_data("Demand", date(2026, 6, 20), date(2026, 7, 5))
    path = generate_pdf_report("Demand", s, d.head(10), "test_demand_report.pdf")
    print(f"Generated test report at: {path}")
