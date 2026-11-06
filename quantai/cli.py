"""QuantAI Unified Command Line Interface (CLI)."""

import argparse
import sys
import logging
from quantai.config.settings import get_config
from quantai.storage.db import get_db_manager, init_database
from quantai.storage.models import TradeDecisionRecord, TradeRecord, RiskEvent

logger = logging.getLogger("quantai.cli")


def cmd_status(args):
    """Displays current system status, portfolio exposure, and risk state."""
    from quantai.risk.guardian import IndependentRiskGuardian
    from quantai.execution.paper_engine import PaperExecutionEngine

    init_database()
    config = get_config()
    db_mgr = get_db_manager()
    risk = IndependentRiskGuardian()
    execution = PaperExecutionEngine()

    print("\n" + "=" * 60)
    print(" 🚀 QUANTAI PLATFORM STATUS & TELEMETRY")
    print("=" * 60)
    print(f" Environment    : {config.environment}")
    print(f" Execution Mode : {config.execution_mode.value.upper()}")
    print(f" Binance API    : {'CONFIGURED (Protected)' if config.exchange.api_key else 'UNSET'}")
    print(f" Target Pairs   : {', '.join(config.exchange.pairs)}")
    print(f" Portfolio Value: ${risk.total_capital:,.2f}")
    print(f" Available Cash : ${risk.available_capital:,.2f}")
    print(f" Active Exposure: ${risk.active_exposure_usd:,.2f}")
    print(f" Circuit Breaker: {'HALTED (Alert)' if risk.emergency_halt else 'NOMINAL (Normal)'}")
    print("-" * 60)

    with db_mgr.get_session() as session:
        recent_decisions = (
            session.query(TradeDecisionRecord)
            .order_by(TradeDecisionRecord.timestamp.desc())
            .limit(5)
            .all()
        )
        print(f"\nRecent Strategy Decisions ({len(recent_decisions)}):")
        for d in recent_decisions:
            print(f" [{d.timestamp.strftime('%H:%M:%S')}] {d.pair} -> {d.action} (Conf: {d.confidence:.1%}, Status: {d.risk_status})")

        recent_trades = (
            session.query(TradeRecord)
            .order_by(TradeRecord.open_time.desc())
            .limit(5)
            .all()
        )
        print(f"\nRecent Executed Trades ({len(recent_trades)}):")
        for t in recent_trades:
            print(f" [{t.open_time.strftime('%H:%M:%S')}] {t.pair} {t.side.upper()} {t.amount:.4f} @ ${t.entry_price:,.2f} | PnL: ${t.realized_pnl:,.2f} ({t.status})")
    print("=" * 60 + "\n")


def cmd_benchmark(args):
    """Executes comparative benchmark evaluation against historical data."""
    from quantai.ingestion.binance import BinanceMarketDataClient
    from quantai.intelligence.technical.feature_engine import TechnicalFeatureEngine
    from quantai.research.benchmarks import BenchmarkEvaluator

    print("\nRunning QuantAI Benchmark Suite on BTC/USDT...")
    client = BinanceMarketDataClient()
    candles = client.fetch_klines(symbol="BTC/USDT", interval="5m", limit=args.candles)
    feature_engine = TechnicalFeatureEngine()
    df = feature_engine.dataframe_from_candles(candles)

    evaluator = BenchmarkEvaluator()
    metrics = evaluator.run_all(df, symbol="BTC/USDT")

    print("\n" + "=" * 90)
    print(f" {'STRATEGY NAME':<32} | {'TRADES':<6} | {'WIN %':<7} | {'NET PNL':<9} | {'PF':<5} | {'SHARPE':<6} | {'MAX DD':<7}")
    print("=" * 90)
    for m in metrics:
        print(
            f" {m.strategy_name:<32} | {m.total_trades:<6} | {m.win_rate_pct:>6.1f}% | {m.net_pnl_pct:>+8.2f}% | {m.profit_factor:>5.2f} | {m.sharpe_ratio:>6.2f} | {m.max_drawdown_pct:>6.2f}%"
        )
    print("=" * 90 + "\n")


