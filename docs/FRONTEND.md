# Frontend Dashboard

> React 19 + TypeScript + Vite + Tailwind CSS dashboard with AI chat panel, interactive charts, and data upload capabilities.

---

## Overview

The frontend (`frontend/`) is a single-page application (SPA) that provides:

1. **Executive Dashboard** — Cross-feature overview with KPI cards
2. **Feature Pages** — Dedicated views for each of the 5 analytics features
3. **Chat Panel** — Persistent AI chat sidebar powered by the agent
4. **Upload Page** — Upload new CSV data and trigger the processing pipeline

## File Structure

```
frontend/
├── package.json              # Dependencies and scripts
├── tsconfig.json             # TypeScript configuration
├── vite.config.ts            # Vite bundler configuration
├── tailwind.config.js        # Tailwind CSS configuration
├── postcss.config.js         # PostCSS configuration
├── index.html                # HTML entry point
└── src/
    ├── main.tsx              # React entry point
    ├── App.tsx               # Router + layout (sidebar + content)
    ├── api.ts                # API client (fetch wrapper)
    ├── index.css             # Global styles (Tailwind imports)
    ├── vite-env.d.ts         # Vite environment types
    ├── components/
    │   ├── Card.tsx          # Reusable card wrapper
    │   ├── ChatPanel.tsx     # AI chat sidebar
    │   ├── KpiCard.tsx       # KPI display card with icon
    │   ├── Sidebar.tsx       # Navigation sidebar
    │   └── Spinner.tsx       # Loading spinner
    ├── pages/
    │   ├── Dashboard.tsx     # Executive overview (all features)
    │   ├── ForecastPage.tsx  # Demand forecast view
    │   ├── ComboPage.tsx     # Product combos view
    │   ├── ExpansionPage.tsx # Expansion feasibility view
    │   ├── StaffingPage.tsx  # Shift staffing view
    │   ├── GrowthPage.tsx    # Growth strategy view
    │   └── UploadPage.tsx    # Data upload + pipeline trigger
    ├── hooks/                # Custom React hooks
    └── utils/                # Utility functions
```

---

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **React** | 19.0 | UI framework |
| **TypeScript** | 5.7 | Type safety |
| **Vite** | 6.0 | Build tool and dev server |
| **Tailwind CSS** | 3.4 | Utility-first CSS |
| **Recharts** | 2.15 | Chart library |
| **react-markdown** | 9.0 | Markdown rendering for chat responses |

## Pages

### Dashboard (`/`)
- Executive overview with KPI cards from all 5 features
- Quick metrics: top forecast, best combos, expansion ranking, staffing status, growth potential
- Uses `GET /api/dashboard/overview`

### Forecast (`/forecast`)
- Branch-by-branch demand predictions
- Charts showing predicted orders across scenarios and horizons
- Uses `GET /api/dashboard/forecast`

### Combos (`/combo`)
- Top product pairs ranked by association strength (lift)
- Support, confidence, and lift values displayed
- Uses `GET /api/dashboard/combo`

### Expansion (`/expansion`)
- Candidate branch feasibility scores and rankings
- KPI breakdown per branch
- Expansion recommendation display
- Uses `GET /api/dashboard/expansion`

### Staffing (`/staffing`)
- Hourly staffing gap visualization
- Top understaffed slots highlighted
- Branch-level findings and summaries
- Uses `GET /api/dashboard/staffing`

### Growth (`/growth`)
- Beverage attachment rates by branch
- Growth potential rankings
- Food→beverage bundle rules
- Uses `GET /api/dashboard/growth`

### Upload (`/upload`)
Four-step upload workflow:
1. **Prepare** — Archives old data and clears DynamoDB
2. **Select Files** — Choose CSV files to upload
3. **Upload** — Files uploaded to S3 via presigned URLs
4. **Trigger Pipeline** — Starts Step Functions processing

---

## API Client (`api.ts`)

```typescript
const BASE = import.meta.env.VITE_API_URL ?? '';
```

- **Production:** `VITE_API_URL` is empty → requests go to the same origin (CloudFront)
- **Local dev:** Set `VITE_API_URL=http://localhost:8000` for direct agent access
- CloudFront proxies `/api/*` requests to the ALB → EC2 agent

### API Functions

| Function | Endpoint | Description |
|----------|----------|-------------|
| `chat(message)` | `POST /api/chat` | Send message to AI agent |
| `getDashboardOverview()` | `GET /api/dashboard/overview` | Executive overview |
| `getDashboardForecast()` | `GET /api/dashboard/forecast` | All forecasts |
| `getDashboardCombo()` | `GET /api/dashboard/combo` | All combos |
| `getDashboardExpansion()` | `GET /api/dashboard/expansion` | Expansion data |
| `getDashboardStaffing()` | `GET /api/dashboard/staffing` | Staffing data |
| `getDashboardGrowth()` | `GET /api/dashboard/growth` | Growth data |
| `prepareUpload()` | `POST /api/upload/prepare` | Archive + clear |
| `presignUpload(filename)` | `POST /api/upload/presign` | Get upload URL |
| `triggerPipeline()` | `POST /api/upload/trigger` | Start pipeline |
| `getPipelineStatus(arn)` | `POST /api/upload/status` | Check status |

---

## Components

### ChatPanel
- Persistent sidebar chat interface
- Sends messages to `POST /api/chat`
- Renders markdown responses via `react-markdown`
- Shows tool call traces (which tools the agent called)

### Sidebar
- Navigation between all pages
- Active page highlighting
- Responsive design

### KpiCard
- Displays a single KPI with icon, label, and value
- Color-coded by status or feature

### Card
- Reusable wrapper component for content sections
- Consistent styling across all pages

### Spinner
- Loading state indicator

---

## Development

### Install Dependencies

```bash
cd frontend
npm install
```

### Run Dev Server

```bash
npm run dev
```

Starts at `http://localhost:5173` with hot module replacement.

### Build for Production

```bash
npm run build
```

Outputs to `frontend/dist/` — static files ready for S3 deployment.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `''` (empty) | API base URL. Empty = same origin (CloudFront proxy) |

---

## CloudFront Integration

In production, the frontend is served from S3 via CloudFront CDN:

- **Static assets** → S3 origin (cache-optimized)
- **`/api/*` requests** → ALB origin (no caching, all methods allowed)
- **SPA fallback** → 404/403 → `/index.html` with 200 status

This means the frontend and API share the same domain (CloudFront), avoiding CORS issues entirely.
