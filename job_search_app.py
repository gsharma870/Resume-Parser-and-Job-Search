import streamlit as st
import pdfplumber
import json
import re
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from html.parser import HTMLParser

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Automotive Job Search Assistant",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color: #0f1117; }

  .card {
    background: #1a1d27; border: 1px solid #2d3040;
    border-radius: 12px; padding: 1.4rem 1.6rem; margin-bottom: 1rem;
  }
  .job-card {
    background: #1a1d27; border: 1px solid #2d3040;
    border-left: 4px solid #4f8ef7; border-radius: 10px;
    padding: 1.2rem 1.4rem; margin-bottom: 1rem; transition: border-color .2s;
  }
  .job-card:hover { border-left-color: #7eb3ff; }

  .badge-high   { background:#1a4731; color:#4ade80; border-radius:20px; padding:3px 12px; font-size:.78rem; font-weight:600; }
  .badge-medium { background:#3b2f14; color:#facc15; border-radius:20px; padding:3px 12px; font-size:.78rem; font-weight:600; }
  .badge-low    { background:#3b1414; color:#f87171; border-radius:20px; padding:3px 12px; font-size:.78rem; font-weight:600; }

  .skill-tag {
    display:inline-block; background:#1e2a3a; color:#7eb3ff;
    border:1px solid #2d4a6a; border-radius:16px;
    padding:3px 12px; margin:3px 4px 3px 0; font-size:.8rem;
  }
  .skill-tag-gap {
    display:inline-block; background:#2a1e1e; color:#f87171;
    border:1px solid #4a2d2d; border-radius:16px;
    padding:3px 12px; margin:3px 4px 3px 0; font-size:.8rem;
  }
  .metric-tile {
    background:#1a1d27; border:1px solid #2d3040;
    border-radius:10px; padding:1rem; text-align:center;
  }
  .metric-number { font-size:2rem; font-weight:700; color:#4f8ef7; }
  .metric-label  { font-size:.85rem; color:#9ca3af; margin-top:4px; }

  h1,h2,h3 { color:#f0f2f6; }
  p, li { color:#c9cdd4; }
  a { color:#7eb3ff !important; }
  .stExpander { border:1px solid #2d3040 !important; border-radius:10px !important; }
</style>
""", unsafe_allow_html=True)

# ── Paths ──────────────────────────────────────────────────────────────────────
DEFAULT_RESUME = Path(__file__).parent / "GSharma_Resume.pdf"
CACHE_FILE     = Path(__file__).parent / "jobs_cache.json"
CACHE_TTL_HRS  = 24

# ══════════════════════════════════════════════════════════════════════════════
# RESUME UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def extract_pdf_text(file_obj) -> str:
    try:
        with pdfplumber.open(file_obj) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        return f"Error reading PDF: {e}"


def resume_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


SKILL_VOCAB = [
    "Eye-Tracking", "Usability Testing", "Mixed-Methods Research",
    "Experimental Design", "Psychophysical Experiments", "Survey Design",
    "In-Depth Interviews", "Thematic Coding", "Affinity Mapping", "Personas",
    "Regression Analysis", "ANOVA", "t-tests", "Multi-level Modeling",
    "Factor Analysis", "Likert Scaling", "Python", "R", "MATLAB",
    "Smart Eye Pro", "Gaze Metrics", "Qualtrics", "Wizard-of-Oz Prototyping",
    "Human-Vehicle Interaction", "ADAS", "HMI Design", "Haptic Feedback",
    "Immersive Environments", "AB Testing", "Situational Awareness",
]

def parse_resume(text: str) -> dict:
    data = {"name": "", "skills": []}
    for line in text.splitlines():
        if line.strip():
            data["name"] = line.strip()
            break
    for kw in SKILL_VOCAB:
        if kw.lower() in text.lower():
            data["skills"].append(kw)
    return data


def build_search_queries(resume_text: str) -> list:
    txt = resume_text.lower()
    queries = [
        "HMI Researcher automotive",
        "UX Researcher ADAS autonomous driving",
        "Human Factors Researcher automotive",
        "Senior UX Researcher automotive",
    ]
    if "eye" in txt and "track" in txt:
        queries.append("eye tracking researcher automotive")
    if "psychophys" in txt:
        queries.append("psychophysics human factors automotive")
    if "haptic" in txt:
        queries.append("haptic feedback HMI researcher")
    if "adas" in txt or "advanced driver" in txt:
        queries.append("ADAS human factors engineer")
    if "autonomous" in txt or "self-driving" in txt:
        queries.append("autonomous driving UX researcher")
    return queries

# ══════════════════════════════════════════════════════════════════════════════
# JOB ENRICHMENT
# ══════════════════════════════════════════════════════════════════════════════

TAG_MAP = {
    "ADAS":               ["adas", "advanced driver", "driver assistance", "adaptive cruise", "lane keep"],
    "Autonomous Driving": ["autonomous", "self-driving", "robotaxi", "level 3", "level 4", "level 2"],
    "UX Research":        ["ux research", "user research", "usability", "user experience", "ux researcher"],
    "HMI":                ["hmi", "human machine interface", "in-vehicle", "cockpit", "infotainment"],
    "Human Factors":      ["human factors", "ergonomics", "cognitive", "psychophysics", "human-systems"],
    "Eye-Tracking":       ["eye track", "gaze", "smart eye", "tobii", "eye movement"],
    "EV":                 ["electric vehicle", " ev ", "battery electric", " bev"],
    "Rider Experience":   ["rider", "passenger experience", "robotaxi rider"],
    "Management":         ["manager", "research lead", "director", "head of research"],
    "Simulation":         ["driving simulator", "simulation", "carla", "carmaker"],
}

GAP_MAP = {
    "Figma / Axure Prototyping":    ["figma", "axure", "wireframe", "prototype tool"],
    "SQL / Data Engineering":       ["sql", "bigquery", "data warehouse", "database query"],
    "ISO 26262 / SOTIF":            ["iso 26262", "sotif", "iso 21448", "functional safety"],
    "CAN Bus / Vehicle Data":       ["can bus", "can signal", "obd", "vehicle telemetry"],
    "Simulator Programming":        ["carla", "carmaker", "openscenario", "simulation software"],
    "Research Ops (Dovetail/Maze)": ["dovetail", "maze ", "usertesting.com", "research ops"],
    "Bayesian Modeling":            ["bayesian", "stan ", "pymc", "probabilistic model"],
    "EEG / GSR Physiology":         ["eeg", "gsr", "galvanic skin", "biometric", "biosignal"],
}

FIT_KEYWORDS_HIGH = [
    "adas", "hmi", "eye-tracking", "eye tracking", "psychophysics",
    "human factors", "human-vehicle", "ux researcher", "hci researcher",
    "autonomous driving", "driver assistance", "automated driving",
    "human machine interface", "driver experience", "hmi researcher",
]
FIT_KEYWORDS_MED = [
    "usability", "user research", "user experience", "automotive",
    "in-vehicle", "cockpit", "infotainment", "driver", "vehicle",
    "mixed method", "qualitative", "quantitative", "researcher",
    "perception", "trust", "transparency", "interaction",
]


def auto_tag(job_text: str) -> list:
    txt = job_text.lower()
    return [tag for tag, kws in TAG_MAP.items() if any(k in txt for k in kws)]


def detect_gaps(job_text: str, resume_text: str) -> list:
    jt, rt = job_text.lower(), resume_text.lower()
    return [
        skill for skill, kws in GAP_MAP.items()
        if any(k in jt for k in kws) and not any(k in rt for k in kws)
    ]


def score_fit(job_text: str, resume_text: str) -> str:
    jt, rt = job_text.lower(), resume_text.lower()
    # Count high-value keywords present in BOTH job and resume
    hi  = sum(1 for k in FIT_KEYWORDS_HIGH if k in jt and k in rt)
    # Count medium keywords present in job (regardless of resume — they indicate domain fit)
    med = sum(1 for k in FIT_KEYWORDS_MED if k in jt)
    if hi >= 2 or (hi >= 1 and med >= 3): return "High"
    if hi >= 1 or med >= 4:               return "Medium"
    return "Low"


def enrich(job: dict, resume_text: str) -> dict:
    combined        = job.get("title", "") + " " + job.get("description", "")
    job["fit"]        = score_fit(combined, resume_text)
    job["tags"]       = auto_tag(combined) or ["Automotive"]
    job["gap_skills"] = detect_gaps(combined, resume_text)
    return job

# ══════════════════════════════════════════════════════════════════════════════
# LIVE JOB FETCHING (Indeed RSS)
# ══════════════════════════════════════════════════════════════════════════════

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks = []
    def handle_data(self, d):
        self.chunks.append(d)
    def get_text(self):
        return " ".join(self.chunks)

def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return re.sub(r"\s+", " ", s.get_text()).strip()


def fetch_indeed_rss(query: str, location: str = "United States", limit: int = 12) -> list:
    params = urllib.parse.urlencode({"q": query, "l": location, "sort": "date", "limit": limit})
    url    = f"https://www.indeed.com/rss?{params}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
        root    = ET.fromstring(raw)
        channel = root.find("channel")
        jobs, seen_urls, seen_titles = [], set(), set()

        for item in channel.findall("item"):
            title_raw = item.findtext("title", "").strip()
            link      = item.findtext("link",  "").strip()
            desc_html = item.findtext("description", "")
            pub_date  = item.findtext("pubDate", "")

            if link in seen_urls:
                continue
            seen_urls.add(link)

            company, title = "", title_raw
            if " - " in title_raw:
                parts   = title_raw.rsplit(" - ", 1)
                title   = parts[0].strip()
                company = parts[1].strip()

            title_key = title.lower()[:40]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            desc = _strip_html(desc_html)[:600]

            posted = "Recent"
            if pub_date:
                try:
                    dt     = datetime.strptime(pub_date[:25], "%a, %d %b %Y %H:%M:%S")
                    posted = dt.strftime("%d %b %Y")
                except Exception:
                    posted = pub_date[:16]

            jobs.append({
                "title":       title,
                "company":     company,
                "location":    "",
                "description": desc,
                "url":         link,
                "posted":      posted,
                "source":      "live",
                "requirements": [],
                "fit":         "Medium",
                "tags":        [],
                "gap_skills":  [],
            })
        return jobs
    except Exception:
        return []


def fetch_all_live_jobs(queries: list, resume_text: str) -> list:
    seen_urls, seen_titles, raw = set(), set(), []
    for q in queries:
        for job in fetch_indeed_rss(q):
            tkey = job["title"].lower()[:40]
            if job["url"] not in seen_urls and tkey not in seen_titles:
                seen_urls.add(job["url"])
                seen_titles.add(tkey)
                raw.append(job)

    enriched = [enrich(j, resume_text) for j in raw]
    order    = {"High": 0, "Medium": 1, "Low": 2}
    enriched.sort(key=lambda j: order.get(j["fit"], 2))
    return enriched

# ══════════════════════════════════════════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════════════════════════════════════════

def save_cache(jobs: list, resume_hash_val: str):
    try:
        CACHE_FILE.write_text(json.dumps({
            "updated_at":  datetime.utcnow().isoformat(),
            "resume_hash": resume_hash_val,
            "jobs":        jobs,
        }, indent=2))
    except Exception:
        pass


def load_cache():
    if not CACHE_FILE.exists():
        return None
    try:
        payload = json.loads(CACHE_FILE.read_text())
        updated = datetime.fromisoformat(payload["updated_at"])
        if datetime.utcnow() - updated < timedelta(hours=CACHE_TTL_HRS):
            return payload
    except Exception:
        pass
    return None


def cache_age_str() -> str:
    if not CACHE_FILE.exists():
        return "never"
    try:
        payload = json.loads(CACHE_FILE.read_text())
        updated = datetime.fromisoformat(payload["updated_at"])
        mins    = int((datetime.utcnow() - updated).total_seconds() // 60)
        if mins < 60:  return f"{mins}m ago"
        if mins < 1440: return f"{mins//60}h ago"
        return f"{mins//1440}d ago"
    except Exception:
        return "unknown"

# ══════════════════════════════════════════════════════════════════════════════
# CURATED BASELINE (always shown, scored dynamically against resume)
# ══════════════════════════════════════════════════════════════════════════════

CURATED_JOBS = [
    {
        "title": "Senior UX Researcher, Rider Experience", "company": "Waymo",
        "location": "San Francisco / Mountain View, CA",
        "description": (
            "Waymo is hiring a Senior UX Researcher focused on the One robotaxi rider experience — "
            "trust, transparency, in-vehicle UI, and emotional experience from boarding to drop-off. "
            "Mixed-methods research (qualitative + quantitative) feeds directly into product and engineering."
        ),
        "requirements": [
            "5+ years UX research in mobility, automotive, or related domain",
            "Strong mixed-methods expertise (interviews, surveys, field research)",
            "PhD or Master's in HCI, Psychology, or Cognitive Science preferred",
        ],
        "url": "https://www.linkedin.com/jobs/view/senior-ux-researcher-rider-experience-at-waymo-4344062954",
        "posted": "Active — Mar 2026", "source": "curated",
    },
    {
        "title": "Senior UX Researcher, Weavers UX and Design", "company": "Woven by Toyota",
        "location": "Tokyo / Remote-friendly (Japan)",
        "description": (
            "Supporting four pillars: AD/ADAS, Arene (software-defined vehicle platform), Woven City, and Cloud & AI. "
            "7+ years UX research required; own complex projects, mentor teammates, drive data-informed decisions."
        ),
        "requirements": [
            "7+ years UX research or equivalent experience",
            "Bachelor's in Psychology, Human Factors, HCI, or Robotics",
            "Strong qualitative and quantitative research skills",
        ],
        "url": "https://jobs.lever.co/woven-by-toyota/d802556d-3889-4c4b-ba85-d816b0690cf0",
        "posted": "Active — Mar 2026", "source": "curated",
    },
    {
        "title": "UX Researcher", "company": "Applied Intuition",
        "location": "Sunnyvale, CA (On-site)",
        "description": (
            "Applied Intuition ($15B, powering 18 of top-20 global automakers) needs a UX Researcher for field research, "
            "ethnographic studies with professional users, and usability testing on ADAS/AV interaction designs. "
            "Salary: $91K–$141K + equity."
        ),
        "requirements": [
            "Experience with field research / ethnographic studies with professional users",
            "Ability to run usability tests (in-lab and remote) on complex interaction flows",
            "Comfortable scoping research independently at the product level",
        ],
        "url": "https://boards.greenhouse.io/appliedintuition",
        "posted": "Active — Mar 2026", "source": "curated",
    },
    {
        "title": "HMI Researcher – ADAS & Automated Driving", "company": "Mercedes-Benz R&D North America",
        "location": "Sunnyvale, CA / Detroit, MI (Hybrid)",
        "description": (
            "Evaluate driver interaction with Level 2+ ADAS systems. Design user studies, conduct eye-tracking analyses, "
            "translate findings into HMI design guidelines. Collaborate with engineering teams in Stuttgart."
        ),
        "requirements": [
            "PhD or Master's in HCI, Cognitive Science, or Human Factors",
            "3+ years in automotive HMI research",
            "Proficiency with eye-tracking hardware and analysis (e.g., Smart Eye)",
        ],
        "url": "https://group.mercedes-benz.com/careers/", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "Senior Human Factors Researcher", "company": "Ford Motor Company",
        "location": "Dearborn, MI (Hybrid)",
        "description": (
            "Lead driver-centered research for ADAS and connected vehicle technologies. "
            "Plan and execute lab and real-world studies; synthesize findings for engineering and design; mentor junior researchers."
        ),
        "requirements": [
            "PhD preferred in Human Factors, HCI, or Cognitive Psychology",
            "7+ years automotive human factors research",
            "Experience with driving simulators and instrumented vehicles",
        ],
        "url": "https://ford.wd12.myworkdayjobs.com/fordcareers", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "Staff UX Researcher – Driver Assistance Systems", "company": "General Motors",
        "location": "Warren, MI / Austin, TX (Hybrid)",
        "description": (
            "Super Cruise team: evaluate driver trust, engagement, and misuse of hands-free ADAS. "
            "Design within/between-subject experiments, naturalistic driving studies, present to senior leadership."
        ),
        "requirements": [
            "PhD in HCI, Human Factors, or Psychology",
            "5+ years automotive UX or human factors research",
            "Experience with SAE Level 2/3 systems and driver monitoring",
        ],
        "url": "https://search-careers.gm.com/", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "HMI & UX Researcher – Automated Driving", "company": "BMW Group",
        "location": "San Jose, CA (Hybrid)",
        "description": (
            "Study driver behavior during automated driving handovers. Eye-tracking, physiological measurement, "
            "and usability evaluation in simulator and on-road contexts. Feeds Munich product teams."
        ),
        "requirements": [
            "PhD or Master's in HCI or Engineering Psychology",
            "Experience with automation handover research (takeover requests)",
            "Proficiency in multimodal data analysis (gaze, physiology, CAN bus)",
        ],
        "url": "https://www.bmwgroup.jobs/", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "Senior UX Researcher – Infotainment & Cockpit", "company": "Lucid Motors",
        "location": "Newark, CA (Hybrid)",
        "description": (
            "Evaluate in-cabin experience of DreamDrive ADAS and infotainment systems. "
            "Work with UI/UX designers and system engineers on concept validation and iterative usability tests."
        ),
        "requirements": [
            "5+ years UX research, automotive or consumer electronics",
            "Ability to run formative and summative research",
            "Familiarity with ADAS feature sets (adaptive cruise, lane keeping)",
        ],
        "url": "https://jobs.lucidmotors.com/", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "Human Factors Scientist – ADAS Perception", "company": "Mobileye (Intel)",
        "location": "Detroit, MI / Remote-friendly",
        "description": (
            "Evaluate how drivers interact with vision-based ADAS features. Bridge psychophysical experimentation, "
            "perception research, and real-world validation. Define human performance benchmarks."
        ),
        "requirements": [
            "PhD in Human Factors, Experimental Psychology, or Vision Science",
            "Strong background in perception and psychophysics",
            "Programming in Python or MATLAB for data analysis",
        ],
        "url": "https://jobs.mobileye.com/", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "Senior Researcher – Driver Experience & Trust", "company": "Toyota Research Institute (TRI)",
        "location": "Los Altos, CA (Hybrid)",
        "description": (
            "Study driver trust calibration and mental model formation for automated driving. "
            "Design simulator and real-world studies; collaborate with AI and robotics teams. Salary: $180K–$270K (CA)."
        ),
        "requirements": [
            "PhD in HCI, Human Factors, Cognitive Science, or Psychology",
            "Prior research on trust, transparency, or explainability in automation",
            "Strong publication record",
        ],
        "url": "https://jobs.lever.co/tri", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "Human Factors Engineer – Vehicle Automation", "company": "Aptiv",
        "location": "Troy, MI (Hybrid)",
        "description": (
            "Define human-system interaction requirements for ADAS platforms. "
            "Focus on ISO 26262/SOTIF compliance, human error analysis, and translating HF insights into design specs."
        ),
        "requirements": [
            "Master's or PhD in Human Factors or Systems Engineering",
            "Experience with SOTIF (ISO 21448) and functional safety",
        ],
        "url": "https://www.aptiv.com/en/about/careers", "posted": "Check career page", "source": "curated",
    },
    {
        "title": "UX Researcher – Cockpit & Infotainment Systems", "company": "Volkswagen Group of America",
        "location": "Herndon, VA / Belmont, CA (Hybrid)",
        "description": (
            "Evaluate cockpit and infotainment experience across VW, Audi, and Porsche brands. "
            "Usability studies, heuristic evaluations, and competitive benchmarking."
        ),
        "requirements": [
            "5+ years UX research in automotive or connected devices",
            "Experience with heuristic evaluation and competitive analysis",
        ],
        "url": "https://www.vw.com/en/models/careers.html", "posted": "Check career page", "source": "curated",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# STATIC ANALYSIS DATA
# ══════════════════════════════════════════════════════════════════════════════

CANDIDATE_SKILLS = [
    "Mixed-Methods Research", "Eye-Tracking (Smart Eye Pro)", "Psychophysics",
    "Usability Testing", "Experimental Design (Within/Between-Subjects)",
    "Survey Design (Qualtrics)", "In-Depth Interviews", "Thematic Coding",
    "Affinity Mapping", "Personas", "Regression Analysis", "ANOVA", "t-tests",
    "Multi-level Modeling", "Factor Analysis", "Python", "R", "MATLAB",
    "Wizard-of-Oz Prototyping", "Human-Vehicle Interaction", "ADAS Research",
    "HMI Design Guidelines", "Haptic Feedback Research", "Situational Awareness",
    "AB Testing", "Likert Scaling",
]

RECOMMENDED_SKILLS = [
    ("Figma / Axure Prototyping",       "Many product-facing UX researcher roles expect basic prototyping literacy to collaborate with designers."),
    ("Bayesian Modeling (Stan / PyMC3)", "TRI, Waymo, and academia-adjacent roles increasingly use Bayesian methods alongside frequentist approaches."),
    ("SQL for Log Data Analysis",        "Ride-data and fleet telemetry analysis at scale (Waymo, Zoox) requires SQL."),
    ("ISO 26262 / SOTIF (ISO 21448)",    "Tier-1 and OEM engineering teams expect human factors engineers to understand functional safety standards."),
    ("CAN Bus / Vehicle Data Integration","Merging eye-tracking with vehicle CAN data is sought-after at BMW, Mercedes, and GM."),
    ("Driving Simulator Programming",   "Hands-on simulator setup (CARLA, CarMaker) distinguishes senior researchers at OEMs."),
    ("Research Ops (Dovetail, Maze)",   "Modern UX research teams use dedicated platforms for recruiting, synthesis, and sharing insights."),
    ("XAI / Explainable AI Familiarity","As automation transparency becomes central, familiarity with explainability concepts adds depth."),
    ("Physiological Signals (EEG, GSR)","Several BMW, Mercedes, and Mobileye roles list multimodal physiological data as a differentiator."),
]

ROLE_SUGGESTIONS = [
    ("Senior HMI Researcher",             "Direct match — your Audi + Toyota background and hands-free driving research are a perfect fit."),
    ("Senior UX Researcher (Automotive)", "Strong fit — emphasize ADAS usability studies and stakeholder deliverables."),
    ("Human Factors Scientist / Engineer","Strong fit — lean on your psychophysics expertise and threshold-detection publications."),
    ("UX Research Lead / Manager",        "Stretch role — consider highlighting any mentoring or project leadership at Audi."),
    ("Research Scientist – HVI",          "Academia-industry hybrid; publications and postdoc are competitive advantages."),
    ("Driver Experience Researcher",      "Emerging title at EV startups; emphasize trust, transparency, and behavioral research."),
]

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════════════

for key, default in [
    ("jobs", []), ("last_updated", None),
    ("resume_hash", ""), ("fetch_error", ""), ("live_count", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🚗 Job Search Assistant")
    st.markdown("*Automotive HMI & UX Research*")
    st.divider()

    st.markdown("### Upload Resume")
    uploaded = st.file_uploader("Upload a PDF resume", type=["pdf"], label_visibility="collapsed")
    st.caption("Default: GSharma_Resume.pdf")

    st.divider()
    st.markdown("### Job Search")
    st.caption(f"Last searched: **{cache_age_str()}**")
    do_refresh = st.button(
        "🔄 Refresh Job Listings", use_container_width=True,
        help="Re-search Indeed for the latest openings (10–15 s).",
    )

    st.divider()
    st.markdown("### Filter Jobs")
    fit_filter = st.multiselect(
        "Fit Level", ["High", "Medium", "Low"], default=["High", "Medium"],
    )
    source_filter = st.multiselect(
        "Source", ["Live (Indeed)", "Curated"], default=["Live (Indeed)", "Curated"],
    )
    all_tags   = sorted({t for j in (st.session_state.jobs or CURATED_JOBS) for t in j.get("tags", [])})
    tag_filter = st.multiselect("Tags / Domain", all_tags, default=[])

    st.divider()
    st.markdown("### Quick Stats")
    job_pool = st.session_state.jobs or CURATED_JOBS
    st.markdown(f'<div class="metric-tile"><div class="metric-number">{len(job_pool)}</div><div class="metric-label">Listings</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-tile" style="margin-top:.5rem"><div class="metric-number">{sum(1 for j in job_pool if j.get("fit")=="High")}</div><div class="metric-label">High Fit</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-tile" style="margin-top:.5rem"><div class="metric-number" style="color:#4ade80">{st.session_state.live_count}</div><div class="metric-label">Live (Indeed)</div></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# LOAD RESUME
# ══════════════════════════════════════════════════════════════════════════════

if uploaded:
    resume_text   = extract_pdf_text(uploaded)
    resume_source = f"Uploaded: **{uploaded.name}**"
elif DEFAULT_RESUME.exists():
    resume_text   = extract_pdf_text(str(DEFAULT_RESUME))
    resume_source = "Default: **GSharma_Resume.pdf**"
else:
    resume_text   = ""
    resume_source = "No resume loaded"

parsed       = parse_resume(resume_text)
current_hash = resume_hash(resume_text) if resume_text else ""

# ══════════════════════════════════════════════════════════════════════════════
# REFRESH LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def do_job_refresh(resume_text: str, current_hash: str):
    queries   = build_search_queries(resume_text)
    live_jobs = fetch_all_live_jobs(queries, resume_text)

    curated = [enrich(dict(j), resume_text) for j in CURATED_JOBS]

    # Drop curated entries whose company already appears in live results
    live_companies = {j["company"].lower() for j in live_jobs}
    deduped = [
        j for j in curated
        if not any(
            j["company"].lower() in lc or lc in j["company"].lower()
            for lc in live_companies
        )
    ]

    order  = {"High": 0, "Medium": 1, "Low": 2}
    merged = sorted(live_jobs + deduped, key=lambda j: order.get(j.get("fit", "Low"), 2))

    st.session_state.jobs         = merged
    st.session_state.last_updated = datetime.utcnow().isoformat()
    st.session_state.resume_hash  = current_hash
    st.session_state.live_count   = len(live_jobs)
    st.session_state.fetch_error  = (
        "" if live_jobs else
        "⚠️ Could not reach Indeed RSS (network or rate-limit). Showing curated listings only."
    )
    save_cache(merged, current_hash)


resume_changed = bool(current_hash) and current_hash != st.session_state.resume_hash

if do_refresh and resume_text:
    with st.spinner("Searching Indeed for the latest openings… (10–15 s)"):
        do_job_refresh(resume_text, current_hash)
    st.rerun()

elif resume_changed and resume_text:
    with st.spinner("New resume detected — re-scoring and re-searching…"):
        do_job_refresh(resume_text, current_hash)
    st.rerun()

elif not st.session_state.jobs:
    cached = load_cache()
    if cached:
        st.session_state.jobs         = cached["jobs"]
        st.session_state.last_updated = cached["updated_at"]
        st.session_state.resume_hash  = cached.get("resume_hash", "")
        st.session_state.live_count   = sum(1 for j in cached["jobs"] if j.get("source") == "live")
    else:
        # No cache yet — show curated scored against current resume
        st.session_state.jobs       = [enrich(dict(j), resume_text) for j in CURATED_JOBS]
        st.session_state.live_count = 0

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("# 🚗 Automotive Job Search Assistant")
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f"Resume loaded — {resume_source}")
with col_h2:
    if st.session_state.last_updated:
        try:
            dt_str = datetime.fromisoformat(st.session_state.last_updated).strftime("%d %b %Y %H:%M UTC")
        except Exception:
            dt_str = str(st.session_state.last_updated)[:16]
        st.caption(f"Jobs last refreshed: {dt_str}")

if st.session_state.fetch_error:
    st.warning(st.session_state.fetch_error)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4 = st.tabs(["📋 Resume Analysis", "💼 Job Matches", "🎯 Skill Gaps", "📄 Raw Resume"])

# ────────────────────────────────────────────────────────────────────────────
# TAB 1 — Resume Analysis
# ────────────────────────────────────────────────────────────────────────────
with tab1:
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown("### 👤 Candidate Profile")
        st.markdown(
            f'<div class="card"><h3 style="margin:0;color:#f0f2f6">{parsed["name"] or "Gyanendra Sharma"}</h3>'
            f'<p style="color:#9ca3af;margin:4px 0 0">Senior HMI & UX Researcher · 7+ Years · Automotive ADAS</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown("### 🏆 Recommended Roles")
        for role, reason in ROLE_SUGGESTIONS:
            with st.expander(f"**{role}**"):
                st.markdown(f"*{reason}*")

    with col_right:
        st.markdown("### 🛠 Detected Skills")
        skills_html = "".join(
            f'<span class="skill-tag">{s}</span>'
            for s in (parsed["skills"] or CANDIDATE_SKILLS)
        )
        st.markdown(f'<div class="card">{skills_html}</div>', unsafe_allow_html=True)

        st.markdown("### 📈 Experience Timeline")
        for period, title, org in [
            ("2023 – Present", "Senior HMI Researcher",  "Audi of America (ADAS)"),
            ("2021 – 2023",    "HMI Researcher",          "Toyota Research Institute / Woven Planet"),
            ("2019 – 2020",    "Postdoctoral Researcher", "Northeastern University"),
            ("2014 – 2019",    "PhD Researcher",          "Rensselaer Polytechnic Institute"),
        ]:
            st.markdown(f"""
            <div style="display:flex;gap:1rem;align-items:flex-start;margin-bottom:.8rem">
              <div style="min-width:110px;color:#4f8ef7;font-size:.8rem;padding-top:2px">{period}</div>
              <div>
                <div style="color:#f0f2f6;font-weight:600">{title}</div>
                <div style="color:#9ca3af;font-size:.85rem">{org}</div>
              </div>
            </div>""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# TAB 2 — Job Matches
# ────────────────────────────────────────────────────────────────────────────
with tab2:
    source_map      = {"Live (Indeed)": "live", "Curated": "curated"}
    allowed_sources = {source_map[s] for s in source_filter}

    filtered = [
        j for j in st.session_state.jobs
        if j.get("fit", "Low") in fit_filter
        and j.get("source", "curated") in allowed_sources
        and (not tag_filter or any(t in j.get("tags", []) for t in tag_filter))
    ]

    live_ct    = sum(1 for j in filtered if j.get("source") == "live")
    curated_ct = sum(1 for j in filtered if j.get("source") == "curated")

    st.markdown(f"### 💼 {len(filtered)} Matching Positions")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            '<span style="background:#1a3a1a;color:#4ade80;border-radius:6px;padding:3px 10px;'
            'font-size:.78rem;font-weight:600">🟢 Live (Indeed)</span> — freshly fetched from Indeed RSS',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<span style="background:#1e2a3a;color:#7eb3ff;border-radius:6px;padding:3px 10px;'
            'font-size:.78rem;font-weight:600">🔵 Curated</span> — known-hiring company; check career page',
            unsafe_allow_html=True,
        )
    st.caption(
        f"Scored dynamically against your resume · {live_ct} live · {curated_ct} curated  "
        f"· Hit **🔄 Refresh** in the sidebar to re-search"
    )

    if not filtered:
        st.info("No jobs match your current filters. Try expanding Fit Level or Source in the sidebar.")
    else:
        for job in filtered:
            fit       = job.get("fit", "Medium")
            badge_cls = f"badge-{fit.lower()}"
            tags_html = "".join(
                f'<span class="skill-tag" style="font-size:.73rem">{t}</span>'
                for t in job.get("tags", [])
            )
            is_live   = job.get("source") == "live"
            src_badge = (
                '<span style="background:#1a3a1a;color:#4ade80;border-radius:6px;'
                'padding:2px 8px;font-size:.72rem;font-weight:600;margin-right:6px">🟢 LIVE</span>'
                if is_live else
                '<span style="background:#1e2a3a;color:#7eb3ff;border-radius:6px;'
                'padding:2px 8px;font-size:.72rem;font-weight:600;margin-right:6px">🔵 CURATED</span>'
            )
            loc  = job.get("location", "") or "See posting for location"
            post = job.get("posted", "Recent")

            with st.container():
                st.markdown(f"""
                <div class="job-card">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.4rem">
                    <div>
                      {src_badge}
                      <span style="font-size:1.1rem;font-weight:700;color:#f0f2f6">{job["title"]}</span>
                      <span style="color:#9ca3af;margin-left:10px">·</span>
                      <span style="color:#7eb3ff;margin-left:8px">{job.get("company","")}</span>
                    </div>
                    <span class="{badge_cls}">{fit} Fit</span>
                  </div>
                  <div style="color:#9ca3af;font-size:.85rem;margin:6px 0">📍 {loc}  ·  🗓 {post}</div>
                  <p style="color:#c9cdd4;margin:8px 0 10px">{job.get("description","")}</p>
                  <div style="margin-bottom:8px">{tags_html}</div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("View Requirements & Skill Gaps"):
                    req_col, gap_col = st.columns(2)
                    with req_col:
                        reqs = job.get("requirements", [])
                        if reqs:
                            st.markdown("**Requirements**")
                            for r in reqs:
                                st.markdown(f"- {r}")
                    with gap_col:
                        gaps = job.get("gap_skills", [])
                        if gaps:
                            st.markdown("**Potential Skill Gaps**")
                            for g in gaps:
                                st.markdown(f'<span class="skill-tag-gap">⚠ {g}</span>', unsafe_allow_html=True)
                        else:
                            st.markdown("**No significant gaps identified ✅**")
                    st.markdown(f"[🔗 View Job Posting →]({job['url']})")

                st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# TAB 3 — Skill Gaps
# ────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 🎯 Skills to Consider Adding")
    st.caption("These skills appear frequently in target job postings and would strengthen your profile.")
    for skill, rationale in RECOMMENDED_SKILLS:
        st.markdown(f"""
        <div class="card" style="margin-bottom:.7rem">
          <div style="margin-bottom:6px"><span class="skill-tag-gap">⚠ {skill}</span></div>
          <p style="margin:0;font-size:.9rem;color:#c9cdd4">{rationale}</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.markdown("### ✅ Your Strongest Differentiators")
    for title, desc in [
        ("Eye-Tracking & Psychophysics",    "Rare combination mapping directly to ADAS perception and HMI research at OEMs and Tier-1s."),
        ("Real-World & Simulator Studies",  "Audi and Toyota roles included on-road and tabletop simulator work — a versatile toolkit."),
        ("Published & Patented Research",   "Peer-reviewed papers and a patent significantly strengthen credibility in research-scientist tracks."),
        ("Cross-OEM Brand Experience",      "Audi AG + Porsche AG + TRI is an exceptional mix of OEM and startup research exposure."),
        ("Haptic / Multimodal Interaction", "Haptic feedback research in steering is highly specialized and sought after at Tier-1 suppliers."),
    ]:
        st.markdown(f"""
        <div class="card" style="margin-bottom:.7rem;border-left:4px solid #4ade80">
          <div style="font-weight:600;color:#4ade80;margin-bottom:4px">✓ {title}</div>
          <p style="margin:0;font-size:.9rem;color:#c9cdd4">{desc}</p>
        </div>
        """, unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# TAB 4 — Raw Resume
# ────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### 📄 Extracted Resume Text")
    if resume_text:
        st.text_area("Resume Content", value=resume_text, height=600, label_visibility="collapsed")
    else:
        st.warning("No resume text could be extracted. Please upload a PDF.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<p style='text-align:center;color:#4b5563;font-size:.8rem'>"
    "Automotive Job Search Assistant · Built with Streamlit · Live data via Indeed RSS · Curated by Claude"
    "</p>",
    unsafe_allow_html=True,
)
