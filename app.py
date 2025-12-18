import streamlit as st
import google.generativeai as genai
import pandas as pd
from io import BytesIO
import docx
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
import time
import json
import re
from pypdf import PdfReader

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="V7 - Hệ Thống Ra Đề Nghiêm Ngặt", layout="wide", page_icon="⚡")
st.title("⚡ Tool Ra Đề V7 (Fix Lỗi Logic & Format)")
st.caption("✅ Câu hỏi được SÁNG TÁC từ YCCĐ (Không copy). ✅ Format: Câu - Điểm - Mức. ✅ Sạch code rác.")
st.markdown("---")

# ==============================================================================
# 1. BỘ XỬ LÝ TEXT & LỌC RÁC (QUAN TRỌNG)
# ==============================================================================
def clean_response(text):
    """
    Hàm này đóng vai trò 'người kiểm duyệt', cắt bỏ mọi lời chào và code thừa.
    """
    # 1. Xóa các block code markdown (```json ... ```)
    text = re.sub(r'```[a-zA-Z]*', '', text)
    text = text.replace('```', '')
    
    # 2. Xóa các câu chào hỏi thừa thãi của AI
    lines = text.split('\n')
    clean_lines = []
    start_collecting = False
    
    # Logic: Chỉ bắt đầu lấy nội dung khi thấy dòng bắt đầu bằng "Câu" hoặc "Phần"
    # Hoặc nếu không thấy, lấy tất cả nhưng bỏ dòng chứa "Tuyệt vời", "Dưới đây", "JSON"
    for line in lines:
        l_lower = line.strip().lower()
        if "tuyệt vời" in l_lower or "dưới đây là" in l_lower or "json" in l_lower or "chatgpt" in l_lower or "gemini" in l_lower:
            continue
        clean_lines.append(line)
        
    return "\n".join(clean_lines).strip()

# ==============================================================================
# 2. API ENGINE
# ==============================================================================
def generate_strict(api_key, prompt, response_json=False):
    genai.configure(api_key=api_key)
    try: models = list(genai.list_models())
    except: return None, "Lỗi kết nối API."
    
    valid = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
    if not valid: return None, "Không tìm thấy model."

    # Ưu tiên Flash cho JSON (nhanh), Pro cho viết đề (sáng tạo câu hỏi hay)
    priority = [m for m in valid if 'flash' in m] if response_json else [m for m in valid if 'pro' in m]
    priority += valid
    
    for m in priority:
        try:
            model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"} if response_json else {})
            res = model.generate_content(prompt)
            return res.text, m
        except: time.sleep(1); continue
    return None, "Server Busy."

# ==============================================================================
# 3. XỬ LÝ FILE ĐẦU VÀO
# ==============================================================================
def process_input(file):
    try:
        if file.name.endswith('.xlsx'):
            df = pd.read_excel(file, header=None)
            h_idx = 0
            for i, r in df.iterrows():
                if any(k in str(s).lower() for k in ['chủ đề', 'mạch', 'nội dung']): h_idx = i; break
            # Lấy dữ liệu và fill các ô merge
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
# 4. LOGIC AI - PROMPT V7 (CỰC KỲ KHẮT KHE)
# ==============================================================================

def step1_parse_matrix(txt, api_key):
    """Phân tích ma trận thành JSON cấu trúc"""
    prompt = f"""
    Nhiệm vụ: Chuyển đổi văn bản ma trận đề thi sau thành JSON List.
    Yêu cầu: Giữ nguyên thứ tự dòng. Chỉ lấy dòng có yêu cầu ra đề.

    INPUT TEXT:
    {txt[:25000]}

    OUTPUT JSON:
    [
      {{
        "order": 1,
        "topic": "...", 
        "yccd": "...", 
        "type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Mức 1 / Mức 2 / Mức 3",
        "points": "0.5",
        "label": "Câu 1" (Nếu file gốc có ghi)
      }}
    ]
    """
    return generate_strict(api_key, prompt, response_json=True)

