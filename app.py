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
st.set_page_config(page_title="V12 - Hệ Thống Ra Đề Pro", layout="wide", page_icon="🎓")
st.title("🎓 Hệ Thống Ra Đề Thi V12 (Logic Kép & Tách Đáp Án)")
st.caption("✅ Fix lỗi 'thập cẩm'. ✅ Tách riêng đáp án. ✅ Đánh số thứ tự chuẩn.")
st.markdown("---")

# ==============================================================================
# 1. TOOLKIT: XỬ LÝ JSON & TEXT (NÂNG CẤP)
# ==============================================================================
def extract_json_robust(text):
    """Trích xuất JSON an toàn từ phản hồi của AI"""
    try:
        # Tìm đoạn JSON nằm giữa { và } hoặc [ và ]
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except:
        return None

def clean_text(text):
    """Làm sạch văn bản hiển thị"""
    if not text: return ""
    # Xóa các thẻ markdown thừa
    text = text.replace('**', '').replace('##', '').strip()
    return text

# ==============================================================================
# 2. AI ENGINE & LOGIC V12 (DYNAMIC PROMPTING)
# ==============================================================================
def call_ai_json(api_key, prompt):
    """Hàm gọi AI chuyên dụng trả về JSON"""
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
        res = model.generate_content(prompt)
        return extract_json_robust(res.text)
    except Exception as e:
        return None

def step1_parse_matrix(txt, api_key):
    """Phân tích ma trận - Bắt buộc xác định rõ loại bài"""
    prompt = f"""
    Bạn là chuyên gia khảo thí. Hãy phân tích ma trận đề thi sau thành JSON List.
    QUAN TRỌNG: Xác định chính xác loại câu hỏi (type) cho từng dòng.
    
    INPUT DATA:
    {txt[:20000]}
    
    OUTPUT JSON FORMAT:
    [
      {{
        "topic": "Tên chủ đề/bài học", 
        "yccd": "Yêu cầu cần đạt (nếu có)", 
        "type": "TN" (Trắc nghiệm 4 chọn 1) | "DS" (Đúng/Sai) | "NC" (Nối cột) | "DK" (Điền khuyết) | "TL" (Tự luận),
        "level": "Biết/Hiểu/Vận dụng", 
        "points": "Số điểm (VD: 0.5, 1.0)"
      }}
    ]
    """
    return call_ai_json(api_key, prompt)

def step2_generate_question_v12(item, context, api_key, q_index):
    """
    LOGIC V12: Tạo prompt riêng biệt cho từng loại câu hỏi.
    Ngăn chặn việc AI sinh ra dạng bài hỗn tạp.
    """
    subject = context.get('subject', 'Môn học')
    grade = context.get('grade', '')
    q_type = item.get('type', 'TN')
    
    # 1. Xây dựng hướng dẫn format riêng (Dynamic Prompting)
    format_guide = ""
    if q_type == "TN":
        format_guide = "Câu hỏi trắc nghiệm có 4 đáp án A, B, C, D. Chỉ có 1 đáp án đúng."
    elif q_type == "DS":
        format_guide = "Câu hỏi dạng Đúng/Sai. Gồm 1 câu dẫn và 4 ý a), b), c), d). Mỗi ý xác định là Đúng hoặc Sai."
    elif q_type == "NC":
        format_guide = "Dạng bài Nối cột A với cột B. Đảm bảo nội dung khớp logic."
    elif q_type == "DK":
        format_guide = "Dạng bài điền từ vào chỗ trống. Dùng ký hiệu '......' cho vị trí cần điền."
    else:
        format_guide = "Câu hỏi tự luận ngắn, yêu cầu học sinh viết câu trả lời."

    prompt = f"""
    Đóng vai giáo viên ra đề thi {subject} {grade} theo chương trình GDPT 2018.
    Hãy soạn nội dung cho Câu hỏi số {q_index}.
    
    THÔNG TIN ĐẦU VÀO:
    - Chủ đề: {item.get('topic')}
    - Yêu cầu cần đạt: {item.get('yccd')}
    - Mức độ: {item.get('level')}
    - Dạng bài: {q_type} ({format_guide})
    
    YÊU CẦU OUTPUT JSON (BẮT BUỘC 2 TRƯỜNG):
    {{
        "question_content": "Nội dung câu hỏi hoàn chỉnh để in vào đề thi (KHÔNG bao gồm đáp án đúng, KHÔNG giải thích). Trình bày đẹp.",
        "answer_key": "Đáp án chi tiết và Hướng dẫn chấm (VD: Đáp án A. Giải thích... / 1-a, 2-b...)"
    }}
    """
    
    data = call_ai_json(api_key, prompt)
    if not data:
        return {"question_content": "Lỗi tạo câu hỏi.", "answer_key": "Không có dữ liệu."}
    return data

