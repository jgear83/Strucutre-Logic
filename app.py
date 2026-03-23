import streamlit as st
import datetime
import pandas as pd
import io
import plotly.express as px

# ==========================================
# 1. THE CORE ENGINE (Classes)
# ==========================================
class WorkingDayCalendar:
    def __init__(self, hours_per_week, holidays=None):
        self.hours_per_week = hours_per_week
        self.hours_per_day = hours_per_week / 6.0 
        self.holidays = set(holidays) if holidays else set()

    def is_working_day(self, date_obj):
        if date_obj.weekday() == 6: return False # 6 is Sunday
        if date_obj in self.holidays: return False
        return True

    def add_working_days(self, start_date, days):
        if days <= 0: return start_date
        current_date = start_date
        
        while not self.is_working_day(current_date):
            current_date += datetime.timedelta(days=1)
            
        days_added = 1
        while days_added < days:
            current_date += datetime.timedelta(days=1)
            if self.is_working_day(current_date): 
                days_added += 1
        return current_date

    def subtract_working_days(self, from_date, days):
        if days <= 0: return from_date
        current_date = from_date
        
        while not self.is_working_day(current_date):
            current_date -= datetime.timedelta(days=1)
            
        days_subtracted = 1
        while days_subtracted < days:
            current_date -= datetime.timedelta(days=1)
            if self.is_working_day(current_date): 
                days_subtracted += 1
        return current_date

    def shift_days(self, from_date, offset_days):
        """Shifts a date strictly forward or backward by X working days (for Lag/Overlap & FS Links)"""
        if offset_days == 0: return from_date
        current = from_date
        if offset_days > 0:
            added = 0
            while added < offset_days:
                current += datetime.timedelta(days=1)
                if self.is_working_day(current): added += 1
        else:
            subbed = 0
            while subbed < abs(offset_days):
                current -= datetime.timedelta(days=1)
                if self.is_working_day(current): subbed += 1
        return current

class ScheduleOfRates:
    def __init__(self, resource_rates, material_rates): 
        self.res_rates = resource_rates
        self.mat_rates = material_rates
        
    def get_res_rate(self, name): 
        return self.res_rates.get(name, 0.0)
        
    def get_mat_rate(self, name): 
        mat_data = self.mat_rates.get(name, {})
        if isinstance(mat_data, dict): return mat_data.get('rate', 0.0)
        return float(mat_data)
        
    def get_rate(self, name):
        if name in self.res_rates: return self.get_res_rate(name)
        return self.get_mat_rate(name)

class WorkElement:
    def __init__(self, name, quantity, unit, material_name=None):
        self.name = name
        self.quantity = quantity
        self.unit = unit
        self.material_name = material_name
        
    def get_cost(self, sor): 
        mat_name = getattr(self, 'material_name', None)
        if mat_name and mat_name != "None": return self.quantity * sor.get_mat_rate(mat_name)
        return 0.0

class ResourceAllocation:
    def __init__(self, resource_name, hours, is_labour=True):
        self.resource_name, self.hours, self.is_labour = resource_name, hours, is_labour
    def get_cost(self, sor): 
        cost_func = getattr(sor, 'get_res_rate', sor.get_rate)
        return self.hours * cost_func(self.resource_name)

class Activity:
    def __init__(self, name):
        self.name = name
        self.elements = []
        self.resources = []
    def add_element(self, element): self.elements.append(element)
    def add_resource(self, resource): self.resources.append(resource)

class Zone:
    def __init__(self, name, grid_reference):
        self.name, self.grid_reference = name, grid_reference
        self.activities = []
    def add_activity(self, activity): self.activities.append(activity)

class ProgrammeTask:
    def __init__(self, task_id, zone, activity, duration_days, start_date, calendar, is_parent=False):
        self.task_id = task_id
        self.zone = zone
        self.activity = activity
        self.duration_days = duration_days
        self.start_date = start_date
        self.is_parent = is_parent
        
        # Scheduling Meta-Data 
        self.link_type = "Manual Date"
        self.pred_id = None
        self.offset = 0
        self.manual_start = start_date
        
        if duration_days > 0:
            self.end_date = calendar.add_working_days(self.start_date, self.duration_days)
        else:
            self.end_date = start_date
        
    def get_task_cost(self, sor): 
        if self.is_parent or not self.activity: return 0.0 
        res_cost = 0.0
        for res in self.activity.resources:
            if hasattr(res, 'get_cost'): res_cost += res.get_cost(sor)
        mat_cost = 0.0
        for el in self.activity.elements:
            if hasattr(el, 'get_cost'): mat_cost += el.get_cost(sor)
        return res_cost + mat_cost
        
    def get_task_labour_hours(self): 
        if self.is_parent or not self.activity: return 0.0
        return sum(res.hours for res in self.activity.resources if res.is_labour)

# ==========================================
# 2. APP INITIALIZATION & MEMORY
# ==========================================
st.set_page_config(page_title="Pricing Engine", layout="wide")

