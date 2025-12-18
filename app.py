import streamlit as st
import pandas as pd
import google.generativeai as genai
from io import BytesIO

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Trợ Lý Ra Đề Thi Tiều Học", page_icon="📝", layout="wide")

# --- 1. GIẢ LẬP CƠ SỞ DỮ LIỆU (DATABASE) CHƯƠNG TRÌNH 2018 ---
# Trong thực tế, dữ liệu này nên được lưu ở file Excel hoặc JSON riêng và load vào.
# Ở đây tôi tạo mẫu chi tiết cho Lớp 4 - Bộ Kết nối tri thức.
DB_CURRICULUM = {
    "Lớp 4": {
        "Kết nối tri thức": {
            "Toán": {
                "icon": "➗",
                "topics": {
                    "Số và phép tính": {
                        "Bài 1: Ôn tập các số đến 100 000": [
                            "Đọc, viết được các số đến 100 000",
                            "Nhận biết được cấu tạo thập phân của số",
                            "So sánh, xếp thứ tự các số trong phạm vi 100 000"
                        ],
                        "Bài 10: Số có sáu chữ số": [
                            "Đọc, viết được các số có sáu chữ số",
                            "Hiểu được hàng và lớp của số có sáu chữ số"
                        ]
                    },
                    "Hình học": {
                        "Bài 23: Góc nhọn, góc tù, góc bẹt": [
                            "Nhận biết được góc nhọn, góc tù, góc bẹt",
                            "Sử dụng thước đo góc để đo độ lớn góc"
                        ]
                    }
                }
            },
            "Tiếng Việt": {
                "icon": "📖",
                "topics": {
                    "Đọc hiểu văn bản": {
                        "Chủ điểm: Mỗi người một vẻ": [
                            "Nhận biết được các chi tiết tiêu biểu trong bài đọc",
                            "Hiểu nội dung chính, ý nghĩa của bài đọc",
                            "Liên hệ nội dung bài đọc với bản thân"
                        ]
                    },
                    "Luyện từ và câu": {
                        "Danh từ": [
                            "Nhận biết được danh từ trong câu",
                            "Phân loại được danh từ chỉ người, vật, hiện tượng"
                        ],
                         "Động từ": [
                            "Nhận biết được động từ chỉ hoạt động, trạng thái",
                        ]
                    }
                }
            }
        },
        "Cánh Diều": {
             "Toán": { "icon": "📐", "topics": {"Đang cập nhật...": {}}} # Placeholder
        },
         "Chân trời sáng tạo": {
             "Toán": { "icon": "📐", "topics": {"Đang cập nhật...": {}}} # Placeholder
        }
    },
    "Lớp 3": { "Kết nối tri thức": {} }, # Placeholder
    "Lớp 5": { "Kết nối tri thức": {} }  # Placeholder
}

# --- XỬ LÝ SESSION STATE (LƯU TRẠNG THÁI) ---
if 'exam_questions' not in st.session_state:
    st.session_state['exam_questions'] = [] # Danh sách câu hỏi đã chọn
if 'current_generated_question' not in st.session_state:
    st.session_state['current_generated_question'] = "" # Câu hỏi vừa sinh ra (chưa lưu)

# --- SIDEBAR: CẤU HÌNH API & CHỌN MÔN ---
with st.sidebar:
    st.header("⚙️ Cấu hình & Dữ liệu")
    api_key = st.text_input("Nhập Gemini API Key", type="password")
    
    st.divider()
    
    # Menu chọn phân cấp (Cascading Dropdown)
    selected_grade = st.selectbox("Chọn Lớp", list(DB_CURRICULUM.keys()))
    
    available_books = list(DB_CURRICULUM[selected_grade].keys())
    selected_book = st.selectbox("Chọn Bộ Sách", available_books)
    
    available_subjects = list(DB_CURRICULUM[selected_grade][selected_book].keys())
    if available_subjects:
        selected_subject = st.selectbox("Chọn Môn Học", available_subjects)
        subject_icon = DB_CURRICULUM[selected_grade][selected_book][selected_subject].get('icon', '')
    else:
        selected_subject = None
        subject_icon = ""

# --- GIAO DIỆN CHÍNH ---
st.title(f"{subject_icon} HỆ THỐNG RA ĐỀ THI - {selected_subject or '...'}")
st.markdown("---")

