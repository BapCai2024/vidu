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
st.set_page_config(page_title="V10 - Hệ Thống Ra Đề Hoàn Thiện", layout="wide", page_icon="💎")
st.title("💎 Tool Ra Đề V10 (Cơ chế từng câu - Chính xác 100%)")
st.caption("✅ Giữ nguyên cấu trúc V9. ✅ Fix lỗi lạc đề. ✅ Format do Python kiểm soát.")
st.markdown("---")

# ==============================================================================
# 1. CÁC HÀM XỬ LÝ TEXT & FILE (GIỮ NGUYÊN TỪ V9)
# ==============================================================================
def clean_text_final(text):
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL).replace('```', '')
    # Xóa các dòng thừa nếu AI lỡ in ra
    lines = text.split('\n')
    clean = [l for l in lines if not any(x in l.lower() for x in ['tuyệt vời', 'dưới đây', 'json', 'chủ đề:', 'bài học:'])]
    return "\n".join(clean).strip()

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
# 2. API ENGINE
# ==============================================================================
def call_ai_fast(api_key, prompt):
    """Dùng model Flash cho JSON (Nhanh)"""
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
        return model.generate_content(prompt).text
    except: return None

def call_ai_smart(api_key, prompt):
    """Dùng model Pro cho nội dung câu hỏi (Chính xác)"""
    genai.configure(api_key=api_key)
    try:
        # Thử Pro trước
        model = genai.GenerativeModel('gemini-1.5-pro')
        return model.generate_content(prompt).text
    except:
        try:
            time.sleep(1)
            model = genai.GenerativeModel('gemini-1.5-flash') # Fallback
            return model.generate_content(prompt).text
        except: return None

# ==============================================================================
# 3. LOGIC MỚI: CHIA ĐỂ TRỊ (LOOP TỪNG CÂU)
# ==============================================================================

def step1_parse_matrix(txt, api_key):
    """Phân tích ma trận ra JSON List"""
    prompt = f"""
    Phân tích văn bản ma trận đề thi sau thành JSON List. 
    Yêu cầu: Giữ nguyên thứ tự dòng. Chỉ lấy dòng có yêu cầu ra câu hỏi (Số lượng > 0).
    
    INPUT: {txt[:25000]}
    
    OUTPUT FORMAT:
    [
      {{
        "topic": "Chủ đề/Bài học", 
        "yccd": "Yêu cầu cần đạt (nếu có, nếu không thì để trống)", 
        "type": "TN 4 lựa chọn / Đúng Sai / Nối cột / Điền khuyết / Tự luận",
        "level": "Mức 1 / Mức 2 / Mức 3", 
        "points": "0.5", 
        "label": "Câu 1" (Nếu file gốc ghi rõ)
      }}
    ]
    """
    res = call_ai_fast(api_key, prompt)
    if res: return json.loads(res)
    return None

def generate_single_question(item, subject, grade, api_key):
    """Hàm sinh 1 câu hỏi duy nhất dựa trên 1 dòng ma trận"""
    
    # Logic kiểm tra nguồn dữ liệu (Case A vs Case B)
    source_instruction = ""
    if item.get('yccd') and len(item['yccd']) > 5:
        source_instruction = f"Dựa cốt lõi vào YCCĐ này để ra đề: '{item['yccd']}'. KHÔNG copy yccd làm câu hỏi."
    else:
        source_instruction = f"Chủ đề này không có YCCĐ cụ thể. Hãy tự tra cứu kiến thức chuẩn trong SGK {subject} {grade} (Bộ Kết nối/Chân trời/Cánh diều) về chủ đề '{item['topic']}' để ra đề."

    prompt = f"""
    Bạn là chuyên gia ra đề thi CT2018.
    Nhiệm vụ: Viết DUY NHẤT 1 câu hỏi cho môn {subject} - {grade}.
    
    THÔNG TIN ĐẦU VÀO:
    - Chủ đề: {item.get('topic')}
    - Dạng bài: {item.get('type')}
    - Mức độ: {item.get('level')}
    - {source_instruction}

    YÊU CẦU FORMAT (Chỉ trả về nội dung câu hỏi, KHÔNG ghi lại 'Câu 1' hay 'Chủ đề'):
    1. Trắc nghiệm: Câu dẫn + 4 đáp án A. B. C. D. (Xuống dòng).
    2. Đúng/Sai: Câu dẫn + 4 ý a), b), c), d).
    3. Nối cột: Phải ghi rõ nội dung Cột A và Cột B.
    4. Điền khuyết: Đoạn văn có dấu "......".
    
    Lưu ý: Ngôn ngữ phù hợp học sinh tiểu học. Logic chặt chẽ.
    """
    res = call_ai_smart(api_key, prompt)
    return clean_text_final(res) if res else "Lỗi tạo câu hỏi."

