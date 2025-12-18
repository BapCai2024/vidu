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
st.set_page_config(page_title="V12.1 - Hệ Thống Ra Đề Pro (Fix)", layout="wide", page_icon="🛠️")
st.title("🛠️ Hệ Thống Ra Đề Thi V12.1 (Fixed Reading)")
st.caption("✅ Đã khôi phục khả năng đọc Bảng/Ma trận. ✅ Giữ tính năng tách Đáp án.")
st.markdown("---")

# ==============================================================================
# 1. TOOLKIT: XỬ LÝ JSON & ĐỌC FILE (KHÔI PHỤC TỪ V11)
# ==============================================================================
def extract_json_robust(text):
    """Trích xuất JSON an toàn"""
    try:
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match: return json.loads(match.group(0))
        return None
    except: return None

def read_input_file_robust(file):
    """
    Hàm đọc file mạnh mẽ (Lấy từ V11 sang)
    Đọc được text trong Table của Word -> Quan trọng cho Ma trận
    """
    try:
        if file.name.endswith('.xlsx'):
            df = pd.read_excel(file)
            return df.to_string()
        elif file.name.endswith('.pdf'):
            reader = PdfReader(file)
            return "".join([page.extract_text() for page in reader.pages])
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            full_text = []
            # 1. Đọc đoạn văn thường
            for para in doc.paragraphs:
                full_text.append(para.text)
            # 2. QUAN TRỌNG: Đọc nội dung trong Bảng (Ma trận nằm ở đây)
            for table in doc.tables:
                for row in table.rows:
                    # Nối các cột bằng dấu | để AI hiểu cấu trúc hàng
                    row_data = " | ".join([cell.text.strip() for cell in row.cells])
                    full_text.append(row_data)
            return "\n".join(full_text)
    except Exception as e:
        st.error(f"Lỗi đọc file: {e}")
        return ""

# ==============================================================================
# 2. AI ENGINE (GIỮ NGUYÊN LOGIC V12)
# ==============================================================================
def call_ai_json(api_key, prompt):
    genai.configure(api_key=api_key)
    try:
        # Tăng token để tránh bị cắt giữa chừng
        model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
        res = model.generate_content(prompt)
        return extract_json_robust(res.text)
    except: return None

def step1_parse_matrix(txt, api_key):
    prompt = f"""
    Bạn là chuyên gia khảo thí. Hãy phân tích ma trận đề thi sau thành JSON List.
    Dữ liệu đầu vào là text được trích xuất từ bảng, các cột ngăn cách bởi dấu "|".
    
    INPUT DATA:
    {txt[:25000]}
    
    OUTPUT JSON FORMAT:
    [
      {{
        "topic": "Tên chủ đề/bài học", 
        "yccd": "Yêu cầu cần đạt (nếu có)", 
        "type": "TN" (Trắc nghiệm) | "DS" (Đúng/Sai) | "NC" (Nối cột) | "DK" (Điền khuyết) | "TL" (Tự luận),
        "level": "Biết/Hiểu/Vận dụng", 
        "points": "Số điểm"
      }}
    ]
    """
    return call_ai_json(api_key, prompt)

def step2_generate_question_v12(item, context, api_key, q_index):
    subject = context.get('subject', 'Môn học')
    grade = context.get('grade', '')
    q_type = item.get('type', 'TN')
    
    # Prompt động theo loại câu hỏi
    format_guide = "Trắc nghiệm 4 lựa chọn A,B,C,D"
    if q_type == "DS": format_guide = "Đúng/Sai với 4 ý a,b,c,d"
    elif q_type == "NC": format_guide = "Nối cột A và cột B"
    elif q_type == "DK": format_guide = "Điền từ vào chỗ trống '......'"
    elif q_type == "TL": format_guide = "Tự luận ngắn"

    prompt = f"""
    Soạn câu hỏi thi {subject} {grade}.
    - Chủ đề: {item.get('topic')}
    - Yêu cầu: {item.get('yccd')}
    - Dạng: {q_type} ({format_guide})
    - Mức độ: {item.get('level')}
    
    OUTPUT JSON:
    {{
        "question_content": "Nội dung câu hỏi để in đề (Không kèm đáp án)",
        "answer_key": "Đáp án chi tiết (để in trang đáp án)"
    }}
    """
    return call_ai_json(api_key, prompt)

