import pdfplumber
import re
import io
import os
from datetime import datetime
import pandas as pd
from dateutil.relativedelta import relativedelta
import dateparser
import spacy
from transformers import pipeline
from sentence_transformers import SentenceTransformer, util
from rapidfuzz import fuzz
from email_validator import validate_email, EmailNotValidError

# ---------------------------
# Load Models
# ---------------------------
def load_models():
    try:
        nlp = spacy.load("en_core_web_trf")
    except:
        nlp = spacy.load("en_core_web_sm")
    hf_ner = pipeline("ner", aggregation_strategy="simple", device=-1)
    sbert = SentenceTransformer("all-mpnet-base-v2")
    return nlp, hf_ner, sbert

nlp, hf_ner, sbert = load_models()

BASE_SKILLS = [
    "Python","Java","C++","C#","JavaScript","TypeScript","SQL","NoSQL","PostgreSQL","MySQL",
    "MongoDB","AWS","GCP","Azure","Docker","Kubernetes","Django","Flask","FastAPI",
    "React","Angular","Vue","Node.js","Express","Pandas","NumPy","TensorFlow","PyTorch",
    "Machine Learning","Deep Learning","NLP","Computer Vision","Spark","Hadoop","Terraform",
    "Ansible","CI/CD","Jenkins","Git","Linux","REST","GraphQL","Microservices"
]
SKILLS_EMBED = sbert.encode(BASE_SKILLS)

email_re = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}")
phone_re = re.compile(r"(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?[\d\-.\s]{6,15}")
linkedin_re = re.compile(r"(https?://)?(www\.)?linkedin\.com/[A-Za-z0-9_\-\/]+", re.I)
years_exp_re = re.compile(r"(\d{1,2}(?:\.\d)?)[\s\-+]*(?:years?|yrs?)", re.I)

def extract_text_from_pdf(path):
    text_pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            text_pages.append(txt)
    return "\n\n".join(text_pages)

def extract_name(text):
    doc = nlp(text[:1000])
    persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    return persons[0] if persons else ""

def extract_contact(text):
    email = ""
    phone = ""
    linkedin = ""

    m = re.search(email_re, text)
    if m:
        try:
            email = validate_email(m.group()).email
        except:
            email = m.group()

    phones = re.findall(phone_re, text)
    flat = ["".join(p).strip() for p in phones]
    for p in flat:
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15:
            phone = p
            break

    m2 = re.search(linkedin_re, text)
    if m2:
        linkedin = m2.group()

    return email, phone, linkedin

def extract_experience_years(text):
    m = re.search(years_exp_re, text)
    if m:
        return float(m.group(1))
    return ""

def extract_skills(text):
    found = set()
    lower = text.lower()

    for skill in BASE_SKILLS:
        if fuzz.partial_ratio(skill.lower(), lower) > 85:
            found.add(skill)

    return ", ".join(sorted(found))

def rating(years):
    if years == "":
        return ""
    if years <= 2:
        return "Junior"
    if 3 <= years <= 5:
        return "Mid-Level"
    return "Senior"

# ---------------------------
# Process a single PDF
# ---------------------------
def process_resume(path):
    text = extract_text_from_pdf(path)

    name = extract_name(text)
    email, phone, linkedin = extract_contact(text)
    years = extract_experience_years(text)
    skills = extract_skills(text)
    rate = rating(years)

    return {
        "Date Entry": datetime.now().strftime("%Y-%m-%d"),
        "Name": name,
        "Email": email,
        "Phone": phone,
        "LinkedIn": linkedin,
        "Work Experience (Years)": years,
        "Skills": skills,
        "Rating": rate,
        "Resume Path": path
    }

# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    folder = input("Enter folder path containing PDF resumes: ").strip()

    files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    print(f"\nFound {len(files)} PDF resumes.\n")

    rows = []
    for f in files:
        full_path = os.path.join(folder, f)
        print(f"Processing: {f}")
        rows.append(process_resume(full_path))

    df = pd.DataFrame(rows)
    out = "parsed_resumes.xlsx"
    df.to_excel(out, index=False)

    print(f"\nDone! Excel saved as {out}")
