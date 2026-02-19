import argparse
import sys

# Fallback lists for skills and job titles
FALLBACK_SKILLS = [
    "Python", "Java", "C++", "SQL", "Machine Learning", "Data Analysis", "Project Management", "Communication", "Leadership", "Teamwork"
]
FALLBACK_JOB_TITLES = [
    "Software Engineer", "Data Scientist", "Project Manager", "Business Analyst", "Research Assistant", "Intern"
]

def check_dependencies():
    missing = []
    try:
        from docx import Document
    except ImportError:
        missing.append("docx")
    try:
        import PyPDF2
    except ImportError:
        missing.append("PyPDF2")
    try:
        import pdfplumber
    except ImportError:
        missing.append("pdfplumber")
    try:
        import dateparser
    except ImportError:
        missing.append("dateparser")
    try:
        import spacy
    except ImportError:
        missing.append("spacy")
    try:
        import nltk
    except ImportError:
        missing.append("nltk")
    try:
        import sentence_transformers
    except ImportError:
        missing.append("sentence-transformers")
    if missing:
        logger.error(f"Missing dependencies: {', '.join(missing)}. Please install them using 'pip install -r requirements.txt'.")
        sys.exit(1)

# CLI entry point will be added below

def main():
    parser = argparse.ArgumentParser(description="CV Parser - Extracts structured data from CV files.")
    parser.add_argument('--input', '-i', required=True, help='Path to input CV file (PDF, DOCX, or TXT)')
    parser.add_argument('--output', '-o', required=True, help='Path to output JSON file')
    parser.add_argument('--print', action='store_true', help='Print parsed JSON to stdout')
    args = parser.parse_args()

    check_dependencies()

    try:
        result = parse_cv(args.input)
        if result:
            save_to_json(result, args.output)
            if args.print:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            logger.info("CV parsing completed successfully.")
        else:
            logger.error("Failed to parse CV. No output generated.")
            sys.exit(2)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(3)





from docx import Document
import os
import re
import nltk
import pandas as pd
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer, util
import spacy
import json
import dateparser
from datetime import datetime
import logging
from typing import Dict, List, Optional, Tuple
import warnings

warnings.filterwarnings('ignore')

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Download NLTK data
nltk.download('stopwords', quiet=True)
nltk.download("punkt")
nltk.download("punkt_tab")
nltk.download("wordnet")
nltk.download("averaged_perceptron_tagger")

"""Input Handling"""
def extract_text(file_path: str) -> str:
    """Extract text from PDF, DOCX, TXT files"""
    try:
        ext = os.path.splitext(file_path)[1].lower()
        def extract_text_from_docx(file_path: str) -> str:
            """Extract text from DOCX"""
            doc = Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        if file_path.endswith('.pdf'):
            reader = PdfReader(file_path)
            text = ''
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + '\n'
            return text
        elif ext in ['.docx', '.doc']:
            return extract_text_from_docx(file_path)
        elif file_path.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {str(e)}")
        raise

"""Text Cleaning & Tokenization"""

def clean_text(text: str) -> str:
    """Clean text while preserving important characters"""
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def split_sentences(text: str) -> List[str]:
    """Split text into sentences"""
    sentences = nltk.sent_tokenize(text)
    return sentences

"""Load Models (With Caching)"""

logger.info("Loading models...")
try:
    sbert_model = SentenceTransformer('all-MiniLM-L6-v2')
    nlp = spacy.load("en_core_web_sm")
    logger.info("Models loaded successfully!")
except Exception as e:
    logger.error(f"Error loading models: {str(e)}")
    raise

"""Regex Patterns"""

email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
phone_pattern = r'(?<!/)(?<!\d)\+?[\d\s()-]{10,}(?!\d)'
linkedin_pattern = r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+'
github_pattern = r'(?:https?://)?(?:www\.)?github\.com/[\w\-]+'

# Enhanced date patterns
month_pattern = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember))'
year_pattern = r'\d{4}'
date_pattern = f'(?:{month_pattern}\\s+{year_pattern}|{year_pattern})'
duration_pattern = f'({date_pattern})\\s*[-–—to]+\\s*(Present|Current|Now|{date_pattern})'



"""Load Skills and Job Titles CSV"""

