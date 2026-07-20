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

# UPDATED AI ROUTE — ab AI khud "guess" nahi karta, sirf jo bhi text dikh raha hai
# usko transcribe karta hai. Exact decode index.html mein deterministic logic se hota hai
# (S.sensor array wali line se — yehi asli code hota hai, AI ke bharose nahi chhodte).
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

        prompt = """Ye ek iPhone panic-log crash report ki photo hai (chahe angle se li ho, dhundhli ho, andheri ho, background mein haath/table dikh raha ho — jo bhi ho).

Tumhara kaam: is photo mein jitna bhi panic/crash text (panicString) visible hai, use BILKUL WAISA HI, jaisa likha hai, transcribe karo. Khaaskar dhyan rakhna in cheezon ka agar dikhein:
- "S.sensor array 0 - N is ..." wali poori line (numbers exactly jaise likhe hain, comma samet)
- "F.sensor array ..." line
- "Missing sensor(s): ..." line
- "SMC PANIC", "AOP PANIC", "DCP PANIC", "SCMto", "userspace watchdog timeout" jaise keywords
- koi bhi 0x hex code ya panic identifier

Sirf transcribed text return karo — koi explanation, koi "here is the text", koi markdown formatting nahi. Agar text bilkul illegible/unreadable hai to sirf "UNREADABLE" likhna."""

        # New stable model execution
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )

        if not response or not response.text:
            return jsonify({'success': False, 'error': "AI response khali mila."}), 500

        extracted_text = response.text.strip()
        return jsonify({'success': True, 'text': extracted_text})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
