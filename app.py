import streamlit as st
import pandas as pd

# 1. Initialize Session State
if 'wbs_df' not in st.session_state:
    st.session_state.wbs_df = pd.DataFrame(columns=['WBS_Code', 'WBS_Name'])

if 'master_rates' not in st.session_state:
    # In reality, this would be populated by a file uploader
    st.session_state.master_rates = pd.DataFrame({
        'Description': ['Concrete 32MPa', 'Formply', 'Carpenter', 'Excavator'],
        'Category': ['Material', 'Material', 'Labor', 'Plant'],
        'Unit': ['m3', 'm2', 'hr', 'hr'],
        'Rate': [280, 45, 85, 150]
    })

if 'detailed_items' not in st.session_state:
    st.session_state.detailed_items = pd.DataFrame(columns=[
        'Parent_WBS', 'Sub_Code', 'Description', 'Material', 'Unit', 'Qty', 'Rate', 'Total'
    ])

# 2. Define Page Functions
def page_1_wbs():
    st.header("1. High Level Work Breakdown Structure")
    st.write("Define your primary project areas.")
    
    # Using data_editor allows Excel-like interaction
    edited_df = st.data_editor(st.session_state.wbs_df, num_rows="dynamic")
    st.session_state.wbs_df = edited_df

def page_2_detail():
    st.header("2. Detailed WBS & Materials")
    
    if st.session_state.wbs_df.empty:
        st.warning("Please create a WBS on Page 1 first.")
        return
        
    # Select parent WBS
    wbs_list = st.session_state.wbs_df['WBS_Code'].tolist()
    selected_wbs = st.selectbox("Select WBS Area", wbs_list)
    
    # Filter master rates for dropdowns
    materials = st.session_state.master_rates[st.session_state.master_rates['Category'] == 'Material']['Description'].tolist()
    
    # ... logic for adding sub items and calculating costs goes here ...

# 3. Streamlit Page Navigation (Streamlit 1.36+ syntax)
pg = st.navigation([
    st.Page(page_1_wbs, title="1. High Level WBS"),
    st.Page(page_2_detail, title="2. Detail WBS"),
    # Add pages 3, 4, 5 here
])

pg.run()
