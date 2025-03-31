from flask import Flask, request, jsonify
import os
import zipfile
import csv
import requests
from io import TextIOWrapper

app = Flask(__name__)

FALLBACK_ANSWER = "42"
LLM_TIMEOUT = 25

def query_llm(prompt):
    """Simplified LLM query"""
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1",
            headers={"Authorization": f"Bearer {os.getenv('HF_TOKEN')}"},
            json={"inputs": prompt},
            timeout=LLM_TIMEOUT
        )
        return response.json()[0]['generated_text'].split("Answer:")[-1].strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        return FALLBACK_ANSWER

def process_uploaded_file(file):
    """Pure Python CSV processor"""
    try:
        if file.filename.endswith('.zip'):
            with zipfile.ZipFile(file) as z:
                for name in z.namelist():
                    if name.endswith('.csv'):
                        with z.open(name) as f:
                            reader = csv.DictReader(TextIOWrapper(f))
                            return next(reader)['answer']
        else:
            reader = csv.DictReader(TextIOWrapper(file))
            return next(reader)['answer']
    except Exception as e:
        print(f"File Error: {e}")
    return None

@app.route('/api/', methods=['POST'])
def solve_question():
    question = request.form.get('question', '').strip()
    file = request.files.get('file')
    
    if file:
        file_answer = process_uploaded_file(file)
        if file_answer:
            return jsonify({'answer': file_answer})
    
    prompt = f"Question: {question}\nAnswer: "
    return jsonify({'answer': query_llm(prompt)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
