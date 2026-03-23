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
        if date_obj.weekday() == 6: return False
        if date_obj in self.holidays: return False
        return True

    def add_working_days(self, start_date, days):
        current_date = start_date
        while not self.is_working_day(current_date): current_date += datetime.timedelta(days=1)
        days_added = 0
        while days_added < days - 1:
            current_date += datetime.timedelta(days=1)
            if self.is_working_day(current_date): days_added += 1
        return current_date

    def subtract_working_days(self, from_date, days):
        current_date = from_date
        days_subtracted = 0
        while days_subtracted < days:
            current_date -= datetime.timedelta(days=1)
            if self.is_working_day(current_date): days_subtracted += 1
        return current_date

class ScheduleOfRates:
    def __init__(self, resource_rates, material_rates): 
        self.res_rates = resource_rates
        self.mat_rates = material_rates
        
    def get_res_rate(self, name): 
        return self.res_rates.get(name, 0.0)
        
    def get_mat_rate(self, name): 
        mat_data = self.mat_rates.get(name, {})
        if isinstance(mat_data, dict):
            return mat_data.get('rate', 0.0)
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
        if mat_name and mat_name != "None": 
            return self.quantity * sor.get_mat_rate(mat_name)
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
if 'temp_act_name' not in st.session_state: st.session_state.temp_act_name = ""
if 'temp_elements' not in st.session_state: st.session_state.temp_elements = []
if 'temp_resources' not in st.session_state: st.session_state.temp_resources = []

for key in ['ui_zone_name', 'ui_grid_ref', 'ui_act_name', 'ui_elem_name']:
    if key not in st.session_state: st.session_state[key] = ""
for key in ['ui_elem_qty', 'ui_res_hours_overall', 'ui_res_hrs_per']:
    if key not in st.session_state: st.session_state[key] = 0.0
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
        if existing_idx is not None:
            st.session_state.active_zone_idx = existing_idx
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
        if st.session_state.is_creating:
            st.session_state.temp_elements.append(new_el)
        elif st.session_state.active_act_idx is not None:
            st.session_state.zones[st.session_state.active_zone_idx].activities[st.session_state.active_act_idx].add_element(new_el)
        st.session_state.ui_elem_name = ""
        st.session_state.ui_elem_qty = 0.0

def cb_add_res():
    if st.session_state.resource_rates:
        name = st.session_state.ui_res_name
        is_lab = (st.session_state.ui_res_type == "Labour")
        
        if st.session_state.ui_alloc_method == "Overall Hours": total_hours = st.session_state.ui_res_hours_overall
        else: total_hours = st.session_state.ui_res_qty * st.session_state.ui_res_hrs_per
        if total_hours > 0:
            new_res = ResourceAllocation(name, total_hours, is_labour=is_lab)
            if st.session_state.is_creating:
                st.session_state.temp_resources.append(new_res)
            elif st.session_state.active_act_idx is not None:
                st.session_state.zones[st.session_state.active_zone_idx].activities[st.session_state.active_act_idx].add_resource(new_res)
            st.session_state.ui_res_hours_overall = 0.0
            st.session_state.ui_res_qty = 1
            st.session_state.ui_res_hrs_per = 0.0

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
    if st.session_state.active_act_idx == a_idx:
        st.session_state.active_act_idx = None
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

def generate_export_df():
    data = []
    for z in st.session_state.zones:
        for a in z.activities:
            for el in a.elements:
                data.append({"Location": z.name, "Grid": z.grid_reference, "Activity": a.name, "Item Name": el.name, "Type": "Quantity", "Amount": el.quantity, "Unit": el.unit})
            for res in a.resources:
                data.append({"Location": z.name, "Grid": z.grid_reference, "Activity": a.name, "Item Name": res.resource_name, "Type": "Resource", "Amount": res.hours, "Unit": "hrs"})
    return pd.DataFrame(data)

# ==========================================
# 3. USER INTERFACE (Tabs)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["1. Master Rates", "2. Project Scope", "3. Scheduling (WBS)", "4. Reporting & Export"])

