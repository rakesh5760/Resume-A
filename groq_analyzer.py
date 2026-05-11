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
from dateutil import parser as date_parser
from tenacity import retry, stop_after_attempt, wait_exponential

# Load API Key
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY not found in .env file.")
    exit(1)

# Initialize instructor client
client = instructor.from_groq(Groq(api_key=GROQ_API_KEY), mode=instructor.Mode.TOOLS)

# ==========================
# 1. Pydantic Data Models
# ==========================

class JobEntry(BaseModel):
    role: str = Field(description="Role title")
    company: str = Field(description="Company name")
    start_date: str = Field(description="Start date (any format)")
    end_date: str = Field(description="End date (any format) or 'Present'")
    description: str = Field(description="Job description tasks")
    type: Literal["Full-Time", "Internship", "Contract"]
    skills: List[str] = Field(description="Canonical skills found in THIS entry")

class ProjectEntry(BaseModel):
    name: str = Field(description="Project name")
    description: str = Field(description="Summary of project")
    skills: List[str] = Field(description="Canonical skills found in THIS project")

class ResumeDataV5(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = Field(description="LinkedIn URL or profile handle", default=None)
    location: Optional[str] = None
    current_title: Optional[str] = None
    last_graduation_date: Optional[str] = None
    first_job_start_date: Optional[str] = None
    skills_list: List[str] = Field(description="List of skills from the 'Skills' section", default_factory=list)
    jobs: List[JobEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)

# ============================
# 2. Robust Calculation Logic
# ============================

def safe_parse_date(date_str):
    if not date_str: return None
    if date_str.lower() == "present": return datetime.today()
    try:
        return date_parser.parse(str(date_str))
    except:
        return None

def get_interval(entry: JobEntry):
    s = safe_parse_date(entry.start_date)
    e = safe_parse_date(entry.end_date)
    if s and e and s < e: return (s, e)
    return None

def merge_intervals(intervals):
    if not intervals: return 0
    intervals.sort()
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        p_s, p_e = merged[-1]
        if s <= p_e:
            merged[-1] = (p_s, max(p_e, e))
        else:
            merged.append((s, e))
    
    total = 0
    for s, e in merged:
        total += (e.year - s.year) * 12 + (e.month - s.month)
    return total

def format_duration(months):
    return f"{months // 12}y {months % 12}m"

def group_skills_by_metrics(skill_data):
    groups = {}
    for s in skill_data:
        key = (s['months'], s['projects'])
        if key not in groups: groups[key] = []
        groups[key].append(s['name'])
    
    sorted_keys = sorted(groups.keys(), key=lambda x: (x[0], x[1]), reverse=True)
    lines = []
    for k in sorted_keys:
        m, p = k
        lines.append(f"{', '.join(sorted(groups[k]))} – {format_duration(m)} – {p} projects")
    return "\n".join(lines) if lines else "-"

# =========================
# 3. Extraction logic
# =========================

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    try:
        if ext == ".pdf":
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages: 
                    text += (page.extract_text() or "") + "\n"
                    # Extract hidden hyperlinks in PDF
                    if page.hyperlinks:
                        for hl in page.hyperlinks:
                            uri = hl.get("uri")
                            if uri:
                                text += f"\n[Hidden Link Found: {uri}]\n"
        elif ext == ".docx":
            doc = Document(file_path)
            text = "\n".join([pa.text for pa in doc.paragraphs])
            # Extract hidden hyperlinks in DOCX
            for rel in doc.part.rels.values():
                if "hyperlink" in rel.reltype:
                    text += f"\n[Hidden Link Found: {rel.target_ref}]\n"
    except Exception as e:
        print(f"Read error {file_path}: {e}")
    return text.strip()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def analyze_resume_v5(text):
    if not text: return None
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": """Strict Resume Parser v5. Accuracy > Completeness. LinkedIn, Skills, Dates normalization rules apply."""},
            {"role": "user", "content": f"Extract resume data:\n\n{text}"}
        ],
        response_model=ResumeDataV5
    )

# =========================
# 4. Core Process (For Web/CLI)
# =========================

def process_single_resume(f_path):
    raw_text = extract_text(f_path)
    if not raw_text: return None
    
    data = analyze_resume_v5(raw_text)
    if not data: return None

    # Robust LinkedIn
    li = data.linkedin or "-"
    if li != "-" and not li.startswith("http"):
        if "linkedin.com" in li:
            li = "https://" + li.split("linkedin.com")[-1] if not li.startswith("linkedin.com") else "https://" + li
        else:
            li = "-"

    # Combine all skills
    all_skills = set(data.skills_list)
    for j in data.jobs: all_skills.update(j.skills)
    for p in data.projects: all_skills.update(p.skills)

    # Experience Calculations
    skill_stats = []
    for sn in all_skills:
        relevant_ivs = []
        mentioned_in_exp = False
        for j in data.jobs:
            if any(sn.lower() == s.lower() for s in j.skills):
                mentioned_in_exp = True
                iv = get_interval(j)
                if iv: relevant_ivs.append(iv)
        
        m_sum = merge_intervals(relevant_ivs)
        if mentioned_in_exp and m_sum == 0: m_sum = 1
        
        p_count = sum(1 for p in data.projects if any(sn.lower() == s.lower() for s in p.skills))
        if p_count == 0 and any(sn.lower() == s.lower() for p in data.projects for s in p.skills):
            p_count = 1
            
        skill_stats.append({'name': sn, 'months': m_sum, 'projects': p_count})

    grouped_skills = group_skills_by_metrics(skill_stats)

    # Role History
    role_lines = []
    sorted_jobs = sorted(data.jobs, key=lambda x: safe_parse_date(x.start_date) or datetime.min, reverse=True)
    for j in sorted_jobs:
        status = "Present" if j.end_date.lower() == "present" else "Past"
        months = merge_intervals([i for i in [get_interval(j)] if i])
        role_lines.append(f"{j.role} - {status} ({format_duration(months)})")

    ft_m = merge_intervals([i for i in [get_interval(j) for j in data.jobs if j.type != "Internship"] if i])
    in_m = merge_intervals([i for i in [get_interval(j) for j in data.jobs if j.type == "Internship"] if i])

    return {
        "Date Entry": datetime.today().strftime("%Y-%m-%d"),
        "Candidate Name": data.name or "-",
        "Email": data.email or "-",
        "Phone": data.phone or "-",
        "LinkedIn": li,
        "Current Title": "\n".join(role_lines) or "-",
        "Total Experience": f"FT: {format_duration(ft_m)} | Int: {format_duration(in_m)}",
        "Skills Summary": grouped_skills,
        "Last Graduation": data.last_graduation_date or "-",
        "Location": data.location or "-",
        "Resume Path": os.path.abspath(f_path)
    }

def run_analysis_folder(folder_path):
    if not os.path.isdir(folder_path): return None
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith((".pdf", ".docx"))]
    results = []
    for f in tqdm(files):
        res = process_single_resume(f)
        if res: results.append(res)
    
    if results:
        out = f"analysis_{datetime.now().strftime('%H%M%S')}.xlsx"
        pd.DataFrame(results).to_excel(out, index=False)
        return out, results
    return None, None

if __name__ == "__main__":
    path = input("Folder Path: ").strip()
    of, _ = run_analysis_folder(path)
    if of: print(f"Saved to {of}")