def load_reference_data():
    """Load skills and job titles from CSV files with fallback"""
    try:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        # Try to load skills.csv
        try:
            skills_path = os.path.join(BASE_DIR, "data", "skills.csv")
            skills_df = pd.read_csv(skills_path)
            if 'skill_name' not in skills_df.columns:
                logger.warning("skills.csv missing 'skill_name' column, using fallback")
                skills_list = FALLBACK_SKILLS
            else:
                skills_list = skills_df['skill_name'].dropna().str.strip().unique().tolist()
                # Remove empty strings
                skills_list = [s for s in skills_list if s]
                logger.info(f"✅ Loaded {len(skills_list)} skills from skills.csv")
        except FileNotFoundError:
            logger.warning("❌ skills.csv not found, using fallback list")
            skills_list = FALLBACK_SKILLS

        # Try to load job_titles.csv
        try:
            job_titles_path = os.path.join(BASE_DIR, "data", "job_titles.csv")
            job_titles_df = pd.read_csv(job_titles_path)
            if 'title_name' not in job_titles_df.columns:
                logger.warning("job_titles.csv missing 'title_name' column, using fallback")
                job_titles_list = FALLBACK_JOB_TITLES
            else:
                job_titles_list = job_titles_df['title_name'].dropna().str.strip().unique().tolist()
                job_titles_list = [t for t in job_titles_list if t]
                logger.info(f"✅ Loaded {len(job_titles_list)} job titles from job_titles.csv")
        except FileNotFoundError:
            logger.warning("❌ job_titles.csv not found, using fallback list")
            job_titles_list = FALLBACK_JOB_TITLES

        # Create embeddings
        logger.info("Creating embeddings...")
        skills_embeddings = sbert_model.encode(skills_list, show_progress_bar=False, batch_size=32)
        job_titles_embeddings = sbert_model.encode(job_titles_list, show_progress_bar=False, batch_size=32)

        return skills_list, skills_embeddings, job_titles_list, job_titles_embeddings

    except Exception as e:
        logger.error(f"Error loading reference data: {str(e)}")
        logger.info("Using fallback lists")
        skills_embeddings = sbert_model.encode(FALLBACK_SKILLS, show_progress_bar=False)
        job_titles_embeddings = sbert_model.encode(FALLBACK_JOB_TITLES, show_progress_bar=False)
        return FALLBACK_SKILLS, skills_embeddings, FALLBACK_JOB_TITLES, job_titles_embeddings

# Load data
skills_list, skills_embeddings, job_titles_list, job_titles_embeddings = load_reference_data()

"""Helper Functions"""

TECH_KEYWORDS = {
    'typescript', 'javascript', 'python', 'java', 'html', 'css', 'php', 'sql',
    'react', 'next.js', 'redux', 'tailwind', 'mysql', 'postgresql', 'sqlite',
    'git', 'github', 'supabase', 'node.js', 'express', 'mongodb', 'aws',
    'docker', 'kubernetes', 'jenkins', 'c++', 'c#', 'ruby', 'swift', 'kotlin',
    'flutter', 'vue', 'angular', 'django', 'flask', 'laravel', 'spring'
}

def extract_name(text: str) -> str:
    """Extract name from first lines of CV"""
    lines = text.split('\n')[:5]

    for line in lines:
        line = line.strip()
        if 5 < len(line) < 50:
            words = line.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                if not any(char in line for char in ['@', '+', 'http', '|', '–']):
                    return line

    # Fallback to spaCy
    doc = nlp(' '.join(lines))
    for ent in doc.ents:
        if ent.label_ == "PERSON" and len(ent.text.split()) >= 2:
            return ent.text

    return ""

def extract_contact_info(text: str) -> Dict[str, List[str]]:
    """Extract all contact information with improved patterns"""
    emails = list(set(re.findall(email_pattern, text)))

    # Phone extraction with better filtering
    phone_matches = re.findall(phone_pattern, text)
    # Filter out numbers that appear in URLs or are too short
    phones = []
    for phone in phone_matches:
        clean_phone = re.sub(r'[^\d+]', '', phone)
        if len(clean_phone) >= 10 and 'linkedin' not in text[max(0, text.find(phone)-20):text.find(phone)+20].lower():
            phones.append(phone.strip())

    return {
        'email': emails,
        'phone': list(set(phones)),
        'linkedin': list(set(re.findall(linkedin_pattern, text, re.IGNORECASE))),
        'github': list(set(re.findall(github_pattern, text, re.IGNORECASE)))
    }

