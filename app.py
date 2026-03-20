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
    with col_b: n_slots_burnt = st.number_input("ช่องเทอ้อยไฟไหม้", 0, 20, 0)
    
    st.subheader("🚛 คิวค้างหน้าโรงงาน")
    col_if1, col_if2 = st.columns(2)
    with col_if1: init_fac_fresh = st.number_input("หางหนักอ้อยสด (ใบ)", 0, 100, 0, key="init_fac_f")
    with col_if2: init_fac_burnt = st.number_input("หางหนักอ้อยไฟไหม้ (ใบ)", 0, 100, 0, key="init_fac_b")

    st.subheader("📦 หางหนักค้างที่ Hub")
    col_h1, col_h2 = st.columns(2)
    with col_h1: init_hub_fresh = st.number_input("อ้อยสดที่ Hub (ใบ)", 0, 100, 0, key="init_hub_f")
    with col_h2: init_hub_burnt = st.number_input("อ้อยไหม้ที่ Hub (ใบ)", 0, 100, 0, key="init_hub_b")

    st.subheader("� ปัจจัยแทรกซ้อน (External Factors)")
    ext_prob = st.number_input("โอกาสเจอรถคิวก่อนหน้า (%)", 0, 100, 20)
    ext_min, ext_max = st.columns(2)
    with ext_min: n_ext_min = st.number_input("จำนวนคันที่แทรก (Min)", 1, 20, 1)
    with ext_max: n_ext_max = st.number_input("จำนวนคันที่แทรก (Max)", 1, 20, 3)
        
    dist_hub_factory = st.number_input("ระยะทาง Hub -> โรงงาน (กม.)", 1, 200, 60)

    st.subheader("⏱️ ตั้งค่าเวลาในกระบวนการทำงาน")
    unld_dist, unld_p = stochastic_input_ui("เวลาในการเทต่อคันต่อช่อง", "unld", 100)
    hook_dist, hook_p = stochastic_input_ui("เวลาเกี่ยว/ถอดหางต่อคัน", "hook", 30)
    load_dist, load_p = stochastic_input_ui("เวลาคีบอ้อยต่อหาง", "load", 45)
    
    trailer_cap = st.number_input("ความจุต่อหาง (ตัน)", 10.0, 50.0, 29.0)
    
    num_days = st.number_input("จำนวนวันที่จำลอง (วัน)", 1, 30, 1)

    st.subheader("☕ เวลาพักเบรก (Lunch Break)")
    brk_y_start, brk_y_end = st.time_input("พักลาน (เริ่ม)", time(12,0)), st.time_input("พักลาน (เสร็จ)", time(13,0))
    brk_f_start, brk_f_end = st.time_input("พักโรงงาน (เริ่ม)", time(12,0)), st.time_input("พักโรงงาน (เสร็จ)", time(13,0))

# Calculate simulation time
start_min = yard_start.hour * 60 + yard_start.minute
fac_open_min = (fac_start.hour * 60 + fac_start.minute) - start_min
fac_close_min = (fac_end.hour * 60 + fac_end.minute) - start_min
yard_close_min = (yard_end.hour * 60 + yard_end.minute) - start_min
sim_duration = (1440 * (num_days - 1)) + max(fac_close_min, yard_close_min)

