import asyncio
from aiohttp import web
import json
import yaml
from pathlib import Path
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

async def handle_add_asset(request):
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    goal_path = state_path / "goal.yaml"
    strategy_path = state_path / "strategy.yaml"
    
    data = await request.post()
    asset = data.get("asset", "").strip().upper()
    
    if asset:
        goal = yaml.safe_load(goal_path.read_text()) if goal_path.exists() else {}
        strategy = yaml.safe_load(strategy_path.read_text()) if strategy_path.exists() else {}
        
        assets = goal.get("assets", [])
        if asset not in assets:
            assets.append(asset)
            goal["assets"] = assets
            strategy["assets"] = assets
            
            goal_path.write_text(yaml.safe_dump(goal, sort_keys=False))
            strategy_path.write_text(yaml.safe_dump(strategy, sort_keys=False))
            print(f">>> [Dashboard] Added asset: {asset}")
            
    raise web.HTTPFound('/')

async def handle_remove_asset(request):
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    goal_path = state_path / "goal.yaml"
    strategy_path = state_path / "strategy.yaml"
    trades_path = state_path / "trades.jsonl"
    
    data = await request.post()
    asset = data.get("asset", "").strip().upper()
    
    if asset:
        # Check if asset is in open trades
        open_assets = set()
        if trades_path.exists():
            for line in trades_path.read_text().splitlines():
                if line.strip():
                    t = json.loads(line)
                    a = t.get("asset")
                    if t.get("status") == "open":
                        open_assets.add(a)
                    elif t.get("status") == "closed" and a in open_assets:
                        open_assets.remove(a)
                        
        if asset not in open_assets:
            goal = yaml.safe_load(goal_path.read_text()) if goal_path.exists() else {}
            strategy = yaml.safe_load(strategy_path.read_text()) if strategy_path.exists() else {}
            
            assets = goal.get("assets", [])
            if asset in assets:
                assets.remove(asset)
                goal["assets"] = assets
                strategy["assets"] = assets
                
                goal_path.write_text(yaml.safe_dump(goal, sort_keys=False))
                strategy_path.write_text(yaml.safe_dump(strategy, sort_keys=False))
                print(f">>> [Dashboard] Removed asset: {asset}")
                
    raise web.HTTPFound('/')

async def handle_strategy_file(request):
    from hermes_trading.config import get_state_dir
    strategy_path = get_state_dir() / "strategy.yaml"
    if strategy_path.exists():
        return web.Response(text=strategy_path.read_text(), content_type='text/yaml')
    return web.Response(text="strategy.yaml not found", status=404)

async def handle_goal_file(request):
    from hermes_trading.config import get_state_dir
    goal_path = get_state_dir() / "goal.yaml"
    if goal_path.exists():
        return web.Response(text=goal_path.read_text(), content_type='text/yaml')
    return web.Response(text="goal.yaml not found", status=404)

