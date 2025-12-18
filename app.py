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
st.set_page_config(page_title="V11 - Hệ Thống Ra Đề Final", layout="wide", page_icon="🏆")
st.title("🏆 Hệ Thống Ra Đề Thi V11 (Auto-Detect & Robust JSON)")
st.caption("✅ Fix lỗi JSON V10. ✅ Tự động nhận diện môn. ✅ Logic 2 luồng dữ liệu.")
st.markdown("---")

# ==============================================================================
# 1. CORE LOGIC: TRÍCH XUẤT JSON AN TOÀN (FIX LỖI CRASH V10)
# ==============================================================================
def extract_json_robust(text):
    """
    Hàm này dùng Regex để 'mổ' lấy đoạn JSON nằm giữa đống văn bản hỗn độn.
    Giải quyết triệt để lỗi AI trả về kèm lời dẫn hoặc markdown.
    """
    try:
        # 1. Tìm đoạn nằm giữa [ và ] đầu tiên và cuối cùng
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        return None
    except:
        return None

def clean_ai_response(text):
    """Lọc sạch mọi thứ rác, chỉ giữ lại nội dung câu hỏi"""
    # Xóa code block
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL).replace('```', '')
    # Xóa các dòng metadata nếu AI lỡ in ra (Chủ đề: ..., Bài học: ...)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        lower = line.lower()
        if any(x in lower for x in ['chủ đề:', 'bài học:', 'yccđ:', 'json', 'tuyệt vời']):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()

# ==============================================================================
# 2. API ENGINE
# ==============================================================================
def call_ai(api_key, prompt, model_type='flash'):
    genai.configure(api_key=api_key)
    try: models = list(genai.list_models())
    except: return None
    
    # Chọn model
    keyword = 'flash' if model_type == 'flash' else 'pro'
    valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
    priority = [m for m in valid_models if keyword in m] + valid_models
    
    for m in priority:
        try:
            # Nếu là flash (JSON) thì force json mode, nếu là pro (Content) thì text mode
            config = {"response_mime_type": "application/json"} if model_type == 'flash' else {}
            model = genai.GenerativeModel(m, generation_config=config)
            res = model.generate_content(prompt)
            return res.text
        except: time.sleep(1); continue
    return None

# ==============================================================================
# 3. AUTO-DETECT MODULE (TỰ ĐỘNG NHẬN DIỆN MÔN)
# ==============================================================================
def detect_file_context(txt, api_key):
    prompt = f"""
    Đọc văn bản đầu vào và xác định Môn học và Lớp học.
    Văn bản: {txt[:3000]}
    
    Trả về JSON duy nhất: {{"subject": "Tên môn", "grade": "Lớp mấy"}}
    Ví dụ: {{"subject": "Khoa học", "grade": "Lớp 4"}}
    """
    res = call_ai(api_key, prompt, 'flash')
    data = extract_json_robust(res) if res else None
    
    # Fallback nếu AI trả về Object thay vì List, hoặc lỗi
    if isinstance(data, dict): return data
    if isinstance(data, list) and len(data) > 0: return data[0]
    return {"subject": "Môn học chung", "grade": "Tiểu học"}

# ==============================================================================
# 4. QUY TRÌNH XỬ LÝ LOGIC (CHIA ĐỂ TRỊ)
# ==============================================================================

def step1_parse_matrix(txt, api_key):
    """Phân tích ma trận ra JSON List (Giữ nguyên thứ tự)"""
    prompt = f"""
    Phân tích ma trận đề thi sau thành JSON List. Giữ nguyên thứ tự dòng.
    Chỉ lấy những dòng có yêu cầu ra câu hỏi.
    
    INPUT: {txt[:25000]}
    
    OUTPUT JSON:
    [
      {{
        "topic": "Tên chủ đề/bài học", 
        "yccd": "Nội dung yêu cầu cần đạt (Copy nguyên văn)", 
        "type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Mức 1 / Mức 2 / Mức 3", 
        "points": "0.5", 
        "label": "Câu 1" (Nếu có)
      }}
    ]
    """
    res = call_ai(api_key, prompt, 'flash')
    return extract_json_robust(res)

