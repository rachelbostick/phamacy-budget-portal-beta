import streamlit as st
import google.generativeai as genai
import pandas as pd
import json

# 1. Setup AI (We will link the API key in Streamlit settings later)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- INPUT SECTION 1: AI EXTRACTION ---
st.header("1. Protocol AI Extraction")
uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])

if uploaded_file:
    # This is the "System Prompt" to get your Columns B-H
    prompt = """
    Analyze this protocol table. Extract every drug row. 
    Return a JSON list where each object has these keys exactly:
    "Risk Group", "Drug Name", "Age Group", "Dose per Admin", "Units", "Calc Factor", "Total Doses".
    Example: {"Risk Group": "Low-Risk", "Drug Name": "Vincristine", "Age Group": "<1 year", "Dose per Admin": 0.025, "Units": "mg/kg", "Calc Factor": "Weight", "Total Doses": 18}
    """
    
    with st.spinner("AI is reading the protocol..."):
        response = model.generate_content([prompt, uploaded_file])
        # We convert the AI text into a Python list (DataFrame)
        raw_data = json.loads(response.text.replace('```json', '').replace('```', ''))
        df = pd.DataFrame(raw_data)
        st.write("Extracted Data (Columns B-H):", df)

    # --- INPUT SECTION 2: MANUAL VARIABLES ---
    st.header("2. Manual Cost & Patient Variables")
    col1, col2 = st.columns(2)
    with col1:
        cost_vial = st.number_input("Cost per Vial ($) (Col J)", value=15.58)
        vial_size = st.number_input("Vial Size (mg) (Col K)", value=1.0)
    with col2:
        weight = st.number_input("Avg Patient Weight (kg) (Col L)", value=30.0)
        bsa = st.number_input("Avg Patient BSA (m2) (Col M)", value=1.0)

    # --- CALCULATION ENGINE (Columns N-V) ---
    # We apply your Excel logic to every row the AI found
    def run_calculations(row):
        # Col N: Calculated Dose
        dose = row['Dose per Admin'] * (weight if row['Calc Factor'] == "Weight" else bsa)
        # Col O: Vials Required
        vials = -(-dose // vial_size) # Ceiling math
        # Col P: Cost per Admin
        cost_admin = vials * cost_vial
        # Col Q: Total Cost per Patient
        total_pt = cost_admin * row['Total Doses']
        
        # Inflation Math (Col T & V)
        inflation = 0.04 # Default 4%
        total_10yr = total_pt * ((1 + inflation)**10 - 1) / inflation
        
        return pd.Series([dose, vials, cost_admin, total_pt, total_10yr])

    # Apply math to the table
    df[['Calc Dose', 'Vials', 'Cost/Admin', 'Total/Pt', '10-Year Total']] = df.apply(run_calculations, axis=1)

    # --- OUTPUT SECTION ---
    st.header("3. Financial Results (Cols P-V)")
    st.dataframe(df[['Drug Name', 'Cost/Admin', 'Total/Pt', '10-Year Total']])

    # Export to Excel (Matches your second screenshot)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Export Budget to Spreadsheet", data=csv, file_name="protocol_budget.csv", mime="text/csv")
