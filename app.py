import json
import uuid
import datetime
import streamlit as st

from utils.export_docx import export_exam_docx

# ---------------- Config ----------------
st.set_page_config(page_title="TT27 — Tạo đề Toán lớp 3 HK1", page_icon="📝", layout="wide")

LEVELS = ["recognize", "understand", "apply"]
LEVEL_LABELS = {"recognize": "Nhận biết", "understand": "Thông hiểu", "apply": "Vận dụng"}
POINTS_PER_TYPE = {"MCQ": 0.5, "TrueFalse": 0.5, "Matching": 1.0, "FillBlank": 1.0, "Essay": 1.0}
TYPE_LABELS = {"MCQ": "Nhiều lựa chọn", "TrueFalse": "Đúng/Sai", "Matching": "Nối cột", "FillBlank": "Điền khuyết", "Essay": "Tự luận"}

# ---------------- Data IO ----------------
@st.cache_data
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

matrix = load_json("data/matrix.json")
questions_db = load_json("data/questions.json")

if "questions" not in st.session_state:
    st.session_state["questions"] = questions_db  # mutable working set
if "exams" not in st.session_state:
    st.session_state["exams"] = []

# ---------------- Helpers ----------------
def get_topics(mtx):
    return mtx.get("topics", [])

def get_lessons(mtx, topic_id):
    for t in get_topics(mtx):
        if t["topic_id"] == topic_id:
            return t["lessons"]
    return []

def get_lesson_matrix(mtx, topic_id, lesson_id):
    for t in get_topics(mtx):
        if t["topic_id"] == topic_id:
            for l in t["lessons"]:
                if l["lesson_id"] == lesson_id:
                    return l["matrix"]
    return {}

def filter_questions(grade, subject, semester, topic_id, lesson_id):
    return [q for q in st.session_state["questions"]
            if q["grade"] == grade and q["subject"] == subject and q["semester"] == semester
            and q["topic_id"] == topic_id and q["lesson_id"] == lesson_id]

def count_by_level(questions):
    c = {lvl: 0 for lvl in LEVELS}
    for q in questions:
        if q["level"] in c:
            c[q["level"]] += 1
    return c

def total_points(questions):
    return sum(float(q.get("points", 0)) for q in questions)

def is_allowed_type(lesson_mtx, q_type):
    return q_type in lesson_mtx.get("allowed_types", [])

def remaining_quota(lesson_mtx, level, used):
    plan = int(lesson_mtx[level]["questions"])
    return max(0, plan - used)

# ---------------- Header ----------------
st.title("📝 Tạo đề kiểm tra định kỳ — Toán lớp 3 (Học kì 1) theo TT27")

# ---------------- Filters ----------------
flt = st.columns(5)
with flt[0]:
    grade = st.selectbox("Lớp", [3], index=0)
with flt[1]:
    subject = st.selectbox("Môn", ["Toán"], index=0)
with flt[2]:
    semester = st.selectbox("Học kỳ", ["HK1"], index=0)

topics = get_topics(matrix)
topic_labels = {t["topic_id"]: t["title"] for t in topics}
with flt[3]:
    topic_id = st.selectbox("Chủ đề (chương SGK)", options=[t["topic_id"] for t in topics], format_func=lambda x: topic_labels.get(x, x))
lessons = get_lessons(matrix, topic_id)
lesson_labels = {l["lesson_id"]: l["title"] for l in lessons}
with flt[4]:
    lesson_id = st.selectbox("Bài học", options=[l["lesson_id"] for l in lessons], format_func=lambda x: lesson_labels.get(x, x))

st.divider()

# ---------------- Two columns ----------------
left, right = st.columns([7, 5])

