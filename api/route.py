from flask import Flask, request, jsonify, Request
import os
import zipfile
import pandas as pd
import requests
import io
import re
from werkzeug.datastructures import FileStorage

app = Flask(__name__)

# Configuration
FALLBACK_ANSWER = "42"
LLM_TIMEOUT = 25

# Free LLM endpoints with fallback priority
LLM_ENDPOINTS = [
    {
        "name": "HuggingFace",
        "url": "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1",
        "headers": {"Authorization": f"Bearer {os.getenv('HF_TOKEN')}"},
        "payload": lambda prompt: {"inputs": prompt}
    },
    {
        "name": "OpenRouter",
        "url": "https://api.openrouter.ai/api/v1/chat/completions",
        "headers": {
            "Authorization": "Bearer free",
            "HTTP-Referer": "https://tds-solver.vercel.app",
            "X-Title": "IITM TDS Project"
        },
        "payload": lambda prompt: {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [{
                "role": "system", 
                "content": "You are a precise calculator. Return ONLY the numerical answer with no explanations."
            },{
                "role": "user",
                "content": prompt
            }]
        }
    }
]

def looks_like_math(text):
    """Check if question is simple arithmetic"""
    math_pattern = r"(what is|calculate|solve)\s+(\d+\s*[-+*/]\s*\d+)"
    return re.search(math_pattern, text.lower()) is not None

def calculate_math(text):
    """Solve simple math problems directly"""
    try:
        math_expr = re.search(r"(\d+\s*[-+*/]\s*\d+)", text.lower()).group(1)
        return str(eval(math_expr.replace(' ', '')))
    except:
        return None

def parse_llm_response(data):
    """Extract answer from different LLM response formats"""
    if isinstance(data, list) and "generated_text" in data[0]:  # HuggingFace
        return data[0]["generated_text"].split("Answer:")[-1].strip(' "\n')
    elif "choices" in data:  # OpenRouter
        content = data["choices"][0]["message"]["content"]
        return content.strip(' "\n')
    return None

def query_llm(prompt):
    """Enhanced LLM query with math detection"""
    # First try direct math calculation
    if looks_like_math(prompt):
        math_answer = calculate_math(prompt)
        if math_answer:
            return math_answer
    
    # Fall back to LLM for complex questions
    for endpoint in LLM_ENDPOINTS:
        try:
            response = requests.post(
                endpoint["url"],
                headers=endpoint["headers"],
                json=endpoint["payload"](prompt),
                timeout=LLM_TIMEOUT
            )
            answer = parse_llm_response(response.json())
            if answer and answer.lower() not in ["error", "none"]:
                return answer
        except Exception as e:
            print(f"{endpoint['name']} failed: {str(e)}")
    
    return FALLBACK_ANSWER

def process_uploaded_file(file):
    """Handle ZIP/CSV files in memory"""
    try:
        file_bytes = io.BytesIO(file.read())
        
        if file.filename.endswith('.zip'):
            with zipfile.ZipFile(file_bytes) as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.endswith('.csv'):
                        with zip_ref.open(file_info) as csv_file:
                            df = pd.read_csv(csv_file)
                            if 'answer' in df.columns:
                                return str(df['answer'].iloc[0])
        else:
            df = pd.read_csv(file_bytes)
            if 'answer' in df.columns:
                return str(df['answer'].iloc[0])
    except Exception as e:
        print(f"File processing error: {e}")
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
    llm_answer = query_llm(prompt)
    return jsonify({'answer': llm_answer})

# Vercel Serverless Adapter
def vercel_handler(req):
    with app.app_context():
        if req.method == 'POST':
            flask_request = Request.from_values(
                method=req.method,
                headers=req.headers,
                data=req.body,
                content_type=req.headers.get('content-type'),
                mimetype=req.headers.get('content-type')
            )
            
            if req.files and 'file' in req.files:
                flask_request.files = {'file': FileStorage(
                    stream=io.BytesIO(req.files['file'].read()),
                    filename=req.files['file'].filename,
                    content_type=req.files['file'].content_type
                )}
            
            if req.form and 'question' in req.form:
                flask_request.form = {'question': req.form['question']}
            
            with app.request_context(flask_request.environ):
                return solve_question()
        
        return jsonify({'error': 'Method not allowed'}), 405

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
