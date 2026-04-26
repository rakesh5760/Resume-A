import os
import pandas as pd
import pdfplumber
from docx import Document
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import instructor
from groq import Groq
from dotenv import load_dotenv
from tqdm import tqdm

# Load API Key
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY not found in .env file.")
    exit(1)

# Initialize instructor client with Groq
client = instructor.from_groq(Groq(api_key=GROQ_API_KEY), mode=instructor.Mode.TOOLS)

# =========================
# 1. Pydantic Data Models
# =========================

class JobEntry(BaseModel):
    role: str = Field(description="Role title")
    company: str = Field(description="Company name")
    start_date: str = Field(description="YYYY-MM-DD")
    end_date: str = Field(description="YYYY-MM-DD or 'Present'")
    description: str = Field(description="Job description/responsibilities")
    type: Literal["Full-Time", "Internship", "Contract"]
    skills: List[str] = Field(description="Normalized skill names mentioned in THIS description section")

class ProjectEntry(BaseModel):
    name: str = Field(description="Project name")
    description: str = Field(description="Project summary")
    skills: List[str] = Field(description="Normalized skill names mentioned in THIS project description")

class PreciseResumeData(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = Field(description="ONLY full URL (https://www.linkedin.com/in/...). Return null if not found.", default=None)
    location: Optional[str] = None
    current_title: Optional[str] = None
    last_graduation_date: Optional[str] = None
    first_job_start_date: Optional[str] = None
    all_found_skills: List[str] = Field(description="Unique list of ALL skills found in Skills section, Experience, or Projects. Group variations (e.g., Python3 -> Python, MySQL -> SQL).")
    jobs: List[JobEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)

# =========================
# 2. Calculation & Grouping Logic
# =========================

def get_job_interval(job: JobEntry):
    try:
        start = datetime.strptime(job.start_date, "%Y-%m-%d")
        end = datetime.today() if job.end_date.lower() == "present" else datetime.strptime(job.end_date, "%Y-%m-%d")
        return (start, end) if start < end else None
    except:
        return None

def merge_intervals(intervals):
    if not intervals: return 0
    intervals.sort()
    merged = [intervals[0]]
    for cur_s, cur_e in intervals[1:]:
        prev_s, prev_e = merged[-1]
        if cur_s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, cur_e))
        else:
            merged.append((cur_s, cur_e))
    
    total_months = 0
    for s, e in merged:
        total_months += (e.year - s.year) * 12 + (e.month - s.month)
    return total_months

def format_duration(months):
    y = months // 12
    m = months % 12
    return f"{y} years {m} months"

def group_skills_by_metrics(skill_data):
    """
    Groups skills by common (months, project_count).
    skill_data: list of {'name': str, 'months': int, 'projects': int}
    """
    groups = {}
    for s in skill_data:
        key = (s['months'], s['projects'])
        if key not in groups:
            groups[key] = []
        groups[key].append(s['name'])
    
    # Sort keys: Highest experience (months) first, then project count
    sorted_keys = sorted(groups.keys(), key=lambda x: (x[0], x[1]), reverse=True)
    
    output_lines = []
    for k in sorted_keys:
        months, projects = k
        skills_str = ", ".join(sorted(groups[k]))
        duration_str = format_duration(months)
        output_lines.append(f"{skills_str} – {duration_str} – {projects} projects")
    
    return "\n".join(output_lines) if output_lines else "-"

# =========================
# 3. Extraction logic
# =========================

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == ".pdf":
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages: text += (page.extract_text() or "") + "\n"
        elif ext == ".docx":
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"Read error: {e}")
    return text.strip()

def analyze_resume_v4(text):
    if not text.strip(): return None
    try:
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": """You are Resume Parser v5 (STRICT ACCURACY).

LINKEDIN RULES:
- Extract the LinkedIn URL EXACTLY as it appears.
- If it starts with 'linkedin.com', it is valid.
- If ONLY the word 'LinkedIn' is found without a specific profile handle or URL, return null.

TITLE RULES:
- Extract 'Current Title' and 'Candidate Name' EXACTLY as written in the resume. DO NOT summarize or rephrase.