def step2_generate_single_question(item, context, api_key):
    """
    Sinh 1 câu hỏi duy nhất.
    Logic IF/ELSE quan trọng để xử lý nguồn dữ liệu.
    """
    subject = context.get('subject', 'Môn học')
    grade = context.get('grade', '')
    
    # LOGIC 2 TRƯỜNG HỢP DỮ LIỆU
    source_prompt = ""
    if item.get('yccd') and len(str(item['yccd'])) > 10:
        # Case A: Có YCCĐ -> Bám sát YCCĐ
        source_prompt = f"""
        - NGUỒN DỮ LIỆU: Dựa hoàn toàn vào YCCĐ: "{item['yccd']}".
        - NHIỆM VỤ: Hãy chuyển hóa YCCĐ này thành một câu hỏi kiểm tra đánh giá.
        - LƯU Ý: KHÔNG copy nguyên văn YCCĐ làm câu hỏi.
        """
    else:
        # Case B: Không có YCCĐ -> Mở rộng tra cứu sách
        source_prompt = f"""
        - NGUỒN DỮ LIỆU: Chủ đề này chưa có YCCĐ cụ thể. Bạn hãy tra cứu kiến thức chuẩn trong SGK {subject} {grade} (Bộ Kết nối/Chân trời/Cánh diều) liên quan đến chủ đề "{item['topic']}".
        - NHIỆM VỤ: Sáng tạo câu hỏi phù hợp với chủ đề và mức độ "{item['level']}".
        """

    prompt = f"""
    Bạn là chuyên gia ra đề thi CT2018. Hãy viết NỘI DUNG cho 1 câu hỏi môn {subject}.
    
    THÔNG TIN:
    - Dạng bài: {item['type']}
    - {source_prompt}

    YÊU CẦU FORMAT (Chỉ trả về nội dung, không tiêu đề):
    1. Trắc nghiệm: Câu dẫn + 4 đáp án A. B. C. D. (Mỗi đáp án 1 dòng).
    2. Đúng/Sai: Câu dẫn + 4 ý a), b), c), d).
    3. Nối cột: Ghi rõ nội dung Cột A và Cột B (Có nội dung khớp nhau).
    4. Điền khuyết: Đoạn văn có dấu "......".
    
    OUTPUT: Chỉ viết nội dung câu hỏi. Không chào hỏi.
    """
    res = call_ai(api_key, prompt, 'pro') # Dùng Pro để viết cho hay
    return clean_ai_response(res) if res else "Lỗi tạo nội dung."

