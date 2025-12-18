import streamlit as st
import pandas as pd
from io import BytesIO
import docx
from pypdf import PdfReader
import google.generativeai as genai

# Cấu hình trang
st.set_page_config(page_title="Gemini Exam Generator", layout="wide")

st.title("🎓 Tool Hỗ Trợ Ra Đề Thi Tiểu Học (Gemini)")
st.markdown("---")

# Sidebar: Nhập API Key
with st.sidebar:
    st.header("Cấu hình")
    api_key = st.text_input("Nhập Google Gemini API Key", type="password")
    st.info("Lấy key miễn phí tại: aistudio.google.com")

# Hàm đọc nội dung từ file
def read_file(uploaded_file):
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
            text_content = df.to_string()
    except Exception as e:
        return f"Lỗi đọc file: {e}"
    return text_content

# Hàm gọi Gemini tạo đề
def generate_exam(matrix_text, topic):
    if not api_key:
        return None
    
    # Cấu hình Gemini
    try:
        genai.configure(api_key=api_key)
        
        # --- SỬA LỖI TẠI ĐÂY: Dùng model 'gemini-pro' thay vì 'gemini-1.5-flash' ---
        model = genai.GenerativeModel('gemini-pro') 
        
        # Prompt (Câu lệnh)
        prompt = f"""
        Bạn là một giáo viên tiểu học giỏi. Hãy đóng vai chuyên gia soạn đề thi.
        Dựa vào MA TRẬN ĐỀ THI được cung cấp dưới đây, hãy soạn thảo một đề thi hoàn chỉnh.

        THÔNG TIN ĐẦU VÀO (MA TRẬN):
        {matrix_text}

        YÊU CẦU CỤ THỂ:
        1. Chủ đề/Môn học: {topic}
        2. Cấu trúc trả về phải gồm 2 phần rõ ràng:
           - PHẦN 1: ĐỀ THI (Gồm các câu hỏi trắc nghiệm hoặc tự luận tùy theo ma trận).
           - PHẦN 2: ĐÁP ÁN VÀ THANG ĐIỂM CHI TIẾT.
        3. Đảm bảo nội dung phù hợp với lứa tuổi tiểu học, ngôn ngữ trong sáng, dễ hiểu.
        4. Trình bày đẹp, phân tách các câu hỏi rõ ràng.
        """

        # Gọi API
        with st.spinner("Gemini đang suy nghĩ và soạn đề..."):
            response = model.generate_content(prompt)
            return response.text

    except Exception as e:
        st.error(f"Lỗi kết nối Gemini: {e}")
        return None

# Hàm tạo file Word
def create_docx(exam_text):
    doc = docx.Document()
    doc.add_heading('ĐỀ THI TIỂU HỌC', 0)
    
    # Xử lý text để đưa vào word
    # Thay thế các ký tự markdown cơ bản để word đỡ lỗi
    clean_text = exam_text.replace("**", "").replace("##", "")
    
    for line in clean_text.split('\n'):
        if line.strip():
            doc.add_paragraph(line)
    
    bio = BytesIO()
    doc.save(bio)
    return bio

# --- GIAO DIỆN CHÍNH ---

tab1, tab2, tab3 = st.tabs(["📂 Tab 1: Tạo Đề Từ Ma Trận", "⚙️ Tab 2: Phát triển sau", "📊 Tab 3: Phát triển sau"])

with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("1. Input")
        uploaded_file = st.file_uploader("Upload Ma Trận (PDF, Excel, Word)", type=['pdf', 'docx', 'xlsx'])
        exam_topic = st.text_input("Nhập tên môn/chủ đề (VD: Tiếng Việt lớp 4)")
        
        generate_btn = st.button("🚀 Phân tích & Tạo đề")

        if generate_btn:
            if not uploaded_file:
                st.warning("Vui lòng upload file ma trận trước.")
            elif not api_key:
                st.warning("Vui lòng nhập Gemini API Key bên tay trái.")
            else:
                # Đọc file
                matrix_content = read_file(uploaded_file)
                # Gọi AI
                generated_content = generate_exam(matrix_content, exam_topic)
                
                if generated_content:
                    st.session_state['result'] = generated_content
                    st.success("Đã tạo xong! Mời xem kết quả bên cạnh.")

    with col2:
        st.subheader("2. Kết quả & Chỉnh sửa")
        
        if 'result' in st.session_state:
            # Cho phép chỉnh sửa trực tiếp
            edited_content = st.text_area(
                "Nội dung đề thi (Sửa trực tiếp tại đây):",
                value=st.session_state['result'],
                height=600
            )
            
            st.subheader("3. Tải xuống")
            docx_file = create_docx(edited_content)
            
            st.download_button(
                label="📥 Tải xuống file Word (.docx)",
                data=docx_file.getvalue(),
                file_name=f"De_thi_Gemini.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        else:
            st.info("👈 Hãy upload file và bấm nút tạo đề để xem kết quả tại đây.")
