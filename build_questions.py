"""把 OCR 文字解析成 questions.json
用法: python build_questions.py <ocr目录1> [<ocr目录2> ...]
多个目录时, 每题优先采用第一个目录中解析成功的版本, 失败则用后面的目录补上。
"""
import json, re, sys
from pathlib import Path

SRCS = [Path(p) for p in sys.argv[1:]]
OUT = Path(__file__).parent / "questions.json"
WATERMARK = "2026全国羽绒行业职业技能竞赛"

# 常见 OCR 错字修正
FIX = {
    "冒允": "冒充", "以次允好": "以次充好", "记求": "记录", "因家": "国家", "止确": "正确",
    "循坏": "循环", "以土": "以上", "□头": "口头", "I作": "工作", "并H": "并且",
    "绒予": "绒子", "哪儿种": "哪几种", "大然": "天然",
}


def load_sections(src):
    files = sorted(src.glob("*.txt"))
    lines = []
    for f in files:
        lines += f.read_text(encoding="utf-8").splitlines()
    clean = []
    for ln in lines:
        s = ln.strip()
        if not s or "理论考试题库及参考答案" in s:
            continue
        if re.fullmatch(r"第\s*\d+\s*页\s*共\s*\d+\s*页", s):
            continue
        # 去掉混进来的水印碎片 (以空格分隔、是水印子串的词)
        toks = s.split(" ")
        toks = [t for t in toks if not (len(t) >= 2 and t in WATERMARK and not t.isdigit())]
        s = " ".join(toks).strip()
        if not s:
            continue
        for a, b in FIX.items():
            s = s.replace(a, b)
        clean.append(s)

    sections = {"single": [], "multi": [], "judge": [], "short": []}
    cur = None
    for s in clean:
        if s.startswith("一、单选题"): cur = "single"; continue
        if s.startswith("二、多选题"): cur = "multi"; continue
        if s.startswith("三、判断题"): cur = "judge"; continue
        if s.startswith("四、简答题"): cur = "short"; continue
        if cur == "judge" and s.startswith("打“"):
            continue
        if cur: sections[cur].append(s)
    return sections


def split_questions(rows):
    """按题号顺序切分; 允许跳过最多 3 个题号 (OCR 漏掉题号的情况)"""
    qs, expect = [], 1
    for s in rows:
        m = re.match(r"^(\d{1,3})\s*[\.．、]\s*(.*)$", s)
        if m and expect <= int(m.group(1)) <= expect + 3:
            n = int(m.group(1))
            qs.append([n, [m.group(2)]])
            expect = n + 1
        elif qs:
            qs[-1][1].append(s)
    return qs


OPT_RE = re.compile(r"(?<![A-Z/])([A-F])\s*[\.．、]")
ANS_RE = re.compile(r"[（(]\s*([A-F](?:\s*[A-F])*)\s*[)）]")
JUDGE_RE = re.compile(r"[（(]\s*([√×xXＸ✓✗vV])\s*[)）]")


def join_rows(rows):
    """接续换行: 两边都是英数字时才补空格"""
    out = ""
    for r in rows:
        if out and (re.match(r"[A-F]\s*[\.．、]", r) or
                    (re.match(r"[A-Za-z0-9]", r[:1]) and re.search(r"[A-Za-z0-9]$", out))):
            out += " "
        out += r
    return out


def parse_options(text):
    """在一段文字里找出 A. B. C. D. ... 顺序出现的位置"""
    found, want = [], "A"
    for m in OPT_RE.finditer(text):
        if m.group(1) == want:
            found.append(m)
            want = chr(ord(want) + 1)
    return found


def parse_choice(no, rows, qtype):
    # 题干: 直到第一个以 A. 开头的行
    stem, rest = [], []
    for i, s in enumerate(rows):
        if re.match(r"^A\s*[\.．、]", s):
            rest = rows[i:]
            break
        stem.append(s)
    stem_text = join_rows(stem)
    body = join_rows(rest)
    ms = parse_options(body)
    opts = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        opts.append({"key": m.group(1), "text": body[m.end():end].strip()})
    am = list(ANS_RE.finditer(stem_text))
    if not am:
        return None, f"{qtype} {no}: 找不到答案 :: {stem_text}"
    a = am[-1]
    ans = re.sub(r"\s", "", a.group(1))
    stem_text = stem_text[:a.start()] + "（　　）" + stem_text[a.end():]
    q = {"type": qtype, "no": no, "text": stem_text.strip(), "options": opts,
         "answer": ans if qtype == "single" else sorted(set(ans))}
    err = None
    keys = [o["key"] for o in opts]
    if len(opts) != 4 or any(not o["text"] for o in opts) or any(k not in keys for k in ans):
        err = f"{qtype} {no}: 选项异常 {keys} 答案 {ans}"
    if qtype == "single" and len(ans) != 1:
        err = f"{qtype} {no}: 单选答案异常 {ans}"
    return q, err


def parse_judge(no, rows):
    text = "".join(rows)
    ms = list(JUDGE_RE.finditer(text))
    if not ms:
        return None, f"judge {no}: 找不到答案 :: {text}"
    m = ms[-1]
    ans = "T" if m.group(1) in "√✓vV" else "F"
    stem = text[:m.start()].rstrip() + "（　　）"
    return {"type": "judge", "no": no, "text": stem,
            "options": [{"key": "T", "text": "正确 √"}, {"key": "F", "text": "错误 ×"}],
            "answer": ans}, None


