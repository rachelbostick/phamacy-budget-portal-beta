import streamlit as st
import pandas as pd

# --- REFERENCE DATA (The "Reference" Sheet) ---
drug_data = {
    "Vincristine": {"inflation": 0.04},
    "Dactinomycin": {"inflation": 0.065},
    "Cyclophosphamide": {"inflation": 0.03},
    "Irinotecan": {"inflation": 0.035}
}

age_data = {
    "Less than 6 months": {"n": 5, "w": 6.0, "bsa": 0.32},
    "6 months or greater": {"n": 130, "w": 28.0, "bsa": 0.98},
    "Less than 1 year": {"n": 11, "w": 8.0, "bsa": 0.40},
    "1 year to Less than 3 years": {"n": 30, "w": 12.5, "bsa": 0.55},
    "3 years or greater": {"n": 94, "w": 35.0, "bsa": 1.15}
}

# --- APP INTERFACE ---
st.set_page_config(page_title="RMS Budget Automator", layout="wide")
st.title("Pediatric Oncology Budget Automation Portal")
st.markdown("---")

# Layout: 3 Columns for Inputs
col1, col2, col3 = st.columns(3)

with col1:
    drug_name = st.selectbox("Select Drug", list(drug_data.keys()))
    age_group = st.selectbox("Select Age Group", list(age_data.keys()))

with col2:
    cost_vial = st.number_input("Cost per Vial ($)", min_value=0.0, value=100.0)
    vial_size = st.number_input("Vial Size (mg)", min_value=0.1, value=1.0)

with col3:
    dose_val = st.number_input("Dose per Admin (numeric)", value=1.5)
    calc_factor = st.radio("Calculation Factor", ["BSA", "Weight"])

# --- THE CALCULATIONS (Your Excel Formulas) ---
selected_age = age_data[age_group]
selected_drug = drug_data[drug_name]

# 1. Determine Weight or BSA based on selection
factor_val = selected_age['bsa'] if calc_factor == "BSA" else selected_age['w']

# 2. Calculated Dose (N in your sheet)
calc_dose = dose_val * factor_val

# 3. Vials Required (O in your sheet)
vials_req = -(-calc_dose // vial_size) # This is a Python "Ceiling" trick

# 4. Total Project Cost for Drug (S in your sheet)
# Note: In a real app, we'd add 'Doses per Patient' input here
annual_cost = (vials_req * cost_vial) * selected_age['n']

# 5. Inflation Projection (V in your sheet)
rate = selected_drug['inflation']
total_10yr = annual_cost * ((1 + rate)**10 - 1) / rate

# --- DISPLAY RESULTS ---
st.markdown("---")
res_col1, res_col2 = st.columns(2)

with res_col1:
    st.subheader("Current Year Estimates")
    st.write(f"**Patients in Cohort:** {selected_age['n']}")
    st.write(f"**Calculated Dose:** {calc_dose:.2f} mg")
    st.write(f"**Vials per Admin:** {vials_req}")

with res_col2:
    st.subheader("10-Year Financial Projection")
    st.metric("Inflation Adjusted Total", f"${total_10yr:,.2f}", f"{rate*100}% Inflation")

st.info("This tool automates the logic from the RMS Protocol Budget Spreadsheet.")
