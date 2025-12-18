import streamlit as st
import google.generativeai as genai
import pandas as pd
from io import BytesIO
import docx
from docx.shared import Pt
import time
import json
from pypdf import PdfReader

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Hệ Thống Ra Đề (Core 7h.py + New AI)", layout="wide", page_icon="🏫")

st.title("🏫 Tool Ra Đề Thi: Core 7h.py & Xử Lý Đa Năng")
st.markdown("---")

# --- 1. HÀM API CHÍNH XÁC TỪ FILE 7h.py (CÓ CẬP NHẬT JSON) ---
def generate_content_with_rotation_7h(api_key, prompt, response_json=False):
    """
    Hàm này lấy logic từ file 7h.py: Tự động list_models để tìm model khả dụng.
    Đã thêm tham số response_json để hỗ trợ phân tích ma trận.
    """
    genai.configure(api_key=api_key)
    try:
        all_models = list(genai.list_models())
    except Exception as e:
        return f"Lỗi kết nối hoặc Key sai: {e}", None

    # Lọc model hỗ trợ generateContent
    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    if not valid_models:
        return "Lỗi: Key đúng nhưng không có model nào hỗ trợ generateContent.", None

    # Sắp xếp ưu tiên như 7h.py: Flash -> Pro -> Khác
    priority_order = []
    for m in valid_models:
        if 'flash' in m.lower() and '1.5' in m: priority_order.append(m)
    for m in valid_models:
        if 'pro' in m.lower() and '1.5' in m and m not in priority_order: priority_order.append(m)
    for m in valid_models:
        if m not in priority_order: priority_order.append(m)

    last_error = ""
    
    # Thử từng model trong danh sách ưu tiên
    for model_name in priority_order:
        try:
            # Cấu hình JSON nếu cần
            config = {"response_mime_type": "application/json"} if response_json else {}
            
            model = genai.GenerativeModel(model_name, generation_config=config)
            response = model.generate_content(prompt)
            return response.text, model_name
        except Exception as e:
            last_error = str(e)
            # Nếu gặp lỗi 429 (Resource Exhausted), nghỉ 2s rồi thử model khác
            if "429" in str(e) or "ResourceExhausted" in str(e):
                time.sleep(2)
            continue

    return None, f"Hết model khả dụng. Lỗi cuối: {last_error}"

# --- 2. BỘ XỬ LÝ FILE (PRE-PROCESSORS) ---

def process_excel_to_text(file):
    """Xử lý Excel: Fill merged cells để AI không bị nhầm"""
    try:
        df = pd.read_excel(file, header=None)
        # Tìm header
        header_idx = 0
        for idx, row in df.iterrows():
            if any('chủ đề' in str(s).lower() or 'mạch' in str(s).lower() for s in row):
                header_idx = idx
                break
        
        df_clean = df.iloc[header_idx:].reset_index(drop=True)
        # Forward Fill để lấp đầy các ô bị merge (quan trọng cho file Book1.xlsx)
        df_clean = df_clean.ffill()
        return df_clean.to_string()
    except Exception as e:
        return f"Lỗi Excel: {e}"

def process_pdf_to_text(file):
    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages: text += page.extract_text() + "\n"
        return text
    except: return "Lỗi PDF"

def process_docx_to_text(file):
    try:
        doc = docx.Document(file)
        text = ""
        for table in doc.tables:
            for row in table.rows:
                text += " | ".join([c.text.strip() for c in row.cells]) + "\n"
        return text
    except: return "Lỗi Word"

# --- 3. AI PHÂN TÍCH & VIẾT ĐỀ ---