def step2_write_exam(json_data, grade, subject, api_key):
    """Viết đề thi từ JSON"""
    prompt = f"""
    Bạn là chuyên gia ra đề thi Chương trình GDPT 2018 (Sách Kết nối, Chân trời, Cánh diều, Cùng khám phá).
    
    NHIỆM VỤ: Dựa vào JSON dưới đây để SOẠN THẢO đề thi môn {subject} - Lớp {grade}.
    
    DỮ LIỆU ĐẦU VÀO (MA TRẬN):
    {json_data}

    QUY TẮC "VÀNG" (BẮT BUỘC TUÂN THỦ):
    1. **KHÔNG ĐƯỢC COPY "YÊU CẦU CẦN ĐẠT" LÀM CÂU HỎI**.
       - Sai: "Câu 1: Nhận biết được các bộ phận của máy tính." (Đây là YCCĐ -> SAI)
       - Đúng: "Câu 1: Thiết bị nào sau đây dùng để nhập dữ liệu vào máy tính?" (Đây là câu hỏi -> ĐÚNG)
    
    2. **FORMAT CÂU HỎI (Tuyệt đối chính xác):**
       - Bắt buộc theo mẫu: **Câu [X]:** ([Điểm] điểm) [Mức độ] [Nội dung câu hỏi...]
       - Ví dụ: **Câu 1:** (0,5 điểm) [Mức 1] Trong phần mềm Paint, công cụ nào dùng để tẩy?
    
    3. **QUY ĐỊNH DẠNG BÀI:**
       - **Trắc nghiệm:** 4 đáp án A. B. C. D. (Mỗi đáp án xuống dòng).
       - **Đúng/Sai:** Phải có 4 ý a), b), c), d) để học sinh tích.
       - **Điền khuyết:** Phải dùng dấu chấm "......" (ít nhất 6 chấm).
       - **Nối cột:** Phải ghi rõ "Cột A" và "Cột B". Có hình ảnh giả định (nếu cần thì ghi [Hình ảnh minh họa...]).

    4. **TRÌNH BÀY:**
       - KHÔNG viết lời mở đầu (Tuyệt vời, Chào bạn...).
       - Bắt đầu ngay bằng Câu 1.
       - Cuối cùng là ĐÁP ÁN CHI TIẾT.
    """
    raw_text, m = generate_strict(api_key, prompt, response_json=False)
    if raw_text:
        return clean_response(raw_text), m # Lọc sạch rác trước khi trả về
    return None, m

