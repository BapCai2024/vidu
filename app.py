import streamlit as st
import google.generativeai as genai
import pandas as pd
from io import BytesIO
import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
import time
import re

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Hệ Thống Ra Đề Thi Chuẩn TT27", layout="wide", page_icon="🏫")

st.title("🏫 Hệ Thống Ra Đề Thi Tiểu Học (Chuẩn Ma Trận TT27)")
st.markdown("---")

# --- 1. HÀM API THÔNG MINH (GIỮ NGUYÊN TỪ BẢN TRƯỚC) ---
def generate_content_with_rotation(api_key, prompt):
    genai.configure(api_key=api_key)
    try:
        all_models = list(genai.list_models())
    except Exception as e:
        return f"Lỗi kết nối API: {e}", None

    valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
    if not valid_models: return "Không tìm thấy model phù hợp.", None

    # Ưu tiên Flash (nhanh) -> Pro (thông minh)
    priority = []
    for m in valid_models:
        if 'flash' in m.lower() and '1.5' in m: priority.append(m)
    for m in valid_models:
        if 'pro' in m.lower() and '1.5' in m and m not in priority: priority.append(m)
    
    # Nếu không có 1.5 thì lấy pro thường
    if not priority:
        for m in valid_models: 
            if 'gemini-pro' in m: priority.append(m)

    last_error = ""
    for model_name in priority:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text, model_name
        except Exception as e:
            last_error = str(e)
            time.sleep(1)
            continue
    return f"Lỗi tất cả models: {last_error}", None

# --- 2. HÀM PHÂN TÍCH EXCEL (LOGIC MỚI QUAN TRỌNG) ---
def analyze_excel_matrix(df):
    """
    Hàm này cố gắng hiểu cấu trúc file Excel ma trận đặc tả.
    Nó tìm các cột quan trọng: Chủ đề, YCCĐ, Số câu TN/TL, Câu số.
    """
    # 1. Tìm dòng header thực sự (Dòng chứa chữ "Chủ đề" hoặc "Mạch kiến thức")
    header_row_idx = 0
    for idx, row in df.iterrows():
        row_str = row.astype(str).str.lower().values
        if any('chủ đề' in s for s in row_str) or any('mạch kiến thức' in s for s in row_str):
            header_row_idx = idx
            break
    
    # Đặt lại header
    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx+1:].reset_index(drop=True)
    
    # 2. Xác định các cột dựa trên từ khóa (Keyword mapping)
    cols = df.columns.astype(str).str.lower()
    
    col_map = {
        'topic': None,      # Chủ đề
        'content': None,    # Nội dung kiến thức
        'yccd': None,       # Yêu cầu cần đạt / Mức độ đánh giá
        'q_num': [],        # Cột chứa thông tin câu số (VD: Câu số, Số câu TN...)
    }

    for col in df.columns:
        c_lower = str(col).lower()
        if 'chủ đề' in c_lower or 'mạch' in c_lower:
            if not col_map['topic']: col_map['topic'] = col
        elif 'nội dung' in c_lower or 'đơn vị' in c_lower:
            col_map['content'] = col
        elif 'mức độ' in c_lower or 'yêu cầu' in c_lower or 'yccđ' in c_lower:
            col_map['yccd'] = col
        elif 'câu số' in c_lower or 'số câu' in c_lower or 'tn' in c_lower or 'tl' in c_lower or 'mức' in c_lower:
            # Lấy tất cả các cột liên quan đến số lượng câu hỏi
            col_map['q_num'].append(col)

    # 3. Quét từng dòng để tạo "Kịch bản đề thi"
    exam_blueprint = []
    
    current_topic = ""
    current_content = ""
    
    for idx, row in df.iterrows():
        # Xử lý merge cell: Nếu ô chủ đề trống, dùng chủ đề của dòng trước
        topic_val = str(row[col_map['topic']]) if col_map['topic'] and pd.notna(row[col_map['topic']]) else ""
        if topic_val.strip() and topic_val.lower() != 'nan': 
            current_topic = topic_val
        
        content_val = str(row[col_map['content']]) if col_map['content'] and pd.notna(row[col_map['content']]) else ""
        if content_val.strip() and content_val.lower() != 'nan':
            current_content = content_val
            
        yccd_val = str(row[col_map['yccd']]) if col_map['yccd'] and pd.notna(row[col_map['yccd']]) else ""
        
        # Quét các cột số lượng câu hỏi để tìm xem dòng này có câu hỏi nào không
        # Logic: Tìm các ô có chứa số (VD: "1", "2") hoặc chữ "Câu 1", "Câu 5-6"
        questions_found = []
        for q_col in col_map['q_num']:
            val = str(row[q_col])
            if pd.notna(val) and val.lower() != 'nan' and val.strip() != '':
                # Kiểm tra xem có phải là số câu hỏi hay số thứ tự câu
                # Giả sử format là số lượng (1, 2) hoặc index (Câu 1)
                clean_val = val.strip()
                if any(char.isdigit() for char in clean_val):
                     questions_found.append(f"{q_col}: {clean_val}")

        if questions_found and yccd_val.lower() != 'nan':
            exam_blueprint.append({
                "Topic": current_topic,
                "Content": current_content,
                "YCCD": yccd_val,
                "Details": ", ".join(questions_found)
            })
            
    return exam_blueprint

