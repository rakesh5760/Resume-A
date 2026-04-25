import os
import pandas as pd
import pdfplumber
from docx import Document
from datetime import datetime
from typing import List, Optional
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

class WorkExperience(BaseModel):
    company: str = Field(description="Name of the company")
    role: str = Field(description="Job title/role")
    start_date: str = Field(description="Start date in YYYY-MM-DD format (use 01 for day if missing)")
    end_date: str = Field(description="End date in YYYY-MM-DD format, or 'Present'")
    skills: List[str] = Field(description="List of skills used in this role")
    technologies: List[str] = Field(description="List of specific technologies used")
    description: str = Field(description="Brief summary of responsibilities")

class Project(BaseModel):
    title: str = Field(description="Title of the project")
    technologies: List[str] = Field(description="Technologies used in the project")
    skills: List[str] = Field(description="Skills applied in the project")
    link: Optional[str] = Field(description="Project link or description of link", default="-")

class ResumeData(BaseModel):
    candidate_name: str
    email: str
    phone: str
    location: str
    linkedin: str
    current_title: str
    last_graduation_date: str = Field(description="Date of last graduation in YYYY-MM-DD format")
    first_job_start_date: Optional[str] = Field(description="Date of first job start in YYYY-MM-DD format")
    work_experience: List[WorkExperience]
    projects: List[Project]

# =========================
# 2. Text Extraction Logic
# =========================

def read_pdf(file_path):
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
    return text.strip()

def read_docx(file_path):
    try:
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs]).strip()
    except Exception as e:
        print(f"Error reading DOCX {file_path}: {e}")
        return ""

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return read_pdf(file_path)
    elif ext == ".docx":
        return read_docx(file_path)
    return ""

# =========================
# 3. Helper Functions
# =========================

def calculate_duration(start_str, end_str):
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        if end_str.lower() == "present":
            end_dt = datetime.today()
        else:
            end_dt = datetime.strptime(end_str, "%Y-%m-%d")
        
        months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
        return months
    except:
        return 0

def format_total_experience(experience_list):
    total_months = 0
    for exp in experience_list:
        total_months += calculate_duration(exp.start_date, exp.end_date)
    
    years = total_months // 12
    remaining_months = total_months % 12
    return f"{years} years {remaining_months} months"

def calculate_profile_gap(grad_date_str, first_job_start_str):
    try:
        grad_dt = datetime.strptime(grad_date_str, "%Y-%m-%d")
        job_dt = datetime.strptime(first_job_start_str, "%Y-%m-%d")
        months_gap = (job_dt.year - grad_dt.year) * 12 + (job_dt.month - grad_dt.month)
        return max(0, months_gap)
    except:
        return "-"

def format_skills_summary(experience_list, projects_list):
    skill_stats = {} # {skill: {'months': int, 'projects': int}}
    
    for exp in experience_list:
        duration = calculate_duration(exp.start_date, exp.end_date)
        for skill in exp.skills:
            if skill not in skill_stats:
                skill_stats[skill] = {'months': 0, 'projects': 0}
            skill_stats[skill]['months'] += duration
            
    for proj in projects_list:
        for skill in proj.skills:
            if skill not in skill_stats:
                skill_stats[skill] = {'months': 0, 'projects': 0}
            skill_stats[skill]['projects'] += 1
            
    lines = []
    for skill, data in skill_stats.items():
        y = data['months'] // 12
        m = data['months'] % 12
        p = data['projects']
        lines.append(f"{skill} – {y} years {m} months – {p} projects")
    
    return "\n".join(lines) if lines else "-"

# =========================
# 4. Main Processing logic
# =========================

def analyze_resume(text):
    if not text:
        return None
    
    try:
        return client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a highly accurate resume parser. Extract information exactly as requested in the schema. For dates, if only the year is provided, assume January 1st (YYYY-01-01). If a date is 'Present', use 'Present'."},
                {"role": "user", "content": f"Parse the following resume text:\n\n{text}"}
            ],
            response_model=ResumeData
        )
    except Exception as e:
        print(f"Groq API Error: {e}")
        return None

def main():
    folder_path = input("Enter the folder path containing resumes: ").strip()
    if not os.path.isdir(folder_path):
        print("Invalid folder path.")
        return

    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) 
             if f.lower().endswith((".pdf", ".docx"))]
    
    if not files:
        print("No PDF or DOCX files found.")
        return

    excel_name = "analyzed_resumes_groq.xlsx"
    results = []

    print(f"\nProcessing {len(files)} resumes...\n")

    for file_path in tqdm(files, desc="Parsing Resumes"):
        text = extract_text(file_path)
        data = analyze_resume(text)
        
        if data:
            # Calculate derived fields
            total_exp = format_total_experience(data.work_experience)
            first_job = data.first_job_start_date or (data.work_experience[-1].start_date if data.work_experience else "-")
            gap = calculate_profile_gap(data.last_graduation_date, first_job)
            skills_summ = format_skills_summary(data.work_experience, data.projects)
            
            # Format Work Exp Details
            exp_details = []
            for exp in data.work_experience:
                dur = format_total_experience([exp])
                exp_details.append(f"Company: {exp.company}\nRole: {exp.role}\nDuration: {dur}\nSkills: {', '.join(exp.skills)}\nTech: {', '.join(exp.technologies)}")
            
            # Format Projects Details
            proj_details = []
            for p in data.projects:
                proj_details.append(f"Project Title: {p.title}\nTechnologies: {', '.join(p.technologies)}\nSkills: {', '.join(p.skills)}\nLink: {p.link}")

            # Create row
            row = {
                "Date Entry": datetime.today().strftime("%Y-%m-%d"),
                "Date of Interview": "-",
                "Candidate Name": data.candidate_name,
                "Email": data.email,
                "Phone": data.phone,
                "Location": data.location,
                "LinkedIn": data.linkedin,
                "Current Title": data.current_title,
                "Work Experience (Years & Months)": total_exp,
                "Last Graduation Date": data.last_graduation_date,
                "First Job Start Date": first_job,
                "Profile Gap (Months)": gap,
                "Skills (Experience + No. of Projects)": skills_summ,
                "Work Experience Details (Years, Role, Skills, Tech)": "\n\n".join(exp_details),
                "Projects (Title, Technologies, Skills)": "\n\n".join(proj_details),
                "Rating": "-",
                "Notice Period": "-",
                "CTC": "-",
                "Recommendation": "-",
                "Comments": "-"
            }
            results.append(row)
        else:
            print(f"Skipping {os.path.basename(file_path)} due to parsing error.")

    if results:
        df = pd.DataFrame(results)
        df.to_excel(excel_name, index=False)
        print(f"\nSuccess! Results saved to {excel_name}")
    else:
        print("\nNo results to save.")

if __name__ == "__main__":
    main()
