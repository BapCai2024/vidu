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
st.set_page_config(page_title="V9 - Hệ Thống Ra Đề Thông Minh", layout="wide", page_icon="🎯")
st.title("🎯 Tool Ra Đề V9 (Auto-Detect & Logic Đa Chiều)")
st.caption("✅ Tự động nhận diện Môn/Lớp. ✅ Xử lý 2 tình huống (Có/Không YCCĐ). ✅ Format chuẩn.")
st.markdown("---")

# ==============================================================================
# 1. MODULE XỬ LÝ TEXT & CLEANING
# ==============================================================================
def aggressive_clean(text):
    """Lọc sạch rác, chỉ giữ lại nội dung đề thi"""
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = text.replace('```', '')
    
    # Cắt bỏ phần lời dẫn, chỉ lấy từ "Câu 1" trở đi
    match = re.search(r'(Câu 1[:.]|Câu 01[:.])', text)
    if match:
        return text[match.start():].strip()
    
    # Nếu không thấy Câu 1 (trường hợp hiếm), lọc thủ công các từ khóa AI
    lines = text.split('\n')
    clean_lines = [l for l in lines if not any(x in l.lower() for x in ['tuyệt vời', 'dưới đây', 'json', 'chatgpt'])]
    return "\n".join(clean_lines).strip()

# ==============================================================================
# 2. API ENGINE
# ==============================================================================
def call_ai(api_key, prompt, json_mode=False):
    genai.configure(api_key=api_key)
    try: models = list(genai.list_models())
    except: return None, "Lỗi kết nối API."
    
    valid = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
    if not valid: return None, "Không tìm thấy model."

    # Ưu tiên Flash cho JSON/Detect (nhanh), Pro cho Viết đề (Sâu sắc)
    priority = [m for m in valid if 'flash' in m] if json_mode else [m for m in valid if 'pro' in m]
    priority += valid
    
    for m in priority:
        try:
            model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"} if json_mode else {})
            res = model.generate_content(prompt)
            return res.text, m
        except: time.sleep(1); continue
    return None, "Server Busy."

# ==============================================================================
# 3. AUTO-DETECT SUBJECT (TỰ ĐỘNG NHẬN DIỆN MÔN)
# ==============================================================================
def detect_context(txt, api_key):
    """Đọc file để xác định Môn học và Lớp"""
    prompt = f"""
    Đọc văn bản sau và xác định chính xác Môn học và Lớp học.
    Văn bản: {txt[:2000]}
    
    Trả về JSON duy nhất: {{"subject": "Tên môn", "grade": "Lớp mấy"}}
    Ví dụ: {{"subject": "Khoa học", "grade": "Lớp 4"}}
    """
    res, _ = call_ai(api_key, prompt, json_mode=True)
    try: return json.loads(res)
    except: return {"subject": "Chưa xác định", "grade": ""}

# ==============================================================================
# 4. LOGIC AI CORE
# ==============================================================================

def step1_parse_matrix(txt, api_key):
    prompt = f"""
    Chuyển đổi ma trận đề thi sau thành JSON. Giữ nguyên thứ tự dòng.
    INPUT: {txt[:25000]}
    OUTPUT JSON List:
    [{{
        "order": 1, 
        "topic": "Chủ đề/Bài học", 
        "yccd": "Yêu cầu cần đạt (nếu có)", 
        "type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Mức 1 / Mức 2 / Mức 3", 
        "points": "Số điểm", 
        "label": "Câu 1" (Nếu file gốc ghi rõ)
    }}]
    """
    return call_ai(api_key, prompt, json_mode=True)

def step2_write_exam(json_data, detected_info, api_key):
    subject = detected_info.get('subject', 'Môn học')
    grade = detected_info.get('grade', '')
    
    prompt = f"""
    Bạn là chuyên gia biên soạn đề thi CT2018.
    Nhiệm vụ: Soạn đề thi môn {subject} - {grade}.
    
    DỮ LIỆU MA TRẬN: {json_data}

    HƯỚNG DẪN XỬ LÝ DỮ LIỆU (QUAN TRỌNG):
    1. **TRƯỜNG HỢP A (Có YCCĐ):** Nếu trường "yccd" có nội dung:
       - Hãy dùng YCCĐ làm căn cứ cốt lõi.
       - Từ YCCĐ, hãy viết lại thành câu hỏi trắc nghiệm/tự luận tương ứng.
       - TUYỆT ĐỐI KHÔNG copy nguyên văn YCCĐ vào làm câu hỏi.
       - Ví dụ YCCĐ: "Nhận biết được vật dẫn nhiệt" -> Câu hỏi: "Vật nào sau đây dẫn nhiệt tốt?"
       
    2. **TRƯỜNG HỢP B (Thiếu YCCĐ, chỉ có Chủ đề/Bài học):**
       - BẮT BUỘC tự tìm kiếm kiến thức chuẩn trong chương trình {subject} {grade} (Bộ sách Kết nối/Chân trời/Cánh diều).
       - Tự sáng tạo câu hỏi phù hợp với "topic" và "level" (Mức độ).

    QUY ĐỊNH FORMAT (BẮT BUỘC):
    - **Câu [X]:** ([Điểm] điểm) [Mức độ] [Nội dung câu hỏi...]
    - Trắc nghiệm: 4 đáp án A. B. C. D. xuống dòng.
    - Đúng/Sai: Phải có 4 ý a), b), c), d).
    - Nối cột: Phải có Cột A và Cột B (Nội dung logic).
    - Điền khuyết: Dùng dấu "......".
    
    OUTPUT:
    - Không chào hỏi.
    - Bắt đầu ngay bằng Câu 1.
    - Kết thúc bằng ĐÁP ÁN CHI TIẾT.
    """
    raw_text, m = call_ai(api_key, prompt, json_mode=False)
    if raw_text: return aggressive_clean(raw_text), m
    return None, m