# ==============================================================================
# 3. WORD GENERATOR V12 (TÁCH ĐỀ & ĐÁP ÁN)
# ==============================================================================
def create_docx_v12(questions, school, exam, context, time_limit):
    doc = docx.Document()
    style = doc.styles['Normal']; font = style.font
    font.name = 'Times New Roman'; font.size = Pt(13)
    
    # --- PHẦN 1: ĐỀ BÀI ---
    # Header
    tbl = doc.add_table(rows=1, cols=2)
    tbl.autofit = False; tbl.columns[0].width = Cm(7); tbl.columns[1].width = Cm(9)
    p1 = tbl.cell(0, 0).paragraphs[0]
    p1.add_run(f"{school.upper()}\n").bold = True
    p1.add_run("ĐỀ KIỂM TRA ĐỊNH KỲ").bold = False
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2 = tbl.cell(0, 1).paragraphs[0]
    p2.add_run(f"{exam.upper()}\n").bold = True
    p2.add_run(f"Môn: {context['subject']} - {context['grade']}\n").bold = True
    p2.add_run(f"Thời gian: {time_limit} phút").italic = True
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("\n")
    
    # Loop in câu hỏi
    for idx, q in enumerate(questions):
        # Đánh số cứng bằng Python (Fix lỗi nhảy số)
        full_label = f"Câu {idx+1}: ({q['points']} điểm) [{q['level']}]"
        
        p = doc.add_paragraph()
        run = p.add_run(full_label)
        run.bold = True; run.font.color.rgb = RGBColor(0, 0, 0)
        
        # Nội dung câu hỏi (Đã sạch, không chứa đáp án)
        content_lines = q['content'].split('\n')
        for line in content_lines:
            if line.strip():
                doc.add_paragraph(line.strip())
        doc.add_paragraph("") # Dòng trống ngăn cách

    # --- PHẦN 2: ĐÁP ÁN (Trang mới) ---
    doc.add_page_break()
    h = doc.add_paragraph("HƯỚNG DẪN CHẤM VÀ ĐÁP ÁN CHI TIẾT")
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.runs[0].bold = True; h.runs[0].font.size = Pt(14)
    doc.add_paragraph("\n")
    
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Câu'
    hdr_cells[1].text = 'Nội dung đáp án'
    
    for idx, q in enumerate(questions):
        row_cells = table.add_row().cells
        row_cells[0].text = f"Câu {idx+1}"
        row_cells[1].text = q['answer'] # In đáp án riêng

    bio = BytesIO(); doc.save(bio); return bio

# ==============================================================================
# 4. GIAO DIỆN CHÍNH (STREAMLIT)
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Cấu hình V12"); api_key = st.text_input("Nhập Gemini API Key", type="password")
    st.info("V12 sử dụng model 'Flash' để tối ưu tốc độ và định dạng JSON.")

st.subheader("1. Tải lên Ma trận đề thi")
uploaded_file = st.file_uploader("Hỗ trợ: .xlsx, .docx, .pdf", type=['xlsx', 'docx', 'pdf'])

# Biến toàn cục lưu trạng thái
if 'context' not in st.session_state: st.session_state['context'] = {}

