import streamlit as st
import google.generativeai as genai
import pandas as pd
from io import BytesIO
import docx
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import time
import json
import re
from pypdf import PdfReader

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Tool Ra Đề Thi (Chuẩn Ma Trận)", layout="wide", page_icon="🏫")
st.title("🏫 Hệ Thống Ra Đề Thi (Bám Sát Thứ Tự Ma Trận)")
st.caption("Fix lỗi: Giữ nguyên thứ tự câu hỏi trong ma trận - Không tự ý gom nhóm.")
st.markdown("---")

# ==============================================================================
# 1. API & MODEL (GIỮ NGUYÊN TỐI ƯU CŨ)
# ==============================================================================
def generate_content_robust(api_key, prompt, response_json=False):
    genai.configure(api_key=api_key)
    try:
        all_models = list(genai.list_models())
    except: return None, "Lỗi kết nối API."
    
    # Ưu tiên Flash cho xử lý JSON (Nhanh), Pro cho viết đề (Thông minh)
    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    if not valid_models: return None, "Không có model phù hợp."
    
    priority = []
    if response_json: priority = [m for m in valid_models if 'flash' in m] + valid_models
    else: priority = [m for m in valid_models if 'pro' in m] + valid_models # Ưu tiên Pro để viết đề khôn hơn
    
    for attempt in range(3):
        for m in priority:
            try:
                model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"} if response_json else {})
                res = model.generate_content(prompt)
                return res.text, m
            except Exception as e:
                if "429" in str(e): time.sleep(2); continue
                continue
    return None, "Lỗi API (Quá tải/Sai Key)"

# ==============================================================================
# 2. XỬ LÝ FILE (GIỮ NGUYÊN)
# ==============================================================================
def process_excel_to_text(file):
    try:
        df = pd.read_excel(file, header=None)
        # Tìm header
        h_idx = 0
        for i, row in df.iterrows():
            if any('chủ đề' in str(s).lower() or 'mạch' in str(s).lower() for s in row): h_idx = i; break
        df = df.iloc[h_idx:].reset_index(drop=True)
        df = df.ffill() # Quan trọng: Lấp đầy ô merge
        return df.to_string()
    except: return "Lỗi Excel"

def process_pdf_to_text(file):
    try:
        reader = PdfReader(file); txt = ""
        for p in reader.pages: txt += p.extract_text() + "\n"
        return txt
    except: return "Lỗi PDF"

def process_docx_to_text(file):
    try:
        doc = docx.Document(file); txt = ""
        for t in doc.tables:
            for r in t.rows: txt += " | ".join([c.text.strip() for c in r.cells]) + "\n"
        return txt
    except: return "Lỗi Word"

# ==============================================================================
# 3. LOGIC AI MỚI (QUAN TRỌNG NHẤT)
# ==============================================================================

def analyze_matrix_step(file_text, api_key):
    """
    Bước 1: Trích xuất danh sách câu hỏi theo đúng thứ tự xuất hiện trong file.
    """
    prompt = f"""
    Phân tích ma trận đề thi sau thành JSON List.
    QUAN TRỌNG: Giữ nguyên thứ tự xuất hiện của các câu hỏi trong văn bản gốc. Không được tự ý sắp xếp lại.
    
    VĂN BẢN MA TRẬN:
    {file_text[:20000]}

    OUTPUT JSON FORMAT:
    [
      {{
        "order": 1, // Số thứ tự dòng trong ma trận
        "topic": "Chủ đề...",
        "yccd": "Yêu cầu cần đạt...",
        "question_type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Biết/Hiểu/Vận dụng",
        "question_label": "Câu 1" // Nếu trong file có ghi rõ là Câu 1, Câu 2...
      }}
    ]
    Chỉ trích xuất những dòng CÓ YÊU CẦU RA CÂU HỎI.
    """
    res, model = generate_content_robust(api_key, prompt, response_json=True)
    return res, model