# --- TAB 1: MASTER RATES ---
with tab1:
    st.subheader("Schedule of Rates")
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
            if isinstance(v, dict):
                mat_list.append({"Material Name": k, "Unit Rate ($)": v.get('rate', 0.0), "Unit": v.get('unit', 'ea')})
            else:
                mat_list.append({"Material Name": k, "Unit Rate ($)": float(v), "Unit": "ea"}) 
        
        mat_df = pd.DataFrame(mat_list)
        edited_mat = st.data_editor(
            mat_df, 
            num_rows="dynamic", 
            use_container_width=True, 
            key="mat_edit",
            column_config={
                "Unit": st.column_config.SelectboxColumn("Unit", options=["m2", "m3", "tonnes", "lm", "ea"])
            }
        )
        
        updated_mat = {}
        for _, row in edited_mat.iterrows():
            name = str(row["Material Name"]).strip()
            if name and name != "nan" and name != "None":
                updated_mat[name] = {
                    'rate': float(row["Unit Rate ($)"]) if pd.notna(row["Unit Rate ($)"]) else 0.0,
                    'unit': str(row["Unit"]) if pd.notna(row["Unit"]) else 'ea'
                }
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
                    st.radio("Allocation Method", ["Overall Hours", "Resource Multiplier"], horizontal=True, key="ui_alloc_method", label_visibility="collapsed")
                    r_col1, r_col2 = st.columns([2, 1])
                    r_col1.selectbox("Select Resource", list(st.session_state.resource_rates.keys()), key="ui_res_name")
                    r_col2.selectbox("Type", ["Labour", "Plant"], key="ui_res_type")
                    
                    rm_col1, rm_col2, rm_col3 = st.columns([3, 3, 2])
                    if st.session_state.ui_alloc_method == "Overall Hours":
                        rm_col1.number_input("Total Hours", key="ui_res_hours_overall", min_value=0.0)
                    else:
                        rm_col1.number_input("Workers/Plant (Qty)", key="ui_res_qty", min_value=1, step=1)
                        rm_col2.number_input("Hours per unit", key="ui_res_hrs_per", min_value=0.0)
                        
                    st.button("Add Resource", on_click=cb_add_res)

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
                    
                    if i != a_idx:
                        e_col2.button("✏️ Edit", key=f"edit_act_{i}", on_click=cb_edit_activity, args=(i,), use_container_width=True)
                    else:
                        e_col2.info("Editing")
                        
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
                
                if z_i != z_idx:
                    zc2.button("✏️ Edit Zone", key=f"edit_z_{z_i}", on_click=cb_edit_zone, args=(z_i,), use_container_width=True)
                else:
                    zc2.info("Active")
                    
                zc3.button("🗑️ Delete Zone", key=f"del_z_{z_i}", on_click=cb_delete_zone, args=(z_i,), type="secondary", use_container_width=True)

                zc1.write(f"**Total Activities:** {len(z.activities)}")
                if z.activities:
                    for a in z.activities:
                        zc1.write(f"- {a.name}")

