"use client";

import React, { useState, useEffect } from "react";

interface PortfolioData {
  total_capital_usd: number;
  available_capital_usd: number;
  active_exposure_usd: number;
  peak_capital_usd: number;
  daily_drawdown_pct: number;
  total_drawdown_pct: number;
  emergency_halt: boolean;
  open_positions: any[];
}

interface DecisionRecord {
  id: number;
  pair: string;
  timestamp: string;
  action: string;
  confidence: number;
  expected_return_bps: number;
  risk_status: string;
  supporting_evidence: string[];
  contradictory_evidence: string[];
  explanation: string;
}

interface WhaleEventRecord {
  id: number;
  event_type: string;
  asset: string;
  amount: number;
  usd_value: number;
  source: string;
  dest: string;
  signal_bias: string;
  confidence: number;
  timestamp: string;
}

interface MarkedTradeRecord {
  trade_id: string;
  status: string;
  pair: string;
  side: string;
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  take_profit: number;
  stop_loss: number;
  risk_reward: number;
  allocated_usd: number;
  realized_pnl_usd: number;
  realized_pnl_pct: number;
  exit_reason: string;
  thesis_confirmed: string;
  strategy_rationale: string;
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [whales, setWhales] = useState<WhaleEventRecord[]>([]);
  const [markedTrades, setMarkedTrades] = useState<MarkedTradeRecord[]>([]);
  const [selectedPair, setSelectedPair] = useState<string>("BTC");
  const [loading, setLoading] = useState(false);
  const [cycleMsg, setCycleMsg] = useState<string | null>(null);

  const fetchTelemetry = async () => {
    try {
      const portRes = await fetch("http://localhost:8000/api/v1/portfolio");
      if (portRes.ok) setPortfolio(await portRes.json());

      const decRes = await fetch("http://localhost:8000/api/v1/decisions?limit=8");
      if (decRes.ok) setDecisions(await decRes.json());

      const whaleRes = await fetch("http://localhost:8000/api/v1/intelligence/whale?limit=6");
      if (whaleRes.ok) setWhales(await whaleRes.json());

      const tradesRes = await fetch(`http://localhost:8000/api/v1/trades/live-ledger?pair=${selectedPair}`);
      if (tradesRes.ok) setMarkedTrades(await tradesRes.json());
    } catch (err) {
      console.error("Telemetry sync error:", err);
    }
  };

