import streamlit as st
import pandas as pd

# --- 1. SESSION STATE INITIALIZATION ---
# Initialize separate dataframes for each resource type
if 'mat_rates' not in st.session_state:
    st.session_state.mat_rates = pd.DataFrame()
if 'lab_rates' not in st.session_state:
    st.session_state.lab_rates = pd.DataFrame()
if 'plant_rates' not in st.session_state:
    st.session_state.plant_rates = pd.DataFrame()
if 'wbs_df' not in st.session_state:
    st.session_state.wbs_df = pd.DataFrame(columns=['WBS_Code', 'WBS_Name'])


# --- 2. THE UPLOAD HELPER FUNCTION ---
# We write this once, and use it for all four uploads below.
def process_upload(uploaded_file, expected_columns, state_key, success_name):
    """Reads the file, validates columns, and saves to session state."""
    try:
        # Handle both CSV and Excel
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        # Validate columns
        missing_cols = [col for col in expected_columns if col not in df.columns]
        
        if not missing_cols:
            # Clean data: drop empty rows based on the expected columns
            df = df.dropna(subset=expected_columns)
            
            # Save to the specific session state variable
            st.session_state[state_key] = df
            
            st.success(f"✅ {success_name} uploaded successfully! ({len(df)} items loaded)")
            with st.expander(f"Preview {success_name}"):
                st.dataframe(df, use_container_width=True)
        else:
            st.error(f"⚠️ Upload failed. Missing columns: {missing_cols}")
            st.info(f"Required headers exactly as written: {', '.join(expected_columns)}")
            
    except Exception as e:
        st.error(f"An error occurred reading the file: {e}")


# --- 3. PAGE 1: UPLOADS & SETUP ---
def page_1_uploads():
    st.header("Step 1: Project Setup & Uploads")
    st.write("Upload your project WBS and schedule of rates to begin estimating.")
    st.divider()

    # Create 4 clean tabs for the user interface
    tab1, tab2, tab3, tab4 = st.tabs(["🏗️ WBS", "🧱 Materials", "👷 Labour", "🚜 Plant & Equip"])

    # --- TAB 1: WBS UPLOAD ---
    with tab1:
        st.subheader("Upload Work Breakdown Structure")
        wbs_file = st.file_uploader("Upload WBS (CSV/Excel)", type=['csv', 'xlsx'], key="wbs_up")
        
        if wbs_file:
            process_upload(
                uploaded_file=wbs_file, 
                expected_columns=['WBS_Code', 'WBS_Name'], 
                state_key='wbs_df', 
                success_name="WBS Structure"
            )
            
        # Optional: Keep the manual entry option below the upload just in case
        with st.expander("Or Add WBS Manually"):
             with st.form("manual_wbs", clear_on_submit=True):
                 col1, col2 = st.columns([1, 3])
                 w_code = col1.text_input("WBS Code")
                 w_name = col2.text_input("WBS Name")
                 if st.form_submit_button("Add") and w_code and w_name:
                     new_row = pd.DataFrame([{'WBS_Code': w_code, 'WBS_Name': w_name}])
                     st.session_state.wbs_df = pd.concat([st.session_state.wbs_df, new_row], ignore_index=True).drop_duplicates(subset=['WBS_Code'])
                     st.success("Added!")

    # --- TAB 2: MATERIALS UPLOAD ---
    with tab2:
        st.subheader("Upload Material Rates")
        mat_file = st.file_uploader("Upload Materials (CSV/Excel)", type=['csv', 'xlsx'], key="mat_up")
        
        if mat_file:
            process_upload(
                uploaded_file=mat_file, 
                # Defined the structure typical for materials
                expected_columns=['Material_Code', 'Description', 'Unit', 'Unit_Rate'], 
                state_key='mat_rates', 
                success_name="Material Rates"
            )

    # --- TAB 3: LABOUR UPLOAD ---
    with tab3:
        st.subheader("Upload Labour Rates")
        lab_file = st.file_uploader("Upload Labour (CSV/Excel)", type=['csv', 'xlsx'], key="lab_up")
        
        if lab_file:
            process_upload(
                uploaded_file=lab_file, 
                # Defined the structure typical for trades/labour
                expected_columns=['Trade_Code', 'Role_Description', 'Hourly_Rate'], 
                state_key='lab_rates', 
                success_name="Labour Rates"
            )

    # --- TAB 4: PLANT UPLOAD ---
    with tab4:
        st.subheader("Upload Plant & Equipment Rates")
        plant_file = st.file_uploader("Upload Plant (CSV/Excel)", type=['csv', 'xlsx'], key="plant_up")
        
        if plant_file:
            process_upload(
                uploaded_file=plant_file, 
                # Defined the structure typical for machinery
                expected_columns=['Plant_Code', 'Equipment_Description', 'Hourly_Rate'], 
                state_key='plant_rates', 
                success_name="Plant Rates"
            )

# --- 4. NAVIGATION ROUTING ---
pg = st.navigation([
    st.Page(page_1_uploads, title="1. Setup & Uploads", icon="⚙️"),
    # st.Page(page_2_detail, title="2. Detail BOQ", icon="📋") # Ready for the next step
])

pg.run()