# Đọc file và Auto-Detect (Cho phép sửa tay)
if uploaded_file:
    # Hàm đọc file (giữ nguyên logic cũ nhưng gọn hơn)
    def read_file(f):
        if f.name.endswith('.xlsx'): return pd.read_excel(f).to_string()
        if f.name.endswith('.docx'): return " ".join([p.text for p in docx.Document(f).paragraphs])
        if f.name.endswith('.pdf'): return "".join([p.extract_text() for p in PdfReader(f).pages])
        return ""
    
    raw_text = read_file(uploaded_file)
    
    # Auto-detect đơn giản (lấy 5000 ký tự đầu)
    if not st.session_state['context']:
        with st.spinner("Đang quét nội dung..."):
            if api_key:
                prompt_detect = f"Xác định Môn học và Lớp học từ văn bản này. Trả về JSON {{'subject': '...', 'grade': '...'}}. Text: {raw_text[:5000]}"
                det = call_ai_json(api_key, prompt_detect)
                if det: st.session_state['context'] = det
    
    # UI cho phép người dùng sửa (Manual Override)
    c1, c2 = st.columns(2)
    subj = c1.text_input("Môn học (Có thể sửa)", st.session_state.get('context', {}).get('subject', ''))
    grad = c2.text_input("Lớp/Khối (Có thể sửa)", st.session_state.get('context', {}).get('grade', ''))
    
    col_opt1, col_opt2, col_opt3 = st.columns(3)
    school = col_opt1.text_input("Tên trường", "TRƯỜNG TIỂU HỌC A")
    exam_name = col_opt2.text_input("Tên kỳ thi", "KIỂM TRA CUỐI KỲ I")
    time_lim = col_opt3.number_input("Thời gian (phút)", 40)

    if st.button("🚀 BẮT ĐẦU TẠO ĐỀ (V12)", type="primary"):
        if not api_key: st.error("Chưa nhập API Key!"); st.stop()
        
        ctx = {'subject': subj, 'grade': grad}
        st_bar = st.progress(0); st_status = st.empty()
        
        try:
            # B1: Phân tích Ma trận
            st_status.info("🔍 Đang phân tích cấu trúc ma trận...")
            blueprint = step1_parse_matrix(raw_text, api_key)
            
            if not blueprint or not isinstance(blueprint, list):
                st.error("Không đọc được ma trận. Hãy thử file đơn giản hơn."); st.stop()
            
            # B2: Tạo câu hỏi (Loop)
            final_data = []
            total = len(blueprint)
            st_status.info(f"✅ Tìm thấy {total} câu hỏi. Đang xử lý chi tiết...")
            
            for i, item in enumerate(blueprint):
                # Gọi hàm tạo câu hỏi V12
                res = step2_generate_question_v12(item, ctx, api_key, i+1)
                
                final_data.append({
                    'points': item.get('points', '1'),
                    'level': item.get('level', ''),
                    'content': res['question_content'], # Chỉ câu hỏi
                    'answer': res['answer_key']         # Chỉ đáp án
                })
                
                pct = (i+1)/total
                st_bar.progress(pct)
                st_status.write(f"✍️ Đang viết câu {i+1}/{total}: {item.get('type')} - {item.get('topic')}")
                time.sleep(1) # Tránh rate limit nhẹ
            
            # B3: Xuất file
            st_status.success("🎉 Hoàn tất! Đang tạo file Word...")
            docx_file = create_docx_v12(final_data, school, exam_name, ctx, time_lim)
            
            st.markdown("### 👇 Tải về kết quả")
            st.download_button(
                label="📥 Tải Đề Thi + Đáp Án (.docx)",
                data=docx_file,
                file_name=f"De_thi_{subj}_V12.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary"
            )
            
            # Preview nhanh
            with st.expander("Xem trước nội dung thô"):
                for idx, q in enumerate(final_data):
                    st.markdown(f"**Câu {idx+1}:**")
                    st.text(q['content'])
                    st.markdown(f"*Đáp án:* {q['answer']}")
                    st.divider()

        except Exception as e:
            st.error(f"Lỗi hệ thống: {e}")

else:
    st.info("👈 Hãy tải file ma trận lên để bắt đầu.")