def extract_summary(text: str) -> str:
    """Extract professional summary with improved detection"""
    summary_keywords = [
        'summary', 'objective', 'profile', 'about', 'overview',
        'professional summary', 'career objective', 'career profile',
        'personal statement', 'executive summary', 'professional profile'
    ]

    lines = text.split('\n')
    
    # First pass: look for explicit summary section headers
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check if line contains any summary keyword
        if any(kw in line_lower for kw in summary_keywords):
            # This might be a section header
            summary_lines = []
            
            # Collect lines after the header
            for j in range(i + 1, min(i + 15, len(lines))):
                next_line = lines[j].strip()
                
                # Stop at next section
                if any(keyword in next_line.lower() for keyword in 
                       ['education', 'experience', 'work', 'technical skills', 
                        'skills', 'employment', 'history', 'certification', 
                        'projects', 'languages', 'contact']):
                    if len(next_line) < 30:  # Only stop on short section headers
                        break
                
                # Include meaningful lines
                if next_line and len(next_line) > 10:
                    summary_lines.append(next_line)
                    if len(' '.join(summary_lines)) > 400:
                        break
            
            if summary_lines:
                return ' '.join(summary_lines)
    
    # Second pass: look for content at the beginning before education/experience
    # This catches CVs without explicit summary headers
    first_section_idx = min(
        text.lower().find('education'),
        text.lower().find('experience'),
        text.lower().find('work history'),
        text.lower().find('employment')
    )
    
    if first_section_idx > 200:  # There's substantial content before first section
        intro_text = text[:first_section_idx]
        
        # Split into sentences and take first few meaningful ones
        sentences = nltk.sent_tokenize(intro_text)
        summary_parts = []
        
        for sent in sentences[:5]:  # Take first 5 sentences
            sent = sent.strip()
            if len(sent) > 30:  # Only meaningful sentences
                summary_parts.append(sent)
                if len(' '.join(summary_parts)) > 300:
                    break
        
        if summary_parts:
            return ' '.join(summary_parts)

    return ""

def extract_skills_with_confidence(text: str, similarity_threshold: float = 0.60) -> List[Dict]:
    """
    Extract skills using BOTH keyword matching and semantic similarity
    Returns list of dicts with name and confidence
    """
    found_skills = {}  # skill_name -> confidence
    text_lower = text.lower()

    # Method 1: Direct keyword matching (fast and accurate) - high confidence
    for skill in skills_list:
        skill_lower = skill.lower()
        pattern = r'\b' + re.escape(skill_lower) + r'\b'
        if re.search(pattern, text_lower):
            found_skills[skill] = 0.95  # High confidence for direct match

    # Method 2: Semantic similarity for variations
    if len(found_skills) < 10:
        text_emb = sbert_model.encode(text, show_progress_bar=False)
        similarities = util.cos_sim(text_emb, skills_embeddings)[0]

        for i, score in enumerate(similarities):
            skill_name = skills_list[i]
            if score > similarity_threshold:
                if skill_name not in found_skills:
                    found_skills[skill_name] = float(score)

    # Convert to list of dicts sorted by confidence
    result = [{"name": name, "confidence": round(conf, 2)} 
              for name, conf in found_skills.items()]
    return sorted(result, key=lambda x: x['confidence'], reverse=True)

def extract_job_titles_optimized(text: str, similarity_threshold: float = 0.65) -> List[str]:
    """Extract job titles using keyword matching and similarity"""
    found_titles = set()
    text_lower = text.lower()

    for title in job_titles_list:
        title_lower = title.lower()
        if title_lower in text_lower:
            found_titles.add(title)

    if len(found_titles) < 5:
        text_emb = sbert_model.encode(text, show_progress_bar=False)
        similarities = util.cos_sim(text_emb, job_titles_embeddings)[0]

        for i, score in enumerate(similarities):
            if score > similarity_threshold:
                found_titles.add(job_titles_list[i])

    return sorted(list(found_titles))

