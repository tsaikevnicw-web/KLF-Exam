import json
import re

def clean_brackets(text):
    # 移除题目末尾或中间的答案括号：（　　）、（ ）、()、（）、( ) 等
    text = re.sub(r'[（(]\s*[)）]\s*[。.]?\s*$', '', text)
    text = re.sub(r'[（(]\s*[\u3000\s]*[)）]\s*[。.]?\s*$', '', text)
    text = re.sub(r'[（(]\s*[\u3000\s]*[)）]', '', text)
    text = text.rstrip()
    if not text.endswith(('。', '？', '！', '：', ':', '?', '!')):
        text += '。'
    return text

print("Cleaning parentheses from questions.json (keeping original Simplified Chinese)...")
raw_questions = json.load(open('questions.json', 'r', encoding='utf-8'))

for q in raw_questions:
    q['text'] = clean_brackets(q['text'])

with open('questions.json', 'w', encoding='utf-8') as f:
    json.dump(raw_questions, f, ensure_ascii=False, indent=1)

print("questions.json successfully updated without parentheses in Simplified Chinese!")
