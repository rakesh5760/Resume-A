import os
import pandas as pd
from datetime import datetime
import openai
import pdfplumber
from docx import Document
import tkinter as tk
from tkinter import filedialog
import json

# =========================
# 1. User Configuration
# =========================
openai.api_key = os.getenv("OPENAI_API_KEY")  # <-- Load from .env file

# Final Excel columns
EXCEL_COLUMNS = [
    "Date Entry", "Date of Interview", "Candidate Name", "Email", "Phone", "Location", "LinkedIn",
    "Current Title", "Work Experience (Years & Months)", "Last Graduation Date", "First Job Start Date",
    "Profile Gap (Months)", "Skills (Experience + No. of Projects)",
    "Work Experience Details (Years, Role, Skills, Tech)", "Projects (Title, Technologies, Skills)",
    "Rating", "Notice Period", "CTC", "Recommendation", "Comments"
]

# =========================
# 2. Helper Functions
# =========================

def read_pdf(file_path):
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
    except:
        text = ""
    return text.strip()

def read_docx(file_path):
    try:
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except:
        return ""

def extract_resume_text(file_path):
    if file_path.lower().endswith(".pdf"):
        return read_pdf(file_path)
    elif file_path.lower().endswith(".docx"):
        return read_docx(file_path)
    else:
        return ""

def analyze_resume_with_gemini(resume_text):
    if not resume_text.strip():
        return {}  # Empty resume
    try:
        prompt = f"""
        Extract the resume information from the text below in a clear JSON format 
        with these keys: candidate_name, email, phone, location, linkedin, current_title, education, work_experience, projects.
        Respond ONLY with valid JSON, without extra explanation.
        Text:
        {resume_text}
        """
        response = openai.responses.create(
            model="gemini-1",
            input=prompt
        )

        # Gemini API may return structured content in 'response.output[0].content[0].text'
        # depending on SDK version
        if hasattr(response, "output") and len(response.output) > 0:
            content = response.output[0].get("content", [])
            if content and "text" in content[0]:
                response_text = content[0]["text"]
                try:
                    data = json.loads(response_text)
                    return data
                except json.JSONDecodeError:
                    print("Failed to parse JSON from Gemini response")
                    print("Raw text returned:", response_text)
                    return {}
        return {}

    except Exception as e:
        print(f"Gemini API error: {e}")
        return {}




def safe_get(d, key, default="-"):
    return d.get(key, default)

def calculate_work_experience(experience_list):
    if not experience_list:
        return "-"
    total_months = 0
    for exp in experience_list:
        start = exp.get("start_date")
        end = exp.get("end_date", str(datetime.today().date()))
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
            total_months += months
        except:
            continue
    years = total_months // 12
    months = total_months % 12
    return f"{years} years {months} months"

def calculate_profile_gap(last_grad_date, first_job_date):
    if last_grad_date == "-" or first_job_date == "-":
        return "-"
    try:
        grad_dt = datetime.strptime(last_grad_date, "%Y-%m-%d")
        job_dt = datetime.strptime(first_job_date, "%Y-%m-%d")
        months_gap = (job_dt.year - grad_dt.year) * 12 + (job_dt.month - grad_dt.month)
        return months_gap
    except:
        return "-"

def format_skills(experience_list, projects_list):
    if not experience_list and not projects_list:
        return "-"
    skill_count = {}
    for exp in experience_list:
        skills = exp.get("skills", [])
        duration_months = 0
        start = exp.get("start_date")
        end = exp.get("end_date", str(datetime.today().date()))
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            duration_months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
        except:
            duration_months = 0
        for skill in skills:
            if skill not in skill_count:
                skill_count[skill] = {"months": duration_months, "projects": 0}
            else:
                skill_count[skill]["months"] += duration_months
    for proj in projects_list or []:
        skills = proj.get("skills", [])
        for skill in skills:
            if skill not in skill_count:
                skill_count[skill] = {"months": 0, "projects": 1}
            else:
                skill_count[skill]["projects"] += 1
    skill_lines = []
    for skill, val in skill_count.items():
        years = val["months"] // 12
        months = val["months"] % 12
        proj_count = val["projects"]
        skill_lines.append(f"{skill} – {years} years {months} months – {proj_count} projects")
    return "\n".join(skill_lines) if skill_lines else "-"