if 'resource_rates' not in st.session_state: st.session_state.resource_rates = {} 
if 'material_rates' not in st.session_state: st.session_state.material_rates = {} 
if 'zones' not in st.session_state: st.session_state.zones = [] 
if 'tasks' not in st.session_state: st.session_state.tasks = [] 
if 'calendar' not in st.session_state: st.session_state.calendar = WorkingDayCalendar(hours_per_week=60)

if 'active_zone_idx' not in st.session_state: st.session_state.active_zone_idx = None
if 'active_act_idx' not in st.session_state: st.session_state.active_act_idx = None
if 'is_creating' not in st.session_state: st.session_state.is_creating = False

for key in ['temp_act_name', 'ui_zone_name', 'ui_grid_ref', 'ui_act_name', 'ui_elem_name']:
    if key not in st.session_state: st.session_state[key] = ""
for key in ['ui_elem_qty', 'ui_res_hours_overall']:
    if key not in st.session_state: st.session_state[key] = 0.0
    
if 'temp_elements' not in st.session_state: st.session_state.temp_elements = []
if 'temp_resources' not in st.session_state: st.session_state.temp_resources = []
if 'ui_res_qty' not in st.session_state: st.session_state.ui_res_qty = 1
if 'ui_alloc_method' not in st.session_state: st.session_state.ui_alloc_method = "Overall Hours"
if 'ui_res_type' not in st.session_state: st.session_state.ui_res_type = "Labour"

# ==========================================
# CALLBACK FUNCTIONS
# ==========================================
def cb_set_zone():
    z_name = st.session_state.ui_zone_name.strip()
    z_grid = st.session_state.ui_grid_ref.strip()
    if z_name:
        existing_idx = next((i for i, z in enumerate(st.session_state.zones) if z.name == z_name and z.grid_reference == z_grid), None)
        if existing_idx is not None: st.session_state.active_zone_idx = existing_idx
        else:
            st.session_state.zones.append(Zone(z_name, z_grid))
            st.session_state.active_zone_idx = len(st.session_state.zones) - 1
        st.session_state.active_act_idx = None 
        st.session_state.is_creating = False

def cb_update_zone():
    z_idx = st.session_state.active_zone_idx
    if z_idx is not None:
        z = st.session_state.zones[z_idx]
        z.name = st.session_state.ui_zone_name.strip()
        z.grid_reference = st.session_state.ui_grid_ref.strip()

def cb_start_create_activity():
    name = st.session_state.ui_act_name.strip()
    if name:
        st.session_state.is_creating = True
        st.session_state.temp_act_name = name
        st.session_state.temp_elements = []
        st.session_state.temp_resources = []
        st.session_state.ui_act_name = ""

def cb_add_qty():
    name = st.session_state.ui_elem_name
    qty = st.session_state.ui_elem_qty
    unit = st.session_state.ui_elem_unit
    mat_name = st.session_state.ui_elem_mat if st.session_state.ui_elem_mat != "None" else None
    if name and qty > 0:
        new_el = WorkElement(name, qty, unit, mat_name)
        if st.session_state.is_creating: st.session_state.temp_elements.append(new_el)
        elif st.session_state.active_act_idx is not None:
            st.session_state.zones[st.session_state.active_zone_idx].activities[st.session_state.active_act_idx].add_element(new_el)
        st.session_state.ui_elem_name = ""
        st.session_state.ui_elem_qty = 0.0

def cb_add_res():
    if st.session_state.resource_rates:
        name = st.session_state.ui_res_name
        is_lab = (st.session_state.ui_res_type == "Labour")
        total_hours = st.session_state.ui_res_hours_overall
        if total_hours > 0:
            new_res = ResourceAllocation(name, total_hours, is_labour=is_lab)
            if st.session_state.is_creating: st.session_state.temp_resources.append(new_res)
            elif st.session_state.active_act_idx is not None:
                st.session_state.zones[st.session_state.active_zone_idx].activities[st.session_state.active_act_idx].add_resource(new_res)
            st.session_state.ui_res_hours_overall = 0.0

def cb_del_qty(el_idx):
    if st.session_state.is_creating: st.session_state.temp_elements.pop(el_idx)
    else: st.session_state.zones[st.session_state.active_zone_idx].activities[st.session_state.active_act_idx].elements.pop(el_idx)

def cb_del_res(res_idx):
    if st.session_state.is_creating: st.session_state.temp_resources.pop(res_idx)
    else: st.session_state.zones[st.session_state.active_zone_idx].activities[st.session_state.active_act_idx].resources.pop(res_idx)

def cb_new_activity():
    st.session_state.active_act_idx = None
    st.session_state.is_creating = False
    st.session_state.ui_act_name = ""

def cb_edit_activity(a_idx):
    st.session_state.active_act_idx = a_idx
    st.session_state.is_creating = False

