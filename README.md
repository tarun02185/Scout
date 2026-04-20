# Scout — Talk to Your Data in Plain English

Scout is a self-service data intelligence platform where anyone — technical or not — can upload files and ask questions in plain English. It returns clear explanations written for non-experts, interactive charts, and transparent source citations. No SQL, no dashboards, no jargon.

**Built for the NatWest Code for Purpose — India Hackathon**

> **Live Demo:** [https://scout-amber.vercel.app](https://scout-amber.vercel.app)
> Click **"Continue as Guest"** to try it instantly — no sign-up required.

---

## Overview

- **What it does:** Users upload any file (CSV, PDF, images, logs, databases) and ask questions in natural language. The system returns structured answers with a headline, explanation, key details, and follow-up suggestions — all in everyday language.
- **What problem it solves:** Many people struggle to get quick, trustworthy answers from data because existing tools require technical expertise. Scout removes that friction completely.
- **Who it's for:** Business analysts, managers, team leads, and anyone who needs data insights without learning SQL or BI tools.

### The Three Pillars

| Clarity | Trust | Speed |
|---|---|---|
| Answers simple enough for non-experts | Source transparency, consistent metric definitions | Streaming responses, instant chart generation |

---

## Features

- **Multi-format file support:** CSV, Excel, PDF, images (PNG/JPG), log files, SQLite databases, JSON, Parquet, and plain text
- **Natural language queries:** Ask "Why did revenue drop?" or "Compare North vs South" — no SQL needed
- **Smart source separation:** Uploads multiple files and correctly identifies which source to query based on the question (won't mix CSV data with PDF content)
- **Cross-document intelligence:** Ask questions spanning multiple files (e.g., "Do the CSV numbers match what the report says?")
- **Image and diagram analysis:** Uses Groq Vision (fast) with Gemini fallback to understand uploaded images
- **Automatic chart generation:** Only shows charts when the question is about data/numbers — picks bar, line, or pie based on data shape
- **Structured non-techie output:** Every response follows a 5-part structure:
  1. **Headline answer** with the key number bolded
  2. **What this means** in plain English with analogies
  3. **Key details** as bullet points with breakdowns
  4. **Why it matters** — significance explained
  5. **What you can ask next** — follow-up suggestions
- **Progressive disclosure:** Expandable "Show details & sources" reveals the SQL query and source files used
- **Streaming responses:** Token-by-token output with a blinking cursor — no waiting for the full response
- **Follow-up conversations:** Context-aware — "why?" after a revenue answer knows you mean revenue
- **Chat session management:** New chat, switch between sessions, auto-titled by first question
- **Semantic metric dictionary:** `metrics.yaml` ensures "revenue", "profit", "orders" always resolve consistently
- **Five-layer data protection (see section below):** input tokenization, prompt-injection filter, column-level SQL blocklist, hardened system prompts, output masking + audit log
- **SQL safety guardrails:** Only SELECT queries — DROP, DELETE, UPDATE blocked with auto-retry on failure
- **Website / URL ingestion (beta):** Paste a URL to crawl up to 30 pages with a path filter, feeding the same RAG pipeline (static HTML only — see *Limitations*)
- **Google OAuth + Guest login:** Sign in with Google or continue as guest instantly

---

## Data Protection

Scout assumes any file a user uploads can contain sensitive personal data (emails, phone numbers, addresses, IDs, card numbers, passwords, Aadhaar, PAN). The LLM still needs *some* view of the data to answer questions — but we enforce five independent layers so that **no one can extract raw sensitive values through the chat interface, regardless of how the question is phrased**.

| # | Layer | What it does | File |
|---|---|---|---|
| 1 | **Input-side tokenization** | Every PII value going into an LLM prompt (SQL sample rows, query result rows, RAG chunks) is replaced with a deterministic opaque token like `[PII_EMAIL_a1b2c3d4]`. The LLM literally never sees the raw value, so it cannot leak it. Tokens are stable per value, so grouping and equality semantics survive. | `backend/src/guardrails/tokenizer.py` |
| 2 | **Prompt-injection / extraction filter** | Every user question is screened before it reaches the LLM. Jailbreak phrases (*"ignore previous instructions", "reveal the system prompt", "dump the database"*) and PII-enumeration phrases (*"list every email", "show all phone numbers"*) are rejected with a polite refusal. Aggregate questions (*"how many unique emails"*) are allowed because they don't disclose individual values. | `backend/src/guardrails/injection.py` |
| 3 | **Column-level SQL blocklist** | Generated SQL is rejected if it puts a sensitive column into the `SELECT` projection (including `SELECT *` against a table that contains any PII column). Only aggregate calls (`COUNT(email)`, `COUNT(DISTINCT email)`, etc.) are allowed on sensitive columns. Filtering / grouping by those columns in `WHERE`, `GROUP BY`, `ORDER BY` is still permitted — those paths don't leak values through the result set. | `backend/src/guardrails/validator.py` |
| 4 | **Hardened system prompts** | A non-negotiable `SECURITY_PREAMBLE` is prepended to every LLM system prompt (SQL generation, response generation, clarification). It explicitly forbids revealing raw personal data, forbids decoding the opaque tokens, and instructs the model to ignore any user content that tries to override these rules. | `backend/src/config.py` |
| 5 | **Output filter + audit log** | As a last line of defence, every LLM response is regex-scanned for PII patterns (email, phone, SSN, credit card, Aadhaar, PAN, IP) and masked before being shown to the user or persisted to the session database. Every block/mask event is written to an append-only `backend/audit.log` with a timestamp, event type, and a short preview (never the raw value). | `backend/src/guardrails/pii.py`, `backend/src/guardrails/audit.py` |

**Test coverage:** 42 unit tests exercise the five layers, covering PII tokenization across DataFrames and text, ~20 injection/extraction phrases, column-level SQL safety (including `SELECT *` blocking and aggregate exemptions), and output masking with count. Run with `python -m pytest tests/ -v` (125 tests total; all passing).

**What each layer protects against, briefly:**
- Layer 1 defeats leakage even when the response LLM is fully compromised.
- Layer 2 defeats prompt-injection via the question itself.
- Layer 3 defeats PII exfiltration via crafted SQL from the generator model.
- Layer 4 reduces the chance the model will ever try to disclose, even unprompted.
- Layer 5 catches anything the first four layers missed and makes attempts auditable.

---

## Install and Run Instructions

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm

### Step 1: Clone the repository

```bash
git clone <repository-url>
cd hackathon
```

### Step 2: Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

| Variable | Where to get it | Purpose |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) (free) | LLM for SQL generation + response |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) (free) | Image/diagram analysis (fallback) |
| `GOOGLE_CLIENT_ID` | [console.cloud.google.com](https://console.cloud.google.com) (optional) | Google OAuth sign-in |

Start the backend:

```bash
uvicorn main:app --reload --port 8000
```

### Step 3: Frontend setup

```bash
cd frontend
npm install
```

Create `frontend/.env` (optional):

```env
VITE_API_URL=
VITE_GOOGLE_CLIENT_ID=your_google_client_id_here
```

Start the frontend:

```bash
npm run dev
```

Open **http://localhost:5173** — click **"Continue as Guest"** to start.

### Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

All 60 tests should pass.

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18 + TypeScript + Tailwind CSS v4 | Chat UI, file upload, session management |
| **Build Tool** | Vite | Fast dev server and production builds |
| **Charts** | Recharts | Auto-generated bar, line, and pie charts |
| **Backend** | FastAPI (Python) | REST API + SSE streaming |
| **Primary LLM** | Groq (Llama 3.3 70B) | Response generation (streaming) |
| **Fast LLM** | Groq (Llama 3.1 8B Instant) | SQL generation (5x faster) |
| **Vision LLM** | Groq Vision (Llama 3.2 90B) → Gemini fallback | Image/diagram understanding |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2) | Local text embeddings for RAG |
| **Vector Database** | ChromaDB | Document chunk storage for semantic search |
| **Structured Database** | DuckDB | In-memory SQL engine for CSV/Excel queries |
| **PDF Processing** | PyMuPDF + pdfplumber | Text, table, and image extraction |
| **Auth** | Google OAuth + Guest login | User authentication |
| **Session Storage** | SQLite | Chat history and session persistence |

