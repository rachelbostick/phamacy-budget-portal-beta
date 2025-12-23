import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image  

# 1. Setup AI (We will link the API key in Streamlit settings later)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.title("Pediatric Oncology Protocol Budgeter")

# --- INPUT SECTION 1: AI EXTRACTION ---
st.header("1. Protocol AI Extraction")
uploaded_file = st.file_uploader("Upload Protocol Screenshot", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    # 1. Convert the Streamlit buffer into a PIL Image object
    img = Image.open(uploaded_file)
    
    # 2. Display the image in the app so you know it worked
    st.image(img, caption="Protocol Screenshot", width=400)

    with st.spinner("AI is reading the protocol..."):
        # 3. Pass the 'img' object to Gemini instead of 'uploaded_file'
        response = model.generate_content([prompt, img])
        
        # 4. Clean and parse the response
        try:
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            raw_data = json.loads(clean_json)
            df = pd.DataFrame(raw_data)
            
            # Show the "Extracted" data before doing math
            st.subheader("Extracted Protocol Details (Columns B-H)")
            st.dataframe(df)
            
        except Exception as e:
            st.error(f"AI extracted the data, but the format was messy: {e}")
            st.text("Raw AI Output:")
            st.write(response.text)

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
