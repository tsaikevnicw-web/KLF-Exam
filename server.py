"""KLF 羽绒行业理论考试 - 本地随机组卷服务

启动: python server.py   然后浏览 http://localhost:8000
题库: questions.json (由 build_questions.py 从 PDF 生成)
标准答案只保存在服务端, 出卷时不会传给浏览器, 评分时才返回。
"""
import json
import random
import secrets
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 8000
EXAM_SIZE = 20
POINTS = 5

QUESTIONS = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))
BY_ID = {q["id"]: q for q in QUESTIONS}
EXAMS = {}  # exam_id -> [question ids]
GRADED_EXAMS = set()  # exam_ids that have been graded


def public(q):
    """去掉答案后的题目, 供前端显示"""
    return {k: v for k, v in q.items() if k not in ("answer",)}


TYPE_LIMITS = {
    "single": 500,
    "multi": 240,
    "judge": 230,
    "short": 30,
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "static"), **kw)

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/exam"):
            import urllib.parse
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            q_type = params.get("type", ["mixed"])[0]
            start_no = params.get("from", [""])[0]
            end_no = params.get("to", [""])[0]

            pool = QUESTIONS
            if q_type in TYPE_LIMITS:
                pool = [q for q in QUESTIONS if q.get("type") == q_type]
                max_limit = TYPE_LIMITS[q_type]
                try:
                    s = int(start_no) if start_no else 1
                except ValueError:
                    s = 1
                try:
                    e = int(end_no) if end_no else max_limit
                except ValueError:
                    e = max_limit
                if s > e:
                    s, e = e, s
                s = max(1, s)
                e = min(max_limit, e)
                pool = [q for q in pool if s <= q.get("no", 0) <= e]

            if not pool:
                return self._json({"error": "选定题型及范围内没有找到题目，请调整范围后重试"}, 400)

            sample_size = min(EXAM_SIZE, len(pool))
            picked = random.sample(pool, sample_size)
            exam_id = secrets.token_hex(8)
            EXAMS[exam_id] = [q["id"] for q in picked]
            return self._json({"examId": exam_id, "points": POINTS,
                               "totalPool": len(pool),
                               "questions": [public(q) for q in picked]})

        if self.path.startswith("/api/download_docx"):
            import urllib.parse
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            token = params.get("examId", [""])[0]
            if not token or token not in GRADED_EXAMS:
                self.send_response(403)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h3>抱歉，只有在完成交卷并取得评分成绩后，才可下载或查看题库核对 Word 档！</h3>".encode("utf-8"))
                return

            docx_name = "KLF_羽绒行业理论考试题库_完整1000题.docx"
            docx_file = ROOT / docx_name
            if not docx_file.exists():
                docx_files = list(ROOT.glob("*.docx"))
                if docx_files:
                    docx_file = docx_files[0]
                    docx_name = docx_file.name

            if docx_file.exists():
                data = docx_file.read_bytes()
                encoded_name = urllib.parse.quote(docx_name)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self.send_error(404, "Docx file not found")
                return

        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/grade"):
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            exam_id = data.get("examId")
            ids = EXAMS.get(exam_id)
            if not ids:
                return self._json({"error": "考卷不存在或已过期, 请重新出卷"}, 400)
            GRADED_EXAMS.add(exam_id)
            answers = data.get("answers", {})
            results = []
            for qid in ids:
                q = BY_ID[qid]
                given = answers.get(qid)
                if q["type"] == "short":
                    results.append({"id": qid, "answer": q["answer"], "correct": None})
                    continue
                if q["type"] == "multi":
                    correct = sorted(given or []) == sorted(q["answer"])
                else:
                    correct = given == q["answer"]
                results.append({"id": qid, "answer": q["answer"], "correct": correct})
            return self._json({"results": results})
        self.send_error(404)


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(f"Question bank loaded: {len(QUESTIONS)} questions.")
    print(f"Server running at: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
