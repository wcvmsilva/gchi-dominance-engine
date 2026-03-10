# GCHI Dominance Engine v8.4

**JobTread CSV Validator & Compliance Engine**
GC Home Improvement LLC | Charleston, SC

---

## Overview

The GCHI Dominance Engine is an internal tool that validates project estimate CSVs against the official GCHI v8.4 rules before importing them into JobTread. It ensures 100% compliance with:

- **199 Cost Codes** — Official GCHI cost code library
- **7 Cost Types** — Labor, Materials, Subcontractor, Equipment/Rental, Permits/Fees, Allowance, Other
- **19 Units** — All approved measurement units

## Features

- Upload CSV proposals for instant validation
- Auto-detection and correction of common CSV formatting issues
- Visual dashboard with compliance metrics and error charts
- Detailed error table with row-level issue descriptions
- Download validated "JobTread-Ready" CSV files
- Sample template download for quick start

## Tech Stack

- **Python 3.11+**
- **Streamlit** — Web interface
- **Pandas** — Data processing
- **Plotly** — Interactive charts

## Local Development

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

This app is deployed on [Streamlit Cloud](https://share.streamlit.io).

---

*Confidential — GC Home Improvement LLC*
