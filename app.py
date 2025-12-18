import streamlit as st
import pandas as pd
from io import BytesIO
import docx
from pypdf import PdfReader
from openai import OpenAI

# Cấu hình trang
st.set_page_config(page_title="AI Exam Generator", layout="wide")

st.title("🎓 Tool Hỗ Trợ Ra Đề Thi Tiểu Học")
st.markdown("---")

# Sidebar: Nhập API Key (Bảo mật)
with st.sidebar:
    st.header("Cấu hình")
    api_key = st.text_input("Nhập OpenAI API Key", type="password")
    st.info("Cần có API Key để AI phân tích ma trận và tạo đề.")

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

# Hàm gọi AI tạo đề (Sử dụng OpenAI)
def generate_exam(matrix_text, topic):
    if not api_key:
        return None, None
    
    client = OpenAI(api_key=api_key)
    
    # Prompt (Câu lệnh) gửi cho AI
    prompt = f"""
    Bạn là một giáo viên tiểu học giỏi. Hãy dựa vào MA TRẬN ĐỀ THI dưới đây để ra một đề thi hoàn chỉnh và đáp án.
    
    THÔNG TIN MA TRẬN:
    {matrix_text}
    
    YÊU CẦU:
    1. Chủ đề/Môn học: {topic}
    2. Tạo ra 2 phần riêng biệt: ĐỀ THI và ĐÁP ÁN CHI TIẾT.
    3. Đảm bảo bám sát mức độ, dạng câu hỏi và điểm số trong ma trận.
    4. Trình bày rõ ràng.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # Hoặc gpt-4 nếu bạn có quyền truy cập
            messages=[
                {"role": "system", "content": "Bạn là trợ lý soạn đề thi chuyên nghiệp."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        full_text = response.choices[0].message.content
        
        # Tách sơ bộ Đề và Đáp án (Giả định AI trả về có từ khóa)
        # Trong thực tế có thể cần prompt kỹ hơn để trả về JSON
        return full_text
    except Exception as e:
        st.error(f"Lỗi kết nối AI: {e}")
        return None

# Hàm tạo file Word để tải xuống
def create_docx(exam_text):
    doc = docx.Document()
    doc.add_heading('ĐỀ THI TIỂU HỌC', 0)
    doc.add_paragraph(exam_text)
    
    bio = BytesIO()
    doc.save(bio)
    return bio

# --- GIAO DIỆN CHÍNH ---

tab1, tab2, tab3 = st.tabs(["📂 Tab 1: Tạo Đề Từ Ma Trận", "⚙️ Tab 2: (Đang phát triển)", "📊 Tab 3: (Đang phát triển)"])

with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("1. Input")
        uploaded_file = st.file_uploader("Upload Ma Trận (PDF, Excel, Word)", type=['pdf', 'docx', 'xlsx'])
        exam_topic = st.text_input("Nhập tên môn/chủ đề (VD: Toán lớp 5 giữa kì)")
        
        if uploaded_file and exam_topic:
            st.success("Đã nhận file!")
            if st.button("🚀 Phân tích & Tạo đề"):
                with st.spinner("AI đang đọc ma trận và soạn đề..."):
                    # Đọc file
                    matrix_content = read_file(uploaded_file)
                    # Gọi AI
                    generated_content = generate_exam(matrix_content, exam_topic)
                    
                    if generated_content:
                        st.session_state['result'] = generated_content
                        st.success("Đã tạo xong!")
                    else:
                        st.warning("Vui lòng nhập API Key để chạy.")

    with col2:
        st.subheader("2. Kết quả & Chỉnh sửa")
        
        if 'result' in st.session_state:
            # Cho phép chỉnh sửa trực tiếp trên giao diện
            edited_content = st.text_area(
                "Nội dung đề thi & Đáp án (Bạn có thể sửa trực tiếp ở đây):",
                value=st.session_state['result'],
                height=500
            )
            
            st.subheader("3. Tải xuống")
            # Nút download
            docx_file = create_docx(edited_content)
            st.download_button(
                label="📥 Tải xuống file Word (.docx)",
                data=docx_file.getvalue(),
                file_name="De_thi_tieu_hoc.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        else:
            st.info("Kết quả sẽ hiện thị tại đây sau khi bạn bấm nút tạo đề.")