import os
from sqlalchemy import func
from app.models.watchlist import Watchlist, WatchlistItem, WatchlistScore
from app.models.stock import Stock
from app.models.market_data import DailyOHLCV

def simulate_scenario(watchlist_id: str, scenario: str, db):
    """
    Simulates a macroeconomic shock scenario on all stocks in a watchlist
    and returns baseline vs scenario composite scores and impact details.
    """
    # Fetch watchlist
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not wl:
        return {"error": "Watchlist not found"}
        
    # Get custom weights
    w_tech = float(wl.weight_technical)
    w_fund = float(wl.weight_fundamental)
    w_sent = float(wl.weight_sentiment)
    w_risk = float(wl.weight_risk)
    w_cat = float(wl.weight_catalyst)
    w_sum = w_tech + w_fund + w_sent + w_risk + w_cat
    if w_sum == 0:
        w_sum = 1.0

    # Get watchlist items
    items = db.query(WatchlistItem).filter(WatchlistItem.watchlist_id == watchlist_id).all()
    tickers = [item.ticker for item in items]
    
    if not tickers:
        return {"data": [], "summary": "No stocks in watchlist"}
        
    # Get company details
    stocks = db.query(Stock).filter(Stock.ticker.in_(tickers)).all()
    sector_map = {s.ticker: s.sector for s in stocks}
    name_map = {s.ticker: s.company_name for s in stocks}
    
    # Get current scores
    scores = db.query(WatchlistScore).filter(WatchlistScore.ticker.in_(tickers)).all()
    scores_map = {s.ticker: s for s in scores}

    # Get latest prices
    latest_ohlcv_subquery = db.query(
        DailyOHLCV.ticker,
        func.max(DailyOHLCV.date).label("max_date")
    ).filter(DailyOHLCV.ticker.in_(tickers)).group_by(DailyOHLCV.ticker).subquery()
    
    latest_ohlcvs = db.query(DailyOHLCV).join(
        latest_ohlcv_subquery,
        (DailyOHLCV.ticker == latest_ohlcv_subquery.c.ticker) &
        (DailyOHLCV.date == latest_ohlcv_subquery.c.max_date)
    ).all()
    price_map = {o.ticker: o.close for o in latest_ohlcvs}
    
    results = []
    total_baseline_score = 0.0
    total_scenario_score = 0.0
    
    for ticker in tickers:
        sector = sector_map.get(ticker, "General")
        name = name_map.get(ticker, f"{ticker} Tbk.")
        score_record = scores_map.get(ticker)
        price = float(price_map.get(ticker, 0.0))
        
        if not score_record:
            # Fallback defaults if no score calculated yet
            t_score = 50.0
            f_score = 50.0
            s_score = 50.0
            r_score = 50.0
            c_score = 50.0
        else:
            t_score = float(score_record.technical_score)
            f_score = float(score_record.fundamental_score)
            s_score = float(score_record.sentiment_score)
            r_score = float(score_record.risk_score)
            c_score = float(score_record.catalyst_score)
            
        # Compute baseline composite score
        baseline_score = (
            (t_score * w_tech) +
            (f_score * w_fund) +
            (s_score * w_sent) +
            (r_score * w_risk) +
            (c_score * w_cat)
        ) / w_sum
        baseline_score = round(baseline_score, 1)
        
        # Apply scenario-based shifts
        adj_t = t_score
        adj_f = f_score
        adj_s = s_score
        adj_r = r_score
        adj_c = c_score
        impact_desc = "No major impact expected."
        
        if scenario == "macro_shock":
            # High inflation / High interest rate hike (BI Rate)
            # Tech and Property suffer high debt costs
            if sector.lower() in ["technology", "properties", "property"]:
                adj_t = max(0.0, t_score - 20.0)
                adj_f = max(0.0, f_score - 25.0)
                adj_r = max(0.0, r_score - 15.0)
                adj_c = max(0.0, c_score - 10.0)
                impact_desc = "Sektor utang tinggi (Properti/Teknologi) terpukul oleh kenaikan biaya bunga dan pelemahan valuasi."
            # Financials are relatively resilient due to NIM margins
            elif sector.lower() in ["financials", "finance", "financial"]:
                adj_t = max(0.0, t_score - 2.0)
                adj_f = max(0.0, f_score - 3.0)
                adj_r = max(0.0, r_score - 2.0)
                impact_desc = "Sektor perbankan tangguh karena mendapat perlindungan marjin bunga bersih (NIM) yang lebih tinggi."
            # Defensives suffer less
            elif sector.lower() in ["consumer non-cyclicals", "utilities", "healthcare"]:
                adj_t = max(0.0, t_score - 5.0)
                adj_f = max(0.0, f_score - 5.0)
                adj_r = max(0.0, r_score - 3.0)
                impact_desc = "Sektor defensif cukup tangguh terhadap inflasi karena permintaan produk yang stabil."
            else:
                adj_t = max(0.0, t_score - 10.0)
                adj_f = max(0.0, f_score - 10.0)
                adj_r = max(0.0, r_score - 8.0)
                impact_desc = "Dampak moderat dari kenaikan suku bunga dan perlambatan pengeluaran konsumen."
                
        elif scenario == "commodity_collapse":
            # Coal, Oil, Gas, Mining crash
            if sector.lower() in ["energy", "basic materials"]:
                adj_t = max(0.0, t_score - 30.0)
                adj_f = max(0.0, f_score - 35.0)
                adj_r = max(0.0, r_score - 20.0)
                adj_c = max(0.0, c_score - 15.0)
                impact_desc = "Sektor komoditas terpukul hebat akibat kejatuhan harga jual global (Batubara, Nikel, Minyak)."
            # Consumer/Transport benefit from lower input costs
            elif sector.lower() in ["transportation", "consumer cyclicals", "industrial", "industrials"]:
                adj_t = min(100.0, t_score + 5.0)
                adj_f = min(100.0, f_score + 8.0)
                impact_desc = "Mendapat dampak positif berkat penurunan biaya logistik, bahan baku, dan energi."
            else:
                adj_t = max(0.0, t_score - 5.0)
                adj_f = max(0.0, f_score - 5.0)
                impact_desc = "Dampak netral atau minimal dari guncangan komoditas global."
                
        elif scenario == "market_crisis":
            # Systemic panic sell-off. Highly volatile/risky stocks drop the most
            if r_score < 40.0:  # High volatility / high drawdown risk
                adj_t = max(0.0, t_score - 25.0)
                adj_r = max(0.0, r_score - 25.0)
                adj_s = max(0.0, s_score - 30.0)
                impact_desc = "Saham volatilitas tinggi (High-Beta) tertekan kepanikan pasar secara ekstrem."
            elif r_score >= 70.0:  # Defensive / low volatility
                adj_t = max(0.0, t_score - 8.0)
                adj_r = max(0.0, r_score - 8.0)
                adj_s = max(0.0, s_score - 10.0)
                impact_desc = "Saham defensif (Low-Beta) menjadi pelindung portofolio dari aksi jual sistemik."
            else:
                adj_t = max(0.0, t_score - 15.0)
                adj_r = max(0.0, r_score - 15.0)
                adj_s = max(0.0, s_score - 20.0)
                impact_desc = "Mengalami penurunan sedang searah dengan kejatuhan indeks pasar IHSG."

        # Compute scenario composite score
        scenario_score = (
            (adj_t * w_tech) +
            (adj_f * w_fund) +
            (adj_s * w_sent) +
            (adj_r * w_risk) +
            (adj_c * w_cat)
        ) / w_sum
        scenario_score = round(scenario_score, 1)
        
        delta = round(scenario_score - baseline_score, 1)
        
        total_baseline_score += baseline_score
        total_scenario_score += scenario_score
        
        results.append({
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "price": price,
            "baseline_score": baseline_score,
            "scenario_score": scenario_score,
            "delta": delta,
            "impact": impact_desc,
            "breakdown": {
                "technical": {"baseline": t_score, "adjusted": round(adj_t, 1)},
                "fundamental": {"baseline": f_score, "adjusted": round(adj_f, 1)},
                "sentiment": {"baseline": s_score, "adjusted": round(adj_s, 1)},
                "risk": {"baseline": r_score, "adjusted": round(adj_r, 1)},
                "catalyst": {"baseline": c_score, "adjusted": round(adj_c, 1)}
            }
        })
        
    avg_baseline = round(total_baseline_score / len(tickers), 1) if tickers else 0.0
    avg_scenario = round(total_scenario_score / len(tickers), 1) if tickers else 0.0
    avg_delta = round(avg_scenario - avg_baseline, 1)
    
    # Portfolio summary text
    summary_text = "Portfolio dalam keadaan stabil."
    if scenario == "macro_shock":
        if avg_delta < -10:
            summary_text = f"Risiko Kenaikan Bunga Tinggi: Watchlist Anda sangat sensitif (rata-rata skor turun {avg_delta} poin). Diperlukan diversifikasi ke sektor Perbankan/Defensif."
        else:
            summary_text = f"Ketahanan Bunga Moderat: Watchlist Anda cukup defensif terhadap goncangan suku bunga (rata-rata penurunan hanya {avg_delta} poin)."
    elif scenario == "commodity_collapse":
        if avg_delta < -10:
            summary_text = f"Kerentanan Komoditas Tinggi: Watchlist Anda didominasi emiten tambang/energi (rata-rata turun {avg_delta} poin). Berisiko tinggi jika harga komoditas global jatuh."
        else:
            summary_text = f"Aman dari Komoditas: Portofolio Anda tidak terpapar langsung oleh harga komoditas (rata-rata penurunan hanya {avg_delta} poin)."
    elif scenario == "market_crisis":
        if avg_delta < -12:
            summary_text = f"Risiko Likuiditas Ekstrem: Watchlist Anda didominasi saham agresif ber-Beta tinggi. Jika IHSG crash, portofolio Anda berpotensi anjlok tajam (rata-rata turun {avg_delta} poin)."
        else:
            summary_text = f"Perlindungan Defensif Kuat: Portofolio didominasi saham defensif ber-Beta rendah. Mampu menahan badai koreksi IHSG dengan sangat baik (rata-rata turun hanya {avg_delta} poin)."

    return {
        "data": results,
        "avg_baseline": avg_baseline,
        "avg_scenario": avg_scenario,
        "avg_delta": avg_delta,
        "summary": summary_text
    }
