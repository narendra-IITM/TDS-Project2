import os
import zipfile
import csv
import re
import requests
from io import BytesIO
import json

FALLBACK_ANSWER = "42"
LLM_TIMEOUT = 25

# Keep your existing safe_eval, query_llm, and extract_arithmetic_answer functions

def process_uploaded_file(file_content, filename):
    """Modified for Vercel's byte-based file handling"""
    try:
        file_bytes = BytesIO(file_content)
        
        if filename.endswith('.zip'):
            with zipfile.ZipFile(file_bytes) as z:
                for name in z.namelist():
                    if name.endswith('.csv'):
                        with z.open(name) as f:
                            reader = csv.DictReader(TextIOWrapper(f))
                            return next(reader)['answer']
        else:
            reader = csv.DictReader(TextIOWrapper(file_bytes))
            return next(reader)['answer']
    except Exception as e:
        print("File processing error:", e)
        return None

def parse_multipart(body, boundary):
    """Parse multipart/form-data manually"""
    parts = body.split(b'--' + boundary)
    data = {}
    files = {}
    
    for part in parts[1:-1]:  # Skip first and last empty parts
        if b'\r\n\r\n' not in part:
            continue
            
        headers, content = part.split(b'\r\n\r\n', 1)
        headers = headers.decode().split('\r\n')
        name = None
        filename = None
        
        for header in headers:
            if 'Content-Disposition' in header:
                items = header.split(';')
                for item in items:
                    if 'name=' in item:
                        name = item.split('=')[1].strip('"')
                    if 'filename=' in item:
                        filename = item.split('=')[1].strip('"')
        
        if filename:
            files[name] = (filename, content.strip(b'\r\n'))
        elif name:
            data[name] = content.strip(b'\r\n').decode()
    
    return data, files

def handler(event, context):
    """Vercel serverless function entry point"""
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
        body = event.get('body', '').encode() if event.get('body') else b''
        
        if 'multipart/form-data' in content_type:
            boundary = content_type.split('boundary=')[-1].encode()
            data, files = parse_multipart(body, boundary)
        else:
            data = parse_qs(body.decode())
            data = {k: v[0] for k, v in data.items()}

        # Process request
        question = data.get('question', '')
        file_info = files.get('file', (None, None))
        response = {}

        # File processing
        if file_info[0] and file_info[1]:
            filename, content = file_info
            file_answer = process_uploaded_file(content, filename)
            if file_answer:
                response['answer'] = file_answer

        # Question processing
        if question and not response:
            if arithmetic_answer := extract_arithmetic_answer(question):
                response['answer'] = arithmetic_answer
            else:
                prompt = f"Question: {question}\nAnswer:"
                response['answer'] = query_llm(prompt)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(response if response else {'error': 'No valid input'})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