SKILL RULES:
- SOURCE: Check Skills, Experience, and Projects sections.
- NORMALIZATION: Group variations (e.g., Python3 -> Python, MySQL -> SQL).
- mapping: Only map skill to job/project if mentioned in that specific description.
"""},
                {"role": "user", "content": f"Analyze this resume precisely:\n\n{text}"}
            ],
            response_model=PreciseResumeData
        )
    except Exception as e:
        print(f"API Error: {e}")
        return None

def main():
    folder = input("Enter resumes folder path: ").strip()
    if not os.path.exists(folder): return

    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith((".pdf", ".docx"))]
    results = []

    print(f"\nProcessing {len(files)} resumes with Grouped Skill Logic...")

    for f_path in tqdm(files, desc="Processing"):
        text = extract_text(f_path)
        data = analyze_resume_v4(text)
        if not data: continue

        # Compute Experience Breakdown
        ft_months = merge_intervals([i for i in [get_job_interval(j) for j in data.jobs if j.type != "Internship"] if i])
        int_months = merge_intervals([i for i in [get_job_interval(j) for j in data.jobs if j.type == "Internship"] if i])
        tot_exp_str = f"FT: {format_duration(ft_months)} | Intern: {format_duration(int_months)}"

        # Skill Experience & Projects Calculation
        skill_data_to_group = []
        for skill in data.all_found_skills:
            relevant_intervals = []
            has_exp_mention = False
            for j in data.jobs:
                if any(skill.lower() == s.lower() for s in j.skills):
                    has_exp_mention = True
                    interval = get_job_interval(j)
                    if interval: relevant_intervals.append(interval)
            
            skill_months = merge_intervals(relevant_intervals)
            # Zero-value fix: if mentioned but dates unclear, min 1 month
            if has_exp_mention and skill_months == 0: skill_months = 1
            
            p_count = sum(1 for p in data.projects if any(skill.lower() == s.lower() for s in p.skills))
            
            skill_data_to_group.append({
                'name': skill,
                'months': skill_months,
                'projects': p_count
            })

        skills_summary_grouped = group_skills_by_metrics(skill_data_to_group)

        # Role History Formatting
        role_lines = []
        for j in data.jobs:
            status = "Present" if j.end_date.lower() == "present" else "Past"
            job_iv = get_job_interval(j)
            job_months = merge_intervals([job_iv]) if job_iv else 0
            role_lines.append(f"{j.role} - {status} (YOE {format_duration(job_months)})")
        roles_summary = "\n".join(role_lines) if role_lines else "-"

        # Format Details for other columns
        exp_details = [f"[{j.type}] {j.role} at {j.company} ({j.start_date} to {j.end_date})" for j in data.jobs]
        proj_details = [f"Project: {p.name}\nDesc: {p.description}" for p in data.projects]

        row = {
            "Date Entry": datetime.today().strftime("%Y-%m-%d"),
            "Date of Interview": "-",
            "Candidate Name": data.name or "-",
            "Email": data.email or "-",
            "Phone": data.phone or "-",
            "Location": data.location or "-",
            "LinkedIn": data.linkedin or "-",
            "Current Title": roles_summary,
            "Work Experience (Years & Months)": tot_exp_str,
            "Last Graduation Date": data.last_graduation_date or "-",
            "First Job Start Date": data.first_job_start_date or "-",
            "Profile Gap (Months)": "-", 
            "Skills (Experience + No. of Projects)": skills_summary_grouped,
            "Work Experience Details (Years, Role, Skills, Tech)": "\n\n".join(exp_details) if exp_details else "-",
            "Projects (Title, Technologies, Skills)": "\n\n".join(proj_details) if proj_details else "-",
            "Rating": "-",
            "Notice Period": "-",
            "CTC": "-",
            "Recommendation": "-",
            "Comments": "-"
        }
        results.append(row)

    if results:
        out = f"analyzed_resumes_grouped_{datetime.now().strftime('%H%M%S')}.xlsx"
        pd.DataFrame(results).to_excel(out, index=False)
        print(f"\nDone! Saved to {out}")

if __name__ == "__main__":
    main()