  useEffect(() => {
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 5000);
    return () => clearInterval(interval);
  }, [selectedPair]);

  const triggerCycle = async (symbol: string) => {
    setLoading(true);
    setCycleMsg(`Running full pipeline cycle for ${symbol}...`);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/pipeline/cycle?symbol=${encodeURIComponent(symbol)}`, {
        method: "POST",
      });
      const data = await res.json();
      setCycleMsg(`Finished ${symbol}: Action: ${data.decision.action} | Price: $${data.latest_price.toLocaleString()} | Approved: ${data.risk_verdict.approved}`);
      await fetchTelemetry();
    } catch (err) {
      setCycleMsg(`Error running cycle: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const triggerReplay = async (symbol: string) => {
    setLoading(true);
    setCycleMsg(`Running forward replay audit on ${symbol} (120 15m candles)...`);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/pipeline/replay?symbol=${encodeURIComponent(symbol)}&candles=120&timeframe=15m`, {
        method: "POST",
      });
      const data = await res.json();
      setCycleMsg(`Replay complete: ${data.total_trades_marked} trades marked | Win Rate: ${data.win_rate_pct}% | Net PnL: $${data.net_realized_pnl_usd}`);
      await fetchTelemetry();
    } catch (err) {
      setCycleMsg(`Error running replay: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const triggerHalt = async () => {
    if (confirm("Emergency Circuit Breaker: Halt all QuantAI trading immediately?")) {
      await fetch("http://localhost:8000/api/v1/risk/halt?reason=NextJsDashboardOverride", { method: "POST" });
      await fetchTelemetry();
    }
  };

  const winsCount = markedTrades.filter((t) => t.realized_pnl_usd > 0).length;
  const lossesCount = markedTrades.filter((t) => t.realized_pnl_usd <= 0 && t.status !== "OPEN").length;
  const totalPnL = markedTrades.reduce((acc, t) => acc + (t.realized_pnl_usd || 0), 0);

  return (
    <main className="min-h-screen bg-[#0a0e17] text-slate-100 p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Header */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-white/10 gap-4">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-r from-blue-500 to-purple-600 px-3 py-1.5 rounded-lg font-bold text-sm tracking-wide">
            QUANTAI 1.0
          </div>
          <div>
            <h1 className="text-xl font-bold">Autonomous Quantitative Intelligence Platform</h1>
            <p className="text-xs text-slate-400">Binance Spot (BTC/USDT, ETH/USDT) • Freqtrade Substrate</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-full text-xs font-semibold text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            DRY-RUN PAPER ACTIVE
          </div>
          <button
            onClick={triggerHalt}
            className="bg-red-600 hover:bg-red-700 text-white font-semibold text-xs px-4 py-2 rounded-lg transition shadow-lg shadow-red-600/20"
          >
            CIRCUIT BREAKER
          </button>
        </div>
      </header>

      {/* Control Banner */}
      <div className="flex flex-wrap items-center justify-between bg-white/[0.03] border border-white/10 p-4 rounded-xl gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            disabled={loading}
            onClick={() => triggerCycle("BTC/USDT")}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg transition"
          >
            ⚡ Run BTC Cycle
          </button>
          <button
            disabled={loading}
            onClick={() => triggerCycle("ETH/USDT")}
            className="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg transition"
          >
            ⚡ Run ETH Cycle
          </button>
          <button
            disabled={loading}
            onClick={() => triggerReplay("BTC/USDT")}
            className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg transition"
          >
            ⏩ Replay BTC (15m)
          </button>
          <button
            disabled={loading}
            onClick={() => triggerReplay("ETH/USDT")}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg transition"
          >
            ⏩ Replay ETH (15m)
          </button>
          <button
            onClick={fetchTelemetry}
            className="bg-white/10 hover:bg-white/20 text-white font-medium text-xs px-3 py-2.5 rounded-lg transition"
          >
            🔄 Refresh
          </button>
        </div>
        {cycleMsg && <p className="text-xs text-blue-300 font-mono">{cycleMsg}</p>}
      </div>

      {/* Key Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white/[0.03] border border-white/10 p-5 rounded-xl">
          <p className="text-xs uppercase tracking-wider text-slate-400 font-medium">Portfolio Capital</p>
          <h2 className="text-2xl font-bold mt-2 text-white">
            ${portfolio?.total_capital_usd.toLocaleString(undefined, { minimumFractionDigits: 2 }) ?? "100,000.00"}
          </h2>
          <p className="text-xs text-emerald-400 mt-1">
            Available: ${portfolio?.available_capital_usd.toLocaleString(undefined, { minimumFractionDigits: 2 }) ?? "100,000.00"}
          </p>
        </div>

        <div className="bg-white/[0.03] border border-white/10 p-5 rounded-xl">
          <p className="text-xs uppercase tracking-wider text-slate-400 font-medium">Daily Drawdown</p>
          <h2 className="text-2xl font-bold mt-2 text-white">
            {((portfolio?.daily_drawdown_pct ?? 0) * 100).toFixed(2)}%
          </h2>
          <p className="text-xs text-slate-400 mt-1">Hard Limit: 2.00%</p>
        </div>

        <div className="bg-white/[0.03] border border-white/10 p-5 rounded-xl">
          <p className="text-xs uppercase tracking-wider text-slate-400 font-medium">Active Exposure</p>
          <h2 className="text-2xl font-bold mt-2 text-white">
            ${portfolio?.active_exposure_usd.toLocaleString(undefined, { minimumFractionDigits: 2 }) ?? "0.00"}
          </h2>
          <p className="text-xs text-slate-400 mt-1">Max Ceiling: 50.00%</p>
        </div>

        <div className="bg-white/[0.03] border border-white/10 p-5 rounded-xl">
          <p className="text-xs uppercase tracking-wider text-slate-400 font-medium">Risk Guardian Status</p>
          <h2 className={`text-2xl font-bold mt-2 ${portfolio?.emergency_halt ? "text-red-500" : "text-emerald-400"}`}>
            {portfolio?.emergency_halt ? "HALTED" : "NOMINAL"}
          </h2>
          <p className="text-xs text-slate-400 mt-1">Fractional Kelly: 0.35x</p>
        </div>
      </div>

      {/* SECTION: Marked Trades Ledger & Outcome Tracker */}
      <div className="bg-white/[0.03] border border-white/10 p-5 rounded-xl space-y-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div>
            <h3 className="font-semibold text-sm uppercase tracking-wide text-slate-200">
              Forward Paper Trades Ledger & Outcome Tracker
            </h3>
            <p className="text-xs text-slate-400">
              Synchronized with Excel • Record: {winsCount}W / {lossesCount}L • Net PnL:{" "}
              <span className={totalPnL >= 0 ? "text-emerald-400 font-mono" : "text-red-400 font-mono"}>
                ${totalPnL >= 0 ? `+${totalPnL.toFixed(2)}` : totalPnL.toFixed(2)}
              </span>
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex bg-white/5 rounded-lg p-1 text-xs font-semibold">
              <button
                onClick={() => setSelectedPair("BTC")}
                className={`px-3 py-1 rounded ${selectedPair === "BTC" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                BTC/USDT
              </button>
              <button
                onClick={() => setSelectedPair("ETH")}
                className={`px-3 py-1 rounded ${selectedPair === "ETH" ? "bg-purple-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                ETH/USDT
              </button>
            </div>
            <a
              href={`http://localhost:8000/api/v1/trades/download-excel?pair=${selectedPair}`}
              className="bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 text-emerald-300 font-semibold text-xs px-3.5 py-1.5 rounded-lg transition flex items-center gap-1.5"
            >
              📥 Download Excel (.xlsx)
            </a>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400 border-b border-white/10 pb-2">
              <tr>
                <th className="py-2.5">Trade ID</th>
                <th>Status</th>
                <th>Pair</th>
                <th>Side</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>Target TP</th>
                <th>Stop Loss</th>
                <th>Net PnL</th>
                <th>Thesis Confirmed?</th>
                <th>Strategy Rationale</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono">
              {markedTrades.length === 0 ? (
                <tr>
                  <td colSpan={11} className="py-6 text-center text-slate-500 font-sans">
                    No marked trades recorded yet. Run a replay or launch the live observer.
                  </td>
                </tr>
              ) : (
                markedTrades.map((t) => (
                  <tr key={t.trade_id} className="hover:bg-white/[0.02]">
                    <td className="py-3 font-bold text-slate-300">{t.trade_id}</td>
                    <td>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          t.status === "CLOSED_WIN"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : t.status === "CLOSED_LOSS"
                            ? "bg-red-500/20 text-red-400"
                            : "bg-yellow-500/20 text-yellow-400"
                        }`}
                      >
                        {t.status}
                      </span>
                    </td>
                    <td className="font-semibold text-slate-200">{t.pair}</td>
                    <td>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          t.side === "BUY" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                        }`}
                      >
                        {t.side}
                      </span>
                    </td>
                    <td>${t.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td>${t.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className="text-emerald-400">${t.take_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className="text-red-400">${t.stop_loss.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className={t.realized_pnl_usd >= 0 ? "text-emerald-400 font-bold" : "text-red-400 font-bold"}>
                      ${t.realized_pnl_usd >= 0 ? `+${t.realized_pnl_usd.toFixed(2)}` : t.realized_pnl_usd.toFixed(2)} ({t.realized_pnl_pct >= 0 ? `+${t.realized_pnl_pct.toFixed(2)}` : t.realized_pnl_pct.toFixed(2)}%)
                    </td>
                    <td>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          t.thesis_confirmed === "YES"
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : t.thesis_confirmed === "NO"
                            ? "bg-red-500/20 text-red-400 border border-red-500/30"
                            : "bg-yellow-500/20 text-yellow-400"
                        }`}
                      >
                        {t.thesis_confirmed || "PENDING"}
                      </span>
                    </td>
                    <td className="font-sans text-[11px] text-slate-400 max-w-xs truncate" title={t.strategy_rationale}>
                      {t.strategy_rationale}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Grid: Live Decisions & Whale Intelligence */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Decisions Table (2 cols) */}
        <div className="lg:col-span-2 bg-white/[0.03] border border-white/10 p-5 rounded-xl space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold text-sm uppercase tracking-wide text-slate-200">
              Live Swarm Decisions & Rationale
            </h3>
            <span className="text-xs text-slate-400">{decisions.length} Recent Records</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-slate-400 border-b border-white/10 pb-2">
                <tr>
                  <th className="py-2.5">Time</th>
                  <th>Pair</th>
                  <th>Action</th>
                  <th>Confidence</th>
                  <th>Net Edge</th>
                  <th>Risk Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {decisions.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-slate-500">
                      No decisions recorded yet. Click a cycle button above.
                    </td>
                  </tr>
                ) : (
                  decisions.map((d) => (
                    <tr key={d.id} className="hover:bg-white/[0.02]">
                      <td className="py-3 font-mono text-slate-400">
                        {new Date(d.timestamp).toLocaleTimeString()}
                      </td>
                      <td className="font-semibold text-slate-200">{d.pair}</td>
                      <td>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            d.action === "BUY"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : d.action === "SELL"
                              ? "bg-red-500/20 text-red-400"
                              : "bg-slate-500/20 text-slate-400"
                          }`}
                        >
                          {d.action}
                        </span>
                      </td>
                      <td>{(d.confidence * 100).toFixed(1)}%</td>
                      <td className="text-emerald-400 font-mono">+{d.expected_return_bps.toFixed(1)} bps</td>
                      <td>
                        <span className="text-slate-400 text-[11px]">{d.risk_status}</span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Whale Intelligence Feed (1 col) */}
        <div className="bg-white/[0.03] border border-white/10 p-5 rounded-xl space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold text-sm uppercase tracking-wide text-slate-200">
              Whale & Smart Money Radar
            </h3>
            <span className="text-xs text-slate-400">On-Chain</span>
          </div>

          <div className="space-y-3">
            {whales.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">Monitoring institutional addresses...</p>
            ) : (
              whales.map((w) => (
                <div
                  key={w.id}
                  className={`p-3 rounded-lg border-l-4 bg-white/[0.02] ${
                    w.signal_bias === "BULLISH"
                      ? "border-emerald-500"
                      : w.signal_bias === "BEARISH"
                      ? "border-red-500"
                      : "border-slate-500"
                  }`}
                >
                  <div className="flex justify-between items-start text-xs">
                    <span className="font-bold text-slate-200">{w.event_type}</span>
                    <span className="font-mono text-emerald-400">${(w.usd_value / 1e6).toFixed(2)}M</span>
                  </div>
                  <div className="flex justify-between items-center text-[11px] text-slate-400 mt-1">
                    <span>{w.asset}</span>
                    <span>Conf: {(w.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
