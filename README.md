# India markets & macro dashboard
- `python build.py` fetches data and writes `docs/index.html` (serve via GitHub Pages from /docs, or Cloudflare Pages).
- Auto: Yahoo Finance + FRED. Manual (RBI, GST, NSDL, AMFI, NSE P/E): add `date,value` rows to `data/manual/<id>.csv` (ids are in build.py).
- Set repo variable `STOCKS_URL` to link the Stocks tab to your NSE dashboard.
- Workflow runs every Monday; or run it manually from the Actions tab.