def extract_education(text: str) -> List[Dict]:
    """Extract education information with improved parsing"""
    education = []

    lines = text.split('\n')
    in_education = False
    edu_lines = []

    for line in lines:
        line_stripped = line.strip()
        if 'education' in line_stripped.lower() and len(line_stripped) < 30:
            in_education = True
            continue

        if in_education:
            if any(keyword in line_stripped.lower() for keyword in ['experience', 'work', 'project', 'technical skills']) and len(line_stripped) < 40:
                break
            if line_stripped:
                edu_lines.append(line_stripped)

    if edu_lines:
        edu_text = ' '.join(edu_lines)
        doc = nlp(edu_text)

        # Extract organizations - filter out tech keywords
        all_orgs = [ent.text for ent in doc.ents
                    if ent.label_ == 'ORG' and ent.text.lower() not in TECH_KEYWORDS]

        # Prioritize universities over faculties
        university = ""
        faculty = ""

        for org in all_orgs:
            if 'university' in org.lower() or 'college' in org.lower() or 'institute' in org.lower():
                university = org
            elif 'faculty' in org.lower() or 'school of' in org.lower() or 'department' in org.lower():
                faculty = org

        # Use university as primary school, or faculty if no university found
        school = university if university else (faculty if faculty else (all_orgs[0] if all_orgs else ""))

        # Extract degrees and faculty information
        degree_patterns = [
            r'(Bachelor|Master|PhD|Ph\.D\.|B\.Sc\.|M\.Sc\.|B\.A\.|M\.A\.|Associate|Diploma)[^.]*?(?:in|of)\s+([\w\s]+?)(?:\s+\d{4}|$|,|\|)',
            r'(BS|MS|BA|MA|BSc|MSc)\s+(?:in\s+)?([\w\s]+?)(?:\s+\d{4}|$|,|\|)',
            r'Faculty of ([\w\s]+?)(?:\s+\d{4}|$|,|\s+and\s+)',
        ]

        degree_info = ""
        field_of_study = ""

        for pattern in degree_patterns:
            matches = re.findall(pattern, edu_text, re.IGNORECASE)
            if matches:
                if len(matches[0]) == 2:  # Degree type + field
                    degree_type, field = matches[0]
                    degree_info = f"{degree_type.strip()} - {field.strip()}"
                    field_of_study = field.strip()
                elif isinstance(matches[0], str):  # Just field (Faculty of X)
                    field_of_study = matches[0].strip()
                    degree_info = f"Bachelor - {field_of_study}"  # Assume Bachelor's
                break

        # If we found faculty but no degree, use faculty as degree
        if not degree_info and faculty:
            degree_info = faculty

        # Extract years
        years = re.findall(r'\b(19\d{2}|20\d{2})\b', edu_text)

        # Extract GPA
        gpa_match = re.search(r'GPA[:\s]*([\d.]+)', edu_text, re.IGNORECASE)
        gpa = gpa_match.group(1) if gpa_match else ""

        # Extract location
        location = ""
        location_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2,})',  # City, Region, Country
            r'([A-Z][a-z]+),\s*([A-Z]{2,})',  # City, Country
        ]

        for pattern in location_patterns:
            loc_match = re.search(pattern, edu_text)
            if loc_match:
                location = loc_match.group(0)
                break

        # Extract GPE entities as fallback for location
        if not location:
            locations = [ent.text for ent in doc.ents if ent.label_ == 'GPE']
            if locations:
                location = ', '.join(locations[:2])  # Take first 2 location entities

        if school or degree_info:
            education.append({
                'degree': degree_info,
                'school': school,
                'year': f"{years[0]} - {years[1]}" if len(years) >= 2 else years[0] if years else "",
                'gpa': gpa,
                'location': location
            })

    return education

def parse_duration(duration_str: str) -> Tuple[str, str]:
    """Parse duration string into start and end dates"""
    if not duration_str:
        return "", ""

    parts = re.split(r'[-–—]', duration_str)
    if len(parts) != 2:
        return "", ""

    start = parts[0].strip()
    end = parts[1].strip()

    return start, end

def calculate_duration(start_str: str, end_str: str) -> float:
    """Calculate duration in years"""
    try:
        if not start_str:
            return 0.0

        start = dateparser.parse(start_str)
        if not start:
            return 0.0

        if any(word in end_str.lower() for word in ['present', 'current', 'now']):
            end = datetime.now()
        else:
            end = dateparser.parse(end_str)
            if not end:
                return 0.0

        delta = end - start
        years = delta.days / 365.25
        return round(max(years, 0.0), 1)
    except:
        return 0.0