def analyze_matrix(file_text, api_key):
    prompt = f"""
    Phân tích văn bản ma trận đề thi sau thành cấu trúc JSON.
    Văn bản:
    {file_text[:15000]}
    
    Yêu cầu Output JSON List:
    [
      {{
        "topic": "Tên chủ đề",
        "yccd": "Yêu cầu cần đạt",
        "questions": [
           {{"type": "TN nhiều lựa chọn/Tự luận...", "level": "Biết/Hiểu/Vận dụng", "count": "Số lượng câu (VD: 1 câu hoặc Câu 5)"}}
        ]
      }}
    ]
    Chỉ lấy dòng có yêu cầu ra câu hỏi.
    """
    res, model = generate_content_with_rotation_7h(api_key, prompt, response_json=True)
    return res, model

def create_exam(blueprint, subject, api_key):
    prompt = f"""
    Bạn là giáo viên tiểu học. Soạn đề thi môn {subject} theo cấu trúc này:
    {blueprint}
    
    Yêu cầu:
    1. Đầy đủ số lượng câu hỏi theo cấu trúc.
    2. Chia 2 phần: I. Trắc nghiệm, II. Tự luận.
    3. Có Đáp án và Hướng dẫn chấm chi tiết ở cuối.
    4. Trình bày rõ ràng.
    """
    res, model = generate_content_with_rotation_7h(api_key, prompt, response_json=False)
    return res, model

# --- 4. HÀM WORD ---
def create_word(text):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font; font.name = 'Times New Roman'; font.size = Pt(13)
    for line in text.split('\n'):
        if line.strip():
            p = doc.add_paragraph(line.strip())
            if any(x in line.lower() for x in ["câu", "phần", "đáp án", "đề thi"]): p.runs[0].bold = True
    bio = BytesIO(); doc.save(bio); return bio

# --- GIAO DIỆN ---
with st.sidebar:
    st.header("Cấu hình")
    api_key = st.text_input("Gemini API Key", type="password")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Input")
    uploaded_file = st.file_uploader("Upload Ma Trận", type=['xlsx', 'pdf', 'docx'])
    sub_name = st.text_input("Tên môn (VD: Tin học lớp 3)")
    
    if uploaded_file and api_key and sub_name:
        # Nút bấm gộp cả 2 bước cho nhanh (hoặc tách ra tùy bạn)
        if st.button("🚀 Phân tích & Tạo đề ngay", type="primary"):
            status = st.status("Đang chạy...", expanded=True)
            
            # B1: Đọc file
            status.write("📂 Đang đọc nội dung file...")
            if uploaded_file.name.endswith('.xlsx'): f_text = process_excel_to_text(uploaded_file)
            elif uploaded_file.name.endswith('.pdf'): f_text = process_pdf_to_text(uploaded_file)
            else: f_text = process_docx_to_text(uploaded_file)
            
            # B2: Phân tích
            status.write("🤖 Đang phân tích ma trận (Core 7h.py)...")
            blueprint, m1 = analyze_matrix(f_text, api_key)
            
            if blueprint:
                st.session_state['blueprint'] = blueprint
                status.write(f"✅ Phân tích xong (Model: {m1})")
                
                # B3: Viết đề
                status.write("✍️ Đang soạn đề thi...")
                exam_txt, m2 = create_exam(blueprint, sub_name, api_key)
                
                if exam_txt:
                    st.session_state['result'] = exam_txt
                    status.update(label=f"Hoàn thành! (Model: {m2})", state="complete")
                else:
                    status.update(label="Lỗi tạo đề", state="error")
                    st.error(m2)
            else:
                status.update(label="Lỗi phân tích", state="error")
                st.error(m1)

with col2:
    st.subheader("2. Kết quả")
    tab1, tab2 = st.tabs(["📝 Đề thi", "🔍 Cấu trúc"])
    
    with tab2:
        if 'blueprint' in st.session_state:
            st.json(st.session_state['blueprint'])
            
    with tab1:
        if 'result' in st.session_state:
            final_txt = st.text_area("Nội dung:", st.session_state['result'], height=600)
            doc_file = create_word(final_txt)
            st.download_button("📥 Tải Word", doc_file, f"De_{sub_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary")