# -------- Right: Matrix panel --------
with right:
    st.subheader("📊 Ma trận bài học (TT27)")
    lesson_mtx = get_lesson_matrix(matrix, topic_id, lesson_id)
    current_qs = filter_questions(grade, subject, semester, topic_id, lesson_id)
    used_counts = count_by_level(current_qs)
    pt_used = total_points(current_qs)

    cols = st.columns(3)
    for i, lvl in enumerate(LEVELS):
        plan = lesson_mtx[lvl]["questions"]
        used = used_counts.get(lvl, 0)
        cols[i].metric(LEVEL_LABELS[lvl], f"{used}/{plan} câu", f"{pt_used:.1f} điểm")

    st.caption("Dạng cho phép: " + ", ".join(TYPE_LABELS[t] for t in lesson_mtx["allowed_types"]))
    st.caption("Điểm mỗi dạng: MCQ=0.5 • TrueFalse=0.5 • Matching=1 • FillBlank=1 • Essay=1")

    # Quick adjust quotas (session-only)
    with st.popover("Sửa ma trận (phiên chạy)"):
        for lvl in LEVELS:
            c1, c2 = st.columns(2)
            with c1:
                new_q = st.number_input(f"Số câu — {LEVEL_LABELS[lvl]}", min_value=0, step=1, value=int(lesson_mtx[lvl]["questions"]))
                lesson_mtx[lvl]["questions"] = int(new_q)
            with c2:
                st.write("Điểm mức độ phụ thuộc dạng câu. Xem bảng điểm dạng.")

# -------- Left: Question form --------
with left:
    st.subheader("✍️ Tạo / Sửa câu hỏi")
    colA, colB, colC, colD = st.columns(4)
    with colA:
        q_type = st.selectbox("Dạng câu hỏi", options=["MCQ", "TrueFalse", "FillBlank", "Matching", "Essay"], format_func=lambda x: TYPE_LABELS[x])
    with colB:
        q_level = st.selectbox("Mức độ", options=LEVELS, format_func=lambda x: LEVEL_LABELS[x])
    with colC:
        default_points = POINTS_PER_TYPE[q_type]
        q_points = st.number_input("Điểm câu", min_value=0.0, step=0.5, value=float(default_points))
    with colD:
        q_id = st.text_input("Mã câu (để trống tự sinh)")

    prompt = st.text_area("Nội dung câu hỏi")
    options = None
    answer = None

    if q_type == "MCQ":
        st.info("Nhập phương án và chọn đáp án đúng.")
        c1, c2 = st.columns(2)
        with c1:
            opt_a = st.text_input("Phương án A")
            opt_b = st.text_input("Phương án B")
            opt_c = st.text_input("Phương án C")
        with c2:
            opt_d = st.text_input("Phương án D")
            answer = st.selectbox("Đáp án đúng", options=["A", "B", "C", "D"])
        options = [opt_a, opt_b, opt_c, opt_d]
    elif q_type == "TrueFalse":
        answer = st.selectbox("Đáp án", options=["Đúng", "Sai"])
    else:
        answer = st.text_input("Đáp án / gợi ý đáp án")

    explanation = st.text_area("Lời giải / diễn giải (tùy chọn)")

    st.markdown("#### 👀 Xem trước")
    st.write(f"- Lớp {grade} • {subject} • {semester} • Chủ đề: {topic_labels.get(topic_id)} • Bài: {lesson_labels.get(lesson_id)}")
    st.write(f"- Dạng: {TYPE_LABELS[q_type]} • Mức độ: {LEVEL_LABELS[q_level]} • Điểm: {q_points}")
    st.write(prompt)
    if q_type == "MCQ" and options:
        for i, opt in enumerate(options):
            st.write(f"{chr(65+i)}. {opt}")
        st.write(f"→ Đáp án: {answer}")
    else:
        st.write(f"→ Đáp án/Gợi ý: {answer}")

    def validate_add():
        if not prompt or not answer:
            return False, "Cần nội dung câu hỏi và đáp án."
        if not is_allowed_type(lesson_mtx, q_type):
            return False, "Dạng câu hỏi không được phép theo ma trận bài học."
        used = used_counts.get(q_level, 0)
        remain = remaining_quota(lesson_mtx, q_level, used)
        if remain <= 0:
            return False, f"Đã đủ số câu cho mức độ {LEVEL_LABELS[q_level]}."
        if q_type == "MCQ":
            filled = [o for o in options if o and o.strip()]
            if len(filled) < 2:
                return False, "Cần ít nhất 2 phương án cho MCQ."
        return True, ""

    a1, a2 = st.columns(2)
    with a1:
        if st.button("➕ Thêm câu hỏi"):
            ok, msg = validate_add()
            if not ok:
                st.error(msg)
            else:
                new_id = q_id or f"Q-{subject}-{grade}-{semester}-{topic_id}-{lesson_id}-{str(uuid.uuid4())[:6]}"
                st.session_state["questions"].append({
                    "id": new_id,
                    "grade": grade, "subject": subject, "semester": semester,
                    "topic_id": topic_id, "lesson_id": lesson_id,
                    "type": q_type, "level": q_level, "points": float(q_points),
                    "prompt": prompt, "options": options if q_type == "MCQ" else None,
                    "answer": answer, "explanation": explanation
                })
                # Ghi ra file
                save_json("data/questions.json", st.session_state["questions"])
                st.success(f"Đã thêm câu hỏi {new_id}.")
    with a2:
        st.button("🧹 Xóa form", type="secondary")