def cb_delete_activity(a_idx):
    z_idx = st.session_state.active_zone_idx
    st.session_state.zones[z_idx].activities.pop(a_idx)
    if st.session_state.active_act_idx == a_idx: st.session_state.active_act_idx = None
    elif st.session_state.active_act_idx is not None and st.session_state.active_act_idx > a_idx:
        st.session_state.active_act_idx -= 1

def cb_complete_activity():
    z_idx = st.session_state.active_zone_idx
    if st.session_state.is_creating:
        new_act = Activity(st.session_state.temp_act_name)
        for el in st.session_state.temp_elements: new_act.add_element(el)
        for res in st.session_state.temp_resources: new_act.add_resource(res)
        st.session_state.zones[z_idx].add_activity(new_act)
        st.session_state.is_creating = False
        st.session_state.temp_act_name = ""
        st.session_state.temp_elements = []
        st.session_state.temp_resources = []
    elif st.session_state.active_act_idx is not None:
        st.session_state.active_act_idx = None

def cb_new_zone():
    st.session_state.active_zone_idx = None
    st.session_state.active_act_idx = None
    st.session_state.is_creating = False
    st.session_state.ui_zone_name = ""
    st.session_state.ui_grid_ref = ""
    st.session_state.ui_act_name = ""

def cb_complete_zone():
    st.session_state.active_zone_idx = None
    st.session_state.active_act_idx = None
    st.session_state.is_creating = False
    st.session_state.ui_zone_name = ""
    st.session_state.ui_grid_ref = ""
    st.session_state.ui_act_name = ""

def cb_edit_zone(z_idx):
    st.session_state.active_zone_idx = z_idx
    st.session_state.active_act_idx = None
    st.session_state.is_creating = False
    z = st.session_state.zones[z_idx]
    st.session_state.ui_zone_name = z.name
    st.session_state.ui_grid_ref = z.grid_reference

def cb_delete_zone(z_idx):
    st.session_state.zones.pop(z_idx)
    if st.session_state.active_zone_idx == z_idx:
        st.session_state.active_zone_idx = None
        st.session_state.active_act_idx = None
        st.session_state.is_creating = False
        st.session_state.ui_zone_name = ""
        st.session_state.ui_grid_ref = ""
    elif st.session_state.active_zone_idx is not None and st.session_state.active_zone_idx > z_idx:
        st.session_state.active_zone_idx -= 1

# --- WBS SCHEDULING ENGINE ---
def cb_add_zone_to_wbs():
    zone_key = st.session_state.ui_schedule_zone
    task_id = st.session_state.ui_schedule_id
    zone = next((z for z in st.session_state.zones if f"{z.name} (Grid: {z.grid_reference})" == zone_key), None)
    if not zone: return
    
    current_start = datetime.date.today()
    child_tasks = []
    
    last_task_id = None
    for t in reversed(st.session_state.tasks):
        if not getattr(t, 'is_parent', False):
            last_task_id = t.task_id
            break
            
    for idx, act in enumerate(zone.activities):
        child_id = f"{task_id}.{idx + 1}"
        ct = ProgrammeTask(child_id, zone, act, 5, current_start, st.session_state.calendar, is_parent=False)
        
        # Smart Default Links
        if idx == 0:
            if last_task_id:
                ct.link_type = "Finish-to-Start (FS)"
                ct.pred_id = last_task_id
            else:
                ct.link_type = "Manual Date"
                ct.pred_id = None
        else:
            ct.link_type = "Finish-to-Start (FS)"
            ct.pred_id = f"{task_id}.{idx}"
            
        child_tasks.append(ct)
        
    pt = ProgrammeTask(task_id, zone, None, 0, current_start, st.session_state.calendar, is_parent=True)
    st.session_state.tasks.append(pt)
    st.session_state.tasks.extend(child_tasks)
    cb_update_schedule() 

