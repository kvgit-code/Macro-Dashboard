"""Builds docs/index.html. Run weekly: python build.py
Auto sources: Yahoo Finance (yfinance), FRED (no key needed).
Still manual (no machine-readable feed found): GST, SIP, capacity utilization: drop a CSV 'date,value' into data/manual/<id>.csv."""
import csv, io, json, os, datetime as dt, urllib.request
from pathlib import Path
ROOT = Path(__file__).parent
YEARS = 10
CUT = (dt.date.today() - dt.timedelta(days=365 * YEARS)).isoformat()

def fred(sid):
    raw = urllib.request.urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=30).read().decode()
    r = csv.reader(io.StringIO(raw)); next(r)
    return [(d, float(v)) for d, v in r if v not in ("", ".") and d >= CUT]

def yahoo(t):
    import yfinance as yf
    h = yf.Ticker(t).history(period=f"{YEARS}y", interval="1wk")["Close"].dropna()
    return [(d.strftime("%Y-%m-%d"), round(float(v), 2)) for d, v in h.items()]

def manual(mid):
    p = ROOT / "data" / "manual" / f"{mid}.csv"
    if not p.exists(): return []
    r = csv.reader(p.open()); next(r, None)
    return [(d, float(v)) for d, v in r if v.strip()]


UA = {"User-Agent": "Mozilla/5.0"}
def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read().decode()

def monthly(pts):
    d = {}
    for t, v in sorted(pts): d[t[:7]] = (t, v)
    return list(d.values())

def readcache(mid):
    p = ROOT / "data" / "cache" / f"{mid}.json"
    return [tuple(x) for x in json.loads(p.read_text())] if p.exists() else []

def cached(mid, fn):
    """Fetch; on success save to data/cache, on failure fall back to last good copy."""
    p = ROOT / "data" / "cache" / f"{mid}.json"
    try:
        pts = fn(); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(pts)); return pts
    except Exception as e:
        print("FAILED", mid, e); return readcache(mid)

def bis_repo():  # BIS central bank policy rates, India (RBI repo rate)
    raw = get("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.IN?format=csv")
    rows = list(csv.DictReader(io.StringIO(raw)))
    return [p for p in monthly([(r["TIME_PERIOD"], float(r["OBS_VALUE"])) for r in rows if r["OBS_VALUE"]]) if p[0] >= CUT]

def fx_reserves(_):  # FRED: India total reserves excl. gold, converted to USD bn
    return [(d, round(v / 1e3 if v < 1e8 else v / 1e9, 1)) for d, v in fred("TRESEGINM052N")]

def nifty_pe(_):  # NSE Indices historical P/E, fetched year by year
    out = []
    for y in range(int(CUT[:4]), dt.date.today().year + 1):
        info = "{'name':'NIFTY 50','startDate':'01-Jan-%d','endDate':'31-Dec-%d','indexName':'NIFTY 50'}" % (y, y)
        raw = get("https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString",
                  json.dumps({"cinfo": info}).encode(), {"Content-Type": "application/json", "Referer": "https://www.niftyindices.com/reports/historical-data"})
        for r in json.loads(json.loads(raw)["d"]):
            out.append((dt.datetime.strptime(r["DATE"], "%d %b %Y").strftime("%Y-%m-%d"), float(r["pe"])))
    return monthly(out)

def fiidii(cat):  # NSE gives only the latest day, so history builds up week by week in data/cache
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    op.addheaders = list(UA.items()) + [("Referer", "https://www.nseindia.com/reports/fii-dii")]
    op.open("https://www.nseindia.com/reports/fii-dii", timeout=30)
    rows = json.loads(op.open("https://www.nseindia.com/api/fiidiiTradeReact", timeout=30).read().decode())
    hist = dict(readcache(cat.lower()))
    for r in rows:
        if r["category"].upper().startswith(cat):
            hist[dt.datetime.strptime(r["date"], "%d-%b-%Y").strftime("%Y-%m-%d")] = float(r["netValue"])
    return sorted(hist.items())