st.divider()

# ---------------- Exam build & export ----------------
st.subheader("📦 Tạo đề và xuất Word")
available = filter_questions(grade, subject, semester, topic_id, lesson_id)
st.caption(f"Có {len(available)} câu trong tuyến dữ liệu này.")
selected_ids = st.multiselect("Chọn câu hỏi", options=[q["id"] for q in available])

exam_id = st.text_input("Mã đề", value=f"EX-{subject}-{grade}-{semester}-{str(uuid.uuid4())[:6]}")
header_school = st.text_input("Trường", value="TRƯỜNG TIỂU HỌC PA VÌ")
header_grade = st.text_input("Khối lớp", value="Lớp 3")
header_subject = st.text_input("Môn", value="Toán")
header_semester = st.text_input("Kỳ", value="Cuối học kỳ 1")
header_time = st.text_input("Thời gian làm bài", value="40 phút")
header_note = st.text_area("Ghi chú đề (tùy chọn)", value="Họ và tên: ______________________    Lớp: ________")

chosen = [q for q in available if q["id"] in selected_ids]
pt = total_points(chosen)
st.write(f"Tổng điểm các câu chọn: {pt:.1f} điểm")

if st.button("✅ Tạo đề"):
    exam = {
        "exam_id": exam_id,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "grade": grade, "subject": subject, "semester": semester,
        "topic_id": topic_id, "lesson_id": lesson_id,
        "question_ids": selected_ids, "total_points": float(pt),
        "header": {
            "school": header_school,
            "grade": header_grade,
            "subject": header_subject,
            "semester": header_semester,
            "time": header_time,
            "note": header_note
        }
    }
    st.session_state["exams"].append(exam)
    st.success(f"Đã tạo đề {exam_id}.")

st.markdown("#### 🧾 Xuất Word")
if st.button("📄 Xuất file .docx"):
    qs = [q for q in st.session_state["questions"] if q["id"] in selected_ids]
    if not qs:
        st.error("Chưa chọn câu hỏi.")
    else:
        file_bytes = export_exam_docx(
            header={
                "school": header_school,
                "subject": header_subject,
                "grade": header_grade,
                "semester": header_semester,
                "time": header_time,
                "note": header_note
            },
            questions=qs
        )
        st.download_button("⬇️ Tải đề Word", data=file_bytes, file_name=f"{exam_id}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

st.divider()

# ---------------- Existing exams ----------------
st.subheader("🗂️ Đề đã tạo")
for ex in st.session_state["exams"]:
    st.write(f"- {ex['exam_id']} • {ex['subject']} • {ex['grade']} • {ex['semester']} • Điểm {ex['total_points']:.1f}")
