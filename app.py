import streamlit as st
import simpy
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import time

try:
    import google.generativeai as genai
    has_genai = True
except ImportError:
    has_genai = False


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
yards_list = ["Hub", "ศูนย์โนนสัง", "ศูนย์โนนสว่าง", "ศูนย์ศรีบุญเรือง", "ศูนย์ข้องโป้", "ศูนย์ทรายทอง"]
hub_name = "Hub"
default_distances = {
    "Hub": 0.0, "ศูนย์โนนสัง": 60.0, "ศูนย์โนนสว่าง": 58.0, "ศูนย์ศรีบุญเรือง": 37.0, "ศูนย์ข้องโป้": 25.0, "ศูนย์ทรายทอง": 39.0
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
    st.info("🏭 โรงงานทำงาน 24 ชั่วโมง\n(กำหนดเวลาลานแยกรายศูนย์ที่หน้าจอหลัก)")

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
    
    trailer_cap = st.number_input("ความจุต่อหาง (ตัน)", 10.0, 50.0, 29.0)
    
    num_days = st.number_input("จำนวนวันที่จำลอง (วัน)", 1, 30, 1)

    # --- AI ASSISTANT (CHATBOT) ---
    st.divider()
    with st.expander("💬 สอบถามวิธีใช้งาน (AI Assistant)", expanded=True):
        st.caption("ผู้ช่วยอัจฉริยะ แนะนำการตั้งค่าและ Logic ระบบ")
        
        # 1. API Key Config
        api_key = st.text_input("Gemini API Key", type="password", help="ใส่ Google Gemini API Key เพื่อเริ่มแชท", key="chat_api_key")
        
        if st.button("🗑️ ล้างประวัติแชท", use_container_width=True):
            st.session_state.messages = [
                {"role": "assistant", "content": "สวัสดีครับ! ผมคือผู้ช่วย KSL Sim Copilot 🚜\nสงสัยเรื่องการตั้งค่าพารามิเตอร์ หรือ Logic การทำงานของ Hub & Spoke ถามผมได้เลยครับ"}
            ]
            st.rerun()

        # 2. Initialize Chat
        if "messages" not in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "สวัสดีครับ! ผมคือผู้ช่วย KSL Sim Copilot 🚜\nสงสัยเรื่องการตั้งค่าพารามิเตอร์ หรือ Logic การทำงานของ Hub & Spoke ถามผมได้เลยครับ"}
            ]

        # 3. Display Chat History
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

    # 4. Chat Input & Processing (ต้องอยู่นอก Expander)
    if prompt := st.chat_input("พิมพ์คำถามที่นี่...", key="sidebar_chat_input"):
        if not has_genai:
            st.error("⚠️ ไม่พบ Library AI: กรุณาติดตั้งโดยพิมพ์ใน Terminal: `pip install google-generativeai`")
        elif not api_key:
            st.error("กรุณาใส่ API Key ในกล่องแชทด้านบนก่อนครับ")
        else:
            # User Message
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # AI Processing
            try:
                genai.configure(api_key=api_key)
                
                # --- ดึงข้อมูลผลการจำลองจาก Session State (ถ้ามี) ---
                sim_result_context = ""
                if 'ai_sim_data' in st.session_state:
                    sim_res = st.session_state['ai_sim_data']
                    d = sim_res['data']
                    
                    total_trips_ai = sum(d['trips'].values())
                    avg_wait_ai = (d['total_fac_wait'] / d['fac_wait_count']) if d['fac_wait_count'] else 0
                    hub_wait_hr = sum(x['Duration'] for x in d['hub_wait']) / 60
                    
                    sim_result_context = f"""
                    \n**📊 ข้อมูลผลลัพธ์จากการจำลองล่าสุด (Simulation Results Data):**
                    - **ภาพรวม**: ภาระงานรวม {d.get('total_workload',0):,.0f} ตัน | ส่งสำเร็จ {d['factory_delivered']:,.0f} ตัน | เที่ยววิ่งรวม {total_trips_ai} เที่ยว
                    - **ประสิทธิภาพ**: รอคิวโรงงานเฉลี่ย {avg_wait_ai:.1f} นาที | รอหางที่ Hub รวม {hub_wait_hr:.1f} ชม.
                    - **ปัญหา (Issues)**: Stuck {d.get('stuck_tons',0):,.0f} ตัน | Leftover {d.get('leftover_tons',0):,.0f} ตัน | Overtime {d.get('overtime_tons',0):,.0f} ตัน
                    
                    **รายละเอียดรายศูนย์ (Trips / Delivered):**
                    """
                    for y, t in d['trips'].items():
                        sim_result_context += f"- {y}: {t} เที่ยว, {d['delivered_ton'][y]:,.0f} ตัน\n"
                    sim_result_context += "---\n(ใช้ข้อมูลข้างต้นตอบคำถามเกี่ยวกับผลลัพธ์ได้ทันที)\n"
                # -----------------------------------------------------
                
                # System Context (ความรู้เกี่ยวกับโปรแกรม)
                system_instruction = f"""
                คุณคือผู้ช่วย AI สำหรับโปรแกรม "KSL Logistics Simulation" (Hub & Spoke Model)
                หน้าที่: อธิบายวิธีการใช้งานและ Logic ของระบบจำลองขนส่งอ้อย
                {sim_result_context}

                **1. คำแนะนำการตั้งค่า Sidebar (Sidebar Settings):**
                - **เวลาเปิด-ปิด**: 
                   - *ลาน (Yard)*: กำหนดช่วงเวลา inflow ของชาวไร่ (แต่รถคีบ/รถลากทำงานเก็บตกได้นอกเวลาหากมีงานค้าง)
                   - *โรงงาน (Factory)*: กำหนดเวลาเปิดรับเท (ถ้านอกเวลา รถจะจอดรอข้ามคืน)
                - **ช่องเทโรงงาน (Factory Slots)**: จำนวนจุดรับเทอ้อยแยก สด/ไหม้ (เป็นคอขวดสำคัญ ถ้าน้อยเกินไปคิวจะยาว)
                - **คิวค้าง/หางค้าง (Initial Inventory)**: 
                   - *หน้าโรงงาน*: รถที่จอดรอคิวอยู่แล้วก่อนเริ่ม Simulation
                   - *Hub*: หางหนักที่กองรอที่ Hub (Buffer) พร้อมส่งโรงงาน
                - **ปัจจัยแทรกซ้อน (External Factors)**: โอกาส (%) ที่จะเจอรถชาวไร่นอกระบบมาแทรกคิวหน้าโรงงาน ทำให้เสียเวลารอเพิ่ม
                - **เวลาปฏิบัติการ (Stochastic Times)**: เวลาเท/เกี่ยว/คีบ สามารถตั้งเป็นค่าคงที่ หรือสุ่ม (Normal/Triangle) เพื่อความสมจริง

                **2. คำแนะนำการตั้งค่าศูนย์และ Hub (Yard Configuration 🛠️):**
                - **การตั้งค่าทั่วไป (General)**:
                   - **เวลาเปิด-ปิด**: กำหนดช่วงเวลาที่ชาวไร่นำอ้อยเข้าลาน (Inflow) ส่วนรถในระบบทำงาน 24 ชม. เพื่อเคลียร์ของ
                   - **ระยะทาง**: ระยะทางวิ่งจากลานไป Hub (หรือไปโรงงานสำหรับศูนย์โนนสัง Direct)
                - **ทรัพยากร (Resources)**:
                   - **รถลาก (Tractor)**: จำนวนหัวลากที่วิ่งประจำศูนย์นั้น
                   - **หางรวม (Trailers)**: จำนวนหางพ่วงทั้งหมดที่หมุนเวียนในศูนย์นั้น (ถ้าหางไม่พอ รถคีบจะไม่มีงานทำ/รถลากจะไม่มีของลาก)
                   - **รถคีบ (Loaders)**: มีเฉพาะที่ศูนย์ลูกข่าย (Hub ไม่มี) ทำงานคีบอ้อยจากรถชาวไร่ใส่หางพ่วง
                - **ตั้งค่าการขึ้นอ้อย (Loading Settings 🚜)**:
                   - **ปริมาณอ้อยบนรถลูกไร่ (Farmer Truck Load)**: น้ำหนักอ้อยเฉลี่ยต่อคันรถชาวไร่ (ตัน)
                     *Logic*: หางพ่วง 1 ใบ (~{trailer_cap} ตัน) ต้องใช้รถชาวไร่หลายคันมาเทรวมกันจนเต็ม (เช่น รถชาวไร่ 10 ตัน ต้องใช้ 3 คัน)
                     *ผลกระทบ*: ถ้ารถชาวไร่คันเล็ก ต้องใช้จำนวนคันมากเพื่อเติมเต็ม 1 หาง ทำให้เสียเวลาคีบนานขึ้นและรถคีบทำงานหนักขึ้น
                   - **เวลาคีบต่อรถขนอ้อย (Loading Time)**: เวลาที่รถคีบใช้จัดการรถชาวไร่ 1 คัน (นาที)
                     *Logic*: เป็นเวลา Service Time ต่อคันรถชาวไร่ (ไม่ใช่ต่อหางพ่วง)
                     *ผลกระทบ*: ถ้าตั้งเวลานาน จะทำให้ระบายรถชาวไร่ไม่ทัน เกิดอ้อยค้างในไร่ (Leftover) สูง
                - **แผนอ้อย (Cane Plan)**:
                   - **Manual**: กรอกยอดเข้าสด/ไหม้ รายชั่วโมงด้วยตนเอง
                   - **Auto-Generate**: ให้ระบบสุ่มยอดตามเป้าหมาย (Min/Max) และกระจายตามช่วงเวลา (Peak Time) เพื่อจำลองพฤติกรรมจริง
                   - **Daily Random**: หากเลือก ระบบจะสุ่มยอดใหม่ทุกวันที่มีการจำลอง (Multi-day) เพื่อความหลากหลาย

                **3. โครงสร้างและ Logic ของระบบ (System Overview):**
                - **Hub & Spoke**:
                   - **Hub ({hub_name})**: จุดพักหาง ใช้รถ **Leg B** วิ่ง Hub<->โรงงาน (Drop & Hook)
                   - **Spoke (ลูกข่าย)**: ใช้รถ **Leg A** วิ่ง Spoke->Hub ส่งหางเต็ม และ **ต้องรอรับหางเปล่าจาก Hub** กลับมา (ถ้าหางเปล่าขาด รถจะรอที่ Hub)
                   - **Direct (ศูนย์โนนสัง)**: วิ่งตรงเข้าโรงงาน ไม่ผ่าน Hub
                - **ทรัพยากร**: หางพ่วง (Trailer ~{trailer_cap} ตัน) เป็นทรัพยากรหมุนเวียนที่สำคัญที่สุด, รถคีบ (Loader) ทำงาน 24 ชม.
                
                **4. อธิบายความหมายส่วนแสดงผล (โดยละเอียด):**
                
                🏆 **สรุปผลการดำเนินงาน (Executive Summary):**
                1. **ภาระงานรวม (Total Workload)**: 
                   - ปริมาณอ้อยทั้งหมดที่ต้องบริหารจัดการ = (แผนอ้อยเข้าใหม่ + สต็อกเก่าค้างระบบทั้งหมด)
                2. **ส่งเข้าโรงงานสำเร็จ (Delivered)**: 
                   - อ้อยที่ขนส่งไปถึงและเทลงรางเรียบร้อยแล้วภายในเวลาที่กำหนด
                3. **ส่งไม่สำเร็จ (Stuck) - สำคัญ**: 
                   - อ้อยที่ "คีบใส่หางแล้ว" แต่ยังค้างอยู่ในระบบขนส่ง (บนรถ/คิวโรงงาน/รอที่ Hub) ยังไม่ลงรางเท
                   - *สาเหตุ*: เวลาไม่พอ, รถติดคิวโรงงานนาน, หรือการขนส่ง Hub->โรงงาน ระบายไม่ทัน
                4. **คีบไม่หมด (Leftover) - สำคัญ**: 
                   - อ้อยที่ยัง "กองอยู่ที่ลานหรือรอคิวคีบ" (ยังไม่ได้ถูกคีบขึ้นหาง)
                   - *สาเหตุ*: รถคีบไม่พอ หรือ ไม่มีหางเปล่าหมุนเวียนกลับมาให้ใส่ (System Deadlock/Starvation)
                5. **คีบหลังปิดลาน (Overtime)**: 
                   - ยอดอ้อยที่คีบได้ในช่วงเวลานอกทำการ (กลางคืน) แสดงถึงความสามารถในการเคลียร์อ้อยค้าง

                ⏱️ **ประสิทธิภาพเวลาและการใช้งาน (Efficiency Metrics):**
                - **เวลารอคิวเท (Queue Time)**: เวลารวมและเฉลี่ยต่อคันที่ต้องจอดรอหน้าโรงงาน (ยิ่งน้อยยิ่งดี ถ้า >60 นาที แสดงว่าคอขวดที่โรงงาน)
                - **เวลารอหางเปล่าที่ Hub (Hub Wait)**: *สำคัญ* คือเวลาที่รถลูกข่ายเสียเปล่าเพื่อรอรับหางเปล่า ถ้าสูง = ระบบขาดแคลนหางหมุนเวียน (Deadlock risk)
                - **Utilization (%)**: สัดส่วนการทำงานจริงเทียบกับเวลาทั้งหมด
                   - **รถคีบ**: ถ้าต่ำ อาจเพราะรถเยอะเกินความจำเป็น หรือไม่มีหางให้คีบ (Idle)
                   - **รถลาก**: ถ้าต่ำ แสดงว่ารถว่างงานเยอะ (Over-supply)
                   - **หางพ่วง**: วัดความถี่ในการถูกใช้งานหมุนเวียน

                📈 **การแปลผลกราฟสถานะระบบ (Monitoring Analysis):**
                - **รถขนอ้อยขาเข้า (Incoming Trucks)**: ดูช่วงเวลาที่รถเข้าเยอะ (Peak) เพื่อวางแผนรถคีบ
                - **คิวรถรอคีบ (Queue Length)**: ถ้ากราฟพุ่งสูงค้างนาน แสดงว่ารถคีบทำงานไม่ทัน
                - **หางว่างคงเหลือ (Empty Trailers)**: ถ้ากราฟแตะ 0 บ่อยๆ แสดงว่าระบบ "ขาดหาง" ทำให้การคีบชะงัก (Starvation)
                - **หางหนักค้างลาน**: ถ้าสูงขึ้นเรื่อยๆ แสดงว่ารถลากลูกข่าย (Leg A) ระบายของไม่ทัน
                - **หางหนักค้าง Hub**: ถ้ากราฟชันขึ้น แสดงว่ารถส่งโรงงาน (Leg B) ระบายออกไม่ทัน หรือติดคิวโรงงาน
                - **คิวโรงงาน**: แสดงความหนาแน่นหน้าโรงงาน (ช่วงเช้าอาจสูงจากการรอเปิด)

                ⚙️ **การวิเคราะห์รถและเที่ยววิ่ง (Fleet & Trips Analysis):**
                - **สัดส่วนเที่ยววิ่ง**: แสดงปริมาณงานขนส่งแยกรายศูนย์ (ดูว่าศูนย์ไหนวิ่งเยอะ/น้อย เพื่อเกลี่ยทรัพยากร)
                - **ประสิทธิภาพรถลาก (Tractor Utilization)**: กราฟแท่งแสดงสัดส่วนเวลาทำงาน (Working) เทียบกับเวลาว่าง (Idle) ของรถแต่ละคัน
                   - *Working*: เวลาที่รถวิ่งรับ-ส่งจริง
                   - *Idle*: เวลาที่จอดรอคิว, รอหาง, หรือไม่มีงานทำ (ถ้าสูง >50% อาจพิจารณาลดจำนวนรถ)
                - **ประสิทธิภาพรถคีบ (Loader Utilization)**: แสดงความคุ้มค่าของการใช้รถคีบในแต่ละลาน (ถ้า % สูงมากเสี่ยงรถเสีย, ถ้าต่ำเกินไปแสดงว่ารถเยอะเกินจำเป็น)

                ⏱️ **Cycle Analysis (วิเคราะห์รอบเวลา):**
                - **ตารางสถิติ (Statistics)**: 
                   - **Avg (min)**: เวลาเฉลี่ยที่ใช้ในการทำงาน 1 รอบ (Cycle Time) ยิ่งน้อยยิ่งดี
                   - **Std Dev**: ค่าความเบี่ยงเบนมาตรฐาน (ถ้าสูงแสดงว่าเวลารอบแกว่งมาก ไม่เสถียร อาจเกิดจากคิวที่ไม่แน่นอน)
                   - **Max**: เวลารอบที่นานที่สุด (Worst-case) มักเกิดในช่วง Peak หรือรถติดคิวหนัก
                - **Boxplot (การกระจายตัว)**: 
                   - กราฟกล่องช่วยให้เห็นช่วงเวลาทำงานส่วนใหญ่ (กล่องสี่เหลี่ยม) และค่าผิดปกติ (Outliers จุดๆ)
                   - ถ้ารถลาก (Tractor) มี Cycle Time สูงผิดปกติ ให้เช็คคิวโรงงาน หรือคิวรอหางที่ Hub
                   - ถ้ารถคีบ (Loader) มีเวลานาน อาจเกิดจากรอรถชาวไร่ หรือประสิทธิภาพการคีบ

                ตอบคำถามโดยวิเคราะห์ตาม Logic นี้เท่านั้น
                """
                
                with st.spinner("..."):
                    # เทคนิค: ดึงรายชื่อโมเดลที่ใช้งานได้จริงจาก API ของ User (Auto-Discovery)
                    try:
                        # ดึงโมเดลที่รองรับ generateContent
                        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                        # จัดลำดับความสำคัญ: Flash (เร็ว) -> Pro (ฉลาด) -> อื่นๆ
                        candidate_models = sorted(available, key=lambda x: 0 if 'flash' in x else (1 if 'pro' in x else 2))
                    except:
                        # Fallback ถ้าดึง List ไม่ได้ (กรณี Key มีปัญหาหรือ Net หลุด)
                        candidate_models = ["models/gemini-1.5-flash", "gemini-1.5-flash", "models/gemini-pro", "gemini-pro"]

                    response = None
                    last_error = None
                    
                    for model_name in candidate_models:
                        try:
                            model = genai.GenerativeModel(model_name)
                            response = model.generate_content(f"{system_instruction}\n\nUser Question: {prompt}")
                            break # ถ้าสำเร็จ ให้หยุดลอง
                        except Exception as e:
                            last_error = e
                            continue # ถ้าไม่สำเร็จ ให้ลองตัวถัดไป

                    if response:
                        ai_reply = response.text
                        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                        st.rerun()
                    else:
                        st.error(f"❌ ไม่สามารถเชื่อมต่อกับ AI ได้ (ลองทั้งหมด {len(candidate_models)} โมเดล). Error ล่าสุด: {last_error}")
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")

