from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from flask_cors import CORS
import os
import groq_analyzer
import json
import pandas as pd
from datetime import datetime
from collections import Counter

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Ensure upload directory exists
UPLOAD_FOLDER = 'uploads'
MASTER_REPORT = 'master_report.xlsx'

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
                pass # Do not delete files so they can be viewed in the UI
                # if should_delete and os.path.exists(f_path):
                #     os.remove(f_path)

        # Master Report Logic
        new_df = pd.DataFrame(results)
        if os.path.exists(MASTER_REPORT):
            try:
                existing_df = pd.read_excel(MASTER_REPORT)
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            except:
                combined_df = new_df
        else:
            combined_df = new_df
            
        # Clean up legacy 'View Resume' column if it exists in the master report
        if 'View Resume' in combined_df.columns:
            combined_df.drop(columns=['View Resume'], inplace=True)
            
        combined_df.to_excel(MASTER_REPORT, index=False)
        
        final_data = {
            "type": "done",
            "results": results,
            "excel_file": MASTER_REPORT
        }
        yield f"data: {json.dumps(final_data)}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/download/<filename>')
def download(filename):
    return send_file(filename, as_attachment=True)

@app.route('/view')
def view_resume():
    path = request.args.get('path')
    if path and os.path.exists(path):
        return send_file(path)
    return "File not found", 404

@app.route('/api/dashboard', methods=['GET'])
def dashboard_data():
    if not os.path.exists(MASTER_REPORT):
        return jsonify({"success": False, "error": "No data available. Process some resumes first."}), 404
        
    try:
        df = pd.read_excel(MASTER_REPORT)
        candidates = []
        
        for index, row in df.iterrows():
            # 1. Parse Skills
            skills = []
            if 'Skills Summary' in df.columns and pd.notna(row['Skills Summary']) and row['Skills Summary'] != '-':
                lines = str(row['Skills Summary']).split('\n')
                for line in lines:
                    parts = line.split(' – ')
                    if parts:
                        skill_names = [s.strip() for s in parts[0].split(',') if s.strip()]
                        skills.extend(skill_names)
            
            # 2. Parse Experience
            exp_level = "Unknown"
            if 'Total Experience' in df.columns and pd.notna(row['Total Experience']):
                exp = str(row['Total Experience'])
                if "FT:" in exp:
                    ft_part = exp.split('|')[0].replace('FT:', '').strip()
                    y_str = ft_part.split('y')[0].strip()
                    try:
                        years = int(y_str)
                        if years < 1: exp_level = "Entry (<1y)"
                        elif years <= 3: exp_level = "Mid (1-3y)"
                        else: exp_level = "Senior (3y+)"
                    except:
                        pass
                        
            # 3. Parse Location
            loc = "Unknown"
            if 'Location' in df.columns and pd.notna(row['Location']) and str(row['Location']).strip() != '-':
                loc = str(row['Location']).strip()
                
            candidates.append({
                "id": index,
                "skills": skills,
                "experience": exp_level,
                "location": loc
            })
            
        return jsonify({
            "success": True,
            "candidates": candidates
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