def parse_short(no, rows):
    stem, ans, in_ans = [], [], False
    for s in rows:
        if not in_ans and s.startswith("参考答案"):
            in_ans = True
            tail = re.sub(r"^参考答案\s*[:：]?", "", s).strip()
            if tail: ans.append(tail)
            continue
        (ans if in_ans else stem).append(s)
    # 合并被换行截断的句子: 以 (n) 或 "xxx：" 开头的行另起一行, 其余接到上一行
    merged = []
    for s in ans:
        if not merged or re.match(r"^[（(]\s*\d+\s*[)）]|^[^，。；]{1,8}[:：]$", s):
            merged.append(s)
        else:
            merged[-1] += s
    return {"type": "short", "no": no, "text": "".join(stem), "answer": "\n".join(merged)}, None


EXPECTED = {"single": 500, "multi": 240, "judge": 230, "short": 30}


def parse_source(src):
    result = {}
    for qtype, rows in load_sections(src).items():
        for no, rws in split_questions(rows):
            if qtype in ("single", "multi"):
                q, e = parse_choice(no, rws, qtype)
            elif qtype == "judge":
                q, e = parse_judge(no, rws)
            else:
                q, e = parse_short(no, rws)
            result[(qtype, no)] = (q, e)
    return result


# 针对跨页或 OCR 字符轻微粘连的题目进行准确修补
MANUAL_PATCHES = {
    ("single", 264): {
        "type": "single", "no": 264,
        "text": "原毛接收表把“已脱水”和“已精洗”放在同一个勾选栏，采用以下（　　）方式能减少工序误认。",
        "options": [
            {"key": "A", "text": "分别记录已完成的工序，并与来料批次关联"},
            {"key": "B", "text": "把两种工序统一改为“前处理完成”一栏"},
            {"key": "C", "text": "只记录最近一次操作，不记录之前工序"},
            {"key": "D", "text": "按供方产品名称自动填“精洗”，不核对工序"}
        ],
        "answer": "A"
    },
    ("single", 334): {
        "type": "single", "no": 334,
        "text": "GB/T 10288-2026 实施日期为（　　）。",
        "options": [
            {"key": "A", "text": "2026-04-30"},
            {"key": "B", "text": "2026-09-01"},
            {"key": "C", "text": "2027-01-01"},
            {"key": "D", "text": "2026-07-01"}
        ],
        "answer": "B"
    },
    ("single", 418): {
        "type": "single", "no": 418,
        "text": "GB/T 17685-2026 中规定的AP 是指（　　）。",
        "options": [
            {"key": "A", "text": "辛基酚和壬基酚"},
            {"key": "B", "text": "甲基酚和乙基酚"},
            {"key": "C", "text": "丙基酚和丁基酚"},
            {"key": "D", "text": "苯酚和甲酚"}
        ],
        "answer": "A"
    },
    ("single", 457): {
        "type": "single", "no": 457,
        "text": "按照GB/T10288—2026，粗洗羽绒羽毛的总杂质包含（　　）。",
        "options": [
            {"key": "A", "text": "尾羽和脚皮"},
            {"key": "B", "text": "毛梗和脚皮"},
            {"key": "C", "text": "杂质和脚皮"},
            {"key": "D", "text": "毛梗和沙土"}
        ],
        "answer": "C"
    },
    ("multi", 131): {
        "type": "multi", "no": 131,
        "text": "GB/T17685-2026 规定烷基酚和烷基酚聚氧乙烯醚管控指标为（　　）。",
        "options": [
            {"key": "A", "text": "烷基酚（AP）总量应<10mg/kg"},
            {"key": "B", "text": "烷基酚聚氧乙烯醚（APnEO）的总量应<100mg/kg"},
            {"key": "C", "text": "烷基酚（AP）和烷基酚聚氧乙烯醚（APnEO）的总量应<100mg/kg"},
            {"key": "D", "text": "烷基酚（AP）和烷基酚聚氧乙烯醚（APnEO）的总量应≤100mg/kg"}
        ],
        "answer": ["A", "C"]
    },
    ("multi", 188): {
        "type": "multi", "no": 188,
        "text": "GB/T 17685-2026 中，“羽绒羽毛”的定义包含（　　）。",
        "options": [
            {"key": "A", "text": "绒子"},
            {"key": "B", "text": "绒丝"},
            {"key": "C", "text": "羽丝"},
            {"key": "D", "text": "损伤羽毛"}
        ],
        "answer": ["A", "B", "C", "D"]
    }
}

parsed = [parse_source(s) for s in SRCS]
questions, errors = [], []
for qtype, total in EXPECTED.items():
    for no in range(1, total + 1):
        if (qtype, no) in MANUAL_PATCHES:
            q = dict(MANUAL_PATCHES[(qtype, no)])
        else:
            cands = [p[(qtype, no)] for p in parsed if (qtype, no) in p]
            good = [q for q, e in cands if q and not e]
            if good:
                q = good[0]
            else:
                usable = [q for q, e in cands if q]
                errs = [e for q, e in cands if e]
                errors.append(f"[{qtype} {no}] " + (" || ".join(errs) if errs else "缺失"))
                if not usable:
                    continue
                q = usable[0]
        q["id"] = {"single": "S", "multi": "M", "judge": "J", "short": "Q"}[qtype] + str(no)
        questions.append(q)

for t in EXPECTED:
    print(t, sum(1 for q in questions if q["type"] == t), "/", EXPECTED[t])
print(f"Total parsed: {len(questions)}, errors: {len(errors)}")
Path(OUT.with_name("parse_errors.txt")).write_text("\n".join(errors), encoding="utf-8")
OUT.write_text(json.dumps(questions, ensure_ascii=False, indent=1), encoding="utf-8")
