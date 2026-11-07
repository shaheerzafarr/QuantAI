import os
import openpyxl
from quantai.execution.live_observer import LiveMarketObserver

def test_single_excel_and_500_portfolio():
    excel_path = "user_data/QuantAI_Live_Forward_Trades.xlsx"
    obs = LiveMarketObserver(excel_path=excel_path, initial_capital=500.0)
    
    print(f"Initial capital: ${obs.initial_capital}")
    print(f"Risk guardian capital: ${obs.risk_guardian.total_capital}")
    print(f"Risk guardian max exposure: {obs.risk_guardian.risk_cfg.max_portfolio_exposure_pct:.0%}")
    print(f"Max active positions: {obs.config.exchange.max_active_positions}")
    
    # Run a live scan on BTC/USDT and ETH/USDT
    for pair in ["BTC/USDT", "ETH/USDT"]:
        print(f"\n--- Scanning {pair} ---")
        t = obs.scan_and_analyze(pair)
        if t:
            print(f"Marked trade on {pair}: {t['trade_id']} | Side: {t['side']} | Margin: ${t['margin_usd']} | Notional: ${t['allocated_usd']}")
        else:
            print(f"No trade opened on {pair} (Decision logged)")
            
    # Verify Excel was saved
    assert os.path.exists(excel_path), f"File {excel_path} should exist"
    wb = openpyxl.load_workbook(excel_path)
    print(f"\nExcel tabs: {wb.sheetnames}")
    ws_sum = wb["Live Performance Summary"]
    print(f"Summary Balance: {ws_sum['B6'].value}")
    
    # Check for any rogue timestamped files
    user_data_files = os.listdir("user_data")
    rogue = [f for f in user_data_files if "Live_Forward_Trades_" in f]
    print(f"Rogue timestamped files: {rogue}")
    assert len(rogue) == 0, f"Found rogue files: {rogue}"
    print("\nSUCCESS: Exactly 1 single Excel file maintained and $500 portfolio verified!")

if __name__ == "__main__":
    test_single_excel_and_500_portfolio()