def format_work_experience_details(experience_list):
    if not experience_list:
        return "-"
    details = []
    for exp in experience_list:
        company = safe_get(exp, "company")
        role = safe_get(exp, "role")
        start = safe_get(exp, "start_date")
        end = safe_get(exp, "end_date")
        skills = ", ".join(exp.get("skills", [])) or "-"
        tech = ", ".join(exp.get("technologies", [])) or "-"
        duration = "-"
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d") if end != "-" else datetime.today()
            months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
            years = months // 12
            rem_months = months % 12
            duration = f"{years} years {rem_months} months"
        except:
            pass
        block = f"Company: {company}\nRole: {role}\nDuration: {duration}\nSkills Used: {skills}\nTechnologies: {tech}"
        details.append(block)
    return "\n\n".join(details)

def format_projects(projects_list):
    if not projects_list:
        return "-"
    proj_lines = []
    for proj in projects_list:
        title = safe_get(proj, "title")
        tech = ", ".join(proj.get("technologies", [])) or "-"
        skills = ", ".join(proj.get("skills", [])) or "-"
        link = safe_get(proj, "link")
        block = f"Project Title: {title}\nTechnologies: {tech}\nSkills: {skills}\nLink: {link}"
        proj_lines.append(block)
    return "\n\n".join(proj_lines)

# =========================
# 3. Main Procedure
# =========================

def main():
    root = tk.Tk()
    root.withdraw()

    # Step 1: Pick resume file or folder
    resume_path = filedialog.askopenfilename(
        title="Select a Resume File (or Cancel to pick folder)",
        filetypes=[("PDF files", "*.pdf"), ("Word Documents", "*.docx")]
    )
    if not resume_path:
        resume_path = filedialog.askdirectory(title="Select Folder with Resumes")

    if os.path.isdir(resume_path):
        resume_files = [os.path.join(resume_path, f) for f in os.listdir(resume_path)
                        if f.lower().endswith((".pdf", ".docx"))]
    else:
        resume_files = [resume_path]

    if not resume_files:
        print("No resumes found. Exiting.")
        return

    # Step 2: Pick Excel file
    excel_file = filedialog.asksaveasfilename(
        title="Select or Create Excel File",
        defaultextension=".xlsx",
        filetypes=[("Excel files", "*.xlsx")]
    )
    if os.path.exists(excel_file):
        df = pd.read_excel(excel_file)
    else:
        df = pd.DataFrame(columns=EXCEL_COLUMNS)

    # Step 3: Process each resume
    for file in resume_files:
        print(f"Processing: {file}")
        resume_text = extract_resume_text(file)
        analyzed_data = analyze_resume_with_gemini(resume_text)

        candidate_name = safe_get(analyzed_data, "candidate_name")
        email = safe_get(analyzed_data, "email")
        phone = safe_get(analyzed_data, "phone")
        location = safe_get(analyzed_data, "location")
        linkedin = safe_get(analyzed_data, "linkedin")
        current_title = safe_get(analyzed_data, "current_title")
        education = analyzed_data.get("education", {})
        last_grad_date = safe_get(education, "last_graduation_date")
        first_job_date = "-"
        experience_list = analyzed_data.get("work_experience", [])
        if experience_list:
            dates = [exp.get("start_date") for exp in experience_list if exp.get("start_date")]
            first_job_date = min(dates) if dates else "-"
        profile_gap = calculate_profile_gap(last_grad_date, first_job_date)
        work_exp = calculate_work_experience(experience_list)
        projects_list = analyzed_data.get("projects", [])
        skills_str = format_skills(experience_list, projects_list)
        work_exp_details = format_work_experience_details(experience_list)
        projects_str = format_projects(projects_list)

        # Prepare row
        row = {
            "Date Entry": datetime.today().strftime("%Y-%m-%d"),
            "Date of Interview": "-",  # untouched
            "Candidate Name": candidate_name,
            "Email": email,
            "Phone": phone,
            "Location": location,
            "LinkedIn": linkedin,
            "Current Title": current_title,
            "Work Experience (Years & Months)": work_exp,
            "Last Graduation Date": last_grad_date,
            "First Job Start Date": first_job_date,
            "Profile Gap (Months)": profile_gap,
            "Skills (Experience + No. of Projects)": skills_str,
            "Work Experience Details (Years, Role, Skills, Tech)": work_exp_details,
            "Projects (Title, Technologies, Skills)": projects_str,
            "Rating": "-",  # untouched
            "Notice Period": "-",  # untouched
            "CTC": "-",  # untouched
            "Recommendation": "-",  # untouched
            "Comments": "-"  # untouched
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    # Step 4: Save Excel
    df.to_excel(excel_file, index=False)
    print(f"All resumes processed and saved to {excel_file}")

# =========================
# Run main
# =========================
if __name__ == "__main__":
    main()
