from flask import Flask
import pandas as pd
import plotly.graph_objects as go

app = Flask(__name__)

@app.route('/')
def dashboard():
    try:
        df = pd.read_csv('equity_curve.csv')
        df['datetime'] = pd.to_datetime(df['datetime'])
    except FileNotFoundError:
        return "<h1>Error: equity_curve.csv not found!<br>Run the main optimizer script first.</h1>"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['datetime'],
        y=df['pnl_before'],
        mode='lines',
        name='Cumulative PnL (Before cost)',
        line=dict(color='royalblue', width=2),
        hovertemplate='<b>Date:</b> %{x|%Y-%m-%d %H:%M:%S}<br>'
                      '<b>PnL Before:</b> $%{y:,.2f}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=df['datetime'],
        y=df['pnl_after'],
        mode='lines',
        name='Cumulative PnL (After cost)',
        line=dict(color='crimson', width=2),
        hovertemplate='<b>Date:</b> %{x|%Y-%m-%d %H:%M:%S}<br>'
                      '<b>PnL After:</b> $%{y:,.2f}<extra></extra>'
    ))

    # FIXED: Clamp zoom-out (no blank edges) + enable wheel zoom
    fig.update_xaxes(
        autorange=False,
        range=[df['datetime'].min(), df['datetime'].max()]   # locks max zoom-out to full data
    )
    fig.update_yaxes(autorange=True)

    fig.update_layout(
        title='Interactive Dashboard',
        xaxis_title='Time',
        yaxis_title='Cumulative PnL (USD)',
        hovermode='x unified',
        template='plotly_white',
        height=800,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )

    graph_html = fig.to_html(
        full_html=False,
        include_plotlyjs='cdn',
        config={'scrollZoom': True, 'displayModeBar': True, 'modeBarButtonsToRemove': ['lasso2d']}
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Interactive Dashboard (Optimized)</title>
        <style>body {{ font-family: Arial; margin: 20px; background: #f8f9fa; }}</style>
    </head>
    <body>
        <h1>📈 Optimized Strategy Dashboard</h1>
        <p><b>How to use:</b><br>
           • Hover → tooltip box shows exact date (YYYY-MM-DD hh:mm:ss) + PnL (like investing.com)<br>
           • Mouse wheel scroll (anywhere on graph) → zoom in/out (now fully responsive)<br>
           • Zoom-out button / double-click → cannot create blank edges (clamped to full data range)<br>
           • Use Reset button in top-right to return to full view</p>
        {graph_html}
        <p style="text-align:center; color:#666; margin-top:30px;">
            Built with Flask + Plotly • Best parameters from Optuna
        </p>
    </body>
    </html>
    """

if __name__ == '__main__':
    print("🚀 Starting dashboard at http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
