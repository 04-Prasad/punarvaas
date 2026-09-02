<p align="center">
  <strong style="font-size:32px">पु</strong>
</p>

<h1 align="center">PUNARVAAS</h1>
<p align="center">
  <b>P</b>latform for <b>U</b>nified <b>N</b>ational <b>A</b>ssessment of <b>R</b>isk,
  <b>V</b>ulnerability <b>A</b>nd <b>A</b>lternative-<b>S</b>ite Selection
</p>
<p align="center">
  <em>SIH 2026 · Ministry of Home Affairs · NDRF — Disaster Management Division</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/SIH-2026-blue?style=for-the-badge" alt="SIH 2026">
  <img src="https://img.shields.io/badge/Theme-Disaster%20Management-red?style=for-the-badge" alt="Disaster Management">
  <img src="https://img.shields.io/badge/Category-Software-green?style=for-the-badge" alt="Software">
  <img src="https://img.shields.io/badge/Python-3.11+-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-purple?style=for-the-badge" alt="License">
</p>

---

## 🎯 The Problem

> *"A village of 1,200 residents sits below a landslide-prone slope. The government already knows it's vulnerable. What it cannot answer is: how many people actually need to move, where should they go, and how much will it cost?"*

India's hazard, census, and terrain data is scattered across separate maps, reports, spreadsheets, and government departments. **There is no unified intelligent system that converts it into a clear relocation decision.**

PUNARVAAS is that conversion layer. Everything it builds ends in **an action, a number, and a rupee figure**.

---

## 💡 Core Insight

Most systems label an entire village as "high-risk" — implying all 1,200 people must move. **PUNARVAAS goes sub-village.** Using H3 hexagonal grids (~120 m resolution) and dasymetric population disaggregation, it can say:

> *"420 of 600 residents in 2 hamlets face unacceptable risk. Site B holds 300 due to water constraints. Relocate 88 highest-risk households first. Estimated cost: ₹12.4 Cr."*

This precision cuts relocation costs by ~65% and turns shelved proposals into approved action plans.

---

## 🏗️ Architecture — Three Chained Engines

The system is structured as three chained decision engines, where each feeds the next:

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   ENGINE 1      │       │   ENGINE 2      │       │   ENGINE 3      │
│   Risk Engine   │──────▶│   Site Engine   │──────▶│   Plan Engine   │
│                 │       │                 │       │                 │
│ Where is it     │       │ Where can they  │       │ Who should be   │
│ unsafe?         │       │ go?             │       │ relocated first?│
│                 │       │                 │       │                 │
│ Red/Orange/     │       │ Ranked sites +  │       │ Priority +      │
│ Yellow/Green    │       │ carrying        │       │ Budget + BCR    │
│                 │       │ capacity        │       │                 │
└─────────────────┘       └─────────────────┘       └─────────────────┘
```

### Engine 1 — Risk Scoring
Combines 7 hazard layers (landslide, flood, erosion, cloudburst, ground deformation, seismic, GLOF/cyclone) using a **probabilistic union** — not a weighted average — so one catastrophic hazard can never be masked.

Zones are assigned by a **versioned YAML rule engine**, editable by an SDMA with approving authority and version tracking.

| Zone | Meaning | Action |
|------|---------|--------|
| 🔴 Red | Unacceptable risk | Relocation or urgent intervention |
| 🟠 Orange | High risk requiring inspection | Short-term mitigation and monitoring |
| 🟡 Yellow | Moderate risk | Preparedness and building restrictions |
| 🟢 Green | Comparatively safer | Possible relocation candidate site |

### Engine 2 — Safe-Site Discovery
Auto-discovers, ranks, and explains the best relocation options using a **hard exclusion → soft scoring** funnel:
1. Exclude Red & Orange zones
2. Exclude unbuildable terrain (slope > 15%)
3. Exclude forests, protected areas, CRZ
4. Exclude floodplain & erosion corridors
5. Exclude prime irrigated agricultural land
6. Prefer government/revenue land
7. Contiguous patch filtering
8. **AHP-weighted TOPSIS** scoring on 13 suitability criteria

### Engine 3 — Carrying Capacity & Prioritisation
Computes per-resource capacity (water, land, roads, health, education) against **real Indian norms** (JJM, RTE, IPHS), identifies the **binding constraint**, costs the gap in ₹, and maps it to the government scheme that pays.

Ranks habitations into: **Immediate → Short-term → Medium-term → Mitigate**.

---

## ⚙️ Tech Stack

| Layer | Technologies |
|-------|-------------|
| **API** | FastAPI · Uvicorn · Pydantic |
| **Database** | PostgreSQL + PostGIS · SQLAlchemy · GeoAlchemy2 · Alembic |
| **Grid & Geospatial** | H3 · Shapely · GeoPandas · Rasterio · rioxarray · xarray · WhiteboxTools |
| **Data Acquisition** | pystac-client · planetary-computer · odc-stac |
| **Science & ML** | NumPy · Pandas · SciPy · scikit-learn · XGBoost · SHAP · pymcdm · OR-Tools |
| **Rules & Reports** | PyYAML · Jinja2 · WeasyPrint |
| **Orchestration** | Prefect · Redis |
| **Frontend** | HTML/JS (Vite dev server) |
| **Containers** | Docker · Docker Compose · GDAL sidecar |

---

## 📁 Project Structure

```
SIH_2026/
├── api/                    # FastAPI backend
│   ├── main.py             # Application entry point
│   ├── deps.py             # Dependency injection
│   └── routers/            # API route handlers
├── core/                   # Core logic library
│   ├── hazard/             # Hazard layer computation
│   ├── risk/               # Risk scoring engine
│   ├── site/               # Site discovery & suitability
│   ├── capacity/           # Carrying capacity computation
│   ├── plan/               # Prioritisation & phasing
│   ├── grid/               # H3 hexagonal grid utilities
│   ├── harmonise/          # Data harmonisation
│   ├── ingest/             # Data ingestion pipeline
│   ├── provenance/         # Provenance & audit trail
│   ├── rules/              # YAML rule engine
│   ├── store/              # Data store abstraction
│   ├── ml.py               # ML model wrappers (XGBoost + SHAP)
│   ├── terrain.py          # Terrain analysis (slope, HAND, etc.)
│   ├── confidence.py       # Confidence scoring
│   └── config.py           # Configuration management
├── pipelines/              # Data processing pipelines
│   ├── engine1.py          # Risk engine pipeline (~30k LoC)
│   └── engine2.py          # Site discovery pipeline (~22k LoC)
├── web/                    # Frontend application
│   ├── index.html          # Entry point
│   └── src/                # Source files
├── field/                  # Field verification app
│   └── src/                # Mobile/field data collection
├── scripts/                # Utility scripts
│   └── check_data.py       # Data source availability checker
├── data/                   # Data directory (git-ignored)
│   ├── raw/                # Raw downloaded data
│   ├── interim/            # Intermediate processing
│   ├── processed/          # Final processed datasets
│   ├── seed/               # Database seed data
│   └── reports/            # Generated report outputs
├── db/
│   └── migrations/         # Database migration scripts
├── docker/
│   └── api.Dockerfile      # API container definition
├── rules/
│   └── zoning/             # Zoning rule YAML configs
├── reports/                # Report generation
│   ├── build.py            # Report builder
│   ├── charts.py           # Chart generation
│   ├── fmt.py              # Formatting utilities
│   └── templates/          # Jinja2 report templates
├── tools/                  # CLI tools
│   ├── ingest.py           # Data ingestion CLI
│   └── serve.py            # Dev server helpers
├── validation/             # Hindcast validation tests
├── out/                    # Build outputs (git-ignored)
├── docs/                   # Documentation
├── docker-compose.yml      # Full local stack definition
├── requirements.txt        # Python dependencies (pinned)
├── solution.html           # Interactive solution brief
├── plan.md                 # Detailed implementation plan
└── data_availability.md    # Data source availability report
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **Docker** & **Docker Compose** (for PostGIS + GDAL)
- **Node.js 20+** (for the web frontend)

