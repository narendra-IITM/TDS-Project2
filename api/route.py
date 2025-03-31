from flask import Flask, request, jsonify
import os
import zipfile
import csv
import re
import requests
from io import TextIOWrapper

app = Flask(__name__)

FALLBACK_ANSWER = "42"
LLM_TIMEOUT = 25

def safe_eval(expr):
    """
    Evaluates a simple arithmetic expression safely.
    Allows only digits, operators +, -, *, /, decimal points, and spaces.
    """
    # Allow only these characters
    if re.fullmatch(r'[\d+\-*/\s.()]+', expr):
        try:
            # Evaluate expression using eval in a restricted environment
            result = eval(expr, {"__builtins__": {}})
            return str(result)
        except Exception as e:
            print("Arithmetic evaluation error:", e)
    return None

def query_llm(prompt):
    """
    Query the LLM using Hugging Face's distilgpt2 model.
    This function is used as a fallback for non-arithmetic questions.
    """
    hf_url = "https://api-inference.huggingface.co/models/distilgpt2"
    hf_token = os.getenv("HF_TOKEN")
    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    
    try:
        response = requests.post(hf_url, headers=headers, json={"inputs": prompt}, timeout=LLM_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        print("HuggingFace distilgpt2 response:", data)  # Debug output
        
        if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
            generated_text = data[0]["generated_text"].strip()
            # Attempt to extract a number from the response, if present.
            match = re.search(r'\d+', generated_text)
            if match:
                return match.group(0)
            else:
                return generated_text  # Fallback: return the whole text if no number is found.
        else:
            print("Unexpected response format:", data)
            return FALLBACK_ANSWER
    except requests.exceptions.HTTPError as http_err:
        error_details = (
            f"HTTP error: {http_err}\nStatus Code: {response.status_code}\nResponse: {response.text}"
        )
        print("HuggingFace API error:", error_details)
        return FALLBACK_ANSWER
    except Exception as e:
        print("HuggingFace API error:", e)
        return FALLBACK_ANSWER

def process_uploaded_file(file):
    """
    Processes an uploaded file (ZIP or CSV) to extract the 'answer' column.
    Assumes that the CSV file contains a column named 'answer'.
    """
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
        print("File processing error:", e)
    return None

def extract_arithmetic_answer(question):
    """
    If the question is a simple arithmetic problem like "What is 5+5?",
    extract the arithmetic expression and compute the answer.
    """
    # Regex to capture expressions after "What is" and before "?"
    match = re.search(r'What is\s+(.+?)\s*\?', question, re.IGNORECASE)
    if match:
        expr = match.group(1)
        print("Extracted arithmetic expression:", expr)
        result = safe_eval(expr)
        if result is not None:
            return result
    return None

@app.route('/api/', methods=['POST'])
def solve_question():
    question = request.form.get('question', '').strip()
    file = request.files.get('file')
    
    if not question and not file:
        return jsonify({"error": "No question or file provided"}), 400

    # If a file is uploaded, process it first.
    if file:
        file_answer = process_uploaded_file(file)
        if file_answer:
            return jsonify({'answer': file_answer})
    
    # Attempt to process arithmetic questions directly
    arithmetic_answer = extract_arithmetic_answer(question)
    if arithmetic_answer is not None:
        print("Arithmetic answer computed:", arithmetic_answer)
        return jsonify({'answer': arithmetic_answer})
    
    # For other questions, use the LLM endpoint
    prompt = (
        "You are an IIT Madras Data Science TA. Answer the following assignment question exactly as required for submission. "
        "Do not include any extra commentary—only provide the final answer.\n\n"
        f"Question: {question}\n"
        "Answer:"
    )
    answer = query_llm(prompt)
    return jsonify({'answer': answer})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