# ==============================================================================
# 5. XỬ LÝ FILE ĐẦU VÀO
# ==============================================================================
def read_input_file(file):
    try:
        if file.name.endswith('.xlsx'):
            df = pd.read_excel(file, header=None)
            # Tìm header chứa từ khóa
            h_idx = 0
            for i, r in df.iterrows():
                if any(k in str(s).lower() for k in ['chủ đề', 'mạch', 'nội dung']): h_idx = i; break
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
# 6. XUẤT WORD (PYTHON CONTROLLED HEADER)
# ==============================================================================
def create_docx_v11(questions, school, exam, context, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # Header Bảng
    tbl = doc.add_table(rows=1, cols=2)
    tbl.autofit = False
    tbl.columns[0].width = Cm(7); tbl.columns[1].width = Cm(9)
    
    c1 = tbl.cell(0, 0); p1 = c1.paragraphs[0]
    p1.add_run(f"{school.upper()}\n").bold = True
    p1.add_run("ĐỀ KIỂM TRA ĐỊNH KỲ").bold = False
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    c2 = tbl.cell(0, 1); p2 = c2.paragraphs[0]
    p2.add_run(f"{exam.upper()}\n").bold = True
    p2.add_run(f"Môn: {context['subject']} - {context['grade']}\n").bold = True
    p2.add_run(f"Thời gian: {time_limit} phút").italic = True
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("\n")

    # Nội dung câu hỏi
    for idx, q in enumerate(questions):
        # Python tự tạo Header câu hỏi -> Chuẩn 100%
        label = q.get('label') if q.get('label') else f"Câu {idx+1}"
        points = q.get('points', '1')
        level = q.get('level', 'Biết')
        
        p = doc.add_paragraph()
        run = p.add_run(f"{label}: ({points} điểm) [{level}] ")
        run.bold = True; run.font.color.rgb = RGBColor(0, 0, 0)
        
        # Nội dung từ AI
        lines = q['content'].split('\n')
        for line in lines:
            clean = line.strip()
            if not clean: continue
            
            p_content = doc.add_paragraph(clean)
            
            # Format đặc biệt
            if "Cột A" in clean or "Cột B" in clean: p_content.runs[0].bold = True
            if re.match(r'^[a-dA-D]\)', clean) or re.match(r'^[a-d]\.', clean):
                p_content.paragraph_format.left_indent = Cm(1)

    # Đáp án
    doc.add_page_break()
    p_end = doc.add_paragraph("ĐÁP ÁN VÀ HƯỚNG DẪN CHẤM")
    p_end.runs[0].bold = True; p_end.runs[0].font.size = Pt(14)
    p_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("(Giáo viên tự điền chi tiết)")

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 7. GIAO DIỆN CHÍNH
# ==============================================================================
with st.sidebar:
    st.header("🔧 Cấu hình"); api_key = st.text_input("API Key", type="password")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Input")
    uploaded_file = st.file_uploader("Upload Ma trận", type=['xlsx', 'docx', 'pdf'])
    
    with st.expander("Thông tin chung", expanded=True):
        school = st.text_input("Trường", "TRƯỜNG TH KIM ĐỒNG")
        exam = st.text_input("Kỳ thi", "CUỐI HỌC KỲ 1")
        time_limit = st.number_input("Thời gian (phút)", 35)

    if st.button("🚀 TẠO ĐỀ (V11 FINAL)", type="primary"):
        if uploaded_file and api_key:
            status = st.status("Đang khởi động hệ thống...", expanded=True)
            try:
                # B1: Đọc file
                status.write("📂 Đọc file đầu vào...")
                txt = read_input_file(uploaded_file)
                
                # B2: Auto-Detect
                status.write("🔍 Đang nhận diện Môn & Lớp...")
                context = detect_file_context(txt, api_key)
                st.info(f"Phát hiện: {context.get('subject')} - {context.get('grade')}")
                
                # B3: Parse Matrix (Robust JSON)
                status.write("🤖 Phân tích cấu trúc ma trận...")
                blueprint = step1_parse_matrix(txt, api_key)
                
                if blueprint and isinstance(blueprint, list):
                    status.write(f"✅ Tìm thấy {len(blueprint)} câu hỏi. Bắt đầu viết chi tiết...")
                    
                    # B4: Generate Row-by-Row
                    final_qs = []
                    bar = st.progress(0)
                    
                    for i, item in enumerate(blueprint):
                        status.write(f"✍️ Đang viết câu {i+1}/{len(blueprint)}...")
                        content = step2_generate_single_question(item, context, api_key)
                        
                        final_qs.append({
                            'label': item.get('label'), 
                            'points': item.get('points'), 
                            'level': item.get('level'), 
                            'content': content
                        })
                        bar.progress((i+1)/len(blueprint))
                    
                    st.session_state['final_qs'] = final_qs
                    st.session_state['meta'] = {'school': school, 'exam': exam, 'ctx': context, 'time': time_limit}
                    status.update(label="Hoàn tất!", state="complete", expanded=False)
                else:
                    status.update(label="Lỗi cấu trúc Ma trận (JSON Fail)", state="error")
                    st.error("AI không trích xuất được ma trận. File quá phức tạp hoặc API lỗi.")
            except Exception as e: st.error(f"Lỗi hệ thống: {e}")
        else: st.warning("Thiếu File/Key")

with col2:
    st.subheader("2. Kết quả")
    if 'final_qs' in st.session_state:
        # Preview
        txt_prev = ""
        for q in st.session_state['final_qs']:
            l = q.get('label', 'Câu')
            txt_prev += f"{l}: ({q.get('points')}đ) [{q.get('level')}]\n{q['content']}\n\n"
        
        st.text_area("Preview:", txt_prev, height=700)
        
        # Download
        meta = st.session_state['meta']
        doc = create_docx_v11(st.session_state['final_qs'], meta['school'], meta['exam'], meta['ctx'], meta['time'])
        st.download_button("📥 Tải File Word (.docx)", doc, f"De_thi.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary")