def extract_experience(text: str) -> List[Dict]:
    """Extract work experience with improved parsing"""
    experiences = []

    lines = text.split('\n')
    in_experience = False
    exp_lines = []

    for line in lines:
        line_stripped = line.strip()
        if any(kw in line_stripped.lower() for kw in ['work experience', 'experience', 'employment history']) and len(line_stripped) < 50:
            in_experience = True
            continue

        if in_experience:
            if any(keyword in line_stripped.lower() for keyword in ['education', 'project', 'technical skills', 'certification']) and len(line_stripped) < 40:
                break
            if line_stripped:
                exp_lines.append(line_stripped)

    if not exp_lines:
        return []

    # Split into entries - improved logic
    entries = []
    current_entry = []

    for line in exp_lines:
        line = line.strip()

        # New entry starts with a job title + date OR just date pattern
        is_new_entry = False

        # Check if line contains date range
        if re.search(duration_pattern, line, re.IGNORECASE):
            # This is likely a header line with job title + dates
            is_new_entry = True
        # Check if it's a standalone location/type line after we have content
        elif current_entry and re.search(r'^\s*(Remote|On-?site|Hybrid)\s*$', line, re.IGNORECASE):
            # Add to current entry, don't start new one
            current_entry.append(line)
            continue
        # Check for bullet points (description lines)
        elif line.startswith('–') or line.startswith('-') or line.startswith('•'):
            if current_entry:
                current_entry.append(line)
                continue

        if is_new_entry:
            if current_entry:
                entries.append("\n".join(current_entry))
            current_entry = [line]
        else:
            if current_entry or not line.startswith('–'):
                current_entry.append(line)

    if current_entry:
        entries.append("\n".join(current_entry))

    # Parse each entry
    for entry in entries:
        # Extract dates first
        duration_matches = re.findall(duration_pattern, entry, re.IGNORECASE)
        duration_str = ""
        if duration_matches:
            start, end = duration_matches[0]
            duration_str = f"{start} - {end}"

        # Extract the first line (usually contains title)
        first_line = entry.split('\n')[0]

        # Remove date from first line to get title
        first_line_clean = re.sub(duration_pattern, '', first_line, flags=re.IGNORECASE).strip()
        first_line_clean = re.sub(r'\s+', ' ', first_line_clean)  # Clean extra spaces

        # Try to split title and company - look for patterns like "Title at Company" or "Title - Company"
        title = first_line_clean
        company = ""
        
        # Pattern: "Title – Company" or "Title - Company" or "Title at Company"
        title_company_match = re.match(r'^(.+?)(?:\s*[-–—]\s*|\s+at\s+)(.+)$', first_line_clean, re.IGNORECASE)
        if title_company_match:
            title = title_company_match.group(1).strip()
            company = title_company_match.group(2).strip()
        
        # If no company found, try NER but be more careful
        if not company:
            doc = nlp(entry)
            orgs = [ent.text for ent in doc.ents if ent.label_ == 'ORG']
            # Filter out tech keywords and short orgs
            org_list = [org for org in orgs 
                       if org.lower() not in TECH_KEYWORDS 
                       and len(org) > 2
                       and org.lower() != title.lower()]
            if org_list:
                company = org_list[0]
        
        # Detect job type
        job_type = "Full-time"
        if re.search(r'\bIntern\b|\bInternship\b', entry, re.IGNORECASE):
            job_type = "Internship"
        elif re.search(r'\bRemote\b', entry, re.IGNORECASE):
            job_type = "Remote"
        elif re.search(r'\bContract\b|\bFreelance\b', entry, re.IGNORECASE):
            job_type = "Contract"
        elif re.search(r'\bPart-time\b', entry, re.IGNORECASE):
            job_type = "Part-time"

        # Extract location
        location = ""
        location_match = re.search(r'\b(Remote|On-?site|Hybrid)\b', entry, re.IGNORECASE)
        if location_match:
            location = location_match.group(1)

        # Calculate years
        start, end = parse_duration(duration_str)
        years = calculate_duration(start, end)

        if title or company:
            experiences.append({
                'title': title,
                'company': company,
                'duration': duration_str,
                'location': location,
                'job_type': job_type,
                'years': years
            })

    return experiences
 
