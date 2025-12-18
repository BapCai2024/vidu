import streamlit as st
import google.generativeai as genai
import pandas as pd
from io import BytesIO
import docx
from pypdf import PdfReader
import time

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="AI Exam Generator (Fix Lỗi)", layout="wide")

st.title("🎓 Tool Tạo Đề Thi Từ Ma Trận (Phiên bản Fix Lỗi 404/429)")
st.markdown("---")

# --- 1. HÀM XỬ LÝ API THÔNG MINH (TRÍCH TỪ FILE 7h.py) ---
def generate_content_with_rotation(api_key, prompt):
    """
    Hàm này tự động tìm model khả dụng để tránh lỗi 404 và 429.
    Ưu tiên: Flash -> Pro -> Các model khác.
    """
    genai.configure(api_key=api_key)
    try:
        # Lấy danh sách tất cả model mà key này được phép dùng
        all_models = list(genai.list_models())
    except Exception as e:
        return f"Lỗi kết nối hoặc API Key sai: {e}", None

    # Lọc ra các model hỗ trợ tạo văn bản (generateContent)
    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    
    if not valid_models:
        return "Lỗi: API Key đúng nhưng không tìm thấy model nào hỗ trợ tạo văn bản.", None

    # Sắp xếp độ ưu tiên: Flash > Pro > Khác
    priority_order = []
    for m in valid_models:
        if 'flash' in m.lower() and '1.5' in m: priority_order.append(m)
    for m in valid_models:
        if 'pro' in m.lower() and '1.5' in m and m not in priority_order: priority_order.append(m)
    for m in valid_models:
        if m not in priority_order: priority_order.append(m)

    last_error = ""
    # Thử chạy lần lượt từng model
    for model_name in priority_order:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text, model_name # Trả về kết quả và tên model đã dùng
        except Exception as e:
            last_error = str(e)
            time.sleep(1) # Nghỉ 1 chút trước khi thử model tiếp theo
            continue

    return f"Đã thử tất cả model nhưng đều thất bại. Lỗi cuối cùng: {last_error}", None

# --- 2. CÁC HÀM HỖ TRỢ ĐỌC FILE & XUẤT WORD ---

def read_file(uploaded_file):
    """Đọc nội dung file upload (PDF, Word, Excel)"""
    text_content = ""
    try:
        if uploaded_file.name.endswith('.pdf'):
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        elif uploaded_file.name.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text_content += para.text + "\n"
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
            # Chuyển Excel thành text để AI đọc
            text_content = df.to_string()
    except Exception as e:
        return f"Lỗi đọc file: {e}"
    return text_content

def create_docx(exam_text, topic):
    doc = docx.Document()
    # Cài đặt font chữ cơ bản
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = docx.shared.Pt(13)
    
    doc.add_heading(f'ĐỀ THI: {topic.upper()}', 0)
    
    # Xử lý xuống dòng để văn bản trong Word đẹp hơn
    for line in exam_text.split('\n'):
        if line.strip():
            doc.add_paragraph(line)
    
    bio = BytesIO()
    doc.save(bio)
    return bio

# --- 3. GIAO DIỆN CHÍNH (TAB 1) ---

with st.sidebar:
    st.header("Cấu hình")
    api_key = st.text_input("Nhập Google Gemini API Key", type="password")
    st.info("Code này sẽ tự động tìm model phù hợp (Flash/Pro) để tránh lỗi.")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Nhập liệu")
    uploaded_file = st.file_uploader("Upload Ma Trận (PDF, Excel, Word)", type=['pdf', 'docx', 'xlsx'])
    exam_topic = st.text_input("Nhập tên môn/chủ đề (VD: Toán lớp 4 Giữa kì 1)")
    
    btn_generate = st.button("🚀 Phân tích & Tạo đề", type="primary")

    if btn_generate:
        if not uploaded_file:
            st.warning("Vui lòng upload file ma trận.")
        elif not api_key:
            st.warning("Vui lòng nhập API Key.")
        else:
            with st.spinner("AI đang đọc file và tìm model phù hợp..."):
                # 1. Đọc file
                matrix_content = read_file(uploaded_file)
                
                # 2. Tạo Prompt
                prompt = f"""
                Bạn là một giáo viên tiểu học giỏi. Hãy đóng vai chuyên gia soạn đề thi.
                Dựa vào MA TRẬN ĐỀ THI được cung cấp dưới đây, hãy soạn thảo một đề thi hoàn chỉnh.

                THÔNG TIN MA TRẬN:
                {matrix_content}

                YÊU CẦU:
                1. Chủ đề: {exam_topic}
                2. Tạo 2 phần: ĐỀ THI và ĐÁP ÁN CHI TIẾT.
                3. Nội dung phù hợp học sinh tiểu học.
                4. Trình bày rõ ràng.
                """
                
                # 3. Gọi hàm xử lý thông minh
                result_text, used_model = generate_content_with_rotation(api_key, prompt)
                
                if used_model:
                    st.session_state['result'] = result_text
                    st.success(f"✅ Đã tạo xong! (Sử dụng model: {used_model})")
                else:
                    st.error(f"❌ Thất bại: {result_text}")

with col2:
    st.subheader("2. Kết quả & Tải về")
    
    if 'result' in st.session_state:
        # Khu vực chỉnh sửa
        edited_content = st.text_area(
            "Nội dung đề thi (Sửa trực tiếp tại đây):",
            value=st.session_state['result'],
            height=600
        )
        
        # Nút tải về
        docx_file = create_docx(edited_content, exam_topic if exam_topic else "De_thi")
        st.download_button(
            label="📥 Tải xuống file Word (.docx)",
            data=docx_file.getvalue(),
            file_name=f"De_thi_{exam_topic.replace(' ', '_')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary"
        )
    else:
        st.info("👈 Hãy upload file ma trận và bấm nút tạo đề.")
