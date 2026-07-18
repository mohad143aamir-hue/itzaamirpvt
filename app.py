from flask import Flask, render_template, request, jsonify
import json  # Python ka built-in json library
import os

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

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
    
    # Har request par naya data load hoga taaki file me badlav turant dikhe
    panic_database = load_database()
    
    if code in panic_database:
        return jsonify({"status": "success", "data": panic_database[code]})
    else:
        return jsonify({"status": "error", "message": "Yeh code abhi database me nahi hai!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)