def create_exam_step(blueprint_json, subject, api_key):
    """
    Bước 2: Viết đề thi - TUÂN THỦ TUYỆT ĐỐI THỨ TỰ TRONG JSON
    """
    prompt = f"""
    Bạn là chuyên gia ra đề thi Tiểu học (CT GDPT 2018).
    Nhiệm vụ: Soạn câu hỏi lần lượt theo danh sách JSON dưới đây.
    
    DỮ LIỆU ĐẦU VÀO (Đã sắp xếp đúng thứ tự ma trận):
    {blueprint_json}

    QUY TẮC VÀNG (BẮT BUỘC TUÂN THỦ):
    1. **KHÔNG ĐƯỢC ĐẢO LỘN THỨ TỰ**: Phần tử đầu tiên trong JSON phải là Câu 1, phần tử thứ 2 là Câu 2. Tuyệt đối không gom nhóm Trắc nghiệm riêng, Tự luận riêng nếu ma trận không yêu cầu.
    2. **ĐÁNH SỐ CÂU**: Nếu JSON có trường "question_label" (VD: Câu 5) thì dùng đúng số đó. Nếu không, hãy đánh số liên tục 1, 2, 3...
    
    QUY ĐỊNH DẠNG CÂU HỎI (FORMAT):
    - **TN 4 lựa chọn**: 1 câu hỏi + 4 đáp án A. B. C. D.
    - **Đúng/Sai**: 
        Câu X: ...
        a) ... ( )
        b) ... ( )
        c) ... ( )
        d) ... ( )
    - **Nối cột**:
        Câu X: Nối cột A với cột B
        Cột A: 1. ..., 2. ...
        Cột B: a. ..., b. ...
    - **Tự luận**: Câu hỏi mở + Hướng dẫn trả lời.

    OUTPUT TRÌNH BÀY:
    - Bắt đầu ngay vào câu hỏi (Không cần chia Phần I, Phần II nếu làm xáo trộn thứ tự).
    - Cuối cùng là phần ĐÁP ÁN CHI TIẾT.
    """
    res, model = generate_content_robust(api_key, prompt, response_json=False)
    return res, model

# ==============================================================================
# 4. XUẤT WORD (UPDATE FORMAT)
# ==============================================================================
def create_word_doc(text):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # Căn lề
    for s in doc.sections:
        s.top_margin = Cm(2); s.bottom_margin = Cm(2)
        s.left_margin = Cm(2.5); s.right_margin = Cm(2)

    for line in text.split('\n'):
        clean = line.strip()
        if not clean: continue
        p = doc.add_paragraph(clean)
        
        # In đậm thông minh
        lower = clean.lower()
        if re.match(r'^(Câu|Bài)\s+\d+[:.]', clean) or "đáp án" in lower or "hướng dẫn chấm" in lower:
            p.runs[0].bold = True
            p.runs[0].font.color.rgb = RGBColor(0, 51, 102) # Màu xanh đậm cho tiêu đề câu
        
        # Format cho dạng Đúng/Sai (a, b, c, d)
        if re.match(r'^[a-d]\)', clean):
            p.paragraph_format.left_indent = Cm(1) # Thụt lề cho các ý con
            
    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 5. GIAO DIỆN
# ==============================================================================
with st.sidebar:
    st.header("Cấu hình"); api_key = st.text_input("API Key", type="password")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Nhập liệu")
    uploaded_file = st.file_uploader("Upload Ma Trận", type=['xlsx', 'pdf', 'docx'])
    subject = st.text_input("Tên môn (VD: Khoa học 4)")
    
    if st.button("🚀 Tạo đề (Giữ nguyên thứ tự)", type="primary"):
        if uploaded_file and api_key:
            status = st.status("Đang xử lý...", expanded=True)
            
            # B1: Đọc file
            status.write("📂 Đọc file...")
            if uploaded_file.name.endswith('.xlsx'): txt = process_excel_to_text(uploaded_file)
            elif uploaded_file.name.endswith('.pdf'): txt = process_pdf_to_text(uploaded_file)
            else: txt = process_docx_to_text(uploaded_file)
            
            # B2: Phân tích
            status.write("🤖 Phân tích thứ tự câu hỏi...")
            bp, m1 = analyze_matrix_step(txt, api_key)
            
            if bp:
                st.session_state['blueprint'] = bp
                status.write(f"✅ Đã hiểu cấu trúc (Model: {m1})")
                
                # B3: Viết đề
                status.write("✍️ Đang soạn đề theo thứ tự ma trận...")
                exam, m2 = create_exam_step(bp, subject, api_key)
                
                if exam:
                    st.session_state['result'] = exam
                    status.update(label="Xong!", state="complete", expanded=False)
                else: st.error(m2)
            else: st.error(m1)

with col2:
    st.subheader("2. Kết quả")
    tab1, tab2 = st.tabs(["📝 Đề thi", "🔍 Cấu trúc JSON"])
    
    with tab2:
        if 'blueprint' in st.session_state:
            try: st.json(json.loads(st.session_state['blueprint'].replace("```json","").replace("```","")))
            except: st.text(st.session_state['blueprint'])
            
    with tab1:
        if 'result' in st.session_state:
            res_txt = st.text_area("Nội dung:", st.session_state['result'], height=600)
            doc = create_word_doc(res_txt)
            st.download_button("📥 Tải Word", doc, f"De_{subject}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary")