def cb_update_schedule():
    end_dates = {}
    start_dates = {}
    cal = st.session_state.calendar
    
    for t in st.session_state.tasks:
        if getattr(t, 'is_parent', False): continue
        
        # Read from dynamic form with getattr safety nets for old cache data
        t.duration_days = st.session_state.get(f"dur_{t.task_id}", t.duration_days)
        t.link_type = st.session_state.get(f"link_{t.task_id}", getattr(t, 'link_type', 'Manual Date'))
        t.pred_id = st.session_state.get(f"pred_{t.task_id}", getattr(t, 'pred_id', None))
        t.offset = st.session_state.get(f"off_{t.task_id}", getattr(t, 'offset', 0))
        t.manual_start = st.session_state.get(f"start_{t.task_id}", getattr(t, 'manual_start', t.start_date))
        
        if t.link_type == "Manual Date":
            base = t.manual_start
            while not cal.is_working_day(base): base += datetime.timedelta(days=1)
            t.start_date = base
            t.end_date = cal.add_working_days(t.start_date, t.duration_days)
        else:
            if t.link_type == "Finish-to-Start (FS)":
                p_end = end_dates.get(t.pred_id, datetime.date.today())
                # FS Starts 1 working day strictly AFTER predecessor finishes
                base_s = cal.shift_days(p_end, 1) 
                t.start_date = cal.shift_days(base_s, t.offset)
                t.end_date = cal.add_working_days(t.start_date, t.duration_days)
                
            elif t.link_type == "Start-to-Start (SS)":
                p_start = start_dates.get(t.pred_id, datetime.date.today())
                # SS Starts on EXACT same working day as predecessor starts
                t.start_date = cal.shift_days(p_start, t.offset)
                t.end_date = cal.add_working_days(t.start_date, t.duration_days)
                
            elif t.link_type == "Finish-to-Finish (FF)":
                p_end = end_dates.get(t.pred_id, datetime.date.today())
                # FF Finishes on EXACT same working day as predecessor finishes
                t.end_date = cal.shift_days(p_end, t.offset)
                t.start_date = cal.subtract_working_days(t.end_date, t.duration_days)
                
        start_dates[t.task_id] = t.start_date
        end_dates[t.task_id] = t.end_date
        
    for t in st.session_state.tasks:
        if getattr(t, 'is_parent', False):
            children = [ct for ct in st.session_state.tasks if not getattr(ct, 'is_parent', False) and ct.task_id.startswith(f"{t.task_id}.")]
            if children:
                t.start_date = min(c.start_date for c in children)
                t.end_date = max(c.end_date for c in children)

# ==========================================
# 3. USER INTERFACE (Tabs)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["1. Setup & Rates", "2. Project Scope", "3. Scheduling (WBS)", "4. Reporting & Export"])

# --- TAB 1: MASTER RATES & SETUP ---
with tab1:
    st.subheader("📅 Project Calendar Configuration")
    st.write("Upload an Excel file containing non-working dates (e.g., Holidays, RDOs) in **Column C**.")
    
    uploaded_file = st.file_uploader("Upload Calendar (.xlsx or .xls)", type=['xlsx', 'xls'])
    if uploaded_file is not None:
        try:
            df_cal = pd.read_excel(uploaded_file, usecols=[2], header=None)
            holidays = set()
            for val in df_cal.iloc[:, 0].dropna():
                if isinstance(val, (datetime.datetime, pd.Timestamp)): holidays.add(val.date())
            st.session_state.calendar.holidays = holidays
            st.success(f"Successfully loaded {len(holidays)} non-working dates! Sundays are automatically excluded.")
        except Exception as e:
            st.error(f"Error reading file. Ensure your dates are in Column C. (Error: {e})")
    
    st.divider()
    st.subheader("💲 Schedule of Rates")
    rt_col1, rt_col2 = st.columns(2)
    
    with rt_col1:
        st.markdown("### 👷 Resource Rates (Labour/Plant)")
        with st.form("add_res_rate_form", clear_on_submit=True):
            r_name = st.text_input("Quick Add: Resource Name")
            r_rate = st.number_input("Quick Add: Hourly Rate ($)", min_value=0.0, step=1.0)
            if st.form_submit_button("Add Resource") and r_name:
                st.session_state.resource_rates[r_name] = r_rate
                st.rerun()
                
        st.info("💡 **Tip:** Click directly on any cell in the table below to **edit the rate**, or select a row and press `Delete` to remove it.")
        res_df = pd.DataFrame(list(st.session_state.resource_rates.items()), columns=["Resource Name", "Rate ($/hr)"])
        edited_res = st.data_editor(res_df, num_rows="dynamic", use_container_width=True, key="res_edit")
        
        updated_res = {}
        for _, row in edited_res.iterrows():
            name = str(row["Resource Name"]).strip()
            if name and name != "nan" and name != "None":
                updated_res[name] = float(row["Rate ($/hr)"]) if pd.notna(row["Rate ($/hr)"]) else 0.0
        st.session_state.resource_rates = updated_res
            
    with rt_col2:
        st.markdown("### 🧱 Material Rates")
        with st.form("add_mat_rate_form", clear_on_submit=True):
            m_name = st.text_input("Quick Add: Material Name")
            c1, c2 = st.columns(2)
            m_rate = c1.number_input("Unit Rate ($)", min_value=0.0, step=1.0)
            m_unit = c2.selectbox("Unit", ["m2", "m3", "tonnes", "lm", "ea"])
            if st.form_submit_button("Add Material") and m_name:
                st.session_state.material_rates[m_name] = {'rate': m_rate, 'unit': m_unit}
                st.rerun()
                
        st.info("💡 **Tip:** Click directly on any cell in the table below to **edit the rate**, or select a row and press `Delete` to remove it.")
        mat_list = []
        for k, v in st.session_state.material_rates.items():
            if isinstance(v, dict): mat_list.append({"Material Name": k, "Unit Rate ($)": v.get('rate', 0.0), "Unit": v.get('unit', 'ea')})
            else: mat_list.append({"Material Name": k, "Unit Rate ($)": float(v), "Unit": "ea"}) 
        
        mat_df = pd.DataFrame(mat_list)
        edited_mat = st.data_editor(mat_df, num_rows="dynamic", use_container_width=True, key="mat_edit", column_config={"Unit": st.column_config.SelectboxColumn("Unit", options=["m2", "m3", "tonnes", "lm", "ea"])})
        
        updated_mat = {}
        for _, row in edited_mat.iterrows():
            name = str(row["Material Name"]).strip()
            if name and name != "nan" and name != "None":
                updated_mat[name] = {'rate': float(row["Unit Rate ($)"]) if pd.notna(row["Unit Rate ($)"]) else 0.0, 'unit': str(row["Unit"]) if pd.notna(row["Unit"]) else 'ea'}
        st.session_state.material_rates = updated_mat

