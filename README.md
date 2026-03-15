## Quick Onboarding
```bash
git clone https://github.com/NewtonHatesApples/QuantHackathon2026.git
```
```bash
pip install -r requirements.txt
```
Then create a directory named `data` for storing crypto's csv, a directory named `tmp_data` to assist with the process of downloading data.
<br>
When using `api.py`, set environmental variables `API_KEY` for the API key and `API_SECRET` for the secret key.
## Backtesting scripts and visualization
`backtest.ipynb`, `dashboard.py`
## (Modified) Roostoo API
`api.py`
<br>
Referenced from https://github.com/roostoo/Roostoo-API-Documents.
## Data source
From Binance. https://data.binance.vision/data/spot/daily/klines.
<br>
Data granularity up to 1m.