### 1. Clone & Setup

```bash
git clone <repo-url>
cd SIH_2026

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Start the Database & Services

```bash
# Start PostGIS database + API server
docker compose up -d db api

# (Optional) Start the web frontend
docker compose --profile web up -d web

# (Optional) Run GDAL commands
docker compose --profile tools run --rm gdal ogrinfo --version
```

### 3. Run the API Server (without Docker)

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Check Data Source Availability

```bash
# Full check — requires internet access
python3 scripts/check_data.py

# Quick portal reachability sweep
python3 scripts/check_data.py --portals-only

# Check specific districts
python3 scripts/check_data.py -d chamoli -d kendrapara
```

### 5. Run Tests

```bash
pytest
```

---

## 🐳 Docker Services

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| `db` | `pv_db` | `5433` | PostGIS 16 database |
| `api` | `pv_api` | `8000` | FastAPI backend (hot-reload) |
| `gdal` | `pv_gdal` | — | GDAL/OGR sidecar (on-demand) |
| `web` | `pv_web` | `5173` | Vite frontend dev server |

---

## 🔬 Validation Strategy

PUNARVAAS uses **hindcast validation** — feeding the system only pre-event data and checking if it would have flagged the hazard before the disaster actually occurred:

- **Wayanad 2024** — Landslide
- **Joshimath 2023** — Ground subsidence
- **Coastal erosion in Odisha** — Riverbank/coastal erosion
- **Historical flood events** — Flood inundation

---

## 🛡️ Design Principles

1. **Decision, not data** — Every output is an action, a number, and a rupee figure
2. **Glass box, not black box** — AI is used in 8 named slots only; zoning thresholds are rule-based, expert-controlled, and versioned
3. **Fully explainable** — Click any Red Zone to see which hazard, which datasets, what factors, who approved, and when it was last updated
4. **Honest estimates** — Disaggregated population figures carry confidence scores; field surveys replace estimates as a first-class feature
5. **Chained engines** — A village is only "Immediate relocation" if a viable destination exists with enough capacity

---

## 📊 Key Data Sources

| Source | Usage |
|--------|-------|
| Microsoft Planetary Computer | Sentinel-1, Sentinel-2, NASADEM, Copernicus DEM 30m, ESA WorldCover |
| GSI Bhukosh | Geological & landslide inventory maps |
| NRSC Bhuvan | Indian satellite imagery & base maps |
| IMD Pune | Gridded rainfall data for cloudburst analysis |
| Census India | Population data for dasymetric disaggregation |
| OSM Overpass | Building footprints for population distribution |
| India-WRIS | Water resource information |
| FSI | Forest cover data |

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Python: **Ruff** for linting and formatting
- Follow existing code conventions in `core/`

---

## 📄 License

This project is developed as part of **Smart India Hackathon 2026**.

---

<p align="center">
  <em>पुनर्वास — because rehabilitation is not a map; it's a decision.</em>
</p>
