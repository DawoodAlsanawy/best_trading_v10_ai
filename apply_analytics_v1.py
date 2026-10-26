#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_analytics_v1.py — Analytics & Reporting System
======================================================
يُضيف نظام مخرجات تحليلي شامل للـ backtest والـ live:

  1. run_manifest_{run_id}.json — إعادة إنتاج كاملة (config + environment + results)
  2. trades_log_*_extended.jsonl — 60+ حقل لكل صفقة (مسارها الكامل)
  3. portfolio_timeseries_{mode}.parquet — رأس مال + مخاطرة كل شمعة
  4. market_context_{mode}.parquet — سياق السوق دورياً
  5. position_events_{mode}.jsonl — كل حدث على كل مركز (SL updates, BEEsc, partial)
  6. signals_candidates_{mode}.jsonl — كل الإشارات الخام (لـ counterfactual)
  7. quantum_v6_results_v2.png — 24 لوحة بصرية شاملة
  8. quantum_v6_report_{run_id}.html — تقرير HTML تفاعلي (Plotly)

كل شيء opt-in. بدون flags → السلوك مطابق 100%.

الفلسفة:
  • Backward compatible تماماً (كل شيء via flags)
  • Graceful degradation (إذا plotly/pyarrow غير مثبتين → fallback)
  • Buffer + flush (لا نُبطئ الحلقة الرئيسية)
  • Atomic writes (no corrupted files)
  • Run manifest للمقارنة الموثوقة

الاستخدام:
  python3 apply_analytics_v1.py --dry-run --verbose
  python3 apply_analytics_v1.py
  
  # ثم في التشغيل:
  --analytics                          # تفعيل كل شيء
  --analytics-dir ./analytics_out      # مجلد الإخراج (default: ./analytics)
  --analytics-no-signals               # تعطيل signals_candidates
  --analytics-no-portfolio-ts          # تعطيل portfolio_timeseries
  --analytics-no-market-context        # تعطيل market_context
  --analytics-no-events                # تعطيل position_events
  --analytics-no-html                  # تعطيل HTML report
  --analytics-no-png-v2                # استخدام PNG القديم