def parse_date_to_yyyy_mm_dd(date_str: str) -> str:
    """Parse various date formats and return YYYY-MM-DD format"""
    if not date_str:
        return ""
    
    date_str = date_str.strip()
    
    # Try different patterns
    patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),  # YYYY-MM-DD
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%m/%d/%Y'),  # MM/DD/YYYY
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', '%m-%d-%Y'),  # MM-DD-YYYY
        (r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+(\d{4})', '%b %Y'),  # Month YYYY
        (r'(\d{4})', '%Y'),  # Just year
    ]
    
    for pattern, fmt in patterns:
        match = re.search(pattern, date_str, re.IGNORECASE)
        if match:
            try:
                if fmt == '%Y':
                    return match.group(1)
                elif fmt == '%b %Y':
                    month_str = match.group(1)
                    year = match.group(2)
                    month_num = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                                 'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                                 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
                    return f"{year}-{month_num.get(month_str.lower()[:3], '01')}-01"
                else:
                    dt = datetime.strptime(match.group(0), fmt)
                    return dt.strftime('%Y-%m-%d')
            except:
                pass
    
    return date_str

def transform_to_output_format(cv_data: Dict) -> Dict:
    """Transform extracted data to the output format specified in CONTEXT.md"""
    
    # Extract name parts
    name = cv_data.get('name', '')
    if name:
        parts = name.strip().split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    else:
        first_name, last_name = "", ""
    
    # Get contact info
    emails = cv_data.get('email', [])
    phones = cv_data.get('phone', [])
    linkedins = cv_data.get('linkedin', [])
    githubs = cv_data.get('github', [])
    
    # Clean phone - take first valid phone
    phone = ""
    if phones:
        phone = phones[0].replace('\n', ' ').replace('  ', ' ').strip()
    
    # Transform education
    education_list = []
    for edu in cv_data.get('education', []):
        degree_str = edu.get('degree', '')
        degree_type = "OTHER"
        
        degree_lower = degree_str.lower()
        if 'bachelor' in degree_lower or 'b.sc' in degree_lower or 'bs' in degree_lower:
            degree_type = "BACHELOR"
        elif 'master' in degree_lower or 'm.sc' in degree_lower or 'ms' in degree_lower:
            degree_type = "MASTER"
        elif 'phd' in degree_lower or 'ph.d' in degree_lower or 'doctor' in degree_lower:
            degree_type = "PHD"
        elif 'associate' in degree_lower:
            degree_type = "ASSOCIATE"
        elif 'high school' in degree_lower:
            degree_type = "HIGH_SCHOOL"
        
        # Parse years - handle "2022 - 2026" format
        year_str = edu.get('year', '')
        start_date = ""
        end_date = ""
        is_current = False
        
        if year_str:
            parts = re.split(r'[-–—to]+', year_str)
            if len(parts) >= 1:
                start_date = parse_date_to_yyyy_mm_dd(parts[0].strip())
            if len(parts) >= 2:
                end_str = parts[1].strip()
                if any(word in end_str.lower() for word in ['present', 'current', 'now']):
                    is_current = True
                else:
                    end_date = parse_date_to_yyyy_mm_dd(end_str)
        
        # Extract field of study from degree string
        field_of_study = degree_str
        for prefix in ['Bachelor - ', 'Master - ', 'Bachelor of ', 'Master of ']:
            field_of_study = field_of_study.replace(prefix, '')
        
        education_list.append({
            "institutionName": edu.get('school', ''),
            "degreeType": degree_type,
            "fieldOfStudy": field_of_study.strip(),
            "startDate": start_date,
            "endDate": end_date if end_date else None,
            "isCurrent": is_current,
            "gpa": float(edu.get('gpa', '')) if edu.get('gpa') else None,
            "description": None
        })
    
    # Transform work experience
    work_experience_list = []
    work_preference = "ANY"
    
    for exp in cv_data.get('experience', []):
        duration_str = exp.get('duration', '')
        start_date = ""
        end_date = ""
        is_current = False
        
        if duration_str:
            parts = re.split(r'[-–—]+', duration_str)
            if len(parts) >= 1:
                start_date = parse_date_to_yyyy_mm_dd(parts[0].strip())
            if len(parts) >= 2:
                end_str = parts[1].strip()
                if any(word in end_str.lower() for word in ['present', 'current', 'now']):
                    is_current = True
                else:
                    end_date = parse_date_to_yyyy_mm_dd(end_str)
        
        # Get work preference from location
        location = exp.get('location', '')
        if location:
            loc_lower = location.lower()
            if 'remote' in loc_lower:
                work_preference = 'REMOTE'
            elif 'hybrid' in loc_lower:
                work_preference = 'HYBRID'
            elif 'onsite' in loc_lower or 'on-site' in loc_lower:
                work_preference = 'ONSITE'
        
        work_experience_list.append({
            "companyName": exp.get('company', ''),
            "jobTitle": exp.get('title', ''),
            "location": location if location else None,
            "startDate": start_date,
            "endDate": end_date if end_date else None,
            "isCurrent": is_current,
            "description": exp.get('description')
        })
    
    # Transform skills
    skills_list = cv_data.get('skills', [])
    
    # Get job title
    job_titles = cv_data.get('job_titles', [])
    title = job_titles[0] if job_titles else None
    
    # Calculate years of experience
    years_of_exp = cv_data.get('total_experience_years', 0.0)
    
    # Build output according to CONTEXT.md schema
    output = {
        "personalInfo": {
            "firstName": first_name,
            "lastName": last_name,
            "email": emails[0] if emails else "",
            "phone": phone,
            "location": "",
            "linkedinUrl": linkedins[0] if linkedins else None,
            "githubUrl": githubs[0] if githubs else None,
            "portfolioUrl": None
        },
        "professionalSummary": cv_data.get('summary', ''),
        "title": title,
        "education": education_list,
        "workExperience": work_experience_list,
        "skills": skills_list,
        "expectedSalary": None,
        "workPreference": work_preference,
        "yearsOfExperience": years_of_exp if years_of_exp > 0 else None,
        "noticePeriod": None,
        "availabilityStatus": None
    }
    
    return output


