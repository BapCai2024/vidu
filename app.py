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
st.set_page_config(page_title="Ra Đề Thi Chuẩn CT2018 (Final)", layout="wide", page_icon="📚")
st.title("📚 Hệ Thống Ra Đề Thi Tiểu Học (Chuẩn CT GDPT 2018)")
st.caption("✅ Nguồn dữ liệu: Kết nối tri thức / Chân trời sáng tạo / Cánh diều. ✅ Đúng thứ tự ma trận.")
st.markdown("---")

# ==============================================================================
# 1. API ENGINE (ROBUST MODE)
# ==============================================================================
def generate_content_strict(api_key, prompt, response_json=False):
    """
    Hàm gọi AI với chế độ 'Khắt khe'.
    Tự động retry nếu lỗi.
    """
    genai.configure(api_key=api_key)
    try:
        all_models = list(genai.list_models())
    except: return None, "Lỗi kết nối API. Vui lòng kiểm tra Key/Mạng."

    # Lọc model
    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    if not valid_models: return None, "Không tìm thấy model nào hỗ trợ."

    # Ưu tiên model thông minh nhất (Pro) để đảm bảo kiến thức CT2018 chính xác
    priority = []
    if response_json:
        # JSON cần nhanh và tuân thủ format -> Flash
        priority = [m for m in valid_models if 'flash' in m] + valid_models
    else:
        # Nội dung đề cần chính xác sách giáo khoa -> Pro
        priority = [m for m in valid_models if 'pro' in m] + valid_models

    last_err = ""
    for attempt in range(3):
        for m in priority:
            try:
                # Cấu hình safety settings để không bị block nhầm
                model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"} if response_json else {})
                res = model.generate_content(prompt)
                return res.text, m
            except Exception as e:
                last_err = str(e)
                if "429" in last_err: time.sleep(2); continue
                continue
    return None, f"Lỗi khởi tạo nội dung: {last_err}"

# ==============================================================================
# 2. XỬ LÝ FILE (PRE-PROCESSING)
# ==============================================================================
def process_file(uploaded_file):
    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, header=None)
            # Tìm header chứa "Chủ đề" hoặc "Mạch"
            h_idx = 0
            for i, row in df.iterrows():
                if any(k in str(s).lower() for k in ['chủ đề', 'mạch kiến thức', 'nội dung']):
                    h_idx = i; break
            df = df.iloc[h_idx:].reset_index(drop=True)
            df = df.ffill() # Lấp đầy ô merge
            return df.to_string()
            
        elif uploaded_file.name.endswith('.pdf'):
            reader = PdfReader(uploaded_file); txt = ""
            for p in reader.pages: txt += p.extract_text() + "\n"
            return txt
            
        elif uploaded_file.name.endswith('.docx'):
            doc = docx.Document(uploaded_file); txt = ""
            for t in doc.tables:
                for r in t.rows: txt += " | ".join([c.text.strip() for c in r.cells]) + "\n"
            return txt
    except Exception as e: return f"Lỗi đọc file: {e}"
    return ""

# ==============================================================================
# 3. LOGIC AI (CT2018 STRICT MODE)
# ==============================================================================

def step1_analyze_matrix(file_text, api_key):
    """
    Bước 1: Trích xuất danh sách yêu cầu (Blueprint).
    Yêu cầu: Giữ nguyên thứ tự dòng.
    """
    prompt = f"""
    Bạn là trợ lý giáo dục. Nhiệm vụ: Phân tích văn bản ma trận đề thi dưới đây thành JSON.
    
    YÊU CẦU QUAN TRỌNG:
    1. Giữ nguyên thứ tự xuất hiện của các câu hỏi (Dòng nào trước ghi trước).
    2. Chỉ trích xuất những dòng có yêu cầu ra câu hỏi (Số lượng > 0).

    VĂN BẢN MA TRẬN:
    {file_text[:25000]}

    OUTPUT JSON FORMAT (List of Objects):
    [
      {{
        "order": 1,
        "topic": "Tên bài/Chủ đề (VD: Bài 3 - Vật dẫn nhiệt...)",
        "yccd": "Yêu cầu cần đạt (VD: Nêu được ứng dụng...)",
        "type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Mức 1 (Biết) / Mức 2 (Hiểu) / Mức 3 (Vận dụng)",
        "label": "Câu 1" (Nếu file có ghi rõ số câu, nếu không để trống)
      }}
    ]
    """
    res, model = generate_content_strict(api_key, prompt, response_json=True)
    return res, model