# ==============================================================================
# 5. XUẤT WORD
# ==============================================================================
def create_docx_v9(text, school_name, exam_name, detected_info, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # Header Bảng
    tbl = doc.add_table(rows=1, cols=2)
    tbl.autofit = False
    tbl.columns[0].width = Cm(7); tbl.columns[1].width = Cm(9)
    
    c1 = tbl.cell(0, 0); p1 = c1.paragraphs[0]
    p1.add_run(f"{school_name.upper()}\n").bold = True
    p1.add_run("ĐỀ KIỂM TRA ĐỊNH KỲ").bold = False
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    c2 = tbl.cell(0, 1); p2 = c2.paragraphs[0]
    p2.add_run(f"{exam_name.upper()}\n").bold = True
    p2.add_run(f"Môn: {detected_info['subject']} - {detected_info['grade']}\n").bold = True
    p2.add_run(f"Thời gian làm bài: {time_limit} phút").italic = True
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("\n")

    # Nội dung
    lines = text.split('\n')
    for line in lines:
        clean = line.strip()
        if not clean: continue
        
        if "ĐÁP ÁN" in clean.upper() or "HƯỚNG DẪN CHẤM" in clean.upper():
            doc.add_page_break()
            p = doc.add_paragraph(clean)
            p.runs[0].bold = True; p.runs[0].font.size = Pt(14)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue

        p = doc.add_paragraph(clean)
        
        # Format tiêu đề câu
        match = re.match(r'^(Câu\s+\d+:.*?\])', clean)
        if match:
            title_part = match.group(1)
            content_part = clean[len(title_part):]
            p.clear()
            run = p.add_run(title_part)
            run.bold = True; run.font.color.rgb = RGBColor(0, 0, 0)
            p.add_run(content_part)
        elif re.match(r'^(Câu|Bài)\s+\d+[:.]', clean):
            p.runs[0].bold = True

        if "Cột A" in clean and "Cột B" in clean: p.runs[0].bold = True
        if re.match(r'^[a-dA-D]\)', clean) or re.match(r'^[a-d]\.', clean):
            p.paragraph_format.left_indent = Cm(1)

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 6. GIAO DIỆN CHÍNH
# ==============================================================================
with st.sidebar:
    st.header("🔧 Cấu hình")
    api_key = st.text_input("Nhập API Key", type="password")
    
col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Input File")
    uploaded_file = st.file_uploader("Upload Ma trận", type=['xlsx', 'docx', 'pdf'])
    
    # Ẩn bớt các input thủ công, để AI tự lo
    with st.expander("Cài đặt Header Đề thi", expanded=True):
        school_name = st.text_input("Tên trường", "TRƯỜNG TH KIM ĐỒNG")
        exam_name = st.text_input("Kỳ thi", "CUỐI HỌC KỲ 1")
        time_limit = st.number_input("Thời gian (phút)", value=35)
    
    if st.button("🚀 TẠO ĐỀ NGAY (AUTO-DETECT)", type="primary"):
        if uploaded_file and api_key:
            with st.status("Đang xử lý...", expanded=True) as status:
                try:
                    # B1: Đọc file
                    status.write("📂 Đọc nội dung file...")
                    if uploaded_file.name.endswith('.xlsx'):
                        df = pd.read_excel(uploaded_file, header=None)
                        h_idx = 0
                        for i, r in df.iterrows():
                            if any(k in str(s).lower() for k in ['chủ đề', 'mạch']): h_idx = i; break
                        txt = df.iloc[h_idx:].ffill().to_string()
                    elif uploaded_file.name.endswith('.pdf'):
                        txt = "".join([p.extract_text() for p in PdfReader(uploaded_file).pages])
                    else:
                        doc = docx.Document(uploaded_file); txt = ""
                        for t in doc.tables:
                            for r in t.rows: txt += " | ".join([c.text.strip() for c in r.cells]) + "\n"

                    # B2: Auto-Detect Subject
                    status.write("🔍 Đang nhận diện Môn & Lớp...")
                    det_info = detect_context(txt, api_key)
                    st.info(f"Đã phát hiện: {det_info.get('subject')} - {det_info.get('grade')}")

                    # B3: Parse Matrix
                    status.write("🤖 Phân tích cấu trúc ma trận...")
                    bp, m1 = step1_parse_matrix(txt, api_key)

                    # B4: Write Exam
                    if bp:
                        status.write("✍️ Đang soạn câu hỏi (Logic: YCCĐ + Sách GK)...")
                        exam, m2 = step2_write_exam(bp, det_info, api_key)
                        
                        if exam:
                            st.session_state['result'] = exam
                            st.session_state['meta'] = {
                                'school': school_name, 'exam': exam_name, 
                                'det': det_info, 'time': time_limit
                            }
                            status.update(label="Thành công!", state="complete", expanded=False)
                        else: st.error(f"Lỗi tạo đề: {m2}")
                    else: st.error(f"Lỗi phân tích JSON: {m1}")

                except Exception as e: st.error(f"Lỗi: {e}")
        else: st.warning("Thiếu File hoặc Key.")

with col2:
    st.subheader("2. Kết quả")
    if 'result' in st.session_state:
        res = st.session_state['result']
        st.text_area("Xem trước (Đã lọc sạch):", res, height=700)
        
        meta = st.session_state['meta']
        doc = create_docx_v9(res, meta['school'], meta['exam'], meta['det'], meta['time'])
        
        st.download_button(
            label="📥 Tải file Word (.docx)",
            data=doc,
            file_name=f"De_{meta['det']['subject']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary"
        )
