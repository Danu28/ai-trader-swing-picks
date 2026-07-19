import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'market_data.db')

STOCKS = [
    ("RELIANCE.NS", "Reliance Industries", "Energy", "nifty50"),
    ("TCS.NS", "Tata Consultancy Services", "Information Technology", "nifty50"),
    ("HDFCBANK.NS", "HDFC Bank", "Financial Services", "nifty50"),
    ("INFY.NS", "Infosys", "Information Technology", "nifty50"),
    ("ICICIBANK.NS", "ICICI Bank", "Financial Services", "nifty50"),
    ("HINDUNILVR.NS", "Hindustan Unilever", "Fast Moving Consumer Goods", "nifty50"),
    ("BHARTIARTL.NS", "Bharti Airtel", "Telecom", "nifty50"),
    ("ITC.NS", "ITC Limited", "Fast Moving Consumer Goods", "nifty50"),
    ("KOTAKBANK.NS", "Kotak Mahindra Bank", "Financial Services", "nifty50"),
    ("LT.NS", "Larsen & Toubro", "Construction", "nifty50"),
    ("SBIN.NS", "State Bank of India", "Financial Services", "nifty50"),
    ("BAJFINANCE.NS", "Bajaj Finance", "Financial Services", "nifty50"),
    ("AXISBANK.NS", "Axis Bank", "Financial Services", "nifty50"),
    ("NTPC.NS", "NTPC Limited", "Power", "nifty50"),
    ("MARUTI.NS", "Maruti Suzuki", "Automobile", "nifty50"),
    ("TITAN.NS", "Titan Company", "Consumer Goods", "nifty50"),
    ("SUNPHARMA.NS", "Sun Pharmaceutical", "Healthcare", "nifty50"),
    ("ASIANPAINT.NS", "Asian Paints", "Consumer Goods", "nifty50"),
    ("ULTRACEMCO.NS", "UltraTech Cement", "Construction Materials", "nifty50"),
    ("HCLTECH.NS", "HCL Technologies", "Information Technology", "nifty50"),
    ("ONGC.NS", "Oil & Natural Gas Corp", "Oil & Gas", "nifty50"),
    ("ADANIENT.NS", "Adani Enterprises", "Metals & Mining", "nifty50"),
    ("ADANIPORTS.NS", "Adani Ports & SEZ", "Transport", "nifty50"),
    ("POWERGRID.NS", "Power Grid Corporation", "Power", "nifty50"),
    ("COALINDIA.NS", "Coal India", "Metals & Mining", "nifty50"),
    ("WIPRO.NS", "Wipro", "Information Technology", "nifty50"),
    ("BAJAJ-AUTO.NS", "Bajaj Auto", "Automobile", "nifty50"),
    ("NESTLEIND.NS", "Nestle India", "Fast Moving Consumer Goods", "nifty50"),
    ("JSWSTEEL.NS", "JSW Steel", "Metals & Mining", "nifty50"),
    ("TATASTEEL.NS", "Tata Steel", "Metals & Mining", "nifty50"),
    ("TECHM.NS", "Tech Mahindra", "Information Technology", "nifty50"),
    ("HINDALCO.NS", "Hindalco Industries", "Metals & Mining", "nifty50"),
    ("DRREDDY.NS", "Dr Reddys Laboratories", "Healthcare", "nifty50"),
    ("M&M.NS", "Mahindra & Mahindra", "Automobile", "nifty50"),
    ("GRASIM.NS", "Grasim Industries", "Construction Materials", "nifty50"),
    ("TRENT.NS", "Trent", "Retail", "nifty50"),
    ("BEL.NS", "Bharat Electronics", "Aerospace & Defense", "nifty50"),
    ("BRITANNIA.NS", "Britannia Industries", "Fast Moving Consumer Goods", "nifty50"),
    ("CIPLA.NS", "Cipla", "Healthcare", "nifty50"),
    ("EICHERMOT.NS", "Eicher Motors", "Automobile", "nifty50"),
    ("INDUSINDBK.NS", "IndusInd Bank", "Financial Services", "nifty50"),
    ("APOLLOHOSP.NS", "Apollo Hospitals", "Healthcare Services", "nifty50"),
    ("BPCL.NS", "Bharat Petroleum", "Oil & Gas", "nifty50"),
    ("HDFCLIFE.NS", "HDFC Life Insurance", "Insurance", "nifty50"),
    ("HEROMOTOCO.NS", "Hero MotoCorp", "Automobile", "nifty50"),
    ("SBILIFE.NS", "SBI Life Insurance", "Insurance", "nifty50"),
    ("DIVISLAB.NS", "Divi's Laboratories", "Healthcare", "nifty50"),
    ("HINDPETRO.NS", "Hindustan Petroleum", "Oil & Gas", "nifty50"),
    ("ABBOTINDIA.NS", "Abbott India", "Healthcare", "nifty50"),
    ("ABCAPITAL.NS", "Aditya Birla Capital", "Financial Services", "niftymidcap150"),
    ("ABFRL.NS", "Aditya Birla Fashion", "Retail", "niftymidcap150"),
    ("ACC.NS", "ACC Limited", "Construction Materials", "niftymidcap150"),
    ("AIAENG.NS", "AIA Engineering", "Capital Goods", "niftymidcap150"),
    ("AJANTPHARM.NS", "Ajanta Pharma", "Healthcare", "niftymidcap150"),
    ("ALKEM.NS", "Alkem Laboratories", "Healthcare", "niftymidcap150"),
    ("APARINDS.NS", "Apar Industries", "Capital Goods", "niftymidcap150"),
    ("APLAPOLLO.NS", "APL Apollo Tubes", "Metals & Mining", "niftymidcap150"),
    ("APOLLOTYRE.NS", "Apollo Tyres", "Automobiles", "niftymidcap150"),
    ("ASHOKLEY.NS", "Ashok Leyland", "Automobiles", "niftymidcap150"),
    ("ASTRAL.NS", "Astral Limited", "Capital Goods", "niftymidcap150"),
    ("ATGL.NS", "Adani Total Gas", "Oil & Gas", "niftymidcap150"),
    ("AUBANK.NS", "AU Small Finance Bank", "Banks", "niftymidcap150"),
    ("AUROPHARMA.NS", "Aurobindo Pharma", "Healthcare", "niftymidcap150"),
    ("AWL.NS", "Adani Wilmar", "Consumer Goods", "niftymidcap150"),
    ("BAJAJFINSV.NS", "Bajaj Finserv", "Financial Services", "nifty50"),
    ("BALKRISIND.NS", "Balkrishna Industries", "Automobiles", "niftymidcap150"),
    ("BANDHANBNK.NS", "Bandhan Bank", "Banks", "niftymidcap150"),
    ("BANKINDIA.NS", "Bank of India", "Banks", "niftymidcap150"),
    ("BDL.NS", "Bharat Dynamics", "Aerospace & Defense", "niftymidcap150"),
    ("BERGEPAINT.NS", "Berger Paints", "Consumer Goods", "niftymidcap150"),
    ("BHARATFORG.NS", "Bharat Forge", "Automobiles", "niftymidcap150"),
    ("BHARTIHEXA.NS", "Bharti Hexacom", "Telecom", "niftymidcap150"),
    ("BHEL.NS", "Bharat Heavy Electricals", "Capital Goods", "niftymidcap150"),
    ("BIOCON.NS", "Biocon", "Healthcare", "niftymidcap150"),
    ("BLUESTARCO.NS", "Blue Star", "Consumer Goods", "niftymidcap150"),
    ("COCHINSHIP.NS", "Cochin Shipyard", "Industrial Products", "niftymidcap150"),
    ("COFORGE.NS", "Coforge", "Information Technology", "niftymidcap150"),
    ("COLPAL.NS", "Colgate-Palmolive", "Fast Moving Consumer Goods", "niftymidcap150"),
    ("CONCOR.NS", "Container Corp of India", "Logistics & Cargo", "niftymidcap150"),
    ("COROMANDEL.NS", "Coromandel International", "Chemicals", "niftymidcap150"),
    ("CRISIL.NS", "CRISIL", "Capital Markets", "niftymidcap150"),
    ("CUMMINSIND.NS", "Cummins India", "Capital Goods", "niftymidcap150"),
    ("DALBHARAT.NS", "Dalmia Bharat", "Construction Materials", "niftymidcap150"),
    ("DEEPAKNTR.NS", "Deepak Nitrite", "Chemicals", "niftymidcap150"),
    ("DIXON.NS", "Dixon Technologies", "Consumer Goods", "niftymidcap150"),
    ("EMAMILTD.NS", "Emami", "Consumer Goods", "niftymidcap150"),
    ("ENDURANCE.NS", "Endurance Technologies", "Automobiles", "niftymidcap150"),
    ("ESCORTS.NS", "Escorts", "Automobiles", "niftymidcap150"),
    ("EXIDEIND.NS", "Exide Industries", "Automobiles", "niftymidcap150"),
    ("FEDERALBNK.NS", "The Federal Bank", "Banks", "niftymidcap150"),
    ("FLUOROCHEM.NS", "Gujarat Fluorochemicals", "Chemicals", "niftymidcap150"),
    ("FORTIS.NS", "Fortis Healthcare", "Healthcare Services", "niftymidcap150"),
    ("GICRE.NS", "General Insurance Corp", "Insurance", "niftymidcap150"),
    ("GLAND.NS", "Gland Pharma", "Healthcare", "niftymidcap150"),
    ("GLAXO.NS", "GlaxoSmithKline Pharma", "Healthcare", "niftymidcap150"),
    ("GLENMARK.NS", "Glenmark Pharmaceuticals", "Healthcare", "niftymidcap150"),
    ("GMRAIRPORT.NS", "GMR Airports", "Construction", "niftymidcap150"),
    ("GODREJIND.NS", "Godrej Industries", "Diversified", "niftymidcap150"),
    ("GODREJPROP.NS", "Godrej Properties", "Realty", "niftymidcap150"),
    ("GUJENERGY.NS", "Gujarat Energy", "Power", "niftymidcap150"),
    ("GUJGASLTD.NS", "Gujarat Gas", "Oil & Gas", "niftymidcap150"),
    ("GVT&D.NS", "GVT&D", "Power", "niftymidcap150"),
    ("HDFCAMC.NS", "HDFC Asset Management", "Capital Markets", "niftymidcap150"),
    ("HINDZINC.NS", "Hindustan Zinc", "Metals & Mining", "niftymidcap150"),
    ("HONAUT.NS", "Honeywell Automation", "Capital Goods", "niftymidcap150"),
    ("HUDCO.NS", "HUDCO", "Financial Services", "niftymidcap150"),
    ("IDEA.NS", "Vodafone Idea", "Telecom", "niftymidcap150"),
    ("IDFCFIRSTB.NS", "IDFC First Bank", "Banks", "niftymidcap150"),
    ("IGL.NS", "Indraprastha Gas", "Oil & Gas", "niftymidcap150"),
    ("INDIANB.NS", "Indian Bank", "Banks", "niftymidcap150"),
    ("INDUSTOWER.NS", "Indus Towers", "Telecom", "niftymidcap150"),
    ("IPCALAB.NS", "Ipca Laboratories", "Healthcare", "niftymidcap150"),
    ("IRB.NS", "IRB Infrastructure", "Construction", "niftymidcap150"),
    ("IRCTC.NS", "IRCTC", "Leisure Services", "niftymidcap150"),
    ("IREDA.NS", "IREDA", "Financial Services", "niftymidcap150"),
    ("JKCEMENT.NS", "JK Cement", "Construction Materials", "niftymidcap150"),
    ("JSL.NS", "Jindal Stainless", "Metals & Mining", "niftymidcap150"),
    ("JSWINFRA.NS", "JSW Infrastructure", "Construction", "niftymidcap150"),
    ("JUBLFOOD.NS", "Jubilant FoodWorks", "Leisure Services", "niftymidcap150"),
    ("KALYANKJIL.NS", "Kalyan Jewellers", "Consumer Goods", "niftymidcap150"),
    ("KEI.NS", "KEI Industries", "Capital Goods", "niftymidcap150"),
    ("KPITTECH.NS", "KPIT Technologies", "Information Technology", "niftymidcap150"),
    ("KPRMILL.NS", "KPR Mill", "Textiles", "niftymidcap150"),
    ("LICHSGFIN.NS", "LIC Housing Finance", "Financial Services", "niftymidcap150"),
    ("LINDEINDIA.NS", "Linde India", "Chemicals", "niftymidcap150"),
    ("LLOYDSME.NS", "Lloyds Metals & Energy", "Metals & Mining", "niftymidcap150"),
    ("LTF.NS", "L&T Finance", "Financial Services", "niftymidcap150"),
    ("LTTS.NS", "L&T Technology Services", "Information Technology", "niftymidcap150"),
    ("LUPIN.NS", "Lupin", "Healthcare", "niftymidcap150"),
    ("M&MFIN.NS", "Mahindra & Mahindra Financial", "Financial Services", "niftymidcap150"),
    ("MAHABANK.NS", "Bank of Maharashtra", "Banks", "niftymidcap150"),
    ("MANKIND.NS", "Mankind Pharma", "Healthcare", "niftymidcap150"),
    ("MARICO.NS", "Marico", "FMCG", "niftymidcap150"),
    ("MAXHEALTH.NS", "Max Healthcare", "Healthcare Services", "niftymidcap150"),
    ("MAZDOCK.NS", "Mazagon Dock Shipbuilders", "Industrial Products", "niftymidcap150"),
    ("MEDANTA.NS", "Medanta", "Healthcare Services", "niftymidcap150"),
    ("MFSL.NS", "Max Financial Services", "Insurance", "niftymidcap150"),
    ("MOTILALOFS.NS", "Motilal Oswal Financial", "Capital Markets", "niftymidcap150"),
    ("MPHASIS.NS", "Mphasis", "Information Technology", "niftymidcap150"),
    ("MRF.NS", "MRF", "Automobiles", "niftymidcap150"),
    ("MRPL.NS", "Mangalore Refinery & Petro", "Petroleum Products", "niftymidcap150"),
    ("MSUMI.NS", "Motherson Sumi Wiring", "Automobiles", "niftymidcap150"),
    ("MUTHOOTFIN.NS", "Muthoot Finance", "Financial Services", "niftymidcap150"),
    ("NAM-INDIA.NS", "Nippon India AMC", "Capital Markets", "niftymidcap150"),
    ("NATIONALUM.NS", "National Aluminium", "Metals & Mining", "niftymidcap150"),
    ("NHPC.NS", "NHPC Limited", "Power", "niftymidcap150"),
    ("NIACL.NS", "New India Assurance", "Insurance", "niftymidcap150"),
    ("NLCINDIA.NS", "NLC India", "Power", "niftymidcap150"),
    ("NMDC.NS", "NMDC Limited", "Metals & Mining", "niftymidcap150"),
    ("NTPCGREEN.NS", "NTPC Green Energy", "Power", "niftymidcap150"),
    ("NYKAA.NS", "Nykaa", "Retail", "niftymidcap150"),
    ("OBEROIRLTY.NS", "Oberoi Realty", "Realty", "niftymidcap150"),
    ("OFSS.NS", "Oracle Financial Services", "Information Technology", "niftymidcap150"),
    ("OIL.NS", "Oil India", "Oil & Gas", "niftymidcap150"),
    ("OLAELEC.NS", "Ola Electric", "Automobiles", "niftymidcap150"),
    ("PAGEIND.NS", "Page Industries", "Textiles", "niftymidcap150"),
    ("PATANJALI.NS", "Patanjali Foods", "FMCG", "niftymidcap150"),
    ("PAYTM.NS", "Paytm", "Services", "niftymidcap150"),
    ("PERSISTENT.NS", "Persistent Systems", "Information Technology", "niftymidcap150"),
    ("PETRONET.NS", "Petronet LNG", "Petroleum Products", "niftymidcap150"),
    ("PHOENIXLTD.NS", "Phoenix Mills", "Realty", "niftymidcap150"),
    ("PIIND.NS", "PI Industries", "Chemicals", "niftymidcap150"),
    ("POLICYBZR.NS", "PolicyBazaar", "Insurance", "niftymidcap150"),
    ("POLYCAB.NS", "Polycab India", "Capital Goods", "niftymidcap150"),
    ("POWERINDIA.NS", "ABB Power India", "Power", "niftymidcap150"),
    ("PREMIERENE.NS", "Premier Energies", "Capital Goods", "niftymidcap150"),
    ("PRESTIGE.NS", "Prestige Estates", "Realty", "niftymidcap150"),
    ("RVNL.NS", "Rail Vikas Nigam", "Construction", "niftymidcap150"),
    ("SAIL.NS", "Steel Authority of India", "Metals & Mining", "niftymidcap150"),
    ("SBICARD.NS", "SBI Cards", "Financial Services", "niftymidcap150"),
    ("SCHAEFFLER.NS", "Schaeffler India", "Automobiles", "niftymidcap150"),
    ("SJVN.NS", "SJVN Limited", "Power", "niftymidcap150"),
    ("SOLARINDS.NS", "Solar Industries", "Chemicals", "niftymidcap150"),
    ("SONACOMS.NS", "Sona BLW Precision", "Automobiles", "niftymidcap150"),
    ("SRF.NS", "SRF Limited", "Chemicals", "niftymidcap150"),
    ("STARHEALTH.NS", "Star Health Insurance", "Insurance", "niftymidcap150"),
    ("SUNDARMFIN.NS", "Sundaram Finance", "Financial Services", "niftymidcap150"),
    ("SUNTV.NS", "Sun TV Network", "Media", "niftymidcap150"),
    ("SUPREMEIND.NS", "Supreme Industries", "Industrial Products", "niftymidcap150"),
    ("SUZLON.NS", "Suzlon Energy", "Capital Goods", "niftymidcap150"),
    ("SYNGENE.NS", "Syngene International", "Healthcare", "niftymidcap150"),
    ("TATACOMM.NS", "Tata Communications", "Telecommunication", "niftymidcap150"),
    ("TATAELXSI.NS", "Tata Elxsi", "Information Technology", "niftymidcap150"),
    ("TATAINVEST.NS", "Tata Investment Corp", "Capital Markets", "niftymidcap150"),
    ("TATATECH.NS", "Tata Technologies", "Information Technology", "niftymidcap150"),
    ("THERMAX.NS", "Thermax", "Capital Goods", "niftymidcap150"),
    ("TIINDIA.NS", "Tube Investments", "Automobiles", "niftymidcap150"),
    ("TORNTPOWER.NS", "Torrent Power", "Power", "niftymidcap150"),
    ("UBL.NS", "United Breweries", "Beverages", "niftymidcap150"),
    ("UNIONBANK.NS", "Union Bank of India", "Banks", "niftymidcap150"),
    ("UNOMINDA.NS", "UNO Minda", "Automobiles", "niftymidcap150"),
    ("UPL.NS", "UPL Limited", "Chemicals", "niftymidcap150"),
    ("VMM.NS", "Vedanta M&M", "Metals & Mining", "niftymidcap150"),
    ("VOLTAS.NS", "Voltas", "Consumer Goods", "niftymidcap150"),
    ("WAAREEENER.NS", "Waaree Energies", "Industrials", "niftymidcap150"),
    ("YESBANK.NS", "Yes Bank", "Banks", "niftymidcap150"),
]


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            universe_slug TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_ohlcv (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER, adj_close REAL,
            PRIMARY KEY (symbol, date)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS factor_scores (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            momentum_price REAL, momentum_vol REAL, rs_momentum REAL,
            trend_adx REAL, ma_structure REAL,
            pullback REAL, rsi REAL,
            liquidity REAL, volatility REAL,
            composite REAL,
            PRIMARY KEY (symbol, date)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS screener_results (
            run_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            composite REAL,
            factor_breakdown TEXT, factor_detail TEXT,
            entry_price REAL, target_price REAL, stoploss REAL,
            sector TEXT, universe TEXT,
            PRIMARY KEY (run_date, rank)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_regime (
            date TEXT PRIMARY KEY,
            regime TEXT, nifty_trend TEXT,
            breadth_ratio REAL, vix_proxy REAL
        )
    ''')

    existing = set(r[0] for r in c.execute("SELECT symbol FROM stocks").fetchall())
    for stock in STOCKS:
        if stock[0] not in existing:
            c.execute("INSERT INTO stocks (symbol, company_name, sector, universe_slug) VALUES (?,?,?,?)", stock)

    conn.commit()
    conn.close()
    print(f"DB initialized at {DB_PATH}")
    print(f"Stocks: {len(STOCKS)} registered")
    print("Run: python scripts/pipeline.py --full   to fetch data and screen")


if __name__ == '__main__':
    init_db()
