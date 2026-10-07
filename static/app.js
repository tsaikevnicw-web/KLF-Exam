const TYPE_NAME = { single: "单选题", multi: "多选题", judge: "判断题", short: "简答题" };
const form = document.getElementById("exam");
const gradeBtn = document.getElementById("gradeBtn");
const newBtn = document.getElementById("newBtn");
const scoreBox = document.getElementById("scoreBox");
const docxBanner = document.getElementById("docxBanner");
const downloadDocxLink = document.getElementById("downloadDocxLink");
const historyBtn = document.getElementById("historyBtn");
const historyCountSpan = document.getElementById("historyCount");
const historyModal = document.getElementById("historyModal");
const closeModalBtn = document.getElementById("closeModalBtn");
const historyList = document.getElementById("historyList");
const historyDetail = document.getElementById("historyDetail");
const backToListBtn = document.getElementById("backToListBtn");
const detailContent = document.getElementById("detailContent");

let exam = null;        // {examId, points, questions}
let selfScore = {};     // 简答题自评: id -> true/false
let currentResults = null;
let currentAnswers = null;

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// 考试记录存取 (localStorage)
const STORAGE_KEY = "KLF_EXAM_HISTORY_V1";
function getHistory() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch (e) {
    return [];
  }
}

function saveHistoryItem(item) {
  const list = getHistory();
  list.unshift(item); // 最新的放最前
  if (list.length > 50) list.pop(); // 最多存50笔
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  updateHistoryCount();
}

function updateHistoryCount() {
  const list = getHistory();
  if (historyCountSpan) historyCountSpan.textContent = list.length;
}

let fullQuestionBank = null;

async function getQuestionBank() {
  if (fullQuestionBank) return fullQuestionBank;
  try {
    const res = await fetch("questions.json");
    fullQuestionBank = await res.json();
    return fullQuestionBank;
  } catch (e) {
    console.error("Failed to load questions.json", e);
    return [];
  }
}

async function loadExam() {
  scoreBox.classList.add("hidden");
  if (docxBanner) docxBanner.classList.add("hidden");
  form.classList.remove("graded");
  gradeBtn.disabled = false;
  selfScore = {};
  currentResults = null;
  currentAnswers = null;
  form.innerHTML = '<div class="card">出卷中…</div>';

  try {
    // 优先尝试本地后端 API
    const res = await fetch("/api/exam", { cache: "no-store" });
    if (res.ok) {
      exam = await res.json();
    } else {
      throw new Error("API not available, fallback to static mode");
    }
  } catch (e) {
    // GitHub Pages 纯静态模式：直接从 questions.json 随机抽取 20 题
    const bank = await getQuestionBank();
    const shuffled = [...bank].sort(() => 0.5 - Math.random());
    const picked = shuffled.slice(0, 20);
    const examId = "exam_" + Math.random().toString(36).substring(2, 10);
    exam = {
      examId: examId,
      points: 5,
      isStatic: true,
      questions: picked.map(q => {
        const copy = Object.assign({}, q);
        delete copy.answer;
        return copy;
      }),
      _fullPicked: picked // 仅本地評分用
    };
  }

  render();
  window.scrollTo({ top: 0 });
}

function render() {
  form.innerHTML = exam.questions.map((q, i) => {
    let body = "";
    if (q.type === "short") {
      body = `<textarea name="${q.id}" placeholder="请在此作答…"></textarea>`;
    } else {
      const inputType = q.type === "multi" ? "checkbox" : "radio";
      body = q.options.map(o => `
        <label class="opt" data-key="${esc(o.key)}">
          <input type="${inputType}" name="${q.id}" value="${esc(o.key)}">
          ${q.type === "judge" ? "" : `<span class="key">${esc(o.key)}.</span>`}
          <span>${esc(o.text)}</span>
        </label>`).join("");
    }
    return `
      <div class="card" id="card-${q.id}">
        <div class="q-head">
          <span class="q-no">${i + 1}.</span>
          <span class="q-type">${TYPE_NAME[q.type]}</span>
          <span class="q-text">${esc(q.text)}</span>
          <span class="q-mark"></span>
        </div>
        ${body}
      </div>`;
  }).join("");
}

