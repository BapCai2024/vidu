import streamlit as st
import google.generativeai as genai
import pandas as pd
from io import BytesIO
import docx
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import time
import json
import re
from pypdf import PdfReader

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Hệ Thống Ra Đề Thi V6", layout="wide", page_icon="📝")
st.title("📝 Hệ Thống Ra Đề Thi Tiểu Học (Chuẩn Form Nhà Trường)")
st.caption("✅ Sách: Kết nối / Chân trời / Cánh diều / Cùng khám phá. ✅ Header chuẩn. ✅ Format câu hỏi chi tiết.")
st.markdown("---")

# ==============================================================================
# 1. API ENGINE
# ==============================================================================
def generate_content_strict(api_key, prompt, response_json=False):
    genai.configure(api_key=api_key)
    try: all_models = list(genai.list_models())
    except: return None, "Lỗi kết nối API."
    
    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    if not valid_models: return None, "Không tìm thấy model hỗ trợ."
    
    # Ưu tiên Flash cho JSON (nhanh), Pro cho viết đề (thông minh)
    priority = [m for m in valid_models if 'flash' in m] if response_json else [m for m in valid_models if 'pro' in m]
    priority += valid_models # Thêm các model còn lại
    
    for m in priority:
        try:
            model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"} if response_json else {})
            res = model.generate_content(prompt)
            return res.text, m
        except: time.sleep(1); continue
    return None, "Server quá tải (429). Vui lòng thử lại sau 30s."

# ==============================================================================
# 2. XỬ LÝ FILE
# ==============================================================================
def process_file(file):
    try:
        if file.name.endswith('.xlsx'):
            df = pd.read_excel(file, header=None)
            h_idx = 0
            for i, r in df.iterrows():
                if any(k in str(s).lower() for k in ['chủ đề', 'mạch']): h_idx = i; break
            return df.iloc[h_idx:].ffill().to_string()
        elif file.name.endswith('.pdf'):
            return "".join([p.extract_text() for p in PdfReader(file).pages])
        elif file.name.endswith('.docx'):
            doc = docx.Document(file); txt = ""
            for t in doc.tables:
                for r in t.rows: txt += " | ".join([c.text.strip() for c in r.cells]) + "\n"
            return txt
    except: return ""

# ==============================================================================
# 3. LOGIC AI (PROMPT ĐƯỢC TINH CHỈNH KHẮT KHE)
# ==============================================================================

def step1_analyze(txt, api_key):
    prompt = f"""
    Phân tích ma trận sau thành JSON (Giữ nguyên thứ tự dòng):
    {txt[:25000]}
    OUTPUT JSON:
    [
      {{
        "order": 1,
        "topic": "...", 
        "yccd": "...",
        "type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Mức 1 / Mức 2 / Mức 3",
        "points": "0.5" (Nếu có),
        "label": "Câu 1" (Nếu có)
      }}
    ]
    Chỉ lấy dòng có yêu cầu ra câu hỏi.
    """
    return generate_content_strict(api_key, prompt, response_json=True)

def step2_create(json_data, subject, school_name, exam_name, time_limit, api_key):
    prompt = f"""
    Bạn là chuyên gia ra đề thi Tiểu học. Hãy soạn nội dung đề thi môn {subject} dựa trên JSON sau:
    {json_data}

    1. NGUỒN DỮ LIỆU: 
       - Sách: Kết nối tri thức, Chân trời sáng tạo, Cánh diều, Cùng khám phá (Tin học).
       - Nội dung phải chính xác, khoa học.

    2. FORMAT CÂU HỎI (BẮT BUỘC):
       - Cấu trúc tiêu đề câu: **Câu [X]:** ([Điểm] điểm) [Mức độ] [Nội dung câu hỏi]
       - Ví dụ: **Câu 1:** (0,5 điểm) [Mức 1] Thiết bị nào sau đây...
       
       - Dạng "TN 4 lựa chọn": 4 đáp án A. B. C. D. xuống dòng.
       - Dạng "Đúng/Sai": Tạo các ý a, b, c, d.
       - Dạng "Điền khuyết": Dùng dấu chấm "......" (ít nhất 6 chấm).
       - Dạng "Nối cột": 
         + Thiết kế nội dung để hiển thị thành 2 cột.
         + Cột A (1,2,3,4) - Cột B (a,b,c,d).
    
    3. YÊU CẦU KHÁC:
       - Logic câu hỏi: Phải chặt chẽ, không đánh đố sai mức độ.
       - KHÔNG viết lời chào, KHÔNG viết tiêu đề (Tiêu đề sẽ do code tự sinh).
       - Bắt đầu ngay vào Câu 1.
       - Cuối cùng là phần ĐÁP ÁN CHI TIẾT.
    """
    return generate_content_strict(api_key, prompt, response_json=False)