# --- TAB 2: PROJECT SCOPE ---
with tab2:
    z_idx = st.session_state.active_zone_idx
    a_idx = st.session_state.active_act_idx
    is_creating = st.session_state.is_creating

    st.subheader("1. Work Zone")
    if z_idx is None:
        st.info("Set a Work Zone to begin adding activities.")
        l_col1, l_col2, l_col3 = st.columns([2, 2, 1])
        l_col1.text_input("Zone Name", key="ui_zone_name", placeholder="e.g., Top Tower Level")
        l_col2.text_input("Grid Reference", key="ui_grid_ref", placeholder="e.g., A1-C4")
        l_col3.write("") 
        l_col3.button("Add Zone", on_click=cb_set_zone, type="primary", use_container_width=True)
    else:
        active_zone = st.session_state.zones[z_idx]
        st.success(f"📍 **Active Work Zone:** {active_zone.name} (Grid: {active_zone.grid_reference})")
        
        if not is_creating and a_idx is None:
            l_col1, l_col2, l_col3 = st.columns([2, 2, 1])
            l_col1.text_input("Edit Zone Name", key="ui_zone_name")
            l_col2.text_input("Edit Grid Ref", key="ui_grid_ref")
            l_col3.write("") 
            l_col3.button("Update Zone", on_click=cb_update_zone, type="secondary", use_container_width=True)
    
    st.divider()

    if z_idx is not None:
        st.subheader("2. Activity Details")
        
        if not is_creating and a_idx is None:
            c_col1, c_col2 = st.columns([4, 1])
            c_col1.text_input("Activity Name", key="ui_act_name", placeholder="e.g., Bulk Excavation")
            c_col2.write("")
            c_col2.button("Create Activity", on_click=cb_start_create_activity, type="primary", use_container_width=True)
        
        else:
            if is_creating:
                st.markdown(f"#### 🏗️ Creating Activity: **{st.session_state.temp_act_name}**")
                elements_source = st.session_state.temp_elements
                resources_source = st.session_state.temp_resources
            else:
                active_act = st.session_state.zones[z_idx].activities[a_idx]
                st.markdown(f"#### 🏗️ Editing Activity: **{active_act.name}**")
                elements_source = active_act.elements
                resources_source = active_act.resources
            
            with st.container(border=True):
                # ----------------- QUANTITIES -----------------
                st.write("**Nominate Quantities**")
                q_col1, q_col2, q_col3, q_col4, q_col5 = st.columns([2.5, 1, 1, 1.5, 2])
                q_col1.text_input("Work Element", key="ui_elem_name", placeholder="e.g., Formwork", label_visibility="collapsed")
                q_col2.number_input("Quantity", key="ui_elem_qty", min_value=0.0, label_visibility="collapsed")
                q_col3.selectbox("Unit", ["m2", "m3", "tonnes", "lm", "ea"], key="ui_elem_unit", label_visibility="collapsed")
                mat_options = ["None"] + list(st.session_state.material_rates.keys())
                q_col4.selectbox("Link Material Rate", mat_options, key="ui_elem_mat", label_visibility="collapsed")
                q_col5.button("Add Quantity", on_click=cb_add_qty, use_container_width=True)

                if elements_source:
                    for el_i, el in enumerate(elements_source):
                        c1, c2 = st.columns([9, 1])
                        mat_name = getattr(el, 'material_name', None)
                        mat_str = f" [Linked: {mat_name}]" if mat_name and mat_name != "None" else ""
                        c1.markdown(f"&nbsp;&nbsp;&nbsp;**{el_i+1}.** {el.quantity:,.2f} {el.unit} of **{el.name}**{mat_str}")
                        c2.button("🗑️", key=f"del_q_live_{el_i}", on_click=cb_del_qty, args=(el_i,))

                st.divider()
                
                # ----------------- RESOURCES -----------------
                st.write("**Assign Resources**")
                if not st.session_state.resource_rates:
                    st.warning("Go to Tab 1 to add Resource Rates first.")
                else:
                    r_col1, r_col2, r_col3, r_col4 = st.columns([2.5, 1.5, 1.5, 2])
                    r_col1.selectbox("Select Resource", list(st.session_state.resource_rates.keys()), key="ui_res_name")
                    r_col2.selectbox("Type", ["Labour", "Plant"], key="ui_res_type")
                    r_col3.number_input("Total Hours", min_value=0.0, key="ui_res_hours_overall")
                    r_col4.write("")
                    r_col4.button("Add Resource", on_click=cb_add_res, use_container_width=True)

                if resources_source:
                    for res_i, res in enumerate(resources_source):
                        c1, c2 = st.columns([9, 1])
                        c1.markdown(f"&nbsp;&nbsp;&nbsp;**{res_i+1}.** {res.hours:,.2f} hrs of **{res.resource_name}**")
                        c2.button("🗑️", key=f"del_r_live_{res_i}", on_click=cb_del_res, args=(res_i,))
            
            st.write("")
            st.button("✅ Complete Activity", on_click=cb_complete_activity, type="primary", use_container_width=True)

        st.divider()

        st.subheader("📋 Activity Summary")
        active_zone = st.session_state.zones[z_idx]
        
        if not active_zone.activities:
            st.caption("No activities saved to this zone yet.")
        else:
            for i, act in enumerate(active_zone.activities):
                with st.expander(f"{'🔵 ' if i == a_idx else ''}{act.name}", expanded=True):
                    e_col1, e_col2, e_col3 = st.columns([7, 1.5, 1.5])
                    
                    if i != a_idx: e_col2.button("✏️ Edit", key=f"edit_act_{i}", on_click=cb_edit_activity, args=(i,), use_container_width=True)
                    else: e_col2.info("Editing")
                    e_col3.button("🗑️ Delete", key=f"del_act_{i}", on_click=cb_delete_activity, args=(i,), type="secondary", use_container_width=True)

                    if act.elements:
                        e_col1.write("**Quantities:**")
                        for el_i, el in enumerate(act.elements):
                            mat_name = getattr(el, 'material_name', None)
                            mat_str = f" [Linked: {mat_name}]" if mat_name and mat_name != "None" else ""
                            e_col1.write(f"&nbsp;&nbsp;**{el_i+1}.** {el.quantity:,.2f} {el.unit} of {el.name}{mat_str}")
                    
                    if act.resources:
                        e_col1.write("**Resources:**")
                        for res_i, res in enumerate(act.resources):
                            e_col1.write(f"&nbsp;&nbsp;**{res_i+1}.** {res.hours:,.2f} hrs of {res.resource_name}")

        st.write("")
        st.button("➕ Add Activity", on_click=cb_new_activity, use_container_width=True)
        st.divider()
        st.button("✅ Complete Zone", on_click=cb_complete_zone, type="primary", use_container_width=True)
        st.button("🌍 Add Zone", on_click=cb_new_zone, type="secondary", use_container_width=True)

    # -----------------------------------------
    # 3. ZONE SUMMARY
    # -----------------------------------------
    st.divider()
    st.subheader("🌍 Zone Summary")
    
    if not st.session_state.zones:
        st.caption("No zones created yet.")
    else:
        for z_i, z in enumerate(st.session_state.zones):
            with st.expander(f"{'📍 ' if z_i == z_idx else ''}{z.name} | Grid: {z.grid_reference}"):
                zc1, zc2, zc3 = st.columns([7, 1.5, 1.5])
                
                if z_i != z_idx: zc2.button("✏️ Edit Zone", key=f"edit_z_{z_i}", on_click=cb_edit_zone, args=(z_i,), use_container_width=True)
                else: zc2.info("Active")
                    
                zc3.button("🗑️ Delete Zone", key=f"del_z_{z_i}", on_click=cb_delete_zone, args=(z_i,), type="secondary", use_container_width=True)
                zc1.write(f"**Total Activities:** {len(z.activities)}")
                if z.activities:
                    for a in z.activities: zc1.write(f"- {a.name}")