function collectAnswers() {
  const answers = {};
  for (const q of exam.questions) {
    if (q.type === "short") {
      answers[q.id] = form.querySelector(`textarea[name="${q.id}"]`).value.trim();
    } else if (q.type === "multi") {
      answers[q.id] = [...form.querySelectorAll(`input[name="${q.id}"]:checked`)].map(i => i.value);
    } else {
      const el = form.querySelector(`input[name="${q.id}"]:checked`);
      answers[q.id] = el ? el.value : null;
    }
  }
  return answers;
}

async function grade() {
  try {
    const answers = collectAnswers();
    const blank = exam.questions.filter(q => {
      const a = answers[q.id];
      return a == null || a === "" || (Array.isArray(a) && a.length === 0);
    }).length;
    if (blank && !confirm(`还有 ${blank} 题未作答，确定要交卷评分吗？`)) return;

    let results = [];
    if (exam.isStatic || !exam.examId || exam.examId.startsWith("exam_")) {
      // 纯静态模式评分：直接对照题目标准答案
      const fullBank = await getQuestionBank();
      const bankMap = {};
      fullBank.forEach(q => { bankMap[q.id] = q; });

      for (const q of exam.questions) {
        const fullQ = bankMap[q.id] || (exam._fullPicked ? exam._fullPicked.find(x => x.id === q.id) : null) || q;
        const correctAns = fullQ.answer;
        const given = answers[q.id];

        if (q.type === "short") {
          results.push({ id: q.id, answer: correctAns || "（请核对标准答案）", correct: null });
        } else if (q.type === "multi") {
          const target = Array.isArray(correctAns) ? correctAns : [correctAns];
          const isOk = Array.isArray(given) &&
            given.length === target.length &&
            [...given].sort().join("") === [...target].sort().join("");
          results.push({ id: q.id, answer: target, correct: isOk });
        } else {
          results.push({ id: q.id, answer: correctAns, correct: given === correctAns });
        }
      }
    } else {
      const res = await fetch("/api/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ examId: exam.examId, answers }),
      });
      const data = await res.json();
      if (data.error) { alert(data.error); return; }
      results = data.results;
    }

    form.classList.add("graded");
    gradeBtn.disabled = true;
    form.querySelectorAll("input, textarea").forEach(el => el.disabled = true);

    currentResults = results;
    currentAnswers = answers;

    for (const r of results) {
      const q = exam.questions.find(x => x.id === r.id);
      if (!q) continue;
      const card = document.getElementById("card-" + r.id);
      if (!card) continue;
      const mark = card.querySelector(".q-mark");

      if (q.type === "short") {
        const ref = document.createElement("div");
        ref.className = "ref";
        ref.textContent = "参考答案：\n" + r.answer;
        card.appendChild(ref);
        const sg = document.createElement("div");
        sg.className = "self-grade";
        sg.innerHTML = `简答题请对照参考答案自评：
          <button type="button" data-v="1">答对 +${exam.points}</button>
          <button type="button" data-v="0">答错</button>`;
        sg.addEventListener("click", e => {
          const b = e.target.closest("button"); if (!b) return;
          selfScore[r.id] = b.dataset.v === "1";
          sg.querySelectorAll("button").forEach(x => x.className = "");
          b.className = selfScore[r.id] ? "on-ok" : "on-bad";
          if (mark) {
            mark.textContent = selfScore[r.id] ? "✓ 正确" : "✗ 错误";
            mark.className = "q-mark " + (selfScore[r.id] ? "ok" : "bad");
          }
          updateScore(results);
          recordHistory();
        });
        card.appendChild(sg);
        if (mark) mark.textContent = "待自评";
        continue;
      }

      if (mark) {
        mark.textContent = r.correct ? `✓ +${exam.points}` : "✗ 0";
        mark.className = "q-mark " + (r.correct ? "ok" : "bad");
      }

      if (!r.correct) {
        const right = Array.isArray(r.answer) ? r.answer : [r.answer];
        const given = answers[r.id] == null ? [] : [].concat(answers[r.id]);
        card.querySelectorAll(".opt").forEach(opt => {
          const k = opt.dataset.key;
          if (right.includes(k)) opt.classList.add("correct");
          else if (given.includes(k)) opt.classList.add("wrong");
        });
        if (given.length === 0) {
          const n = document.createElement("div");
          n.className = "unanswered";
          n.textContent = "（未作答）";
          card.appendChild(n);
        }
      }
    }

    // 解锁 DOCX 下载链接
    if (docxBanner && downloadDocxLink) {
      if (exam.isStatic || !exam.examId || exam.examId.startsWith("exam_")) {
        downloadDocxLink.href = "KLF_羽绒行业理论考试题库_完整1000题.docx";
        downloadDocxLink.setAttribute("download", "KLF_羽绒行业理论考试题库_完整1000题.docx");
      } else {
        downloadDocxLink.href = `/api/download_docx?examId=${encodeURIComponent(exam.examId)}`;
      }
      docxBanner.classList.remove("hidden");
    }

    updateScore(results);
    recordHistory();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    console.error("Grade execution error:", err);
    alert("评分执行出错：" + (err.message || err));
  }
}