if selected_subject and api_key:
    # Lấy dữ liệu chi tiết của môn đã chọn
    subject_data = DB_CURRICULUM[selected_grade][selected_book][selected_subject]["topics"]
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("1. Thiết lập câu hỏi")
        with st.container(border=True):
            # Chọn Chủ đề & Bài học
            selected_topic_group = st.selectbox("Chủ đề / Mạch nội dung", list(subject_data.keys()))
            
            lessons_map = subject_data[selected_topic_group]
            selected_lesson = st.selectbox("Bài học", list(lessons_map.keys()))
            
            # Chọn YCCĐ (Dữ liệu từ Database)
            yccds = lessons_map[selected_lesson]
            selected_yccd = st.selectbox("Yêu cầu cần đạt (YCCĐ)", yccds)
            
            st.divider()
            
            # Các thông số kỹ thuật khác
            q_type = st.selectbox("Dạng câu hỏi", ["Trắc nghiệm (4 đáp án)", "Tự luận", "Đúng/Sai", "Điền khuyết", "Ghép nối"])
            q_level = st.selectbox("Mức độ (TT27)", ["Mức 1: Nhận biết", "Mức 2: Thông hiểu", "Mức 3: Vận dụng"])
            q_score = st.number_input("Điểm số", min_value=0.25, step=0.25, value=1.0)
            
            btn_generate = st.button("✨ TẠO CÂU HỎI (DRAFT)", use_container_width=True, type="primary")

    with col2:
        st.subheader("2. Xem trước & Chỉnh sửa")
        
        # LOGIC GỌI GEMINI
        if btn_generate:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                prompt = f"""
                Đóng vai giáo viên tiểu học Việt Nam. Hãy tạo 1 câu hỏi kiểm tra đánh giá.
                - Môn: {selected_subject} - Lớp: {selected_grade} - Bộ sách: {selected_book}
                - Bài: {selected_lesson}
                - Yêu cầu cần đạt: {selected_yccd}
                - Dạng: {q_type}
                - Mức độ: {q_level}
                
                Yêu cầu định dạng output:
                - Chỉ xuất nội dung câu hỏi và đáp án (nếu có).
                - Không giải thích dài dòng.
                - Nếu là trắc nghiệm, hãy đánh dấu đáp án đúng.
                """
                
                with st.spinner("Đang suy nghĩ..."):
                    response = model.generate_content(prompt)
                    st.session_state['current_generated_question'] = response.text
            except Exception as e:
                st.error(f"Lỗi API: {e}")

        # Khu vực hiển thị kết quả sinh ra để người dùng sửa
        if st.session_state['current_generated_question']:
            with st.container(border=True):
                # Text area cho phép giáo viên chỉnh sửa trực tiếp
                final_content = st.text_area(
                    "Nội dung câu hỏi (Bạn có thể sửa lại trước khi thêm)",
                    value=st.session_state['current_generated_question'],
                    height=200
                )
                
                c1, c2, c3 = st.columns([1, 1, 2])
                with c1:
                    if st.button("Làm lại câu khác 🔄"):
                         # Logic kích hoạt lại nút generate (cần click lại nút Tạo bên trái thực tế)
                         st.info("Hãy bấm nút 'TẠO CÂU HỎI' bên trái để sinh câu mới.")
                with c2:
                    if st.button("Thêm vào đề ✅", type="primary"):
                        # Lưu vào Session State
                        new_q = {
                            "STT": len(st.session_state['exam_questions']) + 1,
                            "Tên bài": selected_lesson,
                            "YCCĐ": selected_yccd,
                            "Dạng": q_type,
                            "Mức độ": q_level,
                            "Điểm": q_score,
                            "Nội dung": final_content
                        }
                        st.session_state['exam_questions'].append(new_q)
                        st.success("Đã thêm vào danh sách!")
                        # Clear nội dung tạm
                        st.session_state['current_generated_question'] = ""
                        st.rerun()

    # --- PHẦN 3: BẢNG THỐNG KÊ & XUẤT FILE ---
    st.markdown("---")
    st.subheader("3. Ma trận đề thi & Xuất file")

    if len(st.session_state['exam_questions']) > 0:
        df = pd.DataFrame(st.session_state['exam_questions'])
        
        # Hiển thị bảng đẹp
        st.dataframe(df.style.format({"Điểm": "{:.2f}"}), use_container_width=True)
        
        col_act1, col_act2 = st.columns([1, 5])
        with col_act1:
            if st.button("🗑️ Xóa toàn bộ"):
                st.session_state['exam_questions'] = []
                st.rerun()
        
        with col_act2:
            # Giả lập xuất Word (Trong thực tế dùng thư viện python-docx)
            # Ở đây xuất CSV để demo tính năng tải xuống
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Tải xuống đề thi (Excel/CSV)",
                data=csv,
                file_name='de_thi_tieu_hoc.csv',
                mime='text/csv',
                type="primary"
            )
            st.info("*Lưu ý: Tính năng xuất file Word (.docx) định dạng đẹp sẽ được tích hợp bằng thư viện `python-docx` trong bản chính thức.*")
            
    else:
        st.info("Chưa có câu hỏi nào trong đề. Hãy thêm câu hỏi ở trên.")

else:
    st.warning("Vui lòng nhập API Key và chọn đầy đủ thông tin Môn học để bắt đầu.")