---

## Usage Examples

### 1. Understand what changed
Upload `sales.csv`, then ask:
> "Why does the South region have lower revenue?"

**Response:**
> **The South region has a total revenue of $314K**, which is the lowest among all regions. This means the South region is bringing in less money compared to other areas — think of it like a store that's not selling as many products as its neighbors...

### 2. Compare
> "Compare Technology vs Furniture sales"

**Response:**
> **Technology sales are about $15K less than Furniture**, with Technology at $454K and Furniture at $469K. It's a close race — Furniture is slightly ahead...

### 3. Breakdown
> "What makes up total sales? Break it down by category"

**Response:**
> **The top 3 categories make up over 90% of total sales**, with Furniture being the largest at $469K (about 31% of total)...

### 4. Summarize
> "Give me a summary of key metrics"

**Response:**
> **Total revenue is $1.39M** with a profit of $548K. The average order value is $1,445, and the discount rate is around 10%...

### 5. Document queries (no chart)
Upload a PDF alongside your CSV, then ask:
> "What is the theme of the hackathon?"

**Response:** Text-only answer from the PDF — no chart shown, no CSV data mixed in.

---

## Architecture

```
Frontend (React + Tailwind)            Backend (FastAPI + Python)
┌─────────────────────────┐            ┌───────────────────────────────────┐
│  Login (Google/Guest)   │            │  Auth (Google OAuth + Guest)      │
│  Chat UI (streaming)    │   REST +   │                                   │
│  File Upload (multi)    │───SSE────▶ │  Ingestion Engine                 │
│  Recharts (auto)        │            │  ├── CSV/Excel/JSON → DuckDB      │
│  Session Switcher       │◀───────────│  ├── PDF → Text chunks → ChromaDB │
│  Source Panel           │            │  ├── Images → stored (lazy vision) │
│                         │            │  └── Logs → parsed → DuckDB       │
└─────────────────────────┘            │                                   │
                                       │  Query Orchestrator                │
Deployed: Vercel                       │  ├── Intent (rule-based, instant)  │
                                       │  ├── SQL Engine (8B fast model)    │
                                       │  ├── RAG Engine (ChromaDB search)  │
                                       │  ├── Vision (Groq → Gemini)        │
                                       │  └── Response Gen (70B streaming)  │
                                       │                                   │
                                       │  Guardrails                        │
                                       │  ├── SQL Validator + Auto-retry    │
                                       │  ├── PII Masker                    │
                                       │  └── Source Separation             │
                                       │                                   │
                                       │  Semantic Layer (metrics.yaml)     │
                                       └───────────────────────────────────┘
                                       Deployed: Render
```