def parse_cv(file_path: str) -> Optional[Dict]:
    """
    Main function to parse CV

    Args:
        file_path: Path to CV file

    Returns:
        Dictionary containing extracted data or None on error
    """
    try:
        logger.info(f"Starting to parse CV: {file_path}")

        # 1. Extract text
        text = extract_text(file_path)
        if not text or len(text.strip()) < 50:
            logger.error("Extracted text is too short or empty")
            return None

        logger.info(f"Extracted {len(text)} characters from CV")

        # 2. Clean text
        cleaned_text = clean_text(text)

        # 3. Extract all information
        logger.info("Extracting CV information...")

        cv_data = {
            "name": extract_name(text),
            **extract_contact_info(text),
            "summary": extract_summary(text),
            "education": extract_education(text),
            "experience": extract_experience(text),
            "skills": extract_skills_with_confidence(cleaned_text),
            "job_titles": extract_job_titles_optimized(cleaned_text),
            "total_experience_years": 0.0
        }

        # 4. Calculate total experience
        total_exp = sum(exp.get('years', 0.0) for exp in cv_data['experience'])
        cv_data['total_experience_years'] = round(total_exp, 1)

        # 5. Transform to output format
        output_data = transform_to_output_format(cv_data)

        # 6. Validation
        if not cv_data['name']:
            logger.warning("⚠️ Could not extract candidate name")
        if not cv_data['email']:
            logger.warning("⚠️ Could not extract email address")

        logger.info(f"✅ Successfully parsed CV:")
        logger.info(f"   - Skills: {len(output_data['skills'])}")
        logger.info(f"   - Job Titles: {len(output_data.get('title', ''))}")
        logger.info(f"   - Experience Entries: {len(output_data['workExperience'])}")
        logger.info(f"   - Education Entries: {len(output_data['education'])}")

        return output_data

    except Exception as e:
        logger.error(f"❌ Error parsing CV: {str(e)}", exc_info=True)
        return None

"""Validation & Output Functions"""

def save_to_json(cv_data: Dict, output_path: str) -> bool:
    """Save data to JSON file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cv_data, f, indent=4, ensure_ascii=False)
        logger.info(f"✅ CV data saved to {output_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving to JSON: {str(e)}")
        return False

def print_cv_summary(cv_data: Dict):
    """Print summary of extracted data"""

if __name__ == "__main__":
    main()
# CLI entry point will be added below