def step2_create_exam(blueprint_json, subject_grade, api_key):
    """
    Bước 2: Viết đề thi dựa trên Blueprint.
    Yêu cầu: Kiến thức 3 bộ sách, Format chuẩn.
    """
    prompt = f"""
    Đóng vai: Chuyên gia biên soạn đề thi Tiểu học theo Chương trình GDPT 2018.
    Nhiệm vụ: Soạn đề thi môn {subject_grade} dựa trên cấu trúc JSON sau.

    DỮ LIỆU CẤU TRÚC (BẮT BUỘC TUÂN THỦ THỨ TỰ):
    {blueprint_json}

    NGUỒN DỮ LIỆU (TỐI QUAN TRỌNG):
    Chỉ sử dụng kiến thức, ngữ liệu, thuật ngữ nằm trong 3 bộ sách giáo khoa hiện hành:
    1. Kết nối tri thức với cuộc sống
    2. Chân trời sáng tạo
    3. Cánh diều
    (Tuyệt đối không sử dụng kiến thức cũ trước 2018 hoặc kiến thức trên mạng không chính thống).

    QUY ĐỊNH VỀ DẠNG CÂU HỎI (FORMAT):
    1. "TN 4 lựa chọn": Câu hỏi + 4 đáp án A, B, C, D.
    2. "Đúng/Sai": 
       - Định dạng:
         Câu X: [Đề dẫn]
         a) [Ý 1] ( )
         b) [Ý 2] ( )
         c) [Ý 3] ( )
         d) [Ý 4] ( )
    3. "Nối cột": Tạo 2 cột nội dung tương ứng để học sinh nối.
    4. "Điền khuyết": Một đoạn văn có chỗ trống (.....).

    YÊU CẦU TRÌNH BÀY:
    - Đánh số câu liên tục theo danh sách JSON (Câu 1, Câu 2...).
    - KHÔNG tự ý đảo lộn thứ tự, KHÔNG tự ý gom nhóm (trừ khi ma trận yêu cầu).
    - Cuối cùng là phần: ĐÁP ÁN VÀ HƯỚNG DẪN CHẤM (Chi tiết).
    """
    res, model = generate_content_strict(api_key, prompt, response_json=False)
    return res, model

# ==============================================================================
# 4. XUẤT WORD
# ==============================================================================
def create_docx_final(text):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # Căn lề
    for s in doc.sections:
        s.top_margin = Cm(2); s.bottom_margin = Cm(2)
        s.left_margin = Cm(2.5); s.right_margin = Cm(2)

    lines = text.split('\n')
    for line in lines:
        clean = line.strip()
        if not clean: continue
        
        p = doc.add_paragraph(clean)
        
        # In đậm tiêu đề câu (Câu 1:, Câu 2...)
        if re.match(r'^(Câu|Bài)\s+\d+[:.]', clean):
            p.runs[0].bold = True
            p.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        
        # In đậm các phần lớn
        elif any(x in clean.lower() for x in ["phần", "đáp án", "hướng dẫn", "đề thi"]):
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(14)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
        # Thụt lề cho các ý a), b) của câu đúng sai
        if re.match(r'^[a-d]\)', clean):
            p.paragraph_format.left_indent = Cm(1)

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 5. UI (STREAMLIT)
# ==============================================================================
with st.sidebar:
    st.header("🔑 Cấu hình"); api_key = st.text_input("Gemini API Key", type="password")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Nhập liệu")
    uploaded_file = st.file_uploader("Tải lên Ma trận (Excel/PDF/Word)", type=['xlsx', 'pdf', 'docx'])
    subject = st.text_input("Tên môn & Lớp (VD: Khoa học lớp 4 - Bộ sách Kết nối)")
    
    if st.button("🚀 TẠO ĐỀ THI (Chuẩn CT2018)", type="primary"):
        if not uploaded_file or not api_key:
            st.warning("Thiếu thông tin!")
        else:
            status = st.status("Đang khởi chạy quy trình...", expanded=True)
            
            try:
                # B1: Đọc file
                status.write("📂 Đang đọc nội dung file...")
                txt = process_file(uploaded_file)
                
                # B2: Phân tích cấu trúc
                status.write("🤖 Đang trích xuất ma trận (Giữ nguyên thứ tự)...")
                bp, m1 = step1_analyze_matrix(txt, api_key)
                
                if bp:
                    st.session_state['blueprint'] = bp
                    status.write(f"✅ Đã hiểu cấu trúc (Model: {m1})")
                    
                    # B3: Viết đề
                    status.write("✍️ Đang soạn câu hỏi từ sách giáo khoa (CT2018)...")
                    exam, m2 = step2_create_exam(bp, subject, api_key)
                    
                    if exam:
                        st.session_state['result'] = exam
                        status.update(label="Hoàn tất! Kết quả hiển thị bên phải.", state="complete", expanded=False)
                    else:
                        status.update(label="Lỗi tạo đề", state="error"); st.error(m2)
                else:
                    status.update(label="Lỗi phân tích ma trận", state="error"); st.error(m1)
            except Exception as e:
                status.update(label="Lỗi hệ thống", state="error"); st.error(e)

with col2:
    st.subheader("2. Kết quả")
    tab1, tab2 = st.tabs(["📝 Đề thi", "🔍 Dữ liệu phân tích"])
    
    with tab2:
        if 'blueprint' in st.session_state:
            try: st.json(json.loads(st.session_state['blueprint'].replace("```json","").replace("```","")))
            except: st.text(st.session_state['blueprint'])
            
    with tab1:
        if 'result' in st.session_state:
            # Hiển thị kết quả ra Text Area để người dùng thấy ngay
            res_content = st.session_state['result']
            edited_txt = st.text_area("Xem trước & Chỉnh sửa:", value=res_content, height=700)
            
            # Tạo nút tải về
            doc = create_docx_final(edited_txt)
            st.download_button(
                label="📥 Tải file Word (.docx)",
                data=doc,
                file_name=f"De_{subject.replace(' ','_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary"
            )
        else:
            st.info("Chưa có kết quả. Vui lòng nhấn nút Tạo đề bên trái.")
