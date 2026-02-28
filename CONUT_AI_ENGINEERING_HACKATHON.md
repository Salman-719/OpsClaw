# Conut AI Engineering Hackathon

## 12-Hour Chief of Operations Agent Challenge

### Course
AI Engineering (focus on AI systems, full MLOps pipeline, and business feasibility)

---

## Overview
You are working with real operational data from **Conut**, a growing sweets and beverages business.

Your task is to build an **AI-Driven Chief of Operations Agent** that turns data into business decisions Conut can act on.

This is not a toy assignment. You will design, implement, and present a practical AI system under time pressure.

---

## Business Objectives
Your solution must address all of the following:

1. **Combo Optimization**
Identify optimal product combinations based on customer purchasing patterns.

2. **Demand Forecasting by Branch**
Forecast demand per branch to support inventory and supply chain decisions.

3. **Expansion Feasibility**
Evaluate whether opening a new branch is feasible and recommend candidate locations.

4. **Shift Staffing Estimation**
Estimate required employees per shift using demand and time-related operational data.

5. **Coffee and Milkshake Growth Strategy**
Develop data-driven strategies to increase coffee and milkshake sales.

---

## Mandatory Integration Requirement (OpenClaw)
Your final system **must be integrated with OpenClaw**.

OpenClaw should be able to interact with your model/system to execute operational queries (for example: demand prediction, staffing recommendation, combo suggestions, and sales strategy prompts).

Your grade includes whether this integration works in practice, not only in theory.

---

## Data Package
Use the scaled dataset in:

`Conut bakery Scaled Data `

### Available Files
- `REP_S_00136_SMRY.csv` - Summary by division/menu channel.
- `REP_S_00194_SMRY.csv` - Tax summary by branch.
- `REP_S_00461.csv` - Time and attendance logs.
- `REP_S_00502.csv` - Sales by customer in detail (delivery, line-item style).
- `rep_s_00150.csv` - Customer orders with first/last order timestamps, totals, and order counts.
- `rep_s_00191_SMRY.csv` - Sales by items and groups.
- `rep_s_00334_1_SMRY.csv` - Monthly sales by branch.
- `rep_s_00435_SMRY.csv` - Average sales by menu.
- `rep_s_00435_SMRY (1).csv` - Duplicate report version.

### Important Data Notes
- Numeric values are intentionally transformed to arbitrary units.
- Focus on **patterns, ratios, and relative comparisons**, not absolute values.
- The exports are report-style CSVs with repeated headers/page markers. A robust ingestion and cleaning step is expected.
- Customer and employee names are anonymized in the scaled dataset.

---

## Minimum Technical Requirements
Your submission must include:

1. **End-to-end pipeline**
Data ingestion, cleaning, feature engineering, modeling/analytics, and inference/reporting.

2. **Reproducibility**
Clear run instructions and pinned dependencies.

3. **Operational AI component**
An agent or service layer that can answer business questions from the five objectives.

4. **OpenClaw integration**
Demonstrable interaction between OpenClaw and your system.

---

## Deliverables
1. **Public GitHub repository** with clean structure and documentation.
2. **README.md** explaining:
   - business problem
   - approach and architecture
   - how to run
   - key results and recommendations
3. **Executive brief** (max 2 pages, PDF):
   - problem framing
   - top findings
   - recommended actions
   - expected impact and risks
4. **Demo evidence**:
   - screenshots or short video
   - OpenClaw invoking your solution

Code will be executed for validation, so broken or non-reproducible submissions will be penalized.

---

## Team Format
- Maximum 3 students per team.
- Solo and duo submissions are allowed.

---

## Evaluation Criteria
- **Business impact and insight quality**
- **Technical correctness and ML rigor**
- **System engineering quality (MLOps, reproducibility, maintainability)**
- **OpenClaw integration quality**
- **Clarity of communication and recommendations**

---

## Rules
1. You may use any language, framework, library, and tooling.
2. You may use AI assistants and open-source resources.
3. External data is allowed only if clearly documented and justified.
4. Claims must be backed by evidence from your pipeline outputs.

---

## Submission
- Submit your public GitHub repository link via Moodle.
- Include the executive brief and demo evidence in the repo or linked from it.
- Results will be announced after review and execution checks.

---

## Final Note
Treat this like a real consulting and AI systems engagement. The goal is not just to train a model, but to deliver a reliable decision-support system that Conut could realistically use.

**Professor Ammar Mohanna**  
American University of Beirut