# --- TAB 3: SCHEDULING (WBS) ---
with tab3:
    st.subheader("1. Work Breakdown Structure")
    
    if not st.session_state.zones:
        st.warning("Please define and save at least one Zone in the 'Project Scope' tab first.")
    else:
        zone_options = {f"{z.name} (Grid: {z.grid_reference})": z for z in st.session_state.zones}
        
        l_col1, l_col2, l_col3 = st.columns([3, 1, 1])
        l_col1.selectbox("Select Zone", list(zone_options.keys()), key="ui_schedule_zone")
        
        parent_count = sum(1 for t in st.session_state.tasks if getattr(t, 'is_parent', False))
        suggested_id = f"T{parent_count + 1:02d}"
        l_col2.text_input("Parent Task ID", value=suggested_id, key="ui_schedule_id")
        
        l_col3.write("")
        l_col3.button("Add Zone to WBS", on_click=cb_add_zone_to_wbs, type="primary", use_container_width=True)
        
        st.divider()
        st.subheader("2. Assign Dependencies")
        st.write("Edit durations, link types, and offset dates for all scheduled activities. Changes update instantly, or click **Update Schedule** to force a refresh.")
        
        if not st.session_state.tasks:
            st.info("Add a Zone to the WBS above to begin scheduling.")
        else:
            pred_opts = [t.task_id for t in st.session_state.tasks if not getattr(t, 'is_parent', False)]
            
            h1, h2, h3, h4, h5, h6 = st.columns([1.5, 1, 1.5, 1.5, 1, 1.2])
            h1.markdown("**Activity (ID)**")
            h2.markdown("**Duration**")
            h3.markdown("**Link Type**")
            h4.markdown("**Predecessor**")
            h5.markdown("**Lag / Overlap**")
            h6.markdown("**Manual Date**")
            
            for t in st.session_state.tasks:
                if getattr(t, 'is_parent', False):
                    st.markdown(f"#### 📍 {t.task_id} | {t.zone.name}")
                else:
                    c1, c2, c3, c4, c5, c6 = st.columns([1.5, 1, 1.5, 1.5, 1, 1.2])
                    c1.write(f"└ **{t.task_id}** {t.activity.name}")
                    
                    c2.number_input("Duration", min_value=1, value=t.duration_days, key=f"dur_{t.task_id}", label_visibility="collapsed")
                    
                    link_opts = ["Manual Date", "Finish-to-Start (FS)", "Start-to-Start (SS)", "Finish-to-Finish (FF)"]
                    
                    # Fetch link type from memory, default to safe fallback for old tasks
                    t_link = st.session_state.get(f"link_{t.task_id}", getattr(t, 'link_type', 'Manual Date'))
                    link_idx = link_opts.index(t_link) if t_link in link_opts else 0
                    
                    # The selectbox will instantly update session_state and rerun the app when changed
                    c3.selectbox("Link Type", link_opts, index=link_idx, key=f"link_{t.task_id}", label_visibility="collapsed")
                    
                    # Greying out logic
                    is_manual = (t_link == "Manual Date")
                    
                    t_pred = getattr(t, 'pred_id', None)
                    def_pred_idx = pred_opts.index(t_pred) if t_pred in pred_opts else 0
                    c4.selectbox("Predecessor", pred_opts, index=def_pred_idx, key=f"pred_{t.task_id}", label_visibility="collapsed", disabled=is_manual)
                    
                    t_off = getattr(t, 'offset', 0)
                    c5.number_input("Lag", value=t_off, step=1, key=f"off_{t.task_id}", label_visibility="collapsed", disabled=is_manual)
                    
                    t_manual = getattr(t, 'manual_start', t.start_date)
                    c6.date_input("Start", t_manual, key=f"start_{t.task_id}", label_visibility="collapsed", disabled=not is_manual)
                    
            st.write("")
            st.button("✅ Update Schedule", on_click=cb_update_schedule, type="primary", use_container_width=True)

        st.divider()
        st.write("### 3. Current Schedule")
        
        if st.session_state.tasks:
            # -----------------------------------------
            # DATA FRAME TABLE VIEW
            # -----------------------------------------
            sched_list = []
            for t in st.session_state.tasks:
                start_str = t.start_date.strftime('%d/%m/%Y')
                end_str = t.end_date.strftime('%d/%m/%Y')
                
                if getattr(t, 'is_parent', False):
                    sched_list.append({
                        "Zone / Activity": f"{t.task_id} | {t.zone.name} (Zone Summary)",
                        "Duration (Days)": "-",
                        "Start Date": start_str,
                        "End Date": end_str
                    })
                else:
                    sched_list.append({
                        "Zone / Activity": f"    └ {t.task_id} | {t.activity.name if t.activity else ''}",
                        "Duration (Days)": str(t.duration_days),
                        "Start Date": start_str,
                        "End Date": end_str
                    })
            
            st.dataframe(pd.DataFrame(sched_list), hide_index=True, use_container_width=True)
            
            # -----------------------------------------
            # TASK DELETION & MANAGEMENT
            # -----------------------------------------
            st.write("#### Manage Schedule")
            del_c1, del_c2, del_c3 = st.columns([2, 1, 1])
            
            task_options = {f"{t.task_id} - {t.zone.name if getattr(t, 'is_parent', False) else t.activity.name}": t.task_id for t in st.session_state.tasks}
            task_to_del_key = del_c1.selectbox("Select Task to Remove", list(task_options.keys()), label_visibility="collapsed")
            
            if del_c2.button("🗑️ Remove Task", use_container_width=True):
                t_del_id = task_options[task_to_del_key]
                t_del = next((t for t in st.session_state.tasks if t.task_id == t_del_id), None)
                
                if t_del:
                    if getattr(t_del, 'is_parent', False):
                        st.session_state.tasks = [task for task in st.session_state.tasks if not (task.task_id == t_del.task_id or str(task.task_id).startswith(f"{t_del.task_id}."))]
                    else:
                        st.session_state.tasks = [task for task in st.session_state.tasks if task.task_id != t_del.task_id]
                    st.rerun()
                    
            if del_c3.button("🗑️ Clear Schedule", type="secondary", use_container_width=True):
                st.session_state.tasks = []
                st.rerun()

            st.divider()
            
            # -----------------------------------------
            # PLOTLY GANTT CHART
            # -----------------------------------------
            st.write("### Project Gantt Chart")
            gantt_data = []
            for t in st.session_state.tasks:
                if not getattr(t, 'is_parent', False):
                    gantt_data.append({
                        "Task": f"{t.task_id} - {t.activity.name}",
                        "Start": t.start_date,
                        "Finish": t.end_date,
                        "Zone": t.zone.name
                    })
                    
            if gantt_data:
                df_gantt = pd.DataFrame(gantt_data)
                fig = px.timeline(df_gantt, x_start="Start", x_end="Finish", y="Task", color="Zone")
                fig.update_yaxes(autorange="reversed") 
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Add child activities to the schedule to generate the Gantt Chart.")
        else:
            st.info("No tasks currently scheduled.")

