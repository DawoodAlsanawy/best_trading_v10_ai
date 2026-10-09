"""
شمعة السيولة — عرض الشمعة = عمق السوق
======================================
- ccxt لجلب BTC/USDT
- plotly مع shapes لرسم شموع بعرض متغير
- السيولة التاريخية: Volume / Range (Amihud معكوس)
- لقطة حية لدفتر الأوامر من اللحظة الراهنة
"""

import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ============ 1) جلب OHLCV ============
exchange = ccxt.binance({'enableRateLimit': True})
symbol = 'BTC/USDT'
timeframe = '1h'
limit = 150

ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
df['ts'] = pd.to_datetime(df['ts'], unit='ms')

# ============ 2) لقطة حية لدفتر الأوامر ============
ob_ok = False
try:
    ob = exchange.fetch_order_book(symbol, limit=200)
    bids = np.array(ob['bids'], dtype=float)
    asks = np.array(ob['asks'], dtype=float)
    mid = (bids[0, 0] + asks[0, 0]) / 2

    def depth_within(book, ref, pct):
        lo, hi = ref * (1 - pct), ref * (1 + pct)
        return book[(book[:, 0] >= lo) & (book[:, 0] <= hi), 1].sum()

    bid_d = depth_within(bids, mid, 0.01)   # عمق الشراء ±1%
    ask_d = depth_within(asks, mid, 0.01)   # عمق البيع  ±1%
    spread_bps = (asks[0, 0] - bids[0, 0]) / mid * 1e4
    ob_ok = True
    print(f"Mid={mid:,.2f} | Spread={spread_bps:.2f} bps | "
          f"Bid±1%={bid_d:.2f} BTC | Ask±1%={ask_d:.2f} BTC")
except Exception as e:
    print(f"[Order Book] فشل الجلب: {e}")

# ============ 3) حساب السيولة التاريخية ============
df['range'] = (df['high'] - df['low']).replace(0, np.nan)
df['liq_raw'] = (df['volume'] / df['range']).bfill().ffill()

# تحويل لوغاريتمي (ذيول سمينة)
df['liq_log'] = np.log1p(df['liq_raw'])
lmin, lmax = df['liq_log'].min(), df['liq_log'].max()
df['liq_norm'] = (df['liq_log'] - lmin) / (lmax - lmin + 1e-12)

# ============ 4) عرض الشمعة ============
tf_ms = {'1m': 60_000, '5m': 300_000, '15m': 900_000, '30m': 1_800_000,
         '1h': 3_600_000, '4h': 14_400_000, '1d': 86_400_000}
spacing = tf_ms[timeframe]

df['x'] = df['ts'].astype('int64') // 10**6
df['half_w'] = spacing * (0.20 + 0.75 * df['liq_norm']) / 2

# ============ 5) الرسم ============
fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    row_heights=[0.78, 0.22], vertical_spacing=0.03,
    subplot_titles=("سعر BTC — عرض الشمعة يعكس السيولة",
                    "مؤشر السيولة Λ (Volume / Range) — مطبّع")
)

UP, DOWN = '#26a69a', '#ef5350'

# --- الصف الأول: الشموع بعرض متغير (shapes) ---
for _, r in df.iterrows():
    color = UP if r['close'] >= r['open'] else DOWN
    b_lo = min(r['open'], r['close'])
    b_hi = max(r['open'], r['close'])
    x0 = r['x'] - r['half_w']
    x1 = r['x'] + r['half_w']

    # جسم الشمعة كـ rectangle
    fig.add_shape(
        type='rect', x0=x0, x1=x1, y0=b_lo, y1=b_hi,
        fillcolor=color, line=dict(color=color, width=0),
        xref='x', yref='y', layer='below'
    )
    # الظل العلوي
    fig.add_shape(
        type='line', x0=r['x'], x1=r['x'], y0=b_hi, y1=r['high'],
        line=dict(color=color, width=1),
        xref='x', yref='y', layer='below'
    )
    # الظل السفلي
    fig.add_shape(
        type='line', x0=r['x'], x1=r['x'], y0=b_lo, y1=r['low'],
        line=dict(color=color, width=1),
        xref='x', yref='y', layer='below'
    )

# --- الصف الثاني: مؤشر السيولة ---
fig.add_trace(
    go.Bar(
        x=df['x'], y=df['liq_norm'],
        marker=dict(color=df['liq_norm'], colorscale='Viridis',
                    showscale=False, line=dict(width=0)),
        name='Liquidity', hovertemplate='Liquidity: %{y:.3f}<extra></extra>',
    ),
    row=2, col=1
)

# --- trace شفاف لتفعيل hover على الصف الأول ---
hover_text = [
    f"O: {r['open']:.1f}<br>H: {r['high']:.1f}<br>"
    f"L: {r['low']:.1f}<br>C: {r['close']:.1f}<br>"
    f"Vol: {r['volume']:.1f}<br>Liq: {r['liq_norm']:.3f}<br>"
    f"Width: {r['half_w']*2/spacing*100:.0f}%"
    for _, r in df.iterrows()
]
fig.add_trace(
    go.Scatter(
        x=df['x'], y=df['close'], mode='markers',
        marker=dict(size=6, color='rgba(0,0,0,0)'),
        text=hover_text, hoverinfo='text', showlegend=False,
    ),
    row=1, col=1
)

# --- annotation لدفتر الأوامر ---
if ob_ok:
    fig.add_annotation(
        xref='paper', yref='paper',
        x=0.01, y=0.98, xanchor='left', yanchor='top',
        text=(f"<b>Live Order Book — Binance</b><br>"
              f"Mid: {mid:,.0f} USDT<br>"
              f"Spread: {spread_bps:.2f} bps<br>"
              f"Bid depth ±1%: {bid_d:.1f} BTC<br>"
              f"Ask depth ±1%: {ask_d:.1f} BTC"),
        showarrow=False, align='left',
        bgcolor='rgba(15,15,15,0.78)', bordercolor='#555',
        borderwidth=1, font=dict(size=11, color='#eee'),
    )

# --- تنسيق عام ---
x_range = [df['x'].iloc[0] - spacing, df['x'].iloc[-1] + spacing]
fig.update_xaxes(type='date', range=x_range, row=1, col=1,
                 showgrid=True, gridcolor='rgba(255,255,255,0.04)')
fig.update_xaxes(type='date', range=x_range, row=2, col=1,
                 title='الزمن — العرض ∝ السيولة',
                 showgrid=True, gridcolor='rgba(255,255,255,0.04)')
fig.update_yaxes(title='السعر (USDT)', row=1, col=1,
                 showgrid=True, gridcolor='rgba(255,255,255,0.04)')
fig.update_yaxes(title='Λ (norm)', row=2, col=1, range=[0, 1.1],
                 showgrid=True, gridcolor='rgba(255,255,255,0.04)')

fig.update_layout(
    title=dict(
        text=f"<b>{symbol} · {timeframe}</b> — Candle Width = Liquidity",
        x=0.5, xanchor='center', font=dict(size=18)
    ),
    template='plotly_dark',
    height=900,
    showlegend=False,
    bargap=0.05,
    margin=dict(l=60, r=30, t=80, b=50),
)

fig.show()