### Why this architecture?

- **DuckDB** for structured data: zero-config, handles CSV/Excel natively — no database server needed
- **ChromaDB** for unstructured data: lightweight vector store — enables semantic search over PDFs and documents
- **Groq 70B** for responses: high-quality explanations for non-technical users, streamed token-by-token
- **Groq 8B Instant** for SQL: 5x faster than 70B, SQL is a structured task that doesn't need the big model
- **Rule-based intent** instead of LLM: saves ~1.5s per query with zero quality loss — the orchestrator handles misclassification gracefully
- **Source separation**: labels each context block with its filename so the LLM never mixes CSV data with PDF content
- **Semantic layer** (metrics.yaml): ensures "revenue" always means `SUM(quantity * unit_price)` regardless of phrasing

### Latency optimizations

| Optimization | Time Saved | Quality Impact |
|---|---|---|
| Rule-based intent (no LLM call) | ~1.5s | None |
| 8B model for SQL generation | ~1s | None (SQL is structured) |
| Schema caching per session | ~0.3s | None |
| Trimmed context (10 rows, 200 char history) | ~0.5s | Minimal |
| Lazy image analysis (on query, not upload) | Upload instant | None |

---

## Deployment

### Frontend → Vercel (Free)

1. Push repo to GitHub
2. Go to [vercel.com](https://vercel.com) → Import Project
3. Set **Root Directory** to `frontend`
4. Set **Framework Preset** to Vite
5. Add environment variables:
   - `VITE_API_URL` = `https://your-backend.onrender.com`
   - `VITE_GOOGLE_CLIENT_ID` = your Google Client ID (optional)
6. Deploy

### Backend → Render (Free)

1. Go to [render.com](https://render.com) → New Web Service
2. Connect your GitHub repo
3. Set **Root Directory** to `backend`
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables:
   - `GROQ_API_KEY` = your Groq key
   - `GOOGLE_API_KEY` = your Google AI key
   - `GOOGLE_CLIENT_ID` = your OAuth client ID (optional)
7. Select **Free** plan → Deploy

### After deployment

1. Copy the Render URL (e.g., `https://scout-n9yf.onrender.com`)
2. Update the Vercel environment variable `VITE_API_URL` with this URL
3. Redeploy Vercel
4. In Google Cloud Console, add both URLs to Authorized JavaScript Origins for OAuth

### Live Demo

> **Frontend:** [https://scout-amber.vercel.app](https://scout-amber.vercel.app)
> **Backend API:** [https://scout-n9yf.onrender.com](https://scout-n9yf.onrender.com)
> **API Docs:** [https://scout-n9yf.onrender.com/docs](https://scout-n9yf.onrender.com/docs)
>
> Click **"Continue as Guest"** — no sign-up needed.
> Upload any CSV or PDF and ask questions.

*Note: Backend on Render free tier sleeps after 15 min idle. First request after sleep takes ~30s to wake.*

---

## Project Structure

```
hackathon/
├── backend/
│   ├── main.py                       # FastAPI app (REST + SSE streaming)
│   ├── src/
│   │   ├── auth.py                   # Google OAuth + Guest login
│   │   ├── config.py                 # All configuration + LLM prompts
│   │   ├── llm.py                    # Shared LLM helper (Groq → Gemini fallback)
│   │   ├── ingestion/
│   │   │   ├── router.py             # File type detection + routing
│   │   │   ├── csv_loader.py         # CSV/Excel/JSON → DuckDB
│   │   │   ├── pdf_loader.py         # PDF → text chunks + tables + images
│   │   │   ├── image_loader.py       # Images → lazy vision analysis
│   │   │   ├── log_loader.py         # Log files → structured parsing
│   │   │   └── db_loader.py          # SQLite → DuckDB import
│   │   ├── query/
│   │   │   ├── orchestrator.py       # Main query coordinator
│   │   │   ├── intent.py             # Rule-based intent classifier
│   │   │   ├── sql_engine.py         # Text-to-SQL with auto-retry
│   │   │   ├── rag_engine.py         # Vector search over documents
│   │   │   └── vision_engine.py      # Image queries (Groq → Gemini)
│   │   ├── semantic/
│   │   │   ├── metrics.yaml          # Metric definitions dictionary
│   │   │   └── resolver.py           # Metric lookup + context builder
│   │   ├── chat/
│   │   │   ├── session_manager.py    # Session CRUD (SQLite)
│   │   │   └── history.py            # Conversation context management
│   │   ├── visualization/
│   │   │   └── charts.py             # Auto chart type detection
│   │   └── guardrails/
│   │       ├── validator.py          # SQL injection prevention
│   │       └── pii.py                # PII detection + masking
│   ├── tests/                        # 60 unit tests
│   ├── data/sample_superstore.csv    # Demo dataset (960 rows)
│   ├── requirements.txt
│   ├── Procfile                      # For Render deployment
│   └── render.yaml                   # Render blueprint
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                   # Main app layout
│   │   ├── components/
│   │   │   ├── auth/LoginScreen.tsx  # Google + Guest login
│   │   │   ├── chat/
│   │   │   │   ├── ChatBubble.tsx    # User/assistant messages
│   │   │   │   ├── ChatInput.tsx     # Input bar with file attach
│   │   │   │   ├── ChartView.tsx     # Auto bar/line/pie charts
│   │   │   │   ├── SourcesPanel.tsx  # Expandable sources + SQL
│   │   │   │   └── WelcomeScreen.tsx # Upload zone + suggestions
│   │   │   └── layout/Sidebar.tsx    # Files, chats, user menu
│   │   ├── hooks/
│   │   │   ├── useAuth.ts           # Auth state management
│   │   │   └── useChat.ts           # Chat + streaming state
│   │   ├── services/api.ts          # API client + SSE parser
│   │   └── types/index.ts           # TypeScript interfaces
│   ├── index.html
│   ├── vite.config.ts
│   ├── vercel.json
│   └── package.json
│
├── README.md
├── LICENSE (Apache 2.0)
└── .gitignore
```

---

## Limitations

- **File re-upload on session restore:** Switching back to a previous chat requires re-uploading files (structured data is in-memory)
- **Free-tier rate limits:** Groq allows ~30 req/min on free tier — heavy usage may hit throttling
- **Render cold starts:** Free tier sleeps after 15 min idle — first request takes ~30s
- **Large files:** Files over 100MB may be slow to process in-memory
- **Website ingestion — static HTML only:** The URL crawler uses `requests` + `BeautifulSoup`, so sites that render content client-side (most SPAs, Twitter/X, much of the newer Apple product pages, anything behind a login or Cloudflare-style bot challenge) return near-empty pages. A Playwright-based renderer would fix this but adds ~200 MB to the deployment image.
- **robots.txt parsing is best-effort:** Python's stdlib `urllib.robotparser` mis-parses large robots.txt files (notably Wikipedia's) and over-blocks. Robots respect is therefore **disabled by default** (opt in with `SCRAPE_RESPECT_ROBOTS=true`). The other safeguards — same-origin restriction, 30-page cap, 250 ms polite delay, 5 MB size cap, path filter — keep the crawler well-behaved.
- **Vision model churn:** Groq periodically decommissions preview vision models. If image analysis starts returning "unavailable", override `GROQ_VISION_MODEL` in `.env` with a currently-served model name from the Groq console.

## Future Work & Improvements

### Attempted but not fully shipped

- **Agentic / on-query website fetching.** We attempted an approach where, instead of pre-crawling, the LLM would decide at query time which pages from a root URL to fetch and embed. The control-flow was complex, latency per query spiked to 10–20s, and the LLM occasionally picked irrelevant links. We fell back to bounded BFS at upload time; on-query fetch remains a planned improvement.
- **JavaScript-rendered pages.** We explored integrating Playwright for JS-heavy sites (Apple product pages, SPAs). The Render free tier has memory and image-size caps that made a Chromium install impractical in this iteration. Deferred behind a future `SCRAPE_RENDER_JS=true` flag.
- **Per-site adapters** (Wikipedia REST API, GitHub API, arXiv OAI) that skip scraping entirely and fetch clean structured content. Faster and more reliable than BFS, but each adapter is a separate integration.

### Planned improvements

- **Persistent DuckDB + ChromaDB storage** so uploaded files survive session restores (currently in-memory for speed).
- **WebSocket streaming** for lower latency than the current SSE implementation.
- **Live database connections** (PostgreSQL, MySQL, Snowflake) with read-only credentials + query timeouts.
- **Export answers and charts as PDF** reports with embedded citations.
- **Fine-tuned embeddings** for domain-specific data (finance, medical, legal).
- **Multi-user workspaces** with shared datasets, role-based access, and row-level ACLs.
- **Stronger privacy primitives:**
  - Differential privacy on aggregates (add calibrated noise when `COUNT` is below a `k`-anonymity threshold).
  - Per-user encryption keys so uploaded files are re-encrypted client-side.
  - Automatic data-residency routing (EU files stay in EU region).
- **Richer web-crawl feature:**
  - Playwright-based renderer for JS sites behind a feature flag.
  - Sitemap + llms.txt discovery, not just the start URL's outgoing links.
  - Incremental re-crawl so a source stays fresh without a full re-upload.
  - Per-domain rate limits read from `robots.txt` `Crawl-delay` (once we swap to a better robots parser).
- **Better evaluation harness:** a golden-set of (question, expected-answer) pairs so model/prompt changes can be auto-graded before merge.
- **Query cost ceiling:** hard per-user token budget and graceful degradation when exceeded.
- **Better observability:** structured JSON logs, per-query trace IDs, latency histograms, and a developer dashboard reading from the audit log.