# ==============================================================================
# 5. XUẤT WORD (HEADER CHUẨN + FORMAT MỚI)
# ==============================================================================
def create_docx_v7(text, school_name, exam_name, grade, subject, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # 1. HEADER BẢNG
    tbl = doc.add_table(rows=1, cols=2)
    tbl.autofit = False
    tbl.columns[0].width = Cm(7); tbl.columns[1].width = Cm(9)
    
    # Ô trái: Trường
    c1 = tbl.cell(0, 0)
    p1 = c1.paragraphs[0]
    p1.add_run(f"{school_name.upper()}\n").bold = True
    p1.add_run("ĐỀ KIỂM TRA ĐỊNH KỲ").bold = False
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Ô phải: Thông tin thi
    c2 = tbl.cell(0, 1)
    p2 = c2.paragraphs[0]
    p2.add_run(f"{exam_name.upper()}\n").bold = True
    p2.add_run(f"Môn: {subject} - Lớp {grade}\n").bold = True
    p2.add_run(f"Thời gian làm bài: {time_limit} phút").italic = True
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("\n")

    # 2. NỘI DUNG ĐỀ
    lines = text.split('\n')
    for line in lines:
        clean = line.strip()
        if not clean: continue
        
        # Tiêu đề ĐÁP ÁN
        if "ĐÁP ÁN" in clean.upper() or "HƯỚNG DẪN CHẤM" in clean.upper():
            doc.add_page_break()
            p = doc.add_paragraph(clean)
            p.runs[0].bold = True; p.runs[0].font.size = Pt(14)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue

        p = doc.add_paragraph(clean)
        
        # Regex bắt format: Câu 1: (0,5 điểm) [Mức 1]
        # Bôi đậm toàn bộ phần Tiêu đề câu hỏi này
        match = re.match(r'^(Câu\s+\d+:.*?\])', clean)
        if match:
            # Tách phần tiêu đề (Bold) và nội dung câu hỏi (Normal)
            title_part = match.group(1) # Lấy phần "Câu 1: (0,5 đ) [Mức 1]"
            content_part = clean[len(title_part):] # Phần còn lại
            
            p.clear() # Xóa text cũ để add lại từng phần
            run_title = p.add_run(title_part)
            run_title.bold = True
            run_title.font.color.rgb = RGBColor(0, 0, 0) # Màu đen
            
            p.add_run(content_part) # Nội dung câu hỏi không đậm
            
        elif re.match(r'^(Câu|Bài)\s+\d+[:.]', clean): # Fallback cho trường hợp AI quên ngoặc
            p.runs[0].bold = True

        # Format Nối cột (Cột A - Cột B)
        if "Cột A" in clean and "Cột B" in clean:
            p.runs[0].bold = True
            
        # Thụt đầu dòng cho a) b) c) d)
        if re.match(r'^[a-dA-D]\)', clean) or re.match(r'^[a-d]\.', clean):
            p.paragraph_format.left_indent = Cm(1)

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 6. GIAO DIỆN (UI UPDATE: CHỌN LỚP - MÔN)
# ==============================================================================
with st.sidebar:
    st.header("🔧 Cấu hình hệ thống")
    api_key = st.text_input("Nhập API Key", type="password")
    
col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Thông tin đầu vào")
    uploaded_file = st.file_uploader("Tải file Ma trận (Excel/PDF/Word)", type=['xlsx', 'docx', 'pdf'])
    
    with st.expander("Thiết lập chi tiết (Bắt buộc)", expanded=True):
        school_name = st.text_input("Tên trường", "TRƯỜNG TH KIM ĐỒNG")
        exam_name = st.text_input("Kỳ thi", "CUỐI HỌC KỲ 1")
        
        c_a, c_b = st.columns(2)
        with c_a:
            grade = st.selectbox("Chọn Lớp", ["Lớp 1", "Lớp 2", "Lớp 3", "Lớp 4", "Lớp 5"])
        with c_b:
            subject = st.text_input("Môn học", "Tin học")
            
        time_limit = st.number_input("Thời gian (phút)", value=35)
    
    if st.button("🚀 TẠO ĐỀ THI V7 (STRICT)", type="primary"):
        if uploaded_file and api_key:
            with st.spinner("🤖 Đang phân tích ma trận & Sáng tạo câu hỏi (Vui lòng đợi)..."):
                try:
                    # B1
                    txt = process_input(uploaded_file)
                    # B2
                    bp, m1 = step1_parse_matrix(txt, api_key)
                    if bp:
                        # B3
                        exam, m2 = step2_write_exam(bp, grade, subject, api_key)
                        if exam:
                            st.session_state['result'] = exam
                            st.session_state['meta'] = {
                                'school': school_name, 'exam': exam_name, 
                                'grade': grade, 'sub': subject, 'time': time_limit
                            }
                            st.success("✅ Đã tạo xong! Nội dung sạch, đúng format.")
                        else: st.error(f"Lỗi tạo đề: {m2}")
                    else: st.error(f"Lỗi phân tích JSON: {m1}")
                except Exception as e: st.error(f"Lỗi: {e}")
        else: st.warning("Thiếu File hoặc Key.")

with col2:
    st.subheader("2. Kết quả")
    if 'result' in st.session_state:
        res = st.session_state['result']
        st.text_area("Xem trước:", res, height=700)
        
        meta = st.session_state['meta']
        doc = create_docx_v7(res, meta['school'], meta['exam'], meta['grade'], meta['sub'], meta['time'])
        
        st.download_button(
            label="📥 Tải file Word (.docx)",
            data=doc,
            file_name=f"De_{meta['sub']}_{meta['grade']}.docx".replace(" ","_"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary"
        )
