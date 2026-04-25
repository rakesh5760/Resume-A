import os
import re
import pandas as pd
from datetime import datetime
import pdfplumber
from docx import Document

# =========================
# 1. User Configuration
# =========================

# Final Excel columns
EXCEL_COLUMNS = [
    "Date Entry", "Date of Interview", "Candidate Name", "Email", "Phone", "Location", "LinkedIn",
    "Current Title", "Work Experience (Years & Months)", "Last Graduation Date", "First Job Start Date",
    "Profile Gap (Months)", "Skills (Experience + No. of Projects)",
    "Work Experience Details (Years, Role, Skills, Tech)", "Projects (Title, Technologies, Skills)",
    "Rating", "Notice Period", "CTC", "Recommendation", "Comments"
]

# List of skills to search for (expand as needed)
SKILLS_LIST = [
    "Python", "Java", "C++", "SQL", "JavaScript", "React", "Node.js", "AWS", "Docker", "Kubernetes"
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

def safe_get(d, key, default="-"):
    return d.get(key, default)

def extract_candidate_info(text):
    """
    Basic regex-based heuristics to extract info from resume text
    """
    info = {}
    info['candidate_name'] = "-"
    name_match = re.search(r"Name[:\-]?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)", text)
    if name_match:
        info['candidate_name'] = name_match.group(1).strip()

    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    info['email'] = email_match.group(0).strip() if email_match else "-"

    phone_match = re.search(r"\+?\d[\d\s\-]{8,}\d", text)
    info['phone'] = phone_match.group(0).strip() if phone_match else "-"

    linkedin_match = re.search(r"(https?://)?(www\.)?linkedin\.com/\S+", text)
    info['linkedin'] = linkedin_match.group(0).strip() if linkedin_match else "-"

    current_title_match = re.search(r"(Current\s*Title|Position)[:\-]?\s*(.+)", text, re.IGNORECASE)
    info['current_title'] = current_title_match.group(2).strip() if current_title_match else "-"

    # Graduation date
    grad_match = re.search(r"(Graduation|Degree).+(\d{4})", text, re.IGNORECASE)
    info['last_graduation_date'] = f"{grad_match.group(2)}-06-01" if grad_match else "-"

    return info

def calculate_work_experience(text):
    """
    Sum total experience mentioned in text: look for patterns like 'X years' or 'X yrs'
    """
    matches = re.findall(r"(\d+)\s*(?:years|yrs|year)", text, re.IGNORECASE)
    total_years = sum([int(m) for m in matches]) if matches else 0
    return f"{total_years} years"

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

def extract_work_experience_blocks(text):
    """
    Heuristic: split text by sections containing 'Company', 'Role', 'Experience', etc.
    """
    blocks = []
    pattern = re.compile(r"(Company|Role|Experience|Designation)[:\s\-](.+?)(?=\n[A-Z])", re.DOTALL | re.IGNORECASE)
    matches = pattern.findall(text)
    for match in matches:
        blocks.append(match[1].strip())
    return blocks

def extract_projects(text):
    """
    Heuristic: split text by 'Project' keyword
    """
    blocks = re.split(r"\bProject\b", text, flags=re.IGNORECASE)
    projects = []
    for b in blocks[1:]:
        title_match = re.search(r"Title[:\-]?\s*(.+)", b)
        tech_match = re.search(r"Technologies?[:\-]?\s*(.+)", b)
        skills_match = re.search(r"Skills?[:\-]?\s*(.+)", b)
        projects.append({
            "title": title_match.group(1).strip() if title_match else "-",
            "technologies": [x.strip() for x in tech_match.group(1).split(",")] if tech_match else [],
            "skills": [x.strip() for x in skills_match.group(1).split(",")] if skills_match else []
        })
    return projects

def extract_skill_experience(text, skills_list):
    """
    Extract approximate months of experience for each skill from resume text.
    Returns a dict: { skill_name: months_of_experience }
    """
    skill_exp = {}
    for skill in skills_list:
        pattern1 = re.compile(rf"{skill}[:\s-]*(\d+)\s*(?:years|yrs)", re.IGNORECASE)
        pattern2 = re.compile(rf"(\d+)\s*(?:years|yrs).*?{skill}", re.IGNORECASE)
        pattern3 = re.compile(rf"{skill}[:\s-]*(\d+)\s*(?:months|mos)", re.IGNORECASE)
        months = 0
        for pattern in [pattern1, pattern2, pattern3]:
            match = pattern.search(text)
            if match:
                val = int(match.group(1))
                if 'month' in pattern.pattern.lower():
                    months = max(months, val)
                else:
                    months = max(months, val * 12)
        skill_exp[skill] = months
    return skill_exp

def format_skills_and_projects(exp_blocks, project_list, resume_text):
    skill_exp = extract_skill_experience(resume_text, SKILLS_LIST)
    skill_projects = {skill: 0 for skill in SKILLS_LIST}
    for proj in project_list:
        for skill in proj.get("skills", []):
            skill_projects[skill] += 1
    for block in exp_blocks:
        for skill in SKILLS_LIST:
            if skill.lower() in block.lower():
                skill_projects[skill] += 1
    lines = []
    for skill in SKILLS_LIST:
        exp_months = skill_exp.get(skill, 0)
        years = exp_months // 12
        months = exp_months % 12
        projects = skill_projects.get(skill, 0)
        if exp_months > 0 or projects > 0:
            lines.append(f"{skill} – {years} years {months} months – {projects} projects")
    return "\n".join(lines) if lines else "-"

# =========================
# 3. Main Procedure
# =========================

def main():
    resume_path = input("Enter the path of a resume file or folder containing resumes: ").strip()
    if os.path.isdir(resume_path):
        resume_files = [os.path.join(resume_path, f) for f in os.listdir(resume_path)
                        if f.lower().endswith((".pdf", ".docx"))]
    else:
        resume_files = [resume_path]

    if not resume_files:
        print("No resumes found. Exiting.")
        return

    excel_file = input("Enter the path of the Excel file to append (will be created if not exists): ").strip()
    if os.path.exists(excel_file):
        df = pd.read_excel(excel_file)
    else:
        df = pd.DataFrame(columns=EXCEL_COLUMNS)

    for file in resume_files:
        print(f"Processing: {file}")
        text = extract_resume_text(file)
        info = extract_candidate_info(text)
        work_exp_blocks = extract_work_experience_blocks(text)
        projects_list = extract_projects(text)
        work_exp_str = calculate_work_experience(text)
        skills_str = format_skills_and_projects(work_exp_blocks, projects_list, text)
        first_job_date = "-"  # heuristic: could be first date in experience blocks
        profile_gap = calculate_profile_gap(info.get("last_graduation_date"), first_job_date)

        row = {
            "Date Entry": datetime.today().strftime("%Y-%m-%d"),
            "Date of Interview": "-",
            "Candidate Name": info.get("candidate_name", "-"),
            "Email": info.get("email", "-"),
            "Phone": info.get("phone", "-"),
            "Location": "-",  # optional: could parse city
            "LinkedIn": info.get("linkedin", "-"),
            "Current Title": info.get("current_title", "-"),
            "Work Experience (Years & Months)": work_exp_str,
            "Last Graduation Date": info.get("last_graduation_date", "-"),
            "First Job Start Date": first_job_date,
            "Profile Gap (Months)": profile_gap,
            "Skills (Experience + No. of Projects)": skills_str,
            "Work Experience Details (Years, Role, Skills, Tech)": "\n\n".join(work_exp_blocks) if work_exp_blocks else "-",
            "Projects (Title, Technologies, Skills)": "\n\n".join([f"Title: {p['title']}\nTechnologies: {', '.join(p['technologies'])}\nSkills: {', '.join(p['skills'])}" for p in projects_list]) if projects_list else "-",
            "Rating": "-",
            "Notice Period": "-",
            "CTC": "-",
            "Recommendation": "-",
            "Comments": "-"
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    df.to_excel(excel_file, index=False)
    print(f"All resumes processed and saved to {excel_file}")

# =========================
# Run
# =========================
if __name__ == "__main__":
    main()