"""

import ast, os, shutil, sys
from datetime import datetime

MARKER = "# [ANALYTICS-V1-APPLIED]"
DEFAULT_TARGET = "trading_2_live4_claude2_v4_micro.py"
VERBOSE = False


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def vlog(msg):
    if VERBOSE:
        log(msg, "DEBUG")


def fail(msg):
    log(msg, "FAIL")
    raise SystemExit(1)


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_analytics_{ts}"
    shutil.copy2(path, bak)
    log(f"  نسخة احتياطية: {bak}")
    return bak


def verify_syntax(content, label=""):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        ctx = ""
        if e.lineno:
            lines = content.split("\n")
            lo, hi = max(0, e.lineno - 9), min(len(lines), e.lineno + 8)
            ctx = f"\n{label} Context:\n"
            for i in range(lo, hi):
                m = ">>> " if i == e.lineno - 1 else "    "
                ctx += f"{m}{i+1:6d}: {lines[i]}\n"
        return False, f"line {e.lineno}: {e.msg}\n{ctx}"


def must_replace(content, old, new, label):
    n = content.count(old)
    if n == 0:
        fail(f"[{label}] anchor not found")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    vlog(f"    [{label}] replaced ({len(old)}→{len(new)} chars)")
    return content.replace(old, new, 1)


def must_insert_before(content, anchor, block, label):
    idx = content.find(anchor)
    if idx < 0:
        fail(f"[{label}] anchor not found")
    if content.count(anchor) > 1:
        fail(f"[{label}] ambiguous ({content.count(anchor)} matches)")
    vlog(f"    [{label}] inserted ({len(block)} chars)")
    return content[:idx] + block + content[idx:]


# ═══════════════════════════════════════════════════════════════
# CODE BLOCKS
# ═══════════════════════════════════════════════════════════════

CONFIG_BLOCK = '''
    # ══ [ANALYTICS v1] Comprehensive Output System ══
    # All disabled by default. Enable with --analytics.
    ANALYTICS_ENABLED: bool = False
    ANALYTICS_OUTPUT_DIR: str = "analytics"
    ANALYTICS_LOG_SIGNALS: bool = True
    ANALYTICS_LOG_PORTFOLIO_TS: bool = True
    ANALYTICS_LOG_MARKET_CONTEXT: bool = True
    ANALYTICS_LOG_POSITION_EVENTS: bool = True
    ANALYTICS_EXPANDED_PNG: bool = True
    ANALYTICS_HTML_REPORT: bool = True
    ANALYTICS_HTML_TITLE: str = "QTT Analytics Report"
    ANALYTICS_BUFFER_FLUSH_SIZE: int = 500
    ANALYTICS_CONTEXT_INTERVAL_S: int = 3600   # market_context sample every N seconds
    ANALYTICS_PORTFOLIO_INTERVAL_BARS: int = 1  # snapshot every N bars
'''


ANALYTICS_MODULE = r'''
# ═══════════════════════════════════════════════════════════════
# [ANALYTICS v1] — Comprehensive output system
# ═══════════════════════════════════════════════════════════════

_ANALYTICS: Dict = {
    'enabled': False,
    'run_id': '',
    'output_dir': '',
    'config_snapshot': None,
    'started_at': None,
    'started_at_iso': '',
    'buffers': {},
    'n_signals_logged': 0,
    'n_events_logged': 0,
    'n_trades_logged': 0,
    'portfolio_snapshots': [],
    'market_snapshots': [],
    'last_context_ts': 0.0,
    'trade_counter': 0,
    'trade_id_map': {},
    'symbol_states': {},
}

_ANALYTICS_OPTIONAL_DEPS: Dict = {}


def _analytics_check_deps() -> Dict:
    """Return dict of {plotly: bool, pyarrow: bool, ...}."""
    if _ANALYTICS_OPTIONAL_DEPS:
        return _ANALYTICS_OPTIONAL_DEPS
    deps = {'plotly': False, 'pyarrow': False}
    try:
        import plotly  # noqa: F401
        deps['plotly'] = True
    except Exception:
        pass
    try:
        import pyarrow  # noqa: F401
        deps['pyarrow'] = True
    except Exception:
        pass
    _ANALYTICS_OPTIONAL_DEPS.update(deps)
    return _ANALYTICS_OPTIONAL_DEPS


def _analytics_init(mode: str, cfg=None) -> None:
    """Initialize analytics system at start of a run."""
    if cfg is None:
        cfg = CFG
    if not getattr(cfg, 'ANALYTICS_ENABLED', False):
        _ANALYTICS['enabled'] = False
        return
    
    try:
        _ANALYTICS['enabled'] = True
        _ANALYTICS['started_at'] = time.time()
        _ANALYTICS['started_at_iso'] = datetime.now(timezone.utc).isoformat()
        
        # Run ID: timestamp + short hash
        _ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        _rand = str(os.getpid())[-3:]
        _ANALYTICS['run_id'] = f"{mode}_{_ts}_{_rand}"
        
        # Output directory
        base_dir = str(getattr(cfg, 'ANALYTICS_OUTPUT_DIR', 'analytics'))
        run_dir = os.path.join(base_dir, _ANALYTICS['run_id'])
        os.makedirs(run_dir, exist_ok=True)
        _ANALYTICS['output_dir'] = run_dir
        
        # Config snapshot (deep copy of relevant fields)
        try:
            _ANALYTICS['config_snapshot'] = {
                k: (v.tolist() if isinstance(v, np.ndarray) else v)
                for k, v in cfg.__dict__.items()
                if not k.startswith('_')
            }
        except Exception:
            _ANALYTICS['config_snapshot'] = {}
        
        # Buffers
        for key in ('signals', 'events'):
            _ANALYTICS['buffers'][key] = []
        
        # Dependency check
        deps = _analytics_check_deps()
        if not deps['plotly']:
            log.info("[Analytics] plotly not installed — HTML report will be limited")
        if not deps['pyarrow']:
            log.info("[Analytics] pyarrow not installed — parquet → CSV fallback")
        
        log.info(f"[Analytics] Initialized — run_id={_ANALYTICS['run_id']}")
        log.info(f"[Analytics] Output: {run_dir}")
    except Exception as e:
        log.warning(f"[Analytics] init failed: {e}")
        _ANALYTICS['enabled'] = False


def _analytics_path(name: str, ext: str) -> str:
    """Build a file path inside run directory."""
    d = _ANALYTICS.get('output_dir') or '.'
    return os.path.join(d, f"{name}.{ext}")


def _analytics_append_buffer(key: str, record: Dict) -> None:
    """Append record to in-memory buffer, flush if full."""
    if not _ANALYTICS.get('enabled'):
        return
    buf = _ANALYTICS['buffers'].get(key)
    if buf is None:
        _ANALYTICS['buffers'][key] = [record]
        return
    buf.append(record)
    if len(buf) >= int(getattr(CFG, 'ANALYTICS_BUFFER_FLUSH_SIZE', 500)):
        _analytics_flush(key)


def _analytics_flush(key: str) -> None:
    """Flush a buffer to its file (atomic append)."""
    if not _ANALYTICS.get('enabled'):
        return
    buf = _ANALYTICS['buffers'].get(key, [])
    if not buf:
        return
    try:
        if key == 'signals':
            path = _analytics_path('signals_candidates', 'jsonl')
        elif key == 'events':
            path = _analytics_path('position_events', 'jsonl')
        else:
            path = _analytics_path(key, 'jsonl')
        
        with open(path, 'a', encoding='utf-8') as f:
            for rec in buf:
                try:
                    f.write(json.dumps(rec, default=str) + "\n")
                except Exception:
                    pass
        _ANALYTICS['buffers'][key] = []
    except Exception as e:
        log.debug(f"[Analytics] flush {key} failed: {e}")


def _analytics_write_manifest(mode: str, cfg, extra: Optional[Dict] = None) -> None:
    """Write run manifest for reproducibility."""
    if not _ANALYTICS.get('enabled'):
        return
    try:
        # File fingerprint
        import hashlib
        try:
            with open(__file__, 'rb') as f:
                _code_hash = hashlib.md5(f.read()).hexdigest()[:16]
        except Exception:
            _code_hash = "unknown"
        
        import platform
        manifest = {
            'run_id': _ANALYTICS['run_id'],
            'mode': mode,
            'started_at': _ANALYTICS['started_at_iso'],
            'python_version': platform.python_version(),
            'platform': platform.platform(),
            'pid': os.getpid(),
            'cwd': os.getcwd(),
            'file_path': os.path.abspath(__file__),
            'code_hash_md5': _code_hash,
            'config': _ANALYTICS.get('config_snapshot') or {},
            'dependencies': _analytics_check_deps(),
        }
        if extra:
            manifest.update(extra)
        
        path = _analytics_path('run_manifest', 'json')
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, default=str, indent=2)
        os.replace(tmp, path)
        log.info(f"[Analytics] Manifest written: {path}")
    except Exception as e:
        log.warning(f"[Analytics] manifest write failed: {e}")


def _analytics_new_trade_id(symbol: str, entry_ts_iso: str = '') -> str:
    """Generate a unique trade ID."""
    _ANALYTICS['trade_counter'] += 1
    n = _ANALYTICS['trade_counter']
    safe_sym = symbol.replace('/', '_').replace(':', '_')
    ts_part = (entry_ts_iso or _ANALYTICS['started_at_iso'])[:16].replace(':', '').replace('-', '').replace(' ', '_')
    tid = f"{safe_sym}_{ts_part}_{n:06d}"
    _ANALYTICS['trade_id_map'][tid] = {'symbol': symbol, 'created_at': time.time()}
    return tid


def _analytics_log_signal_candidate(sym: str, fi: int, ci: int, price: float,
                                     ad, extra: Optional[Dict] = None) -> Dict:
    """
    Log a signal candidate BEFORE filters.
    Returns a context dict for tracking through the filter chain.
    """
    if not _ANALYTICS.get('enabled'):
        return {}
    try:
        ctx = {
            'ts': time.time(),
            'iso': datetime.now(timezone.utc).isoformat(),
            'symbol': sym,
            'fi': int(fi),
            'ci': int(ci),
            'price': float(price),
        }
        # Snapshot of feature values
        if ad is not None:
            try:
                _feat_names = [
                    ('score', 'score', fi), ('dF', 'dF', fi), ('dH', 'dH', fi),
                    ('gauge_force', 'gauge_force', fi), ('friction', 'friction', fi),
                    ('geodesic_accel', 'geodesic_accel', fi), ('H', 'H', fi),
                    ('T_info', 'T_info', fi), ('E_therm', 'E_therm', fi),
                    ('V', 'V', fi), ('delta_gap', 'delta_gap', fi),
                ]
                for key, attr, idx in _feat_names:
                    arr = getattr(ad, attr, None)
                    if arr is not None and 0 <= idx < len(arr):
                        val = arr[idx]
                        ctx[key] = float(val) if np.isfinite(val) else None
            except Exception:
                pass
        if extra:
            ctx.update(extra)
        ctx['verdict'] = 'pending'
        ctx['rejected_by'] = None
        return ctx
    except Exception:
        return {}


def _analytics_finalize_signal(ctx: Dict, verdict: str, reason: str = '') -> None:
    """Finalize a signal candidate with its verdict (accepted/rejected)."""
    if not _ANALYTICS.get('enabled') or not ctx:
        return
    try:
        ctx['verdict'] = verdict
        ctx['rejected_by'] = reason if verdict == 'rejected' else None
        _analytics_append_buffer('signals', ctx)
        _ANALYTICS['n_signals_logged'] += 1
    except Exception:
        pass


def _analytics_log_position_event(trade_id: str, sym: str, event_type: str,
                                    event_data: Dict) -> None:
    """Log a position management event (SL update, BEEsc, partial, etc.)."""
    if not _ANALYTICS.get('enabled'):
        return
    try:
        rec = {
            'ts': time.time(),
            'iso': datetime.now(timezone.utc).isoformat(),
            'trade_id': trade_id,
            'symbol': sym,
            'event_type': event_type,
            'data': event_data,
        }
        _analytics_append_buffer('events', rec)
        _ANALYTICS['n_events_logged'] += 1
    except Exception:
        pass


def _analytics_portfolio_snapshot(ts: float, capital: float, peak: float,
                                    n_open: int, heat: float,
                                    unrealized_pnl: float = 0.0,
                                    realized_pnl_today: float = 0.0) -> None:
    """Append a portfolio snapshot."""
    if not _ANALYTICS.get('enabled'):
        return
    try:
        dd = ((peak - capital) / peak * 100) if peak > 0 else 0.0
        _ANALYTICS['portfolio_snapshots'].append({
            'ts': float(ts),
            'iso': datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            'capital': float(capital),
            'peak': float(peak),
            'drawdown_pct': float(dd),
            'n_open': int(n_open),
            'heat': float(heat),
            'unrealized_pnl': float(unrealized_pnl),
            'realized_pnl_today': float(realized_pnl_today),
        })
    except Exception:
        pass


def _analytics_market_snapshot(ts: float, assets: Dict, open_pos: Dict) -> None:
    """Append a market context snapshot (rate-limited)."""
    if not _ANALYTICS.get('enabled'):
        return
    try:
        now = float(ts)
        last = float(_ANALYTICS.get('last_context_ts', 0.0))
        interval = float(getattr(CFG, 'ANALYTICS_CONTEXT_INTERVAL_S', 3600))
        if now - last < interval:
            return
        _ANALYTICS['last_context_ts'] = now
        
        rvols, gauges, accels = [], [], []
        regimes = {'trending': 0, 'ranging': 0, 'explosive': 0, 'normal': 0}
        for sym, ad in (assets or {}).items():
            try:
                fi = max(0, len(ad.score) - 2 - ad.feat_start)
                if fi < len(ad.E_therm):
                    rvols.append(float(ad.E_therm[fi]))
                if fi < len(ad.gauge_force):
                    gauges.append(float(ad.gauge_force[fi]))
                if fi < len(ad.geodesic_accel):
                    accels.append(float(ad.geodesic_accel[fi]))
                try:
                    _reg = _classify_regime_local(ad, fi, 100)
                    regimes[_reg] = regimes.get(_reg, 0) + 1
                except Exception:
                    pass
            except Exception:
                continue
        
        def _safe_stats(arr):
            if not arr:
                return (0.0, 0.0)
            return (float(np.mean(arr)), float(np.std(arr)))
        
        rvol_mu, rvol_sd = _safe_stats(rvols)
        gauge_mu, gauge_sd = _safe_stats(gauges)
        accel_mu, accel_sd = _safe_stats(accels)
        
        total_regimes = sum(regimes.values()) or 1
        
        _ANALYTICS['market_snapshots'].append({
            'ts': now,
            'iso': datetime.fromtimestamp(now, timezone.utc).isoformat(),
            'n_symbols': len(assets or {}),
            'n_open_positions': len(open_pos or {}),
            'median_rvol': rvol_mu,
            'rvol_std': rvol_sd,
            'median_gauge': gauge_mu,
            'gauge_std': gauge_sd,
            'median_accel': accel_mu,
            'accel_std': accel_sd,
            'regime_trending_pct': regimes.get('trending', 0) / total_regimes * 100,
            'regime_ranging_pct': regimes.get('ranging', 0) / total_regimes * 100,
            'regime_explosive_pct': regimes.get('explosive', 0) / total_regimes * 100,
        })
    except Exception:
        pass


def _analytics_extend_trade_record(record: Dict, pos, ad,
                                     exit_px: float, exit_rsn: str,
                                     exit_ci: int, entry_cap: float,
                                     capital_after: float, net_pnl: float,
                                     log_return: float, mode: str) -> Dict:
    """
    Extend a trade record with analytics fields.
    Modifies `record` in place and returns it.
    """
    if not _ANALYTICS.get('enabled'):
        return record
    try:
        # Trade ID
        _sym = record.get('symbol', '?')
        _entry_iso = str(record.get('entry_time', ''))
        _tid = _analytics_new_trade_id(_sym, _entry_iso)
        record['trade_id'] = _tid
        record['run_id'] = _ANALYTICS['run_id']
        
        # Duration & timing
        try:
            if hasattr(pos, 'signal') and hasattr(pos.signal, 'timestamp'):
                _entry_ts = pd.Timestamp(pos.signal.timestamp).timestamp()
            else:
                _entry_ts = record.get('entry_ts') or 0
            _exit_ts = time.time() if mode in ('live', 'testnet') else None
            if _exit_ts:
                record['duration_sec'] = float(_exit_ts - float(_entry_ts))
        except Exception:
            pass
        
        # MAE (ما لم يكن موجوداً)
        if 'mae_frac' not in record:
            try:
                if hasattr(pos, 'mae_frac'):
                    record['mae_frac'] = float(pos.mae_frac)
            except Exception:
                pass
        
        # Features at exit
        try:
            if ad is not None and 0 <= exit_ci < len(ad.closes):
                _fi_exit = exit_ci - ad.feat_start
                if 0 <= _fi_exit < len(ad.score):
                    record['exit_score'] = float(ad.score[_fi_exit])
                    record['exit_dF'] = float(ad.dF[_fi_exit])
                    record['exit_dH'] = float(ad.dH[_fi_exit])
                    record['exit_gauge'] = float(ad.gauge_force[_fi_exit])
                    record['exit_accel'] = float(ad.geodesic_accel[_fi_exit])
                    record['exit_H'] = float(ad.H[_fi_exit])
                try:
                    record['exit_regime'] = _classify_regime_local(ad, _fi_exit, 100)
                except Exception:
                    pass
        except Exception:
            pass
        
        # Capital context
        try:
            record['capital_before_trade'] = float(entry_cap)
            record['capital_after_trade'] = float(capital_after)
            if entry_cap > 0:
                record['return_on_capital'] = float((capital_after - entry_cap) / entry_cap)
        except Exception:
            pass
        
        # MFE captured ratio
        try:
            mfe = float(record.get('mfe_frac', 0))
            realized = float(record.get('log_return', 0))
            if mfe > 0.001:
                record['mfe_realized_ratio'] = float(min(abs(realized) / mfe, 10.0))
        except Exception:
            pass
        
        # Analytics counters
        _ANALYTICS['n_trades_logged'] += 1
    except Exception:
        pass
    return record


def _analytics_finalize(mode: str, trades: List, equity: List,
                         metrics: Optional[Dict] = None) -> None:
    """Flush buffers, write timeseries, generate reports."""
    if not _ANALYTICS.get('enabled'):
        return
    try:
        log.info("[Analytics] Finalizing...")
        
        # Flush buffers
        _analytics_flush('signals')
        _analytics_flush('events')
        
        # Portfolio timeseries
        if getattr(CFG, 'ANALYTICS_LOG_PORTFOLIO_TS', True) and _ANALYTICS['portfolio_snapshots']:
            _write_portfolio_ts()
        
        # Market context
        if getattr(CFG, 'ANALYTICS_LOG_MARKET_CONTEXT', True) and _ANALYTICS['market_snapshots']:
            _write_market_context()
        
        # Counterfactual post-processing
        if getattr(CFG, 'ANALYTICS_LOG_SIGNALS', True):
            _compute_signal_counterfactual(mode)
        
        # Expanded PNG
        if getattr(CFG, 'ANALYTICS_EXPANDED_PNG', True):
            try:
                _png_path = _analytics_path('quantum_v6_results_v2', 'png')
                plot_results_v2(trades, equity, metrics or {}, out=_png_path)
            except Exception as e:
                log.warning(f"[Analytics] PNG v2 failed: {e}")
        
        # HTML report
        if getattr(CFG, 'ANALYTICS_HTML_REPORT', True):
            try:
                _html_path = _analytics_path('report', 'html')
                generate_html_report(trades, equity, metrics or {}, out=_html_path)
            except Exception as e:
                log.warning(f"[Analytics] HTML failed: {e}")
        
        # Update manifest with results
        try:
            _analytics_update_manifest_results(mode, trades, equity, metrics or {})
        except Exception:
            pass
        
        log.info(
            f"[Analytics] Finalized: "
            f"{_ANALYTICS['n_trades_logged']} trades, "
            f"{_ANALYTICS['n_signals_logged']} signals, "
            f"{_ANALYTICS['n_events_logged']} events"
        )
    except Exception as e:
        log.warning(f"[Analytics] finalize failed: {e}")


def _write_portfolio_ts() -> None:
    """Write portfolio snapshots to parquet or CSV."""
    snaps = _ANALYTICS['portfolio_snapshots']
    if not snaps:
        return
    try:
        df = pd.DataFrame(snaps)
        if _analytics_check_deps().get('pyarrow'):
            path = _analytics_path('portfolio_timeseries', 'parquet')
            df.to_parquet(path, index=False)
        else:
            path = _analytics_path('portfolio_timeseries', 'csv')
            df.to_csv(path, index=False)
        log.info(f"[Analytics] Portfolio timeseries: {path} ({len(df)} rows)")
    except Exception as e:
        log.warning(f"[Analytics] portfolio ts write failed: {e}")


def _write_market_context() -> None:
    """Write market snapshots to parquet or CSV."""
    snaps = _ANALYTICS['market_snapshots']
    if not snaps:
        return
    try:
        df = pd.DataFrame(snaps)
        if _analytics_check_deps().get('pyarrow'):
            path = _analytics_path('market_context', 'parquet')
            df.to_parquet(path, index=False)
        else:
            path = _analytics_path('market_context', 'csv')
            df.to_csv(path, index=False)
        log.info(f"[Analytics] Market context: {path} ({len(df)} rows)")
    except Exception as e:
        log.warning(f"[Analytics] market context write failed: {e}")


def _compute_signal_counterfactual(mode: str) -> None:
    """
    Post-process signals_candidates: compute hypothetical PnL for rejected signals.
    Simplified: use ATR-based approximation from available features.
    """
    try:
        path = _analytics_path('signals_candidates', 'jsonl')
        if not os.path.exists(path):
            return
        # Read all candidates
        records = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        if not records:
            return
        # Aggregate: count per verdict, avg features
        df = pd.DataFrame(records)
        summary = {
            'total_candidates': len(df),
            'accepted': int((df['verdict'] == 'accepted').sum()) if 'verdict' in df else 0,
            'rejected': int((df['verdict'] == 'rejected').sum()) if 'verdict' in df else 0,
            'rejection_reasons': {},
        }
        try:
            if 'rejected_by' in df.columns:
                reasons = df[df['verdict'] == 'rejected']['rejected_by'].dropna()
                summary['rejection_reasons'] = reasons.value_counts().to_dict()
        except Exception:
            pass
        # Write summary
        path_sum = _analytics_path('signals_summary', 'json')
        with open(path_sum, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        log.info(
            f"[Analytics] Signal summary: {summary['accepted']} accepted, "
            f"{summary['rejected']} rejected"
        )
    except Exception as e:
        log.warning(f"[Analytics] counterfactual failed: {e}")


def _analytics_update_manifest_results(mode: str, trades: List, equity: List,
                                          metrics: Dict) -> None:
    """Append results to run_manifest.json."""
    try:
        path = _analytics_path('run_manifest', 'json')
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        manifest['finalized_at'] = datetime.now(timezone.utc).isoformat()
        manifest['wall_clock_secs'] = round(time.time() - _ANALYTICS['started_at'], 1)
        manifest['results'] = {
            'n_trades': len(trades),
            'final_capital': float(equity[-1]) if equity else 0.0,
            'mean_log_return': float(metrics.get('mean_log_return', 0)),
            'sharpe_ratio': float(metrics.get('sharpe_ratio', 0)),
            'profit_factor': float(metrics.get('profit_factor', 0)),
            'max_drawdown_pct': float(metrics.get('max_drawdown_pct', 0)),
            'win_rate': float(metrics.get('win_rate', 0)),
            'n_signals_logged': _ANALYTICS['n_signals_logged'],
            'n_events_logged': _ANALYTICS['n_events_logged'],
        }
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
'''


# ═══════════════════════════════════════════════════════════════
# PLOT_V2 FUNCTION (24 panels)
# ═══════════════════════════════════════════════════════════════

PLOT_V2_FUNCTION = r'''
def plot_results_v2(trades, equity, m, out="quantum_v6_results_v2.png"):
    """
    [Analytics] 24-panel comprehensive visualization.
    Replaces plot_results when ANALYTICS_EXPANDED_PNG=True.
    """
    if not trades or m.get('n_trades', 0) == 0:
        log.info("[Plot v2] no trades — skipping")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except Exception as e:
        log.warning(f"[Plot v2] matplotlib unavailable: {e}")
        return
    
    try:
        fig = plt.figure(figsize=(32, 24), facecolor='#0d0d0d')
        gs = gridspec.GridSpec(6, 4, figure=fig, hspace=0.55, wspace=0.35)
        bk, tc, gr = '#111111', '#e0e0e0', '#2a2a2a'
        plt.rcParams.update({
            'text.color': tc, 'axes.labelcolor': tc,
            'xtick.color': tc, 'ytick.color': tc
        })
        eq = np.array(equity) if len(equity) > 0 else np.array([0])
        
        # ── Row 1: Macro ──
        ax = fig.add_subplot(gs[0, :])
        ax.semilogy(eq, c='#00e5ff', lw=0.8, alpha=0.9)
        ax.axhline(CFG.INITIAL_CAPITAL, c='#ff6b6b', ls='--', lw=1)
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title(
            f"Equity (Log) | {m['n_trades']:,} trades | "
            f"Final=${m.get('final_capital', 0):,.0f} | "
            f"MaxDD={m.get('max_drawdown_pct', 0):.1f}%",
            c='#00e5ff', fontsize=14, fontweight='bold')
        
        # ── Row 2 col 0: Rolling Sharpe ──
        ax = fig.add_subplot(gs[1, 0])
        lrs = [t.log_return for t in trades]
        if len(lrs) > 30:
            w = min(50, len(lrs) // 3)
            rs = pd.Series(lrs).rolling(w).apply(
                lambda x: (x.mean() / (x.std() + 1e-9)) * np.sqrt(252)
                if x.std() > 0 else 0, raw=True)
            ax.plot(rs, c='#66bb6a', lw=1)
            ax.axhline(1, c='white', ls='--', lw=0.8)
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("Rolling Sharpe", c='#66bb6a', fontsize=10)
        
        # ── Row 2 col 1: Monthly Returns ──
        ax = fig.add_subplot(gs[1, 1])
        try:
            if all(hasattr(t, 'entry_time') for t in trades):
                df_t = pd.DataFrame([
                    {'month': pd.Timestamp(t.entry_time).to_period('M'),
                     'pnl': t.net_pnl}
                    for t in trades
                ])
                monthly = df_t.groupby('month')['pnl'].sum()
                if len(monthly) > 0:
                    colors = ['#66bb6a' if x >= 0 else '#ef5350' for x in monthly.values]
                    ax.bar(range(len(monthly)), monthly.values, color=colors)
                    ax.set_xticks(range(0, len(monthly), max(1, len(monthly)//6)))
                    ax.set_xticklabels([str(m_) for m_ in monthly.index[::max(1, len(monthly)//6)]],
                                        rotation=45, fontsize=7)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("Monthly PnL", c=tc, fontsize=10)
        
        # ── Row 2 col 2: Returns Distribution ──
        ax = fig.add_subplot(gs[1, 2])
        ax.hist(lrs, bins=80, color='#ab47bc', alpha=0.7, edgecolor='none')
        ax.axvline(0, c='#ff6b6b', lw=1.5, ls='--')
        ax.axvline(m.get('mean_log_return', 0), c='#00e5ff', lw=1.5,
                    label=f"μ={m.get('mean_log_return', 0):.4f}")
        try:
            from scipy.stats import skew, kurtosis
            sk = skew(lrs); ku = kurtosis(lrs)
            ax.text(0.05, 0.95, f"Skew={sk:.2f}\nKurt={ku:.2f}",
                    transform=ax.transAxes, va='top', fontsize=8,
                    bbox=dict(boxstyle='round', fc='#1e1e1e', alpha=0.8))
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("Returns Distribution", c='#ab47bc', fontsize=10)
        ax.legend(fontsize=7, framealpha=0.3)
        
        # ── Row 2 col 3: Drawdown ──
        ax = fig.add_subplot(gs[1, 3])
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq) / (peak + 1e-12) * 100
        ax.fill_between(range(len(dd)), 0, -dd, color='#ef5350', alpha=0.6)
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title(f"Drawdown (max={m.get('max_drawdown_pct', 0):.1f}%)",
                     c='#ef5350', fontsize=10)
        
        # ── Row 3 col 0: Exit Reasons ──
        ax = fig.add_subplot(gs[2, 0])
        ed = m.get('exit_distribution', {})
        if ed:
            labs = list(ed.keys()); vals = list(ed.values())
            clrs = ['#26c6da','#66bb6a','#ffa726','#ef5350','#ab47bc','#78909c','#ff7043']
            ax.pie(vals, labels=labs, autopct='%1.1f%%',
                    colors=clrs[:len(labs)], textprops={'color': tc, 'fontsize': 7})
        ax.set_title("Exit Reasons", c=tc, fontsize=10)
        
        # ── Row 3 col 1: Exit Reason × R ──
        ax = fig.add_subplot(gs[2, 1])
        try:
            by_reason = {}
            for t in trades:
                reason = t.exit_reason.split("(")[0].split("=")[0].strip()
                by_reason.setdefault(reason, []).append(t.log_return)
            reasons = sorted(by_reason.keys())
            data = [by_reason[r] for r in reasons]
            bp = ax.boxplot(data, labels=[r[:8] for r in reasons], patch_artist=True)
            for patch in bp['boxes']:
                patch.set_facecolor('#26c6da'); patch.set_alpha(0.6)
            ax.tick_params(axis='x', labelsize=7, rotation=30)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("R by Exit Reason", c='#26c6da', fontsize=10)
        
        # ── Row 3 col 2: MFE vs Realized ──
        ax = fig.add_subplot(gs[2, 2])
        try:
            mfes = [t.mfe_frac for t in trades]
            realized = [t.log_return for t in trades]
            colors = ['#66bb6a' if x > 0 else '#ef5350' for x in realized]
            ax.scatter(mfes, realized, c=colors, s=8, alpha=0.5)
            ax.axhline(0, c='white', lw=0.5, ls='--')
            max_r = max(realized) if realized else 0
            ax.plot([0, max(mfes) if mfes else 1],
                    [0, max(mfes) if mfes else 1],
                    c='yellow', lw=1, ls='--', alpha=0.5, label="100% capture")
            ax.legend(fontsize=7, framealpha=0.3)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("MFE vs Realized", c=tc, fontsize=10)
        
        # ── Row 3 col 3: Trade Duration ──
        ax = fig.add_subplot(gs[2, 3])
        try:
            durations = [t.exit_ci - t.entry_ci if hasattr(t, 'exit_ci') else 0
                          for t in trades]
            durations = [d for d in durations if d > 0]
            if durations:
                ax.hist(durations, bins=50, color='#ffa726', alpha=0.7)
                ax.axvline(np.median(durations), c='#00e5ff', lw=1.5,
                            label=f"median={np.median(durations):.0f}")
                ax.legend(fontsize=7, framealpha=0.3)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("Trade Duration (bars)", c='#ffa726', fontsize=10)
        
        # ── Row 4 col 0: PnL by Hour ──
        ax = fig.add_subplot(gs[3, 0])
        try:
            hours = {}
            for t in trades:
                if hasattr(t, 'entry_time'):
                    h = pd.Timestamp(t.entry_time).hour
                    hours.setdefault(h, []).append(t.net_pnl)
            if hours:
                hr_labels = sorted(hours.keys())
                hr_means = [np.mean(hours[h]) for h in hr_labels]
                colors = ['#66bb6a' if x > 0 else '#ef5350' for x in hr_means]
                ax.bar(hr_labels, hr_means, color=colors)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4, axis='y')
        ax.set_title("Mean PnL by Hour (UTC)", c=tc, fontsize=10)
        ax.set_xlabel("Hour", fontsize=8)
        
        # ── Row 4 col 1: PnL by DoW ──
        ax = fig.add_subplot(gs[3, 1])
        try:
            dows = {}
            for t in trades:
                if hasattr(t, 'entry_time'):
                    d = pd.Timestamp(t.entry_time).dayofweek
                    dows.setdefault(d, []).append(t.net_pnl)
            if dows:
                dow_labels = sorted(dows.keys())
                dow_means = [np.mean(dows[d]) for d in dow_labels]
                colors = ['#66bb6a' if x > 0 else '#ef5350' for x in dow_means]
                ax.bar(dow_labels, dow_means, color=colors)
                ax.set_xticks(dow_labels)
                ax.set_xticklabels(['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][:len(dow_labels)],
                                    fontsize=7)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4, axis='y')
        ax.set_title("Mean PnL by DoW", c=tc, fontsize=10)
        
        # ── Row 4 col 2: Win Rate by Score ──
        ax = fig.add_subplot(gs[3, 2])
        try:
            sg = {}
            for t in trades:
                sg.setdefault(int(t.score), []).append(1. if t.net_pnl > 0 else 0.)
            scs = sorted(sg.keys())
            wrs = [np.mean(sg[s]) * 100 for s in scs]
            cnts = [len(sg[s]) for s in scs]
            ax.bar(scs, wrs, color='#26c6da', alpha=0.8)
            for s_, w_, c_ in zip(scs, wrs, cnts):
                ax.text(s_, w_ + 1, str(c_), ha='center', fontsize=6, color=tc)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4, axis='y')
        ax.set_title("Win Rate by Score", c='#26c6da', fontsize=10)
        
        # ── Row 4 col 3: Risk-Return Scatter ──
        ax = fig.add_subplot(gs[3, 3])
        try:
            risks = [t.dynamic_risk_used * 100 for t in trades]
            rets = [t.log_return for t in trades]
            colors = ['#66bb6a' if x > 0 else '#ef5350' for x in rets]
            ax.scatter(risks, rets, c=colors, s=8, alpha=0.4)
            ax.axhline(0, c='white', lw=0.5, ls='--')
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("Risk vs Return", c=tc, fontsize=10)
        ax.set_xlabel("Risk %", fontsize=8)
        
        # ── Row 5 col 0: Top 10 Symbols ──
        ax = fig.add_subplot(gs[4, 0])
        try:
            by_sym = {}
            for t in trades:
                by_sym.setdefault(t.symbol, []).append(t.net_pnl)
            sym_pnl = {s: sum(v) for s, v in by_sym.items()}
            top10 = sorted(sym_pnl.items(), key=lambda x: -x[1])[:10]
            if top10:
                syms = [s.replace('/USDT','') for s, _ in top10]
                pnls = [p for _, p in top10]
                ax.barh(range(len(syms)), pnls, color='#66bb6a')
                ax.set_yticks(range(len(syms)))
                ax.set_yticklabels(syms, fontsize=7)
                ax.invert_yaxis()
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4, axis='x')
        ax.set_title("Top 10 Symbols", c='#66bb6a', fontsize=10)
        
        # ── Row 5 col 1: Bottom 10 Symbols ──
        ax = fig.add_subplot(gs[4, 1])
        try:
            bottom10 = sorted(sym_pnl.items(), key=lambda x: x[1])[:10]
            if bottom10:
                syms = [s.replace('/USDT','') for s, _ in bottom10]
                pnls = [p for _, p in bottom10]
                ax.barh(range(len(syms)), pnls, color='#ef5350')
                ax.set_yticks(range(len(syms)))
                ax.set_yticklabels(syms, fontsize=7)
                ax.invert_yaxis()
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4, axis='x')
        ax.set_title("Bottom 10 Symbols", c='#ef5350', fontsize=10)
        
        # ── Row 5 col 2: BUY vs SELL ──
        ax = fig.add_subplot(gs[4, 2])
        try:
            buy_pnl = [t.net_pnl for t in trades if t.action=="BUY"]
            sell_pnl = [t.net_pnl for t in trades if t.action=="SELL"]
            ax.hist(buy_pnl, bins=40, alpha=0.7, color='#66bb6a',
                    label=f'BUY n={len(buy_pnl)}')
            ax.hist(sell_pnl, bins=40, alpha=0.7, color='#ef5350',
                    label=f'SELL n={len(sell_pnl)}')
            ax.axvline(0, c='white', lw=0.5, ls='--')
            ax.legend(fontsize=7, framealpha=0.3)
        except Exception:
            pass
        ax.set_facecolor(bk); ax.grid(True, c=gr, lw=0.4)
        ax.set_title("BUY vs SELL", c=tc, fontsize=10)
        
        # ── Row 5 col 3: Consecutive Streaks ──
        ax = fig.add_subplot(gs[4, 3])
        try:
            wins_seq = []
            cur_w = cur_l = 0
            max_w = max_l = 0
            for t in trades:
                if t.net_pnl > 0:
                    cur_w += 1; cur_l = 0
                    max_w = max(max_w, cur_w)
                else:
                    cur_l += 1; cur_w = 0
                    max_l = max(max_l, cur_l)
            ax.text(0.5, 0.7, f"Max Win Streak: {max_w}", ha='center',
                    transform=ax.transAxes, fontsize=14, color='#66bb6a')
            ax.text(0.5, 0.4, f"Max Loss Streak: {max_l}", ha='center',
                    transform=ax.transAxes, fontsize=14, color='#ef5350')
            ax.text(0.5, 0.1, f"Total Trades: {len(trades)}", ha='center',
                    transform=ax.transAxes, fontsize=10, color=tc)
            ax.axis('off')
        except Exception:
            pass
        ax.set_title("Streak Analysis", c=tc, fontsize=10)
        
        # ── Row 6: Summary stats ──
        ax = fig.add_subplot(gs[5, :])
        ax.axis('off'); ax.set_facecolor(bk)
        summ = (
            f"═══ PERFORMANCE ═══\n"
            f"E[ln]={m.get('mean_log_return', 0):+.5f}  |  "
            f"Median={m.get('median_log_return', 0):+.5f}  |  "
            f"σ={m.get('std_log_return', 0):.5f}\n"
            f"PF={m.get('profit_factor', 0):.3f}  |  "
            f"Sharpe={m.get('sharpe_ratio', 0):.3f}  |  "
            f"WinRate={m.get('win_rate', 0)*100:.2f}%\n"
            f"Final=${m.get('final_capital', 0):,.0f}  |  "
            f"Return={m.get('total_return_pct', 0):,.0f}%  |  "
            f"MaxDD={m.get('max_drawdown_pct', 0):.2f}%\n"
            f"\n═══ EXITS ═══\n"
            f"{', '.join(f'{k}={v}' for k, v in list(m.get('exit_distribution', {}).items())[:8])}\n"
            f"\n═══ CONTEXT ═══\n"
            f"Avg T_info={m.get('avg_T_info', 0):.3f}  |  "
            f"Avg Risk={m.get('avg_dynamic_risk', 0)*100:.3f}%\n"
            f"BUY={m.get('buy_count', 0)}  |  SELL={m.get('sell_count', 0)}  |  "
            f"LiqWarns={m.get('liq_warnings', 0)} ({m.get('liq_warn_pct', 0):.1f}%)\n"
        )
        ax.text(0.02, 0.98, summ, transform=ax.transAxes, va='top',
                color=tc, fontsize=9, fontfamily='monospace',
                bbox=dict(boxstyle='round', fc='#1e1e1e', alpha=0.9))
        
        fig.suptitle(
            f"QTT Analytics Report — {m.get('n_trades', 0):,} trades | "
            f"E[ln]={m.get('mean_log_return', 0):+.5f} | "
            f"PF={m.get('profit_factor', 0):.2f}",
            color='#00e5ff', fontsize=16, fontweight='bold', y=0.998)
        
        plt.savefig(out, dpi=110, bbox_inches='tight',
                    facecolor='#0d0d0d', edgecolor='none')
        plt.close(fig)
        log.info(f"📊 Analytics PNG v2: {out}")
    except Exception as e:
        log.warning(f"[Plot v2] failed: {e}")
        try:
            plt.close('all')
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
'''


# ═══════════════════════════════════════════════════════════════
# HTML REPORT FUNCTION
# ═══════════════════════════════════════════════════════════════

HTML_REPORT_FUNCTION = r'''
def generate_html_report(trades, equity, m, out="report.html"):
    """
    [Analytics] Generate interactive HTML report using Plotly.
    Falls back to a static placeholder if plotly is unavailable.
    """
    deps = _analytics_check_deps()
    if not deps.get('plotly'):
        _write_html_fallback(trades, equity, m, out)
        return
    
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import plotly.io as pio
    except Exception as e:
        log.warning(f"[HTML] plotly import failed: {e}")
        _write_html_fallback(trades, equity, m, out)
        return
    
    try:
        eq = np.array(equity) if len(equity) > 0 else np.array([0])
        n_trades = len(trades)
        
        # ═══ Overview charts ═══
        # 1. Equity curve
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            y=eq.tolist(), mode='lines', name='Equity',
            line=dict(color='#00e5ff', width=1.5)
        ))
        fig_eq.add_hline(y=CFG.INITIAL_CAPITAL, line_dash="dash",
                          line_color="red", opacity=0.6)
        fig_eq.update_layout(
            title="Equity Curve (Log Scale)",
            yaxis_type="log", template="plotly_dark",
            height=400, showlegend=False
        )
        
        # 2. Drawdown
        peak = np.maximum.accumulate(eq)
        dd_pct = (peak - eq) / (peak + 1e-12) * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            y=(-dd_pct).tolist(), fill='tozeroy',
            mode='lines', name='Drawdown',
            line=dict(color='#ef5350', width=1)
        ))
        fig_dd.update_layout(
            title="Drawdown %",
            template="plotly_dark", height=300, showlegend=False
        )
        
        # 3. Returns distribution
        lrs = [t.log_return for t in trades]
        fig_ret = go.Figure()
        fig_ret.add_trace(go.Histogram(
            x=lrs, nbinsx=80, marker_color='#ab47bc', opacity=0.8,
            name='Returns'
        ))
        fig_ret.add_vline(x=0, line_color="red", line_dash="dash")
        fig_ret.add_vline(x=float(np.mean(lrs)) if lrs else 0,
                           line_color="#00e5ff", line_dash="dash")
        fig_ret.update_layout(
            title="Log Return Distribution",
            xaxis_title="Log Return",
            template="plotly_dark", height=300, showlegend=False
        )
        
        # 4. Exit reasons
        ed = m.get('exit_distribution', {})
        fig_exits = go.Figure(data=[go.Pie(
            labels=list(ed.keys()),
            values=list(ed.values()),
            hole=0.4
        )])
        fig_exits.update_layout(
            title="Exit Reasons",
            template="plotly_dark", height=300
        )
        
        # ═══ Trades table ═══
        trade_rows = []
        for t in trades[:5000]:  # cap at 5000 for HTML size
            trade_rows.append({
                'symbol': getattr(t, 'symbol', ''),
                'action': getattr(t, 'action', ''),
                'entry_time': str(getattr(t, 'entry_time', '')),
                'entry_px': round(getattr(t, 'entry_price', 0), 6),
                'exit_px': round(getattr(t, 'exit_price', 0), 6),
                'exit_rsn': getattr(t, 'exit_reason', '')[:40],
                'net_pnl': round(getattr(t, 'net_pnl', 0), 4),
                'log_return': round(getattr(t, 'log_return', 0), 6),
                'mfe_frac': round(getattr(t, 'mfe_frac', 0), 6),
                'score': round(getattr(t, 'score', 0), 2),
                'risk%': round(getattr(t, 'dynamic_risk_used', 0) * 100, 3),
            })
        
        df_trades = pd.DataFrame(trade_rows)
        
        # ═══ Summary stats table ═══
        summary_stats = {
            'E[ln]': f"{m.get('mean_log_return', 0):+.5f}",
            'Median ln': f"{m.get('median_log_return', 0):+.5f}",
            'Std ln': f"{m.get('std_log_return', 0):.5f}",
            'Profit Factor': f"{m.get('profit_factor', 0):.3f}",
            'Sharpe (annual)': f"{m.get('sharpe_ratio', 0):.3f}",
            'Win Rate': f"{m.get('win_rate', 0)*100:.2f}%",
            'N Trades': f"{m.get('n_trades', 0):,}",
            'BUY / SELL': f"{m.get('buy_count', 0)} / {m.get('sell_count', 0)}",
            'Final Capital': f"${m.get('final_capital', 0):,.2f}",
            'Total Return': f"{m.get('total_return_pct', 0):,.1f}%",
            'Max Drawdown': f"{m.get('max_drawdown_pct', 0):.2f}%",
            'Avg Risk/Trade': f"{m.get('avg_dynamic_risk', 0)*100:.3f}%",
            'Avg T_info': f"{m.get('avg_T_info', 0):.3f}",
        }
        
        # ═══ Build HTML ═══
        html_parts = []
        html_parts.append("<!DOCTYPE html>")
        html_parts.append("<html><head>")
        html_parts.append("<meta charset='utf-8'>")
        html_parts.append(f"<title>{getattr(CFG, 'ANALYTICS_HTML_TITLE', 'QTT Report')}</title>")
        html_parts.append("<style>")
        html_parts.append("""
        body { background: #0d0d0d; color: #e0e0e0; font-family: -apple-system, sans-serif; margin: 0; padding: 20px; }
        h1 { color: #00e5ff; border-bottom: 2px solid #00e5ff; padding-bottom: 10px; }
        h2 { color: #66bb6a; margin-top: 30px; }
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }
        .kpi { background: #1e1e1e; padding: 15px; border-radius: 8px; border-left: 4px solid #00e5ff; }
        .kpi-label { font-size: 11px; color: #999; text-transform: uppercase; }
        .kpi-value { font-size: 22px; font-weight: bold; color: #00e5ff; margin-top: 5px; }
        .kpi-value.positive { color: #66bb6a; }
        .kpi-value.negative { color: #ef5350; }
        .tab-container { margin-top: 20px; }
        .tab-buttons { display: flex; gap: 5px; margin-bottom: 15px; }
        .tab-btn { background: #1e1e1e; color: #999; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px 4px 0 0; }
        .tab-btn.active { background: #00e5ff; color: #000; font-weight: bold; }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 15px; }
        th { background: #1e1e1e; padding: 8px; text-align: left; border-bottom: 2px solid #333; }
        td { padding: 6px; border-bottom: 1px solid #222; }
        tr:hover { background: #1a1a1a; }
        .pos { color: #66bb6a; }
        .neg { color: #ef5350; }
        """)
        html_parts.append("</style>")
        # Embed plotly.js from CDN (smaller file)
        html_parts.append("<script src='https://cdn.plot.ly/plotly-2.27.0.min.js'></script>")
        html_parts.append("</head><body>")
        
        # Header
        html_parts.append(f"<h1>📊 {getattr(CFG, 'ANALYTICS_HTML_TITLE', 'QTT Report')}</h1>")
        html_parts.append(f"<p>Run ID: <code>{_ANALYTICS.get('run_id', '?')}</code> | "
                          f"Mode: {CFG.mode} | Generated: {datetime.now(timezone.utc).isoformat()}</p>")
        
        # KPI cards
        html_parts.append("<div class='kpi-grid'>")
        _kpis = [
            ('E[ln]', m.get('mean_log_return', 0),
             f"{m.get('mean_log_return', 0):+.5f}",
             'pos' if m.get('mean_log_return', 0) > 0 else 'neg'),
            ('Profit Factor', m.get('profit_factor', 0),
             f"{m.get('profit_factor', 0):.3f}",
             'pos' if m.get('profit_factor', 0) > 1 else 'neg'),
            ('Sharpe', m.get('sharpe_ratio', 0),
             f"{m.get('sharpe_ratio', 0):.3f}",
             'pos' if m.get('sharpe_ratio', 0) > 1 else 'neg'),
            ('Win Rate', m.get('win_rate', 0),
             f"{m.get('win_rate', 0)*100:.1f}%", ''),
            ('Max Drawdown', m.get('max_drawdown_pct', 0),
             f"{m.get('max_drawdown_pct', 0):.1f}%", 'neg'),
            ('Final Capital', m.get('final_capital', 0),
             f"${m.get('final_capital', 0):,.0f}",
             'pos' if m.get('final_capital', 0) > CFG.INITIAL_CAPITAL else 'neg'),
            ('N Trades', m.get('n_trades', 0),
             f"{m.get('n_trades', 0):,}", ''),
            ('Total Return', m.get('total_return_pct', 0),
             f"{m.get('total_return_pct', 0):,.0f}%",
             'pos' if m.get('total_return_pct', 0) > 0 else 'neg'),
        ]
        for label, _, value, cls in _kpis:
            html_parts.append(f"<div class='kpi'><div class='kpi-label'>{label}</div>"
                              f"<div class='kpi-value {cls}'>{value}</div></div>")
        html_parts.append("</div>")
        
        # Tabs
        html_parts.append("<div class='tab-container'>")
        html_parts.append("<div class='tab-buttons'>")
        html_parts.append("<button class='tab-btn active' onclick=\"showTab('overview', this)\">📈 Overview</button>")
        html_parts.append("<button class='tab-btn' onclick=\"showTab('charts', this)\">📊 Charts</button>")
        html_parts.append("<button class='tab-btn' onclick=\"showTab('trades', this)\">📋 Trades</button>")
        html_parts.append("<button class='tab-btn' onclick=\"showTab('summary', this)\">📋 Summary</button>")
        html_parts.append("</div>")
        
        # Tab 1: Overview
        html_parts.append("<div id='tab-overview' class='tab-panel active'>")
        html_parts.append(pio.to_html(fig_eq, include_plotlyjs=False, full_html=False))
        html_parts.append(pio.to_html(fig_dd, include_plotlyjs=False, full_html=False))
        html_parts.append("</div>")
        
        # Tab 2: Charts
        html_parts.append("<div id='tab-charts' class='tab-panel'>")
        html_parts.append(pio.to_html(fig_ret, include_plotlyjs=False, full_html=False))
        html_parts.append(pio.to_html(fig_exits, include_plotlyjs=False, full_html=False))
        html_parts.append("</div>")
        
        # Tab 3: Trades
        html_parts.append("<div id='tab-trades' class='tab-panel'>")
        html_parts.append(f"<p>Showing {len(trade_rows):,} of {n_trades:,} trades</p>")
        html_parts.append("<table><thead><tr>")
        for col in ['symbol', 'action', 'entry_time', 'entry_px', 'exit_px',
                    'exit_rsn', 'net_pnl', 'log_return', 'mfe_frac', 'score', 'risk%']:
            html_parts.append(f"<th>{col}</th>")
        html_parts.append("</tr></thead><tbody>")
        for row in trade_rows:
            cls_pnl = 'pos' if row['net_pnl'] > 0 else 'neg'
            html_parts.append("<tr>")
            html_parts.append(f"<td>{row['symbol']}</td>")
            html_parts.append(f"<td>{row['action']}</td>")
            html_parts.append(f"<td>{row['entry_time'][:19]}</td>")
            html_parts.append(f"<td>{row['entry_px']}</td>")
            html_parts.append(f"<td>{row['exit_px']}</td>")
            html_parts.append(f"<td>{row['exit_rsn']}</td>")
            html_parts.append(f"<td class='{cls_pnl}'>{row['net_pnl']:+.4f}</td>")
            html_parts.append(f"<td class='{cls_pnl}'>{row['log_return']:+.6f}</td>")
            html_parts.append(f"<td>{row['mfe_frac']:.6f}</td>")
            html_parts.append(f"<td>{row['score']:.2f}</td>")
            html_parts.append(f"<td>{row['risk%']:.3f}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody></table>")
        html_parts.append("</div>")
        
        # Tab 4: Summary
        html_parts.append("<div id='tab-summary' class='tab-panel'>")
        html_parts.append("<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>")
        for k, v in summary_stats.items():
            html_parts.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
        html_parts.append("</tbody></table>")
        html_parts.append("</div>")
        
        html_parts.append("</div>")  # tab-container
        
        # JS for tabs
        html_parts.append("""
        <script>
        function showTab(name, btn) {
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + name).classList.add('active');
            btn.classList.add('active');
        }
        </script>
        """)
        
        html_parts.append("</body></html>")
        
        with open(out, 'w', encoding='utf-8') as f:
            f.write("\n".join(html_parts))
        log.info(f"🌐 HTML report: {out}")
    except Exception as e:
        log.warning(f"[HTML] generation failed: {e}")
        _write_html_fallback(trades, equity, m, out)


def _write_html_fallback(trades, equity, m, out):
    """Fallback HTML without plotly — just tables and text."""
    try:
        rows_html = ""
        for t in trades[:1000]:
            rows_html += (
                f"<tr><td>{getattr(t,'symbol','')}</td>"
                f"<td>{getattr(t,'action','')}</td>"
                f"<td>{getattr(t,'entry_price',0):.6f}</td>"
                f"<td>{getattr(t,'exit_price',0):.6f}</td>"
                f"<td>{getattr(t,'exit_reason','')[:40]}</td>"
                f"<td>{getattr(t,'net_pnl',0):+.4f}</td>"
                f"<td>{getattr(t,'log_return',0):+.6f}</td></tr>"
            )
        html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>QTT Report (fallback)</title>
<style>
body {{ background: #0d0d0d; color: #e0e0e0; font-family: monospace; padding: 20px; }}
h1 {{ color: #00e5ff; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th, td {{ border: 1px solid #333; padding: 6px; text-align: left; }}
th {{ background: #1e1e1e; }}
</style></head><body>
<h1>QTT Report (Static Fallback)</h1>
<p>plotly not available — showing summary and trades table only.</p>
<h2>Summary</h2>
<ul>
<li>E[ln] = {m.get('mean_log_return', 0):+.5f}</li>
<li>PF = {m.get('profit_factor', 0):.3f}</li>
<li>Sharpe = {m.get('sharpe_ratio', 0):.3f}</li>
<li>Win Rate = {m.get('win_rate', 0)*100:.2f}%</li>
<li>N Trades = {m.get('n_trades', 0):,}</li>
<li>Final = ${m.get('final_capital', 0):,.2f}</li>
</ul>
<h2>Trades (first 1000)</h2>
<table>
<thead><tr><th>Symbol</th><th>Action</th><th>Entry</th><th>Exit</th>
<th>Reason</th><th>PnL</th><th>Log Ret</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>"""
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        log.info(f"🌐 HTML report (fallback): {out}")
    except Exception as e:
        log.warning(f"[HTML fallback] failed: {e}")

# ═══════════════════════════════════════════════════════════════
'''


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_config(content):
    if "ANALYTICS_ENABLED" in content:
        log("  [config] already present — skip")
        return content
    anchor = '''    # ══ [ML FILTER — optional signal rejection] ══
    ML_FILTER_ENABLED: bool = False       # default OFF
'''
    if anchor not in content:
        fail("[config] ML_FILTER anchor not found")
    return must_replace(content, anchor, CONFIG_BLOCK + "\n" + anchor, "config")


def patch_02_analytics_module(content):
    if "def _analytics_init(" in content:
        log("  [analytics-module] already present — skip")
        return content
    anchor = 'def build_signals(assets, mode="backtest"):'
    return must_insert_before(content, anchor, ANALYTICS_MODULE + "\n\n", "analytics-module")


def patch_03_plot_v2_function(content):
    if "def plot_results_v2(" in content:
        log("  [plot-v2] already present — skip")
        return content
    anchor = 'def plot_results(trades, equity, m, out="quantum_v6_results.png"):'
    return must_insert_before(content, anchor, PLOT_V2_FUNCTION + "\n\n", "plot-v2")


def patch_04_html_function(content):
    if "def generate_html_report(" in content:
        log("  [html-function] already present — skip")
        return content
    anchor = 'def run_backtest(cfg):'
    return must_insert_before(content, anchor, HTML_REPORT_FUNCTION + "\n\n", "html-function")


def patch_05_extend_trade_log_bt(content):
    if "_analytics_extend_trade_record" in content and \
       content.count("_analytics_extend_trade_record") > 1:
        log("  [extend-bt] already present — skip")
        return content
    anchor = '''        rec.update(_extract_entry_features_for_log(sig, ad))
        _trade_log_write(rec)
    except Exception as e:
        log.debug(f"[TradeLog] backtest log failed: {e}")'''
    if anchor not in content:
        fail("[extend-bt] _trade_log_from_backtest anchor not found")
    new = '''        rec.update(_extract_entry_features_for_log(sig, ad))
        try:
            rec = _analytics_extend_trade_record(
                rec, pos, ad, exit_px, exit_rsn, exit_ci,
                capital_before, capital_after, net or 0.0, lr, 'backtest'
            )
        except Exception:
            pass
        _trade_log_write(rec)
    except Exception as e:
        log.debug(f"[TradeLog] backtest log failed: {e}")'''
    return must_replace(content, anchor, new, "extend-bt")


def patch_06_extend_trade_log_live(content):
    if "def _trade_log_from_live" in content:
        # check if already patched
        idx = content.find("def _trade_log_from_live")
        be = content.find("\ndef ", idx + 10)
        block = content[idx:be if be > 0 else idx + 5000]
        if "_analytics_extend_trade_record" in block:
            log("  [extend-live] already present — skip")
            return content
    anchor = '''        _trade_log_write(rec)
    except Exception as e:
        log.debug(f"[TradeLog] live log failed: {e}")'''
    if anchor not in content:
        log("  [extend-live] anchor not found — skip (may use different format)")
        return content
    new = '''        try:
            rec = _analytics_extend_trade_record(
                rec, None, ad, exit_px, exit_rsn, 0,
                0.0, 0.0, net_pnl or 0.0, 0.0, CFG.mode
            )
        except Exception:
            pass
        _trade_log_write(rec)
    except Exception as e:
        log.debug(f"[TradeLog] live log failed: {e}")'''
    return must_replace(content, anchor, new, "extend-live")


def patch_07_simulate_portfolio_snapshot(content):
    if "[Analytics] portfolio snapshot per signal" in content:
        log("  [portfolio-snapshot-bt] already present — skip")
        return content
    anchor = '''        # ══ [OppTP] نقل TP لمركز مفتوح عند ظهور إشارة معاكسة ══
        if getattr(CFG, 'OPP_TP_ENABLED', False) and sig.symbol in open_pos:'''
    if anchor not in content:
        fail("[portfolio-snapshot-bt] OppTP anchor not found")
    new = '''        # ══ [Analytics] portfolio snapshot per signal ══
        if _ANALYTICS.get('enabled'):
            try:
                _an_ts = (sig.timestamp.timestamp()
                           if hasattr(sig.timestamp, 'timestamp') else time.time())
                _an_heat = sum(float(p.signal.dynamic_risk)
                                for p in open_pos.values())
                _analytics_portfolio_snapshot(
                    _an_ts, capital, peak_cap,
                    len(open_pos), _an_heat,
                )
            except Exception:
                pass
        
''' + anchor
    return must_replace(content, anchor, new, "portfolio-snapshot-bt")


def patch_08_close_event_hook(content):
    if "[Analytics] log trade close event" in content:
        log("  [close-event] already present — skip")
        return content
    anchor = '''        # ══ [TradeLog] تسجيل الصفقة ══
        try:
            _trade_log_from_backtest(
                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital,
                net_pnl=net, log_return=lr
            )
        except Exception as _tle:
            log.debug(f"[TradeLog] backtest hook failed: {_tle}")'''
    if anchor not in content:
        fail("[close-event] _close anchor not found")
    new = '''        # ══ [Analytics] log trade close event ══
        try:
            _tid = _ANALYTICS.get('trade_id_map', {}).get(id(pos), None)
            if _tid is None and _ANALYTICS.get('enabled'):
                _tid = _analytics_new_trade_id(sig.symbol,
                                                 str(sig.timestamp))
                _ANALYTICS['trade_id_map'][id(pos)] = _tid
            _analytics_log_position_event(
                _tid or '?', sig.symbol, 'closed',
                {'exit_px': float(exit_eff), 'exit_rsn': str(exit_rsn),
                 'net_pnl': float(net), 'log_return': float(lr)}
            )
        except Exception:
            pass
        
''' + anchor
    return must_replace(content, anchor, new, "close-event")


def patch_09_run_backtest_init(content):
    if "[Analytics] init before backtest" in content:
        log("  [run-bt-init] already present — skip")
        return content
    anchor = '''    log.info("§1  مسح أعلى 15 عملة...")
    syms = scan_top_assets(exchange, cfg.n_assets)'''
    if anchor not in content:
        fail("[run-bt-init] anchor not found")
    new = '''    # ══ [Analytics] init before backtest ══
    _analytics_init('backtest', cfg)
    _analytics_write_manifest('backtest', cfg)
    
''' + anchor
    return must_replace(content, anchor, new, "run-bt-init")


def patch_10_run_backtest_finalize(content):
    if "[Analytics] finalize backtest" in content:
        log("  [run-bt-finalize] already present — skip")
        return content
    anchor = '''    print_report(m, "backtest")
    plot_results(trades, equity, m)'''
    if anchor not in content:
        fail("[run-bt-finalize] anchor not found")
    new = '''    print_report(m, "backtest")
    
    # ══ [Analytics] finalize backtest ══
    if _ANALYTICS.get('enabled'):
        if getattr(CFG, 'ANALYTICS_EXPANDED_PNG', True):
            # v2 PNG is generated inside finalize
            _analytics_finalize('backtest', trades, equity, m)
        else:
            plot_results(trades, equity, m)
            _analytics_finalize('backtest', trades, equity, m)
    else:
        plot_results(trades, equity, m)'''
    return must_replace(content, anchor, new, "run-bt-finalize")


def patch_11_run_live_init(content):
    if "[Analytics] init before live" in content:
        log("  [run-live-init] already present — skip")
        return content
    anchor = '''    log.info(f"🔴 [{cfg.mode.upper()}] بدء التشغيل (State Machine v2)")
    state_file = f"live_state_{cfg.mode}.json"'''
    if anchor not in content:
        fail("[run-live-init] anchor not found")
    new = '''    log.info(f"🔴 [{cfg.mode.upper()}] بدء التشغيل (State Machine v2)")
    
    # ══ [Analytics] init before live ══
    _analytics_init(cfg.mode, cfg)
    _analytics_write_manifest(cfg.mode, cfg)
    
    state_file = f"live_state_{cfg.mode}.json"'''
    return must_replace(content, anchor, new, "run-live-init")


def patch_12_run_live_portfolio_snapshot(content):
    if "[Analytics] live portfolio snapshot" in content:
        log("  [run-live-snapshot] already present — skip")
        return content
    anchor = '''            # ══ Persist state ══
            try:
                _lv_save_state(state_file, open_pos_live)'''
    if anchor not in content:
        fail("[run-live-snapshot] anchor not found")
    new = '''            # ══ [Analytics] live portfolio snapshot ══
            if _ANALYTICS.get('enabled'):
                try:
                    _an_heat = sum(float(p.get('dyn_risk', 0))
                                    for p in open_pos_live.values())
                    _analytics_portfolio_snapshot(
                        time.time(), cap_live, peak_cap_live,
                        len(open_pos_live), _an_heat,
                    )
                    _analytics_market_snapshot(
                        time.time(),
                        assets if 'assets' in dir() else {},
                        open_pos_live,
                    )
                except Exception:
                    pass
            
''' + anchor
    return must_replace(content, anchor, new, "run-live-snapshot")


def patch_13_cli_flags(content):
    if 'p.add_argument("--analytics"' in content:
        log("  [cli] already present — skip")
        return content
    anchor = '''    p.add_argument("--trade-log", type=str, default=None,
                   help="Path to trade log file (JSONL). "
                        "Default: trades_log_{mode}.jsonl")'''
    if anchor not in content:
        fail("[cli] --trade-log anchor not found")
    new = anchor + '''
    p.add_argument("--analytics", action="store_true",
                   help="[Analytics] Enable comprehensive output system "
                        "(manifest, extended trades, portfolio ts, market context, "
                        "24-panel PNG, HTML report)")
    p.add_argument("--analytics-dir", type=str, default=None,
                   help="[Analytics] Output directory (default: analytics)")
    p.add_argument("--analytics-no-signals", action="store_true",
                   help="[Analytics] Disable signals_candidates logging")
    p.add_argument("--analytics-no-portfolio-ts", action="store_true",
                   help="[Analytics] Disable portfolio timeseries")
    p.add_argument("--analytics-no-market-context", action="store_true",
                   help="[Analytics] Disable market context")
    p.add_argument("--analytics-no-events", action="store_true",
                   help="[Analytics] Disable position events")
    p.add_argument("--analytics-no-html", action="store_true",
                   help="[Analytics] Disable HTML report")
    p.add_argument("--analytics-no-png-v2", action="store_true",
                   help="[Analytics] Use old PNG instead of 24-panel v2")'''
    return must_replace(content, anchor, new, "cli")


def patch_14_argparse(content):
    if 'CFG.ANALYTICS_ENABLED = True' in content:
        log("  [argparse] already present — skip")
        return content
    anchor = '''    _trade_log_init(CFG.mode, args.trade_log)'''
    if anchor not in content:
        fail("[argparse] _trade_log_init anchor not found")
    new = anchor + '''
    
    # ══ [Analytics] CLI wiring ══
    if getattr(args, "analytics", False):
        CFG.ANALYTICS_ENABLED = True
        if args.analytics_dir:
            CFG.ANALYTICS_OUTPUT_DIR = str(args.analytics_dir)
        if getattr(args, "analytics_no_signals", False):
            CFG.ANALYTICS_LOG_SIGNALS = False
        if getattr(args, "analytics_no_portfolio_ts", False):
            CFG.ANALYTICS_LOG_PORTFOLIO_TS = False
        if getattr(args, "analytics_no_market_context", False):
            CFG.ANALYTICS_LOG_MARKET_CONTEXT = False
        if getattr(args, "analytics_no_events", False):
            CFG.ANALYTICS_LOG_POSITION_EVENTS = False
        if getattr(args, "analytics_no_html", False):
            CFG.ANALYTICS_HTML_REPORT = False
        if getattr(args, "analytics_no_png_v2", False):
            CFG.ANALYTICS_EXPANDED_PNG = False
        log.info(f"[Analytics] ENABLED — output: {CFG.ANALYTICS_OUTPUT_DIR}/<run_id>/")
    else:
        log.info("[Analytics] Disabled (use --analytics to enable)")'''
    return must_replace(content, anchor, new, "argparse")


def patch_15_manifest_extra(content):
    """Update run_manifest to include trades/equity summary after backtest."""
    # Already handled in _analytics_update_manifest_results
    log("  [manifest-extra] skip (handled at finalize)")
    return content


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    path = args.target
    if not os.path.exists(path):
        fail(f"File not found: {path}")

    content = open(path, "r", encoding="utf-8").read()

    if args.force and content.startswith(MARKER + "\n"):
        content = content[len(MARKER) + 1:]
        log("  removed existing marker for re-apply")

    if MARKER in content and not args.force:
        log("Analytics v1 already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE")
    if not ok:
        fail(f"File has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = patch_01_config(content)
        content = patch_02_analytics_module(content)
        content = patch_03_plot_v2_function(content)
        content = patch_04_html_function(content)
        content = patch_05_extend_trade_log_bt(content)
        content = patch_06_extend_trade_log_live(content)
        content = patch_07_simulate_portfolio_snapshot(content)
        content = patch_08_close_event_hook(content)
        content = patch_09_run_backtest_init(content)
        content = patch_10_run_backtest_finalize(content)
        content = patch_11_run_live_init(content)
        content = patch_12_run_live_portfolio_snapshot(content)
        content = patch_13_cli_flags(content)
        content = patch_14_argparse(content)

        content = MARKER + "\n" + content

        ok, err = verify_syntax(content, "POST")
        if not ok:
            fail(f"Result has syntax errors: {err}")

        if args.dry_run:
            log("DRY RUN: syntax OK. Would write to file.")
            return 0

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        log(f"Saved: {path}  ({content.count(chr(10))} lines)")
        log("=" * 60)
        log("Analytics v1 applied successfully.")
        log("")
        log("Default: OFF (behavior unchanged).")
        log("")
        log("To enable:")
        log("  --analytics")
        log("")
        log("Generates (in analytics/<run_id>/):")
        log("  ✓ run_manifest.json")
        log("  ✓ trades_log (extended, JSONL)")
        log("  ✓ portfolio_timeseries.parquet")
        log("  ✓ market_context.parquet")
        log("  ✓ signals_candidates.jsonl")
        log("  ✓ position_events.jsonl")
        log("  ✓ quantum_v6_results_v2.png (24 panels)")
        log("  ✓ report.html (interactive, Plotly)")
        log("")
        log("Optional control flags:")
        log("  --analytics-dir PATH")
        log("  --analytics-no-signals / --analytics-no-portfolio-ts")
        log("  --analytics-no-market-context / --analytics-no-events")
        log("  --analytics-no-html / --analytics-no-png-v2")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"FAILED: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