function updateScore(results) {
  let right = 0, wrong = 0, pending = 0;
  for (const r of results) {
    const ok = r.correct === null ? selfScore[r.id] : r.correct;
    if (ok === undefined) pending++;
    else if (ok) right++;
    else wrong++;
  }
  scoreBox.classList.remove("hidden");
  scoreBox.innerHTML = `
    <div>本次得分</div>
    <div class="big">${right * exam.points} <small style="font-size:18px">/ ${results.length * exam.points}</small></div>
    <div class="detail">答对 ${right} 题 · 答错 ${wrong} 题${pending ? ` · 简答题待自评 ${pending} 题` : ""}</div>`;
}

// 记录到本地历史
function recordHistory() {
  if (!exam || !currentResults) return;
  let right = 0, wrong = 0, pending = 0;
  for (const r of currentResults) {
    const ok = r.correct === null ? selfScore[r.id] : r.correct;
    if (ok === undefined) pending++;
    else if (ok) right++;
    else wrong++;
  }
  
  const historyItem = {
    id: exam.examId,
    timestamp: new Date().toLocaleString(),
    score: right * exam.points,
    totalScore: currentResults.length * exam.points,
    rightCount: right,
    wrongCount: wrong,
    pendingCount: pending,
    questions: exam.questions,
    results: currentResults,
    answers: currentAnswers,
    selfScore: Object.assign({}, selfScore)
  };

  // 若已存在相同 examId 则更新，否则添加
  const list = getHistory();
  const idx = list.findIndex(x => x.id === exam.examId);
  if (idx >= 0) {
    list[idx] = historyItem;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    updateHistoryCount();
  } else {
    saveHistoryItem(historyItem);
  }
}

// 弹窗与记录展示
function openHistoryModal() {
  renderHistoryList();
  historyDetail.classList.add("hidden");
  historyList.classList.remove("hidden");
  historyModal.classList.remove("hidden");
}

function closeHistoryModal() {
  historyModal.classList.add("hidden");
}

function renderHistoryList() {
  const list = getHistory();
  if (list.length === 0) {
    historyList.innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px;">暂无历史考试记录，快去完成一次测验吧！</div>';
    return;
  }
  historyList.innerHTML = list.map((item, idx) => `
    <div class="history-item" onclick="viewHistoryDetail(${idx})">
      <div>
        <div class="history-date">📅 ${item.timestamp}</div>
        <div class="history-stats">答对 ${item.rightCount} 题 · 答错 ${item.wrongCount} 题${item.pendingCount ? ` · 待自评 ${item.pendingCount} 题` : ""}</div>
      </div>
      <div style="text-align:right;">
        <div class="history-score">${item.score} / ${item.totalScore} 分</div>
        <small style="color:var(--accent-dark)">点击查看考题详情 →</small>
      </div>
    </div>
  `).join("");
}