async def handle_dashboard(request):
    from hermes_trading.config import get_state_dir
    state_path = get_state_dir()
    
    # Intercept manual reflection request (?reflect=true)
    if request.query.get("reflect") == "true":
        print(">>> [Web Trigger] Manual reflection requested via dashboard URL parameter.")
        try:
            import subprocess
            import sys
            import os
            reflect_mode = "--hermes" if os.getenv("HERMES_REFLECT_MODE") == "hermes" else "--fallback"
            subprocess.run([sys.executable, "-m", "hermes_trading.reflect", reflect_mode])
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

    open_assets = set()
    for t in trades:
        a = t.get("asset")
        if t.get("status") == "open":
            open_assets.add(a)
        elif t.get("status") == "closed" and a in open_assets:
            open_assets.remove(a)
    asset_rows = []
    for asset in goal.get("assets", []):
        is_open = asset in open_assets
        if is_open:
            action_html = '<span style="color: #e65100; font-size: 0.85em; font-weight: bold; background: #ffe0b2; padding: 4px 8px; border-radius: 4px;">⚠️ ACTIVE POSITION</span>'
        else:
            action_html = f"""
            <form action="/remove_asset" method="post" style="display:inline;">
                <input type="hidden" name="asset" value="{asset}">
                <button type="submit" style="background:#c62828; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:0.85em; font-weight:bold; transition: background 0.2s;" onmouseover="this.style.background=\'#b71c1c\'" onmouseout="this.style.background=\'#c62828\'">Remove</button>
            </form>
            """
        asset_rows.append(f"""
        <tr>
            <td style="font-weight:bold; color:#ffca28; font-size:1.1em;">{asset}</td>
            <td>{action_html}</td>
        </tr>
        """)
    asset_list_html = "".join(asset_rows) if asset_rows else "<tr><td colspan='2' style='text-align:center; color:#777;'>No assets configured</td></tr>"

    # Calculate metrics
    current_capital = goal.get("current_capital_inr", 0)
    starting_capital = goal.get("starting_capital_inr", 1)
    return_pct = ((current_capital - starting_capital) / starting_capital) * 100
    
    # Calculate Unrealized P&L from active positions and live price feed
    active_positions = {}
    for t in trades:
        asset = t.get("asset")
        if t.get("status") == "open":
            active_positions[asset] = t
        elif t.get("status") == "closed" and asset in active_positions:
            del active_positions[asset]
            
    unrealized_pnl = 0.0
    for asset, pos in active_positions.items():
        live_price = prices.get(asset, {}).get("price")
        if live_price is not None:
            unrealized_pnl += (live_price - pos["entry_price"]) * pos["quantity"]
            
    live_portfolio_value = current_capital + unrealized_pnl
    live_return_pct = ((live_portfolio_value - starting_capital) / starting_capital) * 100
    
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
                <p style="margin-top: 10px; font-size: 0.95em;">
                    <a href="/strategy" target="_blank" style="color: #0288d1; font-weight: bold; text-decoration: none; margin-right: 15px; border-bottom: 1px dashed #0288d1;">📄 View Active Strategy</a>
                    <a href="/goal" target="_blank" style="color: #0288d1; font-weight: bold; text-decoration: none; border-bottom: 1px dashed #0288d1;">🎯 View Active Goal</a>
                </p>
            </div>
            <div>
                <span style="background: #e1f5fe; color: #01579b; padding: 8px 16px; border-radius: 20px; font-weight: bold;">PAPER MODE</span>
            </div>
        </div>

        <div class="metric-grid">
            <div class="card metric" style="border: 2px solid #2e7d32; background: #e8f5e9;">
                <h3 style="color: #2e7d32; font-weight: bold;">Live Portfolio Value</h3>
                <p style="color: #1b5e20; font-size: 1.6em;">₹{live_portfolio_value:,.2f}</p>
                <span style="color: {'green' if live_return_pct >= 0 else 'red'}; font-weight: bold;">{live_return_pct:+.2f}% (Live)</span>
            </div>
            <div class="card metric">
                <h3>Realized Capital</h3>
                <p>₹{current_capital:,.2f}</p>
                <span style="color: {'green' if return_pct >= 0 else 'red'}">{return_pct:+.2f}% (Realized)</span>
            </div>
            <div class="card metric">
                <h3>Unrealized P&L</h3>
                <p style="color: {'green' if unrealized_pnl >= 0 else 'red'}">₹{unrealized_pnl:+,.2f}</p>
                <span style="color: #888; font-size: 0.85em;">Open positions swing</span>
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
        </div>

        <div class="card" style="display: flex; gap: 30px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 300px;">
                <h2>Current Assets Basket</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr>
                            <th>Asset Symbol (NSE)</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {asset_list_html}
                    </tbody>
                </table>
            </div>
            
            <div style="flex: 1; min-width: 300px; border-left: 1px solid #ddd; padding-left: 30px;">
                <h2>Add New Asset</h2>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 20px;">Add a new NSE stock ticker to the paper trading asset list. Only letters and standard NSE symbols are allowed.</p>
                <form action="/add_asset" method="post" style="display: flex; gap: 10px; align-items: center;">
                    <input type="text" name="asset" placeholder="e.g. TCS, SBIN, TATAMOTORS" required style="padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 1em; flex: 1; text-transform: uppercase;">
                    <button type="submit" style="background: #2e7d32; color: white; border: none; padding: 10px 20px; border-radius: 4px; font-size: 1em; font-weight: bold; cursor: pointer; transition: background 0.2s;" onmouseover="this.style.background=\'#1b5e20\'" onmouseout="this.style.background=\'#2e7d32\'">Add Asset</button>
                </form>
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
                        <th>Stop Loss</th>
                        <th>Target Price</th>
                        <th>Exit Price</th>
                        <th>P&L (INR)</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([
                        f"<tr>"
                        f"<td>{t['entry_time']}</td>"
                        f"<td>{t.get('asset', '-')}</td>"
                        f"<td>{t['side']}</td>"
                        f"<td>{t.get('quantity', '-')}</td>"
                        f"<td>₹{t['entry_price']:.2f}</td>"
                        f"<td>{f'₹{t[\"stop_loss_price\"]:.2f}' if t.get('stop_loss_price') is not None else '-'}</td>"
                        f"<td>{f'₹{t[\"target_price\"]:.2f}' if t.get('target_price') is not None else '-'}</td>"
                        f"<td>{f'₹{t[\"exit_price\"]:.2f}' if (t.get('exit_price') is not None and t.get('exit_price') != '-') else '-'}</td>"
                        f"<td style='color: {\"green\" if t.get(\"pnl_inr\", 0) >= 0 else \"red\"}'>{f'₹{t[\"pnl_inr\"]:+,.2f}' if t.get('pnl_inr') is not None else '-'}</td>"
                        f"<td>{t['status'].upper()}</td>"
                        f"</tr>"
                        for t in trades[-10:][::-1]
                    ]) if trades else "<tr><td colspan='10' style='text-align:center'>No trades yet</td></tr>"}
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
    app.add_routes([
        web.get('/', handle_dashboard),
        web.get('/strategy', handle_strategy_file),
        web.get('/goal', handle_goal_file),
        web.post('/add_asset', handle_add_asset),
        web.post('/remove_asset', handle_remove_asset)
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Dashboard live at http://localhost:{port}")
