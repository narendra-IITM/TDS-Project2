import os
import zipfile
import csv
import re
import requests
from io import BytesIO, TextIOWrapper
import json
from urllib.parse import parse_qs

FALLBACK_ANSWER = "42"
LLM_TIMEOUT = 25
HF_API_URL = "https://api-inference.huggingface.co/models/distilgpt2"

# ------------------ Core Logic (Unchanged) ------------------
def safe_eval(expr):
    """Your existing safe_eval implementation"""
    if re.fullmatch(r'[\d+\-*/\s.()]+', expr):
        try:
            return str(eval(expr, {"__builtins__": {}}))
        except Exception as e:
            print("Arithmetic error:", e)
    return None

def process_uploaded_file(content, filename):
    """Your file processing logic adapted for bytes"""
    try:
        buffer = BytesIO(content)
        if filename.endswith('.zip'):
            with zipfile.ZipFile(buffer) as z:
                for name in z.namelist():
                    if name.endswith('.csv'):
                        with z.open(name) as f:
                            return next(csv.DictReader(TextIOWrapper(f)))['answer']
        else:
            return next(csv.DictReader(TextIOWrapper(buffer)))['answer']
    except Exception as e:
        print("File error:", e)
        return None

def extract_arithmetic_answer(question):
    """Your existing arithmetic extraction"""
    match = re.search(r'What is\s+(.+?)\s*\?', question, re.I)
    return safe_eval(match.group(1)) if match else None

# ------------------ Model Integration ------------------
def query_llm(prompt):
    """Enhanced model query with error handling"""
    headers = {"Authorization": f"Bearer {os.getenv('HF_TOKEN')}"}
    
    try:
        response = requests.post(
            HF_API_URL,
            headers=headers,
            json={"inputs": prompt},
            timeout=LLM_TIMEOUT
        )
        response.raise_for_status()
        
        result = response.json()
        if isinstance(result, list) and result:
            text = result[0].get('generated_text', FALLBACK_ANSWER)
            return re.search(r'\d+', text).group(0) if re.search(r'\d+', text) else text[:100]
        
        return FALLBACK_ANSWER
    
    except requests.exceptions.RequestException as e:
        print(f"Model API Error: {str(e)}")
        return FALLBACK_ANSWER

# ------------------ Vercel Handler ------------------
def handler(event, context):
    try:
        # Handle CORS preflight
        if event['httpMethod'] == 'OPTIONS':
            return {
                'statusCode': 204,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                }
            }

        # Parse request
        content_type = event.get('headers', {}).get('content-type', '')
        body = event.get('body', '').encode()
        
        # Process multipart/form-data
        if 'multipart/form-data' in content_type:
            boundary = content_type.split('boundary=')[-1].encode()
            parts = body.split(b'--' + boundary)
            data, files = {}, {}
            
            for part in parts[1:-1]:
                if b'\r\n\r\n' in part:
                    headers, content = part.split(b'\r\n\r\n', 1)
                    headers = headers.decode().split('\r\n')
                    
                    name = filename = None
                    for header in headers:
                        if 'Content-Disposition' in header:
                            for item in header.split(';'):
                                if 'name=' in item:
                                    name = item.split('=')[1].strip('"')
                                if 'filename=' in item:
                                    filename = item.split('=')[1].strip('"')
                    
                    if filename:
                        files[name] = (filename, content.strip(b'\r\n'))
                    elif name:
                        data[name] = content.strip(b'\r\n').decode()
        else:
            data = parse_qs(body.decode())
            data = {k: v[0] for k, v in data.items()}

        # Process inputs
        response = {}
        question = data.get('question', '')
        
        # File processing
        if 'file' in files:
            filename, content = files['file']
            if file_answer := process_uploaded_file(content, filename):
                response['answer'] = file_answer
        
        # Question processing
        if question and not response:
            if arithmetic_answer := extract_arithmetic_answer(question):
                response['answer'] = arithmetic_answer
            else:
                prompt = (
                    "You are an IIT Madras Data Science TA. Answer exactly as required.\n\n"
                    f"Question: {question}\nAnswer:"
                )
                response['answer'] = query_llm(prompt)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json', 
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(response or {'error': 'No valid input'})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