# Calculate simulation time
sim_duration = 1440 * num_days
start_min = 0 # 24H Simulation starts at 00:00

# ==========================================
# 3. MAIN UI - YARD CONFIG
# ==========================================
st.divider()
st.subheader("🛠️ ตั้งค่าศูนย์และ Hub (Yard Configuration)")
loc_params, fleet_config = {}, {}
yard_tabs = st.tabs([f"📍 {y}" for y in yards_list])

for i, (y_name, tab) in enumerate(zip(yards_list, yard_tabs)):
    with tab:
        # Per-Yard Operating Hours
        c_gen1, c_gen2, c_gen3 = st.columns([1, 1, 1.5])
        
        with c_gen1:
            if y_name == hub_name:
                st.info("🕒 Hub ทำงาน 24 ชม.")
                y_start = time(0, 0)
                y_end = time(23, 59)
                start_m_val, end_m_val = 0, 1440
            else:
                y_start = st.time_input(f"เวลาเปิด ({y_name})", time(6, 0), key=f"yst_{y_name}")
                start_m_val = y_start.hour * 60 + y_start.minute

        with c_gen2:
            if y_name != hub_name:
                y_end = st.time_input(f"เวลาปิด ({y_name})", time(18, 0), key=f"yed_{y_name}")
                end_m_val = y_end.hour * 60 + y_end.minute
                # Fix: ถ้าเลือก 23:59 ให้ปัดเป็น 1440 (ครบ 24 ชม. เต็ม) เพื่อไม่ให้หยุดทำงาน 1 นาทีตอนเที่ยงคืน
                if end_m_val == 1439: end_m_val = 1440
            else:
                pass # Hub handled above

        with c_gen3:
            if y_name == "ศูนย์โนนสัง":
                st.caption("🚛 วิ่งตรงเข้าโรงงาน (Direct)")
                dist_h = st.number_input(f"ระยะทางไปโรงงาน (กม.)", 0.0, 200.0, default_distances[y_name], key=f"d_{y_name}")
            elif y_name == hub_name:
                dist_h = 0.0
                st.caption("🏁 จุดศูนย์กลาง (Hub)")
            else:
                dist_h = st.number_input(f"ระยะทางจากลานไป Hub", 0.0, 200.0, default_distances[y_name], key=f"d_{y_name}")
            
        st.divider()
        
        # Resource Configuration
        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        with c_res1: n_t = st.number_input("🚛 รถลาก (คัน)", 0, 50, 5 if i==0 else 2, key=f"nty_{y_name}")
        with c_res2: n_e = st.number_input("📦 หางรวม (ใบ)", 1, 500, 6, key=f"ne_{y_name}")
        with c_res3:
            if y_name == hub_name:
                n_loaders = 0
                st.write("🏗️ รถคีบ: -")
            else:
                n_loaders = st.number_input("🏗️ รถคีบ (คัน)", 1, 10, 1, key=f"nl_{y_name}")
        
        with c_res4:
            st.markdown(f"**หางหนักค้าง {y_name}**")
            ci1, ci2 = st.columns(2)
            s_init_f = ci1.number_input("สด", 0, 100, 0, key=f"init_f_{y_name}")
            s_init_b = ci2.number_input("ไหม้", 0, 100, 0, key=f"init_b_{y_name}")

        st.write("")
        with st.expander("🚚 ตั้งค่าความเร็ว (Speed Settings)"):
            s_type, s_p = stochastic_input_ui(f"Speed {y_name}", f"speed_{y_name}", 40)
            fleet_config[y_name] = {"n_t": n_t, "n_e": n_e, "n_loaders": n_loaders, "speed_type": s_type, "speed_params": s_p}
        
        # Initialize truck variables with defaults (ป้องกัน Error สำหรับ Hub)
        ft_type, ft_p = "Constant", {'val': 12.0}
        ld_type, ld_p = "Constant", {'val': 15.0} # Default loading time
        if y_name != hub_name:
            with st.expander("🚜 ตั้งค่าการขึ้นอ้อย"):
                ft_type, ft_p = stochastic_input_ui(f"ปริมาณอ้อยบนรถของลูกไร่ {y_name} (ตัน/คัน)", f"ft_{y_name}", 12.0)
                ld_type, ld_p = stochastic_input_ui(f"⏱️ เวลาคีบต่อรถขนอ้อย (นาที/คัน)", f"ld_{y_name}", 15.0)
        
        plan_f, plan_b = [], []
        gen_min_f, gen_max_f, gen_total_b = 0, 0, 0
        gen_start, gen_end = 0, 0
        peak_range_1, peak_range_2 = (0, 0), (0, 0)
        p1_share, p2_share = (0, 0), (0, 0)
        use_daily_gen = False

        if y_name != hub_name:
            with st.expander("📝 แผนอ้อย"):
                # --- ส่วนสุ่มแผนอ้อย (Auto-Generate) ---
                st.markdown("🎲 **สุ่มแผนการเข้าอ้อย (Auto-Generate)**")
                ag_c1, ag_c2 = st.columns(2)
                with ag_c1: 
                    c_min, c_max = st.columns(2)
                    gen_min_f = c_min.number_input("สด Min (ตัน)", 0, 10000, 100, key=f"gminf_{y_name}")
                    gen_max_f = c_max.number_input("สด Max (ตัน)", 0, 10000, 150, key=f"gmaxf_{y_name}")
                    gen_total_b = st.number_input("เป้าอ้อยไหม้ (ตัน)", 0, 10000, 0, key=f"gtb_{y_name}")
                with ag_c2:
                    # Default 06:00 - 15:00 (Check bounds)
                    def_s = 0 
                    def_e = min(len(range(y_start.hour, y_end.hour+1))-1, 9) # 15:00 is approx index 9 from 06:00
                    gen_start = st.selectbox("เริ่ม (น.)", range(y_start.hour, y_end.hour+1), index=def_s, key=f"gs_{y_name}")
                    gen_end = st.selectbox("ถึง (น.)", range(y_start.hour, y_end.hour+1), index=def_e, key=f"ge_{y_name}")
                
                # Peak Time Selection
                peak_opts = list(range(y_start.hour, y_end.hour+1))
                if not peak_opts: peak_opts = [6] # Fallback
                
                # Default Indices
                p1_s, p1_e = 0, min(2, len(peak_opts)-1)
                p2_s, p2_e = min(4, len(peak_opts)-1), min(6, len(peak_opts)-1)

                pk_c1, pk_c2 = st.columns(2)
                with pk_c1: 
                    peak_range_1 = st.select_slider("Peak Time 1 (ช่วงเวลา)", options=peak_opts, value=(peak_opts[p1_s], peak_opts[p1_e]), key=f"pk1_{y_name}")
                    p1_share = st.slider(f"สัดส่วนยอด Peak 1 (%)", 0, 100, (30, 40), key=f"p1_sh_{y_name}", help="% ของยอดอ้อยรายวันที่เข้าในช่วงเวลานี้")
                with pk_c2: 
                    peak_range_2 = st.select_slider("Peak Time 2 (ช่วงเวลา)", options=peak_opts, value=(peak_opts[p2_s], peak_opts[p2_e]), key=f"pk2_{y_name}")
                    p2_share = st.slider(f"สัดส่วนยอด Peak 2 (%)", 0, 100, (20, 30), key=f"p2_sh_{y_name}", help="% ของยอดอ้อยรายวันที่เข้าในช่วงเวลานี้")

                use_daily_gen = st.checkbox("🔄 สุ่มแผนใหม่ทุกวัน (Daily Random)", value=False, key=f"udg_{y_name}", help="หากเลือก ระบบจะสุ่มยอดเข้าใหม่ทุกวันตามเป้าที่ตั้งไว้ โดยไม่ใช้ค่าในตารางด้านล่าง")
                
                b_gen, b_reset = st.columns(2)
                with b_gen:
                    if st.button("🎲 สุ่มและกระจายยอด", key=f"btn_gen_{y_name}", use_container_width=True):
                        active_hours = [h for h in range(y_start.hour, y_end.hour + 1) if gen_start <= h <= gen_end]
                        if active_hours:
                            # สุ่ม Weight และปรับ Peak Time
                            weights_f = np.random.rand(len(active_hours))
                            weights_b = np.random.rand(len(active_hours))
                            
                            for i, h in enumerate(active_hours):
                                in_p1 = peak_range_1[0] <= h <= peak_range_1[1]
                                in_p2 = peak_range_2[0] <= h <= peak_range_2[1]
                                if in_p1 or in_p2:
                                    weights_f[i] *= 3
                                    weights_b[i] *= 3
                            
                            # Normalize ให้ผลรวมเท่ากับเป้าหมายที่สุ่มได้จากช่วง Min-Max
                            target_f = np.random.uniform(gen_min_f, gen_max_f)
                            dist_f = (weights_f / weights_f.sum() * target_f) if weights_f.sum() > 0 else weights_f
                            dist_b = (weights_b / weights_b.sum() * gen_total_b) if weights_b.sum() > 0 else weights_b
                            
                            # บันทึกลง Session State
                            idx = 0
                            for h_chk in range(y_start.hour, y_end.hour + 1):
                                h_key = f"{h_chk:02d}:00"
                                val_f, val_b = (dist_f[idx], dist_b[idx]) if h_chk in active_hours else (0.0, 0.0)
                                if h_chk in active_hours: idx += 1
                                st.session_state[f"f_{y_name}_{h_key}"] = float(val_f)
                                st.session_state[f"b_{y_name}_{h_key}"] = float(val_b)
                            st.rerun()
                with b_reset:
                    if st.button("🔄 รีเซ็ตเป็น 0", key=f"btn_reset_{y_name}", use_container_width=True):
                        for h_chk in range(y_start.hour, y_end.hour + 1):
                            h_key = f"{h_chk:02d}:00"
                            st.session_state[f"f_{y_name}_{h_key}"] = 0.0
                            st.session_state[f"b_{y_name}_{h_key}"] = 0.0
                        st.rerun()
                
                st.divider()
                h_labels = [f"{h:02d}:00" for h in range(y_start.hour, y_end.hour + 1)]
                for h in h_labels:
                    cx1, cx2 = st.columns(2)
                    with cx1: f_v = st.number_input(f"อ้อยสด {h}", 0.0, 2000.0, 0.0, key=f"f_{y_name}_{h}")
                    with cx2: b_v = st.number_input(f"อ้อยไฟไหม้ {h}", 0.0, 2000.0, 0.0, key=f"b_{y_name}_{h}")
                    plan_f.append(f_v); plan_b.append(b_v)
            
        # Store Gen Params for Simulation
        loc_params[y_name] = {
            "fresh": plan_f, "burnt": plan_b, "dist": dist_h,
            "init_f": s_init_f, "init_b": s_init_b,
            "truck_cap_type": ft_type, "truck_cap_params": ft_p,
            "load_time_type": ld_type, "load_time_params": ld_p,
            "start_min": start_m_val, "end_min": end_m_val,
            "gen_params": {
                "use_random": use_daily_gen, "min_f": gen_min_f, "max_f": gen_max_f, "total_b": gen_total_b,
                "start": gen_start, "end": gen_end, "peaks": [peak_range_1, peak_range_2],
                "peak_shares": [p1_share, p2_share]
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
    loaders_res = {y: simpy.Resource(env, capacity=fleet_config[y]['n_loaders']) for y in yards_list if fleet_config[y]['n_loaders'] > 0}
    final_y = {y: {
        "empty": simpy.Store(env), "full_f": simpy.Store(env), "full_b": simpy.Store(env),
        "wait_f": simpy.Store(env), "wait_b": simpy.Store(env)
    } for y in yards_list}
    
    kpi = {"delivered_ton": {y: 0.0 for y in yards_list}, "trips": {y: 0 for y in yards_list}, "history": [], "hourly_load": [], "loading_events": [], "incoming_cane": [], "hub_wait": [], "ext_wait": [], "total_dist_head": 0.0, "total_dist_tail": 0.0, "factory_delivered": 0.0,
           "total_fac_wait": 0.0, "fac_wait_count": 0, "trailer_util_sum": 0.0, "monitor_count": 0, "total_trailers": sum(fleet_config[y]['n_e'] for y in yards_list),
           "incoming_trucks": [], "queue_len": [], "cycle_logs": [], "overtime_tons": 0.0}
    fac_q_monitor = {"สด": 0, "ไหม้": 0}
    t_util, l_util = {}, {}

    def add_util(tracker, key, duration):
        tracker[key] = tracker.get(key, 0.0) + duration

    def log_cycle(res_type, name, yard, duration):
        kpi['cycle_logs'].append({"Type": res_type, "Name": name, "Yard": yard, "Duration": duration})

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

    # Shared state for active trailers (to allow parallel loading into one trailer)
    yard_active_trailer = {y: {'f': None, 'b': None, 'lock': simpy.Resource(env, 1)} for y in yards_list}

    def loader_worker(y_name):
        while env.now < sim_duration:
            y_start_min = loc_params[y_name]['start_min']
            y_end_min = loc_params[y_name]['end_min']
            # Multi-day Logic: ตรวจสอบเวลาปัจจุบันในรอบวัน (0-1439 นาที)
            tod = env.now % 1440
            
            # Check work: If queue not empty, keep working even if closed (Overtime)
            has_f_trucks = len(final_y[y_name]['wait_f'].items) > 0
            has_b_trucks = len(final_y[y_name]['wait_b'].items) > 0
            
            is_open = False
            if y_end_min > y_start_min:
                is_open = (y_start_min <= tod < y_end_min)
            else: # Cross midnight
                is_open = (tod >= y_start_min or tod < y_end_min)

            if not is_open and not (has_f_trucks or has_b_trucks):
                # Wait until open
                if tod < y_start_min:
                    yield env.timeout(y_start_min - tod)
                elif tod >= y_end_min:
                    yield env.timeout(1440 - tod + y_start_min)
                continue

            if (has_f_trucks or has_b_trucks):
                t_type = 'f' if has_f_trucks else 'b'
                with loaders_res[y_name].request() as req:
                    yield req
                    
                    # 1. Grab Farmer Truck
                    truck_load = yield final_y[y_name][f'wait_{t_type}'].get()
                    
                    # 2. Process/Load Truck (Time to lift cane from truck)
                    start_l = env.now
                    # Use yard-specific loading time per truck
                    yield env.timeout(get_stochastic_val(loc_params[y_name]['load_time_type'], loc_params[y_name]['load_time_params']))
                    duration = env.now - start_l
                    add_util(l_util, y_name, duration)
                    log_cycle('Loader', f"Loader @ {y_name}", y_name, duration)
                    
                    # 3. Dump into Shared Active Trailer (Critical Section)
                    with yard_active_trailer[y_name]['lock'].request() as lock_req:
                        yield lock_req
                        
                        # Get or Create Active Trailer
                        active_t = yard_active_trailer[y_name][t_type]
                        if active_t is None:
                            if len(final_y[y_name]['empty'].items) > 0:
                                active_t = yield final_y[y_name]['empty'].get()
                                active_t['load'] = 0.0
                                yard_active_trailer[y_name][t_type] = active_t
                            else:
                                # No empty trailers, must wait. Put truck back? 
                                # For simplicity, wait here for empty (blocking mutex - strictly serial dumping)
                                active_t = yield final_y[y_name]['empty'].get()
                                active_t['load'] = 0.0
                                yard_active_trailer[y_name][t_type] = active_t
                        
                        # Fill
                        space = trailer_cap - active_t['load']
                        amount_to_fill = min(space, truck_load)
                        active_t['load'] += amount_to_fill
                        
                        # --- เช็คการคีบหลังปิดลาน (Overtime) ---
                        tod_now = env.now % 1440
                        is_open_now = False
                        if y_end_min > y_start_min: is_open_now = (y_start_min <= tod_now < y_end_min)
                        else: is_open_now = (tod_now >= y_start_min or tod_now < y_end_min)
                        if not is_open_now: kpi['overtime_tons'] += amount_to_fill
                        # ------------------------------------
                        
                        kpi["delivered_ton"][y_name] += amount_to_fill
                        kpi['loading_events'].append({'time_min': env.now, 'yard': y_name, 'tons': amount_to_fill})
                        
                        # If trailer full, dispatch
                        if active_t['load'] >= trailer_cap - 0.01:
                            active_t['start'] = env.now
                            if y_name == hub_name:
                                yield (hub_full_f if t_type == 'f' else hub_full_b).put(active_t)
                            else:
                                yield final_y[y_name][f'full_{t_type}'].put(active_t)
                            yard_active_trailer[y_name][t_type] = None
                        
                        # If truck has remainder (rare case if truck > trailer space, but logical)
                        rem = truck_load - amount_to_fill
                        if rem > 0:
                            # Put remainder back to head of queue
                            # Since we don't have push_front, we put at end. 
                            # Or simpler: we assume we just fetch a new trailer immediately in this atomic block 
                            # if we have multiple empties. But let's stick to putting back to queue for robustness.
                            yield final_y[y_name][f'wait_{t_type}'].put(rem)
                            
            else: yield env.timeout(1)

    def tractor_leg_b(t_id, init_job=None):
        tid_name = f"Hub-LegB #{t_id}"
        if init_job:
            m_key = "สด" if init_job == 'F' else "ไหม้"
            fac_q_monitor[m_key] += 1
            t_arrival = env.now
            
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
            duration = env.now - start_work
            add_util(t_util, tid_name, duration)
            log_cycle('Tractor', tid_name, hub_name, duration)
            kpi['trips'][hub_name] += 1
            kpi['total_dist_head'] += dist_hub_factory
            kpi['total_dist_tail'] += dist_hub_factory

        while env.now < sim_duration:
            tod = env.now % 1440
            # Factory works 24h, no wait loop needed for closed hours

            t_type = "B" if len(hub_full_b.items) > 0 else ("F" if len(hub_full_f.items) > 0 else None)
            if t_type:
                start_work = env.now
                tail = yield (hub_full_b if t_type == "B" else hub_full_f).get()
                speed = get_stochastic_val(fleet_config[hub_name]['speed_type'], fleet_config[hub_name]['speed_params'])
                yield env.timeout((dist_hub_factory/speed)*60)
                m_key = "ไหม้" if t_type == "B" else "สด"
                fac_q_monitor[m_key] += 1
                
                t_arrival = env.now
                
                # --- จำลองรถชาวไร่แทรกคิว (External Traffic) ---
                if np.random.uniform(0, 100) < ext_prob:
                    # สุ่มจำนวนรถที่ขวางอยู่ และคำนวณเวลาที่ต้องรอ
                    n_ext = np.random.randint(n_ext_min, n_ext_max + 1)
                    wait_ext_duration = sum([get_stochastic_val(unld_dist, unld_p) for _ in range(n_ext)])
                    yield env.timeout(wait_ext_duration)
                    
                    current_day = int(env.now // 1440) + 1
                    tod_min = env.now % 1440
                    kpi['ext_wait'].append({'Hour': f"D{current_day} {int(tod_min//60):02d}:00", 'Tractor': tid_name, 'Duration': wait_ext_duration})
                
                target_res = slots_b if t_type == "B" else slots_f
                if target_res:
                    with target_res.request() as req:
                        yield req
                        
                        q_duration = env.now - t_arrival
                        kpi['total_fac_wait'] += q_duration
                        kpi['fac_wait_count'] += 1
                        yield env.timeout(get_stochastic_val(unld_dist, unld_p))
                kpi['factory_delivered'] += trailer_cap
                fac_q_monitor[m_key] -= 1
                yield env.timeout((dist_hub_factory/speed)*60)
                yield final_y[hub_name]['empty'].put(tail)
                add_util(t_util, tid_name, env.now - start_work)
                log_cycle('Tractor', tid_name, hub_name, env.now - start_work)
                kpi['trips'][hub_name] += 1
                kpi['total_dist_head'] += dist_hub_factory * 2
                kpi['total_dist_tail'] += dist_hub_factory * 2
            else: yield env.timeout(5)

    def tractor_leg_a(y_name, t_idx, dist):
        tid_name = f"{y_name} #{t_idx}"
        y_start_min = loc_params[y_name]['start_min']
        y_end_min = loc_params[y_name]['end_min']
        while env.now < sim_duration:
            tod = env.now % 1440
            
            # รถลากทำงาน 24 ชม. (Polling รองานทุก 5 นาทีถ้าไม่มีงาน)

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
                    tod_min = env.now % 1440
                    kpi['hub_wait'].append({'Hour': f"D{current_day} {int(tod_min//60):02d}:00", 'Tractor': tid_name, 'Duration': wait_duration})
                
                yield env.timeout((dist/speed)*60)
                yield final_y[y_name]['empty'].put(new_tail)
                add_util(t_util, tid_name, env.now - start_work)
                log_cycle('Tractor', tid_name, y_name, env.now - start_work)
                kpi['trips'][y_name] += 1
                kpi['total_dist_head'] += dist * 2
                kpi['total_dist_tail'] += dist * 2
            else: yield env.timeout(5)

    def tractor_direct(y_name, t_idx, dist):
        tid_name = f"{y_name} #{t_idx}"
        y_start_min = loc_params[y_name]['start_min']
        y_end_min = loc_params[y_name]['end_min']
        
        while env.now < sim_duration:
            tod = env.now % 1440
            
            # รถลาก Direct ทำงาน 24 ชม.

            # Check full trailers at yard
            t_type = 'f' if len(final_y[y_name]['full_f'].items) > 0 else ('b' if len(final_y[y_name]['full_b'].items) > 0 else None)
            
            if t_type:
                start_work = env.now
                # Get full trailer
                tail = yield final_y[y_name][f'full_{t_type}'].get()
                
                # Travel to Factory (Direct)
                speed = get_stochastic_val(fleet_config[y_name]['speed_type'], fleet_config[y_name]['speed_params'])
                yield env.timeout((dist/speed)*60)
                
                # ... Factory Queue Logic (Similar to Leg B) ...
                m_key = "ไหม้" if t_type == 'b' else "สด"
                fac_q_monitor[m_key] += 1
                t_arrival = env.now

                # --- จำลองรถชาวไร่แทรกคิว (External Traffic) ---
                if np.random.uniform(0, 100) < ext_prob:
                    # สุ่มจำนวนรถที่ขวางอยู่ และคำนวณเวลาที่ต้องรอ
                    n_ext = np.random.randint(n_ext_min, n_ext_max + 1)
                    wait_ext_duration = sum([get_stochastic_val(unld_dist, unld_p) for _ in range(n_ext)])
                    yield env.timeout(wait_ext_duration)
                    
                    current_day = int(env.now // 1440) + 1
                    tod_min = env.now % 1440
                    kpi['ext_wait'].append({'Hour': f"D{current_day} {int(tod_min//60):02d}:00", 'Tractor': tid_name, 'Duration': wait_ext_duration})
                
                # Queueing
                target_res = slots_b if t_type == 'b' else slots_f
                if target_res:
                    with target_res.request() as req:
                        yield req
                        
                        # Record Wait Time (Fix: Include Direct Trucks in metrics)
                        q_duration = env.now - t_arrival
                        kpi['total_fac_wait'] += q_duration
                        kpi['fac_wait_count'] += 1
                        
                        # Unloading
                        yield env.timeout(get_stochastic_val(unld_dist, unld_p))
                
                kpi['factory_delivered'] += trailer_cap
                fac_q_monitor[m_key] -= 1
                kpi['trips'][y_name] += 1
                
                # Return empty to Yard
                yield env.timeout((dist/speed)*60)
                yield final_y[y_name]['empty'].put(tail)
                
                add_util(t_util, tid_name, env.now - start_work)
                log_cycle('Tractor', tid_name, y_name, env.now - start_work)
                kpi['total_dist_head'] += dist * 2
                kpi['total_dist_tail'] += dist * 2
            else:
                yield env.timeout(5)

    def monitor_proc():
        while env.now <= sim_duration:
            # Format Day + Time
            current_day = int(env.now // 1440) + 1
            tod_min = env.now % 1440
            h_str = f"D{current_day} {int(tod_min//60):02d}:00"

            for y in yards_list:
                kpi["history"].append({"Hour": h_str, "Location": y, "Value": len(final_y[y]['empty'].items), "Type": "1. หางว่าง"})
                kpi["history"].append({"Hour": h_str, "Location": y, "Value": len(final_y[y]['full_f'].items) + len(final_y[y]['full_b'].items), "Type": "2. หางหนักค้างลาน"})
                kpi["queue_len"].append({"Hour": h_str, "Location": y, "Count": len(final_y[y]['wait_f'].items) + len(final_y[y]['wait_b'].items)})
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
        elif y == "ศูนย์โนนสัง":
            for i in range(fleet_config[y]['n_t']): env.process(tractor_direct(y, i+1, loc_params[y]['dist']))
        else:
            for i in range(fleet_config[y]['n_t']): env.process(tractor_leg_a(y, i+1, loc_params[y]['dist']))
        def farmer(yn):
            gp = loc_params[yn]['gen_params']
            y_s_h = loc_params[yn]['start_min'] // 60
            y_e_h = loc_params[yn]['end_min'] // 60
            
            for day in range(num_days):
                # Wait for yard opening
                tod = env.now % 1440
                if tod < loc_params[yn]['start_min']:
                    yield env.timeout(loc_params[yn]['start_min'] - tod)

                # Determine Plan for the Day
                daily_fresh, daily_burnt = [], []
                
                if gp['use_random']:
                    # Generate Random Plan
                    active_hours = [h for h in range(y_s_h, y_e_h + 1) if gp['start'] <= h <= gp['end']]
                    if not active_hours:
                        daily_fresh = [0.0] * len(loc_params[yn]['fresh'])
                        daily_burnt = [0.0] * len(loc_params[yn]['burnt'])
                    else:
                        # Identify Indices
                        idx_p1 = [i for i, h in enumerate(active_hours) if gp['peaks'][0][0] <= h <= gp['peaks'][0][1]]
                        idx_p2 = [i for i, h in enumerate(active_hours) if gp['peaks'][1][0] <= h <= gp['peaks'][1][1] and i not in idx_p1]
                        idx_norm = [i for i, h in enumerate(active_hours) if i not in idx_p1 and i not in idx_p2]
                        
                        # Shares
                        s1 = np.random.uniform(gp['peak_shares'][0][0], gp['peak_shares'][0][1]) / 100.0
                        s2 = np.random.uniform(gp['peak_shares'][1][0], gp['peak_shares'][1][1]) / 100.0
                        if s1 + s2 > 1.0:
                            scale = s1 + s2
                            s1 /= scale
                            s2 /= scale
                        s_rest = 1.0 - s1 - s2
                        
                        # สุ่มยอดรายวันจากช่วง Min-Max
                        daily_target_f = np.random.uniform(gp['min_f'], gp['max_f'])
                        daily_target_b = gp['total_b']
                        
                        wf_base = np.random.rand(len(active_hours))
                        wb_base = np.random.rand(len(active_hours))
                        
                        d_f = np.zeros(len(active_hours))
                        d_b = np.zeros(len(active_hours))
                        
                        def distribute(total, indices, w_base):
                            if not indices: return
                            sw = w_base[indices]
                            if sw.sum() == 0: sw[:] = 1
                            return (sw / sw.sum()) * total

                        if idx_p1: d_f[idx_p1] = distribute(daily_target_f * s1, idx_p1, wf_base)
                        if idx_p2: d_f[idx_p2] = distribute(daily_target_f * s2, idx_p2, wf_base)
                        if idx_norm: d_f[idx_norm] = distribute(daily_target_f * s_rest, idx_norm, wf_base)

                        if idx_p1: d_b[idx_p1] = distribute(daily_target_b * s1, idx_p1, wb_base)
                        if idx_p2: d_b[idx_p2] = distribute(daily_target_b * s2, idx_p2, wb_base)
                        if idx_norm: d_b[idx_norm] = distribute(daily_target_b * s_rest, idx_norm, wb_base)
                        
                        # Map back to full hours
                        full_h = range(y_s_h, y_e_h + 1)
                        daily_fresh = [d_f[active_hours.index(h)] if h in active_hours else 0.0 for h in full_h]
                        daily_burnt = [d_b[active_hours.index(h)] if h in active_hours else 0.0 for h in full_h]
                else:
                    # Use Static Plan
                    daily_fresh = loc_params[yn]['fresh']
                    daily_burnt = loc_params[yn]['burnt']

                for f, b in zip(daily_fresh, daily_burnt):
                    if f + b > 0:
                        tod_min = env.now % 1440
                        h_str = f"D{day+1} {int(tod_min//60):02d}:00"
                        kpi["incoming_cane"].append({"Hour": h_str, "Location": yn, "Amount": f + b})
                        
                        # Convert Plan (Tons) to Trucks
                        f_trucks, b_trucks = 0, 0
                        
                        # Fresh trucks
                        rem_f = f
                        while rem_f > 0:
                            cap = get_stochastic_val(loc_params[yn]['truck_cap_type'], loc_params[yn]['truck_cap_params'])
                            load = min(rem_f, cap)
                            yield final_y[yn]['wait_f'].put(load)
                            rem_f -= load
                            f_trucks += 1
                            
                        # Burnt trucks
                        rem_b = b
                        while rem_b > 0:
                            cap = get_stochastic_val(loc_params[yn]['truck_cap_type'], loc_params[yn]['truck_cap_params'])
                            load = min(rem_b, cap)
                            yield final_y[yn]['wait_b'].put(load)
                            rem_b -= load
                            b_trucks += 1
                            
                        kpi["incoming_trucks"].append({"Hour": h_str, "Location": yn, "Count": f_trucks + b_trucks})

                    yield env.timeout(60)
                # จบแผนวันนั้นแล้ว ให้รอจนขึ้นวันใหม่ (Sleep overnight)
                day_gap = 1440 - (len(daily_fresh) * 60)
                if day_gap > 0: yield env.timeout(day_gap)
        env.process(farmer(y))

    env.run(until=sim_duration + 1)
    
    # --- Calculate End-of-Sim Metrics ---
    stuck_tons = 0
    leftover_tons = 0
    
    # 1. Stuck in Factory Queue (On the road / Queueing / Unloading)
    stuck_tons += (fac_q_monitor["สด"] + fac_q_monitor["ไหม้"]) * trailer_cap
    
    # 2. Stuck at Hub (Full trailers waiting at Hub)
    stuck_tons += (len(hub_full_f.items) + len(hub_full_b.items)) * trailer_cap
    
    for y in yards_list:
        if y != hub_name: stuck_tons += (len(final_y[y]['full_f'].items) + len(final_y[y]['full_b'].items)) * trailer_cap
        leftover_tons += sum(final_y[y]['wait_f'].items) + sum(final_y[y]['wait_b'].items)
        
    kpi['stuck_tons'] = stuck_tons
    kpi['leftover_tons'] = leftover_tons
    
    return kpi, final_y, t_util, l_util, sim_duration

# ==========================================
# 5. EXECUTION & RESULTS
# ==========================================
if 'sim_results' not in st.session_state:
    st.session_state['sim_results'] = None

if st.button("🚀 รันการจำลองระบบ", use_container_width=True, type="primary"):
    with st.spinner("🔄 กำลังประมวลผล..."):
        data, final_y, t_utils, l_utils, total_time = run_ksl_simulation()
        st.session_state['sim_results'] = {'data': data, 't_utils': t_utils, 'l_utils': l_utils, 'total_time': total_time}

if st.session_state['sim_results']:
    results = st.session_state['sim_results']
    data, t_utils, l_utils, total_time = results['data'], results['t_utils'], results['l_utils'], results['total_time']
    df_h = pd.DataFrame(data['history'])
    
    # --- SUMMARY METRICS CALCULATION ---
    total_trips = sum(data['trips'].values())
    
    # FIX: ใช้ยอดรวมจากข้อมูลจริงที่เกิดขึ้นใน Sim (incoming_cane) เพื่อความแม่นยำ 100%
    total_plan = sum(d['Amount'] for d in data['incoming_cane'])
            
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
    
    # --- Save Data for AI Context ---
    data['total_workload'] = total_workload
    st.session_state['ai_sim_data'] = {'data': data}
    
    # 3. ส่งไม่สำเร็จ (Stuck)
    not_delivered = data['stuck_tons']
    
    # 2. คีบไม่หมด (Leftover) - ให้เป็นยอดคงเหลือเพื่อดุลบัญชี (รวมคิวรอ + ค้างในหาง + กำลังคีบ)
    not_loaded = max(0, total_workload - total_delivered - not_delivered)

    st.markdown("### 🏆 สรุปผลการดำเนินงาน (Executive Summary)")
    
    # Row 1: Cargo Metrics
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("1. ภาระงานรวม", f"{total_workload:,.0f} ตัน", help="แผนอ้อยใหม่ + สต็อกเก่า")
    mc2.metric("2. ส่งโรงงานสำเร็จ", f"{total_delivered:,.0f} ตัน")
    mc3.metric("3. ส่งไม่สำเร็จ (Stuck)", f"{not_delivered:,.0f} ตัน", help="ค้างบนรถ/ค้าง Hub/รอคิว")
    mc4.metric("4. คีบไม่หมด (Leftover)", f"{not_loaded:,.0f} ตัน", help="ค้างในไร่/ลาน (คีบไม่ทัน)")
    mc5.metric("🌙 คีบหลังปิดลาน (Overtime)", f"{data['overtime_tons']:,.0f} ตัน", help="ปริมาณอ้อยที่รถคีบทำงานนอกเวลาเปิดรับ (แสดงถึงการเคลียร์ของ)")
    
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
    tab_mon, tab_fleet, tab_cycle = st.tabs(["📈 Monitoring (สถานะระบบ)", "⚙️ Fleet & Trips (รถและเที่ยววิ่ง)", "⏱️ Cycle Analysis (วิเคราะห์รอบเวลา)"])
    
    with tab_mon:
        st.caption("กราฟแสดงสถานะของระบบตามช่วงเวลา (Time Series Monitor)")
        
        # 1. Incoming Trucks
        if data['incoming_trucks']:
            df_it = pd.DataFrame(data['incoming_trucks'])
            st.plotly_chart(px.line(df_it, x="Hour", y="Count", color="Location", markers=True, title="🚜 จำนวนรถขนอ้อยขาเข้า (Incoming Trucks)"), use_container_width=True)

        # 2. Queue Length
        if data['queue_len']:
            df_q = pd.DataFrame(data['queue_len'])
            st.plotly_chart(px.line(df_q, x="Hour", y="Count", color="Location", markers=True, title="⏳ คิวรถขนอ้อยรอคีบ (Queue Length Realtime)"), use_container_width=True)

        # 3. Realtime Loading Rate (Moved here)
        if data['loading_events']:
            df_load_events = pd.DataFrame(data['loading_events'])
            
            # จัดกลุ่มข้อมูลเป็นรายชั่วโมง (Time Binning)
            df_load_events['Day'] = df_load_events['time_min'].apply(lambda x: int(x // 1440) + 1)
            df_load_events['Hour_of_Day'] = df_load_events['time_min'].apply(lambda x: int(((start_min + x) % 1440) // 60))
            df_load_events['Time_Str'] = df_load_events.apply(lambda r: f"D{int(r['Day'])} {int(r['Hour_of_Day']):02d}:00", axis=1)
            
            # รวมปริมาณตันอ้อยในแต่ละชั่วโมง (Group by Hour & Yard)
            df_realtime = df_load_events.groupby(['Time_Str', 'yard'])['tons'].sum().reset_index(name='ปริมาณอ้อย (ตัน)')
            df_realtime = df_realtime.sort_values('Time_Str')
            
            st.plotly_chart(px.line(df_realtime, x='Time_Str', y='ปริมาณอ้อย (ตัน)', color='yard', markers=True, 
                                    title='ปริมาณการคีบอ้อยรายชั่วโมง (Realtime Tonnage)'), key="realtime_loading_chart",
                             use_container_width=True)

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

    with tab_cycle:
        st.caption("วิเคราะห์สถิติเวลาการทำงานต่อรอบ (Cycle Time Statistics)")
        if data['cycle_logs']:
            df_cycle = pd.DataFrame(data['cycle_logs'])
            
            st.subheader("📊 ตารางสถิติรอบเวลา (แยกตามทรัพยากร)")
            # Group by Type, Yard, Name
            stats = df_cycle.groupby(['Type', 'Yard', 'Name'])['Duration'].agg(['count', 'mean', 'std', 'min', 'max']).reset_index()
            stats.columns = ['Resource Type', 'Yard', 'Resource Name', 'Count (Trips/Loads)', 'Avg (min)', 'Std Dev', 'Min (min)', 'Max (min)']
            
            st.dataframe(stats.style.format({
                'Avg (min)': '{:.2f}', 'Std Dev': '{:.2f}', 'Min (min)': '{:.2f}', 'Max (min)': '{:.2f}'
            }), use_container_width=True)
            
            st.subheader("📦 การกระจายตัวของเวลา (Boxplot)")
            st.plotly_chart(px.box(df_cycle, x="Yard", y="Duration", color="Type", points="all", 
                                   title="การกระจายตัวของรอบเวลาการทำงาน (Tractors & Loaders)"), use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลรอบเวลาการทำงาน (โปรดรันการจำลองก่อน)")

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
