import streamlit as st
import simpy
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import time

# ==========================================
# 1. SETUP & CONFIG
# ==========================================
st.set_page_config(page_title="KSL Logistics Simulation", layout="wide")

# --- 🎨 PRO LOGISTICS UI DESIGN ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600&display=swap');

    /* 1. Global Style & Font กระชับแบบ VS Code */
    html, body, [class*="css"], .stMarkdown, label {
        font-family: 'Kanit', sans-serif !important;
        font-size: 13.5px !important;
        color: #334155;
    }

    /* 2. Dashboard Header */
    .main-header {
        background: linear-gradient(90deg, #1E3A8A 0%, #3B82F6 100%);
        padding: 1rem 1.5rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 1.5rem;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    .main-header h1 { color: white !important; margin: 0; font-size: 24px !important; }
    .main-header p { margin: 5px 0 0 0; opacity: 0.8; font-size: 14px; }

    /* 3. Card Style สำหรับแต่ละศูนย์ */
    div[data-testid="column"] {
        background-color: #ffffff;
        border: 1px solid #E2E8F0;
        padding: 12px !important;
        border-radius: 10px;
    }

    /* 4. Highlight หัวข้อศูนย์ */
    h3 {
        font-size: 16px !important;
        font-weight: 600 !important;
        color: #1E3A8A !important;
        border-bottom: 2px solid #EFF6FF;
        padding-bottom: 5px;
        margin-bottom: 10px !important;
    }

    /* 5. ปรับแต่งปุ่ม Run */
    .stButton>button {
        background: #2563EB !important;
        color: white !important;
        border-radius: 6px !important;
        width: 100%;
        font-weight: 500 !important;
    }

    /* 6. ปรับขนาด Input ให้กะทัดรัด */
    .stNumberInput input {
        padding: 5px !important;
    }
    
    /* 7. สีกรอบแยกประเภทอ้อย */
    .fresh-label { color: #10B981; font-weight: 600; }
    .burnt-label { color: #EF4444; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>🚜 KSL Logistics Simulation</h1><p>ระบบจำลองและวางแผนการขนส่งอ้อยอัจฉริยะรูปแบบ Hub and Spoke ภายใต้โครงการเสริมสร้างความสามารถการดำเนินธุรกิจให้กับผู้ประกอบการภาคอุตสาหกรรมด้วยการบริหารจัดการโลจิสติกส์ที่มีประสิทธิภาพอย่างยั่งยืน ประจำปีงบประมาณ 2569 กองโลจิสติกส์ กรมส่งเสริมอุตสาหกรรม</p></div>', unsafe_allow_html=True)

# --- CONFIG & LISTS ---
yards_list = ["ศูนย์โนนสัง(Hub)", "ศูนย์โนนสว่าง", "ศูนย์ศรีบุญเรือง", "ศูนย์ข้องโป้", "ศูนย์ทรายทอง"]
hub_name = "ศูนย์โนนสัง(Hub)"
default_distances = {
    "ศูนย์โนนสัง(Hub)": 0.0, "ศูนย์โนนสว่าง": 58.0, "ศูนย์ศรีบุญเรือง": 37.0, "ศูนย์ข้องโป้": 25.0, "ศูนย์ทรายทอง": 39.0
}

# --- HELPERS ---
def get_stochastic_val(dist_type, params):
    try:
        if dist_type == "Constant": return params.get('val', 40)
        elif dist_type == "Normal": 
            return max(1, np.random.normal(params.get('mean', 40), params.get('std', 5)))
        elif dist_type == "Triangle": 
            return np.random.triangular(params.get('min', 30), params.get('mode', 40), params.get('max', 60))
    except: return 40
    return 40

def stochastic_input_ui(label, key_prefix, default_v):
    dist_type = st.selectbox(f"รูปแบบ {label}", ["Constant", "Normal", "Triangle"], key=f"{key_prefix}_type")
    params = {}
    if dist_type == "Constant":
        params['val'] = st.number_input(f"ค่าคงที่ ({label})", 1.0, 500.0, float(default_v), key=f"{key_prefix}_v")
    elif dist_type == "Normal":
        c1, c2 = st.columns(2)
        params['mean'] = c1.number_input(f"Mean ({label})", 1.0, 500.0, float(default_v), key=f"{key_prefix}_m")
        params['std'] = c2.number_input(f"Std Dev", 0.1, 100.0, 5.0, key=f"{key_prefix}_s")
    elif dist_type == "Triangle":
        c1, c2, c3 = st.columns(3)
        params['min'] = c1.number_input("Min", 1.0, 500.0, float(default_v*0.7), key=f"{key_prefix}_min")
        params['mode'] = c2.number_input("Mode", 1.0, 500.0, float(default_v), key=f"{key_prefix}_mod")
        params['max'] = c3.number_input("Max", 1.0, 500.0, float(default_v*1.5), key=f"{key_prefix}_max")
    return dist_type, params

# ==========================================
# 2. SIDEBAR
# ==========================================
with st.sidebar:
    st.header("⚙️ ตั้งค่าระบบเวลาเปิดปิด")
    yard_start = st.time_input("ลานเริ่มทำงาน", time(6, 0))
    yard_end = st.time_input("ลานปิดทำงาน", time(20, 0))
    fac_start = st.time_input("โรงงานเริ่มเปิดรับเท", time(8, 0))
    fac_end = st.time_input("โรงงานหยุดเทอ้อย", time(22, 0))
    
    st.divider()
    st.header("🏭 ตั้งค่าโรงงาน KSL-NP (ช่องเท)")
    col_f, col_b = st.columns(2)
    with col_f: n_slots_fresh = st.number_input("ช่องเทอ้อยสด", 0, 20, 3)
    with col_b: n_slots_burnt = st.number_input("ช่องเทอ้อยไฟไหม้", 0, 20, 1)
    
    st.subheader("🚛 คิวค้างหน้าโรงงาน")
    col_if1, col_if2 = st.columns(2)
    with col_if1: init_fac_fresh = st.number_input("หางหนักอ้อยสด (ใบ)", 0, 100, 0, key="init_fac_f")
    with col_if2: init_fac_burnt = st.number_input("หางหนักอ้อยไฟไหม้ (ใบ)", 0, 100, 0, key="init_fac_b")
        
    dist_hub_factory = st.number_input("ระยะทาง Hub -> โรงงาน (กม.)", 1, 200, 60)

    st.subheader("⏱️ ตั้งค่าเวลาในกระบวนการทำงาน")
    unld_dist, unld_p = stochastic_input_ui("เวลาในการเทต่อคันต่อช่อง", "unld", 100)
    hook_dist, hook_p = stochastic_input_ui("เวลาเกี่ยว/ถอดหางต่อคัน", "hook", 30)
    load_dist, load_p = stochastic_input_ui("เวลาคีบอ้อยต่อหาง", "load", 45)
    
    trailer_cap = st.number_input("ความจุต่อหาง (ตัน)", 10.0, 50.0, 29.0)

# Calculate simulation time
start_min = yard_start.hour * 60 + yard_start.minute
fac_open_min = (fac_start.hour * 60 + fac_start.minute) - start_min
fac_close_min = (fac_end.hour * 60 + fac_end.minute) - start_min
yard_close_min = (yard_end.hour * 60 + yard_end.minute) - start_min
sim_duration = max(fac_close_min, yard_close_min)

# ==========================================
# 3. MAIN UI - YARD CONFIG
# ==========================================
loc_params, fleet_config = {}, {}
cols = st.columns(len(yards_list))

for i, y_name in enumerate(yards_list):
    with cols[i]:
        st.subheader(y_name)
        dist_h = 0.0 if y_name == hub_name else st.number_input(f"ระยะทางจากลานไป Hub", 0.0, 200.0, default_distances[y_name], key=f"d_{y_name}")
        n_t = st.number_input("รถลาก (คัน)", 0, 50, 5 if i==0 else 2, key=f"nty_{y_name}")
        n_e = st.number_input("หางรวม (ใบ)", 1, 500, 6, key=f"ne_{y_name}")
        n_loaders = st.number_input("รถคีบ (คัน)", 1, 10, 1, key=f"nl_{y_name}")
        
        st.markdown("**หางหนักค้างลาน**")
        c1, c2 = st.columns(2)
        with c1: s_init_f = st.number_input("อ้อยสด (ใบ)", 0, 100, 0 if y_name == hub_name else 0, key=f"init_f_{y_name}")
        with c2: s_init_b = st.number_input("อ้อยไฟไหม้ (ใบ)", 0, 100, 0 if y_name == hub_name else 0, key=f"init_b_{y_name}")

        with st.expander("🚚 ความเร็ว"):
            s_type, s_p = stochastic_input_ui(f"Speed {y_name}", f"speed_{y_name}", 40)
            fleet_config[y_name] = {"n_t": n_t, "n_e": n_e, "n_loaders": n_loaders, "speed_type": s_type, "speed_params": s_p}
        
        with st.expander("📝 แผนอ้อย"):
            plan_f, plan_b = [], []
            h_labels = [f"{h:02d}:00" for h in range(yard_start.hour, yard_end.hour + 1)]
            for h in h_labels:
                cx1, cx2 = st.columns(2)
                with cx1: f_v = st.number_input(f"อ้อยสด {h}", 0.0, 2000.0, 0.0, key=f"f_{y_name}_{h}")
                with cx2: b_v = st.number_input(f"ไฟไหม้ {h}", 0.0, 2000.0, 0.0, key=f"b_{y_name}_{h}")
                plan_f.append(f_v); plan_b.append(b_v)
            loc_params[y_name] = {"fresh": plan_f, "burnt": plan_b, "dist": dist_h, "init_f": s_init_f, "init_b": s_init_b}

# Top metrics summarizing the plan
st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("📍 ลานทั้งหมด", "5 จุด", "1 Hub / 4 Spoke")
m2.metric("🚛 รถลากรวม", f"{sum(f['n_t'] for f in fleet_config.values())} คัน")
m3.metric("📦 หางรวม", f"{sum(f['n_e'] for f in fleet_config.values())} ใบ")
m4.metric("🏗️ รถคีบรวม", f"{sum(f['n_loaders'] for f in fleet_config.values())} คัน")

# ==========================================
# 4. SIMULATION ENGINE
# ==========================================
def run_ksl_simulation():
    env = simpy.Environment()
    slots_f = simpy.Resource(env, capacity=n_slots_fresh) if n_slots_fresh > 0 else None
    slots_b = simpy.Resource(env, capacity=n_slots_burnt) if n_slots_burnt > 0 else None
    hub_full_f, hub_full_b = simpy.Store(env), simpy.Store(env)
    loaders_res = {y: simpy.Resource(env, capacity=fleet_config[y]['n_loaders']) for y in yards_list}
    final_y = {y: {
        "empty": simpy.Store(env), "full_f": simpy.Store(env), "full_b": simpy.Store(env),
        "wait_f": simpy.Container(env, init=0, capacity=10**9), "wait_b": simpy.Container(env, init=0, capacity=10**9)
    } for y in yards_list}
    
    kpi = {"delivered_ton": {y: 0.0 for y in yards_list}, "history": [], "hourly_load": []}
    fac_q_monitor = {"สด": 0, "ไหม้": 0}
    t_util, l_util = {}, {}

    def add_util(tracker, key, duration):
        tracker[key] = tracker.get(key, 0.0) + duration

    # --- INITIALIZATION ---
    for y in yards_list:
        n_total = fleet_config[y]['n_e']
        if y == hub_name:
            n_e = max(0, n_total - (loc_params[y]['init_f'] + loc_params[y]['init_b'] + init_fac_fresh + init_fac_burnt))
            for i in range(loc_params[y]['init_f']): hub_full_f.put({"id": f"Hub-IF-{i}", "loc": hub_name, "start": env.now})
            for i in range(loc_params[y]['init_b']): hub_full_b.put({"id": f"Hub-IB-{i}", "loc": hub_name, "start": env.now})
        else:
            n_e = max(0, n_total - (loc_params[y]['init_f'] + loc_params[y]['init_b']))
            for i in range(loc_params[y]['init_f']): final_y[y]['full_f'].put({"id": f"{y}-IF-{i}", "loc": y, "start": env.now})
            for i in range(loc_params[y]['init_b']): final_y[y]['full_b'].put({"id": f"{y}-IB-{i}", "loc": y, "start": env.now})
        
        for j in range(n_e): final_y[y]['empty'].put({"id": f"{y}-E{j+1}", "loc": y, "start": env.now})

    def loader_worker(y_name):
        while env.now < yard_close_min:
            has_f = final_y[y_name]['wait_f'].level >= trailer_cap
            has_b = final_y[y_name]['wait_b'].level >= trailer_cap
            if (has_f or has_b) and len(final_y[y_name]['empty'].items) > 0:
                t_type = 'f' if has_f else 'b'
                with loaders_res[y_name].request() as req:
                    yield req
                    start_l = env.now
                    tail = yield final_y[y_name]['empty'].get()
                    yield env.timeout(get_stochastic_val(hook_dist, hook_p))
                    yield final_y[y_name][f'wait_{t_type}'].get(trailer_cap)
                    yield env.timeout(get_stochastic_val(load_dist, load_p))
                    kpi["delivered_ton"][y_name] += trailer_cap
                    add_util(l_util, y_name, env.now - start_l)
                    tail['start'] = env.now 
                    if y_name == hub_name: yield (hub_full_f if t_type == 'f' else hub_full_b).put(tail)
                    else: yield final_y[y_name][f'full_{t_type}'].put(tail)
            else: yield env.timeout(1)

    def tractor_leg_b(t_id, init_job=None):
        tid_name = f"Hub-LegB #{t_id}"
        if init_job:
            m_key = "สด" if init_job == 'F' else "ไหม้"
            fac_q_monitor[m_key] += 1
            if env.now < fac_open_min: yield env.timeout(fac_open_min - env.now)
            with (slots_f if init_job == 'F' else slots_b).request() as req:
                yield req
                start_work = env.now
                yield env.timeout(get_stochastic_val(unld_dist, unld_p))
            fac_q_monitor[m_key] -= 1
            speed = get_stochastic_val(fleet_config[hub_name]['speed_type'], fleet_config[hub_name]['speed_params'])
            yield env.timeout((dist_hub_factory/speed)*60)
            yield final_y[hub_name]['empty'].put({"id": f"Overnight-{t_id}", "loc": hub_name, "start": env.now})
            add_util(t_util, tid_name, env.now - start_work)

        while env.now < fac_close_min:
            t_type = "B" if len(hub_full_b.items) > 0 else ("F" if len(hub_full_f.items) > 0 else None)
            if t_type:
                start_work = env.now
                tail = yield (hub_full_b if t_type == "B" else hub_full_f).get()
                speed = get_stochastic_val(fleet_config[hub_name]['speed_type'], fleet_config[hub_name]['speed_params'])
                yield env.timeout((dist_hub_factory/speed)*60)
                m_key = "ไหม้" if t_type == "B" else "สด"
                fac_q_monitor[m_key] += 1
                if env.now < fac_open_min: yield env.timeout(fac_open_min - env.now)
                with (slots_b if t_type == "B" else slots_f).request() as req:
                    yield req
                    yield env.timeout(get_stochastic_val(unld_dist, unld_p))
                fac_q_monitor[m_key] -= 1
                yield env.timeout((dist_hub_factory/speed)*60)
                yield final_y[hub_name]['empty'].put(tail)
                add_util(t_util, tid_name, env.now - start_work)
            else: yield env.timeout(5)

    def tractor_leg_a(y_name, t_idx, dist):
        tid_name = f"{y_name} #{t_idx}"
        while env.now < yard_close_min:
            t_type = 'f' if len(final_y[y_name]['full_f'].items) > 0 else ('b' if len(final_y[y_name]['full_b'].items) > 0 else None)
            if t_type:
                start_work = env.now
                tail = yield final_y[y_name][f'full_{t_type}'].get()
                speed = get_stochastic_val(fleet_config[y_name]['speed_type'], fleet_config[y_name]['speed_params'])
                yield env.timeout((dist/speed)*60) 
                yield (hub_full_f if t_type == 'f' else hub_full_b).put(tail)
                new_tail = yield final_y[hub_name]['empty'].get()
                yield env.timeout((dist/speed)*60)
                yield final_y[y_name]['empty'].put(new_tail)
                add_util(t_util, tid_name, env.now - start_work)
            else: yield env.timeout(5)

    def monitor_proc():
        while env.now <= sim_duration:
            h_str = f"{int((start_min+env.now)//60):02d}:00"
            for y in yards_list:
                kpi["history"].append({"Hour": h_str, "Location": y, "Value": len(final_y[y]['empty'].items), "Type": "1. หางว่าง"})
                kpi["history"].append({"Hour": h_str, "Location": y, "Value": len(final_y[y]['full_f'].items) + len(final_y[y]['full_b'].items), "Type": "2. หางหนักค้างลาน"})
            kpi["history"].append({"Hour": h_str, "Location": "Hub (สด)", "Value": len(hub_full_f.items), "Type": "3. หางหนักค้าง Hub"})
            kpi["history"].append({"Hour": h_str, "Location": "Hub (ไหม้)", "Value": len(hub_full_b.items), "Type": "3. หางหนักค้าง Hub"})
            kpi["history"].append({"Hour": h_str, "Location": "โรงงาน (สด)", "Value": fac_q_monitor["สด"], "Type": "4. คิวโรงงาน"})
            kpi["history"].append({"Hour": h_str, "Location": "โรงงาน (ไหม้)", "Value": fac_q_monitor["ไหม้"], "Type": "4. คิวโรงงาน"})
            yield env.timeout(60)

    env.process(monitor_proc())
    
    for y in yards_list:
        for _ in range(fleet_config[y]['n_loaders']): env.process(loader_worker(y))
        if y == hub_name:
            n_hub_t = fleet_config[hub_name]['n_t']
            for i in range(n_hub_t):
                job = 'F' if i < init_fac_fresh else ('B' if i < (init_fac_fresh + init_fac_burnt) else None)
                env.process(tractor_leg_b(i+1, job))
        else:
            for i in range(fleet_config[y]['n_t']): env.process(tractor_leg_a(y, i+1, loc_params[y]['dist']))
        def farmer(yn):
            for f, b in zip(loc_params[yn]['fresh'], loc_params[yn]['burnt']):
                if f > 0: yield final_y[yn]['wait_f'].put(f)
                if b > 0: yield final_y[yn]['wait_b'].put(b)
                yield env.timeout(60)
        env.process(farmer(y))

    env.run(until=sim_duration + 1)
    return kpi, final_y, t_util, l_util, sim_duration

# ==========================================
# 5. EXECUTION & RESULTS
# ==========================================
if st.button("🚀 รันการจำลองระบบ", use_container_width=True, type="primary"):
    data, final_y, t_utils, l_utils, total_time = run_ksl_simulation()
    df_h = pd.DataFrame(data['history'])
    
    st.header("📈 1. Monitor สถานะระบบ")
    st.plotly_chart(px.line(df_h[df_h['Type'] == "1. หางว่าง"], x="Hour", y="Value", color="Location", markers=True, title="หางว่างคงเหลือรายลาน"), use_container_width=True)
    
    c1, c2 = st.columns(2)
    with c1: st.plotly_chart(px.line(df_h[df_h['Type'] == "2. หางหนักค้างลาน"], x="Hour", y="Value", color="Location", markers=True, title="หางหนักค้างลานลูก (Spoke Overnight)"), use_container_width=True)
    with c2: st.plotly_chart(px.line(df_h[df_h['Type'] == "3. หางหนักค้าง Hub"], x="Hour", y="Value", color="Location", markers=True, title="หางหนักสะสมที่ Hub (สำหรับรถส่งโรงงาน)"), use_container_width=True)

    st.plotly_chart(px.line(df_h[df_h['Type'] == "4. คิวโรงงาน"], x="Hour", y="Value", color="Location", markers=True, title="คิวรถรอเทหน้าโรงงาน"), use_container_width=True)

    st.header("⚙️ 2. Dashboards ประสิทธิภาพ")
    tab1, tab2 = st.tabs(["🚛 รถลาก (Utilization)", "🏗️ รถคีบ (Utilization)"])
    
    with tab1:
        # แก้ไข Logic ตรงนี้เพื่อป้องกัน DataFrame ว่าง
        if t_utils:
            u_t_list = []
            for k, v in t_utils.items():
                work_pct = (v / total_time) * 100
                u_t_list.append({"Tractor": k, "Working (%)": work_pct, "Idle (%)": 100 - work_pct})
            
            df_util = pd.DataFrame(u_t_list)
            st.plotly_chart(px.bar(df_util, x="Tractor", y=["Working (%)", "Idle (%)"], 
                                   barmode="stack", title="สัดส่วนการทำงานของรถลากแต่ละคัน"), use_container_width=True)
        else:
            st.warning("⚠️ ไม่พบข้อมูลการวิ่งของรถลาก กรุณาตรวจสอบจำนวนรถลากหรือระยะเวลาจำลอง")

    with tab2:
        u_l_list = []
        for y in yards_list:
            n_l = fleet_config[y]['n_loaders']
            if n_l > 0:
                util = (l_utils.get(y, 0) / (total_time * n_l)) * 100
                u_l_list.append({"Yard": y, "Utilization (%)": util})
        
        if u_l_list:
            st.plotly_chart(px.bar(pd.DataFrame(u_l_list), x="Yard", y="Utilization (%)", 
                                   color="Utilization (%)", title="ประสิทธิภาพการใช้รถคีบ"), use_container_width=True)
        else:
            st.info("ไม่มีข้อมูลรถคีบ")

    st.divider()
    # สรุปผลตารางด้านล่าง
    st.subheader("📊 ตารางสรุปผลรายศูนย์")
    summary_data = []
    for y in yards_list:
        summary_data.append({
            "ลาน": y,
            "อ้อยที่ขนสำเร็จ (ตัน)": f"{data['delivered_ton'][y]:,.1f}",
            "หางว่างเหลือที่ลาน": len(final_y[y]['empty'].items),
            "หางหนักค้างลาน (อ้อยค้าง)": len(final_y[y]['full_f'].items) + len(final_y[y]['full_b'].items)
        })
    st.table(summary_data)
