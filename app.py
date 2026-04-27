from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from flask_cors import CORS
import os
import groq_analyzer
import json
import pandas as pd
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Ensure upload directory exists
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    files_to_process = []
    
    # CASE 1: File Uploads (FormData)
    if 'files' in request.files:
        uploaded_files = request.files.getlist('files')
        for file in uploaded_files:
            path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(path)
            files_to_process.append((path, True)) # (path, should_delete)

    # CASE 2: Folder Path (JSON)
    elif request.is_json:
        data = request.json
        folder = data.get('folder_path')
        if folder and os.path.isdir(folder):
            paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith((".pdf", ".docx"))]
            for p in paths:
                files_to_process.append((p, False))

    if not files_to_process:
        return jsonify({"success": False, "error": "No valid resumes or folder path provided"}), 400

    total = len(files_to_process)

    def generate():
        results = []
        for i, (f_path, should_delete) in enumerate(files_to_process):
            try:
                res = groq_analyzer.process_single_resume(f_path)
                if res:
                    results.append(res)
                
                # Send progress update
                progress_data = {
                    "type": "progress",
                    "current": i + 1,
                    "total": total,
                    "file": os.path.basename(f_path)
                }
                yield f"data: {json.dumps(progress_data)}\n\n"
            finally:
                if should_delete and os.path.exists(f_path):
                    os.remove(f_path)

        # Final result and Excel generation
        excel_name = f"analysis_{datetime.now().strftime('%H%M%S')}.xlsx"
        pd.DataFrame(results).to_excel(excel_name, index=False)
        
        final_data = {
            "type": "done",
            "results": results,
            "excel_file": excel_name
        }
        yield f"data: {json.dumps(final_data)}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/download/<filename>')
def download(filename):
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
