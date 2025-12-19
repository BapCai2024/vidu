# TT27 — Tạo đề Toán lớp 3 HK1 bằng Streamlit

## Cách chạy
1. Clone repo hoặc tải file về.
2. Cài đặt: `pip install streamlit python-docx`
3. Chạy: `streamlit run app.py`

## Tính năng
- Hiển thị ma trận theo SGK Toán lớp 3 HK1.
- Tạo/sửa câu hỏi theo dạng (MCQ, Đúng/Sai, Điền khuyết, Tự luận).
- Kiểm định mức độ/dạng câu theo ma trận.
- Chọn câu hỏi vào đề, tính tổng điểm.
- Xuất đề ra Word đúng thể thức.

## Cấu trúc dữ liệu
- `data/matrix.json`: ma trận chương/bài học.
- `data/questions.json`: ngân hàng câu hỏi mẫu.
- `utils/export_docx.py`: xuất đề ra Word.