def cmd_download(args):
    """Downloads historical candles from Binance."""
    from quantai.ingestion.downloader import HistoricalDataDownloader

    downloader = HistoricalDataDownloader()
    count = downloader.download_range(symbol=args.symbol, timeframe=args.timeframe, total_candles=args.limit)
    print(f"Downloaded and saved {count} candles for {args.symbol}.")


def cmd_api(args):
    """Starts the FastAPI server and embedded dashboard."""
    import uvicorn
    config = get_config()
    uvicorn.run("quantai.api.main:app", host=args.host or config.api_host, port=args.port or config.api_port, reload=args.reload)


def cmd_daemon(args):
    """Runs the continuous autonomous trading daemon."""
    from quantai.daemon import main as daemon_main
    daemon_main()


def cmd_freqtrade(args):
    """Executes Freqtrade CLI with QuantAI strategy and configuration."""
    from quantai.execution.freqtrade_runner import FreqtradeRunner
    runner = FreqtradeRunner()

    if args.ft_action == "trade":
        print(f"Launching Freqtrade Spot Trade (Dry-run: {not args.live})...")
        sys.exit(runner.run_trade(dry_run=not args.live, strategy=args.strategy))
    elif args.ft_action == "backtest":
        print(f"Running Freqtrade Backtest for strategy: {args.strategy}...")
        sys.exit(runner.run_backtest(strategy=args.strategy, timeframe=args.timeframe, timerange=args.timerange))
    elif args.ft_action == "download-data":
        print("Downloading Freqtrade exchange market data...")
        sys.exit(runner.run_download_data(days=args.days))
    else:
        print("Unknown Freqtrade action. Choose from: trade, backtest, download-data")


def main():
    parser = argparse.ArgumentParser(
        description="QuantAI Autonomous Quantitative Intelligence & Trading Platform CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Status
    subparsers.add_parser("status", help="Print current system status, portfolio & risk limits")

    # Daemon
    subparsers.add_parser("daemon", help="Start autonomous background trading daemon")

    # API
    api_p = subparsers.add_parser("api", help="Launch FastAPI server and UI dashboard")
    api_p.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    api_p.add_argument("--port", type=int, default=8000, help="Port")
    api_p.add_argument("--reload", action="store_true", help="Auto-reload on code change")

    # Benchmark
    bench_p = subparsers.add_parser("benchmark", help="Run strategy comparative benchmarks")
    bench_p.add_argument("--candles", type=int, default=150, help="Number of candles")

    # Download
    dl_p = subparsers.add_parser("download", help="Download historical market data from Binance")
    dl_p.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair")
    dl_p.add_argument("--timeframe", type=str, default="5m", help="Candle timeframe")
    dl_p.add_argument("--limit", type=int, default=300, help="Total candles to fetch")

    # Freqtrade Subcommand
    ft_p = subparsers.add_parser("freqtrade", help="Run Freqtrade with QuantAI extensions")
    ft_p.add_argument("ft_action", choices=["trade", "backtest", "download-data"], help="Freqtrade operation")
    ft_p.add_argument("--strategy", type=str, default="QuantAIStrategy", help="Strategy to run")
    ft_p.add_argument("--timeframe", type=str, default="5m", help="Timeframe")
    ft_p.add_argument("--timerange", type=str, default=None, help="Timerange for backtest")
    ft_p.add_argument("--days", type=int, default=30, help="Days of data to download")
    ft_p.add_argument("--live", action="store_true", help="Live execution flag (requires explicit approval)")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "daemon":
        cmd_daemon(args)
    elif args.command == "api":
        cmd_api(args)
    elif args.command == "benchmark":
        cmd_benchmark(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "freqtrade":
        cmd_freqtrade(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