window.viewHistoryDetail = function(idx) {
  const list = getHistory();
  const item = list[idx];
  if (!item) return;

  historyList.classList.add("hidden");
  historyDetail.classList.remove("hidden");

  let detailHtml = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:16px;">
      <div style="font-size:18px;font-weight:700;color:var(--accent-dark);">${item.timestamp} 模拟考试回顾</div>
      <div style="font-size:24px;font-weight:700;margin:4px 0;">得分：${item.score} / ${item.totalScore} 分</div>
      <div style="color:var(--muted);font-size:13px;">答对 ${item.rightCount} 题 · 答错 ${item.wrongCount} 题</div>
      <div style="margin-top:10px;">
        <a href="${item.id && item.id.startsWith('exam_') ? 'KLF_羽绒行业理论考试题库_完整1000题.docx' : '/api/download_docx?examId=' + encodeURIComponent(item.id)}" ${item.id && item.id.startsWith('exam_') ? 'download="KLF_羽绒行业理论考试题库_完整1000题.docx"' : ''} target="_blank" class="btn primary-small">📥 打开 / 下载题库 Word 档</a>
      </div>
    </div>
  `;

  detailHtml += item.questions.map((q, qIdx) => {
    const res = item.results.find(r => r.id === q.id) || {};
    const ans = item.answers ? item.answers[q.id] : null;
    let isCorrect = res.correct;
    if (q.type === 'short') {
      isCorrect = item.selfScore ? item.selfScore[q.id] : null;
    }

    let borderClass = isCorrect === true ? "ok-border" : (isCorrect === false ? "bad-border" : "pending-border");
    let statusText = isCorrect === true ? "<span style='color:var(--ok);font-weight:600;'>✓ 答对</span>" :
                     (isCorrect === false ? "<span style='color:var(--bad);font-weight:600;'>✗ 答错</span>" :
                     "<span style='color:var(--muted);'>待自评</span>");

    let optionsHtml = "";
    if (q.type === 'short') {
      optionsHtml = `
        <div style="margin:8px 0;background:#fcfbf8;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:14px;">
          <strong>考生作答：</strong>${esc(ans || "（未作答）")}
        </div>
        <div class="ref" style="font-size:14px;margin-top:6px;">参考答案：\n${esc(res.answer || "")}</div>
      `;
    } else {
      const rightKeys = Array.isArray(res.answer) ? res.answer : [res.answer];
      const givenKeys = ans == null ? [] : [].concat(ans);
      optionsHtml = q.options.map(opt => {
        let optClass = "opt";
        if (rightKeys.includes(opt.key)) optClass += " correct";
        else if (givenKeys.includes(opt.key)) optClass += " wrong";
        return `
          <div class="${optClass}" style="cursor:default;margin:3px 0;">
            ${q.type === "judge" ? "" : `<span class="key">${esc(opt.key)}.</span>`}
            <span>${esc(opt.text)}</span>
            ${givenKeys.includes(opt.key) ? "<span style='margin-left:auto;font-size:12px;opacity:0.8;'>(你的选择)</span>" : ""}
          </div>
        `;
      }).join("");
    }

    return `
      <div class="history-detail-item ${borderClass}">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">
          <div>
            <strong>${qIdx + 1}.</strong>
            <span class="q-type" style="margin:0 6px;">${TYPE_NAME[q.type]}</span>
            <span>${esc(q.text)}</span>
          </div>
          <div>${statusText}</div>
        </div>
        ${optionsHtml}
      </div>
    `;
  }).join("");

  detailContent.innerHTML = detailHtml;
};

backToListBtn.addEventListener("click", () => {
  historyDetail.classList.add("hidden");
  historyList.classList.remove("hidden");
});

historyBtn.addEventListener("click", openHistoryModal);
closeModalBtn.addEventListener("click", closeHistoryModal);
historyModal.addEventListener("click", (e) => {
  if (e.target === historyModal) closeHistoryModal();
});

gradeBtn.addEventListener("click", grade);
newBtn.addEventListener("click", () => {
  if (!form.classList.contains("graded") && !confirm("确定放弃本卷并重新出卷吗？")) return;
  loadExam();
});

updateHistoryCount();
loadExam();

