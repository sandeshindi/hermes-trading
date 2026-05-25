import asyncio
from aiohttp import web
import json
import yaml
from pathlib import Path
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

async def handle_dashboard(request):
    goal_path = Path("state/goal.yaml")
    trades_path = Path("state/trades.jsonl")
    strategy_path = Path("state/strategy.yaml")
    heartbeat_path = Path("state/heartbeat.json")
    hypotheses_path = Path("state/hypotheses.jsonl")

    goal = yaml.safe_load(goal_path.read_text()) if goal_path.exists() else {}
    strategy = yaml.safe_load(strategy_path.read_text()) if strategy_path.exists() else {}
    heartbeat = json.loads(heartbeat_path.read_text()) if heartbeat_path.exists() else {}
    
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
        </style>
    </head>
    <body>
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
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>P&L (INR)</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f"<tr><td>{t['entry_time']}</td><td>{t.get('asset', '-')}</td><td>{t['side']}</td><td>₹{t['entry_price']}</td><td>₹{t.get('exit_price', '-')}</td><td style='color: {'green' if t.get('pnl_inr', 0) >= 0 else 'red'}'>{t.get('pnl_inr', '-')}</td><td>{t['status']}</td></tr>" for t in trades[-10:][::-1]]) if trades else "<tr><td colspan='7' style='text-align:center'>No trades yet</td></tr>"}
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