# ==============================================================================
# 4. XUẤT WORD (LOGIC GHÉP HEADER CỦA PYTHON VÀ NỘI DUNG CỦA AI)
# ==============================================================================
def create_docx_v10(final_questions, school_name, exam_name, subject, grade, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # 1. Header Bảng (Giữ nguyên từ V9)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.autofit = False
    tbl.columns[0].width = Cm(7); tbl.columns[1].width = Cm(9)
    
    c1 = tbl.cell(0, 0); p1 = c1.paragraphs[0]
    p1.add_run(f"{school_name.upper()}\n").bold = True
    p1.add_run("ĐỀ KIỂM TRA ĐỊNH KỲ").bold = False
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    c2 = tbl.cell(0, 1); p2 = c2.paragraphs[0]
    p2.add_run(f"{exam_name.upper()}\n").bold = True
    p2.add_run(f"Môn: {subject} - {grade}\n").bold = True
    p2.add_run(f"Thời gian: {time_limit} phút").italic = True
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("\n")

    # 2. Nội dung câu hỏi (Được ghép từ Python)
    for q in final_questions:
        # Header câu hỏi (Do Python tạo -> Chuẩn 100%)
        # Mẫu: Câu 1: (0.5 điểm) [Mức 1]
        p_header = doc.add_paragraph()
        run_h = p_header.add_run(f"{q['label']}: ({q['points']} điểm) [{q['level']}]")
        run_h.bold = True
        run_h.font.color.rgb = RGBColor(0, 0, 0)
        
        # Nội dung câu hỏi (Do AI viết)
        content_lines = q['content'].split('\n')
        for line in content_lines:
            clean = line.strip()
            if not clean: continue
            
            p = doc.add_paragraph(clean)
            
            # Format in đậm Cột A/B
            if "Cột A" in clean or "Cột B" in clean: p.runs[0].bold = True
            # Thụt lề a) b) c) d)
            if re.match(r'^[a-dA-D]\)', clean) or re.match(r'^[a-d]\.', clean):
                p.paragraph_format.left_indent = Cm(1)

    # 3. Đáp án (Tạo trang mới)
    doc.add_page_break()
    p_ans = doc.add_paragraph("ĐÁP ÁN VÀ HƯỚNG DẪN CHẤM")
    p_ans.runs[0].bold = True; p_ans.runs[0].font.size = Pt(14)
    p_ans.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("(Giáo viên tự điền chi tiết dựa trên đề bài trên)")

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 5. GIAO DIỆN CHÍNH
# ==============================================================================
with st.sidebar:
    st.header("🔧 Cấu hình")
    api_key = st.text_input("Nhập API Key", type="password")
    
col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Input File")
    uploaded_file = st.file_uploader("Upload Ma trận", type=['xlsx', 'docx', 'pdf'])
    
    with st.expander("Thông tin Đề thi", expanded=True):
        school_name = st.text_input("Tên trường", "TRƯỜNG TH KIM ĐỒNG")
        exam_name = st.text_input("Kỳ thi", "CUỐI HỌC KỲ 1")
        c1, c2 = st.columns(2)
        with c1: grade = st.selectbox("Lớp", ["Lớp 3", "Lớp 4", "Lớp 5"])
        with c2: subject = st.text_input("Môn học", "Khoa học")
        time_limit = st.number_input("Thời gian (phút)", value=35)
    
    if st.button("🚀 BẮT ĐẦU TẠO (V10)", type="primary"):
        if uploaded_file and api_key:
            status = st.status("Đang khởi động...", expanded=True)
            try:
                # B1: Đọc file
                status.write("📂 Đọc file ma trận...")
                txt = process_file(uploaded_file)
                
                # B2: Phân tích JSON
                status.write("🤖 Phân tích cấu trúc ma trận...")
                blueprint = step1_parse_matrix(txt, api_key)
                
                if blueprint:
                    status.write(f"✅ Tìm thấy {len(blueprint)} câu hỏi. Đang viết chi tiết...")
                    
                    # B3: Loop từng câu (QUAN TRỌNG)
                    final_questions = []
                    progress_bar = st.progress(0)
                    
                    for i, item in enumerate(blueprint):
                        # Cập nhật Label nếu JSON thiếu
                        if 'label' not in item or not item['label']:
                            item['label'] = f"Câu {i+1}"
                        
                        # Gọi AI viết từng câu
                        status.write(f"✍️ Đang viết {item['label']} ({item['type']})...")
                        q_content = generate_single_question(item, subject, grade, api_key)
                        
                        final_questions.append({
                            'label': item['label'],
                            'points': item.get('points', '1'),
                            'level': item.get('level', 'Biết'),
                            'content': q_content
                        })
                        progress_bar.progress((i + 1) / len(blueprint))
                    
                    st.session_state['final_questions'] = final_questions
                    st.session_state['meta'] = {
                        'school': school_name, 'exam': exam_name, 
                        'grade': grade, 'sub': subject, 'time': time_limit
                    }
                    status.update(label="Hoàn tất!", state="complete", expanded=False)
                else: status.update(label="Lỗi phân tích JSON", state="error")

            except Exception as e: st.error(f"Lỗi: {e}")
        else: st.warning("Thiếu File hoặc Key.")

with col2:
    st.subheader("2. Kết quả")
    if 'final_questions' in st.session_state:
        # Hiển thị Preview
        preview_text = ""
        for q in st.session_state['final_questions']:
            preview_text += f"{q['label']}: ({q['points']} điểm) [{q['level']}]\n{q['content']}\n\n"
        
        st.text_area("Xem trước:", preview_text, height=700)
        
        # Tải file
        meta = st.session_state['meta']
        doc = create_docx_v10(st.session_state['final_questions'], meta['school'], meta['exam'], meta['sub'], meta['grade'], meta['time'])
        
        st.download_button(
            label="📥 Tải file Word Chuẩn (.docx)",
            data=doc,
            file_name=f"De_{meta['sub']}_{meta['grade']}.docx".replace(" ","_"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary"
        )