def create_prompt_from_blueprint(blueprint, topic_name):
    """Tạo prompt chi tiết từ kịch bản đã phân tích"""
    prompt_text = f"Bạn là chuyên gia ra đề thi tiểu học. Hãy soạn đề thi môn {topic_name} dựa trên BẢNG ĐẶC TẢ CHI TIẾT sau đây.\n\n"
    prompt_text += "DANH SÁCH CÂU HỎI CẦN SOẠN:\n"
    
    for i, item in enumerate(blueprint):
        prompt_text += f"#{i+1}. Chủ đề: {item['Topic']} - {item['Content']}\n"
        prompt_text += f"   - Yêu cầu cần đạt: {item['YCCD']}\n"
        prompt_text += f"   - Yêu cầu câu hỏi (Số lượng/Dạng/Mức độ): {item['Details']}\n"
        prompt_text += "---\n"
        
    prompt_text += "\n\nYÊU CẦU ĐẦU RA:\n"
    prompt_text += "1. Trình bày đề thi hoàn chỉnh, đánh số câu hỏi liên tục (Câu 1, Câu 2...).\n"
    prompt_text += "2. Với câu Trắc nghiệm: Phải có 4 đáp án A, B, C, D.\n"
    prompt_text += "3. Với câu Tự luận: Ghi rõ đề bài.\n"
    prompt_text += "4. Cuối cùng là PHẦN ĐÁP ÁN VÀ THANG ĐIỂM chi tiết.\n"
    
    return prompt_text

def create_docx(exam_text):
    doc = docx.Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = docx.shared.Pt(13)
    
    # Tách dòng để xử lý format
    lines = exam_text.split('\n')
    for line in lines:
        if line.strip():
            p = doc.add_paragraph(line)
            # Nếu là tiêu đề câu hỏi (Câu 1, Câu 2...) thì in đậm
            if line.strip().startswith("Câu") and ":" in line:
                p.runs[0].bold = True
                
    bio = BytesIO()
    doc.save(bio)
    return bio

# --- 3. GIAO DIỆN TAB 1 ---
with st.sidebar:
    st.header("🔑 Cấu hình")
    api_key = st.text_input("Nhập Gemini API Key", type="password")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Input")
    uploaded_file = st.file_uploader("Upload Ma Trận (Excel .xlsx)", type=['xlsx'])
    exam_topic = st.text_input("Tên bài thi (VD: Toán Lớp 5 Cuối Kì 1)")
    
    if uploaded_file and api_key and exam_topic:
        if st.button("🚀 Phân tích & Tạo đề", type="primary"):
            status_text = st.empty()
            
            try:
                # BƯỚC 1: ĐỌC EXCEL
                status_text.info("📂 Đang đọc cấu trúc file Excel...")
                df = pd.read_excel(uploaded_file)
                
                # BƯỚC 2: PHÂN TÍCH MA TRẬN
                blueprint = analyze_excel_matrix(df)
                
                if not blueprint:
                    st.error("Không tìm thấy dữ liệu câu hỏi trong file. Hãy đảm bảo file Excel có cột 'Chủ đề', 'Yêu cầu cần đạt' và các cột số lượng câu hỏi.")
                else:
                    # Hiển thị kết quả phân tích cho người dùng check
                    st.session_state['blueprint'] = blueprint
                    
                    # BƯỚC 3: GỌI AI
                    status_text.info("🤖 AI đang soạn đề theo kịch bản...")
                    prompt = create_prompt_from_blueprint(blueprint, exam_topic)
                    
                    result_text, model_used = generate_content_with_rotation(api_key, prompt)
                    
                    if result_text:
                        st.session_state['exam_result'] = result_text
                        status_text.success(f"✅ Xong! (Model: {model_used})")
                    else:
                        status_text.error("Lỗi khi gọi AI.")
                        
            except Exception as e:
                st.error(f"Lỗi: {e}")

with col2:
    st.subheader("2. Kiểm tra & Kết quả")
    
    # Tab con để xem kịch bản phân tích (Debug)
    tab_res1, tab_res2 = st.tabs(["📝 Đề thi hoàn chỉnh", "🔍 Dữ liệu phân tích từ Excel"])
    
    with tab_res2:
        if 'blueprint' in st.session_state:
            st.write(f"Đã tìm thấy {len(st.session_state['blueprint'])} yêu cầu ra đề:")
            st.dataframe(st.session_state['blueprint'])
        else:
            st.info("Chưa có dữ liệu phân tích.")

    with tab_res1:
        if 'exam_result' in st.session_state:
            edited_content = st.text_area("Nội dung đề (Có thể sửa):", value=st.session_state['exam_result'], height=600)
            
            docx = create_docx(edited_content)
            st.download_button(
                label="📥 Tải file Word (.docx)",
                data=docx.getvalue(),
                file_name=f"De_thi_{exam_topic}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary"
            )
        else:
            st.info("Kết quả đề thi sẽ hiện ở đây.")
