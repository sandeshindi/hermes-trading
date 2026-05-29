import asyncio
from aiohttp import web
import json
import yaml
from pathlib import Path
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

async def handle_dashboard(request):
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    
    # Intercept manual reflection request (?reflect=true)
    if request.query.get("reflect") == "true":
        print(">>> [Web Trigger] Manual reflection requested via dashboard URL parameter.")
        try:
            import subprocess
            import sys
            subprocess.run([sys.executable, "-m", "hermes_trading.reflect", "--fallback"])
            raise web.HTTPFound('/')
        except web.HTTPFound:
            raise
        except Exception as e:
            print(f"Error triggering manual reflection: {e}")
    
    goal_path = state_path / "goal.yaml"
    trades_path = state_path / "trades.jsonl"
    strategy_path = state_path / "strategy.yaml"
    heartbeat_path = state_path / "heartbeat.json"
    hypotheses_path = state_path / "hypotheses.jsonl"

    goal = yaml.safe_load(goal_path.read_text()) if goal_path.exists() else {}
    strategy = yaml.safe_load(strategy_path.read_text()) if strategy_path.exists() else {}
    heartbeat = json.loads(heartbeat_path.read_text()) if heartbeat_path.exists() else {}
    
    prices_path = state_path / "prices.json"
    prices = json.loads(prices_path.read_text()) if prices_path.exists() else {}
    
    ticker_items = []
    for asset in goal.get("assets", []):
        info = prices.get(asset, {})
        price_val = info.get("price")
        rsi_val = info.get("rsi")
        price_str = f"₹{price_val:,.2f}" if price_val is not None else "₹-"
        rsi_str = f"RSI: {rsi_val:.1f}" if rsi_val is not None else "RSI: -"
        
        ai_decision = info.get("ai_decision", "SCANNING")
        ai_reason = info.get("ai_reason", "Waiting for AI consult or indicators threshold...")
        ai_class = f"ai-{ai_decision.lower().split()[0]}" if ai_decision else "ai-scanning"
        
        ticker_items.append(
            f'<div class="ticker-item">'
            f'<span class="ticker-symbol">{asset}</span>'
            f'<span class="ticker-price">{price_str}</span>'
            f'<span class="ticker-rsi">({rsi_str})</span>'
            f'<span class="ticker-ai {ai_class}" title="{ai_reason}">{ai_decision}</span>'
            f'</div>'
        )
    ticker_html = "".join(ticker_items)
    
    trades = []
    if trades_path.exists():
        for line in trades_path.read_text().splitlines():
            if line.strip():
                trades.append(json.loads(line))
                
    hypotheses = []
    if hypotheses_path.exists():
        for line in hypotheses_path.read_text().splitlines():
            if line.strip():
                hypotheses.append(json.loads(line))

    # Calculate metrics
    current_capital = goal.get("current_capital_inr", 0)
    starting_capital = goal.get("starting_capital_inr", 1)
    return_pct = ((current_capital - starting_capital) / starting_capital) * 100
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hermes Trading Dashboard</title>
        <meta http-equiv="refresh" content="10">
        <style>
            body {{ font-family: sans-serif; margin: 20px; background: #f4f4f9; }}
            .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; }}
            .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }}
            .metric {{ text-align: center; }}
            .metric h3 {{ margin: 0; color: #666; font-size: 0.9em; }}
            .metric p {{ margin: 5px 0 0; font-size: 1.5em; font-weight: bold; }}
            .status-open {{ color: green; }}
            .status-closed {{ color: red; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background: #eee; }}
            .ticker-bar {{ display: flex; flex-wrap: wrap; gap: 10px; background: #1a1a24; padding: 12px 20px; border-radius: 8px; margin-bottom: 20px; color: white; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.15); }}
            .ticker-bar .ticker-label {{ font-weight: bold; text-transform: uppercase; font-size: 0.8em; color: #4fc3f7; border-right: 2px solid #37474f; padding-right: 15px; margin-right: 5px; letter-spacing: 1px; }}
            .ticker-item {{ background: #263238; padding: 6px 12px; border-radius: 6px; font-size: 0.9em; display: flex; align-items: center; gap: 8px; border: 1px solid #37474f; }}
            .ticker-symbol {{ font-weight: bold; color: #ffca28; }}
            .ticker-price {{ font-family: monospace; font-weight: bold; color: #69f0ae; }}
            .ticker-rsi {{ font-size: 0.8em; color: #b0bec5; }}
            .ticker-ai {{ font-size: 0.8em; padding: 2px 6px; border-radius: 4px; font-weight: bold; text-transform: uppercase; cursor: help; }}
            .ai-buy {{ background: #2e7d32; color: #a5d6a7; }}
            .ai-sell {{ background: #c62828; color: #ef9a9a; }}
            .ai-hold {{ background: #37474f; color: #cfd8dc; }}
            .ai-skip {{ background: #e65100; color: #ffe0b2; }}
            .ai-cooldown {{ background: #4e342e; color: #d7ccc8; }}
            .ai-staggered {{ background: #558b2f; color: #f1f8e9; }}
            .ai-holding {{ background: #1565c0; color: #bbdefb; }}
            .ai-scanning {{ background: #00838f; color: #e0f7fa; }}
            .ai-penalty {{ background: #b71c1c; color: #ffcdd2; animation: pulse 1.5s infinite; }}
            @keyframes pulse {{
                0% {{ opacity: 0.6; }}
                50% {{ opacity: 1.0; }}
                100% {{ opacity: 0.6; }}
            }}
        </style>
    </head>
    <body>
        <div class="ticker-bar">
            <span class="ticker-label">Live NSE Prices</span>
            {ticker_html}
        </div>
        <div class="card header">
            <div>
                <h1>{", ".join(goal.get('assets', []))} <span style="font-size: 0.5em; background: #eee; padding: 4px 8px; border-radius: 4px;">v{strategy.get('version', '01')}</span></h1>
                <p>Status: <span class="status-{heartbeat.get('market_status', 'closed')}">{heartbeat.get('market_status', 'Unknown').upper()}</span> | Last Heartbeat: {heartbeat.get('timestamp', 'N/A')}</p>
            </div>
            <div>
                <span style="background: #e1f5fe; color: #01579b; padding: 8px 16px; border-radius: 20px; font-weight: bold;">PAPER MODE</span>
            </div>
        </div>

        <div class="metric-grid">
            <div class="card metric">
                <h3>Current Capital</h3>
                <p>₹{current_capital:,.2f}</p>
                <span style="color: {'green' if return_pct >= 0 else 'red'}">{return_pct:+.2f}%</span>
            </div>
            <div class="card metric">
                <h3>Starting Capital</h3>
                <p>₹{starting_capital:,.2f}</p>
            </div>
            <div class="card metric">
                <h3>Target Return</h3>
                <p>{goal.get('target_return_30d', 0)*100}%</p>
            </div>
            <div class="card metric">
                <h3>Max Drawdown</h3>
                <p>{goal.get('max_drawdown', 0)*100}%</p>
            </div>
            <div class="card metric">
                <h3>Min Sharpe</h3>
                <p>{goal.get('min_sharpe', 0)}</p>
            </div>
        </div>

        <div class="card">
            <h2>Recent Trades</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date (IST)</th>
                        <th>Asset</th>
                        <th>Side</th>
                        <th>Qty</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>P&L (INR)</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f"<tr><td>{t['entry_time']}</td><td>{t.get('asset', '-')}</td><td>{t['side']}</td><td>{t.get('quantity', '-')}</td><td>₹{t['entry_price']}</td><td>₹{t.get('exit_price', '-')}</td><td style='color: {'green' if t.get('pnl_inr', 0) >= 0 else 'red'}'>{t.get('pnl_inr', '-')}</td><td>{t['status']}</td></tr>" for t in trades[-10:][::-1]]) if trades else "<tr><td colspan='8' style='text-align:center'>No trades yet</td></tr>"}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>Strategy Evolution</h2>
            <table>
                <thead>
                    <tr>
                        <th>Version</th>
                        <th>Date (IST)</th>
                        <th>Variable</th>
                        <th>Change</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f"<tr><td>v{h['version']}</td><td>{h['timestamp']}</td><td>{h['variable']}</td><td>{h['old_value']} &rarr; {h['new_value']}</td><td>{h['reason']}</td></tr>" for h in hypotheses[::-1]]) if hypotheses else "<tr><td colspan='5' style='text-align:center'>Initial version</td></tr>"}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def start_dashboard():
    import os
    app = web.Application()
    app.add_routes([web.get('/', handle_dashboard)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Dashboard live at http://localhost:{port}")