# ==============================================================================
# 3. WORD EXPORT (V12)
# ==============================================================================
def create_docx_v12(questions, school, exam, context, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # Header
    tbl = doc.add_table(rows=1, cols=2)
    tbl.autofit = False; tbl.columns[0].width = Cm(7); tbl.columns[1].width = Cm(9)
    p1 = tbl.cell(0, 0).paragraphs[0]; p1.add_run(f"{school.upper()}\n").bold = True; p1.add_run("ĐỀ KIỂM TRA").bold = False; p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2 = tbl.cell(0, 1).paragraphs[0]; p2.add_run(f"{exam.upper()}\n").bold = True; p2.add_run(f"Môn: {context['subject']} - {context['grade']}\n").bold = True; p2.add_run(f"Thời gian: {time_limit} phút").italic = True; p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("\n")
    
    # Body
    for idx, q in enumerate(questions):
        p = doc.add_paragraph()
        p.add_run(f"Câu {idx+1}: ({q['points']} điểm) [{q['level']}] ").bold = True
        
        lines = q['content'].split('\n')
        for line in lines:
            if line.strip(): doc.add_paragraph(line.strip())
        doc.add_paragraph("")

    # Footer (Đáp án)
    doc.add_page_break()
    doc.add_paragraph("ĐÁP ÁN VÀ HƯỚNG DẪN CHẤM").alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells; hdr[0].text = 'Câu'; hdr[1].text = 'Đáp án'
    for idx, q in enumerate(questions):
        row = table.add_row().cells
        row[0].text = str(idx+1)
        row[1].text = q.get('answer', '')

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 4. MAIN APP
# ==============================================================================
with st.sidebar:
    st.header("⚙️ V12.1 Config"); api_key = st.text_input("Gemini API Key", type="password")

st.subheader("1. Tải lên Ma trận")
uploaded_file = st.file_uploader("Upload .docx, .xlsx, .pdf", type=['docx', 'xlsx', 'pdf'])

if 'ctx' not in st.session_state: st.session_state['ctx'] = {}

if uploaded_file:
    # 1. Đọc file ngay lập tức
    if 'raw_text' not in st.session_state:
        with st.spinner("Đang đọc file..."):
            st.session_state['raw_text'] = read_input_file_robust(uploaded_file)
            # Debug: In ra độ dài text để biết có đọc được không
            st.caption(f"Đã đọc được: {len(st.session_state['raw_text'])} ký tự.")
    
    # 2. Auto Detect (Chạy 1 lần)
    if not st.session_state['ctx'] and api_key and st.session_state['raw_text']:
        with st.spinner("Đang nhận diện Môn & Lớp..."):
            # Lấy mẫu text đầu để detect
            sample = st.session_state['raw_text'][:3000]
            prompt = f"Tìm Môn học và Lớp trong text này. Trả về JSON {{'subject': '...', 'grade': '...'}}. Text: {sample}"
            res = call_ai_json(api_key, prompt)
            if res: st.session_state['ctx'] = res
            else: st.session_state['ctx'] = {'subject': '', 'grade': ''} # Fallback

    # 3. Giao diện nhập liệu (Luôn hiện để user sửa nếu AI sai)
    c1, c2 = st.columns(2)
    sub = c1.text_input("Môn học", value=st.session_state['ctx'].get('subject', ''))
    gra = c2.text_input("Lớp", value=st.session_state['ctx'].get('grade', ''))
    
    # Cập nhật ngược lại session
    st.session_state['ctx']['subject'] = sub
    st.session_state['ctx']['grade'] = gra
    
    c3, c4, c5 = st.columns(3)
    sch = c3.text_input("Trường", "TRƯỜNG TH...")
    exa = c4.text_input("Kỳ thi", "CUỐI HỌC KỲ...")
    tim = c5.number_input("Phút", 35)

    if st.button("🚀 TẠO ĐỀ NGAY", type="primary"):
        if not api_key: st.error("Thiếu API Key"); st.stop()
        
        st_status = st.status("Đang xử lý...", expanded=True)
        try:
            # B1: Parse
            st_status.write("🛠 Phân tích cấu trúc ma trận...")
            blueprint = step1_parse_matrix(st.session_state['raw_text'], api_key)
            
            if blueprint:
                st_status.write(f"✅ Tìm thấy {len(blueprint)} câu hỏi.")
                bar = st.progress(0)
                final_qs = []
                
                # B2: Loop generate
                for i, item in enumerate(blueprint):
                    st_status.write(f"✍️ Đang viết câu {i+1}: {item.get('topic')}...")
                    res = step2_generate_question_v12(item, st.session_state['ctx'], api_key, i+1)
                    if res:
                        final_qs.append({
                            'points': item.get('points', '1'),
                            'level': item.get('level', ''),
                            'content': res.get('question_content', ''),
                            'answer': res.get('answer_key', '')
                        })
                    bar.progress((i+1)/len(blueprint))
                
                # B3: Export
                st_status.update(label="Hoàn tất!", state="complete", expanded=False)
                doc_file = create_docx_v12(final_qs, sch, exa, st.session_state['ctx'], tim)
                
                st.download_button("📥 Tải File Word (.docx)", doc_file, "De_thi_V12.1.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary")
                
            else:
                st_status.update(label="Lỗi đọc ma trận", state="error")
                st.error("AI không hiểu file này. Hãy kiểm tra lại format ma trận.")
                
        except Exception as e:
            st.error(f"Lỗi: {e}")
