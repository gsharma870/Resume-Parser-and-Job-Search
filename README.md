# Automotive Job Search Assistant

A personal Streamlit app that reads your resume, searches the web for relevant job openings, scores each role against your skills, and surfaces skill gaps — all in one place.

Built for HMI / UX Research roles in the automotive and autonomous-driving space, but the scoring and tagging logic adapts to any resume you upload.

---

## Features

- **Resume-driven search** — upload any PDF resume; the app extracts your skills and builds tailored Indeed search queries automatically
- **Live job fetching** — pulls fresh listings from Indeed RSS across multiple targeted queries (HMI Researcher, UX Researcher ADAS, Human Factors, etc.)
- **Dynamic fit scoring** — every job is scored High / Medium / Low by comparing job description keywords against your resume, not a static label
- **Auto-tagging** — jobs are tagged by domain (ADAS, Autonomous Driving, HMI, Eye-Tracking, EV, etc.) from their description text
- **Skill gap detection** — flags skills that appear in a job posting but are missing from your resume (Figma, SQL, ISO 26262, Bayesian modeling, etc.)
- **24-hour cache** — results are cached locally so the app loads instantly; one click refreshes with fresh data
- **Curated baseline** — 12 hand-researched roles at top companies (Waymo, BMW, Ford, TRI, Mobileye, etc.) always available as a fallback
- **Sidebar filters** — filter by fit level (High / Medium / Low), source (Live vs. Curated), and domain tag

---

## Screenshots

| Resume Analysis | Job Matches |
|---|---|
| Skills detected from PDF, experience timeline, recommended role types | Live + curated listings with fit badge, tags, requirements, and skill gaps |

---

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Install dependencies

```bash
pip install streamlit pdfplumber
```

### Run the app

```bash
streamlit run job_search_app.py
```

The app opens at `http://localhost:8501`.

### Default resume

Place your resume as `GSharma_Resume.pdf` in the same folder as `job_search_app.py`. The app loads it automatically on startup. You can also upload a different PDF at any time via the sidebar.

---

## How It Works

```
Resume PDF
    │
    ▼
extract_pdf_text()        ← pdfplumber
    │
    ▼
build_search_queries()    ← keyword extraction from resume text
    │                        (eye-tracking, psychophysics, ADAS, etc. auto-boost queries)
    ▼
fetch_indeed_rss()        ← Indeed RSS feed, one request per query
    │                        (stdlib urllib + xml.etree — no extra dependencies)
    ▼
enrich()
  ├── score_fit()         ← keyword overlap: job description ∩ resume text
  ├── auto_tag()          ← domain tags from description (ADAS, HMI, EV, ...)
  └── detect_gaps()       ← skills in job but absent from resume
    │
    ▼
Merge with curated list   ← deduplicate by company name
    │
    ▼
jobs_cache.json           ← 24-hour TTL; invalidated on resume change or manual refresh
    │
    ▼
Streamlit UI
```

### Refresh triggers

| Event | What happens |
|---|---|
| App loads, cache is fresh (< 24 h) | Loads from `jobs_cache.json` instantly |
| App loads, no cache | Scores curated baseline against resume |
| New resume uploaded | MD5 hash change detected → re-searches + re-scores |
| **🔄 Refresh** button clicked | Forces fresh Indeed fetch + re-scores everything |

---

## Project Structure

```
job-search/
├── job_search_app.py     # Main Streamlit app
├── GSharma_Resume.pdf    # Default resume (replace with your own)
├── jobs_cache.json       # Auto-generated cache (gitignored)
├── .claude/
│   └── launch.json       # Claude Code launch config
└── README.md
```

---

## Customization

### Swap in your own resume

Replace `GSharma_Resume.pdf` with your own PDF, or upload via the sidebar. The skill extraction, search queries, fit scores, and gap analysis all update automatically.

### Change the curated company list

Edit the `CURATED_JOBS` list in `job_search_app.py`. Each entry is a plain Python dict — add or remove companies as you like.

### Tune the fit scoring

Adjust `FIT_KEYWORDS_HIGH` and `FIT_KEYWORDS_MED` near the top of the enrichment section to match your target domain. The thresholds (`hi >= 2`, `med >= 4`) can also be tuned in `score_fit()`.

### Change the search queries

Edit `build_search_queries()` to add or remove Indeed search terms. Queries are sent in parallel and deduplicated before scoring.

---

## Caveats

- **Indeed RSS availability** — Indeed's RSS feeds are publicly accessible but may be rate-limited or blocked in some network environments (e.g., corporate proxies). The app gracefully falls back to the curated list if RSS is unreachable.
- **No official job board API** — this app uses publicly available RSS feeds, not a paid API. Job descriptions from RSS are brief snippets, not full postings; follow the link for complete details.
- **Cache staleness** — the cache TTL is 24 hours by default (`CACHE_TTL_HRS = 24` in the code). Click **🔄 Refresh** at any time to force a fresh search.

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI |
| `pdfplumber` | PDF text extraction |
| `urllib` (stdlib) | Indeed RSS HTTP requests |
| `xml.etree.ElementTree` (stdlib) | RSS XML parsing |
| `hashlib`, `json`, `re` (stdlib) | Caching, data handling |

No external API keys required.

---

## License

MIT — do whatever you want with it.
