# Scraper Agent

Point it in a general direction, ask a question, get a spreadsheet.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...

python -m scraper_agent \
  "trade publications and industry associations in the plastics industry" \
  "list trade shows near me this year that customer XYZ is confirmed or likely to attend" \
  --location "Cleveland, OH" --out shows.xlsx

python -m scraper_agent \
  "bulk spice wholesalers" \
  "bulk pricing for every product line, per-unit normalised" --out spices.xlsx
```

## How it works
Claude runs a research loop (`scraper_agent/agent.py`) with:
- **web_search / web_fetch** (Anthropic server tools) to find and read sources
- **fetch_page** – own fetcher for tables/listings; honours robots.txt, 2 s per-domain delay
- **define_columns / record_rows** – the agent designs the schema for your question and streams rows out
- **finish** – summary of coverage and gaps (goes on the `Notes` sheet)

Every row carries `confidence` (confirmed/likely/unverified), `evidence` and `source_url`,
so you can audit "likely" claims. Output is `.xlsx` (default, `output/`) or `.csv`.

Options: `--effort low|medium|high|xhigh|max`, `--max-turns`, `-q`.
Tests: `pytest`.

## Limits
Won't log in, bypass paywalls or bot protection; blocked sites are reported in the Notes.
JS-only pages may come back empty from `fetch_page` (a Playwright fallback is the natural next step).
