import { useState, useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'
import './index.css'

function App() {
  const [predictions, setPredictions] = useState([])
  const [predictionHorizon, setPredictionHorizon] = useState("T+1")
  const [status, setStatus] = useState({ message: "Idle", progress: 0, is_running: false })
  const [selectedTicker, setSelectedTicker] = useState(null)
  const [backtestData, setBacktestData] = useState(null)
  const [isBacktesting, setIsBacktesting] = useState(false)
  
  // Watchlist & Scoring state variables
  const [activeTab, setActiveTab] = useState("screener") // "screener" or "watchlist"
  const [watchlists, setWatchlists] = useState([])
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("")
  const [watchlistItems, setWatchlistItems] = useState([])
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newWatchlistName, setNewWatchlistName] = useState("")
  const [newWatchlistDesc, setNewWatchlistDesc] = useState("")
  const [watchlistWeights, setWatchlistWeights] = useState({
    technical: 0.30,
    fundamental: 0.25,
    sentiment: 0.15,
    risk: 0.15,
    catalyst: 0.15
  })
  const [showWeightsPanel, setShowWeightsPanel] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState([])
  const [selectedWatchlistItem, setSelectedWatchlistItem] = useState(null)

  // Learning Engine state variables
  const [learningPerf, setLearningPerf] = useState([])
  const [learningRegime, setLearningRegime] = useState({ current: {}, history: [] })
  const [retrainHistory, setRetrainHistory] = useState([])
  const [featureImportances, setFeatureImportances] = useState([])
  const [isRetraining, setIsRetraining] = useState(false)
  const [retrainStatus, setRetrainStatus] = useState("Idle")

  // Scenario Stress Testing state variables
  const [selectedScenario, setSelectedScenario] = useState("normal")
  const [scenarioData, setScenarioData] = useState(null)

  // Chart Overlays
  const [showSmaOverlay, setShowSmaOverlay] = useState(false)
  const [showBbandsOverlay, setShowBbandsOverlay] = useState(false)

  // Paper Trading Portfolio state
  const [portfolio, setPortfolio] = useState(null)
  const [showTradeModal, setShowTradeModal] = useState(false)
  const [tradeAction, setTradeAction] = useState("BUY")
  const [tradeTicker, setTradeTicker] = useState("")
  const [tradeQty, setTradeQty] = useState(100)
  const [tradeNotes, setTradeNotes] = useState("")
  const [tradeError, setTradeError] = useState("")
  const [tradeSuccess, setTradeSuccess] = useState("")

  // Comparison state variables
  const [compareTickers, setCompareTickers] = useState([])
  const [compareData, setCompareData] = useState([])

  // Bandarologi state variables
  const [bandarData, setBandarData] = useState(null)



  const chartContainerRef = useRef()
  const chartRef = useRef(null)
  const candlestickSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)

  // Polling interval for status
  useEffect(() => {
    let interval;
    if (status.is_running) {
      interval = setInterval(() => {
        fetchStatus()
      }, 2000)
    }
    return () => clearInterval(interval)
  }, [status.is_running])

  // Initial load
  useEffect(() => {
    fetchPredictions()
    fetchStatus()
    fetchWatchlists()
  }, [])

  // Watchlists trigger item reloading
  useEffect(() => {
    if (selectedWatchlistId) {
      const activeWl = watchlists.find(w => w.id === selectedWatchlistId)
      if (activeWl) {
        setWatchlistWeights({
          technical: activeWl.weight_technical,
          fundamental: activeWl.weight_fundamental,
          sentiment: activeWl.weight_sentiment,
          risk: activeWl.weight_risk,
          catalyst: activeWl.weight_catalyst
        })
      }
      setSelectedScenario("normal")
      setScenarioData(null)
      fetchWatchlistScores(selectedWatchlistId)
    }
  }, [selectedWatchlistId, watchlists])

  // Chart initialization and update
  useEffect(() => {
    let active = true;
    let resizeHandler = null;
    let chartInstance = null;

    if (selectedTicker && chartContainerRef.current) {
      const chartOptions = {
        layout: {
          textColor: '#8b9bb4',
          background: { type: 'solid', color: 'transparent' },
        },
        grid: {
          vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
          horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        width: chartContainerRef.current.clientWidth,
        height: 400,
        timeScale: {
          timeVisible: false,
          borderColor: 'rgba(255, 255, 255, 0.1)',
        },
        rightPriceScale: {
          borderColor: 'rgba(255, 255, 255, 0.1)',
        }
      };

      chartInstance = createChart(chartContainerRef.current, chartOptions);
      chartRef.current = chartInstance;
      
      const candlestickSeries = chartInstance.addCandlestickSeries({
        upColor: '#00d2ff',
        downColor: '#ff2a2a',
        borderVisible: false,
        wickUpColor: '#00d2ff',
        wickDownColor: '#ff2a2a',
      });
      candlestickSeriesRef.current = candlestickSeries;

      const volumeSeries = chartInstance.addHistogramSeries({
        color: '#26a69a',
        priceFormat: { type: 'volume' },
        priceScaleId: '', // set as an overlay
        scaleMargins: {
          top: 0.8, // highest point of the series will be at 80%
          bottom: 0,
        },
      });
      volumeSeriesRef.current = volumeSeries;

      // Indicators Overlays
      const sma5Series = showSmaOverlay ? chartInstance.addLineSeries({ color: '#29b6f6', lineWidth: 1.5, title: 'SMA 5' }) : null;
      const sma20Series = showSmaOverlay ? chartInstance.addLineSeries({ color: '#ff9800', lineWidth: 1.5, title: 'SMA 20' }) : null;
      const sma50Series = showSmaOverlay ? chartInstance.addLineSeries({ color: '#4caf50', lineWidth: 1.5, title: 'SMA 50' }) : null;

      const bbUpperSeries = showBbandsOverlay ? chartInstance.addLineSeries({ color: 'rgba(38, 166, 154, 0.4)', lineWidth: 1 }) : null;
      const bbMiddleSeries = showBbandsOverlay ? chartInstance.addLineSeries({ color: 'rgba(38, 166, 154, 0.3)', lineWidth: 1, lineStyle: 2 }) : null;
      const bbLowerSeries = showBbandsOverlay ? chartInstance.addLineSeries({ color: 'rgba(38, 166, 154, 0.4)', lineWidth: 1 }) : null;

      resizeHandler = () => {
        if (chartContainerRef.current && chartInstance) {
          chartInstance.applyOptions({ width: chartContainerRef.current.clientWidth });
        }
      };
      window.addEventListener('resize', resizeHandler);

      // Fetch data for chart
      fetch(`http://localhost:8000/api/chart/${selectedTicker}`)
        .then(res => res.json())
        .then(resData => {
          if (!active) return;
          const data = resData.data;
          if(data && data.length > 0 && candlestickSeriesRef.current && volumeSeriesRef.current) {
            candlestickSeriesRef.current.setData(data);
            
            const volumeData = data.map(d => ({
              time: d.time,
              value: d.volume,
              color: d.close >= d.open ? 'rgba(0, 210, 255, 0.3)' : 'rgba(255, 42, 42, 0.3)'
            }));
            volumeSeriesRef.current.setData(volumeData);

            if (showSmaOverlay) {
              const sma5Data = data.filter(d => d.sma_5 !== undefined && d.sma_5 !== null).map(d => ({ time: d.time, value: d.sma_5 }));
              const sma20Data = data.filter(d => d.sma_20 !== undefined && d.sma_20 !== null).map(d => ({ time: d.time, value: d.sma_20 }));
              const sma50Data = data.filter(d => d.sma_50 !== undefined && d.sma_50 !== null).map(d => ({ time: d.time, value: d.sma_50 }));
              sma5Series?.setData(sma5Data);
              sma20Series?.setData(sma20Data);
              sma50Series?.setData(sma50Data);
            }
            if (showBbandsOverlay) {
              const bbUpperData = data.filter(d => d.bb_upper !== undefined && d.bb_upper !== null).map(d => ({ time: d.time, value: d.bb_upper }));
              const bbMiddleData = data.filter(d => d.bb_middle !== undefined && d.bb_middle !== null).map(d => ({ time: d.time, value: d.bb_middle }));
              const bbLowerData = data.filter(d => d.bb_lower !== undefined && d.bb_lower !== null).map(d => ({ time: d.time, value: d.bb_lower }));
              bbUpperSeries?.setData(bbUpperData);
              bbMiddleSeries?.setData(bbMiddleData);
              bbLowerSeries?.setData(bbLowerData);
            }

            if (chartInstance) {
              chartInstance.timeScale().fitContent();
            }
          }
        })
        .catch(err => {
          if (active) {
            console.error(err);
          }
        });
    }

    return () => {
      active = false;
      if (resizeHandler) {
        window.removeEventListener('resize', resizeHandler);
      }
      if (chartInstance) {
        chartInstance.remove();
      }
      chartRef.current = null;
      candlestickSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [selectedTicker, showSmaOverlay, showBbandsOverlay])

  // Fetch Bandarologi data when selectedTicker changes
  useEffect(() => {
    if (selectedTicker) {
      fetch(`http://localhost:8000/api/bandarologi/${selectedTicker}`)
        .then(res => res.json())
        .then(data => setBandarData(data))
        .catch(err => console.error("Error fetching bandarologi:", err));
    } else {
      setBandarData(null);
    }
  }, [selectedTicker])

  // Watchlist stock search autocomplete
  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      if (searchQuery.trim().length >= 1) {
        fetch(`http://localhost:8000/api/stocks/search?q=${searchQuery}`)
          .then(res => res.json())
          .then(data => setSearchResults(data))
          .catch(err => console.error(err))
      } else {
        setSearchResults([])
      }
    }, 300)

    return () => clearTimeout(delayDebounceFn)
  }, [searchQuery])

  const fetchPortfolio = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/portfolio')
      const data = await res.json()
      if (!data.error) {
        setPortfolio(data)
      }
    } catch (e) {
      console.error("Error fetching portfolio:", e)
    }
  }

  const handleExecuteTrade = async (e) => {
    if (e) e.preventDefault()
    setTradeError("")
    setTradeSuccess("")
    try {
      const res = await fetch('http://localhost:8000/api/portfolio/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: tradeTicker,
          action: tradeAction,
          quantity: parseInt(tradeQty),
          notes: tradeNotes
        })
      })
      const data = await res.json()
      if (res.status !== 200) {
        setTradeError(data.detail || "Terjadi kesalahan saat memproses transaksi.")
      } else {
        setTradeSuccess(data.message)
        setTradeNotes("")
        fetchPortfolio()
        if (selectedWatchlistId) {
          fetchWatchlistScores(selectedWatchlistId)
        }
        setTimeout(() => {
          setShowTradeModal(false)
          setTradeSuccess("")
        }, 1500)
      }
    } catch (err) {
      setTradeError("Gagal menghubungi server.")
      console.error(err)
    }
  }

  useEffect(() => {
    if (compareTickers.length >= 2) {
      fetch(`http://localhost:8000/api/stocks/compare?tickers=${compareTickers.join(",")}`)
        .then(res => res.json())
        .then(resData => {
          if (resData.data) {
            setCompareData(resData.data)
          }
        })
        .catch(err => console.error(err))
    } else {
      setCompareData([])
    }
  }, [compareTickers])

  useEffect(() => {
    if (activeTab === 'learning') {
      fetchLearningData()
    } else if (activeTab === 'portfolio') {
      fetchPortfolio()
    }
  }, [activeTab])

  const fetchPredictions = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/predictions')
      const data = await res.json()
      setPredictions(data.data || [])
      if (data.data && data.data.length > 0 && !selectedTicker && activeTab === 'screener') {
        setSelectedTicker(data.data[0].ticker)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const fetchStatus = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/update-status?t=${Date.now()}`)
      const data = await res.json()
      setStatus(data)
      if (!data.is_running && data.progress === 100) {
        fetchPredictions()
        if (selectedWatchlistId) {
          fetchWatchlistScores(selectedWatchlistId)
        }
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleUpdate = async () => {
    if (status.is_running) return;
    try {
      setStatus({ message: "Initializing...", progress: 1, is_running: true })
      await fetch('http://localhost:8000/api/trigger-update', { method: 'POST' })
    } catch (e) {
      console.error(e)
    }
  }

  const handleRunBacktest = async () => {
    setIsBacktesting(true);
    try {
      const res = await fetch('http://localhost:8000/api/backtest?days=100');
      const data = await res.json();
      if(!data.error) {
        setBacktestData(data);
      }
    } catch (e) {
      console.error(e);
    }
    setIsBacktesting(false);
  }

  // --- Learning Engine Functions ---
  const fetchLearningData = async () => {
    try {
      const [perfRes, regimeRes, retrainRes] = await Promise.all([
        fetch('http://localhost:8000/api/learning/performance'),
        fetch('http://localhost:8000/api/learning/regime'),
        fetch('http://localhost:8000/api/learning/retrain-history')
      ])
      const [perfData, regimeData, retrainData] = await Promise.all([
        perfRes.json(),
        regimeRes.json(),
        retrainRes.json()
      ])
      
      setLearningPerf(perfData.data || [])
      setLearningRegime(regimeData || { current: {}, history: [] })
      setRetrainHistory(retrainData.history || [])
      setFeatureImportances(retrainData.feature_importances || [])
      
      if (retrainData.history && retrainData.history.length > 0) {
        const latest = retrainData.history[0]
        if (latest.status === 'success') {
          setRetrainStatus("Idle")
        } else if (latest.status === 'failed') {
          setRetrainStatus(`Last retrain failed: ${latest.error || 'Unknown error'}`)
        } else {
          setRetrainStatus(`Retraining in progress... (${latest.status})`)
        }
      }
    } catch (e) {
      console.error("Error fetching learning data:", e)
    }
  }

  const handleTriggerRetrain = async () => {
    if (isRetraining) return
    setIsRetraining(true)
    setRetrainStatus("Retraining started...")
    try {
      const res = await fetch('http://localhost:8000/api/learning/trigger-retrain', { method: 'POST' })
      const data = await res.json()
      if (data.status === "retraining started") {
        let attempts = 0
        const interval = setInterval(async () => {
          const checkRes = await fetch('http://localhost:8000/api/learning/retrain-history')
          const checkData = await checkRes.json()
          const history = checkData.history || []
          
          if (history.length > 0) {
            const latest = history[0]
            if (latest.status === 'success') {
              clearInterval(interval)
              setRetrainStatus("Retraining successful!")
              setRetrainHistory(history)
              setFeatureImportances(checkData.feature_importances || [])
              setIsRetraining(false)
            } else if (latest.status === 'failed') {
              clearInterval(interval)
              setRetrainStatus(`Retraining failed: ${latest.error || 'Unknown error'}`)
              setIsRetraining(false)
            } else {
              setRetrainStatus(`Retraining in progress... (${latest.status})`)
            }
          }
          attempts++
          if (attempts > 60) {
            clearInterval(interval)
            setRetrainStatus("Retraining timeout.")
            setIsRetraining(false)
          }
        }, 2000)
      }
    } catch (e) {
      console.error(e)
      setRetrainStatus("Error triggering retraining.")
      setIsRetraining(false)
    }
  }

  const handleScenarioChange = async (scenarioName) => {
    setSelectedScenario(scenarioName)
    if (scenarioName === "normal") {
      setScenarioData(null)
      return
    }
    
    if (!selectedWatchlistId) return
    
    try {
      const res = await fetch("http://localhost:8000/api/predictions/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          watchlist_id: selectedWatchlistId,
          scenario: scenarioName
        })
      })
      const data = await res.json()
      if (!data.error) {
        setScenarioData(data)
      }
    } catch (e) {
      console.error("Error simulating scenario:", e)
    }
  }

  useEffect(() => {
    if (activeTab === 'learning') {
      fetchLearningData()
    }
  }, [activeTab])

  // --- Watchlist Functions ---
  const fetchWatchlists = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/watchlists')
      const data = await res.json()
      if (Array.isArray(data)) {
        setWatchlists(data)
        if (data.length > 0 && !selectedWatchlistId) {
          setSelectedWatchlistId(data[0].id)
        }
      } else {
        setWatchlists([])
        console.error("Watchlists response is not an array:", data)
      }
    } catch (e) {
      setWatchlists([])
      console.error("Error fetching watchlists:", e)
    }
  }

  const fetchWatchlistScores = async (id) => {
    if (!id) return;
    try {
      const res = await fetch(`http://localhost:8000/api/watchlists/${id}/scores`)
      const resData = await res.json()
      const itemsList = resData.data;
      if (Array.isArray(itemsList)) {
        setWatchlistItems(itemsList)
        if (itemsList.length > 0) {
          // If current item is set and still in the watchlist, keep it, otherwise set first
          const currentItem = itemsList.find(item => selectedWatchlistItem && item.ticker === selectedWatchlistItem.ticker);
          setSelectedWatchlistItem(currentItem || itemsList[0])
          setSelectedTicker(currentItem ? currentItem.ticker : itemsList[0].ticker)
        } else {
          setSelectedWatchlistItem(null)
        }
      } else {
        setWatchlistItems([])
        setSelectedWatchlistItem(null)
        console.error("Watchlist scores response is not an array:", resData)
      }
    } catch (e) {
      setWatchlistItems([])
      setSelectedWatchlistItem(null)
      console.error(e)
    }
  }

  const handleCreateWatchlist = async (e) => {
    e.preventDefault()
    if (!newWatchlistName.trim()) return;
    try {
      const res = await fetch('http://localhost:8000/api/watchlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newWatchlistName,
          description: newWatchlistDesc
        })
      })
      const data = await res.json()
      if (data.status === "success") {
        setNewWatchlistName("")
        setNewWatchlistDesc("")
        setShowCreateModal(false)
        await fetchWatchlists()
        setSelectedWatchlistId(data.watchlist_id)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleDeleteWatchlist = async () => {
    if (!selectedWatchlistId) return;
    if (!window.confirm("Apakah Anda yakin ingin menghapus watchlist ini beserta semua isinya?")) return;
    try {
      const res = await fetch(`http://localhost:8000/api/watchlists/${selectedWatchlistId}`, {
        method: 'DELETE'
      })
      const data = await res.json()
      if (data.status === "success") {
        setSelectedWatchlistItem(null)
        setWatchlistItems([])
        const nextWatchlists = watchlists.filter(w => w.id !== selectedWatchlistId)
        setWatchlists(nextWatchlists)
        if (nextWatchlists.length > 0) {
          setSelectedWatchlistId(nextWatchlists[0].id)
        } else {
          setSelectedWatchlistId("")
        }
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleAddStock = async (ticker) => {
    if (!selectedWatchlistId) return;
    try {
      const res = await fetch(`http://localhost:8000/api/watchlists/${selectedWatchlistId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: ticker,
          notes: "Saham Pilihan Utama"
        })
      })
      const data = await res.json()
      if (data.status === "success") {
        setSearchQuery("")
        setSearchResults([])
        fetchWatchlistScores(selectedWatchlistId)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleDeleteStock = async (ticker, e) => {
    e.stopPropagation()
    if (!selectedWatchlistId) return;
    try {
      const res = await fetch(`http://localhost:8000/api/watchlists/${selectedWatchlistId}/items/${ticker}`, {
        method: 'DELETE'
      })
      const data = await res.json()
      if (data.status === "success") {
        fetchWatchlistScores(selectedWatchlistId)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleSaveWeights = async () => {
    if (!selectedWatchlistId) return;
    const activeWl = watchlists.find(w => w.id === selectedWatchlistId)
    if (!activeWl) return;
    
    try {
      const res = await fetch(`http://localhost:8000/api/watchlists/${selectedWatchlistId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: activeWl.name,
          description: activeWl.description,
          weight_technical: watchlistWeights.technical,
          weight_fundamental: watchlistWeights.fundamental,
          weight_sentiment: watchlistWeights.sentiment,
          weight_risk: watchlistWeights.risk,
          weight_catalyst: watchlistWeights.catalyst
        })
      })
      const data = await res.json()
      if (data.status === "success") {
        alert("Bobot kustom watchlist berhasil disimpan!")
        await fetchWatchlists()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const applyPreset = (presetName) => {
    switch (presetName) {
      case "balanced":
        setWatchlistWeights({ technical: 0.30, fundamental: 0.25, sentiment: 0.15, risk: 0.15, catalyst: 0.15 });
        break;
      case "technical":
        setWatchlistWeights({ technical: 0.50, fundamental: 0.10, sentiment: 0.15, risk: 0.15, catalyst: 0.10 });
        break;
      case "fundamental":
        setWatchlistWeights({ technical: 0.15, fundamental: 0.45, sentiment: 0.10, risk: 0.20, catalyst: 0.10 });
        break;
      case "momentum":
        setWatchlistWeights({ technical: 0.40, fundamental: 0.10, sentiment: 0.20, risk: 0.10, catalyst: 0.20 });
        break;
      default:
        break;
    }
  }

  const getCompositeScore = (item) => {
    const w = watchlistWeights;
    const sum = w.technical + w.fundamental + w.sentiment + w.risk + w.catalyst;
    if (sum === 0) return 0;
    
    const tScore = (
      (item.technical_score * w.technical) +
      (item.fundamental_score * w.fundamental) +
      (item.sentiment_score * w.sentiment) +
      (item.risk_score * w.risk) +
      (item.catalyst_score * w.catalyst)
    ) / sum;
    
    return Math.round(tScore * 10) / 10;
  }

  const getClassification = (score) => {
    if (score >= 80) return "Strong";
    if (score >= 60) return "Good";
    if (score >= 40) return "Neutral";
    if (score >= 20) return "Weak";
    return "Avoid";
  }

  return (
    <div className="container">
      <header className="header">
        <div className="logo-area">
          <div className="logo-icon">▲</div>
          <h1>AlphaHunter <span className="highlight">IDX</span></h1>
        </div>
        <p className="subtitle">AI-Powered Indonesian Stock Market Prediction</p>
      </header>

      {/* Navigation Tabs */}
      <div className="tabs-container">
        <button 
          className={`tab-button ${activeTab === 'screener' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('screener');
            if (predictions.length > 0) {
              setSelectedTicker(predictions[0].ticker);
            }
          }}
        >
          AI SCREENER (TOP 10)
        </button>
        <button 
          className={`tab-button ${activeTab === 'watchlist' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('watchlist');
            if (watchlistItems.length > 0) {
              setSelectedWatchlistItem(watchlistItems[0]);
              setSelectedTicker(watchlistItems[0].ticker);
            }
          }}
        >
          WATCHLIST & AI SCORER
        </button>
        <button 
          className={`tab-button ${activeTab === 'portfolio' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('portfolio');
            fetchPortfolio();
            setSelectedTicker(null);
          }}
        >
          💼 VIRTUAL PORTFOLIO
        </button>
        <button 
          className={`tab-button ${activeTab === 'learning' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('learning');
            setSelectedTicker(null); // Hide historical stock charts on the learning view
          }}
        >
          AI LEARNING ENGINE
        </button>
      </div>

      <div className="dashboard">
        {/* Controls Panel */}
        {activeTab !== 'learning' && activeTab !== 'portfolio' && (
          <div className="glass-panel controls">
            <h2>Engine Controls</h2>
            <div className="status-container">
              <p className="status-text">{status.message}</p>
              {status.is_running && (
                <div className="progress-bar-bg">
                  <div 
                    className="progress-bar-fill" 
                    style={{ width: `${status.progress}%` }}
                  ></div>
                </div>
              )}
            </div>
            
            <button 
              className={`btn-update ${status.is_running ? 'running' : ''}`}
              onClick={handleUpdate}
              disabled={status.is_running}
              style={{ marginBottom: '0.8rem' }}
            >
              {status.is_running ? `Processing (${status.progress}%)` : 'UPDATE AI PREDICTIONS'}
            </button>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%', marginTop: '0.5rem' }}>
              <button 
                className="btn-update"
                style={{ width: '100%', padding: '0.6rem 1.2rem', background: 'rgba(0, 210, 255, 0.15)', borderColor: 'rgba(0, 210, 255, 0.3)', color: 'var(--primary-glow)', marginTop: 0 }}
                onClick={() => window.open('http://localhost:8000/api/reports/daily/csv')}
              >
                📥 DOWNLOAD REPORT (CSV)
              </button>
              <button 
                className="btn-update"
                style={{ width: '100%', padding: '0.6rem 1.2rem', background: 'rgba(168, 85, 247, 0.15)', borderColor: 'rgba(168, 85, 247, 0.3)', color: '#a855f7', marginTop: 0 }}
                onClick={() => window.print()}
              >
                🖨️ PRINT REPORT (PDF)
              </button>
            </div>
          </div>
        )}

        {activeTab === 'screener' && (
          /* Predictions Panel */
          <div className="glass-panel predictions">
            <div className="predictions-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '1rem' }}>
              <h2 style={{ marginBottom: 0 }}>Top 10 {predictionHorizon} Buys</h2>
              <div className="horizon-tabs" style={{ display: 'flex', gap: '0.5rem' }}>
                <button 
                  className={`btn-preset ${predictionHorizon === 'T+1' ? 'active' : ''}`}
                  style={{ 
                    padding: '0.4rem 0.8rem', 
                    fontSize: '0.8rem', 
                    borderRadius: '6px', 
                    fontWeight: 'bold',
                    cursor: 'pointer',
                    background: predictionHorizon === 'T+1' ? 'var(--primary-glow)' : 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff'
                  }}
                  onClick={() => setPredictionHorizon('T+1')}
                >
                  Horizon T+1 (Harian)
                </button>
                <button 
                  className={`btn-preset ${predictionHorizon === 'T+3' ? 'active' : ''}`}
                  style={{ 
                    padding: '0.4rem 0.8rem', 
                    fontSize: '0.8rem', 
                    borderRadius: '6px', 
                    fontWeight: 'bold',
                    cursor: 'pointer',
                    background: predictionHorizon === 'T+3' ? 'var(--primary-glow)' : 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff'
                  }}
                  onClick={() => setPredictionHorizon('T+3')}
                >
                  Horizon T+3 (Swing 3-Hari)
                </button>
              </div>
            </div>
            {!Array.isArray(predictions) || predictions.length === 0 ? (
              <p className="no-data">No predictions available. Run an update first.</p>
            ) : (
              <div className="table-responsive">
                <table className="pred-table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Ticker</th>
                      <th>Close Price</th>
                      <th>Probability ({predictionHorizon})</th>
                      <th>Patterns</th>
                      <th>Bandarologi</th>
                      <th>Prediction Date</th>
                      <th>Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...predictions]
                      .sort((a, b) => {
                        if (predictionHorizon === 'T+3') {
                          const valA = parseFloat(a.prob_up_t3_raw) || 0;
                          const valB = parseFloat(b.prob_up_t3_raw) || 0;
                          return valB - valA;
                        } else {
                          const valA = parseFloat(a.prob_up_raw) || parseFloat(a.prob_up) || 0;
                          const valB = parseFloat(b.prob_up_raw) || parseFloat(b.prob_up) || 0;
                          return valB - valA;
                        }
                      })
                      .slice(0, 10)
                      .map((row, index) => (
                        <tr 
                          key={index} 
                          className={selectedTicker === row.ticker ? 'active-row' : ''}
                          onClick={() => setSelectedTicker(row.ticker)}
                          style={{ cursor: 'pointer' }}
                        >
                          <td className="rank-col">#{index + 1}</td>
                          <td className="ticker-col">{row.ticker}</td>
                          <td>Rp {Number(row.close).toLocaleString('id-ID')}</td>
                          <td className="prob-col">
                            <div className="prob-pill">
                              {predictionHorizon === 'T+3' ? (row.prob_up_t3 || row.prob_up_t3_raw || '-') : row.prob_up}
                            </div>
                          </td>
                          <td>
                            {row.patterns && row.patterns !== 'nan' && row.patterns !== '' ? (
                              row.patterns.split('|').map((pat, idx) => (
                                <span key={idx} className={`badge badge-${pat.toLowerCase().replace(' ', '-')}`}>
                                  {pat}
                                </span>
                              ))
                            ) : (
                              <span className="text-gray-500 text-xs">-</span>
                            )}
                          </td>
                          <td>
                            {row.bandarologi_status ? (
                              <span className={`badge badge-bandarologi status-${row.bandarologi_status.toLowerCase().replace(' ', '-')}`}>
                                {row.bandarologi_status}
                              </span>
                            ) : (
                              <span className="text-gray-500 text-xs">-</span>
                            )}
                          </td>
                          <td>{row.date}</td>
                          <td>
                            <button 
                              className="btn-preset active" 
                              style={{ padding: '0.35rem 0.7rem', fontSize: '0.75rem', background: 'var(--primary-glow)', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setTradeTicker(row.ticker);
                                setTradeAction("BUY");
                                setTradeQty(100);
                                setTradeError("");
                                setTradeSuccess("");
                                setShowTradeModal(true);
                              }}
                            >
                              Beli
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'watchlist' && (
          /* Watchlist Panel */
          <div className="glass-panel predictions" style={{ animation: 'fadeIn 0.3s ease' }}>
            <div className="watchlist-header">
              <div className="watchlist-select-area">
                <select 
                  className="select-watchlist"
                  value={selectedWatchlistId}
                  onChange={(e) => setSelectedWatchlistId(e.target.value)}
                >
                  {Array.isArray(watchlists) && watchlists.map(w => (
                    <option key={w.id} value={w.id}>{w.name}</option>
                  ))}
                  {(!Array.isArray(watchlists) || watchlists.length === 0) && <option value="">No watchlists</option>}
                </select>
                
                <button 
                  className="btn-icon" 
                  title="Create New Watchlist"
                  onClick={() => setShowCreateModal(true)}
                >
                  ➕
                </button>
                
                {selectedWatchlistId && (
                  <button 
                    className="btn-icon delete" 
                    title="Delete Watchlist"
                    onClick={handleDeleteWatchlist}
                  >
                    🗑️
                  </button>
                )}
              </div>
              
              {selectedWatchlistId && (
                <div className="search-container">
                  <input 
                    type="text" 
                    className="search-input"
                    placeholder="Search & Add Stock..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                  {Array.isArray(searchResults) && searchResults.length > 0 && (
                    <div className="search-dropdown">
                      {searchResults.map(stock => (
                        <div 
                          key={stock.ticker} 
                          className="search-item"
                          onClick={() => handleAddStock(stock.ticker)}
                        >
                          <span className="search-item-ticker">{stock.ticker}</span>
                          <span className="search-item-name">{stock.name} ({stock.sector})</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            
            {selectedWatchlistId && (
              <>
                {/* Scenario Stress Test Selector */}
                <div className="weights-panel-toggle" style={{ borderLeft: '3px solid var(--primary-glow)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                  <span>🛡️ WATCHLIST STRESS TESTING (SCENARIO ANALYSIS)</span>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <select
                      className="select-watchlist"
                      style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem', background: '#0a0d17', border: '1px solid var(--glass-border)', color: '#fff', borderRadius: '6px', cursor: 'pointer', outline: 'none' }}
                      value={selectedScenario}
                      onChange={(e) => handleScenarioChange(e.target.value)}
                    >
                      <option value="normal">Baseline (Normal)</option>
                      <option value="macro_shock">BI Rate Hike & Inflation Shock</option>
                      <option value="commodity_collapse">Global Commodity Price Collapse</option>
                      <option value="market_crisis">Systemic Market Crash (IHSG -5%)</option>
                    </select>
                  </div>
                </div>

                {/* Scenario Summary Banner */}
                {selectedScenario !== 'normal' && scenarioData && (
                  <div className="weights-panel" style={{ background: 'rgba(239, 68, 68, 0.03)', borderColor: 'rgba(239, 68, 68, 0.2)', marginBottom: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', animation: 'fadeIn 0.3s ease' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ color: 'var(--primary-glow)', fontSize: '0.9rem' }}>SCENARIO SIMULATION ACTIVE: {
                        selectedScenario === 'macro_shock' ? 'Kenaikan Suku Bunga & Inflasi' :
                        selectedScenario === 'commodity_collapse' ? 'Kejatuhan Komoditas Global' :
                        'Krisis IHSG Crash -5%'
                      }</strong>
                      <span style={{ 
                        background: scenarioData.avg_delta < 0 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)', 
                        color: scenarioData.avg_delta < 0 ? '#ef4444' : '#10b981', 
                        padding: '0.2rem 0.5rem', 
                        borderRadius: '4px',
                        fontWeight: 'bold',
                        fontSize: '0.8rem'
                      }}>
                        Rata-rata Dampak: {scenarioData.avg_delta > 0 ? `+${scenarioData.avg_delta}` : scenarioData.avg_delta} poin
                      </span>
                    </div>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                      {scenarioData.summary}
                    </p>
                  </div>
                )}

                {/* Weight Customizer Toggle */}
                <div 
                  className="weights-panel-toggle"
                  onClick={() => setShowWeightsPanel(!showWeightsPanel)}
                >
                  <span>⚙️ CUSTOMIZE SCORING WEIGHTS</span>
                  <span>{showWeightsPanel ? '▲ HIDE' : '▼ SHOW'}</span>
                </div>
                
                {showWeightsPanel && (
                  <div className="weights-panel">
                    <div className="preset-buttons">
                      <button 
                        className={`btn-preset ${
                          watchlistWeights.technical === 0.30 && watchlistWeights.fundamental === 0.25 ? 'active' : ''
                        }`}
                        onClick={() => applyPreset("balanced")}
                      >
                        Balanced Preset
                      </button>
                      <button 
                        className={`btn-preset ${watchlistWeights.technical === 0.50 ? 'active' : ''}`}
                        onClick={() => applyPreset("technical")}
                      >
                        Technical Preset
                      </button>
                      <button 
                        className={`btn-preset ${watchlistWeights.fundamental === 0.45 ? 'active' : ''}`}
                        onClick={() => applyPreset("fundamental")}
                      >
                        Fundamental Preset
                      </button>
                      <button 
                        className={`btn-preset ${watchlistWeights.technical === 0.40 && watchlistWeights.catalyst === 0.20 ? 'active' : ''}`}
                        onClick={() => applyPreset("momentum")}
                      >
                        Momentum Preset
                      </button>
                    </div>
                    
                    <div className="weight-slider-row">
                      <div className="weight-slider-header">
                        <span>Technical Analysis (Trend/Momentum)</span>
                        <span>{Math.round(watchlistWeights.technical * 100)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        className="slider-input"
                        value={watchlistWeights.technical}
                        onChange={(e) => setWatchlistWeights({
                          ...watchlistWeights,
                          technical: parseFloat(e.target.value)
                        })}
                      />
                    </div>
                    
                    <div className="weight-slider-row">
                      <div className="weight-slider-header">
                        <span>Fundamental Analysis (Valuation/Quality)</span>
                        <span>{Math.round(watchlistWeights.fundamental * 100)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        className="slider-input"
                        value={watchlistWeights.fundamental}
                        onChange={(e) => setWatchlistWeights({
                          ...watchlistWeights,
                          fundamental: parseFloat(e.target.value)
                        })}
                      />
                    </div>
                    
                    <div className="weight-slider-row">
                      <div className="weight-slider-header">
                        <span>Market Sentiment (Broker Summary/News)</span>
                        <span>{Math.round(watchlistWeights.sentiment * 100)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        className="slider-input"
                        value={watchlistWeights.sentiment}
                        onChange={(e) => setWatchlistWeights({
                          ...watchlistWeights,
                          sentiment: parseFloat(e.target.value)
                        })}
                      />
                    </div>
                    
                    <div className="weight-slider-row">
                      <div className="weight-slider-header">
                        <span>Risk Metrics (Volatility/Drawdown)</span>
                        <span>{Math.round(watchlistWeights.risk * 100)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        className="slider-input"
                        value={watchlistWeights.risk}
                        onChange={(e) => setWatchlistWeights({
                          ...watchlistWeights,
                          risk: parseFloat(e.target.value)
                        })}
                      />
                    </div>
                    
                    <div className="weight-slider-row">
                      <div className="weight-slider-header">
                        <span>Upcoming Catalysts (Earnings/Corporate Actions)</span>
                        <span>{Math.round(watchlistWeights.catalyst * 100)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        className="slider-input"
                        value={watchlistWeights.catalyst}
                        onChange={(e) => setWatchlistWeights({
                          ...watchlistWeights,
                          catalyst: parseFloat(e.target.value)
                        })}
                      />
                    </div>
                    
                    <div className="weights-footer">
                      <span>Total: {Math.round(
                        (watchlistWeights.technical + 
                         watchlistWeights.fundamental + 
                         watchlistWeights.sentiment + 
                         watchlistWeights.risk + 
                         watchlistWeights.catalyst) * 100
                      )}% (Target: 100%)</span>
                      <button 
                        className="btn-save-weights"
                        onClick={handleSaveWeights}
                      >
                        SAVE WEIGHTS
                      </button>
                    </div>
                  </div>
                )}
                
                {/* Watchlist Layout Grid */}
                <div className="watchlist-layout">
                  {/* Left Column: Stocks Table */}
                  <div className="table-responsive">
                    {!Array.isArray(watchlistItems) || watchlistItems.length === 0 ? (
                      <p className="no-data">No stocks in this watchlist. Search and add above.</p>
                    ) : (
                      <table className="pred-table">
                        <thead>
                          <tr>
                            <th>Ticker</th>
                            <th>Close Price</th>
                            <th>AI Score</th>
                            <th>Class</th>
                            <th>Bandarologi</th>
                            <th>Aksi</th>
                          </tr>
                        </thead>
                        <tbody>
                          {watchlistItems.map((item) => {
                            const dynScore = getCompositeScore(item);
                            const isSelected = selectedWatchlistItem && item.ticker === selectedWatchlistItem.ticker;
                            
                            // Scenario override
                            const scItem = selectedScenario !== 'normal' && scenarioData?.data?.find(s => s.ticker === item.ticker);
                            const activeScore = scItem ? scItem.scenario_score : dynScore;
                            const dynClass = getClassification(activeScore);
                            
                            return (
                              <tr 
                                key={item.ticker}
                                className={isSelected ? 'active-row' : ''}
                                onClick={() => {
                                  setSelectedWatchlistItem(item);
                                  setSelectedTicker(item.ticker);
                                }}
                                style={{ cursor: 'pointer' }}
                              >
                                <td className="ticker-col">
                                  <div style={{ display: 'flex', alignItems: 'center' }}>
                                    <input 
                                      type="checkbox"
                                      checked={compareTickers.includes(item.ticker)}
                                      onChange={(e) => {
                                        if (e.target.checked) {
                                          if (compareTickers.length >= 3) {
                                            alert("Maksimal bandingkan 3 saham sekaligus!");
                                            return;
                                          }
                                          setCompareTickers([...compareTickers, item.ticker]);
                                        } else {
                                          setCompareTickers(compareTickers.filter(t => t !== item.ticker));
                                        }
                                      }}
                                      onClick={(e) => e.stopPropagation()}
                                      style={{ marginRight: '0.6rem', accentColor: 'var(--primary-glow)', cursor: 'pointer' }}
                                    />
                                    <div>
                                      <span style={{ fontWeight: 'bold' }}>{item.ticker}</span>
                                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>
                                        {item.name}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td>Rp {Number(item.price).toLocaleString('id-ID')}</td>
                                <td style={{ color: 'var(--primary-glow)', fontWeight: 'bold' }}>
                                  {activeScore}
                                  {scItem && (
                                    <span style={{ 
                                      marginLeft: '0.4rem', 
                                      fontSize: '0.75rem', 
                                      fontWeight: 'bold', 
                                      color: scItem.delta < 0 ? '#ef4444' : scItem.delta > 0 ? '#10b981' : '#8b9bb4' 
                                    }}>
                                      ({scItem.delta > 0 ? `+${scItem.delta}` : scItem.delta})
                                    </span>
                                  )}
                                </td>
                                <td>
                                  <span className={`score-badge score-badge-${dynClass.toLowerCase()}`}>
                                    {dynClass}
                                  </span>
                                </td>
                                <td>
                                  {item.bandarologi_status ? (
                                    <span className={`badge badge-bandarologi status-${item.bandarologi_status.toLowerCase().replace(' ', '-')}`}>
                                      {item.bandarologi_status}
                                    </span>
                                  ) : (
                                    <span className="text-gray-500 text-xs">-</span>
                                  )}
                                </td>
                                <td>
                                  <div style={{ display: 'flex', gap: '0.3rem', alignItems: 'center' }}>
                                    <button 
                                      className="btn-preset active" 
                                      style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', background: '#10b981', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setTradeTicker(item.ticker);
                                        setTradeAction("BUY");
                                        setTradeQty(100);
                                        setTradeError("");
                                        setTradeSuccess("");
                                        setShowTradeModal(true);
                                      }}
                                    >
                                      Beli
                                    </button>
                                    <button 
                                      className="btn-preset active" 
                                      style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', background: '#ef4444', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setTradeTicker(item.ticker);
                                        setTradeAction("SELL");
                                        setTradeQty(100);
                                        setTradeError("");
                                        setTradeSuccess("");
                                        setShowTradeModal(true);
                                      }}
                                    >
                                      Jual
                                    </button>
                                    <button 
                                      className="btn-icon delete" 
                                      style={{ padding: '0.3rem 0.5rem', fontSize: '0.8rem', marginLeft: '0.2rem' }}
                                      title="Delete from Watchlist"
                                      onClick={(e) => handleDeleteStock(item.ticker, e)}
                                    >
                                      🗑️
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    )}
                  </div>
                  
                  {/* Right Column: Score Details Breakdown */}
                  <div>
                    {selectedWatchlistItem ? (() => {
                      const scItem = selectedScenario !== 'normal' && scenarioData?.data?.find(s => s.ticker === selectedWatchlistItem.ticker);
                      const currentCompScore = scItem ? scItem.scenario_score : getCompositeScore(selectedWatchlistItem);
                      const currentCompClass = getClassification(currentCompScore);
                      
                      return (
                        <div className="detail-panel">
                          <div className="detail-header-card" style={{ borderTop: scItem ? '3px solid #ef4444' : 'none' }}>
                            <div className="detail-ticker">{selectedWatchlistItem.ticker}</div>
                            <div className="detail-name">{selectedWatchlistItem.name}</div>
                            <div className="detail-composite-score">
                              {currentCompScore}
                              {scItem && (
                                <span style={{ fontSize: '1rem', color: scItem.delta < 0 ? '#ef4444' : '#10b981', marginLeft: '0.5rem' }}>
                                  ({scItem.delta > 0 ? `+${scItem.delta}` : scItem.delta})
                                </span>
                              )}
                            </div>
                            <span className={`score-badge score-badge-${currentCompClass.toLowerCase()}`}>
                              {currentCompClass}
                            </span>
                            {scItem && (
                              <div style={{ marginTop: '0.8rem', color: '#fca5a5', fontSize: '0.75rem', lineHeight: '1.4', background: 'rgba(239, 68, 68, 0.1)', padding: '0.5rem', borderRadius: '4px', textAlign: 'left' }}>
                                <strong>DAMPAK STRESS TEST:</strong><br />
                                {scItem.impact}
                              </div>
                            )}
                          </div>
                          
                          {/* Factor Score Cards */}
                          {Object.entries({
                            technical: { label: "Technical Score (30%)", icon: "📊" },
                            fundamental: { label: "Fundamental Score (25%)", icon: "🏢" },
                            sentiment: { label: "Sentiment Score (15%)", icon: "💬" },
                            risk: { label: "Risk Score (15%)", icon: "⚠️" },
                            catalyst: { label: "Catalyst Score (15%)", icon: "🚀" }
                          }).map(([key, info]) => {
                            const baseScore = selectedWatchlistItem[`${key}_score`] || 50.0;
                            const adjScore = scItem ? scItem.breakdown[key]?.adjusted : baseScore;
                            const details = selectedWatchlistItem.details?.[key]?.details || {};
                            
                            return (
                              <div key={key} className="factor-card">
                                <div className="factor-card-header">
                                  <span>{info.icon} {info.label}</span>
                                  <span>
                                    {baseScore}
                                    {baseScore !== adjScore && (
                                      <span style={{ color: adjScore < baseScore ? '#ef4444' : '#10b981', fontSize: '0.8rem', marginLeft: '0.4rem', fontWeight: 'bold' }}>
                                        → {adjScore}
                                      </span>
                                    )}
                                  </span>
                                </div>
                                <div className="progress-bar-bg" style={{ marginBottom: '0.5rem' }}>
                                  <div 
                                    className="progress-bar-fill" 
                                    style={{ 
                                      width: `${adjScore}%`,
                                      background: adjScore >= 80 ? '#10b981' : adjScore >= 60 ? '#3b82f6' : adjScore >= 40 ? '#9ca3af' : '#ef4444'
                                    }}
                                  ></div>
                                </div>
                                <div className="factor-card-details">
                                  {Object.entries(details).map(([k, v]) => (
                                    <div key={k}>
                                      <strong>{k.replace('_', ' ').toUpperCase()}:</strong> {v}
                                    </div>
                                  ))}
                                  {Object.keys(details).length === 0 && (
                                    <div>No breakdown data available.</div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      );
                    })() : (
                      <div className="detail-panel" style={{ opacity: 0.5, textAlign: 'center', padding: '2rem 0' }}>
                        <p>Select a stock from the table to view its detailed AI Score Breakdown.</p>
                      </div>
                    )}
                  </div>
                </div>
                {/* Side-by-Side Comparison Panel */}
                {compareData.length >= 2 && (
                  <div className="glass-panel" style={{ marginTop: '2rem', animation: 'fadeIn 0.3s ease', width: '100%', gridColumn: 'span 2' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                      <h2 style={{ margin: 0 }}>Side-by-Side Stock Comparison</h2>
                      <button 
                        className="btn-preset" 
                        onClick={() => setCompareTickers([])}
                        style={{ width: 'auto', padding: '0.4rem 1rem', background: 'rgba(255,255,255,0.05)', color: '#fff', border: '1px solid var(--glass-border)', borderRadius: '4px', cursor: 'pointer' }}
                      >
                        Clear Comparison
                      </button>
                    </div>
                    <div className="table-responsive">
                      <table className="pred-table" style={{ textAlign: 'center' }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: 'left' }}>Metric / Factor</th>
                            {compareData.map(c => (
                              <th key={c.ticker} style={{ fontSize: '1.1rem', color: 'var(--primary-glow)' }}>
                                {c.ticker}
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>{c.name}</div>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td style={{ fontWeight: 'bold', textAlign: 'left' }}>Price</td>
                            {compareData.map(c => <td key={c.ticker}>Rp {Number(c.price).toLocaleString('id-ID')}</td>)}
                          </tr>
                          <tr>
                            <td style={{ fontWeight: 'bold', textAlign: 'left' }}>AI Composite Score</td>
                            {compareData.map(c => (
                              <td key={c.ticker} style={{ fontWeight: 'bold', fontSize: '1.05rem', color: 'var(--secondary-glow)' }}>
                                {c.total_score} ({c.classification})
                              </td>
                            ))}
                          </tr>
                          {["Technical", "Fundamental", "Sentiment", "Risk", "Catalyst"].map(factor => (
                            <tr key={factor}>
                              <td style={{ fontWeight: 'bold', textAlign: 'left' }}>{factor} Score</td>
                              {compareData.map(c => {
                                const val = c[`${factor.toLowerCase()}_score`];
                                return (
                                  <td key={c.ticker}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                      <span style={{ fontWeight: 'bold', width: '30px' }}>{val}</span>
                                      <div className="progress-bar-bg" style={{ width: '80px', height: '6px', margin: 0 }}>
                                        <div 
                                          className="progress-bar-fill" 
                                          style={{ 
                                            width: `${val}%`, 
                                            background: val >= 80 ? '#10b981' : val >= 60 ? '#3b82f6' : val >= 40 ? '#9ca3af' : '#ef4444' 
                                          }}
                                        />
                                      </div>
                                    </div>
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                          <tr>
                            <td style={{ fontWeight: 'bold', textAlign: 'left' }}>Valuation (PER)</td>
                            {compareData.map(c => <td key={c.ticker}>{c.details?.fundamental?.details?.valuation || '-'}</td>)}
                          </tr>
                          <tr>
                            <td style={{ fontWeight: 'bold', textAlign: 'left' }}>Profitability (ROE)</td>
                            {compareData.map(c => <td key={c.ticker}>{c.details?.fundamental?.details?.profitability || '-'}</td>)}
                          </tr>
                          <tr>
                            <td style={{ fontWeight: 'bold', textAlign: 'left' }}>30d Max Drawdown</td>
                            {compareData.map(c => <td key={c.ticker} style={{ color: '#ef4444' }}>{c.details?.risk?.details?.drawdown || '-'}</td>)}
                          </tr>
                          <tr>
                            <td style={{ fontWeight: 'bold', textAlign: 'left' }}>Sector Shock Sensitivity</td>
                            {compareData.map(c => (
                              <td key={c.ticker} style={{ fontSize: '0.8rem', color: 'var(--text-muted)', maxWidth: '200px', lineHeight: '1.4' }}>
                                <strong>{c.sector}</strong><br />
                                {
                                  c.sector.toLowerCase() === 'technology' || c.sector.toLowerCase() === 'properties' || c.sector.toLowerCase() === 'property' ? 'Tinggi (Sensitif suku bunga)' :
                                  c.sector.toLowerCase() === 'financials' || c.sector.toLowerCase() === 'finance' || c.sector.toLowerCase() === 'financial' ? 'Rendah (Resilien / NIM Buffers)' :
                                  'Menengah / Netral'
                                }
                              </td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {activeTab === 'portfolio' && (
          <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '1.5rem', animation: 'fadeIn 0.3s ease' }}>
            {/* Summary Cards */}
            {portfolio && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                <div className="glass-panel" style={{ textAlign: 'center', padding: '1.2rem' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>TOTAL PORTFOLIO VALUE</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--primary-glow)', marginTop: '0.5rem' }}>
                    Rp {portfolio.total_value?.toLocaleString('id-ID')}
                  </div>
                </div>
                <div className="glass-panel" style={{ textAlign: 'center', padding: '1.2rem' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>CASH BALANCE (IDR)</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#fff', marginTop: '0.5rem' }}>
                    Rp {portfolio.cash?.toLocaleString('id-ID')}
                  </div>
                </div>
                <div className="glass-panel" style={{ textAlign: 'center', padding: '1.2rem' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>UNREALIZED P&L</div>
                  <div style={{ 
                    fontSize: '1.5rem', 
                    fontWeight: 'bold', 
                    color: portfolio.unrealized_pnl >= 0 ? '#10b981' : '#ef4444', 
                    marginTop: '0.5rem' 
                  }}>
                    Rp {portfolio.unrealized_pnl >= 0 ? '+' : ''}{portfolio.unrealized_pnl?.toLocaleString('id-ID')}
                  </div>
                </div>
                <div className="glass-panel" style={{ textAlign: 'center', padding: '1.2rem' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>REALIZED P&L</div>
                  <div style={{ 
                    fontSize: '1.5rem', 
                    fontWeight: 'bold', 
                    color: portfolio.realized_pnl >= 0 ? '#10b981' : '#ef4444', 
                    marginTop: '0.5rem' 
                  }}>
                    Rp {portfolio.realized_pnl >= 0 ? '+' : ''}{portfolio.realized_pnl?.toLocaleString('id-ID')}
                  </div>
                </div>
                <div className="glass-panel" style={{ textAlign: 'center', padding: '1.2rem' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>WIN-RATE (CLOSED)</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#a855f7', marginTop: '0.5rem' }}>
                    {portfolio.win_rate}% ({portfolio.total_trades} Trades)
                  </div>
                </div>
              </div>
            )}

            {/* Holdings & Transaction Log */}
            <div className="learning-top-grid" style={{ gridTemplateColumns: '2fr 1.2fr', gap: '1.5rem' }}>
              {/* Current Holdings */}
              <div className="glass-panel" style={{ minHeight: '350px' }}>
                <h2>Current Holdings</h2>
                {!portfolio || portfolio.holdings.length === 0 ? (
                  <p className="no-data" style={{ padding: '4rem 0', textAlign: 'center' }}>
                    No stocks in virtual portfolio. Use Screener or Watchlist tables to BUY virtual shares!
                  </p>
                ) : (
                  <div className="table-responsive">
                    <table className="pred-table">
                      <thead>
                        <tr>
                          <th>Ticker</th>
                          <th>Shares</th>
                          <th>Avg Buy</th>
                          <th>Price</th>
                          <th>Market Value</th>
                          <th>PnL</th>
                          <th>Trade</th>
                        </tr>
                      </thead>
                      <tbody>
                        {portfolio.holdings.map(item => (
                          <tr key={item.ticker}>
                            <td className="ticker-col">
                              <span style={{ fontWeight: 'bold' }}>{item.ticker}</span>
                              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>
                                {item.name}
                              </div>
                            </td>
                            <td>{item.quantity?.toLocaleString('id-ID')}</td>
                            <td>Rp {item.avg_buy_price?.toLocaleString('id-ID')}</td>
                            <td>Rp {item.current_price?.toLocaleString('id-ID')}</td>
                            <td>Rp {item.market_value?.toLocaleString('id-ID')}</td>
                            <td style={{ color: item.unrealized_pnl >= 0 ? '#10b981' : '#ef4444', fontWeight: 'bold' }}>
                              Rp {item.unrealized_pnl >= 0 ? '+' : ''}{item.unrealized_pnl?.toLocaleString('id-ID')}<br/>
                              <span style={{ fontSize: '0.75rem' }}>({item.unrealized_pnl_percent}%)</span>
                            </td>
                            <td>
                              <div style={{ display: 'flex', gap: '0.3rem' }}>
                                <button 
                                  className="btn-preset active" 
                                  style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem', background: '#10b981', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                                  onClick={() => {
                                    setTradeTicker(item.ticker);
                                    setTradeAction("BUY");
                                    setTradeQty(100);
                                    setTradeError("");
                                    setTradeSuccess("");
                                    setShowTradeModal(true);
                                  }}
                                >
                                  Beli
                                </button>
                                <button 
                                  className="btn-preset active" 
                                  style={{ padding: '0.3rem 0.5rem', fontSize: '0.75rem', background: '#ef4444', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                                  onClick={() => {
                                    setTradeTicker(item.ticker);
                                    setTradeAction("SELL");
                                    setTradeQty(100);
                                    setTradeError("");
                                    setTradeSuccess("");
                                    setShowTradeModal(true);
                                  }}
                                >
                                  Jual
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Transaction Logs */}
              <div className="glass-panel" style={{ minHeight: '350px' }}>
                <h2>Transaction Logs</h2>
                {!portfolio || portfolio.transactions.length === 0 ? (
                  <p className="no-data" style={{ padding: '4rem 0', textAlign: 'center' }}>No transactions recorded.</p>
                ) : (
                  <div className="table-responsive" style={{ maxHeight: '350px', overflowY: 'auto' }}>
                    <table className="pred-table" style={{ fontSize: '0.8rem' }}>
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Order</th>
                          <th>Price</th>
                          <th>Qty</th>
                        </tr>
                      </thead>
                      <tbody>
                        {portfolio.transactions.map((tx, idx) => (
                          <tr key={idx}>
                            <td>{tx.date.substring(5, 16)}</td>
                            <td style={{ color: tx.action === 'BUY' ? '#00d2ff' : '#ef4444', fontWeight: 'bold' }}>
                              {tx.action} {tx.ticker}
                            </td>
                            <td>Rp {tx.price?.toLocaleString('id-ID')}</td>
                            <td>{tx.quantity?.toLocaleString('id-ID')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'learning' && (
          /* Learning Engine Panel */
          <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '1.5rem', animation: 'fadeIn 0.3s ease' }}>
            {/* Top Grid: Regime and Retraining Monitor */}
            <div className="learning-top-grid">
              {/* Regime Monitor */}
              <div className="glass-panel">
                <h2>Market Regime Monitor</h2>
                <div className="regime-content">
                  <div className="regime-badge-container">
                    <span className={`regime-badge ${(learningRegime.current?.regime || 'Sideways').toLowerCase().replace(' ', '-')}`}>
                      {learningRegime.current?.regime || 'Sideways'}
                    </span>
                    <span className="regime-sub-badge">{learningRegime.current?.flow || 'Risk-Off'}</span>
                  </div>
                  
                  <div className="regime-stats-grid">
                    <div className="regime-stat-item">
                      <span className="stat-label">IHSG Breadth</span>
                      <span className="stat-value">{learningRegime.current?.breadth || 0}%</span>
                    </div>
                    <div className="regime-stat-item">
                      <span className="stat-label">Market Volatility</span>
                      <span className="stat-value">{learningRegime.current?.volatility || 'Normal'}</span>
                    </div>
                    <div className="regime-stat-item">
                      <span className="stat-label">IHSG Close</span>
                      <span className="stat-value">{Number(learningRegime.current?.ihsg_close || 0).toLocaleString('id-ID')}</span>
                    </div>
                    <div className="regime-stat-item">
                      <span className="stat-label">IHSG SMA50</span>
                      <span className="stat-value">{Number(learningRegime.current?.ihsg_sma50 || 0).toLocaleString('id-ID')}</span>
                    </div>
                  </div>
                  
                  <div className="regime-description">
                    {learningRegime.current?.regime === 'Bull Market' && "Pasar dalam kondisi Bullish (Risk-On). Tren didominasi oleh kenaikan harga IHSG di atas rata-rata 50 dan 200 hari, serta partisipasi pasar (breadth) yang luas. Strategi: Aggressive Buying / Momentum Trading."}
                    {learningRegime.current?.regime === 'Bear Market' && "Pasar dalam kondisi Bearish (Risk-Off). IHSG berada di bawah SMA50 dan SMA200 dengan partisipasi pasar yang rendah. Strategi: Capital Preservation / Short Selling / Cash-Heavy."}
                    {learningRegime.current?.regime === 'Correction' && "Pasar mengalami koreksi jangka pendek. Tekanan jual meningkat namun tren jangka panjang masih berpotensi bertahan. Strategi: Buy on Weakness / Defensive Stocks."}
                    {learningRegime.current?.regime === 'Sideways' && "Pasar bergerak konsolidasi tanpa tren arah yang jelas. Pergerakan harga terbatas dalam range tertentu. Strategi: Swing Trading / Range Trading."}
                    {!learningRegime.current?.regime && "Menghitung kondisi pasar saat ini..."}
                  </div>
                </div>
              </div>

              {/* Auto-Retrain Monitor */}
              <div className="glass-panel">
                <h2>Auto-Retraining Monitor</h2>
                <div className="retrain-status-box">
                  <div className="status-row">
                    <span>Rolling 5-Day Accuracy</span>
                    <span style={{ 
                      color: (learningPerf.slice(-5).reduce((sum, item) => sum + (item.hit_rate || 0), 0) / Math.max(1, learningPerf.slice(-5).length)) < 52.0 && learningPerf.slice(-5).length >= 5 ? '#ef4444' : '#10b981', 
                      fontWeight: 'bold' 
                    }}>
                      {(learningPerf.slice(-5).reduce((sum, item) => sum + (item.hit_rate || 0), 0) / Math.max(1, learningPerf.slice(-5).length)).toFixed(2)}%
                    </span>
                  </div>
                  <div className="status-row">
                    <span>Retrain Trigger Threshold</span>
                    <span>&lt; 52.00%</span>
                  </div>
                  <div className="status-row">
                    <span>Engine Health</span>
                    <span style={{ 
                      color: (learningPerf.slice(-5).reduce((sum, item) => sum + (item.hit_rate || 0), 0) / Math.max(1, learningPerf.slice(-5).length)) < 52.0 && learningPerf.slice(-5).length >= 5 ? '#ef4444' : '#10b981', 
                      fontWeight: 'bold' 
                    }}>
                      {(learningPerf.slice(-5).reduce((sum, item) => sum + (item.hit_rate || 0), 0) / Math.max(1, learningPerf.slice(-5).length)) < 52.0 && learningPerf.slice(-5).length >= 5 ? 'Degraded (Action Required)' : 'Healthy'}
                    </span>
                  </div>
                  <div className="status-row">
                    <span>Retrain Engine Status</span>
                    <span className={`status-badge ${
                      retrainStatus.includes('successful') || retrainStatus === 'Idle' ? 'status-success' : 
                      retrainStatus.includes('failed') ? 'status-failed' : 'status-running'
                    }`}>
                      {retrainStatus}
                    </span>
                  </div>
                  <button 
                    className={`btn-update ${isRetraining ? 'running' : ''}`}
                    onClick={handleTriggerRetrain}
                    disabled={isRetraining}
                    style={{ marginTop: '0.5rem', width: '100%' }}
                  >
                    {isRetraining ? 'Retraining AI Models...' : 'TRIGGER MANUAL RETRAINING'}
                  </button>
                </div>
              </div>
            </div>

            {/* Bottom Grid: SVG Accuracy Chart and Feature Weights & Logs */}
            <div className="learning-bottom-grid">
              {/* Performance Trends Panel */}
              <div className="glass-panel">
                <h2>AI Prediction Accuracy Trends (Last 30 Days)</h2>
                {(() => {
                  if (!Array.isArray(learningPerf) || learningPerf.length === 0) {
                    return <div className="no-data">Loading performance trends...</div>;
                  }
                  
                  const width = 600;
                  const height = 220;
                  const paddingLeft = 45;
                  const paddingRight = 20;
                  const paddingTop = 20;
                  const paddingBottom = 30;
                  
                  const chartWidth = width - paddingLeft - paddingRight;
                  const chartHeight = height - paddingTop - paddingBottom;
                  
                  const hitRates = learningPerf.map(d => d.hit_rate || 0);
                  const precisions = learningPerf.map(d => d.precision_at_10 || 0);
                  const allValues = [...hitRates, ...precisions];
                  
                  let minY = Math.min(...allValues);
                  let maxY = Math.max(...allValues);
                  
                  minY = Math.max(0, Math.floor(minY - 5));
                  maxY = Math.min(100, Math.ceil(maxY + 5));
                  if (maxY === minY) {
                    minY = 0;
                    maxY = 100;
                  }
                  
                  const getX = (idx) => {
                    if (learningPerf.length <= 1) return paddingLeft + chartWidth / 2;
                    return paddingLeft + (idx / (learningPerf.length - 1)) * chartWidth;
                  };
                  
                  const getY = (val) => {
                    return height - paddingBottom - ((val - minY) / (maxY - minY)) * chartHeight;
                  };
                  
                  let hitRatePath = '';
                  let precisionPath = '';
                  
                  learningPerf.forEach((d, idx) => {
                    const x = getX(idx);
                    const yHit = getY(d.hit_rate || 0);
                    const yPrec = getY(d.precision_at_10 || 0);
                    
                    if (idx === 0) {
                      hitRatePath = `M ${x} ${yHit}`;
                      precisionPath = `M ${x} ${yPrec}`;
                    } else {
                      hitRatePath += ` L ${x} ${yHit}`;
                      precisionPath += ` L ${x} ${yPrec}`;
                    }
                  });
                  
                  const gridLines = [];
                  const steps = 4;
                  for (let i = 0; i <= steps; i++) {
                    const val = minY + (i / steps) * (maxY - minY);
                    const y = getY(val);
                    gridLines.push(
                      <g key={i}>
                        <line 
                          x1={paddingLeft} 
                          y1={y} 
                          x2={width - paddingRight} 
                          y2={y} 
                          stroke="rgba(255, 255, 255, 0.05)" 
                          strokeWidth="1" 
                        />
                        <text 
                          x={paddingLeft - 10} 
                          y={y + 4} 
                          fill="#8b9bb4" 
                          fontSize="10" 
                          textAnchor="end"
                        >
                          {Math.round(val)}%
                        </text>
                      </g>
                    );
                  }
                  
                  const dateLabels = [];
                  const labelInterval = Math.max(1, Math.floor(learningPerf.length / 5));
                  learningPerf.forEach((d, idx) => {
                    if (idx % labelInterval === 0 || idx === learningPerf.length - 1) {
                      const x = getX(idx);
                      const displayDate = d.date.substring(5);
                      dateLabels.push(
                        <text 
                          key={idx} 
                          x={x} 
                          y={height - 10} 
                          fill="#8b9bb4" 
                          fontSize="9" 
                          textAnchor="middle"
                        >
                          {displayDate}
                        </text>
                      );
                    }
                  });
                  
                  return (
                    <div className="svg-chart-container" style={{ position: 'relative' }}>
                      <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
                        {gridLines}
                        {dateLabels}
                        
                        {/* Hit Rate Line */}
                        <path 
                          d={hitRatePath} 
                          fill="none" 
                          stroke="rgba(0, 210, 255, 0.2)" 
                          strokeWidth="6" 
                          strokeLinecap="round" 
                          strokeLinejoin="round" 
                        />
                        <path 
                          d={hitRatePath} 
                          fill="none" 
                          stroke="var(--primary-glow)" 
                          strokeWidth="2.5" 
                          strokeLinecap="round" 
                          strokeLinejoin="round" 
                        />
                        
                        {/* Precision Line */}
                        <path 
                          d={precisionPath} 
                          fill="none" 
                          stroke="rgba(168, 85, 247, 0.2)" 
                          strokeWidth="5" 
                          strokeLinecap="round" 
                          strokeLinejoin="round" 
                        />
                        <path 
                          d={precisionPath} 
                          fill="none" 
                          stroke="#a855f7" 
                          strokeWidth="2" 
                          strokeLinecap="round" 
                          strokeLinejoin="round" 
                        />
                        
                        {learningPerf.length > 0 && (
                          <g>
                            <circle 
                              cx={getX(learningPerf.length - 1)} 
                              cy={getY(learningPerf[learningPerf.length - 1].hit_rate || 0)} 
                              r="4" 
                              fill="var(--primary-glow)" 
                            />
                            <circle 
                              cx={getX(learningPerf.length - 1)} 
                              cy={getY(learningPerf[learningPerf.length - 1].precision_at_10 || 0)} 
                              r="4" 
                              fill="#a855f7" 
                            />
                          </g>
                        )}
                      </svg>
                      
                      <div className="chart-legend">
                        <div className="legend-item">
                          <span className="legend-dot" style={{ background: 'var(--primary-glow)' }} />
                          <span>Directional Hit Rate (Rolling)</span>
                        </div>
                        <div className="legend-item">
                          <span className="legend-dot" style={{ background: '#a855f7' }} />
                          <span>Precision @ 10 (Accuracy)</span>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Feature Importance & Retraining Log */}
              <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <div>
                  <h2>Model Feature Importance</h2>
                  <div className="feature-bars-container">
                    {featureImportances.slice(0, 5).map((item, idx) => (
                      <div key={idx} className="feature-bar-row">
                        <div className="feature-bar-label">
                          <span>{item.feature.toUpperCase()}</span>
                          <span>{item.importance}%</span>
                        </div>
                        <div className="progress-bar-bg" style={{ height: '8px' }}>
                          <div 
                            className="progress-bar-fill" 
                            style={{ 
                              width: `${item.importance * 3}%`,
                              maxWidth: '100%',
                              background: 'linear-gradient(90deg, var(--secondary-glow), var(--primary-glow))'
                            }}
                          />
                        </div>
                      </div>
                    ))}
                    {featureImportances.length === 0 && (
                      <div className="no-data">No feature importances loaded. Train a model to see feature weights.</div>
                    )}
                  </div>
                </div>

                <hr style={{ border: 'none', borderTop: '1px solid var(--glass-border)', margin: '0' }} />

                <div>
                  <h2>Model Retraining Logs</h2>
                  <div className="table-responsive" style={{ maxHeight: '150px', overflowY: 'auto' }}>
                    <table className="pred-table" style={{ fontSize: '0.8rem' }}>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Status</th>
                          <th>Accuracy</th>
                          <th>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {retrainHistory.slice(0, 5).map((run, idx) => (
                          <tr key={idx}>
                            <td>{new Date(run.timestamp).toLocaleDateString('id-ID')}</td>
                            <td>
                              <span className={`status-badge ${run.status === 'success' ? 'status-success' : run.status === 'failed' ? 'status-failed' : 'status-running'}`}>
                                {run.status.toUpperCase()}
                              </span>
                            </td>
                            <td>{run.test_accuracy}%</td>
                            <td>
                              {run.is_champion ? (
                                <span className="badge-champion">CHAMPION</span>
                              ) : (
                                <span className="badge-challenger">CHALLENGER</span>
                              )}
                            </td>
                          </tr>
                        ))}
                        {retrainHistory.length === 0 && (
                          <tr>
                            <td colSpan="4" className="no-data" style={{ textAlign: 'center' }}>No retraining logs found.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Chart Panel */}
      {selectedTicker && (
        <div className="glass-panel chart-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.2rem' }}>
            <h2 style={{ margin: 0 }}>{selectedTicker} - Historical Chart</h2>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.85rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', color: '#8b9bb4' }}>
                <input 
                  type="checkbox" 
                  checked={showSmaOverlay} 
                  onChange={(e) => setShowSmaOverlay(e.target.checked)}
                  style={{ accentColor: 'var(--primary-glow)', cursor: 'pointer' }}
                />
                Show SMA Overlay (5, 20, 50)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', color: '#8b9bb4' }}>
                <input 
                  type="checkbox" 
                  checked={showBbandsOverlay} 
                  onChange={(e) => setShowBbandsOverlay(e.target.checked)}
                  style={{ accentColor: 'var(--primary-glow)', cursor: 'pointer' }}
                />
                Show Bollinger Bands
              </label>
            </div>
          </div>
          <div className="chart-layout-wrapper" style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr', gap: '1.5rem', minHeight: '400px' }}>
            <div ref={chartContainerRef} className="chart-container" style={{ width: '100%', height: '100%' }} />
            
            {/* Bandarologi Sidebar details panel */}
            <div className="bandarologi-sidebar-panel" style={{ 
              background: 'rgba(255, 255, 255, 0.01)', 
              borderRadius: '8px', 
              border: '1px solid rgba(255, 255, 255, 0.05)', 
              padding: '1.2rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#fff' }}>Broker Summary (EOD)</h3>
                {bandarData?.acum_status && (
                  <span className={`badge badge-bandarologi status-${bandarData.acum_status.toLowerCase().replace(' ', '-')}`}>
                    {bandarData.acum_status}
                  </span>
                )}
              </div>
              
              <div style={{ display: 'flex', gap: '0.8rem', fontSize: '0.85rem' }}>
                <div style={{ flex: 1, background: 'rgba(0, 210, 255, 0.04)', padding: '0.6rem', borderRadius: '6px', textAlign: 'center' }}>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Accum. Ratio</div>
                  <div style={{ fontWeight: 'bold', color: '#00d2ff', fontSize: '1.1rem', marginTop: '0.2rem' }}>
                    {bandarData?.acum_ratio !== undefined ? `${(bandarData.acum_ratio * 100).toFixed(1)}%` : '0.0%'}
                  </div>
                </div>
                <div style={{ flex: 1, background: 'rgba(16, 185, 129, 0.04)', padding: '0.6rem', borderRadius: '6px', textAlign: 'center' }}>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Net Foreign</div>
                  <div style={{ 
                    fontWeight: 'bold', 
                    color: (bandarData?.net_foreign_value || 0) >= 0 ? '#10b981' : '#ef4444', 
                    fontSize: '1.1rem', 
                    marginTop: '0.2rem' 
                  }}>
                    {bandarData?.net_foreign_value !== undefined 
                      ? `${(bandarData.net_foreign_value / 1_000_000_000).toFixed(2)}B`
                      : '0.00B'
                    }
                  </div>
                </div>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.2rem' }}>
                {/* Top Buyers */}
                <div>
                  <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.8rem', color: '#00d2ff', borderBottom: '1px solid rgba(0, 210, 255, 0.1)', paddingBottom: '0.2rem' }}>Top 5 Buyers</h4>
                  {bandarData?.top_buyers && bandarData.top_buyers.length > 0 ? (
                    bandarData.top_buyers.map((b, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '0.25rem 0' }}>
                        <span style={{ fontWeight: 'bold', color: 'var(--text-muted)' }}>{b.broker}</span>
                        <span style={{ color: '#00d2ff', fontWeight: '500' }}>Rp {(b.net_value / 1_000_000).toFixed(1)}M</span>
                      </div>
                    ))
                  ) : (
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>No buyers data</p>
                  )}
                </div>
                
                {/* Top Sellers */}
                <div>
                  <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.8rem', color: '#ef4444', borderBottom: '1px solid rgba(239, 68, 68, 0.1)', paddingBottom: '0.2rem' }}>Top 5 Sellers</h4>
                  {bandarData?.top_sellers && bandarData.top_sellers.length > 0 ? (
                    bandarData.top_sellers.map((s, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', padding: '0.25rem 0' }}>
                        <span style={{ fontWeight: 'bold', color: 'var(--text-muted)' }}>{s.broker}</span>
                        <span style={{ color: '#ef4444', fontWeight: '500' }}>Rp {Math.abs(s.net_value / 1_000_000).toFixed(1)}M</span>
                      </div>
                    ))
                  ) : (
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>No sellers data</p>
                  )}
                </div>
              </div>
              
              {/* Trend Chart (SVG) */}
              <div style={{ marginTop: '0.4rem', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.8rem' }}>
                <h4 style={{ margin: '0 0 0.4rem 0', fontSize: '0.8rem', color: '#8b9bb4' }}>15-Day Accumulation Score Trend</h4>
                {bandarData?.history && bandarData.history.length > 0 ? (
                  <div style={{ height: '70px', position: 'relative' }}>
                    <svg viewBox="0 0 150 50" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
                      <polyline
                        fill="none"
                        stroke="var(--primary-glow)"
                        strokeWidth="1.5"
                        points={bandarData.history.map((h, i) => `${(i * 10) + 5},${50 - (h.acum_score * 0.4)}`).join(' ')}
                      />
                      {bandarData.history.map((h, i) => (
                        <circle
                          key={i}
                          cx={(i * 10) + 5}
                          cy={50 - (h.acum_score * 0.4)}
                          r="2"
                          fill={h.acum_score > 65 ? '#10b981' : h.acum_score < 40 ? '#ef4444' : '#fff'}
                        />
                      ))}
                    </svg>
                  </div>
                ) : (
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>No trend history available</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Backtest Panel */}
      {activeTab !== 'learning' && (
        <div className="glass-panel backtest-panel" style={{ marginTop: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2>Strategy Backtester (100 Days)</h2>
            <button 
              className={`btn-update ${isBacktesting ? 'running' : ''}`}
              onClick={handleRunBacktest}
              disabled={isBacktesting}
              style={{ width: 'auto', padding: '0.8rem 1.5rem', marginTop: 0 }}
            >
              {isBacktesting ? 'Simulating...' : 'RUN BACKTEST'}
            </button>
          </div>
          
          {!backtestData ? (
            <p className="no-data">Run backtest to simulate historical trading performance.</p>
          ) : (
            <div className="table-responsive">
              <table className="pred-table">
                <thead>
                  <tr>
                    <th>Holding Period</th>
                    <th>Win Rate</th>
                    <th>Total Return</th>
                    <th>Max Drawdown</th>
                  </tr>
                </thead>
                <tbody>
                  {['T+1', 'T+3', 'T+5', 'T+10'].map(horizon => (
                    <tr key={horizon}>
                      <td style={{ fontWeight: 'bold', color: 'var(--primary-glow)' }}>{horizon}</td>
                      <td>{backtestData.metrics[horizon]?.win_rate}%</td>
                      <td style={{ color: backtestData.metrics[horizon]?.total_return > 0 ? '#00d2ff' : '#ff2a2a' }}>
                        {backtestData.metrics[horizon]?.total_return}%
                      </td>
                      <td style={{ color: '#ff2a2a' }}>{backtestData.metrics[horizon]?.max_drawdown}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Trade Modal */}
      {showTradeModal && (
        <div className="modal-overlay" onClick={() => setShowTradeModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontFamily: 'Outfit', color: '#fff', fontSize: '1.25rem' }}>
              Virtual Order: {tradeAction} {tradeTicker}
            </h3>
            {tradeError && (
              <div style={{ color: '#ef4444', background: 'rgba(239, 68, 68, 0.1)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8rem', marginTop: '0.8rem' }}>
                ⚠️ {tradeError}
              </div>
            )}
            {tradeSuccess && (
              <div style={{ color: '#10b981', background: 'rgba(16, 185, 129, 0.1)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8rem', marginTop: '0.8rem' }}>
                ✅ {tradeSuccess}
              </div>
            )}
            <form onSubmit={handleExecuteTrade} style={{ marginTop: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Aksi</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button 
                    type="button" 
                    className={`btn-preset ${tradeAction === 'BUY' ? 'active' : ''}`}
                    onClick={() => setTradeAction('BUY')}
                    style={{ flex: 1, height: '38px', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
                  >
                    BELI (BUY)
                  </button>
                  <button 
                    type="button" 
                    className={`btn-preset ${tradeAction === 'SELL' ? 'active' : ''}`}
                    onClick={() => setTradeAction('SELL')}
                    style={{ flex: 1, height: '38px', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer', color: tradeAction === 'SELL' ? '#ef4444' : '#8b9bb4' }}
                  >
                    JUAL (SELL)
                  </button>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Jumlah Lembar Saham (Shares)</label>
                <input 
                  type="number" 
                  className="form-input" 
                  min="1"
                  required
                  placeholder="Jumlah shares..."
                  value={tradeQty}
                  onChange={(e) => setTradeQty(parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Catatan Transaksi</label>
                <input 
                  type="text" 
                  className="form-input"
                  placeholder="e.g. Swing trade breakout"
                  value={tradeNotes}
                  onChange={(e) => setTradeNotes(e.target.value)}
                />
              </div>
              <div className="modal-actions">
                <button 
                  type="button" 
                  className="btn-secondary"
                  onClick={() => setShowTradeModal(false)}
                >
                  Batal
                </button>
                <button 
                  type="submit" 
                  className="btn-update"
                  style={{ width: 'auto', padding: '0.6rem 1.5rem', marginTop: 0 }}
                >
                  Eksekusi Order
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Create Watchlist Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontFamily: 'Outfit', color: '#fff', fontSize: '1.25rem' }}>Buat Watchlist Baru</h3>
            <form onSubmit={handleCreateWatchlist} style={{ marginTop: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Nama Watchlist</label>
                <input 
                  type="text" 
                  className="form-input" 
                  required
                  placeholder="e.g. Saham LQ45 Pilihan"
                  value={newWatchlistName}
                  onChange={(e) => setNewWatchlistName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Deskripsi</label>
                <textarea 
                  className="form-input"
                  rows="3"
                  placeholder="Deskripsi singkat watchlist..."
                  value={newWatchlistDesc}
                  onChange={(e) => setNewWatchlistDesc(e.target.value)}
                  style={{ resize: 'none' }}
                />
              </div>
              <div className="modal-actions">
                <button 
                  type="button" 
                  className="btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                >
                  Batal
                </button>
                <button 
                  type="submit" 
                  className="btn-update"
                  style={{ width: 'auto', padding: '0.6rem 1.5rem', marginTop: 0 }}
                >
                  Buat
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