yb_s, yb_e = (brk_y_start.hour*60 + brk_y_start.minute) - start_min, (brk_y_end.hour*60 + brk_y_end.minute) - start_min
fb_s, fb_e = (brk_f_start.hour*60 + brk_f_start.minute) - start_min, (brk_f_end.hour*60 + brk_f_end.minute) - start_min

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
            # --- ส่วนสุ่มแผนอ้อย (Auto-Generate) ---
            st.markdown("🎲 **สุ่มแผนการเข้าอ้อย (Auto-Generate)**")
            ag_c1, ag_c2 = st.columns(2)
            with ag_c1: 
                gen_total_f = st.number_input("เป้าอ้อยสด/วัน (ตัน)", 0, 10000, 100, key=f"gtf_{y_name}")
                gen_total_b = st.number_input("เป้าอ้อยไหม้ (ตัน)", 0, 10000, 0, key=f"gtb_{y_name}")
            with ag_c2:
                # Default 06:00 - 15:00 (Check bounds)
                def_s = 0 
                def_e = min(len(range(yard_start.hour, yard_end.hour+1))-1, 9) # 15:00 is approx index 9 from 06:00
                gen_start = st.selectbox("เริ่ม (น.)", range(yard_start.hour, yard_end.hour+1), index=def_s, key=f"gs_{y_name}")
                gen_end = st.selectbox("ถึง (น.)", range(yard_start.hour, yard_end.hour+1), index=def_e, key=f"ge_{y_name}")
            
            # Peak Time Selection
            pk_c1, pk_c2 = st.columns(2)
            with pk_c1: peak_h1 = st.selectbox("Peak Time 1 ", range(yard_start.hour, yard_end.hour+1), index=min(3, len(range(yard_start.hour, yard_end.hour+1))-1), key=f"pk1_{y_name}", help="ช่วงเวลาที่มีอ้อยเข้าเยอะกว่าปกติ")
            with pk_c2: peak_h2 = st.selectbox("Peak Time 2 ", range(yard_start.hour, yard_end.hour+1), index=min(7, len(range(yard_start.hour, yard_end.hour+1))-1), key=f"pk2_{y_name}")

            use_daily_gen = st.checkbox("🔄 สุ่มแผนใหม่ทุกวัน (Daily Random)", value=False, key=f"udg_{y_name}", help="หากเลือก ระบบจะสุ่มยอดเข้าใหม่ทุกวันตามเป้าที่ตั้งไว้ โดยไม่ใช้ค่าในตารางด้านล่าง")
            
            b_gen, b_reset = st.columns(2)
            with b_gen:
                if st.button("🎲 สุ่มและกระจายยอด", key=f"btn_gen_{y_name}", use_container_width=True):
                    active_hours = [h for h in range(yard_start.hour, yard_end.hour + 1) if gen_start <= h <= gen_end]
                    if active_hours:
                        # สุ่ม Weight และปรับ Peak Time
                        weights_f = np.random.rand(len(active_hours))
                        weights_b = np.random.rand(len(active_hours))
                        
                        for i, h in enumerate(active_hours):
                            if h == peak_h1 or h == peak_h2:
                                weights_f[i] *= 3
                                weights_b[i] *= 3
                        
                        # Normalize ให้ผลรวมเท่ากับเป้าหมายที่ตั้งไว้ (Total)
                        dist_f = (weights_f / weights_f.sum() * gen_total_f) if weights_f.sum() > 0 else weights_f
                        dist_b = (weights_b / weights_b.sum() * gen_total_b) if weights_b.sum() > 0 else weights_b
                        
                        # บันทึกลง Session State
                        idx = 0
                        for h_chk in range(yard_start.hour, yard_end.hour + 1):
                            h_key = f"{h_chk:02d}:00"
                            val_f, val_b = (dist_f[idx], dist_b[idx]) if h_chk in active_hours else (0.0, 0.0)
                            if h_chk in active_hours: idx += 1
                            st.session_state[f"f_{y_name}_{h_key}"] = float(val_f)
                            st.session_state[f"b_{y_name}_{h_key}"] = float(val_b)
                        st.rerun()
            with b_reset:
                if st.button("🔄 รีเซ็ตเป็น 0", key=f"btn_reset_{y_name}", use_container_width=True):
                    for h_chk in range(yard_start.hour, yard_end.hour + 1):
                        h_key = f"{h_chk:02d}:00"
                        st.session_state[f"f_{y_name}_{h_key}"] = 0.0
                        st.session_state[f"b_{y_name}_{h_key}"] = 0.0
                    st.rerun()
            
            st.divider()
            plan_f, plan_b = [], []
            h_labels = [f"{h:02d}:00" for h in range(yard_start.hour, yard_end.hour + 1)]
            for h in h_labels:
                cx1, cx2 = st.columns(2)
                with cx1: f_v = st.number_input(f"อ้อยสด {h}", 0.0, 2000.0, 0.0, key=f"f_{y_name}_{h}")
                with cx2: b_v = st.number_input(f"อ้อยไฟไหม้ {h}", 0.0, 2000.0, 0.0, key=f"b_{y_name}_{h}")
                plan_f.append(f_v); plan_b.append(b_v)
            
            # Store Gen Params for Simulation
            loc_params[y_name] = {
                "fresh": plan_f, "burnt": plan_b, "dist": dist_h, "init_f": s_init_f, "init_b": s_init_b,
                "gen_params": {
                    "use_random": use_daily_gen, "total_f": gen_total_f, "total_b": gen_total_b,
                    "start": gen_start, "end": gen_end, "peaks": [peak_h1, peak_h2]
                }
            }

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
    
    kpi = {"delivered_ton": {y: 0.0 for y in yards_list}, "trips": {y: 0 for y in yards_list}, "history": [], "hourly_load": [], "loading_events": [], "incoming_cane": [], "hub_wait": [], "ext_wait": [], "total_dist_head": 0.0, "total_dist_tail": 0.0, "factory_delivered": 0.0,
           "total_fac_wait": 0.0, "fac_wait_count": 0, "trailer_util_sum": 0.0, "monitor_count": 0, "total_trailers": sum(fleet_config[y]['n_e'] for y in yards_list)}
    fac_q_monitor = {"สด": 0, "ไหม้": 0}
    t_util, l_util = {}, {}

    def add_util(tracker, key, duration):
        tracker[key] = tracker.get(key, 0.0) + duration

    # --- INITIALIZATION ---
    for y in yards_list:
        n_total = fleet_config[y]['n_e']
        if y == hub_name:
            # Hub uses global init settings + any specific yard settings
            hub_f_total = init_hub_fresh + loc_params[y]['init_f']
            hub_b_total = init_hub_burnt + loc_params[y]['init_b']
            n_e = max(0, n_total - (hub_f_total + hub_b_total + init_fac_fresh + init_fac_burnt))
            for i in range(hub_f_total): hub_full_f.put({"id": f"Hub-IF-{i}", "loc": hub_name, "start": env.now})
            for i in range(hub_b_total): hub_full_b.put({"id": f"Hub-IB-{i}", "loc": hub_name, "start": env.now})
        else:
            n_e = max(0, n_total - (loc_params[y]['init_f'] + loc_params[y]['init_b']))
            for i in range(loc_params[y]['init_f']): final_y[y]['full_f'].put({"id": f"{y}-IF-{i}", "loc": y, "start": env.now})
            for i in range(loc_params[y]['init_b']): final_y[y]['full_b'].put({"id": f"{y}-IB-{i}", "loc": y, "start": env.now})
        
        for j in range(n_e): final_y[y]['empty'].put({"id": f"{y}-E{j+1}", "loc": y, "start": env.now})

    def loader_worker(y_name):
        while env.now < sim_duration:
            # Multi-day Logic: ตรวจสอบเวลาปัจจุบันในรอบวัน (0-1439 นาที)
            tod = env.now % 1440
            
            # 1. เช็คเวลาปิดลาน (Overnight Sleep)
            if tod >= yard_close_min:
                yield env.timeout(1440 - tod)
                continue

            # ตรวจสอบเวลาพักลาน (Yard Break)
            if yb_s < yb_e and yb_s <= tod < yb_e:
                yield env.timeout(yb_e - tod)
                continue

            has_f = final_y[y_name]['wait_f'].level >= trailer_cap
            has_b = final_y[y_name]['wait_b'].level >= trailer_cap
            if (has_f or has_b) and len(final_y[y_name]['empty'].items) > 0:
                t_type = 'f' if has_f else 'b'
                with loaders_res[y_name].request() as req:
                    yield req
                    # ตรวจสอบเวลาพักอีกครั้งหลังได้คิว (ป้องกันกรณีรอคิวจนเลยเข้าเวลาพัก)
                    tod_check = env.now % 1440
                    if yb_s < yb_e and yb_s <= tod_check < yb_e:
                        yield env.timeout(yb_e - tod_check)
                    start_l = env.now
                    tail = yield final_y[y_name]['empty'].get()
                    yield env.timeout(get_stochastic_val(hook_dist, hook_p))
                    yield final_y[y_name][f'wait_{t_type}'].get(trailer_cap)
                    yield env.timeout(get_stochastic_val(load_dist, load_p))
                    kpi["delivered_ton"][y_name] += trailer_cap
                    kpi['loading_events'].append({'time_min': env.now, 'yard': y_name, 'tons': trailer_cap})
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
            
            t_arrival = env.now
            # คำนวณเวลารอโรงงานเปิด (สำหรับวันแรก หรือกรณีข้ามวัน)
            tod = env.now % 1440
            wait_time = max(0, fac_open_min - tod)
            if wait_time > 0: yield env.timeout(wait_time)
            
            # ตรวจสอบเวลาพักโรงงาน (Factory Break) - ขารถค้างคืน
            if fb_s < fb_e and fb_s <= (env.now % 1440) < fb_e:
                yield env.timeout(fb_e - (env.now % 1440))
            
            target_res = slots_f if init_job == 'F' else slots_b
            if target_res:
                with target_res.request() as req:
                    yield req
                    q_duration = env.now - t_arrival
                    kpi['total_fac_wait'] += q_duration
                    kpi['fac_wait_count'] += 1
                    start_work = env.now
                    yield env.timeout(get_stochastic_val(unld_dist, unld_p))
            kpi['factory_delivered'] += trailer_cap
            fac_q_monitor[m_key] -= 1
            speed = get_stochastic_val(fleet_config[hub_name]['speed_type'], fleet_config[hub_name]['speed_params'])
            yield env.timeout((dist_hub_factory/speed)*60)
            yield final_y[hub_name]['empty'].put({"id": f"Overnight-{t_id}", "loc": hub_name, "start": env.now})
            add_util(t_util, tid_name, env.now - start_work)
            kpi['trips'][hub_name] += 1
            kpi['total_dist_head'] += dist_hub_factory
            kpi['total_dist_tail'] += dist_hub_factory

        while env.now < sim_duration:
            tod = env.now % 1440
            
            # 1. เช็คเวลาปิดโรงงาน (Overnight Sleep)
            if tod >= fac_close_min:
                yield env.timeout(1440 - tod)
                continue

            t_type = "B" if len(hub_full_b.items) > 0 else ("F" if len(hub_full_f.items) > 0 else None)
            if t_type:
                start_work = env.now
                tail = yield (hub_full_b if t_type == "B" else hub_full_f).get()
                speed = get_stochastic_val(fleet_config[hub_name]['speed_type'], fleet_config[hub_name]['speed_params'])
                yield env.timeout((dist_hub_factory/speed)*60)
                m_key = "ไหม้" if t_type == "B" else "สด"
                fac_q_monitor[m_key] += 1
                
                t_arrival = env.now
                
                tod_arrival = env.now % 1440
                wait_time = max(0, fac_open_min - tod_arrival)
                if wait_time > 0: yield env.timeout(wait_time)
                
                # ตรวจสอบเวลาพักโรงงาน (Factory Break) - ขาปกติ
                if fb_s < fb_e and fb_s <= (env.now % 1440) < fb_e:
                    yield env.timeout(fb_e - (env.now % 1440))
                
                # --- จำลองรถชาวไร่แทรกคิว (External Traffic) ---
                if np.random.uniform(0, 100) < ext_prob:
                    # สุ่มจำนวนรถที่ขวางอยู่ และคำนวณเวลาที่ต้องรอ
                    n_ext = np.random.randint(n_ext_min, n_ext_max + 1)
                    wait_ext_duration = sum([get_stochastic_val(unld_dist, unld_p) for _ in range(n_ext)])
                    yield env.timeout(wait_ext_duration)
                    
                    current_day = int(env.now // 1440) + 1
                    tod_min = (start_min + env.now) % 1440
                    kpi['ext_wait'].append({'Hour': f"D{current_day} {int(tod_min//60):02d}:00", 'Tractor': tid_name, 'Duration': wait_ext_duration})
                
                target_res = slots_b if t_type == "B" else slots_f
                if target_res:
                    with target_res.request() as req:
                        yield req
                        
                        # --- FIX: Factory Closing Logic ---
                        # Ensure we don't start unloading if the factory has closed while we waited
                        tod_now = env.now % 1440
                        if tod_now >= fac_close_min:
                            # Factory closed, hold slot but wait until morning
                            yield env.timeout(1440 - tod_now + fac_open_min)
                        elif tod_now < fac_open_min:
                            # Arrived early morning
                            yield env.timeout(fac_open_min - tod_now)
                        # ----------------------------------
                        
                        q_duration = env.now - t_arrival
                        kpi['total_fac_wait'] += q_duration
                        kpi['fac_wait_count'] += 1
                        yield env.timeout(get_stochastic_val(unld_dist, unld_p))
                kpi['factory_delivered'] += trailer_cap
                fac_q_monitor[m_key] -= 1
                yield env.timeout((dist_hub_factory/speed)*60)
                yield final_y[hub_name]['empty'].put(tail)
                add_util(t_util, tid_name, env.now - start_work)
                kpi['trips'][hub_name] += 1
                kpi['total_dist_head'] += dist_hub_factory * 2
                kpi['total_dist_tail'] += dist_hub_factory * 2
            else: yield env.timeout(5)

    def tractor_leg_a(y_name, t_idx, dist):
        tid_name = f"{y_name} #{t_idx}"
        while env.now < sim_duration:
            tod = env.now % 1440
            # 1. เช็คเวลาปิดลาน
            if tod >= yard_close_min:
                yield env.timeout(1440 - tod)
                continue

            t_type = 'f' if len(final_y[y_name]['full_f'].items) > 0 else ('b' if len(final_y[y_name]['full_b'].items) > 0 else None)
            if t_type:
                start_work = env.now
                tail = yield final_y[y_name][f'full_{t_type}'].get()
                speed = get_stochastic_val(fleet_config[y_name]['speed_type'], fleet_config[y_name]['speed_params'])
                yield env.timeout((dist/speed)*60) 
                yield (hub_full_f if t_type == 'f' else hub_full_b).put(tail)
                
                # --- จับเวลาการรอหางว่างที่ Hub ---
                start_wait = env.now
                new_tail = yield final_y[hub_name]['empty'].get()
                wait_duration = env.now - start_wait
                if wait_duration > 0:
                    current_day = int(env.now // 1440) + 1
                    tod_min = (start_min + env.now) % 1440
                    kpi['hub_wait'].append({'Hour': f"D{current_day} {int(tod_min//60):02d}:00", 'Tractor': tid_name, 'Duration': wait_duration})
                
                yield env.timeout((dist/speed)*60)
                yield final_y[y_name]['empty'].put(new_tail)
                add_util(t_util, tid_name, env.now - start_work)
                kpi['trips'][y_name] += 1
                kpi['total_dist_head'] += dist * 2
                kpi['total_dist_tail'] += dist * 2
            else: yield env.timeout(5)

    def monitor_proc():
        while env.now <= sim_duration:
            # Format Day + Time
            current_day = int(env.now // 1440) + 1
            tod_min = (start_min + env.now) % 1440
            h_str = f"D{current_day} {int(tod_min//60):02d}:00"

            for y in yards_list:
                kpi["history"].append({"Hour": h_str, "Location": y, "Value": len(final_y[y]['empty'].items), "Type": "1. หางว่าง"})
                kpi["history"].append({"Hour": h_str, "Location": y, "Value": len(final_y[y]['full_f'].items) + len(final_y[y]['full_b'].items), "Type": "2. หางหนักค้างลาน"})
            kpi["history"].append({"Hour": h_str, "Location": "Hub (สด)", "Value": len(hub_full_f.items), "Type": "3. หางหนักค้าง Hub"})
            kpi["history"].append({"Hour": h_str, "Location": "Hub (ไหม้)", "Value": len(hub_full_b.items), "Type": "3. หางหนักค้าง Hub"})
            kpi["history"].append({"Hour": h_str, "Location": "โรงงาน (สด)", "Value": fac_q_monitor["สด"], "Type": "4. คิวโรงงาน"})
            kpi["history"].append({"Hour": h_str, "Location": "โรงงาน (ไหม้)", "Value": fac_q_monitor["ไหม้"], "Type": "4. คิวโรงงาน"})
            
            current_empty = sum(len(final_y[y]['empty'].items) for y in yards_list)
            kpi['trailer_util_sum'] += (kpi['total_trailers'] - current_empty)
            kpi['monitor_count'] += 1
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
            gp = loc_params[yn]['gen_params']
            
            for day in range(num_days):
                # Determine Plan for the Day
                daily_fresh, daily_burnt = [], []
                
                if gp['use_random']:
                    # Generate Random Plan
                    active_hours = [h for h in range(yard_start.hour, yard_end.hour + 1) if gp['start'] <= h <= gp['end']]
                    if not active_hours:
                        daily_fresh = [0.0] * len(loc_params[yn]['fresh'])
                        daily_burnt = [0.0] * len(loc_params[yn]['burnt'])
                    else:
                        w_f = np.random.rand(len(active_hours))
                        w_b = np.random.rand(len(active_hours))
                        # Apply Peaks
                        for idx, h_val in enumerate(active_hours):
                            if h_val in gp['peaks']:
                                w_f[idx] *= 2.5
                                w_b[idx] *= 2.5
                        
                        d_f = (w_f / w_f.sum() * gp['total_f']) if w_f.sum() > 0 else w_f
                        d_b = (w_b / w_b.sum() * gp['total_b']) if w_b.sum() > 0 else w_b
                        
                        # Map back to full hours
                        full_h = range(yard_start.hour, yard_end.hour + 1)
                        daily_fresh = [d_f[active_hours.index(h)] if h in active_hours else 0.0 for h in full_h]
                        daily_burnt = [d_b[active_hours.index(h)] if h in active_hours else 0.0 for h in full_h]
                else:
                    # Use Static Plan
                    daily_fresh = loc_params[yn]['fresh']
                    daily_burnt = loc_params[yn]['burnt']

                for f, b in zip(daily_fresh, daily_burnt):
                    if f + b > 0:
                        tod_min = (start_min + env.now) % 1440
                        h_str = f"D{day+1} {int(tod_min//60):02d}:00"
                        kpi["incoming_cane"].append({"Hour": h_str, "Location": yn, "Amount": f + b})
                    if f > 0: yield final_y[yn]['wait_f'].put(f)
                    if b > 0: yield final_y[yn]['wait_b'].put(b)
                    yield env.timeout(60)
                # จบแผนวันนั้นแล้ว ให้รอจนขึ้นวันใหม่ (Sleep overnight)
                day_gap = 1440 - (len(daily_fresh) * 60)
                if day_gap > 0: yield env.timeout(day_gap)
        env.process(farmer(y))

    env.run(until=sim_duration + 1)
    return kpi, final_y, t_util, l_util, sim_duration

# ==========================================
# 5. EXECUTION & RESULTS
# ==========================================
if st.button("🚀 รันการจำลองระบบ", use_container_width=True, type="primary"):
    data, final_y, t_utils, l_utils, total_time = run_ksl_simulation()
    df_h = pd.DataFrame(data['history'])
    
    # --- SUMMARY METRICS CALCULATION ---
    total_plan = 0
    total_trips = sum(data['trips'].values())
    for y in yards_list:
        if loc_params[y]['gen_params']['use_random']:
            total_plan += (loc_params[y]['gen_params']['total_f'] + loc_params[y]['gen_params']['total_b']) * num_days
        else:
            total_plan += (sum(loc_params[y]['fresh']) + sum(loc_params[y]['burnt'])) * num_days
            
    total_loaded = sum(data['delivered_ton'].values())
    total_delivered = data['factory_delivered']
    
    # คำนวณสต็อกเริ่มต้นทั้งหมดในระบบ (เพื่อใช้คำนวณของที่ค้างในระบบ)
    init_leaves = init_fac_fresh + init_fac_burnt
    for y in yards_list: init_leaves += loc_params[y]['init_f'] + loc_params[y]['init_b']
    total_init_inv = init_leaves * trailer_cap
    # Hub sidebar variables (init_hub_fresh/burnt) were missing from total count logic above if not in loc_params, adding them now:
    total_init_inv += (init_hub_fresh + init_hub_burnt) * trailer_cap
    
    # 1. Workload = Plan + Stock
    total_workload = total_plan + total_init_inv
    
    # 2. คีบไม่หมด (Leftover in Field)
    not_loaded = max(0, total_plan - total_loaded)
    # 2. ส่งไม่สำเร็จ (ค้างลาน/บนรถ/คิว) = (สต็อกเก่า+ที่คีบได้ใหม่) - ที่ส่งออกไปแล้ว
    not_delivered = max(0, (total_init_inv + total_loaded) - total_delivered)

    st.markdown("### 🏆 สรุปผลการดำเนินงาน (Executive Summary)")
    
    # Row 1: Cargo Metrics
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("1. ภาระงานรวม (Total)", f"{total_workload:,.0f} ตัน", help="สูตร: แผนอ้อยใหม่ตลอดช่วงเวลา + สต็อกเก่าค้างลาน/Hub/โรงงาน")
    mc2.metric("2. ส่งเข้าโรงงานสำเร็จ", f"{total_delivered:,.0f} ตัน", help="สูตร: อ้อยที่ผ่านกระบวนการเทลงรางและรถออกจากโรงงานเรียบร้อยแล้ว")
    mc3.metric("3. ส่งไม่สำเร็จ (Stuck)", f"{not_delivered:,.0f} ตัน", help="สูตร: ภาระงานรวม - ส่งสำเร็จ - คีบไม่หมด\n(คืออ้อยที่ค้างอยู่บนรถ, ค้างที่ Hub, หรือรอคิวหน้าโรงงาน)")
    mc4.metric("4. คีบไม่หมด (Leftover)", f"{not_loaded:,.0f} ตัน", help="สูตร: แผนอ้อยใหม่ - ยอดที่รถคีบทำงานได้จริง\n(คืออ้อยที่คีบไม่ทันหรืออ้อยที่อยู่บนหางที่ยังไม่เต็ม)")
    
    # Row 2: Distance & Trips (Moved to Top)
    d1, d2, d3 = st.columns(3)
    d1.metric("🚛 ระยะทางวิ่งรวม (หัวลาก)", f"{data['total_dist_head']:,.1f} กม.", help="ระยะทางรวมที่รถหัวลากวิ่งทั้งหมด (ไป-กลับ)")
    d2.metric("📦 ระยะทางวิ่งรวม (หางพ่วง)", f"{data['total_dist_tail']:,.1f} กม.", help="ระยะทางรวมที่หางพ่วงถูกลากไปมา")
    d3.metric("🔄 จำนวนเที่ยววิ่งรวม", f"{total_trips:,} เที่ยว", help="จำนวนเที่ยววิ่งรวม")
    
    st.divider()

    # --- EFFICIENCY & TIME METRICS ---
    st.subheader("⏱️ ประสิทธิภาพเวลาและการใช้งาน (Efficiency Metrics)")
    
    # Calculate Metrics
    avg_fac_wait = (data['total_fac_wait'] / data['fac_wait_count']) if data['fac_wait_count'] > 0 else 0
    
    total_loaders = sum(fleet_config[y]['n_loaders'] for y in yards_list)
    avg_loader_util = (sum(l_utils.values()) / (total_loaders * total_time) * 100) if total_loaders > 0 else 0
    
    total_tractors = sum(fleet_config[y]['n_t'] for y in yards_list)
    avg_tractor_util = (sum(t_utils.values()) / (total_tractors * total_time) * 100) if total_tractors > 0 else 0
    
    avg_trailer_util = ((data['trailer_util_sum'] / data['monitor_count']) / data['total_trailers'] * 100) if data['monitor_count'] > 0 and data['total_trailers'] > 0 else 0
    
    total_hub_wait = sum(d['Duration'] for d in data['hub_wait'])

    em1, em2, em3 = st.columns(3)
    em1.metric("⏳ เวลารอคิวเทรวม (Total Queue)", f"{data['total_fac_wait']/60:,.1f} ชม.", help="เวลาที่รถทุกคันต้องเสียไปกับการรอหน้าโรงงานรวมกัน")
    em2.metric("⏱️ เวลารอคิวเทเฉลี่ย/คัน", f"{avg_fac_wait:.1f} นาที", help="เวลารอคิวรวม / จำนวนเที่ยวที่เข้าโรงงาน")
    em3.metric("🔙 เวลารอหางเปล่าที่ Hub รวม", f"{total_hub_wait/60:,.1f} ชม.", help="เวลาที่รถลากจากลานลูกต้องจอดรอที่ Hub เพื่อรับหางเปล่ากลับไป")
    
    em4, em5, em6 = st.columns(3)
    em4.metric("🏗️ ประสิทธิภาพรถคีบเฉลี่ย", f"{avg_loader_util:.1f}%", help="เวลาทำงานจริง / เวลารวมทั้งหมด")
    em5.metric("🚛 ประสิทธิภาพรถลากเฉลี่ย", f"{avg_tractor_util:.1f}%", help="เวลาวิ่งงานจริง / เวลารวมทั้งหมด")
    em6.metric("📦 ประสิทธิภาพหางเฉลี่ย", f"{avg_trailer_util:.1f}%", help="(หางทั้งหมด - หางว่างที่จอดทิ้งในลาน) / หางทั้งหมด")
    
    st.divider()

    # --- TABS: MONITOR & FLEET ---
    tab_mon, tab_fleet = st.tabs(["📈 Monitoring (สถานะระบบ)", "⚙️ Fleet & Trips (รถและเที่ยววิ่ง)"])
    
    with tab_mon:
        st.caption("กราฟแสดงสถานะของระบบตามช่วงเวลา (Time Series Monitor)")
        if data['incoming_cane']:
            df_in = pd.DataFrame(data['incoming_cane'])
            st.plotly_chart(px.line(df_in, x="Hour", y="Amount", color="Location", markers=True, title="ปริมาณอ้อยเข้าลานตามช่วงเวลา (Incoming Cane)"), use_container_width=True)

        st.plotly_chart(px.line(df_h[df_h['Type'] == "1. หางว่าง"], x="Hour", y="Value", color="Location", markers=True, title="หางว่างคงเหลือรายลาน"), use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(px.line(df_h[df_h['Type'] == "2. หางหนักค้างลาน"], x="Hour", y="Value", color="Location", markers=True, title="หางหนักค้างลานลูก"), use_container_width=True)
        with c2: st.plotly_chart(px.line(df_h[df_h['Type'] == "3. หางหนักค้าง Hub"], x="Hour", y="Value", color="Location", markers=True, title="หางหนักสะสมที่ Hub (สำหรับรอส่งโรงงาน)"), use_container_width=True)
        
        st.plotly_chart(px.line(df_h[df_h['Type'] == "4. คิวโรงงาน"], x="Hour", y="Value", color="Location", markers=True, title="คิวรถรอเทหน้าโรงงาน"), use_container_width=True)
        
        # Realtime Loading
        if data['loading_events']:
            st.markdown("---")
            df_load_events = pd.DataFrame(data['loading_events'])
            df_load_events['Day'] = df_load_events['time_min'].apply(lambda x: int(x // 1440) + 1)
            df_load_events['Hour_of_Day'] = df_load_events['time_min'].apply(lambda x: int(((start_min + x) % 1440) // 60))
            df_load_events['Time_Str'] = df_load_events.apply(lambda r: f"D{int(r['Day'])} {int(r['Hour_of_Day']):02d}:00", axis=1)
            df_realtime = df_load_events.groupby(['Time_Str', 'yard'])['tons'].sum().reset_index(name='ปริมาณอ้อย (ตัน)')
            df_realtime = df_realtime.sort_values('Time_Str')
            st.plotly_chart(px.line(df_realtime, x='Time_Str', y='ปริมาณอ้อย (ตัน)', color='yard', markers=True, title='ปริมาณการคีบอ้อยรายชั่วโมง (Realtime Tonnage)'), use_container_width=True)

    with tab_fleet:
        st.caption("วิเคราะห์ประสิทธิภาพรถและปริมาณเที่ยววิ่ง (Fleet Efficiency & Trips)")
        
        # Trip Pie Chart
        df_trips = pd.DataFrame([{"Location": k, "Trips": v} for k, v in data['trips'].items() if v > 0])
        fig_pie = px.pie(df_trips, values='Trips', names='Location', title='สัดส่วนเที่ยววิ่งแยกตามศูนย์', hole=0.4)
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)
        st.divider()
        
        # Utilization Charts
        t1, t2 = st.tabs(["🚛 รถลาก", "🏗️ รถคีบ"])
        with t1:
            if t_utils:
                u_t_list = []
                for k, v in t_utils.items():
                    work_pct = (v / total_time) * 100
                    u_t_list.append({"Tractor": k, "Working (%)": work_pct, "Idle (%)": 100 - work_pct})
                df_util = pd.DataFrame(u_t_list)
                st.plotly_chart(px.bar(df_util, x="Tractor", y=["Working (%)", "Idle (%)"], barmode="stack", title="สัดส่วนการทำงานของรถลากแต่ละคัน"), use_container_width=True)
            else:
                st.warning("⚠️ ไม่พบข้อมูลการวิ่งของรถลาก")
        with t2:
            u_l_list = []
            for y in yards_list:
                n_l = fleet_config[y]['n_loaders']
                if n_l > 0:
                    util = (l_utils.get(y, 0) / (total_time * n_l)) * 100
                    u_l_list.append({"Yard": y, "Utilization (%)": util})
            if u_l_list:
                st.plotly_chart(px.bar(pd.DataFrame(u_l_list), x="Yard", y="Utilization (%)", color="Utilization (%)", title="ประสิทธิภาพการใช้รถคีบ"), use_container_width=True)
            else:
                st.info("ไม่มีข้อมูลรถคีบ")

    # --- Bar Charts with Day Tabs ---
    st.divider()
    st.subheader("📊 วิเคราะห์เวลารอคอย (แยกรายวัน)")
    
    # Create tabs for days
    day_tabs = st.tabs(["All Days"] + [f"Day {d+1}" for d in range(num_days)])
    
    for i, tab in enumerate(day_tabs):
        with tab:
            filter_prefix = f"D{i} " if i > 0 else "" # i=0 is All, i=1 is Day 1 (prefix D1)
            
            # 1. Hub Wait Chart
            if data['hub_wait']:
                df_wait = pd.DataFrame(data['hub_wait'])
                if i > 0: df_wait = df_wait[df_wait['Hour'].str.startswith(filter_prefix)]
                
                if not df_wait.empty:
                    st.plotly_chart(px.bar(df_wait, x="Hour", y="Duration", color="Tractor", title=f"⏳ การรอหางว่างที่ Hub ({'All' if i==0 else f'Day {i}'})", hover_data=["Tractor"]), use_container_width=True)
                else:
                    st.info(f"✅ Day {i}: ไม่มีการรอหางว่างที่ Hub")
            
            # 2. External Wait Chart
            if data['ext_wait']:
                df_ext = pd.DataFrame(data['ext_wait'])
                if i > 0: df_ext = df_ext[df_ext['Hour'].str.startswith(filter_prefix)]
                
                if not df_ext.empty:
                    st.plotly_chart(px.bar(df_ext, x="Hour", y="Duration", color="Tractor", title=f"🚧 การรอคิวแทรกหน้าโรงงาน ({'All' if i==0 else f'Day {i}'})", hover_data=["Tractor"]), use_container_width=True)
                else:
                    st.info(f"✅ Day {i}: ไม่มีการรอคิวแทรก")

    st.divider()
    st.subheader("📊 ตารางสรุปผลรายศูนย์")
    summary_data = []
    for y in yards_list:
        summary_data.append({
            "ลาน": y,
            "เที่ยววิ่ง": data['trips'][y],
            "อ้อยที่ขนสำเร็จ (ตัน)": f"{data['delivered_ton'][y]:,.1f}",
        })
    st.table(summary_data)