# --- TAB 3: SCHEDULING (WBS) ---
with tab3:
    st.subheader("Work Breakdown Structure (WBS)")
    if not st.session_state.zones:
        st.warning("Please define and save at least one Zone in the 'Project Scope' tab first.")
    else:
        # 1. Select Zone & ID
        zone_options = {f"{z.name} (Grid: {z.grid_reference})": z for z in st.session_state.zones}
        selected_zone_key = st.selectbox("1. Add Zone to schedule", list(zone_options.keys()))
        selected_zone = zone_options[selected_zone_key]
        
        parent_count = sum(1 for t in st.session_state.tasks if getattr(t, 'is_parent', False))
        suggested_id = f"T{parent_count + 1:02d}"
        task_id = st.text_input("2. Nominate Parent Task ID", value=suggested_id)
        
        st.divider()
        st.write("### 3. Assign Durations & Start Dates")
        
        if not selected_zone.activities:
            st.info("There are no activities in this zone yet. Go to Project Scope to add some.")
        else:
            activity_schedules = []
            
            # Build list of previously scheduled global tasks to allow cross-zone linking
            global_preds = []
            for t in st.session_state.tasks:
                if not getattr(t, 'is_parent', False):
                    global_preds.append((t.task_id, t.activity.name if t.activity else "Task"))
            
            h1, h2, h3, h4 = st.columns([3, 1.5, 2, 2])
            h1.markdown("**Activity Name (Auto ID)**")
            h2.markdown("**Duration (Days)**")
            h3.markdown("**Start Basis**")
            h4.markdown("**Date / Lag (Days)**")
            
            current_zone_preds = []
            
            for idx, act in enumerate(selected_zone.activities):
                c1, c2, c3, c4 = st.columns([3, 1.5, 2, 2])
                child_id = f"{task_id}.{idx + 1}"
                
                c1.markdown(f"**{child_id}** | {act.name}")
                dur = c2.number_input("Days", min_value=1, value=5, key=f"dur_{selected_zone.name}_{idx}", label_visibility="collapsed")
                
                # Default to the immediate predecessor if it's not the first item
                pred_choices = ["Manual Date"] + [p[0] for p in global_preds] + [p[0] for p in current_zone_preds]
                default_idx = len(pred_choices) - 1 if idx > 0 else 0
                
                # Format the dropdown so it shows the ID + Name nicely
                def format_pred(p_id):
                    if p_id == "Manual Date": return "Manual Date"
                    name = next((p[1] for p in current_zone_preds if p[0] == p_id), None)
                    if not name:
                        name = next((p[1] for p in global_preds if p[0] == p_id), "Task")
                    short_name = (name[:15] + '..') if len(name) > 15 else name
                    return f"After {p_id} ({short_name})"
                
                basis = c3.selectbox("Start Basis", pred_choices, index=default_idx, format_func=format_pred, key=f"basis_{selected_zone.name}_{idx}", label_visibility="collapsed")
                
                start_d = None
                offset = 0
                
                if basis == "Manual Date":
                    start_d = c4.date_input("Start Date", datetime.date.today(), key=f"start_{selected_zone.name}_{idx}", label_visibility="collapsed")
                else:
                    offset = c4.number_input("Lag (+) / Overlap (-)", value=0, step=1, key=f"offset_{selected_zone.name}_{idx}", label_visibility="collapsed")
                    c4.caption("*- overlap, + delay*")
                
                activity_schedules.append({
                    "id": child_id,
                    "act": act,
                    "dur": dur,
                    "basis": basis,
                    "start": start_d,
                    "offset": offset
                })
                
                current_zone_preds.append((child_id, act.name))
                
            st.write("")
            if st.button("💾 Save Zone to Schedule", type="primary"):
                child_tasks = []
                
                # Dictionary to track calculated end dates as we generate the WBS
                end_dates = {t.task_id: t.end_date for t in st.session_state.tasks if not getattr(t, 'is_parent', False)}
                
                for sched in activity_schedules:
                    basis = sched["basis"]
                    
                    if basis == "Manual Date":
                        calc_start = sched["start"]
                    else:
                        pred_end = end_dates.get(basis, datetime.date.today())
                        
                        # Finish-to-Start default: Task starts 1 working day after predecessor finishes
                        base_start = st.session_state.calendar.add_working_days(pred_end, 1)
                        
                        if sched["offset"] > 0:
                            calc_start = st.session_state.calendar.add_working_days(base_start, sched["offset"])
                        elif sched["offset"] < 0:
                            calc_start = st.session_state.calendar.subtract_working_days(base_start, abs(sched["offset"]))
                        else:
                            calc_start = base_start
                            
                    ct = ProgrammeTask(sched["id"], selected_zone, sched["act"], sched["dur"], calc_start, st.session_state.calendar, is_parent=False)
                    child_tasks.append(ct)
                    end_dates[ct.task_id] = ct.end_date # Add to dictionary so subsequent tasks can link to it
                    
                if child_tasks:
                    parent_start = min(ct.start_date for ct in child_tasks)
                    parent_end = max(ct.end_date for ct in child_tasks)
                else:
                    parent_start = datetime.date.today()
                    parent_end = datetime.date.today()
                    
                parent_task = ProgrammeTask(task_id, selected_zone, None, 0, parent_start, st.session_state.calendar, is_parent=True)
                parent_task.start_date = parent_start
                parent_task.end_date = parent_end
                
                st.session_state.tasks.append(parent_task)
                st.session_state.tasks.extend(child_tasks)
                st.success(f"Scheduled Zone '{selected_zone.name}' with {len(child_tasks)} activities.")
                st.rerun()

        st.divider()
        st.write("### Current Schedule")
        
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
