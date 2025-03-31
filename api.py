from flask import Flask, request, jsonify
import os
import zipfile
import pandas as pd
import tempfile
import requests
import time
import json  # Added for better error inspection

app = Flask(__name__)

# Configuration
MAX_RETRIES = 3
LLM_TIMEOUT = 30  # Increased timeout
FALLBACK_ANSWER = "42"

def debug_log(message):
    """Helper for debug output"""
    print(f"[DEBUG] {message}")
    with open("debug.log", "a") as f:
        f.write(f"{time.ctime()}: {message}\n")

def query_openrouter(prompt):
    """Improved OpenRouter query with detailed error handling"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            debug_log(f"Sending to OpenRouter: {prompt[:100]}...")
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": "Bearer free",
                    "HTTP-Referer": "http://localhost:5000",  # Changed to localhost
                    "X-Title": "IITM TDS Debug"
                },
                json={
                    "model": "mistralai/mistral-7b-instruct",
                    "messages": [{
                        "role": "system",
                        "content": "You are answering IIT Madras Data Science assignments. Return ONLY the exact value needed."
                    }, {
                        "role": "user",
                        "content": prompt
                    }],
                    "temperature": 0.1
                },
                timeout=LLM_TIMEOUT
            )
            
            debug_log(f"Raw response: {response.text[:200]}...")
            data = response.json()
            
            if 'choices' in data:
                answer = data['choices'][0]['message']['content'].strip()
                debug_log(f"Extracted answer: {answer}")
                return answer
            else:
                debug_log(f"Unexpected response format: {json.dumps(data, indent=2)}")
                return None
                
        except requests.exceptions.RequestException as e:
            debug_log(f"Request failed (attempt {retries+1}): {str(e)}")
            retries += 1
            time.sleep(2)
        except Exception as e:
            debug_log(f"Unexpected error: {str(e)}")
            return None
    
    return None

def get_llm_answer(question):
    """Get answer with detailed debugging"""
    prompt = f"Question: {question}\nAnswer: "
    debug_log(f"\nNew Question: {question}")
    
    answer = query_openrouter(prompt)
    
    if answer:
        debug_log(f"Final answer: {answer}")
        return answer
    else:
        debug_log("Using fallback answer")
        return FALLBACK_ANSWER

@app.route('/api/', methods=['POST'])
def solve_question():
    question = request.form.get('question', '').strip()
    debug_log(f"Received question: {question}")
    return jsonify({'answer': get_llm_answer(question)})

if __name__ == '__main__':
    debug_log("\n\n=== Starting Server ===")
    app.run(host='0.0.0.0', port=5000, debug=True)
