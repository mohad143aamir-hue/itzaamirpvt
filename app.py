import os
import io
import json
from flask import Flask, render_template, request, jsonify
from PIL import Image
from google import genai

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

# New 2026 SDK Method: Yeh automatic Render ke Environment Variable se chabi utha lega
client = genai.Client()

# JSON file se data load karne ka function
def load_database():
    file_path = os.path.join(os.path.dirname(__file__), 'data.json')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/decode', methods=['POST'])
def decode():
    data = request.json
    code = data.get('code', '').strip().upper()
    panic_database = load_database()
    if code in panic_database:
        return jsonify({"status": "success", "data": panic_database[code]})
    else:
        return jsonify({"status": "error", "message": "Yeh code abhi database me nahi hai!"})

# NEW UPDATED AI ROUTE
@app.route('/scan-panic', methods=['POST'])
def scan_panic():
    if 'panic_image' not in request.files:
        return jsonify({'success': False, 'error': 'Koi photo select nahi ki gayi'}), 400
        
    file = request.files['panic_image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'File name khali hai'}), 400

    try:
        image_bytes = file.read()
        image = Image.open(io.BytesIO(image_bytes))

        prompt = """
        You are an expert iPhone motherboard repair technician. Analyze this panic log image carefully.
        Look closely at the 'panicString', 'SMC PANIC - ASSERT', 'DCP PANIC', 'AOP PANIC', 
        or hex codes (like 0x40000, 0x80000), or sensor names (like TB0T, TG0B, mic1, mic2, Prs0, AppleSPMIController).
        
        Extract ONLY the primary error code, hex string, or sensor name that identifies the hardware fault.
        Return ONLY the extracted code string itself (e.g., '0X80000' or 'TG0B' or 'DCP PANIC' or 'AppleSPMIController').
        Do not write full sentences, do not include markdown, just return the raw text of the code.
        """

        # New stable model execution
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )

        if not response or not response.text:
            return jsonify({'success': False, 'error': "AI response khali mila."}), 500

        extracted_code = response.text.strip()
        return jsonify({'success': True, 'code': extracted_code})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