# --- TAB 4: REPORTING & EXPORT ---
with tab4:
    st.subheader("Reporting and Export")
    st.write("Review detailed estimates and download your project report CSVs.")
    
    if not st.session_state.zones:
        st.warning("No data available to report. Please build your scope in Tab 2 first.")
    else:
        boq_data = []
        res_data = []
        cost_data = []
        grand_total = 0.0
        
        sor = ScheduleOfRates(st.session_state.resource_rates, st.session_state.material_rates)
        
        for z in st.session_state.zones:
            for a in z.activities:
                act_mat_cost = 0.0
                act_res_cost = 0.0
                
                # 1. BOQ Data
                for el in a.elements:
                    mat_name = getattr(el, 'material_name', None)
                    mat_rate = sor.get_mat_rate(mat_name) if mat_name and mat_name != "None" else 0.0
                    cost = el.quantity * mat_rate
                    act_mat_cost += cost
                    
                    boq_data.append({
                        "Zone": z.name, "Activity": a.name, "Element": el.name,
                        "Quantity": el.quantity, "Unit": el.unit,
                        "Material Link": mat_name if mat_name and mat_name != "None" else "Unlinked",
                        "Rate ($)": mat_rate, "Total Cost ($)": cost
                    })
                
                # 2. Resource Data
                for res in a.resources:
                    res_rate = getattr(sor, 'get_res_rate', sor.get_rate)(res.resource_name)
                    cost = res.hours * res_rate
                    act_res_cost += cost
                    
                    res_data.append({
                        "Zone": z.name, "Activity": a.name, "Resource": res.resource_name,
                        "Hours": res.hours, "Rate ($/hr)": res_rate, "Total Cost ($)": cost
                    })
                
                # 3. Cost Breakdown Data
                act_total = act_mat_cost + act_res_cost
                grand_total += act_total
                cost_data.append({
                    "Zone": z.name, "Activity": a.name,
                    "Material Cost ($)": act_mat_cost, "Resource Cost ($)": act_res_cost,
                    "Activity Total ($)": act_total
                })
        
        boq_df = pd.DataFrame(boq_data)
        res_df = pd.DataFrame(res_data)
        cost_df = pd.DataFrame(cost_data)
        
        with st.expander("1. Detailed Bill of Quantities", expanded=True):
            st.dataframe(boq_df, use_container_width=True, hide_index=True)
            
        with st.expander("2. Detailed Resource Schedule"):
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            
        with st.expander("3. Cost Breakdown (Activity / Zone)"):
            st.dataframe(cost_df, use_container_width=True, hide_index=True)
            st.metric("Total Project Cost", f"${grand_total:,.2f}")
        
        st.divider()
        st.write("### 📥 Download Reports")
        
        d_col1, d_col2, d_col3 = st.columns(3)
        
        if not boq_df.empty:
            d_col1.download_button(
                label="Download BOQ (CSV)",
                data=boq_df.to_csv(index=False).encode('utf-8'),
                file_name="Bill_of_Quantities.csv",
                mime="text/csv",
                use_container_width=True
            )
            
        if not res_df.empty:
            d_col2.download_button(
                label="Download Resources (CSV)",
                data=res_df.to_csv(index=False).encode('utf-8'),
                file_name="Resource_Schedule.csv",
                mime="text/csv",
                use_container_width=True
            )
            
        if not cost_df.empty:
            d_col3.download_button(
                label="Download Costs (CSV)",
                data=cost_df.to_csv(index=False).encode('utf-8'),
                file_name="Cost_Breakdown.csv",
                mime="text/csv",
                use_container_width=True
            )
