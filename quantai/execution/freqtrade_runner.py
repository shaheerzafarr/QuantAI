"""Freqtrade Execution & Harness Orchestrator for QuantAI.

Provides a unified programmatic and CLI interface to launch, backtest, and
monitor Freqtrade runs using QuantAIStrategy and QuantAIFreqaiModel.
Supports both official Docker container execution and local Python subprocesses.
"""

import logging
import os
import shutil
import subprocess
import sys
from typing import List, Optional

logger = logging.getLogger("quantai.freqtrade_runner")


class FreqtradeRunner:
    """Manages Freqtrade execution with QuantAI extensions."""

    def __init__(self, user_data_path: str = "user_data", config_file: str = "user_data/config.json"):
        self.user_data_path = os.path.abspath(user_data_path)
        self.config_file = os.path.abspath(config_file)
        self.has_docker = shutil.which("docker") is not None

    def run_trade(self, dry_run: bool = True, strategy: str = "QuantAIStrategy") -> int:
        """Executes Freqtrade in trade mode with QuantAI strategy."""
        cmd = [
            "trade",
            "--config", "/freqtrade/user_data/config.json" if self.has_docker else self.config_file,
            "--strategy", strategy,
            "--strategy-path", "/freqtrade/user_data/strategies" if self.has_docker else os.path.join(self.user_data_path, "strategies"),
        ]
        if dry_run:
            cmd.append("--dry-run")

        return self._execute(cmd)

    def run_backtest(
        self,
        strategy: str = "QuantAIStrategy",
        timeframe: str = "5m",
        timerange: Optional[str] = None,
        freqai_model: Optional[str] = "QuantAIFreqaiModel",
    ) -> int:
        """Executes Freqtrade historical backtest."""
        cmd = [
            "backtesting",
            "--config", "/freqtrade/user_data/config.json" if self.has_docker else self.config_file,
            "--strategy", strategy,
            "--strategy-path", "/freqtrade/user_data/strategies" if self.has_docker else os.path.join(self.user_data_path, "strategies"),
            "--timeframe", timeframe,
        ]
        if timerange:
            cmd.extend(["--timerange", timerange])
        if freqai_model:
            cmd.extend(["--freqaimodel", freqai_model])

        return self._execute(cmd)

    def run_download_data(
        self,
        pairs: List[str] = ["BTC/USDT", "ETH/USDT"],
        timeframes: List[str] = ["5m", "1h", "1d"],
        days: int = 30,
    ) -> int:
        """Downloads historical data via Freqtrade exchange connector."""
        cmd = [
            "download-data",
            "--config", "/freqtrade/user_data/config.json" if self.has_docker else self.config_file,
            "--pairs", *pairs,
            "--timeframes", *timeframes,
            "--days", str(days),
        ]
        return self._execute(cmd)

    def _execute(self, ft_args: List[str]) -> int:
        """Executes via Docker if available, falling back to local Python freqtrade module."""
        if self.has_docker:
            base_dir = os.getcwd()
            docker_cmd = [
                "docker", "run", "--rm", "-it",
                "-v", f"{os.path.join(base_dir, 'user_data')}:/freqtrade/user_data",
                "-v", f"{os.path.join(base_dir, 'quantai')}:/freqtrade/quantai",
                "freqtradeorg/freqtrade:stable",
                *ft_args,
            ]
            logger.info(f"Executing Freqtrade in Docker: {' '.join(docker_cmd)}")
            return subprocess.call(docker_cmd)
        else:
            # Fallback to local python module
            local_cmd = [sys.executable, "-m", "freqtrade.main", *ft_args]
            env = os.environ.copy()
            env["PYTHONPATH"] = f"freqtrade;{env.get('PYTHONPATH', '')}"
            logger.info(f"Executing local Freqtrade: {' '.join(local_cmd)}")
            return subprocess.call(local_cmd, env=env)