# id, section, title, unit, loader, arg, source, url, update frequency, note
M = [
 ("nifty","Market & valuation","Nifty 50","index pts",yahoo,"^NSEI","NSE via Yahoo Finance","https://www.nseindia.com/","Weekly","Benchmark of 50 large Indian companies. A bull market is a long, broad uptrend; early-stage ones start with low investor participation and lingering scepticism."),
 ("sensex","Market & valuation","Sensex","index pts",yahoo,"^BSESN","BSE via Yahoo Finance","https://www.bseindia.com/","Weekly","BSE's 30-stock index. Moves closely with the Nifty; useful as a cross-check."),
 ("pe","Market & valuation","Nifty P/E","x",nifty_pe,"pe","NSE indices (historical P/E)","https://www.niftyindices.com/reports/historical-data","Monthly","Price divided by earnings per share. Higher means richer valuation. Compare with bond yields: when yields fall, higher P/E bands can be justified."),
 ("sip","Market & valuation","Monthly SIP inflows","₹ crore",manual,"sip","AMFI","https://www.amfiindia.com/research-information/amfi-monthly","Monthly (manual)","SIP = systematic investment plan. Steady domestic inflows show household participation ('commitment') building up."),
 ("repo","Rates & liquidity","RBI repo rate","%",bis_repo,"repo","RBI via BIS policy-rate data","https://www.rbi.org.in/Scripts/BS_ViewMasCirculardetails.aspx","Monthly","Rate at which RBI lends to banks. Lower rates cut borrowing costs and make equities more attractive relative to deposits."),
 ("g10","Rates & liquidity","India 10-year G-Sec yield","%",fred,"INDIRLTLT01STM","FRED (OECD)","https://fred.stlouisfed.org/series/INDIRLTLT01STM","Monthly","Yield on the government's 10-year bond: the risk-free benchmark. Earnings yield (1/PE) minus this gap shows how well equities pay for their risk."),
 ("fed","Rates & liquidity","US Fed funds rate","%",fred,"FEDFUNDS","FRED (Federal Reserve)","https://fred.stlouisfed.org/series/FEDFUNDS","Monthly","US policy rate. Higher US rates pull global money towards the dollar and can trigger FII outflows from India."),
 ("us10","Rates & liquidity","US 10-year yield","%",yahoo,"^TNX","CBOE via Yahoo Finance","https://finance.yahoo.com/quote/%5ETNX","Weekly","Global anchor for borrowing costs. Moves in this yield ripple into emerging-market bonds and currencies."),
 ("cap","Earnings & demand","Capacity utilization","%",manual,"cap","RBI OBICUS survey","https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=22570","Quarterly (manual)","Share of installed industrial capacity in use. Above ~75% firms tend to invest in new plants, lifting capex and earnings."),
 ("gst","Earnings & demand","GST collections","₹ lakh crore",manual,"gst","GST Council / PIB","https://www.gst.gov.in/newsandupdates","Monthly (manual)","Gross goods-and-services-tax revenue: a real-time proxy for economic activity and formalisation."),
 ("it","Sectors","Nifty IT","index pts",yahoo,"^CNXIT","NSE via Yahoo Finance","https://www.niftyindices.com/","Weekly","Large IT exporters earn in dollars, so a weaker rupee helps margins; slowing client tech budgets hurt."),
 ("pharma","Sectors","Nifty Pharma","index pts",yahoo,"^CNXPHARMA","NSE via Yahoo Finance","https://www.niftyindices.com/","Weekly","US FDA compliance and US generic drug pricing are the main swing factors."),
 ("bank","Sectors","Nifty Bank","index pts",yahoo,"^NSEBANK","NSE via Yahoo Finance","https://www.niftyindices.com/","Weekly","Banks' profits depend on credit growth and NPAs (non-performing assets: loans unpaid for 90+ days)."),
 ("metal","Sectors","Nifty Metal","index pts",yahoo,"^CNXMETAL","NSE via Yahoo Finance","https://www.niftyindices.com/","Weekly","Cyclical: follows global commodity prices and China demand."),
 ("auto","Sectors","Nifty Auto","index pts",yahoo,"^CNXAUTO","NSE via Yahoo Finance","https://www.niftyindices.com/","Weekly","Proxy for consumption, rural demand and interest-rate sensitivity (vehicle loans)."),
 ("npa","Sectors","Gross NPA ratio, banks","%",fred,"DDSI02INA156NWDB","World Bank via FRED (RBI report is half-yearly)","https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=22570","Annual","Bad loans as % of total loans. Rising NPAs force provisions that cut bank profits; 'recognition' means admitting them on the books."),
 ("brent","Commodities & currency","Brent crude","USD/bbl",yahoo,"BZ=F","ICE via Yahoo Finance","https://fred.stlouisfed.org/series/DCOILBRENTEU","Weekly","India imports most of its oil, so higher crude widens the current account deficit and weakens the rupee. Supply (shale/fracking, OPEC) caps prices."),
 ("gold","Commodities & currency","Gold","USD/oz",yahoo,"GC=F","COMEX via Yahoo Finance","https://www.gold.org/goldhub/data","Weekly","Gold pays no interest, so it tends to rise when real rates fall and money is plentiful, and as a hedge against currency weakness."),
 ("real","Commodities & currency","US real 10-year yield","%",fred,"DFII10","FRED (US Treasury)","https://fred.stlouisfed.org/series/DFII10","Daily","Yield after inflation (TIPS). Plot it against gold: they usually move in opposite directions."),
 ("inr","Commodities & currency","USD/INR","₹ per $",yahoo,"INR=X","Yahoo Finance","https://www.rbi.org.in/scripts/ReferenceRateArchive.aspx","Weekly","A rising line means a weaker rupee. Governments sometimes tolerate or encourage depreciation to make exports cheaper and ease debt burdens, at the cost of imported inflation."),
 ("dxy","Commodities & currency","US Dollar Index","index",yahoo,"DX-Y.NYB","ICE via Yahoo Finance","https://finance.yahoo.com/quote/DX-Y.NYB","Weekly","Dollar against a basket of major currencies. A strong dollar usually pressures emerging markets and commodities."),
 ("fx","Commodities & currency","India forex reserves","USD bn",fx_reserves,"fx","RBI via FRED (excl. gold)","https://www.rbi.org.in/Scripts/WSSView.aspx","Monthly","Foreign currency RBI holds. A large buffer lets it smooth rupee falls and reassures foreign investors."),
 ("gdp","Macro","India GDP growth","% y/y",fred,"NYGDPMKTPKDZGIND","FRED (World Bank)","https://fred.stlouisfed.org/series/NYGDPMKTPKDZGIND","Annual","Real growth of the economy. Sustained 6-7%+ underpins long-term earnings growth."),
 ("cpi","Macro","India CPI inflation","% y/y",fred,"FPCPITOTLZGIND","FRED (World Bank)","https://fred.stlouisfed.org/series/FPCPITOTLZGIND","Annual","Consumer price inflation. RBI cuts rates only when inflation is comfortably within its target band."),
 ("fii","Flows","FII net equity flows","₹ crore",fiidii,"FII","NSE provisional data (history builds from first run)","https://www.fpi.nsdl.co.in/web/Reports/Latest.aspx","Monthly (manual)","FII = foreign institutional investors. They chase global risk appetite and the dollar, so flows are volatile."),
 ("dii","Flows","DII net equity flows","₹ crore",fiidii,"DII","NSE provisional data (history builds from first run)","https://www.nseindia.com/reports/fii-dii","Monthly (manual)","DII = domestic institutions (mutual funds, insurers). Their steady buying cushions FII selling."),
 ("cn","Global","China GDP growth","% y/y",fred,"NYGDPMKTPKDZGCHN","FRED (World Bank)","https://fred.stlouisfed.org/series/NYGDPMKTPKDZGCHN","Annual","China drives global metals and oil demand. A slowdown hits commodity prices and emerging-market sentiment."),
]

out = []
for mid, sec, title, unit, fn, arg, src, url, freq, note in M:
    if fn is manual: pts = manual(mid)
    else:
        pts = cached(mid, lambda: fn(arg))
        ov = manual(mid)   # optional CSV in data/manual/ overrides or extends fetched values
        if ov: pts = sorted({**dict(pts), **dict(ov)}.items())
    out.append(dict(id=mid, section=sec, title=title, unit=unit, source=src, url=url, freq=freq, note=note,
                    dates=[p[0] for p in pts], values=[p[1] for p in pts]))
html = (ROOT / "template.html").read_text()
html = html.replace("__DATA__", json.dumps(out)).replace("__STOCKS__", os.getenv("STOCKS_URL") or "#")
html = html.replace("__BUILT__", dt.date.today().strftime("%d %b %Y"))
(ROOT / "docs" / "index.html").write_text(html)
print("Built", len(out), "metrics;", sum(1 for o in out if o["values"]), "with data")
