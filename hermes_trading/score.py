"""
score(trades, goal) -> float in [-1, +1]
"""

def score(trades, goal):
    if not trades:
        return 0.0
        
    # Simplified scoring logic for demo
    total_pnl = sum([t.get('pnl_inr', 0) for t in trades if t.get('status') == 'closed'])
    starting_capital = goal.get('starting_capital_inr', 50000)
    
    realised_return = total_pnl / starting_capital
    target_return = goal.get('target_return_30d', 0.04)
    
    # Normalise realised return vs target to [-1, +1]
    score_return = min(max(realised_return / target_return, -1.0), 1.0)
    
    return score_return