# ==============================================================================
# 4. XUẤT WORD (HEADER CHUẨN + FORMAT ĐẸP)
# ==============================================================================
def set_cell_border(cell, **kwargs):
    """Hàm hỗ trợ kẻ khung cho bảng (dùng cho câu nối cột nếu cần)"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for border_name in kwargs:
        xml = f'<w:{border_name} w:val="single" w:sz="4" w:space="0" w:color="auto" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        tcPr.append(OxmlElement(xml))

def create_docx_final(text, school_name, exam_name, subject, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # 1. TẠO HEADER (QUỐC HIỆU + TÊN TRƯỜNG)
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Cm(7)  # Cột trái
    table.columns[1].width = Cm(9)  # Cột phải
    
    # Ô trái: Trường
    cell_left = table.cell(0, 0)
    p_left = cell_left.paragraphs[0]
    p_left.add_run(f"{school_name.upper()}\n").bold = True
    p_left.add_run("ĐỀ KIỂM TRA ĐỊNH KỲ").bold = False
    p_left.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Ô phải: Quốc hiệu (Có thể bỏ nếu chỉ cần tên kì thi)
    cell_right = table.cell(0, 1)
    p_right = cell_right.paragraphs[0]
    p_right.add_run(f"{exam_name.upper()}\n").bold = True
    p_right.add_run(f"Môn: {subject}\n").bold = True
    p_right.add_run(f"Thời gian: {time_limit} phút").italic = True
    p_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("\n") # Khoảng cách

    # 2. XỬ LÝ NỘI DUNG CHÍNH
    lines = text.split('\n')
    for line in lines:
        clean = line.strip()
        if not clean: continue
        
        # Xử lý tiêu đề phần Đáp án
        if "ĐÁP ÁN" in clean.upper() or "HƯỚNG DẪN CHẤM" in clean.upper():
            doc.add_page_break() # Sang trang mới chấm cho dễ
            p = doc.add_paragraph(clean)
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(14)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue

        p = doc.add_paragraph(clean)
        
        # In đậm "Câu X:" và "[Mức độ]"
        # Regex tìm: Câu 1: (0.5 điểm) [Mức 1]
        if re.match(r'^Câu\s+\d+:', clean):
            p.runs[0].bold = True
            p.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        
        # Format đặc biệt cho câu Nối cột (Nếu AI tạo dạng Cột A | Cột B)
        if "Cột A" in clean and "Cột B" in clean:
            p.runs[0].bold = True
            # (Có thể nâng cấp thêm code tạo bảng thực sự ở đây nếu cần thiết)

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 5. UI (TỐI GIẢN HÓA)
# ==============================================================================
with st.sidebar:
    st.header("Cấu hình"); api_key = st.text_input("API Key", type="password")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Thông tin Đề thi")
    uploaded_file = st.file_uploader("Upload Ma Trận", type=['xlsx', 'docx', 'pdf'])
    
    with st.expander("Thông tin chi tiết (Bắt buộc)", expanded=True):
        school_name = st.text_input("Tên trường", value="TRƯỜNG TH KIM ĐỒNG")
        exam_name = st.text_input("Tên kì thi", value="CUỐI HỌC KÌ 1 NĂM HỌC 2024-2025")
        subject = st.text_input("Môn học & Lớp", value="Tin học lớp 3")
        time_limit = st.number_input("Thời gian (phút)", value=35)
    
    if st.button("🚀 TẠO ĐỀ THI NGAY", type="primary"):
        if uploaded_file and api_key:
            # CHỈ HIỆN 1 DÒNG TRẠNG THÁI DUY NHẤT
            with st.spinner("🤖 AI đang phân tích ma trận và soạn đề... (Vui lòng đợi khoảng 30s)"):
                try:
                    # B1: Đọc
                    txt = process_file(uploaded_file)
                    # B2: Phân tích
                    bp, m1 = step1_analyze(txt, api_key)
                    if bp:
                        # B3: Viết đề
                        exam, m2 = step2_create(bp, subject, school_name, exam_name, time_limit, api_key)
                        if exam:
                            st.session_state['result'] = exam
                            st.session_state['meta'] = {'school': school_name, 'exam': exam_name, 'sub': subject, 'time': time_limit}
                            st.success("✅ Đã xong! Xem kết quả bên phải.")
                        else: st.error(f"Lỗi tạo đề: {m2}")
                    else: st.error(f"Lỗi phân tích: {m1}")
                except Exception as e: st.error(f"Lỗi: {e}")
        else: st.warning("Vui lòng nhập Key và upload file.")

with col2:
    st.subheader("2. Xem trước & Tải về")
    if 'result' in st.session_state:
        # Hiển thị
        res_txt = st.text_area("", st.session_state['result'], height=700)
        
        # Tạo file
        meta = st.session_state['meta']
        doc = create_docx_final(res_txt, meta['school'], meta['exam'], meta['sub'], meta['time'])
        
        st.download_button(
            "📥 Tải file Word chuẩn (.docx)", 
            doc, 
            f"De_{meta['sub'].replace(' ','_')}.docx", 
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
            type="primary"
        )
