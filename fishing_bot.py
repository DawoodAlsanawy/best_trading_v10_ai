#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      محرك التداول الثرموديناميكي الكمي – الإصدار 7.0                        ║
║    Quantum Thermodynamic Trading Engine – v7.0                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  v6.3: إعادة هيكلة كاملة لإدارة الأوامر والمراكز في Live/Testnet:            ║
║   • دفتر كمية صريح (Quantity Ledger) يعرف بالضبط متى يكتفي بالكمية المطلوبة  ║
║   • إعادة تسعير الحزم عند انحراف السعر فقط (لا مؤقت أعمى) لحفظ أولوية الصف   ║
║   • فصل صارم بين بيانات الشموع المغلقة (لإشارات Apex/Topo) والسعر اللحظي     ║
║     (للوقف/الهدف فقط) لمطابقة سلوك الباك-تيست تماماً ومنع الترددات الزائفة   ║
║   • معالجة آمنة للمراكز "اليتيمة" غير المتتبعة بدل قيم SL=0/TP=0 الخطيرة     ║
║   • تقريب الكمية والسعر وفق دقة المنصة قبل إرسال أي أمر                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  v7.0: استبدال الصيغ الفيزيائية الاعتباطية بتقديرات إحصائية حقيقية مُشتقة    ║
║        من البيانات (راجع § V7 قرب أعلى الملف، وقسم "ماذا لم يُنجز" أسفله):  ║
║   ١  HMM حقيقي (Baum-Welch) بدل KMeans، مع رجوع تلقائي آمن عند الفشل         ║
║   ٣  معايرة γ₀ (الاحتكاك) من زمن الترابط الذاتي الفعلي (Onsager) لا ثابت يدوي║
║   ٤  مصنّف احتمالي معاير (Logistic + Platt scaling) بدل exp(...) اعتباطية    ║
║   ٦  وقف/هدف من det(Cov) المحلي × ATR (تقريب معلوماتي عملي، موثّق كتقريب)    ║
║   ٧  كيلي كسري حقيقي (صيغة الرهان الثنائي) + قيد CVaR تجريبي من عوائد الأصل  ║
║   ٨  انزلاق Almgren-Chriss (أثر مؤقت تربيعي + دائم خطي في المشاركة بالسيولة) ║
║   ٩  ارتباط بانكماش Ledoit-Wolf بدل المصفوفة العينية الخام غير المستقرة      ║
║   ١٠ فلتر أس هيرست لتعطيل الدخول في أنظمة كسر-الإرغودية                     ║
║   ١١ Deflated Sharpe Ratio + PBO تقريبي مطبوعان تلقائياً في كل تقرير باك-تست║
║  ⚠  ٢/٥/١٢/١٣ من قائمة التحسينات الأصلية غير مُدمجة في خط الأنابيب الحي —    ║
║     أدوات جاهزة (rank_features_by_mutual_information, compute_ofi) لكن غير  ║
║     موصولة تلقائياً؛ التفاصيل والسبب في § "ماذا لم يُنجز ولماذا" أسفل الرأس  ║
╚══════════════════════════════════════════════════════════════════════════════╝

# ════════════════════════════════════════════════════════════════════════════
# ماذا لم يُنجز في هذا الإصدار، ولماذا (صدق تقني لا تسويق):
# ════════════════════════════════════════════════════════════════════════════
#
# • بند ٢ (متري فيشر الصريح + جيوديسيا كاملة على عائلة أسية p_λ):
#   لم يُطبَّق حرفياً. اشتقاق متري فيشر الحقيقي يتطلب تعريف عائلة أسية صريحة
#   p_λ(x) وتقدير λ لكل صفقة عبر MLE، وهو تصميم نموذج جديد كلياً وليس "تصحيح
#   دالة". ما طُبِّق بدلاً منه (بند ٦) هو تقريب عملي محافظ: det(المصفوفة
#   المحلية للتغاير) كمقياس لليقين المعلوماتي، موثّق بوضوح كتقريب في التعليق
#   داخل compute_geodesic_stop، وليس ادعاءً بأنه جيوديسيا فيشر-راو صحيحة.
#
# • بند ٥ (المعلومات المتبادلة/الانتروبيا الانتقالية لفلترة الميزات تلقائياً):
#   الدوال منفَّذة وتعمل فعلياً (mutual_information_binned,
#   rank_features_by_mutual_information) لكنها أدوات تحليل غير متصلة
#   (offline) تُستدعى يدوياً على بيانات تاريخية لتقرر أي ميزات تُبقيها — لم
#   تُدمج كفلتر تلقائي داخل compute_features لأن حذف ميزة تلقائياً في منتصف
#   التشغيل الحي دون مراجعة بشرية خطر (يغيّر شكل متجه X الذي دُرِّب عليه
#   HMM/المصنّف بصمت).
#
# • بند ١٢ (اختلال تدفق الأوامر OFI): compute_ofi() جاهزة وصحيحة رياضياً، لكن
#   خط أنابيب البيانات الحالي (fetch_all/scan_top_assets) يجلب فقط شموع OHLCV
#   من Binance عبر REST/WS — لا بيانات دفتر أوامر L2 (bid/ask depth) متاحة على
#   الإطلاق في هذا الملف. تفعيل OFI فعلياً يتطلب اشتراك WS جديد لدفتر الأوامر
#   (مثل bookTicker/depth streams) وهي إضافة بنية تحتية منفصلة، ليست "تصحيح
#   صيغة". CFG.OFI_ENABLED=False حتى تُضاف تلك البنية.
#
# • بند ١٣ (بقاء البيانات / Survivorship Bias): لا يمكن إصلاحه داخل هذا
#   الملف لأنه ليس خطأ برمجياً بل قيد في مصدر البيانات نفسه (Binance API
#   الحالي يُرجع فقط الأزواج المُدرَجة حالياً). الإصلاح الحقيقي يتطلب قاعدة
#   بيانات نقطة-زمنية (point-in-time) خارجية تشمل العملات المشطوبة — غير
#   متاحة هنا. أُضيف CFG.SURVIVORSHIP_WARNING فقط كتذكير، وتوصية عملية: اختبر
#   على نافذة زمنية حديثة نسبياً حيث احتمال الشطب أقل تأثيراً.
#
# • تحقق DSR/PBO (بند ١١) واقعي جزئياً: DSR رياضياً صحيحة، لكن دقتها تعتمد
#   على أن تُحدِّث CFG.N_TRIALS_TESTED بصدق (عدد التوليفات/الإعدادات التي
#   جرّبتها فعلياً على هذه البيانات قبل الوصول للنتيجة الحالية). تركه على
#   القيمة الافتراضية (1) يجعل DSR متفائلة زائفاً إن كنت فعلياً قد جرّبت
#   عشرات الإعدادات. PBO المطبوعة تقريب اتجاهي على شرائح زمنية من مسار واحد،
#   وليست CSCV الكامل (الذي يتطلب مسارات باك-تيست متعددة فعلية من توليفات
#   إعداد مختلفة) — لا تعامله كإثبات قاطع، بل كإشارة تحذير إضافية.
#
# • هذا الملف يبقى محرك تنفيذ حي (WebSocket، أوامر Limit/Market حقيقية، رافعة
#   حتى 50x). التحسينات أعلاه تُحسِّن جودة الإشارة والمعايرة الإحصائية، لكنها
#   لا "تثبت" حافة تداول ربحية بذاتها — الإثبات الوحيد المقبول هو باك-تيست
#   Walk-Forward على بيانات تاريخية حقيقية (غير متاحة في بيئة التطوير هذه
#   بلا اتصال شبكة) ثم فترة تجريبية على testnet قبل أي رأس مال حقيقي.
"""

import argparse, json, logging, os, time, warnings
import threading
import multiprocessing as mp
import websocket
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, linregress, skew
from sklearn.cluster import KMeans

import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

# [جديد] Plotly اختياري بالكامل: إن لم تكن المكتبة مثبتة (pip install plotly)
# يستمر البوت بكل وظائفه التداولية بلا أي تأثير — تُعطَّل فقط ميزة رسوم HTML
# التفاعلية للصفقات (تصدير CSV يبقى يعمل دوماً لأنه لا يعتمد على Plotly).
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

warnings.filterwarnings("ignore")
os.environ["LOKY_MAX_CPU_COUNT"] = "1"
CACHE_DIR = "market_data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("QTT6")


# ════════════════════════════════════════════════════════════════
# § 0  الإعدادات المركزية
# ════════════════════════════════════════════════════════════════

@dataclass
class Config:
    mode: str = "backtest"
    api_key: str = ""
    api_secret: str = ""
    testnet_url: str = "https://demo-fapi.binance.com"

    n_assets: int = 7
    min_quote_vol_usd: float = 5e8
    exclude_tokens: List[str] = field(default_factory=lambda: [
        "ETH","BTC","USDC","BUSD","TUSD","USDP","DAI","FDUSD","BVOL","IBVOL",
        "UP","DOWN","BEAR","BULL","HALF","HEDGE"
    ])

    timeframe: str = "1h"
    history_days: int = 30

    N: int = 24; W: int = 30; L: int = 10; K: int = 8
    EMA_SPAN: int = 200; ATR_PERIOD: int = 14

    W_CURV: float=1.0; W_VOL: float=1.0; W_ENTROPY: float=2.0
    W_HMM: float=2.0; W_FREE_E: float=1.0; MIN_SCORE: int=5

    CURV_THRESHOLD: float=0.01; DH_ENTROPY_THRESHOLD: float=0.005
    DH_HMM_UPPER: float=0.01;  DH_HMM_LOWER: float=-0.01
    DF_FREE_E_THRESHOLD: float=-0.01

    BASE_RISK: float = 0.002
    MAX_RISK:  float = 0.05
    MIN_RISK:  float = 0.001
    LAMBDA_KELLY: float = 0.05
    KELLY_SCALE: float = 0.50
    RISK_PER_TRADE: float = 0.03

    LEVERAGE_BASE: float = 20.0
    LEVERAGE_MIN: int = 5
    LEVERAGE_MAX: int = 20
    LEVERAGE: int = 10
    INITIAL_CAPITAL: float = 1000.0
    CAPITAL_FLOOR: float = 0.5
    MAKER_FEE: float = -0.0001
    MAX_CHUNK_USD: float = 100.0
    MIN_NOTIONAL: float = 70.0
    SL_FACTOR: float = 0.15
    TP_BETAS: Tuple = (5,)

    FUNDING_RATE_COST: float = 0.0001
    FUNDING_INTERVAL_BARS: int = 8

    MAX_DRAWDOWN_HALT: float   = 1.00
    REDUCED_RISK_MULT: float   = 0.25
    REDUCED_RISK_MULT_50: float= 0.10
    REDUCED_RISK_MULT_70: float= 0.05
    DRAWDOWN_REDUCE_AT:  float = 0.30
    DRAWDOWN_REDUCE_AT_50: float=0.50
    DRAWDOWN_REDUCE_AT_70: float=0.70

    MAX_CONCURRENT_ASSETS: int   = 1
    CORRELATION_THRESHOLD: float = 0.50

    MAX_HOLD_BARS: int = 168

    TOPO_DIV_THRESHOLD: float = 0.05

    K_MIN: int = 6
    K_MAX: int = 12
    KQUANT_ALPHA: float = 100.0

    COSMOLOGICAL_CONSTANT: float = 0

    OPTIMAL_ENTRY_WAIT: int=8; OPTIMAL_ENTRY_DIP: float=0.3

    REVERSAL_MIN_SCORE: int=3; LYA_WINDOW: int=20
    LYA_THRESHOLD_MULT: float=2.0

    SLIP_BASE: float=0.0003; SLIP_IMPACT: float=0.02
    MAX_SLIPPAGE_FRACTION: float=0.0002

    MAX_ADV_FRACTION: float=0.01

    TRAIN_FRACTION: float=0.50

    LIVE_POLL_SECS: int=30; LIVE_ORDER_TYPE: str = "MARKET"
    # [جديد] نوع أمر الدخول وأمر الخروج (live/testnet) — كل منهما مستقل تماماً
    # وقابل للتعديل من الإعدادات وحده دون المساس بالآخر:
    #   "limit"  → أوامر حدّية سلبية عبر execute_quantum_chunks (يستهدف عمولة
    #              الصانع MAKER_FEE، لكنه أبطأ وقد لا يُنفَّذ فوراً في سوق سريع
    #              الحركة).
    #   "market" → أمر سوق فوري لكامل الكمية دفعة واحدة (تنفيذ مضمون وأسرع،
    #              لكن بعمولة/انزلاق آخذ لا تُطبَّق عليه عمولة الصانع السالبة
    #              عادةً — يُستخدم غالباً عند الحاجة لتنفيذ حاسم فوري).
    #
    # [إصلاح EXEC-1 — تشخيص جذري لعدم دقة الدخول/الخروج المُبلَّغ عنها]
    # كان EXIT_ORDER_TYPE الافتراضي "limit"، أي أن Emergency SL/Hard TP/Apex/
    # Topo-Div/MaxHold جميعها كانت تُغلَق عبر execute_quantum_chunks — وهي
    # مصمَّمة عمداً لتكون **سلبية** (تنتظر في مكانها، لا تُلاحق السوق إلا بعد
    # انحراف > 0.2% عن السعر الأصلي، ثم لا تُعيد التسعير إلا بعد انحراف إضافي
    # يتجاوز ORDER_PRICE_DRIFT_BPS). هذا ممتاز لأوامر الدخول (تفويت فرصة ليس
    # خطيراً)، لكنه **معكوس تماماً** لمنطق وقف الخسارة: عند تفعيل Emergency SL
    # فعلياً (السعر تجاوز pos['sl'])، السوق غالباً يتحرك ضد المركز بسرعة، وأمر
    # بيع سلبي (لإغلاق شراء) يُوضَع *فوق* أفضل سعر بيع حالي (best_ask) لن
    # يُنفَّذ فوراً — بل ينتظر إما ارتداداً مؤقتاً (نادر أثناء موجة هابطة حقيقية)
    # أو انحرافاً إضافياً كافياً لإعادة التسعير. النتيجة: تنفيذ فعلي متأخر
    # وبسعر أسوأ من نقطة التفعيل، بعكس الباك-تيست الذي يفترض تنفيذاً فورياً عند
    # لمس trail_sl بالضبط. لذلك أصبح الافتراضي الآن "market" للخروج فقط —
    # الدخول يبقى "limit" لأن تفويت دخول أقل خطورة من تأخر خروج وقائي.
    ENTRY_ORDER_TYPE: str = "limit"
    EXIT_ORDER_TYPE: str = "market"
    EPSILON: float=1e-9

    GAMMA_0: float = 0.01
    KAPPA: float = 0.1
    XI: float = 1.0
    LORENTZ_CHARGE_Q: float = 1.0
    MAX_EQUILIBRIUM_GAP: float = 0.35
    ERGODIC_DH_WINDOW: int = 12
    ERGODIC_DH_THRESHOLD: float = 0.001
    GEO_EXIT_THRESHOLD: float = 0.02

    # ══ [v7] بناء نموذج الحالة: HMM بدل KMeans (تحسين ١) ══
    STATE_MODEL: str = "hmm"          # "hmm" أو "kmeans" (احتفاظ بالتوافق الرجعي)
    HMM_MAX_ITER: int = 60
    HMM_TOL: float = 1e-4
    HMM_MIN_VAR: float = 1e-4          # سقف أدنى للتباين القطري لتفادي انهيار المكوّن

    # ══ [v7] معايرة الاحتكاك من الارتباط الذاتي (تحسين ٣) ══
    FRICTION_ACF_MAX_LAG: int = 40
    FRICTION_MIN: float = 1e-4

    # ══ [v7] مصنف احتمالي معاير بدل الصيغة اللوجستية الاعتباطية (تحسين ٤) ══
    USE_CALIBRATED_CLASSIFIER: bool = True
    CLASSIFIER_MIN_SAMPLES: int = 80
    CLASSIFIER_PROB_THRESHOLD: float = 0.52   # > عشوائي (0.5) بهامش أمان صغير
    CLASSIFIER_LABEL_HORIZON: int = 24        # عدد الشموع الأمامية لتحديد فوز/خسارة أثناء التدريب

    # ══ [v7] وقف/هدف من مسافة معلوماتية محلية (تقريب متري فيشر) (تحسين ٦) ══
    GEO_STOP_ALPHA: float = 1.0
    GEO_STOP_MIN_PCT: float = 0.004
    GEO_STOP_MAX_PCT: float = 0.05
    GEO_TP_R_MULT: float = 2.0

    # ══ [v7] كيلي كسري + قيد CVaR (تحسين ٧) ══
    KELLY_FRACTION: float = 0.5
    CVAR_ALPHA: float = 0.05
    CVAR_MAX_LOSS_FRACTION: float = 0.15   # أقصى CVaR مقبول كنسبة من رأس المال

    # ══ [v7] أثر السعر على طراز Almgren-Chriss (تحسين ٨) ══
    AC_ETA: float = 0.10     # معامل الأثر المؤقت (تربيعي في سرعة التنفيذ)
    AC_GAMMA_PERM: float = 0.05  # معامل الأثر الدائم (خطي في الحجم)

    # ══ [v7] فلتر عدم-الإرغودية بأس هيرست (تحسين ١٠) ══
    HURST_WINDOW: int = 100
    HURST_LOW: float = 0.35
    HURST_HIGH: float = 0.65
    HURST_HALT_ENABLED: bool = True

    # ══ [v7] معايرة إحصائية صارمة (تحسين ١١) ══
    N_TRIALS_TESTED: int = 1     # عدد التوليفات/الإعدادات التي جُرِّبت فعلياً (لـ DSR)؛ حدِّثه بصدق

    # ══ [v7] اختلال تدفق الأوامر — غير مُفعَّل افتراضياً لغياب بيانات دفتر الأوامر L2 (تحسين ١٢) ══
    OFI_ENABLED: bool = False

    # ══ [v7] بقاء البيانات — تحذير فقط، لا يُصلح تلقائياً دون مصدر بيانات نقطة-زمنية (تحسين ١٣) ══
    SURVIVORSHIP_WARNING: bool = True
    SINGULARITY_MODE: bool = False
    SING_RISK_FRACTION: float = 0.20
    SING_LEVERAGE: int = 50
    SING_STOP_LOSS_PCT: float = 0.0015
    SING_TAKE_PROFIT_PCT: float = 0.006
    SING_RESONANCE_ACCEL: float = 0.0005
    HIGHER_TF: str = "4h"
    HIGHER_TF_EMA_SPAN: int = 20

    # ══ [v6.3] تنفيذ الأوامر: دفتر كمية + إعادة تسعير عند الانحراف فقط ══
    ORDER_FILL_POLL_SECS: float = 0.5          # تردد الاستعلام عن حالة تعبئة الأمر
    ORDER_DRIFT_CHECK_SECS: float = 1.0        # تردد إعادة فحص دفتر الأوامر لكشف الانحراف
    ORDER_PRICE_DRIFT_BPS: float = 3.0         # سماحية انحراف السعر (نقاط أساس) قبل اعتبار الأمر "فقد ميزته"
    # [إصلاح EXEC-2] نطاق "البقاء سلبياً" الأولي عند تسعير كل حزمة دخول جديدة —
    # كان مثبَّتاً ضمنياً على 0.002 (0.2%)؛ الآن مُهيَّأ ومُخفَّض افتراضياً إلى
    # 0.0005 (0.05%) لتقليل فرص الدخول المفقودة بسبب زخم صغير لا يُلاحَق.
    PASSIVE_CHASE_TOLERANCE: float = 0.0005
    ORDER_HARD_TIMEOUT_SECS: float = 20.0      # سقف أمان مطلق لكل حزمة (شبكة معلقة/سوق ميت)
    ORDER_MIN_CHUNK_USD_DUST: float = 5.0      # هامش الغبار: يُضم للحزمة الأخيرة بدل تركه عالقاً
    AMBIGUOUS_ORDER_MAX_RETRIES: int = 3       # محاولات التحقق من حالة أمر غامض بعد الإلغاء
    # [إصلاح حرج] سقف زمني إجمالي مطلق للدالة كاملة (كل الحزم مجتمعة)، مستقل عن
    # سقف الحزمة الواحدة. بدونه: أمر صانع سعر لا يجد طرفاً مقابلاً أبداً (سوق
    # هادئ جداً أو سعرنا متحفظ جداً) وسعر السوق لا ينحرف عنه، يجعل الحلقة
    # الخارجية تُعيد إرسال/إلغاء نفس الحزمة إلى ما لا نهاية — تُجمّد الخيط
    # المستدعي (ماسح الدخول أو حارس مركز) إلى الأبد. هذا يحدّ أقصى وقت ممكن
    # تقضيه الدالة كلها قبل أن تُعيد ما أُنجز فعلياً (وقد يكون صفراً) وتتوقف.
    ORDER_TOTAL_EXECUTION_TIMEOUT_SECS: float = 90.0

    # ══ [v6.3] إدارة الأوامر المعلقة والمراكز ══
    PENDING_ORDER_STALE_SECS: float = 45.0     # عمر الأمر المعلق قبل اعتباره "يتيماً" يحتاج تنظيف
    CORRELATION_REFRESH_SECS: float = 1800.0

    # ══ [v6.3] محرك حي: خيوط + عمليات، وفصل الشموع المغلقة عن اللحظية ══
    FEATURE_REFRESH_SECS: float = 30.0         # دورة أمان كاملة (تعيد حساب كل الأصول)
    CLOSED_BAR_FAST_POLL_SECS: float = 2.0     # دورة سريعة: هل أُغلقت شمعة جديدة عبر WS؟
    REST_RESYNC_SECS: float = 900.0            # مزامنة REST دورية لتصحيح أي انحراف عن WS (كل 15 دقيقة)
    ENTRY_SCAN_SECS: float = 8.0
    GUARDIAN_POLL_SECS: float = 1.0
    POSITION_RECONCILE_SECS: float = 20.0
    PENDING_JANITOR_SECS: float = 5.0
    ASSET_RESCAN_SECS: float = 4 * 3600.0

    # ══ [جديد] تصدير الصفقات إلى CSV + رسوم Plotly تفاعلية (HTML) ══
    # يعمل بنفس المنطق في backtest وlive وtestnet دون تغيير أي سلوك تداول.
    EXPORT_TRADES_CSV: bool = True
    TRADES_CSV_PATH: str = "trades_log.csv"
    EXPORT_TRADE_HTML: bool = True
    TRADE_HTML_DIR: str = "trade_charts"
    TRADE_HTML_CONTEXT_BARS: int = 60   # عدد الشموع المعروضة قبل/بعد الصفقة في الرسم

CFG = Config()


# ════════════════════════════════════════════════════════════════
# § V7  النواة الإحصائية/الفيزيائية الحقيقية (تحسينات ١-١٣)
# ════════════════════════════════════════════════════════════════
# هذا القسم يستبدل الصيغ الاعتباطية بتقديرات مُشتقة فعلياً من البيانات.
# كل دالة موثّقة بمرجعها الرياضي/الفيزيائي المقابل في الملف المرفق.

from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.covariance import LedoitWolf
from sklearn.preprocessing import StandardScaler


# ---------- (١) نموذج ماركوف المخفي (Gaussian HMM, Baum-Welch/EM) ----------
class GaussianHMM:
    """
    HMM بتباين قطري (diagonal covariance) عبر خوارزمية Baum-Welch (EM).
    بديل حقيقي لـ KMeans: يقدّر مصفوفة الانتقال a_ij ويستخدم forward-backward
    بدل التجميع الساكن. واجهة متوافقة جزئياً مع KMeans (predict, cluster_centers_)
    لتقليل التغييرات في بقية خط الأنابيب.
    """
    def __init__(self, n_states=8, max_iter=60, tol=1e-4, min_var=1e-4, random_state=42):
        self.k = n_states
        self.max_iter = max_iter
        self.tol = tol
        self.min_var = min_var
        self.rng = np.random.RandomState(random_state)
        self.mu_ = None; self.var_ = None
        self.A_ = None; self.pi_ = None
        self.n_iter_ = 0
        self.converged_ = False

    @property
    def cluster_centers_(self):
        return self.mu_

    @property
    def transmat_(self):
        return self.A_

    def _log_gauss_diag(self, X):
        # log N(x; mu_j, diag(var_j)) لكل نقطة j -> (n, k)
        n, d = X.shape
        ll = np.zeros((n, self.k))
        for j in range(self.k):
            var = np.maximum(self.var_[j], self.min_var)
            diff2 = (X - self.mu_[j]) ** 2
            ll[:, j] = -0.5 * np.sum(diff2 / var + np.log(2 * np.pi * var), axis=1)
        return ll

    def fit(self, X):
        n, d = X.shape
        k = self.k
        # تهيئة: KMeans++ بسيطة عبر عينة عشوائية من النقاط كمراكز أولية
        km_init = KMeans(n_clusters=k, n_init=5, random_state=42, max_iter=100).fit(X)
        self.mu_ = km_init.cluster_centers_.copy()
        labels0 = km_init.labels_
        self.var_ = np.array([
            np.var(X[labels0 == j], axis=0) if np.sum(labels0 == j) > 1
            else np.var(X, axis=0)
            for j in range(k)
        ])
        self.var_ = np.maximum(self.var_, self.min_var)
        self.A_ = np.full((k, k), 1.0 / k)
        self.pi_ = np.full(k, 1.0 / k)

        prev_ll = -np.inf
        for it in range(self.max_iter):
            log_b = self._log_gauss_diag(X)                      # (n,k)
            log_b -= np.max(log_b)                                 # استقرار عددي
            b = np.exp(log_b) + 1e-300

            # ---- Forward ----
            alpha = np.zeros((n, k)); c = np.zeros(n)
            alpha[0] = self.pi_ * b[0]
            c[0] = alpha[0].sum() + 1e-300
            alpha[0] /= c[0]
            for t in range(1, n):
                alpha[t] = (alpha[t-1] @ self.A_) * b[t]
                c[t] = alpha[t].sum() + 1e-300
                alpha[t] /= c[t]
            loglik = np.sum(np.log(c))

            # ---- Backward ----
            beta = np.zeros((n, k)); beta[-1] = 1.0
            for t in range(n - 2, -1, -1):
                beta[t] = (self.A_ @ (b[t+1] * beta[t+1])) / c[t+1]

            # ---- Gamma / Xi (M-step) ----
            gamma = alpha * beta
            gamma /= (gamma.sum(axis=1, keepdims=True) + 1e-300)

            xi_sum = np.zeros((k, k))
            for t in range(n - 1):
                num = np.outer(alpha[t], b[t+1] * beta[t+1]) * self.A_
                xi_sum += num / (num.sum() + 1e-300)

            self.pi_ = gamma[0]
            denom = gamma[:-1].sum(axis=0) + 1e-300
            self.A_ = xi_sum / denom[:, None]
            self.A_ = np.maximum(self.A_, 1e-8)
            self.A_ /= self.A_.sum(axis=1, keepdims=True)

            w = gamma.sum(axis=0) + 1e-300
            self.mu_ = (gamma.T @ X) / w[:, None]
            for j in range(k):
                diff = X - self.mu_[j]
                self.var_[j] = np.maximum((gamma[:, j][:, None] * diff ** 2).sum(axis=0) / w[j], self.min_var)

            self.n_iter_ = it + 1
            if abs(loglik - prev_ll) < self.tol * max(1.0, abs(prev_ll)):
                self.converged_ = True
                break
            prev_ll = loglik
        return self

    def predict(self, X):
        """حالة فيتربي الأكثر احتمالاً (Viterbi) — تُستخدم كتسلسل رمزي متوافق مع sym_q."""
        n = len(X)
        log_b = self._log_gauss_diag(X)
        log_A = np.log(self.A_ + 1e-300)
        log_pi = np.log(self.pi_ + 1e-300)
        delta = np.zeros((n, self.k)); psi = np.zeros((n, self.k), dtype=np.int32)
        delta[0] = log_pi + log_b[0]
        for t in range(1, n):
            m = delta[t-1][:, None] + log_A
            psi[t] = np.argmax(m, axis=0)
            delta[t] = np.max(m, axis=0) + log_b[t]
        states = np.zeros(n, dtype=np.int32)
        states[-1] = int(np.argmax(delta[-1]))
        for t in range(n - 2, -1, -1):
            states[t] = psi[t+1, states[t+1]]
        return states

    def transition_entropy(self):
        """الانتروبيا الانتقالية H_trans = -Σ π_i a_ij log a_ij (راجع القسم ١)."""
        a = np.clip(self.A_, 1e-12, 1.0)
        return float(-np.sum(self.pi_[:, None] * a * np.log2(a)))


def fit_state_model(X_train, k, model_type=None):
    """يبني نموذج الحالة (HMM أو KMeans) حسب CFG.STATE_MODEL. واجهة موحّدة."""
    model_type = model_type or CFG.STATE_MODEL
    if model_type == "hmm":
        try:
            hmm = GaussianHMM(n_states=k, max_iter=CFG.HMM_MAX_ITER, tol=CFG.HMM_TOL,
                               min_var=CFG.HMM_MIN_VAR).fit(X_train)
            return hmm
        except Exception as e:
            log.warning(f"⚠️ فشل تدريب HMM ({e}) — رجوع مؤقت إلى KMeans لهذا الأصل فقط")
            return fit_kmeans(X_train, k=k)
    return fit_kmeans(X_train, k=k)


def assign_states(X, model):
    if isinstance(model, GaussianHMM):
        return model.predict(X).astype(np.int32)
    return assign(X, model)


# ---------- (٣) معايرة الاحتكاك من دالة الترابط الذاتي (Onsager) ----------
def calibrate_friction_from_autocorrelation(returns_train: np.ndarray, max_lag=None) -> float:
    """
    ζ ∝ ∫₀^∞ ⟨δX(0)δX(t)⟩ dt  (نظرية الاستجابة الخطية / Onsager).
    نقدّرها بالمجموع المتقطع لدالة الترابط الذاتي لعوائد التدريب حتى أول تقاطع
    مع الصفر (زمن الترابط τ)، ثم ζ_0 = 1/τ: كلما تلاشت الارتباطات أسرع، زاد
    الاحتكاك (فقدان الذاكرة أسرع = مقاومة أكبر للتنبؤ).
    """
    max_lag = max_lag or CFG.FRICTION_ACF_MAX_LAG
    r = np.asarray(returns_train, dtype=np.float64)
    r = r[np.isfinite(r)]
    if len(r) < max_lag * 3:
        return CFG.GAMMA_0
    r = r - r.mean()
    var0 = np.dot(r, r) / len(r)
    if var0 < 1e-14:
        return CFG.GAMMA_0
    tau = 1.0  # المساهمة عند اللاق صفر
    for lag in range(1, max_lag + 1):
        rho = np.dot(r[:-lag], r[lag:]) / ((len(r) - lag) * var0)
        if rho <= 0:
            break
        tau += 2.0 * rho
    tau = max(tau, 1e-6)
    zeta0 = 1.0 / tau
    return float(max(zeta0, CFG.FRICTION_MIN))


# ---------- (١٠) أس هيرست لكشف الأنظمة غير الإرغودية ----------
def compute_hurst_series(closes: np.ndarray, window=None) -> np.ndarray:
    """
    R/S ~ n^H عبر نافذة متحركة. H≈0.5 يعني سلوكاً إرغودياً (مشياً عشوائياً)؛
    الانحراف الكبير عنه يكسر افتراض ثبات التوزيع الذي يقوم عليه بقية النموذج.
    """
    window = window or CFG.HURST_WINDOW
    n = len(closes)
    H = np.full(n, 0.5)
    if n < window + 5:
        return H
    lr = np.diff(np.log(np.maximum(closes, 1e-12)))
    lags = np.unique(np.clip(np.logspace(0.7, np.log10(window / 2), 8).astype(int), 2, window // 2))
    for i in range(window, n):
        seg = lr[max(0, i - window):i]
        if len(seg) < window // 2:
            continue
        rs_vals = []
        for lag in lags:
            if lag >= len(seg):
                continue
            m = len(seg) - (len(seg) % lag)
            if m < lag * 2:
                continue
            chunks = seg[:m].reshape(-1, lag)
            rs_chunk = []
            for c in chunks:
                mean_c = c.mean()
                dev = np.cumsum(c - mean_c)
                R = dev.max() - dev.min()
                S = c.std(ddof=1)
                if S > 1e-12:
                    rs_chunk.append(R / S)
            if rs_chunk:
                rs_vals.append((lag, np.mean(rs_chunk)))
        if len(rs_vals) >= 3:
            lags_a = np.log([v[0] for v in rs_vals])
            rs_a = np.log([max(v[1], 1e-8) for v in rs_vals])
            slope, *_ = linregress(lags_a, rs_a)[0:1] + linregress(lags_a, rs_a)[1:]
            try:
                slope = linregress(lags_a, rs_a).slope
                H[i] = float(np.clip(slope, 0.01, 0.99))
            except Exception:
                pass
    return H


# ---------- (٧) كيلي كسري بقيد CVaR ----------
def fractional_kelly_cvar(win_prob: float, reward_risk_ratio: float, trade_returns: np.ndarray,
                            cfg) -> float:
    """
    كيلي للرهان الثنائي (win/loss) بعائد b (= TP/SL):  f* = p - (1-p)/b
    (هذا هو معيار كيلي القياسي لتوزيع برنولي ذي عائدين ثابتين، أدق من μ/σ²
    الغاوسي عندما تكون الصفقة فعلياً SL/TP ثابتين).
    نضربه بكسر (KELLY_FRACTION) لتقليل التذبذب، ثم نتحقق أن CVaR الناتج عن
    توزيع العوائد التاريخية للاستراتيجية لا يتجاوز الحد المسموح؛ إن تجاوزه،
    نقلّص f حتى يتحقق القيد.
    """
    p = float(np.clip(win_prob, 1e-3, 1 - 1e-3))
    b = max(float(reward_risk_ratio), 1e-3)
    f_kelly = p - (1.0 - p) / b
    f = max(f_kelly, 0.0) * cfg.KELLY_FRACTION

    tr = np.asarray(trade_returns, dtype=np.float64)
    tr = tr[np.isfinite(tr)]
    if len(tr) >= 20:
        alpha = cfg.CVAR_ALPHA
        var_q = np.percentile(tr, alpha * 100)
        tail = tr[tr <= var_q]
        cvar = float(-tail.mean()) if len(tail) > 0 else 0.0  # خسارة موجبة متوقعة في أسوأ α%
        if cvar > 1e-9:
            f_cvar_cap = cfg.CVAR_MAX_LOSS_FRACTION / cvar
            f = min(f, f_cvar_cap)

    return float(np.clip(f, cfg.MIN_RISK, cfg.MAX_RISK))


# ---------- (٩) مصفوفة ارتباط منقبضة (Ledoit-Wolf) ----------
def ledoit_wolf_correlation(returns_matrix: np.ndarray) -> np.ndarray:
    """Σ_shrunk = δT + (1-δ)Σ_sample عبر انكماش Ledoit-Wolf، محوّلة إلى مصفوفة ارتباط."""
    if returns_matrix.shape[0] < 20 or returns_matrix.shape[1] < 2:
        n = returns_matrix.shape[1]
        return np.eye(n)
    lw = LedoitWolf().fit(returns_matrix)
    cov = lw.covariance_
    d = np.sqrt(np.diag(cov))
    d[d < 1e-12] = 1e-12
    corr = cov / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)
    return corr


# ---------- (٨) أثر السعر على طراز Almgren-Chriss ----------
def almgren_chriss_slippage(price: float, qty: float, adv_usd: float, action: str,
                              eta=None, gamma_perm=None) -> float:
    """
    التكلفة الكلية = η∫v²dt (أثر مؤقت، تربيعي في معدل التنفيذ) + γ∫|v|dt (أثر
    دائم، خطي في الحجم). نُقارب معدل التنفيذ v بنسبة (قيمة الصفقة / ADV اليومي).
    """
    eta = eta if eta is not None else CFG.AC_ETA
    gamma_perm = gamma_perm if gamma_perm is not None else CFG.AC_GAMMA_PERM
    notional = abs(qty) * price
    participation = notional / max(adv_usd, 1e-6)
    participation = min(participation, 1.0)
    temp_impact = eta * (participation ** 2)
    perm_impact = gamma_perm * participation
    total_impact_frac = CFG.SLIP_BASE + temp_impact + perm_impact
    total_impact_frac = min(total_impact_frac, CFG.MAX_SLIPPAGE_FRACTION * 10)  # سقف أمان
    slip = price * total_impact_frac
    return price + slip if action == "BUY" else price - slip


# ---------- (١١) Deflated Sharpe Ratio و PBO تقريبي ----------
def _norm_cdf(x):
    from math import erf, sqrt
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def deflated_sharpe_ratio(trade_returns: np.ndarray, n_trials: int = None) -> Dict:
    """
    DSR = Φ[(SR - SR0)√(T-1) / √(1-γ3·SR+((γ4-1)/4)·SR²)]
    SR0 هو أقصى شارب متوقع تحت فرضية عدم وجود مهارة عبر n_trials محاولة/توليفة
    (تقريب Bailey & López de Prado). إن كانت DSR منخفضة، فالأداء المرصود لا
    يمكن تمييزه إحصائياً عن أفضل نتيجة عشوائية من بين المحاولات المتعددة.
    """
    n_trials = n_trials or CFG.N_TRIALS_TESTED
    r = np.asarray(trade_returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    T = len(r)
    if T < 10:
        return {'sr': 0.0, 'sr0': 0.0, 'dsr': 0.5, 'note': 'عدد صفقات غير كافٍ لتقدير DSR'}

    sr = float(np.mean(r) / (np.std(r, ddof=1) + 1e-12))
    g3 = float(skew(r, bias=False))
    g4 = float(kurtosis(r, bias=False)) + 3.0  # kurtosis الزائدة -> الكلية

    # SR0: أقصى شارب متوقع من بين n_trials محاولة مستقلة عشوائية (تقريب جامبل)
    if n_trials > 1:
        euler_gamma = 0.5772156649
        from math import sqrt as _sqrt, log as _log
        sr0 = (1 - euler_gamma) * _norm_ppf_approx(1 - 1.0 / n_trials) + \
              euler_gamma * _norm_ppf_approx(1 - 1.0 / (n_trials * np.e))
        sr0 = sr0 / _sqrt(max(T - 1, 1))
    else:
        sr0 = 0.0

    denom = np.sqrt(max(1e-9, 1 - g3 * sr + ((g4 - 1) / 4.0) * sr ** 2))
    z = (sr - sr0) * np.sqrt(max(T - 1, 1)) / denom
    dsr = _norm_cdf(z)
    return {'sr': sr, 'sr0': sr0, 'dsr': float(dsr), 'n_trials': n_trials,
            'note': 'DSR>0.95 يوحي بحافة يصعب تفسيرها بمحض التعدد/الحظ'}


def _norm_ppf_approx(p):
    # تقريب Acklam لدالة الكسور المئوية العكسية للتوزيع الطبيعي القياسي
    if p <= 0: return -8.0
    if p >= 1: return 8.0
    from math import log, sqrt
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow = 0.02425
    if p < plow:
        q = sqrt(-2 * log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - plow:
        q = sqrt(-2 * log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5; r = q*q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def probability_backtest_overfitting_approx(trade_returns: np.ndarray, n_splits: int = 8) -> Dict:
    """
    تقريب مبسّط لـ PBO: نقسّم سلسلة عوائد الصفقات إلى n_splits شرائح متتالية،
    نحسب شارب كل شريحة (In-Sample) وشارب البقية (Out-of-Sample المقابل)، ثم
    نقيس كم مرة كانت أفضل شريحة IS هي الأسوأ فعلياً OOS (علامة overfitting).
    هذا تقريب اتجاهي وليس CSCV الكامل (الذي يتطلب عدة توليفات إعداد فعلية،
    غير متاحة من باك-تيست واحد) — استخدمه كإشارة تحذير لا كإثبات نهائي.
    """
    r = np.asarray(trade_returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < n_splits * 10:
        return {'pbo_approx': None, 'note': 'صفقات غير كافية لتقدير PBO التقريبي'}
    chunks = np.array_split(r, n_splits)
    degrade_count = 0
    for i in range(n_splits):
        is_r = chunks[i]
        oos_r = np.concatenate([c for j, c in enumerate(chunks) if j != i])
        sr_is = np.mean(is_r) / (np.std(is_r, ddof=1) + 1e-12)
        sr_oos = np.mean(oos_r) / (np.std(oos_r, ddof=1) + 1e-12)
        if sr_is > 0 and sr_oos <= 0:
            degrade_count += 1
    pbo = degrade_count / n_splits
    return {'pbo_approx': float(pbo),
            'note': 'نسبة الشرائح ذات أداء داخلي إيجابي وأداء خارجي غير إيجابي (تقريب اتجاهي فقط)'}


# ---------- (٥) المعلومات المتبادلة لفلترة الميزات ----------
def mutual_information_binned(x: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """I(X;Y) = ΣΣ p(x,y) log[p(x,y)/(p(x)p(y))] بتقطيع (binning) بسيط للمتغيرين."""
    x = np.asarray(x, dtype=np.float64); y = np.asarray(y, dtype=np.float64)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 30:
        return 0.0
    x_bins = np.histogram_bin_edges(x, bins=bins)
    y_bins = np.histogram_bin_edges(y, bins=bins)
    joint, _, _ = np.histogram2d(x, y, bins=[x_bins, y_bins])
    pxy = joint / joint.sum()
    px = pxy.sum(axis=1, keepdims=True)
    py = pxy.sum(axis=0, keepdims=True)
    nz = pxy > 0
    mi = np.sum(pxy[nz] * np.log2(pxy[nz] / (px @ py)[nz] + 1e-300))
    return float(max(mi, 0.0))


def rank_features_by_mutual_information(feature_dict: Dict[str, np.ndarray],
                                          forward_return: np.ndarray, bins: int = 10) -> List[Tuple[str, float]]:
    """أداة تحليل غير متصلة (offline): تُرجع الميزات مرتّبة تنازلياً حسب I(X;forward_return)."""
    scores = [(name, mutual_information_binned(vals, forward_return, bins=bins))
              for name, vals in feature_dict.items()]
    return sorted(scores, key=lambda t: -t[1])


# ---------- (١٢) اختلال تدفق الأوامر — جاهزة للتفعيل عند توفر بيانات L2 ----------
def compute_ofi(bid_vol: float, ask_vol: float) -> float:
    """OFI = (V_bid - V_ask) / (V_bid + V_ask). تتطلب بث دفتر أوامر L2؛ معطّلة افتراضياً
    (CFG.OFI_ENABLED=False) لأن خط أنابيب البيانات الحالي يعتمد فقط على شموع OHLCV."""
    denom = bid_vol + ask_vol
    if denom <= 0:
        return 0.0
    return float((bid_vol - ask_vol) / denom)


# ---------- (٤) مصنف احتمالي معاير لتفعيل الدخول (Platt scaling) ----------
class CalibratedEntryClassifier:
    """
    يستبدل P_activation = exp(-fric/(force*T)) الاعتباطية باحتمال حقيقي مُعاير:
    يُدرَّب انحدار لوجستي على ميزات الإشارة (تسارع جيوديسي، احتكاك، T_info،
    فجوة التوازن...) للتنبؤ بما إذا كانت الصفقة ستربح (تصل TP قبل SL خلال أفق
    محدد)، ثم يُعايَر الناتج بـ Platt scaling (CalibratedClassifierCV) ليطابق
    التكرار الفعلي بدل شكل دالي مفروض مسبقاً.
    """
    FEATURE_NAMES = ['geo_accel_abs', 'friction', 'T_info', 'dH', 'gauge_force',
                      'delta_gap', 'C', 'ema_accel']

    def __init__(self):
        self.scaler = StandardScaler()
        self.clf = None
        self.fitted = False
        self.win_rate_train = 0.5

    def _feat_matrix(self, ad, indices):
        rows = []
        for fi in indices:
            rows.append([
                abs(ad.geodesic_accel[fi]), ad.friction[fi], ad.T_info[fi], ad.dH[fi],
                ad.gauge_force[fi], ad.delta_gap[fi], ad.C[fi], ad.ema_accel[ad.feat_start + fi]
                if ad.feat_start + fi < len(ad.ema_accel) else 0.0,
            ])
        return np.array(rows, dtype=np.float64)

    def fit_from_asset(self, ad, cfg):
        """يبني عيّنات تدريب من فترة التدريب فقط عبر افتراض SL/TP كما في build_signals،
        ويلصق التسمية (فوز=1/خسارة=0) بمسح أمامي فعلي على بيانات التدريب (لا تسريب)."""
        n_train = ad.train_end
        horizon = cfg.CLASSIFIER_LABEL_HORIZON
        idxs, labels = [], []
        for fi in range(20, max(n_train - horizon - 1, 20)):
            ci = ad.feat_start + fi
            if ci + horizon >= len(ad.closes) - 1:
                continue
            p0 = ad.closes[ci]
            if p0 <= 0:
                continue
            micro_mom = p0 - ad.closes[ci - 3]
            if micro_mom == 0:
                continue
            action = "BUY" if micro_mom > 0 else "SELL"
            sl_dist = compute_geodesic_stop(p0, ad, fi, cfg)
            tp_dist = sl_dist * cfg.GEO_TP_R_MULT
            future = ad.closes[ci + 1: ci + 1 + horizon]
            if len(future) == 0:
                continue
            if action == "BUY":
                hit_tp = np.any(future >= p0 + tp_dist)
                hit_sl_idx = np.argmax(future <= p0 - sl_dist) if np.any(future <= p0 - sl_dist) else -1
            else:
                hit_tp = np.any(future <= p0 - tp_dist)
                hit_sl_idx = np.argmax(future >= p0 + sl_dist) if np.any(future >= p0 + sl_dist) else -1
            hit_tp_idx = np.argmax(future >= p0 + tp_dist) if action == "BUY" and hit_tp else \
                         (np.argmax(future <= p0 - tp_dist) if hit_tp else -1)
            if hit_tp and (hit_sl_idx == -1 or hit_tp_idx <= hit_sl_idx):
                label = 1
            else:
                label = 0
            idxs.append(fi); labels.append(label)

        if len(idxs) < cfg.CLASSIFIER_MIN_SAMPLES:
            self.fitted = False
            return self

        X = self._feat_matrix(ad, idxs)
        y = np.array(labels)
        if len(np.unique(y)) < 2:
            self.fitted = False
            return self

        Xs = self.scaler.fit_transform(X)
        base = LogisticRegression(max_iter=500, class_weight='balanced')
        try:
            n_pos = int(y.sum()); n_neg = len(y) - n_pos
            cv_folds = min(3, n_pos, n_neg)
            if cv_folds >= 2:
                self.clf = CalibratedClassifierCV(base, method='sigmoid', cv=cv_folds)
            else:
                self.clf = base
            self.clf.fit(Xs, y)
            self.fitted = True
            self.win_rate_train = float(y.mean())
        except Exception as e:
            log.warning(f"⚠️ فشل تدريب المصنّف المعاير ({e}) — رجوع إلى الصيغة اللوجستية القديمة")
            self.fitted = False
        return self

    def predict_proba_one(self, ad, fi) -> Optional[float]:
        if not self.fitted or self.clf is None:
            return None
        X = self._feat_matrix(ad, [fi])
        Xs = self.scaler.transform(X)
        try:
            return float(self.clf.predict_proba(Xs)[0, 1])
        except Exception:
            return None


def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):
    """
    الطور الخامس: مستشعر الأوج بالتكامل الحركي (Action Integral).
    [ملاحظة v6.3]: هذه الدالة ومعاييرها العددية (0.003/0.01/0.005) لم تُمس إطلاقاً —
    المشكلة لم تكن في العتبات بل في *متى ومن أي بيانات* تُستدعى هذه الدالة في
    التداول الحي (راجع LiveEngine._position_guardian وتعليقات AssetData المغلقة).
    """
    if fi < 3:
        return False, ""

    pnl = (current_price - entry_price)/entry_price if pos_action == "BUY" else (entry_price - current_price)/entry_price

    min_profit = 0.003 if CFG.SINGULARITY_MODE else 0.01

    if pnl < min_profit:
        return False, ""

    dF_window = ad.dF[fi-2:fi+1]
    sum_dF = np.sum(dF_window)

    accel_window = ad.geodesic_accel[fi-2:fi+1]
    accel_mean = np.mean(accel_window)

    energy_exhausted = (sum_dF > 0.005)

    if pos_action == "BUY" and energy_exhausted and accel_mean < 0.005:
        return True, "Apex: Action Integral Exhaustion"
    if pos_action == "SELL" and energy_exhausted and accel_mean > -0.005:
        return True, "Apex: Action Integral Exhaustion"

    return False, ""


# ════════════════════════════════════════════════════════════════
# § 18.5  بروتوكول مايسنر لمنع الانزلاق (Quantum Chunking) — v6.3
# ════════════════════════════════════════════════════════════════

def _round_amount_price(exchange, symbol: str, qty: float, price: float) -> Tuple[float, float]:
    """
    [إصلاح D19] تقريب الكمية والسعر وفق دقة المنصة (stepSize/tickSize) قبل إرسال
    أي أمر. بدون هذا، قد يرفض المُبادِل (exchange) الأمر بصمت أو يُقرّبه بطريقة
    غير متوقعة، وهو ما يُنتج "حزماً فاشلة" تُحسب خطأً كأوامر غامضة أو مفقودة رغم
    أن السبب الحقيقي أبسط من ذلك بكثير: دقة رقمية غير متوافقة مع فلاتر المنصة.
    """
    q, p = qty, price
    try:
        q = float(exchange.amount_to_precision(symbol, qty))
    except Exception:
        pass
    try:
        p = float(exchange.price_to_precision(symbol, price))
    except Exception:
        pass
    if q <= 0:
        q = qty
    if p <= 0:
        p = price
    return q, p


def _get_market_order_max_qty(exchange, symbol: str) -> Optional[float]:
    """
    [إصلاح EXEC-3 — جذر خطأ -4005 "Quantity greater than max quantity"]
    منصة Binance Futures تفرض حداً أقصى للكمية لكل *أمر سوق واحد* أقل بكثير
    عادة من الحد الأقصى لأوامر Limit — عبر فلتر `MARKET_LOT_SIZE` (وليس
    `LOT_SIZE` العادي الذي يعكسه `market['limits']['amount']['max']` الموحّد
    في ccxt). لذا فإن مركزاً كبيراً (مثل PORTAL/USDT في السجل المُبلَّغ) قد
    يكون أصغر تماماً من حد Limit العادي، لكنه يتجاوز حد MARKET_LOT_SIZE الأضيق
    فيُرفَض بـ -4005 فور تحويل الخروج إلى أمر سوق (EXIT_ORDER_TYPE="market").
    هذه الدالة تبحث عن الفلتر الدقيق أولاً، ثم تتراجع بأمان للحد الموحّد.
    تُعيد None إن تعذّر العثور على أي حد (فيتصرف المتصل حينها دون تقسيم).
    """
    try:
        m = exchange.market(symbol)
    except Exception:
        return None
    try:
        for f in (m.get('info', {}) or {}).get('filters', []) or []:
            if f.get('filterType') == 'MARKET_LOT_SIZE':
                mx = f.get('maxQty')
                if mx:
                    return float(mx)
        for f in (m.get('info', {}) or {}).get('filters', []) or []:
            if f.get('filterType') == 'LOT_SIZE':
                mx = f.get('maxQty')
                if mx:
                    return float(mx)
    except Exception:
        pass
    try:
        mx = (m.get('limits', {}) or {}).get('amount', {}).get('max')
        if mx:
            return float(mx)
    except Exception:
        pass
    return None


def execute_market_order_safe(exchange, symbol: str, side: str, qty: float,
                               fallback_price: float = 0.0, reduce_only: bool = False) -> Tuple[float, float, bool]:
    """
    [إصلاح EXEC-3] غلاف آمن حول `create_market_order` يُقسِّم الكمية تلقائياً
    إلى دفعات متتالية إن تجاوزت حد MARKET_LOT_SIZE للرمز، بدل إرسال أمر واحد
    قد يُرفَض بالكامل (-4005) ويترك المركز بلا حماية بانتظار التسوية الدورية.

    الحالة الشائعة (qty ضمن الحد): طلب سوق واحد فقط — بلا أي عبء إضافي أو
    تأخير، تماماً كالسلوك السابق. الحالة النادرة (مركز كبير جداً): عدة أوامر
    سوق متتالية سريعة (لا تزال فورية التنفيذ)، مع تجميع الكمية المُنفَّذة
    ومتوسط السعر المرجّح بالكمية عبر كل الدفعات.

    [تمييز مهم بين نوعي الفشل] ليست كل استثناءات create_market_order متكافئة:
      - رفض تحقّق مسبق من المنصة (مثل -4005 "Quantity greater than max
        quantity"، أو -1013 فلتر غير مستوفى) هو رفض **مضمون قبل أي تنفيذ** —
        المنصة تتحقق من الفلاتر قبل قبول الأمر، فلا شك أن الكمية هذه لم
        تُنفَّذ إطلاقاً؛ آمن اعتبارها فشلاً نظيفاً (صفر تنفيذ) والمتابعة.
      - خطأ شبكي/مهلة (NetworkError/RequestTimeout/ExchangeNotAvailable) هو
        فعلاً **غامض**: قد يكون الأمر نُفِّذ فعلياً على المنصة رغم فشل وصول
        الاستجابة للعميل. في هذه الحالة فقط نتحقق من positionAmt الفعلي عبر
        fetch_positions لمعرفة ما إذا تغيّر المركز حقاً، بدل افتراض الفشل أو
        النجاح عشوائياً — عبء إضافي ضئيل (استدعاء واحد) ويقع فقط في المسار
        النادر (استثناء)، فلا يُبطئ التشغيل الطبيعي إطلاقاً.

    تُعيد (الكمية_المُنفَّذة, متوسط_السعر, غامض) — `غامض=True` فقط إذا تعذّر
    التحقق من أي تنفيذ فعلي إطلاقاً عبر كل الدفعات.
    """
    import ccxt as _ccxt

    def _get_position_amt() -> Optional[float]:
        try:
            positions = exchange.fetch_positions(symbols=[symbol])
            for p in positions:
                amt = float(p.get('info', {}).get('positionAmt', p.get('contracts', 0)) or 0)
                if amt != 0:
                    return amt
            return 0.0
        except Exception:
            return None

    _mo_params = {'reduceOnly': True} if reduce_only else {}

    def _place_one(order_qty: float) -> Tuple[float, float, bool]:
        """يُرسل دفعة سوق واحدة. تُعيد (منفَّذ, سعر, غامض_فعلاً)."""
        try:
            order = exchange.create_market_order(symbol, side, order_qty, params=_mo_params)
            f = float(order.get('filled', order_qty) or order_qty)
            a = float(order.get('average') or order.get('price') or 0.0)
            return (f, a, False) if f > 0 else (0.0, 0.0, False)
        except _ccxt.NetworkError as e:
            # غامض فعلاً: تحقّق من المنصة مباشرة بدل التخمين.
            log.warning(f"⚠️ خطأ شبكي أثناء أمر سوق ({symbol}, qty={order_qty}): {e} — "
                        f"يجري التحقق المباشر من المنصة...")
            before = _get_position_amt()
            time.sleep(0.5)
            after = _get_position_amt()
            if before is not None and after is not None and abs(after - before) > 0:
                verified_qty = abs(after - before)
                log.info(f"  ⤷ تحقّق: تغيّر المركز فعلياً بمقدار {verified_qty:.6f} رغم الخطأ الشبكي.")
                return verified_qty, 0.0, False  # السعر غير معروف بدقة؛ الاستدعاء الأعلى سيعتمد سعر السوق الحالي بدلاً منه
            return 0.0, 0.0, True  # تعذّر التحقق أو لم يتغيّر شيء فعلاً — غامض حقاً
        except Exception as e:
            # رفض تحقّق مسبق من المنصة (فلتر، رصيد، دقة...) — فشل نظيف ومؤكد.
            log.error(f"❌ رُفض أمر السوق ({symbol}, qty={order_qty}): {e}")
            return 0.0, 0.0, False

    max_qty = _get_market_order_max_qty(exchange, symbol)
    q_total, _ = _round_amount_price(exchange, symbol, qty, 1.0)

    if not max_qty or q_total <= max_qty:
        f, a, ambiguous = _place_one(q_total)
        if ambiguous:
            return 0.0, 0.0, True
        if f <= 0:
            return 0.0, 0.0, True
        return f, (a if a > 0 else fallback_price), False

    # تقسيم إلى دفعات ضمن الحد الأقصى المسموح لكل أمر سوق واحد
    n_chunks = int(np.ceil(q_total / max_qty))
    remaining = q_total
    filled_total = 0.0
    value_total = 0.0
    any_unfilled = False
    log.warning(f"⚠️ كمية {symbol} ({q_total}) تتجاوز حد أمر السوق الواحد ({max_qty}) — "
                f"سيُقسَّم التنفيذ إلى {n_chunks} دفعة متتالية.")
    for i in range(n_chunks):
        chunk_qty = min(max_qty, remaining)
        chunk_qty, _ = _round_amount_price(exchange, symbol, chunk_qty, 1.0)
        if chunk_qty <= 0:
            break
        f, a, _amb = _place_one(chunk_qty)
        if f > 0:
            filled_total += f
            a_eff = a if a > 0 else fallback_price
            value_total += f * a_eff
            remaining -= f
        else:
            any_unfilled = True
            log.error(f"❌ فشلت دفعة سوق {i+1}/{n_chunks} لـ {symbol} (qty={chunk_qty}) — "
                      f"سيُتابَع بالدفعات المتبقية.")
            # نتابع بقية الدفعات بدل التوقف الكامل — أي تنفيذ جزئي حقيقي
            # أفضل من ترك المركز كاملاً بلا حماية.
            continue

    if filled_total <= 0:
        return 0.0, 0.0, True
    avg_price = value_total / filled_total if filled_total > 0 else 0.0
    if any_unfilled:
        log.warning(f"⚠️ اكتمل تنفيذ {symbol} جزئياً عبر الدفعات: {filled_total:.6f}/{q_total:.6f} "
                     f"— الباقي سيُعاد تقييمه عبر التسوية الدورية.")
    return filled_total, avg_price, False



def _fetch_book_prices(exchange, symbol: str, fallback_mid: float) -> Tuple[Optional[float], Optional[float], float]:
    """يجلب أفضل سعرَي عرض/طلب حاليين، مع رجوع آمن لسعر افتراضي عند الفشل."""
    try:
        ob = exchange.fetch_order_book(symbol, limit=5)
        best_bid = ob['bids'][0][0]
        best_ask = ob['asks'][0][0]
        return best_bid, best_ask, (best_bid + best_ask) / 2
    except Exception as e:
        log.error(f"فشل جلب دفتر الأوامر لـ {symbol}: {e}")
        return None, None, fallback_mid


def execute_quantum_chunks(exchange, symbol: str, side: str, qty: float, limit_price: float,
                            pending_orders=None, order_meta: Optional[Dict] = None):
    """
    [إعادة هيكلة v6.3] تنفيذ بدفتر كمية صريح (Quantity Ledger) وإعادة تسعير عند
    الانحراف فقط (لا مؤقت أعمى).

    المشكلتان اللتان أبلغ عنهما المستخدم وحلّهما هنا معاً:

    1) "السوق يتحرك أثناء وضع الأوامر ولا يعرف البوت متى يكتفي بالكمية":
       كانت النسخة السابقة تحسب `num_chunks`/`chunk_qty` **مرة واحدة** في بداية
       الدالة بناءً على السعر اللحظي عند تلك اللحظة فقط، ثم تُرسل كل الحزم بهذا
       الحجم الثابت بغض النظر عمّا يحدث للسعر بعدها. الآن نستخدم متغير حالة صريح
       `remaining_qty` يُنقَص بالضبط بمقدار ما يتأكد أنه نُفّذ فعلياً (وليس بمقدار
       ما *كان يُفترض* أن يُنفَّذ) بعد كل حزمة، ويُعاد جلب دفتر الأوامر وتسعير كل
       حزمة تالية على حدة بالسعر اللحظي الجديد. هذا يعني أن الدالة "تعرف" في كل
       لحظة بالضبط: كم دخلنا فعلياً (`filled_qty`) وكم تبقّى (`remaining_qty`)،
       وتتوقف تلقائياً بمجرد نفاد `remaining_qty` — لا حاجة لأي "تخمين" لاحق.

    2) "الاعتماد على مدة زمنية لإلغاء الأمر يُفقده أولويته في دفتر الأوامر":
       سابقاً: مهلة ثابتة (5 ثوانٍ) ثم إلغاء وإعادة إرسال دائماً، حتى لو كان
       الأمر لا يزال عند أفضل سعر (Best Bid/Ask) ولم يتحرك السوق إطلاقاً — وهذا
       يعني فقدان الأولوية الزمنية (Time Priority) في محرك المطابقة (Price-Time
       Priority) دون أي داعٍ، ويُبطل فعلياً الغرض من "تكميم الأوامر" (كسب عمولة
       الصانع MAKER_FEE السالبة يتطلب البقاء في الصف لا القفز خارجه باستمرار).
       الآن: نُبقي الأمر مرتاحاً في مكانه طالما أنه **لا يزال ضمن سماحية انحراف
       صغيرة (ORDER_PRICE_DRIFT_BPS) عن أفضل سعر متاح** — نتحقق من هذا الانحراف
       دورياً (ORDER_DRIFT_CHECK_SECS) لا عند كل استعلام تعبئة (توفيراً لحدود
       معدل الطلبات). لا نُلغي/نُعيد التسعير إلا في حالتين فقط:
         (أ) ابتعد السوق عن سعرنا بما يتجاوز السماحية (الأمر لم يعد تنافسياً).
         (ب) تجاوزنا سقف أمان مطلق (ORDER_HARD_TIMEOUT_SECS) لمنع التعليق الأبدي
             في سوق شبه ميت أو عند عطل شبكي.

    ملاحظة حرجة: عند دخول حالة "غامضة" (فشل الإلغاء والتحقق معاً) نتوقف فوراً عن
    إرسال أي حزم إضافية (Circuit-Breaker) ونُبقي الأمر مسجلاً عمداً في
    `pending_orders` (لا نحذفه) ليتم حله لاحقاً عبر `pending_janitor_loop` أو
    `position_reconcile_loop`، بدل المخاطرة بازدواج التعرض.

    order_meta: بيانات إضافية اختيارية (مثل {'purpose':'entry','action':'BUY',
    'dyn_sl_factor':0.01}) تُدمَج في كل سجل pending_orders يُنشأ هنا، لتمكين أي
    مكوّن لاحق (المُنظِّف الدوري أو مطابقة المراكز) من "تبنّي" أي تعبئة متأخرة أو
    غامضة بشكل صحيح ومُدار بالكامل (SL/TP حقيقيان) بدل تركها بلا إدارة أو، الأسوأ،
    إدارتها بقيم وهمية خطيرة (راجع الشرح في LiveEngine.position_reconcile_loop).

    العائد: (الكمية الفعلية المنفذة، متوسط سعر التنفيذ، هل تبقّت حزمة غامضة الحالة)
    """
    order_meta = order_meta or {}
    # [إصلاح SAFETY-1 — خطر انقلاب المركز] reduceOnly لأوامر الخروج فقط: يمنع
    # المنصة من قبول كمية تتجاوز المركز الفعلي وتحويلها خطأً إلى مركز معاكس
    # (قلب الاتجاه بدل الإغلاق) عند أي تفاوت طفيف بين الكمية المحلية والفعلية
    # على المنصة — مثال واقعي: بقايا تعبئة متأخرة لم تُحتسَب محلياً بعد. لا
    # تأثير إطلاقاً على أوامر الدخول (يجب أن تبقى حرة لفتح مركز جديد).
    # ملاحظة: 'safety_flatten' (تسوية مركز غير متتبع الأصل — راجع
    # _safe_flatten_unknown) هي أيضاً دائماً إغلاق تعرّض قائم، فتستحق نفس حماية
    # reduceOnly رغم أنها ليست إغلاقاً استراتيجياً عادياً بمعنى 'exit'.
    _order_params = {'reduceOnly': True} if order_meta.get('purpose') in ('exit', 'safety_flatten') else {}
    mid_price = limit_price
    # تطبيع الرمز قبل أي استخدام داخلي أو تخزين
    symbol = _norm_symbol(symbol)
    best_bid, best_ask, mid_price = _fetch_book_prices(exchange, symbol, limit_price)

    if best_bid is None or best_ask is None:
        # تعذّر الوصول لدفتر الأوامر إطلاقاً: أمر سوق طارئ لكامل الكمية دفعة واحدة
        # (أفضل من عدم التنفيذ إطلاقاً، لكن أسوأ من التنفيذ الكمومي — حالة استثنائية)
        try:
            log.warning(f"⚠️ تحويل {symbol} لأمر سوق كحل طارئ (تعذّر جلب دفتر الأوامر)!")
            q, _ = _round_amount_price(exchange, symbol, qty, limit_price)
            market_order = exchange.create_market_order(symbol, side, q, params=_order_params)
            filled = float(market_order.get('filled', 0))
            avg_price = float(market_order.get('average', mid_price))
            return filled, avg_price, False
        except Exception:
            return 0.0, 0.0, False

    def _passive_price(bb, ba, mid):
        # [إصلاح EXEC-2] كان الحد الفاصل بين "ابقَ سلبياً" و"لاحق السوق" مثبَّتاً
        # على 0.2% (0.002) — نطاق واسع يسمح لحركات زخم حقيقية وصغيرة (0.05%-0.2%)
        # بتجاوز أمر الدخول السلبي دون أن يُلاحقها إطلاقاً، فتُفقَد الفرصة تماماً
        # رغم أن الإشارة كانت صحيحة. أصبح الآن قابلاً للتهيئة عبر
        # CFG.PASSIVE_CHASE_TOLERANCE (افتراضياً 0.05% بدل 0.2%) لموازنة أفضل
        # بين توفير عمولة الصانع والتقاط الفرص الحقيقية.
        tol = CFG.PASSIVE_CHASE_TOLERANCE * mid
        if side == 'buy':
            tp = min(limit_price, bb)
            if (bb - limit_price) > tol:
                tp = bb
        else:
            tp = max(limit_price, ba)
            if (limit_price - ba) > tol:
                tp = ba
        if mid > 0 and abs(tp - mid) / mid > 0.05:
            log.warning(f"⚠️ سعر {symbol} شاذ ({tp:.6f})، التصحيح إلى السعر الحالي {mid:.6f}")
            tp = mid
        return tp

    remaining_qty = float(qty)
    filled_qty = 0.0
    filled_value = 0.0
    ambiguous = False
    dust_notional = max(CFG.MIN_NOTIONAL * 0.05, CFG.ORDER_MIN_CHUNK_USD_DUST)
    overall_start = time.time()

    while remaining_qty * mid_price > dust_notional and not ambiguous:
        # ── [إصلاح: سقف زمني إجمالي] ────────────────────────────────────
        # يمنع حلقة "إرسال حزمة → لا تعبئة ولا انحراف → سقف الحزمة → إلغاء →
        # إعادة إرسال" من الدوران إلى الأبد عندما لا يوجد طرف مقابل في السوق
        # ولا يتحرك السعر (سوق هادئ جداً). نتوقف بأمان بما أُنجز فعلاً.
        if time.time() - overall_start >= CFG.ORDER_TOTAL_EXECUTION_TIMEOUT_SECS:
            log.warning(
                f"⏱️ تجاوز {symbol} السقف الزمني الإجمالي للتنفيذ "
                f"({CFG.ORDER_TOTAL_EXECUTION_TIMEOUT_SECS:.0f}s) — إيقاف بأمان. "
                f"نُفِّذ {filled_qty:.6f} من {qty:.6f} حتى الآن.")
            break
        # ── إعادة تسعير طازجة لهذه الحزمة تحديداً (يحل مشكلة السعر الجامد) ──
        best_bid, best_ask, mid_price = _fetch_book_prices(exchange, symbol, mid_price)
        if best_bid is None or best_ask is None:
            break  # فقدنا الاتصال بالسوق أثناء التنفيذ الجزئي؛ نتوقف بأمان بما أُنجز فعلاً
        target_price = _passive_price(best_bid, best_ask, mid_price)

        chunk_qty = min(remaining_qty, CFG.MAX_CHUNK_USD / max(target_price, 1e-12))
        # [إصلاح D25] لا نترك "غباراً" عالقاً لا يبلغ الحد الأدنى للقيمة الاسمية:
        # إن كانت البقية بعد هذه الحزمة أصغر من هامش الغبار، نضمّها لهذه الحزمة الآن.
        leftover_after = remaining_qty - chunk_qty
        if 0 < leftover_after * target_price < CFG.ORDER_MIN_CHUNK_USD_DUST:
            chunk_qty = remaining_qty

        chunk_qty, target_price = _round_amount_price(exchange, symbol, chunk_qty, target_price)
        if chunk_qty <= 0:
            break

        order_id = None
        try:
            order = exchange.create_limit_order(symbol, side, chunk_qty, target_price, params=_order_params)
            order_id = order['id']
            if pending_orders is not None:
                rec = {
                    'symbol': symbol, 'order_id': order_id, 'side': side,
                    'qty': chunk_qty, 'price': target_price, 'timestamp': time.time(),
                }
                rec.update(order_meta)
                pending_orders[order_id] = rec

            filled_in_chunk = False
            chunk_start = time.time()
            last_drift_check = chunk_start
            reprice_reason = None
            overall_deadline_hit = False

            while True:
                order_status = exchange.fetch_order(order_id, symbol)
                status_filled = float(order_status.get('filled', 0) or 0)
                if order_status['status'] == 'closed':
                    avg_price = float(order_status['average']) if order_status.get('average') else target_price
                    filled_qty += status_filled
                    filled_value += status_filled * avg_price
                    remaining_qty = max(0.0, remaining_qty - status_filled)
                    filled_in_chunk = True
                    if pending_orders is not None:
                        pending_orders.pop(order_id, None)
                    break

                now = time.time()
                elapsed = now - chunk_start
                if elapsed >= CFG.ORDER_HARD_TIMEOUT_SECS:
                    reprice_reason = "hard_timeout"
                    break
                # [إصلاح حرج] السقف الزمني الإجمالي يجب أن يُفحص هنا أيضاً (داخل
                # انتظار الحزمة الحالية) لا فقط بين حزمة وأخرى — وإلا فحزمة واحدة
                # بمهلة صلبة كبيرة (ORDER_HARD_TIMEOUT_SECS) قادرة على تجاوز
                # الميزانية الزمنية الإجمالية للدالة كلها قبل أن يُتاح أي فرصة
                # للتحقق منها في بداية الحلقة الخارجية.
                if now - overall_start >= CFG.ORDER_TOTAL_EXECUTION_TIMEOUT_SECS:
                    reprice_reason = "overall_timeout"
                    overall_deadline_hit = True
                    break

                # ── [إصلاح D11] لا نُلغي إلا إذا فقد الأمر أولويته فعلاً (انحراف
                # السعر) أو تجاوزنا السقف المطلق أعلاه — وليس بمجرد مرور وقت ثابت.
                if now - last_drift_check >= CFG.ORDER_DRIFT_CHECK_SECS:
                    last_drift_check = now
                    bb2, ba2, mid2 = _fetch_book_prices(exchange, symbol, target_price)
                    if bb2 is not None and ba2 is not None and mid2 > 0:
                        cur_best = bb2 if side == 'buy' else ba2
                        drift_bps = abs(cur_best - target_price) / mid2 * 10000.0
                        still_best = (side == 'buy' and target_price >= bb2) or \
                                     (side == 'sell' and target_price <= ba2)
                        if not still_best and drift_bps > CFG.ORDER_PRICE_DRIFT_BPS:
                            reprice_reason = f"drift({drift_bps:.1f}bps)"
                            break

                time.sleep(CFG.ORDER_FILL_POLL_SECS)

            if not filled_in_chunk:
                # نُلغي فقط الآن (إمّا انحراف حقيقي أو سقف أمان) — وليس بمجرد انتظار قصير
                canceled_ok = False
                try:
                    exchange.cancel_order(order_id, symbol)
                    canceled_ok = True
                except Exception as cancel_err:
                    log.error(f"فشل إلغاء الأمر {order_id}: {cancel_err}")

                resolved = False
                last_check_err = None
                for _ in range(CFG.AMBIGUOUS_ORDER_MAX_RETRIES):
                    try:
                        final_status = exchange.fetch_order(order_id, symbol)
                        f_partial = float(final_status.get('filled', 0) or 0)
                        if f_partial > 0:
                            avg_p = float(final_status.get('average') or target_price)
                            filled_qty += f_partial
                            filled_value += f_partial * avg_p
                            remaining_qty = max(0.0, remaining_qty - f_partial)
                            log.warning(
                                f"⚠️ حزمة {symbol} تعبأت جزئياً قبل إعادة التسعير "
                                f"[{reprice_reason}]: {f_partial:.6f} @ {avg_p:.4f}")
                        else:
                            log.info(f"↻ إعادة تسعير حزمة {symbol} [{reprice_reason}] — لا تعبئة سابقة")
                        resolved = True
                        break
                    except Exception as check_err:
                        last_check_err = check_err
                        time.sleep(CFG.ORDER_FILL_POLL_SECS)

                if not resolved:
                    log.error(
                        f"❌ فشل التحقق النهائي من حالة الأمر {order_id} لـ {symbol} بعد "
                        f"{CFG.AMBIGUOUS_ORDER_MAX_RETRIES} محاولات ({last_check_err}). "
                        f"canceled_ok={canceled_ok}. الحزمة تُعتبر غامضة الحالة — "
                        f"سيُترك سجلها في pending_orders ليُحل عبر التسوية الدورية.")
                    ambiguous = True
                    break  # لا نُرسل حزماً إضافية (Circuit-Breaker)

                if pending_orders is not None:
                    pending_orders.pop(order_id, None)

                if overall_deadline_hit:
                    log.warning(
                        f"⏱️ تجاوز {symbol} السقف الزمني الإجمالي للتنفيذ "
                        f"({CFG.ORDER_TOTAL_EXECUTION_TIMEOUT_SECS:.0f}s) — إيقاف بأمان. "
                        f"نُفِّذ {filled_qty:.6f} من {qty:.6f} حتى الآن.")
                    break  # نوقف الحلقة الخارجية فوراً؛ لا نبدأ حزمة جديدة إطلاقاً
                # وإلا: الحلقة الخارجية ستُعيد المحاولة تلقائياً بالكمية المتبقية بسعر جديد

        except Exception as e:
            log.error(f"خطأ في تنفيذ حزمة {symbol}: {e}")
            if pending_orders is not None and order_id is not None:
                pending_orders.pop(order_id, None)
            if filled_qty <= 0:
                try:
                    log.warning(f"⚠️ محاولة أمر سوق طارئ لبقية {symbol}")
                    q, _ = _round_amount_price(exchange, symbol, remaining_qty, target_price)
                    market_order = exchange.create_market_order(symbol, side, q, params=_order_params)
                    filled = float(market_order.get('filled', 0))
                    avg_price = float(market_order.get('average', mid_price))
                    filled_qty += filled
                    filled_value += filled * avg_price
                    remaining_qty = max(0.0, remaining_qty - filled)
                except Exception as me:
                    log.error(f"فشل أمر السوق الطارئ لـ {symbol}: {me}")
            break

    if filled_qty <= 0:
        if not ambiguous:
            log.warning(f"❌ لم يتم تنفيذ أي جزء من أمر {symbol}")
        return 0.0, 0.0, ambiguous

    avg_fill_price = filled_value / filled_qty
    log.info(f"✅ تم تنفيذ {filled_qty:.6f} من {qty:.6f} لـ {symbol} بمتوسط سعر {avg_fill_price:.4f}"
             + (" ⚠️ [حزمة غامضة متبقية]" if ambiguous else ""))
    return filled_qty, avg_fill_price, ambiguous


def pending_symbols_set(pending_orders: Dict[str, Dict]) -> set:
    """يستخرج مجموعة الرموز الفعلية من قاموس pending_orders (مفتاحه order_id)."""
    return {po['symbol'] for po in pending_orders.values()}


# ════════════════════════════════════════════════════════════════
# § 1  مسح الأصول
# ════════════════════════════════════════════════════════════════

def _default_assets():
    return ["BTC/USDT","ETH/USDT","BNB/USDT","SOL/USDT","XRP/USDT",
            "DOGE/USDT","ADA/USDT","AVAX/USDT","LINK/USDT","DOT/USDT",
            "LTC/USDT","UNI/USDT","ATOM/USDT","ETC/USDT","POL/USDT",
            "XAG/USDT","TRX/USDT","TON/USDT","BCH/USDT","NEAR/USDT",
            "APT/USDT","ICP/USDT","HBAR/USDT","VET/USDT","FIL/USDT",
            "CRO/USDT","STX/USDT","MKR/USDT","AAVE/USDT","ARB/USDT",
            "OP/USDT","INJ/USDT","SUI/USDT","TIA/USDT","SEI/USDT",
            "ALGO/USDT","GRT/USDT","PEPE/USDT","FET/USDT","RENDER/USDT",
            "LDO/USDT","KAS/USDT","WIF/USDT","THETA/USDT","EGLD/USDT",
            "SAND/USDT","MANA/USDT","AXS/USDT","XLM/USDT","CHZ/USDT"]

def _norm_symbol(sym: str) -> str:
    """
    يوحّد صيغة الرمز إلى BASE/QUOTE:SETTLE.
    إذا كان الرمز بدون :SETTLE نضيف :USDT إن كان مقابل USDT.
    """
    if ':' not in sym:
        if sym.endswith('/USDT'):
            sym = sym + ':USDT'
    return sym

def scan_top_assets(exchange, n=None) -> List[str]:
    n = n or CFG.n_assets
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"scan_top_assets: {e}")
        return _default_assets()[:n]

    scored = []
    for sym, t in tickers.items():
        if not "/USDT" in sym:
            continue
        base = sym.replace("/USDT","")
        if any(ex in base for ex in CFG.exclude_tokens):
            continue
        qv  = float(t.get("quoteVolume", 0) or 0)
        if qv < CFG.min_quote_vol_usd:
            continue
        chg = abs(float(t.get("percentage",0) or 0))
        scored.append((qv*(chg+1.0), _norm_symbol(sym)))

    scored.sort(key=lambda x: -x[0])
    sel = [_norm_symbol(s) for _,s in scored[:n]]
    if not sel:
        return [_norm_symbol(s) for s in _default_assets()[:n]]
    log.info(f"مسح الأصول: {len(sel)} عملة مختارة")
    return sel


# ════════════════════════════════════════════════════════════════
# § 2  جلب البيانات مع كاش (متوازٍ)
# ════════════════════════════════════════════════════════════════

def _load_cached(symbol, exchange, timeframe, days):
    fp  = os.path.join(CACHE_DIR, f"{symbol.replace('/','_')}_{timeframe}.parquet")
    min_rows = CFG.N + CFG.W + 100
    since_full = exchange.parse8601(
        (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()+"Z")

    if os.path.exists(fp):
        df_old = pd.read_parquet(fp)
        if df_old.index.tz is None:
            df_old.index = pd.to_datetime(df_old.index, utc=True)
        last_ts = df_old.index.max()
        if timeframe.endswith('m'):
            delta = timedelta(minutes=int(timeframe[:-1]))
        elif timeframe.endswith('h'):
            delta = timedelta(hours=int(timeframe[:-1]))
        elif timeframe.endswith('d'):
            delta = timedelta(days=int(timeframe[:-1]))
        else:
            delta = timedelta(hours=1)
        since = exchange.parse8601((last_ts + delta).isoformat() + "Z")
        rows = []
        try:
            while True:
                chunk = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
                if not chunk: break
                rows.extend(chunk); since = chunk[-1][0]+1; time.sleep(0.06)
        except Exception as e:
            log.warning(f"{symbol} update: {e}")
        if rows:
            df_new = pd.DataFrame(rows, columns=['ts','Open','High','Low','Close','Volume'])
            df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
            df_new = df_new.set_index('ts').drop_duplicates().astype(float)
            df = pd.concat([df_old, df_new])
            df = df[~df.index.duplicated(keep='last')].sort_index()
        else:
            df = df_old
        if len(df) >= min_rows:
            df.to_parquet(fp); return df
        os.remove(fp)

    rows = []
    try:
        since = since_full
        while True:
            chunk = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not chunk: break
            rows.extend(chunk); since = chunk[-1][0]+1; time.sleep(0.06)
    except Exception as e:
        log.warning(f"{symbol} full fetch: {e}")
    if len(rows) < min_rows: return None
    df = pd.DataFrame(rows, columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').drop_duplicates().astype(float)
    df.to_parquet(fp); return df


def _fetch_one(args):
    sym, exchange, tf, days = args
    try:
        df = _load_cached(sym, exchange, tf, days)
        if df is None or len(df) < CFG.N+CFG.W+100: return sym, None
        return sym, df
    except Exception as e:
        log.warning(f"{sym}: {e}"); return sym, None


def fetch_all(symbols, exchange, tf, days, workers=5):
    result = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one,(s,exchange,tf,days)):s for s in symbols}
        for f in as_completed(futs):
            sym, df = f.result()
            if df is not None:
                result[sym] = df
                log.info(f"  ✓ {sym:14s}: {len(df):,} شمعة")
            else:
                log.warning(f"  ✗ {sym}")
    return result


def _drop_unclosed_last_row(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    [v6.3] عند إعادة المزامنة عبر REST (fetch_ohlcv)، غالباً ما يُرجع آخر صف
    الشمعة الجارية غير المغلقة بعد (سلوك شائع في العديد من المنصات/ccxt). إن
    أُدرِج هذا الصف في بيانات "الشموع المغلقة" التي تُبنى عليها ميزات Apex/Topo
    فسيُعيد بالضبط نفس مشكلة "تقييم شمعة غير مكتملة" التي أصلحناها عبر بروتوكول
    الشموع المغلقة القادم من WebSocket. هذه الدالة تحذف ذلك الصف الأخير إذا كان
    وقت إغلاقه المتوقع لم يحن بعد.
    """
    if df is None or len(df) == 0:
        return df
    try:
        if timeframe.endswith('m'):
            bar_secs = int(timeframe[:-1]) * 60
        elif timeframe.endswith('h'):
            bar_secs = int(timeframe[:-1]) * 3600
        elif timeframe.endswith('d'):
            bar_secs = int(timeframe[:-1]) * 86400
        else:
            bar_secs = 3600
        last_open = df.index[-1]
        expected_close = last_open + pd.Timedelta(seconds=bar_secs)
        now = pd.Timestamp.now(tz='UTC')
        if now < expected_close:
            return df.iloc[:-1]
    except Exception:
        pass
    return df


# ════════════════════════════════════════════════════════════════
# § 3  محرك الميزات R^7
# ════════════════════════════════════════════════════════════════

def compute_features(closes, volumes, N=None):
    N = N or CFG.N
    n  = len(closes)
    lr = np.diff(np.log(np.maximum(closes, 1e-12)))
    # [إصلاح جوهري - سبب رئيسي لعدم اكتشاف أي إشارات] كانت ميزة متوسط الحجم
    # الخام (بوحدات عملة/عدد عقود، غالباً بمرتبة 1e4-1e9) ومدى السعر المطلق
    # تهيمنان على معيار المتجه L2 (norm)، فيُقسَّم المتجه بالكامل على هذا
    # المعيار الضخم ويُسحق كل بقية الميزات (العوائد/الالتواء/التفلطح/الزخم)
    # إلى أصفار عددياً تقريباً (~1e-7 وأقل). هذا يُفسد فضاء الحالة X بالكامل
    # ومن ثم كل ما يُبنى عليه (KMeans، الانحناء C، التذبذب V، الانتروبيا H) —
    # وهو السبب الجذري وراء عدم تجاوز `score` لعتبة MIN_SCORE في أي شمعة إطلاقاً.
    # الحل: تحويل الحجم ومدى السعر إلى نسب عديمة الأبعاد (قابلة للمقارنة مع
    # بقية الميزات) قبل تطبيق قصّ المعيار الآمن.
    vol_baseline = float(np.mean(volumes)) + 1e-12
    out = []
    for i in range(N, n):
        r = lr[i-N:i]; p = closes[i-N:i+1]; v = volumes[i-N:i]
        s = np.std(r, ddof=1)
        if s < 1e-10: out.append(np.zeros(7)); continue
        p_mean = float(np.mean(p)) + 1e-12
        rel_range = float(np.max(p) - np.min(p)) / p_mean
        rel_vol   = (float(np.mean(v)) / vol_baseline) if len(v) > 0 else 1.0
        vec = np.array([np.mean(r), s,
                        float(skew(r,bias=False)), float(kurtosis(r,bias=False)),
                        rel_range,
                        rel_vol,
                        float((closes[i]-closes[i-N])/(closes[i-N]+1e-12))],
                       dtype=np.float64)
        nm = np.linalg.norm(vec)
        if nm > 1.0: vec /= nm
        out.append(vec)
    return np.array(out, dtype=np.float64)


# ════════════════════════════════════════════════════════════════
# § 4  التكميم الديناميكي (التعديل ③)
# ════════════════════════════════════════════════════════════════

def compute_dynamic_k(current_capital: float, adv_usd: np.ndarray) -> int:
    adv_mean = float(np.mean(adv_usd[adv_usd > 0])) if np.any(adv_usd > 0) else 1e6
    capital_ratio = current_capital / (adv_mean + CFG.EPSILON)
    dynamic_k = int(np.floor(CFG.K_MAX * np.exp(-CFG.KQUANT_ALPHA * capital_ratio)))
    dynamic_k = max(CFG.K_MIN, min(CFG.K_MAX, dynamic_k))
    return dynamic_k


def fit_kmeans(X, k=None):
    k = k or CFG.K
    km = KMeans(n_clusters=k, n_init=15, random_state=42, max_iter=500)
    km.fit(X); return km

def assign(X, km): return km.predict(X).astype(np.int32)


# ════════════════════════════════════════════════════════════════
# § 5  الثرموديناميك
# ════════════════════════════════════════════════════════════════

def _H(sym, k=None):
    k = k or CFG.K
    if len(sym) == 0:
        return 0.0
    sym = np.clip(np.asarray(sym, dtype=np.int32), 0, k - 1)
    c = np.bincount(sym, minlength=k).astype(float)
    p = c / len(sym)
    nz = p[p > 0]
    return float(-np.sum(nz * np.log2(nz + 1e-12)))

def entropy_series(sym_q, W=None, k=None):
    W = W or CFG.W; k = k or CFG.K
    n = len(sym_q); H = np.zeros(n)
    for i in range(W-1,n): H[i] = _H(sym_q[i-W+1:i+1], k=k)
    return H

def entropy_regression(H):
    n = len(H)
    if n < 3: return {'slope':0.,'r2':0.,'se':0.,'trend':'neutral'}
    x = np.arange(n,dtype=float)
    sl,_,rv,_,se = linregress(x, H); r2 = rv**2
    if r2 < 0.05: trend='neutral'
    elif sl>0 and (se==0 or sl>2*se): trend='increasing'
    elif sl<0 and (se==0 or abs(sl)>2*se): trend='decreasing'
    else: trend='neutral'
    return {'slope':sl,'r2':r2,'se':se,'trend':trend}


# ════════════════════════════════════════════════════════════════
# § 6  الهندسة
# ════════════════════════════════════════════════════════════════

def compute_geometry(X, step=None):
    step = step or CFG.L
    n, d = X.shape
    C = np.zeros(n)
    V = np.zeros(n)
    window = max(step, 2)

    for i in range(n):
        start = max(0, i - window + 1)
        chunk = X[start:i + 1]

        if len(chunk) < 2:
            C[i] = 0.0
            V[i] = CFG.EPSILON
            continue

        diffs = np.linalg.norm(np.diff(chunk, axis=0), axis=1)
        C[i] = -float(np.mean(diffs))
        # ملاحظة: C = -(متوسط خطوات المسار) ≤ 0 دوماً بحكم البناء (سالب معيار
        # لا يمكن أن يكون موجباً). أي انحناء/تشتت مرتفع للمسار في فضاء الحالة
        # يعني C سالبة جداً — لذا يجب أن يُختبر الشرط لاحقاً بصيغة
        # `C < -CURV_THRESHOLD` وليس `C > CURV_THRESHOLD` (كان الشرط الأصلي
        # مستحيل التحقق رياضياً لأن C لا تتجاوز الصفر أبداً).

        cov = np.cov(chunk.T) if chunk.shape[0] > 1 else np.eye(d)
        # [إصلاح] محدد (determinant) مصفوفة تباين مشترك بأبعاد d=7 من نافذة
        # قصيرة (~10 عينات) يتقلص بشكل مضاعف مع عدد الأبعاد ويصل عملياً دائماً
        # تقريباً إلى ما دون قاع EPSILON=1e-9 (حتى بعد إصلاح تحجيم الميزات
        # أعلاه) — فيتجمّد V على قيمة القاع الثابتة لكل الشموع تقريباً ويُفقد
        # أي تمايز، ما يجعل عتبة V_q20 عديمة الفائدة. الحل: استخدام متوسط
        # التباين لكل بُعد (أثر المصفوفة / d) كمقياس تذبذب مستقر عددياً بدل
        # المحدد المنهار.
        V[i] = max(float(np.trace(cov)) / d, CFG.EPSILON)

    return C, V


# ════════════════════════════════════════════════════════════════
# § 7  ديناميكا الطاقة
# ════════════════════════════════════════════════════════════════

def compute_lyapunov_dynamic(X, window=60, steps=5, min_dist=10):
    n, d = X.shape
    lya = np.zeros(n)
    if n < 2 * min_dist + steps + window:
        return lya

    sr = max(1, window // 20)

    for i in range(window + steps, n):
        st = i - steps - window
        chunk = X[st:i - steps]
        divs = []

        for t in range(0, window, sr):
            ta = st + t
            if ta + steps >= n:
                continue

            xt = chunk[t]
            bd = float('inf')
            bj = -1

            for j in range(0, window, sr):
                if abs(t - j) < min_dist:
                    continue
                dd = np.linalg.norm(xt - chunk[j])
                if dd < bd:
                    bd = dd
                    bj = j

            if bj == -1 or bd < 1e-12:
                continue

            ja = st + bj
            if ja + steps >= n:
                continue

            ds = np.linalg.norm(X[ta + steps] - X[ja + steps])
            if ds > 1e-12:
                divs.append(np.log(ds / bd))

        if len(divs) > 3:
            lya[i] = np.mean(divs) / steps

    return lya

def compute_energy_dynamics(closes, lr_full, X, feat_start):
    n = len(X); N = CFG.N; KE = np.zeros(n)
    for i in range(n):
        ci = feat_start+i
        if ci>=N: KE[i] = 0.5*float(np.mean(lr_full[ci-N:ci]**2))
    lya  = compute_lyapunov_dynamic(X, window=30, steps=3, min_dist=10)
    dKE  = np.diff(KE,  prepend=KE[0])
    d2KE = np.diff(dKE, prepend=dKE[0])
    return {'KE':KE,'dKE':dKE,'d2KE':d2KE,'lya':lya}

def compute_PE(X, km, H):
    centroids = km.cluster_centers_; labels = km.predict(X)
    k = len(centroids)
    H_max = np.log2(k)
    dists = np.linalg.norm(X-centroids[labels], axis=1)
    order = np.clip(1.-H/(H_max+1e-12), 0., 1.)
    return dists*order


# ════════════════════════════════════════════════════════════════
# § 8  كاشف الانعكاس TRI
# ════════════════════════════════════════════════════════════════

def compute_tri(dH, d2H, dF, dKE, lya):
    q75 = np.percentile(lya[lya>0],75) if np.any(lya>0) else 1.
    thr = q75*CFG.LYA_THRESHOLD_MULT
    tri = np.zeros(len(dH), dtype=np.float32)
    tri += (dF  > 0).astype(np.float32)
    tri += (d2H > 0.01).astype(np.float32)
    tri += (dKE < 0).astype(np.float32)
    tri += (lya > thr).astype(np.float32)
    return tri


# ════════════════════════════════════════════════════════════════
# § 9  نقطة الدخول المثلى
# ════════════════════════════════════════════════════════════════

def find_optimal_entry(ci0, closes, KE, atr, action, feat_start):
    start = ci0+1; end = min(start+CFG.OPTIMAL_ENTRY_WAIT, len(closes)-1)
    if start >= end: return ci0, closes[ci0]
    p0   = closes[ci0]; dip = atr/p0*CFG.OPTIMAL_ENTRY_DIP
    ptgt = p0*(1.-dip) if action=="BUY" else p0*(1.+dip)
    for ci in range(start,end):
        p = closes[ci]
        if action=="BUY"  and p<=ptgt: return ci, p
        if action=="SELL" and p>=ptgt: return ci, p
    ks = max(start-feat_start, 0); ke = min(end-feat_start, len(KE)-1)
    if ke>ks:
        lm = int(np.argmin(KE[ks:ke]))
        bi = start+lm
        if bi < len(closes): return bi, closes[bi]
    return start, closes[start]


# ════════════════════════════════════════════════════════════════
# § 10  نموذج الانزلاق (كايل)
# ════════════════════════════════════════════════════════════════

def apply_slippage(price, qty, adv_usd, action, mode="backtest"):
    """
    [v7 - تحسين ٨] استُبدلت الصيغة الثابتة (SLIP_BASE فقط) بطراز Almgren-Chriss:
    أثر مؤقت تربيعي في نسبة المشاركة (qty/ADV) + أثر دائم خطي فيها. يعكس هذا
    فعلياً أن تحريك حجم أكبر نسبة إلى السيولة اليومية يكلف أكثر من نسبة ثابتة.
    """
    if mode == "backtest":
        return almgren_chriss_slippage(price, qty, adv_usd, action)
    return price

# ════════════════════════════════════════════════════════════════
# § 11  بنية البيانات
# ════════════════════════════════════════════════════════════════

@dataclass
class AssetData:
    symbol: str
    closes: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    volumes: np.ndarray
    timestamps: pd.DatetimeIndex
    X: np.ndarray
    sym_q: np.ndarray
    H: np.ndarray
    dH: np.ndarray
    d2H: np.ndarray
    E_therm: np.ndarray
    F: np.ndarray
    dF: np.ndarray
    C: np.ndarray
    V: np.ndarray
    h: np.ndarray
    score: np.ndarray
    ema200: np.ndarray
    ema_accel: np.ndarray
    atr14: np.ndarray
    adv_usd: np.ndarray
    KE: np.ndarray
    PE: np.ndarray
    ME: np.ndarray
    dKE: np.ndarray
    lya: np.ndarray
    tri: np.ndarray
    T_info: np.ndarray
    train_end: int
    feat_start: int
    km: KMeans
    dynamic_k: int

    gauge_force: np.ndarray
    friction: np.ndarray
    delta_gap: np.ndarray
    geodesic_accel: np.ndarray
    higher_tf_trend: np.ndarray

    # ══ [v7] حقول جديدة ══
    hurst: np.ndarray = None                 # تحسين ١٠: أس هيرست المتحرك
    clf: object = None                       # تحسين ٤: المصنّف الاحتمالي المعاير
    train_log_returns: np.ndarray = None     # عوائد التدريب (لكيلي/CVaR وDSR)
    friction_gamma0: float = 0.01            # القاعدة المعايرة من الارتباط الذاتي
    # ══ [جديد] لدعم شموع يابانية كاملة في رسوم Plotly للصفقات ══
    opens: np.ndarray = None

@dataclass
class Signal:
    timestamp: pd.Timestamp; symbol: str; price: float; score: float
    action: str; sl: float; tp1: float; tp2: float; tp3: float
    atr: float; lam: float; close_idx: int; feat_idx: int
    adv_usd: float; tri_val: float
    dynamic_risk: float
    T_info_val: float
    dyn_sl_factor: float = 0.1

@dataclass
class Trade:
    symbol: str; action: str; entry_price: float; exit_price: float
    pos_size: float; gross_pnl: float; fee: float; net_pnl: float
    capital_after: float; log_return: float
    entry_time: pd.Timestamp; exit_reason: str
    score: float; lam: float; liq_warn: bool
    slippage_paid: float; entry_optimized: bool; tri_at_entry: float
    dynamic_risk_used: float
    T_info_at_entry: float
    # [جديد] وقت الخروج + لقطة كاملة من قيم المؤشرات التي اعتمد عليها القرار
    # عند الدخول (تُستخدم في تصدير CSV ورسوم Plotly). القاموس فارغ افتراضياً
    # كي لا يُغيّر أي إنشاء قديم لـ Trade في أي مكان آخر من الكود.
    exit_time: pd.Timestamp = None
    indicators: Dict[str, float] = field(default_factory=dict)

@dataclass
class OpenPosition:
    symbol: str; signal: Signal
    entry_px: float; pos_size: float; trail_sl: float
    entry_cap: float; entry_ci: int; current_ci: int
    slip_paid: float; opt_entry: bool; tri_entry: float


# ════════════════════════════════════════════════════════════════
# § [جديد] تصدير الصفقات (CSV) ورسوم Plotly التفاعلية (HTML)
# ════════════════════════════════════════════════════════════════
# طبقة تقارير بحتة: لا تُغيّر أي قرار تداولي، ولا تُستدعى إلا بعد اكتمال
# الصفقة (إغلاقها) — عطلها بالكامل عبر CFG.EXPORT_TRADES_CSV/EXPORT_TRADE_HTML
# لا يُغيّر أي سلوك تداولي إطلاقاً.

def build_indicator_snapshot(ad: "AssetData", feat_idx: int) -> Dict[str, float]:
    """
    يلتقط قيم أهم المؤشرات النظرية (المسؤولة فعلياً عن قرار الدخول عبر
    `score`) عند فهرس الميزة `feat_idx` — لتُسجَّل مع كل صفقة في CSV/HTML.
    آمنة تماماً تجاه أي فهرس خارج الحدود أو مصفوفة مفقودة (None).
    """
    def _at(arr, i):
        try:
            if arr is None: return float('nan')
            if i < 0 or i >= len(arr): return float('nan')
            v = arr[i]
            return float(v) if v is not None else float('nan')
        except Exception:
            return float('nan')

    return {
        "score":          _at(ad.score, feat_idx),
        "curvature_C":    _at(ad.C, feat_idx),
        "volatility_V":   _at(ad.V, feat_idx),
        "entropy_H":      _at(ad.H, feat_idx),
        "dH":             _at(ad.dH, feat_idx),
        "d2H":            _at(ad.d2H, feat_idx),
        "free_energy_F":  _at(ad.F, feat_idx),
        "dF":             _at(ad.dF, feat_idx),
        "hmm_state_h":    _at(ad.h, feat_idx),
        "geodesic_accel": _at(ad.geodesic_accel, feat_idx),
        "gauge_force":    _at(ad.gauge_force, feat_idx),
        "friction":       _at(ad.friction, feat_idx),
        "T_info":         _at(ad.T_info, feat_idx),
        "tri":            _at(ad.tri, feat_idx),
        "lyapunov":       _at(ad.lya, feat_idx),
        "hurst":          _at(ad.hurst, feat_idx) if ad.hurst is not None else float('nan'),
        "ema_accel":      _at(ad.ema_accel, feat_idx),
        "atr14":          _at(ad.atr14, feat_idx),
        "higher_tf_trend":_at(ad.higher_tf_trend, feat_idx),
    }


_TRADE_CSV_LOCK = threading.Lock()

def _trade_to_flat_row(t: "Trade") -> Dict:
    row = {
        "symbol": t.symbol, "action": t.action,
        "entry_time": t.entry_time, "exit_time": t.exit_time,
        "entry_price": t.entry_price, "exit_price": t.exit_price,
        "pos_size": t.pos_size, "gross_pnl": t.gross_pnl, "fee": t.fee,
        "net_pnl": t.net_pnl, "capital_after": t.capital_after,
        "log_return": t.log_return, "exit_reason": t.exit_reason,
        "score": t.score, "lam": t.lam, "liq_warn": t.liq_warn,
        "slippage_paid": t.slippage_paid, "entry_optimized": t.entry_optimized,
        "tri_at_entry": t.tri_at_entry, "dynamic_risk_used": t.dynamic_risk_used,
        "T_info_at_entry": t.T_info_at_entry,
    }
    for k, v in (t.indicators or {}).items():
        row[f"ind_{k}"] = v
    return row

def export_trades_csv(trades: List["Trade"], path: str):
    """يكتب/يستبدل ملف CSV كاملاً بكل الصفقات (يُستخدم في نهاية الباك-تيست)."""
    if not trades:
        log.info("  ⤷ لا توجد صفقات لتصديرها إلى CSV.")
        return
    try:
        rows = [_trade_to_flat_row(t) for t in trades]
        df = pd.DataFrame(rows)
        with _TRADE_CSV_LOCK:
            df.to_csv(path, index=False, encoding="utf-8-sig")
        log.info(f"  ⤷ 💾 صُدِّرت {len(trades):,} صفقة إلى {path}")
    except Exception as e:
        log.error(f"⚠️ فشل تصدير الصفقات إلى CSV ({path}): {e}")

def append_trade_csv_row(trade: "Trade", path: str):
    """
    يُلحق صفقة واحدة بملف CSV (يُستخدم في live/testnet فور إغلاق كل صفقة).
    يكتب رأس الأعمدة تلقائياً إن كان الملف غير موجود بعد.
    """
    try:
        row = _trade_to_flat_row(trade)
        df_row = pd.DataFrame([row])
        with _TRADE_CSV_LOCK:
            write_header = not os.path.exists(path)
            df_row.to_csv(path, mode="a", index=False, header=write_header, encoding="utf-8-sig")
        log.info(f"  ⤷ 💾 أُلحقت صفقة {trade.symbol} بـ {path}")
    except Exception as e:
        log.error(f"⚠️ فشل إلحاق الصفقة بملف CSV ({path}): {e}")


def generate_trade_chart_html(trade: "Trade", ad: Optional["AssetData"], out_path: str,
                               context_bars: int = 60):
    """
    يُنشئ رسماً تفاعلياً (Plotly) لصفقة واحدة: مسار السعر حول فترة الصفقة مع
    علامتي الدخول/الخروج وخطي SL/TP، بالإضافة لصفّ فرعي لأهم المؤشرات
    النظرية. يُحفظ كملف HTML مستقل قابل للفتح مباشرة بأي متصفح.

    لا يعتمد على بيانات OHLC كاملة (لا يوجد سعر افتتاح مخزَّن في AssetData) —
    يستخدم مسار الإغلاق (close) كخط بدل الشموع اليابانية، وهو كافٍ لعرض
    السياق والمؤشرات دون المخاطرة بافتراض بيانات غير متوفرة فعلياً.
    """
    if not PLOTLY_AVAILABLE:
        return False
    if ad is None:
        return False
    try:
        # تحديد نافذة عرض حول الصفقة عبر الزمن (وليس الفهرس) لضمان صحتها
        # حتى لو اختلفت فهرسة feat/close.
        ts = pd.DatetimeIndex(ad.timestamps)
        entry_time = pd.Timestamp(trade.entry_time)
        exit_time = pd.Timestamp(trade.exit_time) if trade.exit_time is not None else entry_time
        try:
            i0 = int(ts.searchsorted(entry_time))
            i1 = int(ts.searchsorted(exit_time))
        except Exception:
            i0, i1 = 0, len(ts) - 1
        lo = max(0, min(i0, i1) - context_bars)
        hi = min(len(ad.closes), max(i0, i1) + context_bars)
        if hi - lo < 3:
            lo, hi = 0, len(ad.closes)

        x = ts[lo:hi]
        close_seg = ad.closes[lo:hi]
        score_seg = ad.score[lo:hi] if len(ad.score) >= hi else None

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                             vertical_spacing=0.06,
                             subplot_titles=(f"{trade.symbol} — {trade.action} | {trade.exit_reason}",
                                             "score"))

        # [جديد] شموع يابانية كاملة إن توفّر سعر الافتتاح (opens) على الأصل،
        # مع تراجع آمن لخط الإغلاق فقط إن غاب لأي سبب (بيانات قديمة/جزئية).
        if getattr(ad, "opens", None) is not None and len(ad.opens) >= hi:
            fig.add_trace(go.Candlestick(
                x=x, open=ad.opens[lo:hi], high=ad.highs[lo:hi],
                low=ad.lows[lo:hi], close=close_seg,
                name="OHLC", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
            ), row=1, col=1)
        else:
            fig.add_trace(go.Scatter(x=x, y=close_seg, mode="lines", name="السعر (إغلاق)",
                                      line=dict(color="#42a5f5", width=1.5)), row=1, col=1)

        fig.add_trace(go.Scatter(x=[entry_time], y=[trade.entry_price], mode="markers",
                                  name="دخول", marker=dict(color="#26a69a", size=12, symbol="triangle-up"),
                                  hovertext=[f"دخول {trade.action} @ {trade.entry_price:.6f}"]),
                       row=1, col=1)
        fig.add_trace(go.Scatter(x=[exit_time], y=[trade.exit_price], mode="markers",
                                  name="خروج", marker=dict(color="#ef5350", size=12, symbol="triangle-down"),
                                  hovertext=[f"خروج ({trade.exit_reason}) @ {trade.exit_price:.6f} | "
                                             f"صافي={trade.net_pnl:.4f}"]),
                       row=1, col=1)

        for label, val, color in [("SL", trade.indicators.get("sl_line"), "#ef5350"),
                                   ("TP", trade.indicators.get("tp_line"), "#66bb6a")]:
            if val is not None and not pd.isna(val):
                fig.add_hline(y=val, line_dash="dot", line_color=color,
                              annotation_text=label, row=1, col=1)

        if score_seg is not None:
            fig.add_trace(go.Scatter(x=x, y=score_seg, mode="lines", name="score",
                                      line=dict(color="#ffa726", width=1.2)), row=2, col=1)
            fig.add_hline(y=CFG.MIN_SCORE, line_dash="dash", line_color="#888",
                          annotation_text="MIN_SCORE", row=2, col=1)

        indicators_txt = "<br>".join(
            f"{k} = {v:.6g}" for k, v in (trade.indicators or {}).items()
            if k not in ("sl_line", "tp_line") and v is not None and not (isinstance(v, float) and np.isnan(v))
        )
        fig.add_annotation(xref="paper", yref="paper", x=1.01, y=1.0, showarrow=False,
                            align="left", font=dict(size=10), text=indicators_txt,
                            bordercolor="#888", borderwidth=1, bgcolor="rgba(255,255,255,0.85)")

        fig.update_layout(height=650, width=1100, margin=dict(r=260),
                           title=f"صفقة {trade.symbol} | صافي={trade.net_pnl:.4f} | "
                                 f"{entry_time} → {exit_time}",
                           template="plotly_white", hovermode="x unified",
                           xaxis_rangeslider_visible=False)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        fig.write_html(out_path, include_plotlyjs="cdn")
        return True
    except Exception as e:
        log.warning(f"⚠️ تعذّر إنشاء رسم Plotly للصفقة {trade.symbol}: {e}")
        return False


def generate_trades_summary_html(trades: List["Trade"], out_path: str):
    """رسم إجمالي واحد: منحنى رأس المال + توزيع الصفقات، لمحة سريعة قبل الدخول لكل صفقة على حدة."""
    if not PLOTLY_AVAILABLE or not trades:
        return False
    try:
        times = [t.exit_time or t.entry_time for t in trades]
        cap = [t.capital_after for t in trades]
        colors = ["#26a69a" if t.net_pnl >= 0 else "#ef5350" for t in trades]
        hover = [f"{t.symbol} | {t.action} | صافي={t.net_pnl:.4f} | {t.exit_reason}" for t in trades]

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4],
                             vertical_spacing=0.08,
                             subplot_titles=("منحنى رأس المال", "صافي ربح/خسارة كل صفقة"))
        fig.add_trace(go.Scatter(x=times, y=cap, mode="lines+markers", name="رأس المال",
                                  line=dict(color="#42a5f5")), row=1, col=1)
        fig.add_trace(go.Bar(x=times, y=[t.net_pnl for t in trades], marker_color=colors,
                              name="صافي الصفقة", hovertext=hover), row=2, col=1)
        fig.update_layout(height=750, width=1200, template="plotly_white",
                           title=f"ملخص {len(trades):,} صفقة")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        fig.write_html(out_path, include_plotlyjs="cdn")
        return True
    except Exception as e:
        log.warning(f"⚠️ تعذّر إنشاء رسم الملخص الإجمالي: {e}")
        return False


def generate_all_trade_charts(trades: List["Trade"], assets: Dict[str, "AssetData"], out_dir: str,
                               context_bars: int = 60):
    if not PLOTLY_AVAILABLE:
        log.warning("⚠️ مكتبة plotly غير مثبتة — تخطي رسوم HTML للصفقات "
                    "(نفّذ: pip install plotly). تصدير CSV غير متأثر.")
        return
    os.makedirs(out_dir, exist_ok=True)
    ok = 0
    for idx, t in enumerate(trades):
        ad = assets.get(t.symbol)
        fname = f"{idx:04d}_{t.symbol.replace('/','-').replace(':','-')}_{t.exit_reason.replace(' ','_')}.html"
        if generate_trade_chart_html(t, ad, os.path.join(out_dir, fname), context_bars):
            ok += 1
    generate_trades_summary_html(trades, os.path.join(out_dir, "_summary.html"))
    log.info(f"  ⤷ 🌐 وُلِّد {ok}/{len(trades):,} رسم HTML تفاعلي في {out_dir}/ (+ _summary.html)")


# ════════════════════════════════════════════════════════════════
# § النظرية الموحدة: حقل المقياس، الاحتكاك، وفجوة التوازن
# ════════════════════════════════════════════════════════════════

def compute_gauge_force_and_gap(sym_q: np.ndarray, dyn_k: int, W: int = CFG.W,
                                 P_star: np.ndarray = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    [تصحيح نظري] الورقة (الفرض الرابع: الإرغوديكية + نظرية 6.5/6.20) تُعرّف P*
    كتوزيع التوازن الفعلي لنظام MaxEnt (توزيع جينز)، وهو غير منتظم في الحالة
    العامة — يتحدد فقط بالقيود C. الإصدار السابق افترض P* = 1/k (توزيع منتظم
    على كل العنقودات)، وهو خطأ نظري وعملي: عنقودات K-means نادراً ما تكون
    متساوية الكثافة، فكانت delta_gap تقيس الانحراف عن توزيع وهمي لا عن توازن
    حقيقي، مما يُفسد فلترة MAX_EQUILIBRIUM_GAP. بالاعتماد على الإرغوديكية نفسها
    (متوسط الزمن = متوسط الفضاء)، نقدّر P* تجريبياً من التوزيع طويل المدى
    لعينة التدريب ونمرره من process_asset.
    """
    n = len(sym_q)
    gauge_force = np.zeros(n, dtype=np.float64)
    delta_gap = np.zeros(n, dtype=np.float64)
    if P_star is None:
        P_star = np.full(dyn_k, 1.0 / dyn_k)
    else:
        P_star = np.asarray(P_star, dtype=np.float64)
        if P_star.shape[0] != dyn_k or not np.isclose(P_star.sum(), 1.0, atol=1e-6):
            P_star = np.full(dyn_k, 1.0 / dyn_k)

    for i in range(W, n):
        window = sym_q[i-W:i]

        counts = np.bincount(window, minlength=dyn_k)
        P_n = counts / W
        delta_gap[i] = np.max(np.abs(P_n - P_star))

        T_mat = np.zeros((dyn_k, dyn_k), dtype=np.float64)
        for j in range(1, len(window)):
            T_mat[window[j-1], window[j]] += 1

        sum_T = np.sum(T_mat)
        if sum_T > 0:
            T_mat /= sum_T

        A = T_mat - T_mat.T
        gauge_force[i] = np.linalg.norm(A, ord='fro')

    return gauge_force, delta_gap


def compute_entropy_friction(H: np.ndarray, dyn_k: int, gamma0_calibrated: float = None) -> np.ndarray:
    """
    [v7 - تحسين ٣] القاعدة γ₀ لم تعد ثابتاً اعتباطياً بل تُقدَّر من زمن الترابط
    الذاتي الفعلي لعوائد التدريب عبر calibrate_friction_from_autocorrelation
    (نظرية Onsager). النافذة الأسية على نسبة الانتروبيا تبقى كمُعدِّل ديناميكي
    محلي (الاحتكاك يرتفع عندما تنخفض انتروبيا الحالة، أي عند اقتراب النظام من
    نظام حتمي محلياً) لكن حول القاعدة المُقاسة بدل γ₀=0.01 المفروضة يدوياً.
    """
    gamma0 = gamma0_calibrated if gamma0_calibrated is not None else CFG.GAMMA_0
    H_max = np.log2(dyn_k) + 1e-12
    S_ratio = np.clip(H / H_max, 0.0, 1.0)
    gamma = gamma0 + CFG.KAPPA * gamma0 * np.exp(CFG.XI * (1.0 - S_ratio))
    return np.maximum(gamma, CFG.FRICTION_MIN)

# ════════════════════════════════════════════════════════════════
# § 12  معالجة أصل واحد (Pipeline) + تسارع EMA (التعديل ⑤)
# ════════════════════════════════════════════════════════════════

def process_asset(symbol, df, km_ext=None, current_capital=None, df_high=None):
    closes = df['Close'].values.astype(np.float64)
    highs  = df['High'].values.astype(np.float64)
    lows   = df['Low'].values.astype(np.float64)
    vols   = df['Volume'].values.astype(np.float64)
    # [جديد] سعر الافتتاح كان يُجلَب أصلاً في خط أنابيب البيانات (fetch_ohlcv
    # يُعيد OHLCV كاملة) لكنه لم يكن يُخزَّن على AssetData إطلاقاً — كل ما
    # وصل لاحقاً هو Close/High/Low فقط. أضفناه هنا لتمكين شموع يابانية كاملة
    # في رسوم الصفقات (Plotly) دون أي تعديل على مصدر البيانات نفسه. لا وجود
    # لعمود 'Open' لبعض مسارات df القديمة/الاختبارية نادراً، فنستعيض عنه
    # بأمان بسعر إغلاق الشمعة السابقة (تقريب معقول لا يكسر أي شيء).
    if 'Open' in df.columns:
        opens = df['Open'].values.astype(np.float64)
    else:
        opens = np.concatenate(([closes[0]], closes[:-1]))
    ts     = df.index; N = CFG.N
    if len(closes) < N+CFG.W+100: return None

    feat_start = N
    X = compute_features(closes, vols, N)
    n = len(X)
    if n < CFG.W+50: return None

    train_end = int(n*CFG.TRAIN_FRACTION)

    adv_raw = pd.Series(vols*closes).rolling(24, min_periods=1).mean().values
    cap_now = current_capital if current_capital else CFG.INITIAL_CAPITAL
    dyn_k   = compute_dynamic_k(cap_now, adv_raw[:train_end+feat_start])

    # [v7 - تحسين ١] HMM بدل KMeans افتراضياً (CFG.STATE_MODEL). التوافق الرجعي
    # محفوظ: fit_state_model يرجع إلى KMeans تلقائياً عند الفشل أو إن طُلب صراحة.
    km = km_ext if km_ext else fit_state_model(X[:train_end], k=dyn_k)
    sym_q = np.clip(assign_states(X, km), 0, dyn_k - 1).astype(np.int32)

    H   = entropy_series(sym_q, k=dyn_k)
    dH  = np.diff(H,  prepend=H[0])
    d2H = np.diff(dH, prepend=dH[0])

    lr_full = np.diff(np.log(np.maximum(closes,1e-12)))
    E_therm = np.zeros(n)
    for i in range(n):
        ci = feat_start+i
        if ci >= N:
            w = lr_full[ci-N:ci]
            E_therm[i] = float(np.std(w,ddof=1)) if len(w)>=2 else 0.

    F  = E_therm - H
    dF = np.diff(F, prepend=F[0])

    T_info_raw = np.abs(dF / (np.abs(dH) + 1e-9))
    T_abs = E_therm * 400.0
    T_info = T_info_raw + T_abs
    T_info = np.clip(T_info, 0.5, 20.0)

    # [تصحيح نظري] P* التجريبي = التوزيع طويل المدى لحالات K-means خلال فترة
    # التدريب فقط (لا تسريب بيانات من فترة الاختبار)، بدل الافتراض الخاطئ للتوزيع
    # المنتظم 1/k. هذا يطابق مسلّمة الإرغوديكية في الورقة (Postulate 4): متوسط
    # الزمن على المدى الطويل ⟶ توزيع التوازن الحقيقي P*.
    train_counts = np.bincount(sym_q[:max(train_end, 1)], minlength=dyn_k).astype(np.float64)
    P_star_emp = train_counts / max(train_counts.sum(), 1.0)
    gauge_force, delta_gap = compute_gauge_force_and_gap(sym_q, dyn_k, CFG.W, P_star=P_star_emp)

    # [v7 - تحسين ٣] معايرة القاعدة γ₀ من الارتباط الذاتي لعوائد فترة التدريب فقط
    train_lr = lr_full[:min(feat_start + train_end, len(lr_full))]
    gamma0_cal = calibrate_friction_from_autocorrelation(train_lr[-2000:]) if len(train_lr) > 50 else CFG.GAMMA_0
    friction = compute_entropy_friction(H, dyn_k, gamma0_calibrated=gamma0_cal)

    # [v7 - تحسين ١٠] أس هيرست المتحرك لكشف كسر الإرغوديكية
    hurst = compute_hurst_series(closes[feat_start:feat_start + n] if feat_start + n <= len(closes) else closes[feat_start:], window=CFG.HURST_WINDOW)
    if len(hurst) < n:
        hurst = np.pad(hurst, (0, n - len(hurst)), constant_values=0.5)

    geodesic_accel = np.zeros(n, dtype=np.float64)
    for i in range(n):
        grad_F = -dF[i]
        lorentz = CFG.LORENTZ_CHARGE_Q * gauge_force[i] * dH[i]
        fric_force = friction[i] * dH[i]
        geodesic_accel[i] = grad_F + lorentz - fric_force

    C, V = compute_geometry(X)
    V_tr = V[:train_end]; vv = V_tr[V_tr>CFG.EPSILON]
    V_q20 = np.percentile(vv,20) if len(vv)>0 else np.percentile(V_tr,20)
    V_q20a = np.full(n, V_q20)

    h = np.ones(n, dtype=np.int32)
    h[dH >  CFG.DH_HMM_UPPER] = 0
    h[dH <  CFG.DH_HMM_LOWER] = 2

    sc = np.zeros(n)
    sc += np.abs(geodesic_accel) * 10.0
    sc += CFG.W_CURV    * (C < -CFG.CURV_THRESHOLD).astype(float)
    sc += CFG.W_VOL     * (V < V_q20a).astype(float)
    sc += CFG.W_ENTROPY * ((dH < CFG.DH_ENTROPY_THRESHOLD) & (d2H < 0)).astype(float)
    # [إصلاح منطق ميت] الشرط الأصلي `(h==0)&(dH<-DH_ENTROPY_THRESHOLD)` لا يمكن
    # تحققه إطلاقاً: h==0 مُعرَّفة أعلاه بأنها dH>DH_HMM_UPPER (موجبة)، وهذا
    # يتناقض جبرياً مع اشتراط dH سالبة في نفس السطر — فرع كود ميت 100%.
    # الأقرب لمنطق الملف (تأكيد مبكر لانحدار الانتروبيا قبل أن يبلغ حالة h==2
    # الرسمية) هو مطابقة الحالة المحايدة h==1 مع دخول dH تحت العتبة سلباً.
    sc += CFG.W_HMM     * ((h==2)|((h==1)&(dH<-CFG.DH_ENTROPY_THRESHOLD))).astype(float)
    sc += CFG.W_FREE_E  * (dF < CFG.DF_FREE_E_THRESHOLD).astype(float)

    ema200_series = pd.Series(closes).ewm(span=CFG.EMA_SPAN, adjust=False).mean().values
    ema_diff  = np.diff(ema200_series, prepend=ema200_series[0])
    ema_accel = np.diff(ema_diff,      prepend=ema_diff[0])

    tr  = np.maximum(highs[1:]-lows[1:],
          np.maximum(np.abs(highs[1:]-closes[:-1]), np.abs(lows[1:]-closes[:-1])))
    tr  = np.concatenate([[tr[0]],tr])
    atr = pd.Series(tr).rolling(CFG.ATR_PERIOD, min_periods=1).mean().values
    adv = pd.Series(vols*closes).rolling(24, min_periods=1).mean().values

    higher_tf_trend = np.zeros(len(closes), dtype=np.int8)
    if df_high is not None:
        ema50_high = pd.Series(df_high['Close']).ewm(span=CFG.HIGHER_TF_EMA_SPAN, adjust=False).mean().values
        high_closes = df_high['Close'].values
        high_ts = df_high.index.asi8
        ts_i = ts.asi8
        pos = np.searchsorted(high_ts, ts_i, side='right') - 1
        pos = np.clip(pos, 0, len(high_closes) - 1)
        last_close = high_closes[pos]
        last_ema = ema50_high[pos]
        higher_tf_trend = np.where(last_close > last_ema, 1,
                          np.where(last_close < last_ema, -1, 0)).astype(np.int8)

    ed  = compute_energy_dynamics(closes, lr_full, X, feat_start)
    KE  = ed['KE']; dKE = ed['dKE']
    PE  = compute_PE(X, km, H)
    ME  = KE+PE
    tri = compute_tri(dH, d2H, dF, dKE, ed['lya'])

    train_log_returns = lr_full[:min(feat_start + train_end, len(lr_full))]

    ad = AssetData(
        symbol=symbol, closes=closes, highs=highs, lows=lows,
        volumes=vols, timestamps=ts, X=X, sym_q=sym_q,
        H=H, dH=dH, d2H=d2H, E_therm=E_therm, F=F, dF=dF,
        C=C, V=V, h=h, score=sc,
        ema200=ema200_series, ema_accel=ema_accel,
        atr14=atr, adv_usd=adv,
        KE=KE, PE=PE, ME=ME, dKE=dKE, lya=ed['lya'], tri=tri,
        T_info=T_info,
        train_end=train_end, feat_start=feat_start, km=km,
        dynamic_k=dyn_k,
        gauge_force=gauge_force, friction=friction,
        delta_gap=delta_gap, geodesic_accel=geodesic_accel,
        higher_tf_trend=higher_tf_trend,
        hurst=hurst, clf=None, train_log_returns=train_log_returns,
        friction_gamma0=gamma0_cal,
        opens=opens,
    )

    # [v7 - تحسين ٤] تدريب المصنّف الاحتمالي المعاير على فترة التدريب فقط
    # (بلا تسريب بيانات: المسح الأمامي في fit_from_asset محدود بـ ad.train_end)
    if CFG.USE_CALIBRATED_CLASSIFIER:
        try:
            ad.clf = CalibratedEntryClassifier().fit_from_asset(ad, CFG)
        except Exception as e:
            log.warning(f"⚠️ تعذّر تدريب المصنّف المعاير لـ {symbol}: {e}")
            ad.clf = None

    return ad


# ════════════════════════════════════════════════════════════════
# § 13  بناء الإشارات (التعديلات ①④⑤)
# ════════════════════════════════════════════════════════════════
def compute_geodesic_target(price, geo_accel, friction, delta_gap, cfg):
    accel = abs(float(geo_accel))
    fric = float(friction) + 1e-6
    kelly_scale = getattr(cfg, 'KELLY_SCALE', 0.50)
    move_ratio = (accel / fric) * kelly_scale
    return float(price * move_ratio)


def compute_geodesic_kelly(ad, fi, cfg, win_prob: float = None):
    """
    [v7 - تحسين ٧] كيلي كسري حقيقي بدل السيغمويد الاعتباطي: نستخدم احتمال
    الفوز (من المصنّف المعاير إن توفر، وإلا تقدير تقريبي من نسبة القوة/الاحتكاك)
    ونسبة العائد/المخاطرة الثابتة (TP_R_MULT) في صيغة كيلي الثنائية، ثم نطبّق
    قيد CVaR على توزيع عوائد الأصل التاريخية الفعلية (وليس افتراضاً نظرياً).
    """
    if win_prob is None:
        accel = abs(float(ad.geodesic_accel[fi]))
        fric = float(ad.friction[fi]) + 1e-6
        T_info = float(ad.T_info[fi])
        force_ratio = accel / fric
        thermal_damp = np.exp(-0.01 / (T_info + 1e-6))
        win_prob = 1.0 / (1.0 + np.exp(-((force_ratio * thermal_damp) - 2.0)))

    trade_returns = getattr(ad, 'train_log_returns', None)
    if trade_returns is None:
        trade_returns = np.diff(np.log(np.maximum(ad.closes[:max(ad.train_end, 30)], 1e-12)))

    return fractional_kelly_cvar(win_prob, cfg.GEO_TP_R_MULT, trade_returns, cfg)


def compute_geodesic_stop(entry_price, ad, fi, cfg):
    """
    [v7 - تحسين ٦] تقريب عملي لمسافة جيوديسية على متري معلوماتي: بدل الصيغة
    الاعتباطية (0.012 × uncertainty)/(1+5×friction)، نستخدم معلومة فيشر
    التجريبية المحلية = محدد مصفوفة التغاير المحلية للميزات V[fi] (وهو ما
    تحسبه compute_geometry فعلاً كـ det(Cov)) كمقياس "لعدم اليقين المعلوماتي"،
    مُطبَّعاً بمتوسط V على كامل السلسلة، ثم نحوّله إلى مسافة سعرية عبر ATR
    المحلي (لأن الميزات ليست بوحدة السعر مباشرة). النتيجة تتقلص مع ارتفاع
    الاحتكاك (نظام لزج/يصعب فيه الانزلاق بعيداً) وتتسع مع ارتفاع اللايقين
    المحلي — وهي نفس الروح الفيزيائية لمسافة فيشر-راو لكن بتقدير تجريبي مباشر
    بدل افتراض عائلة أسية صريحة (التي تتطلب معايرة λ لكل صفقة، غير عملية هنا).
    """
    V_mean = float(np.mean(ad.V[:max(ad.train_end, 1)])) + CFG.EPSILON
    info_uncertainty = np.clip(ad.V[fi] / V_mean, 0.3, 4.0) ** 0.5   # جذر det(Cov) ~ "نصف قطر" معلوماتي
    friction = float(ad.friction[fi]) + 1e-6

    ci = min(ad.feat_start + fi, len(ad.atr14) - 1)
    atr_frac = float(ad.atr14[ci]) / max(entry_price, 1e-9)
    atr_frac = atr_frac if atr_frac > 0 else 0.01

    sl_pct = cfg.GEO_STOP_ALPHA * atr_frac * info_uncertainty / (1.0 + friction * 5.0)
    sl_dist = entry_price * sl_pct

    return float(np.clip(sl_dist, cfg.GEO_STOP_MIN_PCT * entry_price, cfg.GEO_STOP_MAX_PCT * entry_price))

def compute_dynamic_leverage(capital, cfg):
    if cfg.SINGULARITY_MODE:
        return cfg.SING_LEVERAGE

    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    return int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))

def detect_singularity_direction(ad, fi, ci, p):
    thr = CFG.SING_RESONANCE_ACCEL

    accel_1m = ad.geodesic_accel[fi]
    accel_5m = np.mean(ad.geodesic_accel[fi-4:fi+1])
    accel_15m = np.mean(ad.geodesic_accel[fi-14:fi+1])

    if not (abs(accel_1m) > thr and abs(accel_5m) > thr and abs(accel_15m) > thr):
        return None

    if accel_1m > 0 and accel_5m > 0 and accel_15m > 0:
        raw_dir = "BUY"
    elif accel_1m < 0 and accel_5m < 0 and accel_15m < 0:
        raw_dir = "SELL"
    else:
        return None

    if ci < 3:
        return None
    momentum = p - ad.closes[ci - 3]
    if raw_dir == "BUY" and momentum <= 0:
        return None
    if raw_dir == "SELL" and momentum >= 0:
        return None

    ema200 = ad.ema200[ci] if ci < len(ad.ema200) else p
    if raw_dir == "BUY" and p < ema200:
        return None
    if raw_dir == "SELL" and p > ema200:
        return None

    if ci < len(ad.higher_tf_trend):
        htf = int(ad.higher_tf_trend[ci])
        if raw_dir == "BUY" and htf < 0:
            return None
        if raw_dir == "SELL" and htf > 0:
            return None

    if fi < len(ad.delta_gap):
        gap = float(ad.delta_gap[fi])
        if gap > CFG.MAX_EQUILIBRIUM_GAP:
            return None

    window = 100
    start = max(0, ci - window)
    recent = ad.closes[start:ci+1]
    if len(recent) < 30:
        return None
    pct = float(np.sum(recent <= p) / len(recent))
    if raw_dir == "BUY" and pct > 0.90:
        return None
    if raw_dir == "SELL" and pct < 0.10:
        return None

    return raw_dir

def build_signals(assets, mode="backtest"):
    sigs = []
    for sym, ad in assets.items():
        n = len(ad.score)
        for fi in range(ad.train_end+1, n):
            ci = ad.feat_start + fi

            if mode == "backtest":
                if ci >= len(ad.closes) - 1: continue
            else:
                if ci < len(ad.closes) - 1: continue

            p = ad.closes[ci]
            if p <= 0: continue

            geo_accel = float(ad.geodesic_accel[fi])
            fric_val = float(ad.friction[fi]) + 1e-6
            T_info = float(ad.T_info[fi])

            if CFG.SINGULARITY_MODE:
                if fi < 15: continue

                action = detect_singularity_direction(ad, fi, ci, p)
                if not action:
                    continue

                friction_drag = p * 0.0005
                tunnel_entry_p = p - friction_drag if action == "BUY" else p + friction_drag

                sl_dist = tunnel_entry_p * CFG.SING_STOP_LOSS_PCT
                tp_dist = tunnel_entry_p * CFG.SING_TAKE_PROFIT_PCT

                sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
                tp1 = tunnel_entry_p + tp_dist if action == "BUY" else tunnel_entry_p - tp_dist

                dynamic_risk = CFG.SING_RISK_FRACTION

                sigs.append(Signal(
                    timestamp=ad.timestamps[ci], symbol=sym, price=tunnel_entry_p,
                    score=99.0, action=action, sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                    atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                    adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                    dynamic_risk=dynamic_risk, T_info_val=T_info,
                    dyn_sl_factor=sl_dist / tunnel_entry_p
                ))

            else:
                # [v7 - تحسين ١٠] فلتر عدم-الإرغودية: تعطيل الدخول عندما ينحرف
                # أس هيرست كثيراً عن 0.5 (كسر لافتراض ثبات التوزيع/الإرغوديكية)
                if CFG.HURST_HALT_ENABLED and fi < len(ad.hurst):
                    hv = float(ad.hurst[fi])
                    if hv < CFG.HURST_LOW or hv > CFG.HURST_HIGH:
                        continue

                # [v7 - تحسين ٤] احتمال تفعيل معاير حقيقي (Platt-scaled) إن توفر
                # مصنّف مدرَّب لهذا الأصل؛ وإلا رجوع إلى الصيغة اللوجستية الأصلية
                # (موسومة صراحة بأنها تقريب غير معاير عندما تُستخدم).
                calibrated_p = ad.clf.predict_proba_one(ad, fi) if (CFG.USE_CALIBRATED_CLASSIFIER and ad.clf is not None) else None
                if calibrated_p is not None:
                    P_activation = calibrated_p
                    if P_activation < CFG.CLASSIFIER_PROB_THRESHOLD: continue
                else:
                    force_mag = abs(geo_accel) + 1e-9
                    P_activation = np.exp(-fric_val / (force_mag * T_info))  # [تقريب غير معاير — راجع الملاحظة أعلاه]
                    if P_activation < 0.35: continue

                micro_momentum = p - ad.closes[ci - 3]
                if micro_momentum == 0: continue
                action = "BUY" if micro_momentum > 0 else "SELL"

                if ad.score[fi] < CFG.MIN_SCORE: continue

                if action == "BUY" and int(ad.higher_tf_trend[ci]) < 0:
                    continue
                if action == "SELL" and int(ad.higher_tf_trend[ci]) > 0:
                    continue

                friction_drag = fric_val * p * 0.1
                tunnel_entry_p = p - friction_drag if action == "BUY" else p + friction_drag

                sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
                sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
                tp1 = tunnel_entry_p + (sl_dist * CFG.GEO_TP_R_MULT) if action == "BUY" else tunnel_entry_p - (sl_dist * CFG.GEO_TP_R_MULT)

                if (sl_dist * CFG.GEO_TP_R_MULT) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue

                # [v7 - تحسين ٧] كيلي كسري بقيد CVaR، باحتمال الفوز المعاير إن توفر
                dynamic_risk = compute_geodesic_kelly(ad, fi, CFG, win_prob=calibrated_p)

                sigs.append(Signal(
                    timestamp=ad.timestamps[ci], symbol=sym, price=tunnel_entry_p,
                    score=float(ad.score[fi]), action=action, sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                    atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                    adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                    dynamic_risk=dynamic_risk, T_info_val=T_info,
                    dyn_sl_factor=sl_dist / tunnel_entry_p
                ))

    sigs.sort(key=lambda s: (s.timestamp, -s.score))
    return sigs


def deduplicate_signals(sigs):
    groups = defaultdict(list)
    for s in sigs:
        key = (s.symbol, s.timestamp.floor('1h'))
        groups[key].append(s)
    result = []
    for _, grp in groups.items():
        result.append(max(grp, key=lambda s:(s.score, s.lam)))
    result.sort(key=lambda s: s.timestamp)
    return result

def compute_correlation_at_idx(ad1, ad2, idx1, idx2, window=200):
    if idx1 < window or idx2 < window:
        return 0.0

    start1 = max(0, idx1 - window)
    start2 = max(0, idx2 - window)
    c1 = ad1.closes[start1:idx1]
    c2 = ad2.closes[start2:idx2]

    if len(c1) < 20 or len(c2) < 20:
        return 0.0

    r1 = np.diff(np.log(np.maximum(c1, 1e-12)))
    r2 = np.diff(np.log(np.maximum(c2, 1e-12)))

    m = min(len(r1), len(r2))
    if m < 10:
        return 0.0

    corr = np.corrcoef(r1[-m:], r2[-m:])[0, 1]
    return float(corr) if not np.isnan(corr) else 0.0

# ════════════════════════════════════════════════════════════════
# § 14  مصفوفة الارتباط
# ════════════════════════════════════════════════════════════════

def precompute_correlations(assets) -> Dict[Tuple[str,str], float]:
    """
    [v7 - تحسين ٩] بدل الارتباط العيني الخام (غير مستقر لعيّنات قصيرة)، نبني
    مصفوفة عوائد مشتركة (محاذاة بآخر N شمعة لكل الأصول) ونطبّق انكماش
    Ledoit-Wolf، مما يقلل تأثير ضوضاء العيّنة على قرارات فتح مراكز مترابطة.
    الرجوع للطريقة الزوجية القديمة يحدث تلقائياً إن كان عدد الأصول < 3 أو
    العينة قصيرة جداً بعد المحاذاة.
    """
    syms = list(assets.keys())
    if len(syms) < 3:
        return _precompute_correlations_pairwise(assets)

    window = 500
    returns_cols = []
    valid_syms = []
    for s in syms:
        c = assets[s].closes[-(window + 1):]
        if len(c) < 30:
            continue
        r = np.diff(np.log(np.maximum(c, 1e-12)))
        returns_cols.append(r[-window:] if len(r) >= window else r)
        valid_syms.append(s)

    if len(valid_syms) < 3:
        return _precompute_correlations_pairwise(assets)

    min_len = min(len(r) for r in returns_cols)
    if min_len < 20:
        return _precompute_correlations_pairwise(assets)

    R = np.column_stack([r[-min_len:] for r in returns_cols])
    try:
        corr_mat = ledoit_wolf_correlation(R)
    except Exception as e:
        log.warning(f"⚠️ فشل انكماش Ledoit-Wolf ({e}) — رجوع إلى الارتباط الزوجي الخام")
        return _precompute_correlations_pairwise(assets)

    cm = {}
    for i, s1 in enumerate(valid_syms):
        for j, s2 in enumerate(valid_syms):
            if i >= j: continue
            corr = float(np.clip(corr_mat[i, j], -1.0, 1.0))
            cm[(s1, s2)] = corr; cm[(s2, s1)] = corr
    # أزواج غير مشمولة (عيّنة قصيرة) ترجع للطريقة الزوجية كاحتياط
    for s1 in syms:
        for s2 in syms:
            if s1 != s2 and (s1, s2) not in cm:
                pw = _precompute_correlations_pairwise({s1: assets[s1], s2: assets[s2]})
                cm[(s1, s2)] = pw.get((s1, s2), 0.5)
    return cm


def _precompute_correlations_pairwise(assets) -> Dict[Tuple[str,str], float]:
    """الطريقة الزوجية الأصلية — تُستخدم احتياطياً فقط الآن."""
    syms = list(assets.keys()); cm = {}
    for i,s1 in enumerate(syms):
        for j,s2 in enumerate(syms):
            if i >= j: continue
            c1 = assets[s1].closes[-500:]
            c2 = assets[s2].closes[-500:]
            N  = min(len(c1), len(c2))
            if N < 20: corr = 0.5
            else:
                r1 = np.diff(np.log(np.maximum(c1[-N:],1e-12)))
                r2 = np.diff(np.log(np.maximum(c2[-N:],1e-12)))
                m  = min(len(r1),len(r2))
                corr = float(np.corrcoef(r1[-m:],r2[-m:])[0,1]) if m>10 else 0.5
            cm[(s1,s2)] = corr; cm[(s2,s1)] = corr
    return cm


# ════════════════════════════════════════════════════════════════
# § 15  محاكاة المحفظة (التعديلات ①②)
# ════════════════════════════════════════════════════════════════

def _ts_to_ci(ad, ts):
    idx = int(np.searchsorted(ad.timestamps.asi8, ts.value, side='right') - 1)
    return max(0, min(idx, len(ad.closes)-1))


def _get_risk_multiplier(drawdown, cfg=None):
    """
    [إصلاح-تدقيق] كانت هذه الدالة تقرأ CFG العامة دائماً بدل أي cfg مُمرَّر،
    وهو ما كان يعمل بالصدفة فقط لأن run_backtest/LiveEngine يستخدمان نفس
    الكائن العام حالياً. أُضيف مُعامل cfg اختياري صراحةً حتى لا ينكسر هذا
    ضمنياً إذا استُخدمت الدالة مستقبلاً مع إعدادات مختلفة عن الافتراضية
    (مثال: اختبارات وحدة، أو تشغيل عدة محركات بإعدادات مختلفة في نفس العملية).
    """
    c = cfg if cfg is not None else CFG
    if drawdown >= c.DRAWDOWN_REDUCE_AT_70: return c.REDUCED_RISK_MULT_70
    if drawdown >= c.DRAWDOWN_REDUCE_AT_50: return c.REDUCED_RISK_MULT_50
    if drawdown >= c.DRAWDOWN_REDUCE_AT:    return c.REDUCED_RISK_MULT
    return 1.0


def _drawdown_halted(drawdown, cfg=None):
    """
    [إصلاح D-DD1 — عيب أمان جوهري مكتشف بالتدقيق]
    MAX_DRAWDOWN_HALT كان معرَّفاً في الإعدادات (§0) لكنه لم يُستخدم في أي مكان
    عبر كامل الملف (تم التحقق عبر بحث شامل: صفر استخدامات فعلية). هذا يعني أن
    "قاطع الدائرة" (circuit breaker) الذي يوحي به اسم المتغير لم يكن موجوداً
    فعلياً؛ خفض المخاطرة عبر REDUCED_RISK_MULT_70 يقلل الحجم عند انخفاض ٪70
    لكنه لا يوقف التداول أبداً مهما بلغ الانخفاض. نفّذ الدالة هنا فعلياً
    ونربطها في كل من الباك-تيست والتداول الحي أدناه.
    """
    c = cfg if cfg is not None else CFG
    return drawdown >= c.MAX_DRAWDOWN_HALT


def _advance(pos, ad, to_ci):
    sig = pos.signal
    trail_sl = pos.trail_sl
    start = pos.current_ci + 1
    end = min(to_ci, len(ad.closes)-1)

    for cidx in range(start, end+1):
        p = ad.closes[cidx]
        high = ad.highs[cidx]
        low = ad.lows[cidx]
        fi = cidx - ad.feat_start

        is_apex, apex_rsn = check_thermodynamic_apex(sig.action, pos.entry_px, p, ad, fi)
        if is_apex:
            next_cidx = cidx + 1
            if next_cidx < len(ad.closes):
                exec_price = ad.closes[next_cidx]
                pos.trail_sl = trail_sl; pos.current_ci = next_cidx
                return exec_price, apex_rsn, next_cidx
            else:
                pass

        if 0 < fi < len(ad.V) and cidx > 0:
            V_curr  = ad.V[fi]
            V_prev  = ad.V[fi-1] if fi > 0 else V_curr
            div_t   = (V_curr - V_prev) / (V_prev + 1e-12)
            dH_curr = ad.dH[fi] if fi < len(ad.dH) else 0.
            if div_t > CFG.TOPO_DIV_THRESHOLD and dH_curr > 0:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return p, f"Topo-Div({div_t:.3f})", cidx

        if cidx - pos.entry_ci > CFG.MAX_HOLD_BARS:
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, "MaxHold", cidx

        if sig.action == "BUY":
            if low <= pos.trail_sl:
                exit_price = pos.trail_sl
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return exit_price, "Emergency SL", cidx
            if high >= sig.tp1:
                exit_price = sig.tp1
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return exit_price, "Hard TP", cidx
        else:
            if high >= pos.trail_sl:
                exit_price = pos.trail_sl
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return exit_price, "Emergency SL", cidx
            if low <= sig.tp1:
                exit_price = sig.tp1
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return exit_price, "Hard TP", cidx

    pos.trail_sl = trail_sl; pos.current_ci = end
    return 0., "", -1


def simulate_portfolio(signals, assets, mode="backtest"):
    capital  = CFG.INITIAL_CAPITAL
    peak_cap = capital
    equity   = [capital]
    trades_out: List[Trade] = []
    open_pos: Dict[str, OpenPosition] = {}

    def _close(pos, ad, exit_px, exit_rsn, exit_ci):
        nonlocal capital, peak_cap
        sig         = pos.signal
        exit_act    = "SELL" if sig.action=="BUY" else "BUY"
        adv_here    = ad.adv_usd[min(exit_ci, len(ad.adv_usd)-1)]
        exit_eff    = apply_slippage(exit_px, pos.pos_size, adv_here, exit_act, mode)
        slip_x      = abs(exit_eff-exit_px)*pos.pos_size

        if sig.action=="BUY":
            gross = (exit_eff - pos.entry_px) * pos.pos_size
        else:
            gross = (pos.entry_px - exit_eff) * pos.pos_size

        fee  = pos.pos_size * (pos.entry_px + exit_eff) * CFG.MAKER_FEE

        hold_bars = exit_ci - pos.entry_ci
        funding_payments = max(0, hold_bars) // CFG.FUNDING_INTERVAL_BARS
        funding_cost = pos.pos_size * pos.entry_px * CFG.FUNDING_RATE_COST * funding_payments

        net  = gross - fee - slip_x - funding_cost
        cap0 = pos.entry_cap
        capital = max(capital+net, 0.)
        peak_cap= max(peak_cap, capital)
        equity.append(capital)

        lr = float(np.log((cap0+net)/cap0)) if cap0>0 else 0.
        lw = (pos.pos_size*pos.entry_px) > (adv_here*24*CFG.MAX_ADV_FRACTION)

        exit_time = ad.timestamps[exit_ci] if 0 <= exit_ci < len(ad.timestamps) else None
        indicators = build_indicator_snapshot(ad, sig.feat_idx)
        indicators["sl_line"] = pos.trail_sl
        indicators["tp_line"] = sig.tp1

        trades_out.append(Trade(
            symbol=sig.symbol, action=sig.action,
            entry_price=pos.entry_px, exit_price=exit_eff,
            pos_size=pos.pos_size, gross_pnl=gross, fee=fee+slip_x,
            net_pnl=net, capital_after=capital, log_return=lr,
            entry_time=sig.timestamp, exit_reason=exit_rsn,
            score=sig.score, lam=sig.lam, liq_warn=lw,
            slippage_paid=pos.slip_paid+slip_x,
            entry_optimized=pos.opt_entry, tri_at_entry=pos.tri_entry,
            dynamic_risk_used=sig.dynamic_risk,
            T_info_at_entry=sig.T_info_val,
            exit_time=exit_time, indicators=indicators,
        ))

    for sig in signals:
        if capital <= CFG.CAPITAL_FLOOR + 0.1:
            break

        to_close = []
        for sym, pos in open_pos.items():
            ad   = assets[sym]
            toci = _ts_to_ci(ad, sig.timestamp)
            ep, er, ec = _advance(pos, ad, toci)
            if ep > 0:
                _close(pos, ad, ep, er, ec)
                to_close.append(sym)
        for sym in to_close:
            del open_pos[sym]

        sym = sig.symbol
        if sym in open_pos: continue
        if capital <= 0: continue

        drawdown = (peak_cap - capital) / (peak_cap + 1e-12)
        if _drawdown_halted(drawdown, CFG):
            continue  # [إصلاح D-DD1] قاطع دائرة فعلي: لا صفقات جديدة بعد تجاوز MAX_DRAWDOWN_HALT
        dd_mult  = _get_risk_multiplier(drawdown, CFG)

        if len(open_pos) >= CFG.MAX_CONCURRENT_ASSETS: continue

        too_corr = False
        for open_sym in open_pos:
            other_idx = _ts_to_ci(assets[open_sym], sig.timestamp)
            corr_val = compute_correlation_at_idx(assets[sym], assets[open_sym],
                                                  sig.close_idx, other_idx)
            if abs(corr_val) > CFG.CORRELATION_THRESHOLD:
                too_corr = True
                break
        if too_corr:
            continue

        ad = assets[sym]

        opt_ci = sig.close_idx
        opt_px = sig.price
        opt_entry = False

        sl_distance = abs(sig.price - sig.sl)

        if sig.action == "BUY":
            sl_h = opt_px - sl_distance
        else:
            sl_h = opt_px + sl_distance

        delta = abs(opt_px - sl_h)
        if delta < 1e-8: continue

        if CFG.SINGULARITY_MODE:
            risk_amt = capital * sig.dynamic_risk
        else:
            free_ratio = max(0.0, (capital - CFG.CAPITAL_FLOOR) / capital)
            power_law_scale = np.sqrt(free_ratio)
            risk = float(np.clip(sig.dynamic_risk * dd_mult * power_law_scale, CFG.MIN_RISK, CFG.MAX_RISK))
            risk_amt = (capital - CFG.CAPITAL_FLOOR) * risk

        qty = risk_amt / delta

        dynamic_leverage = compute_dynamic_leverage(capital, CFG)
        max_notional = capital * dynamic_leverage

        qty = min(qty, max_notional / opt_px)
        not_ = qty * opt_px

        if not_ < CFG.MIN_NOTIONAL: continue

        eff_px    = apply_slippage(opt_px, qty, sig.adv_usd, sig.action, mode)
        slip_paid = abs(eff_px - opt_px) * qty

        if sig.action == "BUY":
            sl_h = eff_px - sl_distance
        else:
            sl_h = eff_px + sl_distance

        delta = abs(eff_px - sl_h)
        if delta < 1e-8:
            continue

        if delta < 0.001 * eff_px:
            continue

        qty = min(risk_amt / delta, max_notional / eff_px)
        not_ = qty * eff_px

        if not_ < CFG.MIN_NOTIONAL:
            continue

        open_pos[sym] = OpenPosition(
            symbol=sym, signal=sig,
            entry_px=eff_px, pos_size=qty, trail_sl=sl_h,
            entry_cap=capital, entry_ci=opt_ci, current_ci=opt_ci,
            slip_paid=slip_paid, opt_entry=opt_entry, tri_entry=sig.tri_val
        )

    for sym, pos in list(open_pos.items()):
        ad = assets[sym]
        end_ci = len(ad.closes) - 1
        ep, er, ec = _advance(pos, ad, end_ci)
        if ep > 0:
            _close(pos, ad, ep, er, ec)
        else:
            _close(pos, ad, ad.closes[-1], "EndOfData", end_ci)

    return trades_out, equity


# ════════════════════════════════════════════════════════════════
# § 16  المقاييس الإحصائية
# ════════════════════════════════════════════════════════════════

def compute_metrics(trades, equity, init):
    if not trades: return {'n_trades':0}
    pnls  = [t.net_pnl for t in trades]
    lrs   = [t.log_return for t in trades]
    wins  = [p for p in pnls if p>0]; loss=[p for p in pnls if p<=0]
    lw    = sum(1 for t in trades if t.liq_warn)
    opt   = sum(1 for t in trades if t.entry_optimized)
    tri_x = sum(1 for t in trades if t.exit_reason.startswith("TRI"))
    topo_x= sum(1 for t in trades if t.exit_reason.startswith("Topo"))
    eq    = np.array(equity)
    peak  = np.maximum.accumulate(eq)
    dd    = (peak-eq)/(peak+1e-12)*100
    m_lr  = float(np.mean(lrs)); s_lr=float(np.std(lrs,ddof=1))
    sh    = (m_lr/s_lr*np.sqrt(252)) if s_lr>1e-10 else 0.
    ec: Dict[str,int]={}
    for t in trades:
        k = t.exit_reason.split("=")[0] if "=" in t.exit_reason else \
            t.exit_reason.split("(")[0]
        ec[k] = ec.get(k,0)+1

    avg_T_info   = float(np.mean([t.T_info_at_entry for t in trades]))
    avg_dyn_risk = float(np.mean([t.dynamic_risk_used for t in trades]))
    sell_count   = sum(1 for t in trades if t.action=="SELL")
    buy_count    = sum(1 for t in trades if t.action=="BUY")

    # [v7 - تحسين ١١] Deflated Sharpe Ratio و PBO تقريبي — تحقق صارم من أن
    # الحافة المرصودة ليست نتاج تعدد المحاولات (راجع CFG.N_TRIALS_TESTED).
    dsr_info = deflated_sharpe_ratio(np.array(lrs), n_trials=CFG.N_TRIALS_TESTED)
    pbo_info = probability_backtest_overfitting_approx(np.array(lrs))

    return {
        'mean_log_return': m_lr, 'median_log_return': float(np.median(lrs)),
        'std_log_return':  s_lr, 'n_trades': len(trades),
        'win_rate':   len(wins)/len(pnls), 'sharpe_ratio': sh,
        'profit_factor': (sum(wins)/abs(sum(loss))) if loss and wins else float('inf'),
        'avg_win':  float(np.mean(wins)) if wins else 0.,
        'avg_loss': float(np.mean(loss)) if loss else 0.,
        'initial_capital': init, 'final_capital': equity[-1],
        'total_return_pct': (equity[-1]-init)/init*100,
        'max_drawdown_pct': float(np.max(dd)),
        'max_drawdown_abs': float(np.max(peak-eq)),
        'liq_warnings': lw, 'liq_warn_pct': lw/len(trades)*100,
        'optimal_entries': opt, 'opt_entry_pct': opt/len(trades)*100,
        'tri_exits': tri_x, 'tri_exit_pct': tri_x/len(trades)*100,
        'topo_exits': topo_x, 'topo_exit_pct': topo_x/len(trades)*100,
        'total_slip': sum(t.slippage_paid for t in trades),
        'exit_distribution': ec,
        'avg_T_info': avg_T_info,
        'avg_dynamic_risk': avg_dyn_risk,
        'buy_count': buy_count, 'sell_count': sell_count,
        'dsr_info': dsr_info, 'pbo_info': pbo_info,
    }

# ════════════════════════════════════════════════════════════════
# § 17  التقرير والرسوم البيانية
# ════════════════════════════════════════════════════════════════

def print_report(m, mode):
    sep = "═"*72
    print(f"\n{sep}")
    print(f"   📊  محرك التداول الثرموديناميكي الكمي v6.3  [{mode.upper()}]")
    print(sep)
    if not m.get('n_trades'):
        print("   لا توجد صفقات."); return

    print("\n▶ المقياس الأساسي (م٦): E[ln(1+fR)] لكل صفقة")
    print(f"   متوسط  : {m['mean_log_return']:+.6f}")
    print(f"   وسيط   : {m['median_log_return']:+.6f}")
    print(f"   انحراف : {m['std_log_return']:.6f}")
    print(f"   → {'✅ حافة إيجابية' if m['mean_log_return']>0 else '❌ حافة سلبية'}")

    print("\n▶ إحصاءات الصفقات")
    print(f"   عدد الصفقات      : {m['n_trades']:,}")
    print(f"   شراء / بيع        : {m['buy_count']:,} / {m['sell_count']:,}")
    print(f"   نسبة النجاح      : {m['win_rate']*100:.2f}%")
    print(f"   عامل الربح (PF)  : {m['profit_factor']:.3f}")
    print(f"   متوسط الربح      : ${m['avg_win']:,.4f}")
    print(f"   متوسط الخسارة   : ${m['avg_loss']:,.4f}")
    print(f"   شارب (سنوي)      : {m['sharpe_ratio']:.3f}")
    print(f"   دخول مُحسَّن       : {m['optimal_entries']:,}  ({m['opt_entry_pct']:.1f}%)")

    print("\n▶ التعديلات v6.3")
    print(f"   ① متوسط T_info (حرارة معلوماتية) : {m['avg_T_info']:.4f}")
    print(f"   ① متوسط المخاطرة الديناميكية     : {m['avg_dynamic_risk']*100:.3f}%")
    print(f"   ② خروج توبولوجي (Topo-Div)       : {m['topo_exits']:,}  ({m['topo_exit_pct']:.1f}%)")
    print(f"   خروج TRI مبكر                    : {m['tri_exits']:,}  ({m['tri_exit_pct']:.1f}%)")
    print(f"   انزلاق إجمالي                    : ${m['total_slip']:,.2f}")

    print("\n▶ رأس المال (مقياس ثانوي)")
    print(f"   ابتدائي: ${m['initial_capital']:.2f}  →  نهائي: ${m['final_capital']:,.2f}")
    print(f"   العائد الكلي     : {m['total_return_pct']:,.1f}%")
    print(f"   أقصى انخفاض     : {m['max_drawdown_pct']:.2f}%  (${m['max_drawdown_abs']:,.2f})")

    lw_pct = m['liq_warn_pct']
    wrn = "⛔ مرتفع" if lw_pct>20 else ("⚠ ملحوظ" if lw_pct>5 else "✅ معقول")
    print(f"\n▶ تحذير السيولة (م٦): {m['liq_warnings']:,} ({lw_pct:.1f}%)  {wrn}")

    print("\n▶ توزيع أسباب الخروج")
    for r,c in sorted(m['exit_distribution'].items(), key=lambda x:-x[1]):
        print(f"   {r:25s}: {c:7,}  ({c/m['n_trades']*100:.1f}%)")

    # [v7 - تحسين ١١] التحقق الصارم
    dsr = m.get('dsr_info', {}); pbo = m.get('pbo_info', {})
    print("\n▶ التحقق الإحصائي الصارم (v7)")
    if dsr.get('n_trials') is not None:
        verdict = "✅ يصعب تفسيرها بالحظ" if dsr.get('dsr', 0) > 0.95 else \
                  ("⚠ غير حاسمة" if dsr.get('dsr', 0) > 0.5 else "❌ لا تختلف إحصائياً عن الحظ")
        print(f"   Sharpe الخام (لكل صفقة)  : {dsr.get('sr', 0):.4f}")
        print(f"   SR0 (عتبة العشوائية, n={dsr.get('n_trials')})  : {dsr.get('sr0', 0):.4f}")
        print(f"   Deflated Sharpe Ratio    : {dsr.get('dsr', 0):.4f}  {verdict}")
    else:
        print(f"   {dsr.get('note','—')}")
    if pbo.get('pbo_approx') is not None:
        print(f"   PBO تقريبي               : {pbo['pbo_approx']*100:.1f}%  ({pbo.get('note','')})")
    else:
        print(f"   {pbo.get('note','—')}")
    print("   [ملاحظة]: PBO هنا تقريب اتجاهي على شرائح زمنية من صفقات باك-تيست")
    print("   واحد فقط، وليس CSCV الكامل عبر توليفات إعداد متعددة. حدِّث")
    print("   CFG.N_TRIALS_TESTED بصدق (عدد التوليفات/المعايرات التي جُرِّبت")
    print("   فعلياً على هذه البيانات) وإلا فـ DSR ستكون متفائلة زائفاً.")
    print(f"\n{sep}\n")


def plot_results(trades, equity, m, out="quantum_v6_results.png"):
    fig = plt.figure(figsize=(20,14), facecolor='#0d0d0d')
    gs  = gridspec.GridSpec(3,4, figure=fig, hspace=0.45, wspace=0.38)
    bk,tc,gr = '#111111','#e0e0e0','#2a2a2a'
    plt.rcParams.update({'text.color':tc,'axes.labelcolor':tc,
                         'xtick.color':tc,'ytick.color':tc})
    eq = np.array(equity)

    ax1 = fig.add_subplot(gs[0,:])
    ax1.semilogy(eq, c='#00e5ff', lw=0.7, alpha=0.9)
    ax1.fill_between(range(len(eq)), CFG.INITIAL_CAPITAL, eq,
                     where=eq>=CFG.INITIAL_CAPITAL, color='#00e5ff', alpha=0.08)
    ax1.axhline(CFG.INITIAL_CAPITAL, c='#ff6b6b', ls='--', lw=1.)
    ax1.set_facecolor(bk); ax1.grid(True,c=gr,lw=0.4)
    ax1.set_title(
        f"منحنى الأسهم (Log) | v6.3 | "
        f"{m['n_trades']:,} صفقة | MaxDD={m['max_drawdown_pct']:.1f}%",
        c='#00e5ff', fontsize=11)

    ax2 = fig.add_subplot(gs[1,0])
    lrs=[t.log_return for t in trades]
    ax2.hist(lrs,bins=80,color='#ab47bc',alpha=0.7,edgecolor='none')
    ax2.axvline(0,c='#ff6b6b',lw=1.5,ls='--')
    ax2.axvline(m['mean_log_return'],c='#00e5ff',lw=1.5,
                label=f"μ={m['mean_log_return']:.5f}")
    ax2.set_facecolor(bk); ax2.grid(True,c=gr,lw=0.4)
    ax2.set_title("توزيع ln(1+fR)",c='#ab47bc',fontsize=10)
    ax2.legend(fontsize=8,framealpha=0.3)

    ax3 = fig.add_subplot(gs[1,1])
    peak=np.maximum.accumulate(eq); dd=(peak-eq)/(peak+1e-12)*100
    ax3.fill_between(range(len(dd)),0,-dd,color='#ef5350',alpha=0.6)
    ax3.set_facecolor(bk); ax3.grid(True,c=gr,lw=0.4)
    ax3.set_title(f"Drawdown (max={m['max_drawdown_pct']:.1f}%)",c='#ef5350',fontsize=10)

    ax4 = fig.add_subplot(gs[1,2])
    T_wins = [t.T_info_at_entry for t in trades if t.net_pnl>0]
    T_loss = [t.T_info_at_entry for t in trades if t.net_pnl<=0]
    ax4.hist(T_wins, bins=40, alpha=0.7, color='#66bb6a', label='رابحة')
    ax4.hist(T_loss, bins=40, alpha=0.7, color='#ef5350', label='خاسرة')
    ax4.axvline(m['avg_T_info'], c='#00e5ff', lw=1.5, label=f"μ={m['avg_T_info']:.3f}")
    ax4.set_facecolor(bk); ax4.grid(True,c=gr,lw=0.4)
    ax4.set_title("① T_info عند الدخول (Boltzmann)",c='#66bb6a',fontsize=10)
    ax4.legend(fontsize=7,framealpha=0.3)

    ax5 = fig.add_subplot(gs[1,3])
    labs=list(m['exit_distribution'].keys()); vals=list(m['exit_distribution'].values())
    clrs=['#26c6da','#66bb6a','#ffa726','#ef5350','#ab47bc','#78909c','#ff7043']
    ax5.pie(vals,labels=labs,autopct='%1.1f%%',colors=clrs[:len(labs)],textprops={'color':tc,'fontsize':8})
    ax5.set_title("② أسباب الخروج",c=tc,fontsize=10)

    ax6 = fig.add_subplot(gs[2,0])
    buy_pnl  = [t.net_pnl for t in trades if t.action=="BUY"]
    sell_pnl = [t.net_pnl for t in trades if t.action=="SELL"]
    ax6.hist(buy_pnl,  bins=50, alpha=0.7, color='#66bb6a', label=f'BUY  n={len(buy_pnl)}')
    ax6.hist(sell_pnl, bins=50, alpha=0.7, color='#ef5350', label=f'SELL n={len(sell_pnl)}')
    ax6.axvline(0,c='white',lw=1.,ls='--')
    ax6.set_facecolor(bk); ax6.grid(True,c=gr,lw=0.4)
    ax6.set_title("④ BUY vs SELL (Λ-bias)",c=tc,fontsize=10)
    ax6.legend(fontsize=8,framealpha=0.3)

    ax7 = fig.add_subplot(gs[2,1])
    sg={}
    for t in trades: sg.setdefault(int(t.score),[]).append(1. if t.net_pnl>0 else 0.)
    scs=sorted(sg.keys()); wrs=[np.mean(sg[s])*100 for s in scs]; cnts=[len(sg[s]) for s in scs]
    ax7.bar(scs,wrs,color='#26c6da',alpha=0.8)
    ax7.set_facecolor(bk); ax7.grid(True,c=gr,lw=0.4,axis='y')
    ax7.set_title("نجاح حسب Score",c='#26c6da',fontsize=10)
    for s,w,c in zip(scs,wrs,cnts): ax7.text(s,w+.5,f"{c}",ha='center',fontsize=7,color=tc)

    ax8 = fig.add_subplot(gs[2,2])
    dr_vals = [t.dynamic_risk_used*100 for t in trades]
    ax8.hist(dr_vals, bins=50, color='#ffa726', alpha=0.8, edgecolor='none')
    ax8.axvline(CFG.BASE_RISK*100, c='#ff6b6b', lw=1.5, ls='--', label=f'Base={CFG.BASE_RISK*100}%')
    ax8.set_facecolor(bk); ax8.grid(True,c=gr,lw=0.4)
    ax8.set_title("① توزيع f*(T) الديناميكي",c='#ffa726',fontsize=10)
    ax8.legend(fontsize=8,framealpha=0.3)

    ax9 = fig.add_subplot(gs[2,3]); ax9.axis('off'); ax9.set_facecolor(bk)
    summ=(f"صفقات: {m['n_trades']:,}\n"
          f"نجاح:  {m['win_rate']*100:.1f}%\n"
          f"PF:    {m['profit_factor']:.2f}\n"
          f"Sharpe:{m['sharpe_ratio']:.2f}\n"
          f"MaxDD: {m['max_drawdown_pct']:.1f}%\n"
          f"Topo:  {m['topo_exit_pct']:.1f}%\n"
          f"TRI:   {m['tri_exit_pct']:.1f}%\n"
          f"Opt:   {m['opt_entry_pct']:.1f}%\n"
          f"T_avg: {m['avg_T_info']:.3f}\n"
          f"r_avg: {m['avg_dynamic_risk']*100:.3f}%\n"
          f"Slip:  ${m['total_slip']:,.0f}")
    ax9.text(0.05,0.95,summ,transform=ax9.transAxes,va='top',color=tc,fontsize=9,
             fontfamily='monospace',
             bbox=dict(boxstyle='round',fc='#1e1e1e',alpha=0.85))
    plt.savefig(out,dpi=150,bbox_inches='tight',facecolor='#0d0d0d',edgecolor='none')
    log.info(f"📊 {out}")


# ════════════════════════════════════════════════════════════════
# § 18  وضع الباك-تيست
# ════════════════════════════════════════════════════════════════

def run_backtest(cfg):
    try:
        import ccxt
    except ImportError:
        log.error("pip install ccxt"); return

    exchange = ccxt.binance({'enableRateLimit':True, 'options':{'defaultType':'future'}})

    log.info("§1  مسح أعلى 15 عملة...")
    syms = scan_top_assets(exchange, cfg.n_assets)

    log.info("§2  جلب البيانات (متوازٍ)...")
    raw = fetch_all(syms, exchange, cfg.timeframe, cfg.history_days, workers=5)
    if not raw:
        log.error("لا بيانات.")
        return

    log.info("§2b جلب بيانات الفريم الأكبر (15m)...")
    raw_high = fetch_all(syms, exchange, CFG.HIGHER_TF, cfg.history_days, workers=5)
    if not raw_high:
        log.warning("تعذر جلب بيانات الفريم الأكبر، سيتم تعطيل فلتر الاتجاه العام.")

    log.info("§3  معالجة فضاء الحالة (K ديناميكي)...")
    assets: Dict[str, AssetData] = {}
    for sym, df in raw.items():
        ad = process_asset(sym, df, current_capital=cfg.INITIAL_CAPITAL,
                           df_high=raw_high.get(sym))
        if ad:
            assets[sym] = ad
            nt = int(np.sum(ad.score[ad.train_end:] >= cfg.MIN_SCORE))
            log.info(f"  ✓ {sym:14s} | K={ad.dynamic_k} | اختبار={nt:5,} | tri_μ={np.mean(ad.tri):.2f}")

    log.info("§4  بناء الإشارات (①②④⑤ مُفعَّلة)...")
    sigs = build_signals(assets)
    sigs = deduplicate_signals(sigs)
    log.info(f"  ✔ {len(sigs):,} إشارة")

    # [إصلاح الانهيار الأصلي] `max()`/`np.mean()` على قائمة فارغة يرمي
    # ValueError إن لم توجد أي إشارات (كان هذا هو سبب الانهيار في السجل —
    # وهو عرَض تال لغياب الإشارات، لا سبباً مستقلاً). الآن بعد إصلاح جذر
    # المشكلة في compute_features/compute_geometry يجب ألا تصل القائمة فارغة
    # في التشغيل الطبيعي، لكن نُبقي الحارس دفاعياً لأي سوق/إعدادات شديدة
    # التقييد لا تُنتج أي إشارة.
    if not sigs:
        log.warning("  ⚠️ لم يتم العثور على أي إشارة في هذه الفترة — تخطي إحصاءات الإشارات والمحاكاة.")
        return
    T_vals = [s.T_info_val for s in sigs]
    dr_vals = [s.dynamic_risk for s in sigs]
    buy_sigs = sum(1 for s in sigs if s.action == "BUY")
    sell_sigs = sum(1 for s in sigs if s.action == "SELL")
    log.info(f"  T_info: μ={np.mean(T_vals):.3f} | σ={np.std(T_vals):.3f}")
    log.info(f"  risk_dynamic: μ={np.mean(dr_vals)*100:.3f}% | max={max(dr_vals)*100:.2f}%")
    log.info(f"  BUY={buy_sigs:,} | SELL={sell_sigs:,} (Λ={cfg.COSMOLOGICAL_CONSTANT})")

    log.info("§5  محاكاة المحفظة متعددة المراكز (بدون غش الارتباط)...")
    trades, equity = simulate_portfolio(sigs, assets, "backtest")
    log.info(f"  ✔ {len(trades):,} صفقة")

    if cfg.EXPORT_TRADES_CSV:
        export_trades_csv(trades, cfg.TRADES_CSV_PATH)
    if cfg.EXPORT_TRADE_HTML:
        generate_all_trade_charts(trades, assets, cfg.TRADE_HTML_DIR, cfg.TRADE_HTML_CONTEXT_BARS)

    m = compute_metrics(trades, equity, cfg.INITIAL_CAPITAL)

    log.info("§6  انحدار الإنتروبيا...")
    for sym, ad in list(assets.items())[:4]:
        H_t = ad.H[ad.train_end:]
        if len(H_t) > 10:
            r = entropy_regression(H_t)
            log.info(f"  {sym:14s}: b={r['slope']:+.5f}  R²={r['r2']:.3f}  [{r['trend']}]")

    print_report(m, "backtest")
    plot_results(trades, equity, m)
    log.info("✅ اكتمل.")
    log.info(f"   E[ln(1+fR)] = {m.get('mean_log_return', 0):+.6f}")
    log.info(f"   MaxDrawdown  = {m.get('max_drawdown_pct', 0):.2f}%")
    log.info(f"   Topo-Exits   = {m.get('topo_exit_pct', 0):.1f}%")
    log.info(f"   AvgRisk      = {m.get('avg_dynamic_risk', 0)*100:.3f}%")


# ════════════════════════════════════════════════════════════════
# § 18.8  محرك الزمكان اللحظي (Quantum WebSocket Streamer) — v6.3
# ════════════════════════════════════════════════════════════════
class BinanceWSEngine:
    """
    [إعادة هيكلة v6.3 — الإصلاح الجذري لمشكلة "الترددات الصغيرة"]

    الفرق الجوهري عن الإصدارات السابقة: تدفق Binance kline عبر WebSocket يُرسل
    حقل `k.x` (isClosed) في كل رسالة — `False` طوال حياة الشمعة الجارية و
    `True` مرة واحدة فقط عند إغلاقها فعلياً. النسخ السابقة كانت **تتجاهل هذا
    الحقل تماماً** وتُعامل كل رسالة (سواء كانت الشمعة مغلقة أو لا تزال تتشكل)
    بنفس الطريقة، ثم تُدرِج هذه "الشمعة الشبحية" (Phantom Candle) في نفس مسار
    البيانات المستخدم لحساب الميزات (الإنتروبيا H، القوة الجيوديسية، إلخ) التي
    تقرر الدخول/الخروج (Apex/Topo).

    لماذا هذا هو مصدر "الترددات الصغيرة" التي تُطلق Apex/Emergency-SL قبل أوانه:
    الشمعة الجارية تتغير قيمها (O/H/L/C/V) عشرات أو مئات المرات في الثانية قبل
    إغلاقها. كل تغيير طفيف في C أو V يُغيّر ناتج `compute_features` لتلك النقطة
    الأخيرة، مما يُغيّر تعيين عنقودها (KMeans)، ومن ثم رمزها الإحصائي، ومن ثم
    الإنتروبيا المتدحرجة H وتغيّراتها dH وd2H، ومن ثم `geodesic_accel` وdF —
    وكلها المدخلات المباشرة لـ `check_thermodynamic_apex`. بعبارة أخرى: كنا
    نُقيّم شرط Apex (بنفس عتباته العددية الصحيحة تماماً) **عشرات المرات على نفس
    "الشمعة" بينما هي لا تزال تتقلب عشوائياً**، بدل مرة واحدة فقط بعد اكتمالها —
    وهذا يُشبه إحصائياً مسألة "الاختبارات المتعددة" (Multiple Hypothesis Testing):
    كلما زاد عدد محاولات اختبار نفس الفرضية على بيانات ضجيجية غير مستقرة، زاد
    احتمال عبور العتبة ولو بالصدفة البحتة، حتى لو كانت العتبة نفسها ممتازة
    ومضبوطة بعناية (كما هي هنا). هذا **لا علاقة له بقيمة العتبات** — لذلك لم
    تُغيَّر أي عتبة عددية في هذا الإصلاح.

    الحل: نفصل تماماً بين:
      • `live_prices[sym]`  — آخر سعر تداول لحظي (من أي رسالة، مغلقة أو لا)،
        يُستخدم فقط لفحص السعر الخام مقابل SL/TP (وهذا **صحيح ومطابق تماماً**
        لما يفعله الباك-تيست: فحص القمة/القاع الفعلي للشمعة أثناء تكوّنها هو
        بالضبط ما يمثله tick السعر اللحظي — لا نغيّر هذا الجزء إطلاقاً).
      • `closed_candles[sym]` — تُحدَّث **فقط** عندما تصل رسالة بعلامة `x=True`،
        وهذه فقط هي التي تُغذّي `cached_data` ومن ثم `process_asset` ومن ثم
        Apex/Topo. بهذا تُقيَّم هذه الشروط **مرة واحدة بالضبط بعد اكتمال كل
        شمعة**، تماماً كما يفعل الباك-تيست الذي يمر على شموع تاريخية مغلقة فقط.
    """
    def __init__(self, symbols: List[str], timeframe: str):
        self.symbols = [s.lower().replace('/', '') for s in symbols]
        self.timeframe = timeframe
        self.live_candles: Dict[str, list] = {}      # آخر شمعة (مغلقة أو جارية) للسعر اللحظي فقط
        self.live_prices: Dict[str, float] = {}
        self.closed_candles: Dict[str, list] = {}     # [ts,o,h,l,c,v] لآخر شمعة مغلقة فقط لكل رمز
        self._closed_dirty: set = set()                # رموز لديها شمعة مغلقة جديدة لم تُستهلك بعد
        self.lock = threading.Lock()
        self.ws = None
        self.thread = None
        self.is_running = False
        # [إصلاح CONN-1] عدّاد محاولات إعادة الاتصال المتتالية للتراجع الأُسي
        # (Exponential Backoff) بدل تأخير ثابت 3 ثوانٍ — ينخفض العبء على
        # الشبكة/المنصة تلقائياً أثناء انقطاع طويل، ويعود فوراً لأقصر تأخير
        # بمجرد استقرار الاتصال من جديد (راجع on_message).
        self._reconnect_attempts = 0
        # [إصلاح CONN-2] طابع زمني لآخر رسالة استُلمت فعلياً — يُستخدم من
        # LiveEngine.feature_loop لاكتشاف "اتصال ميت بصمت" (لا onclose يُطلَق،
        # لكن لا رسائل تصل أيضاً — انقطاع شبكي نصف مفتوح كلاسيكي) وإجباره على
        # إعادة الاتصال بدل الانتظار إلى ما لا نهاية.
        self.last_message_ts: float = 0.0

    def on_message(self, ws, message):
        # [إصلاح CONN-3] أي استثناء غير متوقع هنا (رسالة مشوّهة، حقل مفقود،
        # إلخ) يجب ألا يُفلت خارج رد النداء إطلاقاً — بعض إصدارات مكتبة
        # websocket-client لا تتعامل بلطف مع استثناء داخل on_message وقد
        # يُعطّل ذلك حلقة الاستماع بصمت. الالتقاط هنا صريح ومُسجَّل، ولا يُغيّر
        # أي منطق تحليل رسالة سليمة.
        try:
            self.last_message_ts = time.time()
            self._reconnect_attempts = 0  # اتصال حي ومستقر — تصفير التراجع الأُسي
            data = json.loads(message)
            if 'data' in data:
                kline = data['data']['k']
                sym = _norm_symbol(data['data']['s'].upper().replace('USDT', '/USDT'))

                ts = int(kline['t'])
                o, h, l, c, v = float(kline['o']), float(kline['h']), float(kline['l']), float(kline['c']), float(kline['v'])
                is_closed = bool(kline.get('x', False))

                with self.lock:
                    self.live_candles[sym] = [ts, o, h, l, c, v]
                    self.live_prices[sym] = c
                    if is_closed:
                        self.closed_candles[sym] = [ts, o, h, l, c, v]
                        self._closed_dirty.add(sym)
        except Exception as e:
            log.warning(f"⚠️ رسالة WebSocket غير متوقعة تم تجاهلها بأمان: {e}")

    def on_error(self, ws, error):
        log.error(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        if self.is_running:
            # [إصلاح CONN-1] تراجع أُسي محدود السقف بدل 3 ثوانٍ ثابتة دائماً —
            # يمنع محاولات إعادة اتصال متلاحقة بلا جدوى أثناء عطل ممتد
            # (صيانة المنصة، انقطاع فعلي في الإنترنت) قد تُحسَب كإساءة استخدام
            # من طرف المنصة، مع إبقاء زمن استجابة سريع (3 ثوانٍ) للحالة
            # الشائعة (انقطاع عابر لحظي).
            self._reconnect_attempts += 1
            delay = min(3.0 * (2 ** (self._reconnect_attempts - 1)), 60.0)
            log.warning(f"WebSocket Closed. إعادة الاتصال خلال {delay:.0f} ثانية "
                        f"(محاولة #{self._reconnect_attempts})...")
            threading.Timer(delay, self._reconnect).start()

    def _reconnect(self):
        if self.is_running:
            self.start()

    def is_stale(self, threshold_secs: float = 90.0) -> bool:
        """
        [إصلاح CONN-2] يكتشف اتصالاً "ميتاً بصمت": WS ما زال is_running=True
        (لم يُطلَق on_close)، لكن لم تصل أي رسالة منذ threshold_secs — سيناريو
        شائع عند انقطاع شبكي نصف مفتوح (النظام المحلي لا يزال يعتقد أن المقبس
        مفتوح، لكن لا بيانات تصل فعلياً). لا يُصدر أي إجراء بنفسه؛ المستدعي
        (LiveEngine.feature_loop) هو من يقرر إعادة تشغيل الاتصال عند True.
        """
        if not self.is_running or self.last_message_ts <= 0:
            return False
        return (time.time() - self.last_message_ts) > threshold_secs

    def force_reconnect(self):
        """[إصلاح CONN-2] إعادة اتصال قسرية عند اكتشاف اتصال ميت بصمت (raw kline)."""
        log.warning("⚠️ لم تصل أي بيانات WebSocket منذ فترة طويلة رغم عدم إغلاق الاتصال ظاهرياً "
                    "— إعادة اتصال قسرية.")
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self.start()

    def get_live_candle(self, sym: str):
        with self.lock:
            return self.live_candles.get(sym)

    def get_live_price(self, sym: str):
        with self.lock:
            return self.live_prices.get(sym)

    def get_closed_candle(self, sym: str):
        with self.lock:
            return self.closed_candles.get(sym)

    def pop_dirty_closed_symbols(self) -> set:
        """يُعيد مجموعة الرموز التي أُغلقت لها شمعة جديدة منذ آخر استدعاء، ويُصفّرها."""
        with self.lock:
            dirty = set(self._closed_dirty)
            self._closed_dirty.clear()
            return dirty

    def start(self):
        self.is_running = True
        streams = '/'.join([f"{sym}@kline_{self.timeframe}" for sym in self.symbols])
        ws_url = f"wss://fstream.binance.com/stream?streams={streams}"

        self.ws = websocket.WebSocketApp(ws_url,
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)

        # [إصلاح CONN-2] ping/pong على مستوى البروتوكول: يكتشف اتصالاً معطوباً
        # أسرع بكثير من انتظار مهلة TCP الافتراضية (قد تصل لدقائق)، ويُطلِق
        # on_close تلقائياً إن لم يصل pong خلال ping_timeout — يُكمِّل حارس
        # is_stale أعلاه (طبقتا حماية مستقلتان لنفس المشكلة).
        self.thread = threading.Thread(
            target=self.ws.run_forever,
            kwargs={'ping_interval': 20, 'ping_timeout': 10},
            daemon=True)
        self.thread.start()
        log.info(f"🌐 تم فتح النفق الكمومي (WebSocket) لـ {len(self.symbols)} أصول.")

    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()


def _persist_live_state(state_file: str, open_pos_live: Dict, pending_orders: Dict) -> None:
    """كتابة ذرّية (Atomic Write) لملف حالة التداول الحي، لمنع تلف الملف عند انقطاع مفاجئ."""
    try:
        tmp_path = f"{state_file}.tmp"
        with open(tmp_path, 'w') as f:
            json.dump({'open_pos_live': open_pos_live, 'pending_orders': pending_orders}, f, indent=2)
        os.replace(tmp_path, state_file)
    except Exception as e:
        log.error(f"❌ فشل حفظ حالة التداول الحي: {e}")


# ════════════════════════════════════════════════════════════════
# § 19  محرك Live/Testnet v6.3 — دفتر كمية + شموع مغلقة فقط + أوامر بلا فقد أولوية
# ════════════════════════════════════════════════════════════════
#
# ملخص كل ما تغيّر عن v6.2 هنا (تفاصيل كاملة في PROBLEMS.md وFIX_PLAN.md):
#
#  1) execute_quantum_chunks (أعلاه): دفتر كمية صريح remaining_qty + إعادة تسعير
#     كل حزمة بسعر طازج + إعادة تسعير عند انحراف حقيقي فقط (لا مؤقت أعمى).
#  2) BinanceWSEngine (أعلاه): فصل صارم بين السعر اللحظي (لفحص SL/TP) وبين
#     الشموع المغلقة فقط (لحساب ميزات Apex/Topo) — يُطابق تماماً عقد الباك-تيست.
#  3) هنا: LiveEngine يستهلك فقط الشموع المغلقة في cached_data/self.assets،
#     ويُصلح سباقاً في إطلاق خيوط الحراس، ويتعامل بأمان مع أي مركز "يتيم"
#     (غير معروف الأصل) بدل منحه SL=0/TP=0 اللذين كانا يُشغّلان إغلاقاً فورياً
#     مُصنَّفاً خطأً كـ"Hard TP"/"Emergency SL".
# ════════════════════════════════════════════════════════════════


def _feature_worker(args):
    sym, df, df_high, current_capital = args
    try:
        ad = process_asset(sym, df, current_capital=current_capital, df_high=df_high)
        return sym, ad, None
    except Exception as e:
        return sym, None, str(e)


class LiveEngine:
    def __init__(self, cfg: Config, exchange):
        self.cfg = cfg
        self.exchange = exchange
        self.state_file = f"live_state_{cfg.mode}.json"

        # ── أقفال التزامن ────────────────────────────────────────────────
        self.state_lock = threading.RLock()
        # [إصلاح D15] يحمي تحديداً عملية "تحقق ثم أنشئ" لخيوط الحراس، لمنع
        # إطلاق خيطين مستقلين لنفس الرمز في نفس اللحظة (سباق تحقق-ثم-فعل).
        self.guardian_lock = threading.Lock()
        self.exchange_sema = threading.Semaphore(8)

        self.open_pos_live: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, Dict] = {}
        self.assets: Dict[str, AssetData] = {}
        # [v6.3] cached_data يحتوي الآن الشموع *المغلقة فقط* — لا يُدمَج فيها
        # أبداً أي شمعة جارية لم تُغلق بعد. هذا هو التبديل الجذري الذي يحل
        # مشكلة "الترددات الصغيرة".
        self.cached_data: Dict[str, pd.DataFrame] = {}
        self.cached_data_high: Dict[str, pd.DataFrame] = {}
        self.top_syms: List[str] = []
        self.cap_live: float = cfg.INITIAL_CAPITAL
        # [إصلاح D-DD2 — عيب أمان جوهري مكتشف بالتدقيق] لم يكن هناك أي تتبع لقمة
        # رأس المال (peak) في مسار التداول الحي إطلاقاً، وبالتالي لم يكن ممكناً
        # حساب drawdown هناك، وبالتالي لم يكن dd_mult (تخفيض المخاطرة عند
        # الانخفاض) ولا قاطع الدائرة يُطبَّقان أبداً على الحساب الحي — رغم أن
        # الباك-تيست يطبّقهما بصرامة. هذا يكسر هدف v6.3 المُعلَن صراحة في رأس
        # الملف: "مطابقة سلوك الباك-تيست تماماً". نضيف التتبع هنا.
        self.peak_cap_live: float = cfg.INITIAL_CAPITAL
        self.corr_cache: Dict[Tuple[str, str], float] = {}
        self.ws_engine: Optional[BinanceWSEngine] = None

        self.guardian_threads: Dict[str, threading.Thread] = {}
        self.guardian_stop: Dict[str, threading.Event] = {}
        # [إصلاح WS-APEX1 — جذر مشكلة دقة الدخول/الخروج المُبلَّغ عنها] يتتبع آخر
        # طابع زمني لشمعة *مغلقة* جرى تقييم Apex/Topo-Div/MaxHold عندها لكل رمز،
        # كي تُقيَّم هذه الشروط "المرتبطة بالشمعة" مرة واحدة بالضبط لكل شمعة جديدة
        # تُغلَق (تماماً كما يفعل الباك-تيست) بدل تقييمها كل GUARDIAN_POLL_SECS ضد
        # سعر لحظي متذبذب بينما ميزاتها المُغذِّية (dF/geodesic_accel) لا تزال
        # مجمّدة على نفس الشمعة المغلقة الأخيرة. راجع التوثيق الكامل داخل
        # _position_guardian أدناه.
        self.guardian_last_bar_ts: Dict[str, "pd.Timestamp"] = {}

        self.stop_event = threading.Event()

        n_workers = max(1, min(8, (os.cpu_count() or 4)))
        try:
            mp_ctx = mp.get_context('fork') if hasattr(os, 'fork') else mp.get_context()
        except Exception:
            mp_ctx = None
        self.process_pool = ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_ctx)
        log.info(f"🧮 مجمّع العمليات (Feature Pool) جاهز بـ {n_workers} عامل/عمال")

        self.last_scan_time = 0.0
        self.last_corr_refresh = 0.0
        self.last_rest_resync = 0.0
        self.threads: List[threading.Thread] = []

    # ═══════════════════════════ أدوات مساعدة عامة ═══════════════════════════

    def _persist(self):
        with self.state_lock:
            _persist_live_state(self.state_file, self.open_pos_live, self.pending_orders)

    def _call(self, fn, *args, **kwargs):
        with self.exchange_sema:
            return fn(*args, **kwargs)

    def _spawn_guardian(self, sym: str):
        """[إصلاح D15] فحص-ثم-إطلاق محمي بقفل مخصص لمنع تكرار خيط حارس لنفس الرمز."""
        # [إصلاح WS-APEX1] نُهيّئ آخر طابع زمني "مُقيَّم" على أنه الشمعة المغلقة
        # الحالية وقت الدخول (لا قبلها)، تماماً كما يبدأ الباك-تيست `_advance` من
        # `current_ci + 1` ولا يُعيد فحص شمعة الدخول نفسها. بدون هذا، أول دورة
        # فحص للحارس ستُعامل شمعة الدخول ذاتها كـ"شمعة جديدة" وتُقيّم Apex/Topo
        # عليها فوراً باستخدام سياق ما قبل الدخول، وهو غير صحيح منطقياً.
        ad = self.assets.get(sym)
        if ad is not None and len(ad.timestamps) > 0:
            self.guardian_last_bar_ts[sym] = ad.timestamps[-1]
        with self.guardian_lock:
            old = self.guardian_threads.get(sym)
            if old is not None and old.is_alive():
                return
            stop_flag = threading.Event()
            self.guardian_stop[sym] = stop_flag
            t = threading.Thread(target=self._position_guardian, args=(sym, stop_flag),
                                  name=f"Guardian-{sym}", daemon=True)
            self.guardian_threads[sym] = t
            t.start()
        log.info(f"🛡️ خيط حارس جديد لـ {sym}")

    def _sl_tp_from_signal_like(self, action: str, entry_price: float, dyn_sl_factor: float):
        """
        يُعيد حساب SL/TP بنفس الصيغة المستخدمة في _try_enter، لإعادة استخدامها
        عند "تبنّي" مركز نتج عن تعبئة متأخرة/غامضة (janitor أو reconcile) بدل
        تكرار المنطق أو تركه بلا مستويات حقيقية.
        """
        actual_sl_dist = entry_price * dyn_sl_factor
        if action == "BUY":
            actual_sl = entry_price - actual_sl_dist
            actual_tp = entry_price + 2 * actual_sl_dist
        else:
            actual_sl = entry_price + actual_sl_dist
            actual_tp = entry_price - 2 * actual_sl_dist
        return actual_sl, actual_tp

    def _register_position(self, sym: str, action: str, entry_price: float, qty: float,
                            sl: float, tp1: float, T_info_val: float = 0.0, dyn_risk: float = 0.0):
        sym = _norm_symbol(sym)
        # [جديد] لقطة مؤشرات + وقت الدخول تُحفظ مع المركز نفسه، لتُستخدم لاحقاً
        # عند الإغلاق لبناء سجل الصفقة الكامل لـ CSV/Plotly دون أي تأثير على
        # منطق التداول (حقول إضافية فقط في قاموس الحالة).
        ad = self.assets.get(sym)
        entry_indicators = {}
        entry_time = pd.Timestamp.now(tz="UTC")
        if ad is not None and len(ad.score) > 0:
            fi = len(ad.score) - 1
            entry_indicators = build_indicator_snapshot(ad, fi)
            try:
                entry_time = pd.Timestamp(ad.timestamps[-1])
            except Exception:
                pass
        with self.state_lock:
            self.open_pos_live[sym] = {
                'action': action, 'entry': entry_price, 'qty': qty,
                'sl': sl, 'tp1': tp1, 'T_info': T_info_val, 'dyn_risk': dyn_risk,
                # [ملاحظة] entry_time بصيغة ISO نصية (وليس pd.Timestamp) لأن
                # `_persist_live_state` يستخدم json.dump مباشرة بلا مُرمِّز
                # مخصص — كائن Timestamp غير قابل للتسلسل إلى JSON ويكسر حفظ
                # الحالة بالكامل لولا هذا التحويل.
                'entry_time': entry_time.isoformat(), 'entry_indicators': entry_indicators,
            }
        self._persist()
        self._spawn_guardian(sym)

    def _safe_flatten_unknown(self, sym: str, action_hint: str, qty: float):
        """
        [إصلاح D18] مركز "غير قابل للتتبع" حقاً (لا يوجد له أي سجل أمر معلّق
        نُعيد بناء سياقه منه) لا يجب أبداً أن يُمنح SL=0/TP=0 وهميين — لأن ذلك
        كان يجعل شرط "أعلى/أدنى من صفر" صحيحاً دائماً تقريباً، فيُغلَق المركز
        فوراً في أول فحص للحارس، مُصنَّفاً خطأً كـ"إغلاق هدف/وقف" رغم أنه لم يكن
        كذلك إطلاقاً. البديل الآمن الوحيد المنطقي: تسوية هذا التعرض فوراً
        وبوضوح عبر نفس آلية الإغلاق الكمومي، مع تسجيله بصراحة كإجراء سلامة وليس
        كخروج استراتيجي طبيعي — ولا يدخل دورة إدارة المراكز العادية إطلاقاً.
        """
        sym = _norm_symbol(sym)
        log.error(f"🚨 مركز غير متتبع الأصل على {sym} (qty={qty}) — تسوية فورية للسلامة، "
                  f"لا يُمنح مستويات SL/TP وهمية.")
        try:
            side = 'sell' if action_hint == 'BUY' else 'buy'
            ref_price = self.ws_engine.get_live_price(sym) if self.ws_engine else None
            if ref_price is None:
                ad = self.assets.get(sym)
                ref_price = float(ad.closes[-1]) if ad is not None and len(ad.closes) > 0 else None
            if ref_price is None:
                log.error(f"❌ تعذّر الحصول على سعر مرجعي لتسوية {sym} — سيُعاد المحاولة في الدورة القادمة")
                return
            with self.exchange_sema:
                execute_quantum_chunks(self.exchange, sym, side, qty, ref_price,
                                        self.pending_orders, order_meta={'purpose': 'safety_flatten'})
        except Exception as e:
            log.error(f"❌ فشل تسوية المركز غير المتتبع {sym}: {e}")

    # ═══════════════════════════ الإقلاع والتسوية ═══════════════════════════

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    state = json.load(f)
                    self.open_pos_live = state.get('open_pos_live', {})
                    self.pending_orders = state.get('pending_orders', {})
                log.info(f"  استُعيد {len(self.open_pos_live)} مركز و {len(self.pending_orders)} أمر معلق من الذاكرة المحلية")
            except Exception:
                pass

    def reconcile_startup(self):
        """مطابقة الذاكرة المحلية مع الواقع الفعلي على المنصة عند الإقلاع (وجوداً وكميةً)."""
        if not self.open_pos_live:
            return
        try:
            log.info("🔍 جاري مزامنة الذاكرة مع خوادم المنصة (Observer Measurement)...")
            all_positions = self._call(self.exchange.fetch_positions)
            actual_amt_by_symbol: Dict[str, float] = {}
            for pos in all_positions:
                pos_amt = float(pos['info'].get('positionAmt', 0))
                if abs(pos_amt) > 0:
                    actual_amt_by_symbol[_norm_symbol(pos['symbol'])] = pos_amt

            symbols_to_remove, qty_corrected = [], 0
            for sym, local_pos in self.open_pos_live.items():
                if _norm_symbol(sym) not in actual_amt_by_symbol:
                    log.warning(f"⚠️ المركز {sym} موجود في الذاكرة ولكنه مغلق في المنصة! (سيتم محوه)")
                    symbols_to_remove.append(sym)
                    continue
                actual_qty = abs(actual_amt_by_symbol[_norm_symbol(sym)])
                local_qty = float(local_pos.get('qty', 0) or 0)
                if local_qty <= 0:
                    continue
                rel_diff = abs(actual_qty - local_qty) / max(local_qty, 1e-9)
                if rel_diff > 0.01:
                    log.warning(f"⚠️ انحراف كمية لـ {sym}: محلي={local_qty:.6f} فعلي={actual_qty:.6f} — تصحيح")
                    self.open_pos_live[sym]['qty'] = actual_qty
                    qty_corrected += 1

            with self.state_lock:
                for sym in symbols_to_remove:
                    del self.open_pos_live[sym]
            if symbols_to_remove or qty_corrected:
                self._persist()
            log.info(f"✅ تسوية الإقلاع: حُذف {len(symbols_to_remove)} | صُحح {qty_corrected} | المتبقي {len(self.open_pos_live)}")
        except Exception as e:
            log.error(f"❌ فشل في مزامنة المراكز عند الإقلاع: {e}")

    def bootstrap(self):
        log.info("⏳ جلب الزمكان المالي التاريخي (REST API - مرة واحدة فقط)...")
        self.top_syms = scan_top_assets(self.exchange)
        raw = fetch_all(self.top_syms, self.exchange, self.cfg.timeframe, days=7, workers=5)
        # [v6.3] نحذف أي صف أخير قد يكون شمعة جارية غير مغلقة قبل اعتماد البيانات
        # كـ"بيانات مغلقة" أساسية لحساب الميزات — يمنع تلوث البذرة الأولى بشمعة شبحية.
        self.cached_data = {s: _drop_unclosed_last_row(df, self.cfg.timeframe) for s, df in raw.items()}
        raw_high = fetch_all(self.top_syms, self.exchange, CFG.HIGHER_TF, days=7, workers=5)
        self.cached_data_high = {s: _drop_unclosed_last_row(df, CFG.HIGHER_TF) for s, df in raw_high.items()}
        self.last_scan_time = time.time()
        self.last_rest_resync = time.time()
        if not self.cached_data:
            raise RuntimeError("فشل في تحميل التاريخ الأولي.")

        self.ws_engine = BinanceWSEngine(self.top_syms, self.cfg.timeframe)
        self.ws_engine.start()
        time.sleep(3)
        self.ws_engine.pop_dirty_closed_symbols()  # تفريغ أي أحداث إغلاق وصلت أثناء الإحماء

        self._recompute_features(initial=True)
        self.corr_cache = precompute_correlations(self.assets)
        self.last_corr_refresh = time.time()

        for sym in list(self.open_pos_live.keys()):
            self._spawn_guardian(sym)

    # ═══════════════════════════ حلقة تحديث الميزات (شموع مغلقة فقط) ═══════════════════════════

    def _refresh_asset_universe_if_due(self):
        if time.time() - self.last_scan_time <= self.cfg.ASSET_RESCAN_SECS:
            return
        log.info("🔄 تحديث قائمة الأصول الكبرى...")
        try:
            new_top = scan_top_assets(self.exchange)
            raw = fetch_all(new_top, self.exchange, self.cfg.timeframe, days=7, workers=5)
            new_cached = {s: _drop_unclosed_last_row(df, self.cfg.timeframe) for s, df in raw.items()}
            raw_high = fetch_all(new_top, self.exchange, CFG.HIGHER_TF, days=7, workers=5)
            new_cached_high = {s: _drop_unclosed_last_row(df, CFG.HIGHER_TF) for s, df in raw_high.items()}
            with self.state_lock:
                self.top_syms = new_top
                self.cached_data = new_cached
                self.cached_data_high = new_cached_high
            self.last_scan_time = time.time()
            self.corr_cache = {}
            if self.ws_engine:
                self.ws_engine.stop()
            self.ws_engine = BinanceWSEngine(self.top_syms, self.cfg.timeframe)
            self.ws_engine.start()
            time.sleep(3)
            self.ws_engine.pop_dirty_closed_symbols()
        except Exception as e:
            log.error(f"❌ فشل تحديث قائمة الأصول: {e}")

    def _rest_resync_if_due(self):
        """
        [v6.3] مزامنة REST دورية منخفضة التردد (كل REST_RESYNC_SECS) كشبكة أمان
        في حال فقد WebSocket رسالة إغلاق شمعة (انقطاع مؤقت، إعادة اتصال، إلخ).
        يحذف أي صف أخير غير مغلق قبل الدمج حتى لا تتسرب شمعة جارية إلى البيانات
        "المغلقة".
        """
        if time.time() - self.last_rest_resync <= self.cfg.REST_RESYNC_SECS:
            return
        try:
            for sym in list(self.top_syms):
                fresh = _load_cached(sym, self.exchange, self.cfg.timeframe, days=2)
                if fresh is None:
                    continue
                fresh = _drop_unclosed_last_row(fresh, self.cfg.timeframe)
                with self.state_lock:
                    if sym in self.cached_data:
                        merged = pd.concat([self.cached_data[sym], fresh])
                        merged = merged[~merged.index.duplicated(keep='last')].sort_index()
                        self.cached_data[sym] = merged.tail(self.cfg.N + self.cfg.W + 1000)
                    else:
                        self.cached_data[sym] = fresh
            self.last_rest_resync = time.time()
            log.info("🔁 اكتملت مزامنة REST الدورية (شبكة أمان لأي إغلاق شمعة فائت عبر WS)")
        except Exception as e:
            log.error(f"❌ فشل مزامنة REST الدورية: {e}")

    def _ingest_closed_candles(self) -> set:
        """
        [الإصلاح الجذري v6.3] يسحب فقط الشموع التي أُغلقت فعلياً (x=True) من
        WebSocket ويدمجها في cached_data. لا يُدرَج هنا أبداً أي شمعة لا تزال
        قيد التكوّن. يُعيد مجموعة الرموز التي تغيّرت فعلاً (لإعادة حساب ميزاتها
        فوراً دون انتظار الدورة الدورية الكاملة).
        """
        if self.ws_engine is None:
            return set()
        dirty = self.ws_engine.pop_dirty_closed_symbols()
        changed = set()
        for sym in dirty:
            if sym not in self.cached_data:
                continue
            candle = self.ws_engine.get_closed_candle(sym)
            if not candle:
                continue
            df_new = pd.DataFrame([candle], columns=['ts', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
            df_new = df_new.set_index('ts').astype(float)
            with self.state_lock:
                df_combined = pd.concat([self.cached_data[sym], df_new])
                df_combined = df_combined[~df_combined.index.duplicated(keep='last')].sort_index()
                self.cached_data[sym] = df_combined.tail(self.cfg.N + self.cfg.W + 1000)
            changed.add(sym)
        return changed

    def _recompute_features(self, initial: bool = False, symbols: Optional[List[str]] = None):
        """
        يُرسل مهمة process_asset لكل رمز مطلوب إلى مجمّع العمليات بالتوازي، ثم
        يُحدّث self.assets بدمج النتائج (وليس استبدال القاموس بالكامل عند تمرير
        `symbols` محدد، حفاظاً على بيانات بقية الأصول التي لم تتغيّر هذه الدورة).
        """
        try:
            with self.state_lock:
                cap_snapshot = self.cap_live
            target_syms = symbols if symbols is not None else list(self.top_syms)
            tasks = []
            for sym in target_syms:
                if sym not in self.cached_data:
                    continue
                tasks.append((sym, self.cached_data[sym], self.cached_data_high.get(sym), cap_snapshot))

            if not tasks:
                return

            updated: Dict[str, AssetData] = {}
            futures = {self.process_pool.submit(_feature_worker, t): t[0] for t in tasks}
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    r_sym, ad, err = fut.result()
                    if ad is not None:
                        updated[r_sym] = ad
                    elif err:
                        log.warning(f"  ✗ فشل حساب ميزات {r_sym}: {err}")
                except Exception as e:
                    log.warning(f"  ✗ استثناء عامل الميزات لـ {sym}: {e}")

            if updated:
                if symbols is None:
                    self.assets = updated  # دورة أمان كاملة: تبديل ذرّي تام
                else:
                    new_assets = dict(self.assets)
                    new_assets.update(updated)
                    self.assets = new_assets  # تبديل مرجعي ذرّي (آمن تحت GIL)
                if initial:
                    log.info(f"🧮 تم حساب الميزات الأولية لـ {len(updated)} أصل بالتوازي")
        except Exception as e:
            log.error(f"❌ خطأ في دورة تحديث الميزات: {e}")

    def feature_loop(self):
        """
        [v6.3] حلقة سريعة (كل CLOSED_BAR_FAST_POLL_SECS) تتفاعل فوراً مع أي شمعة
        أُغلقت للتو (زمن استجابة منخفض يُطابق سرعة رد فعل الباك-تيست على إغلاق
        الشمعة)، بالإضافة إلى دورة أمان كاملة أبطأ (FEATURE_REFRESH_SECS) تُعيد
        حساب كل الأصول احتياطاً لأي رسالة WS مفقودة، ومزامنة REST دورية أبطأ.
        """
        last_full = 0.0
        last_ws_check = 0.0
        while not self.stop_event.is_set():
            t0 = time.time()
            try:
                self._refresh_asset_universe_if_due()
                self._rest_resync_if_due()

                changed = self._ingest_closed_candles()
                if changed:
                    self._recompute_features(symbols=list(changed))

                if time.time() - last_full >= self.cfg.FEATURE_REFRESH_SECS:
                    self._recompute_features(symbols=None)
                    last_full = time.time()

                # [إصلاح CONN-2] فحص دوري (كل ~30 ثانية، ليس كل دورة) لاكتشاف
                # اتصال WebSocket "ميت بصمت" — لا onclose يُطلَق لكن لا بيانات
                # تصل فعلياً — وإجباره على إعادة الاتصال بدل ترك السعر اللحظي
                # (المستخدم في فحص SL/TP الفوري) مجمَّداً على قيمة قديمة إلى
                # ما لا نهاية.
                if time.time() - last_ws_check >= 30.0:
                    if self.ws_engine is not None and self.ws_engine.is_stale():
                        self.ws_engine.force_reconnect()
                    last_ws_check = time.time()
            except Exception as e:
                log.error(f"❌ خطأ في feature_loop: {e}")
            elapsed = time.time() - t0
            self.stop_event.wait(max(0.0, self.cfg.CLOSED_BAR_FAST_POLL_SECS - elapsed))

    # ═══════════════════════════ حلقة الارتباط ═══════════════════════════

    def correlation_loop(self):
        while not self.stop_event.is_set():
            self.stop_event.wait(self.cfg.CORRELATION_REFRESH_SECS)
            if self.stop_event.is_set():
                break
            try:
                assets_snapshot = self.assets
                if assets_snapshot:
                    self.corr_cache = precompute_correlations(assets_snapshot)
                    self.last_corr_refresh = time.time()
            except Exception as e:
                log.error(f"❌ خطأ في correlation_loop: {e}")

    # ═══════════════════════════ حلقة تنظيف الأوامر المعلقة ═══════════════════════════

    def pending_janitor_loop(self):
        """
        [إصلاح D2/D24] قبل إلغاء أي أمر معلّق تجاوز عمره PENDING_ORDER_STALE_SECS،
        نستعلم أولاً عن حالته الحقيقية. إن تبيّن أنه امتلأ (كلياً أو جزئياً) قبل
        أن نصل إليه، **لا نتجاهل ذلك** كما كانت تفعل النسخة السابقة (التي كانت
        تُلغي مباشرة وتُفقد أي تعبئة جزئية بصمت) — بل، إن كان أمر دخول
        (purpose='entry')، نُنشئ له مباشرة مركزاً مُداراً بشكل صحيح (SL/TP
        حقيقيان محسوبان من dyn_sl_factor المخزّن وقت الإنشاء)، بدل تركه ليُكتشف
        لاحقاً بلا سياق عبر position_reconcile_loop ويُمنح عندها قيماً وهمية.
        """
        while not self.stop_event.is_set():
            self.stop_event.wait(self.cfg.PENDING_JANITOR_SECS)
            if self.stop_event.is_set():
                break
            try:
                with self.state_lock:
                    stale = [(oid, dict(po)) for oid, po in self.pending_orders.items()
                             if time.time() - po['timestamp'] > self.cfg.PENDING_ORDER_STALE_SECS]

                for order_id, po in stale:
                    sym = po['symbol']
                    purpose = po.get('purpose', 'unknown')
                    filled_amt, avg_price = 0.0, None
                    try:
                        status = self._call(self.exchange.fetch_order, order_id, sym)
                        filled_amt = float(status.get('filled', 0) or 0)
                        avg_price = float(status.get('average') or po.get('price'))
                        if status.get('status') != 'closed':
                            # لا يزال مفتوحاً جزئياً أو كلياً على المنصة: نُلغي البقية فقط
                            try:
                                self._call(self.exchange.cancel_order, order_id, sym)
                            except Exception as e:
                                log.error(f"فشل إلغاء الأمر المعلق {order_id} لـ {sym}: {e}")
                    except Exception as e:
                        # [إصلاح CLEANUP-1 — تسريب pending_orders دائم] `OrderNotFound`
                        # إشارة **نهائية ومؤكدة** من المنصة (الأمر لم يعد موجوداً — إمّا
                        # نُفِّذ بالكامل وأُرشِف، أو أُلغي من خارج البوت)، وليس خطأ عابراً
                        # يستحق إعادة المحاولة. قبل هذا الإصلاح كان أي فشل هنا (بما فيه
                        # هذا الفشل الدائم) يُعيد `continue` ويُبقي السجل في pending_orders
                        # إلى الأبد — يتراكم بصمت عبر أسابيع/أشهر من التشغيل الطويل
                        # ويُعاد الاستعلام عنه كل PENDING_JANITOR_SECS إلى ما لا نهاية
                        # بلا أي تقدّم فعلي. أخطاء أخرى (شبكية/مؤقتة) لا تزال تُعيد
                        # المحاولة في الدورة القادمة كالسابق تماماً.
                        try:
                            import ccxt as _ccxt_janitor
                            is_not_found = isinstance(e, _ccxt_janitor.OrderNotFound)
                        except Exception:
                            is_not_found = False
                        if not is_not_found:
                            is_not_found = "order does not exist" in str(e).lower() or "unknown order" in str(e).lower()
                        if is_not_found:
                            log.warning(f"⚠️ الأمر المعلّق {order_id} لـ {sym} لم يعد موجوداً على "
                                        f"المنصة (نُفِّذ أو أُلغي خارجياً) — إزالته من السجل المحلي "
                                        f"دون افتراض أي تعبئة (ستكتشفه position_reconcile_loop إن "
                                        f"كان قد فتح مركزاً فعلياً).")
                            with self.state_lock:
                                self.pending_orders.pop(order_id, None)
                        else:
                            log.error(f"فشل الاستعلام عن الأمر المعلق {order_id} لـ {sym} قبل التنظيف: {e}")
                        continue

                    with self.state_lock:
                        self.pending_orders.pop(order_id, None)

                    if filled_amt > 0 and purpose == 'entry':
                        action = po.get('action')
                        dyn_sl_factor = float(po.get('dyn_sl_factor', 0.01))
                        entry_price = avg_price or po.get('price')
                        # [إصلاح مصدر الحقيقة الوحيد لسعر الدخول] `avg_price` هنا هو
                        # متوسط تعبئة هذا الأمر المعلّق بمفرده فقط. إن كان هناك مركز
                        # قائم لنفس الرمز بسعر دخول مختلف، فإن المنصة تدمج الاثنين في
                        # `entryPrice` مرجّح بالكمية يختلف عن `avg_price` وحدها. نستعلم
                        # هنا عن `entryPrice` الفعلي من المنصة ونعتمده إن توفر.
                        try:
                            fresh_positions = self._call(self.exchange.fetch_positions, symbols=[sym])
                            for fp in fresh_positions:
                                famt = float(fp['info'].get('positionAmt', 0))
                                if abs(famt) > 0:
                                    fpe = fp.get('entryPrice') or fp.get('info', {}).get('entryPrice')
                                    if fpe:
                                        entry_price = float(fpe)
                                    break
                        except Exception as e:
                            log.warning(f"⚠️ تعذر جلب entryPrice الفعلي من المنصة لـ {sym}: {e} — سيُستخدم متوسط تعبئة الأمر فقط.")
                        log.warning(
                            f"⚠️ أمر دخول معلّق لـ {sym} تبيّن أنه امتلأ ({filled_amt:.6f} @ "
                            f"{entry_price:.4f}) بعد انتهاء مهلة الانتظار — سيُسجَّل كمركز "
                            f"مُدار بشكل صحيح بدل تجاهله.")
                        sl, tp = self._sl_tp_from_signal_like(action, entry_price, dyn_sl_factor)
                        with self.state_lock:
                            existing = self.open_pos_live.get(sym)
                        if existing is not None:
                            # [إصلاح] مركز موجود بالفعل لنفس الرمز (نادر): كان الكود
                            # يجمع الكمية فقط ويترك entry_price/SL/TP القديمة كما هي —
                            # فيبقى الوقف والهدف محسوبين على سعر دخول قديم مختلف عن
                            # `entryPrice` المدمج الحقيقي الذي جلبناه للتو من المنصة.
                            # نُحدّث الكمية وسعر الدخول ونعيد حساب SL/TP من القيم
                            # الحقيقية المحدّثة معاً.
                            with self.state_lock:
                                existing['qty'] = existing.get('qty', 0.0) + filled_amt
                                existing['entry'] = entry_price
                                existing['sl'] = sl
                                existing['tp1'] = tp
                            self._persist()
                        else:
                            self._register_position(sym, action, entry_price, filled_amt, sl, tp)
                    elif filled_amt > 0 and purpose != 'entry':
                        log.info(f"ℹ️ أمر معلّق (purpose={purpose}) لـ {sym} تبيّن أنه امتلأ "
                                 f"{filled_amt:.6f} — سيُترك لدورة مطابقة المراكز للتأكد من الحالة النهائية")
                    else:
                        log.warning(f"🗑️ تم تنظيف أمر معلق لـ {sym} ({purpose}) بلا أي تعبئة")

                    self._persist()
            except Exception as e:
                log.error(f"❌ خطأ في pending_janitor_loop: {e}")

    # ═══════════════════════════ حلقة مطابقة المراكز مع المنصة ═══════════════════════════

    def position_reconcile_loop(self):
        while not self.stop_event.is_set():
            self.stop_event.wait(self.cfg.POSITION_RECONCILE_SECS)
            if self.stop_event.is_set():
                break
            try:
                bal = self._call(self.exchange.fetch_balance)
                self.cap_live = float(bal['USDT']['free'])
                # [إصلاح D-DD2] تحديث قمة رأس المال الحي كي يصبح drawdown قابلاً للحساب.
                # ملاحظة/افتراض صريح (UNVERIFIABLE WITHOUT RUNTIME DATA): نستخدم هنا نفس
                # قيمة 'free' balance المستخدمة أصلاً في تحجيم المراكز عبر الملف كله.
                # هذه القيمة تنخفض أيضاً عند حجز الهامش لمركز جديد (وليس فقط عند الخسارة)،
                # لذا فإن drawdown المحسوب منها قد يتضمن جزءاً من "انخفاض" سببه هامش محجوز
                # لا خسارة فعلية. القياس الأدق هو Total Equity = free + used (margin) +
                # unrealized PnL، لكن هذا يتطلب بيانات إضافية من المنصة (fetch_positions
                # لحساب unrealizedPnl) لم تكن متاحة بشكل موحّد هنا وقت التدقيق.
                self.peak_cap_live = max(self.peak_cap_live, self.cap_live)
            except Exception:
                pass

            try:
                all_positions = self._call(self.exchange.fetch_positions)
                active_amt_by_symbol: Dict[str, float] = {}
                newly_discovered = []
                for pos in all_positions:
                    amt = float(pos['info'].get('positionAmt', 0))
                    if abs(amt) == 0:
                        continue
                    sym_key = _norm_symbol(pos['symbol'])
                    active_amt_by_symbol[sym_key] = amt
                    with self.state_lock:
                        already_tracked = sym_key in self.open_pos_live
                        if not already_tracked:
                            newly_discovered.append((sym_key, amt, float(pos['entryPrice'])))
                        else:
                            local_qty = float(self.open_pos_live[sym_key].get('qty', 0) or 0)
                            actual_qty = abs(amt)
                            if local_qty > 0:
                                rel_diff = abs(actual_qty - local_qty) / max(local_qty, 1e-9)
                                if rel_diff > 0.01:
                                    log.warning(f"⚠️ [تسوية دورية] انحراف كمية لـ {sym_key}: محلي={local_qty:.6f} فعلي={actual_qty:.6f} — تصحيح")
                                    self.open_pos_live[sym_key]['qty'] = actual_qty

                # ── [إصلاح D18] مراكز مُكتشَفة حديثاً: نحاول أولاً "تبنّيها" بسياق
                # حقيقي من سجل أمر معلّق مطابق (entry) قبل اللجوء لأي إجراء آخر.
                for sym_key, amt, entry_price in newly_discovered:
                    action = 'BUY' if amt > 0 else 'SELL'
                    qty = abs(amt)
                    matching_pending = None
                    matching_oid = None
                    with self.state_lock:
                        for oid, po in self.pending_orders.items():
                            if po.get('symbol') == sym_key and po.get('purpose') == 'entry':
                                matching_pending = dict(po)
                                matching_oid = oid
                                break
                    if matching_pending is not None:
                        dyn_sl_factor = float(matching_pending.get('dyn_sl_factor', 0.01))
                        sl, tp = self._sl_tp_from_signal_like(action, entry_price, dyn_sl_factor)
                        log.warning(f"⚠️ مركز {sym_key} اكتُشف على المنصة ويطابق أمر دخول معلّق محفوظ — "
                                    f"سيُسجَّل بمستويات SL/TP حقيقية بدل اعتباره غير معروف.")
                        with self.state_lock:
                            self.pending_orders.pop(matching_oid, None)
                        self._register_position(sym_key, action, entry_price, qty, sl, tp)
                    else:
                        # [إصلاح D18] لا يوجد أي سياق يُفسّر أصل هذا المركز: لا نمنحه
                        # مطلقاً SL=0/TP=0 (كانت تُطلق إغلاقاً فورياً مُصنَّفاً خطأً).
                        # التسوية الآمنة الوحيدة: إغلاقه فوراً بوضوح كإجراء سلامة.
                        self._safe_flatten_unknown(sym_key, action, qty)

                removed = []
                with self.state_lock:
                    for sym_key in list(self.open_pos_live.keys()):
                        if _norm_symbol(sym_key) not in active_amt_by_symbol:
                            log.warning(f"⚠️ المركز {sym_key} موجود في الذاكرة لكنه غير موجود في المنصة — سيتم حذفه")
                            del self.open_pos_live[sym_key]
                            removed.append(sym_key)

                if newly_discovered or removed:
                    self._persist()
                for sym_key in removed:
                    stop_flag = self.guardian_stop.get(sym_key)
                    if stop_flag:
                        stop_flag.set()
            except Exception as e:
                log.error(f"❌ فشل مزامنة المراكز الدورية: {e}")

    # ═══════════════════════════ خيط الحارس (مستقل لكل مركز) ═══════════════════════════

    def _bar_anchored_exit_check(self, sym: str, pos: Dict, ad) -> Tuple[bool, str, float]:
        """
        [إصلاح WS-APEX1 — الإصلاح الجذري لعدم دقة توقيت Apex/Emergency-SL في
        Live/Testnet المُبلَّغ عنه]

        تشخيص السبب الجذري (تم التحقق منه بمقارنة مباشرة مع `_advance` في
        الباك-تيست، السطور ~2525 وما بعدها):

        الباك-تيست يُقيّم `check_thermodynamic_apex` **مرة واحدة بالضبط لكل
        شمعة مغلقة**، باستخدام زوج (سعر إغلاق تلك الشمعة بعينها، ميزاتها هي
        بعينها عند نفس الفهرس fi) — أي أن السعر والميزات متزامنان تماماً دائماً.

        لكن الكود القديم في `_position_guardian` كان يستدعي نفس الدالة **كل
        GUARDIAN_POLL_SECS (=1 ثانية)** طوال عمر المركز، باستخدام السعر
        اللحظي المتذبذب من الـWS (`price`) بينما `fi`/`ad.dF`/`ad.geodesic_accel`
        تبقى مجمّدة على آخر شمعة مغلقة حتى إغلاق التالية. بما أن `pnl` داخل
        `check_thermodynamic_apex` يُحسب من `current_price`، فإن أي تذبذب
        سعري عابر (ضجيج تيك عادي) كان يكفي لعبور `min_profit` لحظياً بينما
        شرط الطاقة (`energy_exhausted`/`accel_mean`) المجمّد من الشمعة
        السابقة لا يزال صحيحاً — فيُطلَق Apex عند أول تذبذب عابر، وليس عند
        إغلاق شمعة فعلي كما في الباك-تيست. هذه بالضبط نفس مشكلة "الاختبارات
        المتعددة على بيانات ضجيجية" التي وثّقها هذا الملف نفسه أعلاه لمشكلة
        الشمعة الشبحية — لكنها انتقلت من جانب الميزات (الذي أُصلح فعلاً) إلى
        جانب السعر/الـpnl (الذي بقي دون إصلاح حتى الآن). كذلك MAX_HOLD_BARS
        لم يكن مُنفَّذاً في Live/Testnet إطلاقاً (تحقق: صفر استخدامات قبل هذا
        الإصلاح)، فكانت المراكز الحية يمكن أن تُحمَل إلى ما لا نهاية خلافاً
        للباك-تيست.

        الحل هنا: نُقيّم Apex/Topo-Div/MaxHold **مرة واحدة بالضبط** عند كل
        شمعة جديدة تُغلَق فعلياً (نكتشف ذلك بمقارنة `ad.timestamps[-1]` بآخر
        طابع زمني قُيِّم سابقاً لهذا الرمز)، وباستخدام `ad.closes[-1]` — أي
        سعر إغلاق تلك الشمعة بعينها، تماماً كالباك-تيست — بدل السعر اللحظي.
        فحص SL/TP يبقى كما هو تماماً (مستمر على كل تيك)، لأنه مطابق فعلياً
        لفحص القمة/القاع داخل الشمعة في الباك-تيست ولم يكن يوماً مصدر المشكلة.

        يُعيد (triggered, reason, exit_price) — لا يُنفّذ أي إغلاق بنفسه.
        """
        if ad is None or len(ad.score) == 0 or len(ad.timestamps) == 0:
            return False, "", 0.0

        bar_ts = ad.timestamps[-1]
        last_seen = self.guardian_last_bar_ts.get(sym)
        if last_seen is not None and bar_ts == last_seen:
            return False, "", 0.0  # لم تُغلَق شمعة جديدة بعد — لا تكرار للتقييم

        self.guardian_last_bar_ts[sym] = bar_ts

        fi = len(ad.score) - 1
        p_close = float(ad.closes[-1])

        is_apex, apex_rsn = check_thermodynamic_apex(pos['action'], pos['entry'], p_close, ad, fi)
        if is_apex:
            return True, apex_rsn, p_close

        if fi > 0 and fi < len(ad.V):
            div_t = (ad.V[fi] - ad.V[fi - 1]) / (ad.V[fi - 1] + 1e-12)
            if div_t > self.cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                return True, f"Topo-Div({div_t:.3f})", p_close

        try:
            entry_ts = pd.Timestamp(pos.get('entry_time'))
            bars_held = int(np.sum(ad.timestamps > entry_ts))
        except Exception:
            bars_held = 0  # [UNVERIFIABLE WITHOUT RUNTIME DATA لو entry_time غائب/تالف] لا نخاطر بإغلاق زائف
        if bars_held > self.cfg.MAX_HOLD_BARS:
            return True, "MaxHold", p_close

        return False, "", 0.0

    def _position_guardian(self, sym: str, stop_flag: threading.Event):
        """
        [v6.3 + إصلاح WS-APEX1] `ad = self.assets.get(sym)` يعكس دائماً آخر
        شمعة *مغلقة* فقط. شروط Apex/Topo-Div/MaxHold (المرتبطة بالشمعة) تُقيَّم
        الآن مرة واحدة بالضبط عند كل إغلاق شمعة فعلي عبر `_bar_anchored_exit_check`
        (طابقاً تماماً لتسلسل أولوية الباك-تيست: Apex→Topo-Div→MaxHold أولاً).
        فحص SL/TP يبقى مستمراً على السعر اللحظي الحقيقي في كل دورة، تماماً
        كفحص القمة/القاع داخل الشمعة في الباك-تيست، ويُقيَّم فقط إن لم يُطلِق
        الفحص المرتبط بالشمعة إغلاقاً في هذه الدورة (نفس ترتيب أولوية `_advance`).
        """
        log.info(f"🛡️ بدء مراقبة {sym} في خيط مستقل")
        while not self.stop_event.is_set() and not stop_flag.is_set():
            try:
                with self.state_lock:
                    pos = self.open_pos_live.get(sym)
                if pos is None:
                    break

                ad = self.assets.get(sym)

                ex, rsn, exit_px = self._bar_anchored_exit_check(sym, pos, ad)

                if not ex:
                    price = self.ws_engine.get_live_price(sym) if self.ws_engine else None
                    if price is None:
                        if ad is not None and len(ad.closes) > 0:
                            price = float(ad.closes[-1])
                        else:
                            stop_flag.wait(self.cfg.GUARDIAN_POLL_SECS)
                            continue

                    if pos['action'] == "BUY":
                        if price <= pos['sl']:
                            ex, rsn, exit_px = True, "Emergency SL", price
                        elif price >= pos.get('tp1', 1e18):
                            ex, rsn, exit_px = True, "Hard TP", price
                    else:
                        if price >= pos['sl']:
                            ex, rsn, exit_px = True, "Emergency SL", price
                        elif price <= pos.get('tp1', 0.):
                            ex, rsn, exit_px = True, "Hard TP", price

                if ex:
                    self._execute_close(sym, pos, exit_px, rsn)
                    with self.state_lock:
                        still_open = sym in self.open_pos_live
                    if not still_open:
                        break

            except Exception as e:
                log.error(f"❌ خطأ في خيط الحارس لـ {sym}: {e}")

            stop_flag.wait(self.cfg.GUARDIAN_POLL_SECS)

        log.info(f"🛡️ إنهاء مراقبة {sym}")
        with self.guardian_lock:
            self.guardian_threads.pop(sym, None)
            self.guardian_stop.pop(sym, None)
        self.guardian_last_bar_ts.pop(sym, None)

    def _execute_close(self, sym: str, pos: Dict, price: float, rsn: str):
        try:
            with self.exchange_sema:
                try:
                    stray = self.exchange.fetch_open_orders(sym)
                    for o in stray:
                        self.exchange.cancel_order(o['id'], sym)
                except Exception as se:
                    log.warning(f"تحذير: فشل تنظيف الأوامر اليتيمة قبل إغلاق {sym}: {se}")

                s = 'sell' if pos['action'] == 'BUY' else 'buy'
                # [جديد] نوع أمر الخروج قابل للتعديل عبر CFG.EXIT_ORDER_TYPE دون
                # أي تأثير على منطق الدخول (يبقى دائماً كما هو عبر
                # execute_quantum_chunks).
                if str(self.cfg.EXIT_ORDER_TYPE).lower() == "market":
                    # [إصلاح EXEC-3 — جذر خطأ -4005] استخدام الغلاف الآمن الذي
                    # يُقسِّم الكمية تلقائياً عند تجاوزها حد MARKET_LOT_SIZE بدل
                    # استدعاء create_market_order مباشرة بكمية واحدة قد تُرفَض
                    # كاملة وتترك المركز بلا حماية حتى التسوية الدورية.
                    filled_qty_close, exec_price, ambiguous_close = execute_market_order_safe(
                        self.exchange, sym, s, pos['qty'], fallback_price=price, reduce_only=True)
                else:
                    filled_qty_close, exec_price, ambiguous_close = execute_quantum_chunks(
                        self.exchange, sym, s, pos['qty'], price, self.pending_orders,
                        order_meta={'purpose': 'exit'}
                    )

            if ambiguous_close:
                log.error(f"⚠️ إغلاق {sym} غامض الحالة — سيُعاد تقييمه عبر التسوية الدورية")
                self._persist()
                return
            if filled_qty_close <= 0:
                log.error(f"❌ فشل إغلاق {sym} — لم يتم تنفيذ أي كمية")
                return

            fully_closed = False
            with self.state_lock:
                cur = self.open_pos_live.get(sym)
                if cur is None:
                    self._persist()
                    return
                if filled_qty_close < cur['qty'] * 0.999:
                    log.warning(f"⚠️ تعبئة جزئية عند إغلاق {sym}: {filled_qty_close:.6f} من {cur['qty']:.6f}")
                    cur['qty'] -= filled_qty_close
                else:
                    del self.open_pos_live[sym]
                    fully_closed = True
            log.info(f"⬛ {sym} إغلاق @ {exec_price:.4f} [{rsn}]")
            self._persist()

            if fully_closed and (self.cfg.EXPORT_TRADES_CSV or self.cfg.EXPORT_TRADE_HTML):
                self._log_closed_trade(sym, pos, filled_qty_close, exec_price, rsn)
        except Exception as e:
            log.error(f"خطأ أثناء الإغلاق لـ {sym}: {e}")

    def _log_closed_trade(self, sym: str, pos: Dict, qty: float, exit_price: float, rsn: str):
        """
        [جديد] يبني سجل Trade من مركز live/testnet المُغلَق للتو ويُصدِّره إلى
        CSV (إلحاق سطر واحد) + رسم Plotly HTML، بنفس مخطط بيانات الباك-تيست
        تماماً. طبقة تقارير بحتة بعد إتمام الإغلاق فعلياً — أي فشل هنا لا يمس
        حالة المركز (مُسجَّل بالفعل قبل هذا الاستدعاء) ولا يُعاد رفعه كخطأ.
        """
        try:
            entry_price = float(pos['entry'])
            action = pos['action']
            entry_time_raw = pos.get('entry_time')
            try:
                entry_time = pd.Timestamp(entry_time_raw) if entry_time_raw else pd.Timestamp.now(tz="UTC")
            except Exception:
                entry_time = pd.Timestamp.now(tz="UTC")
            exit_time = pd.Timestamp.now(tz="UTC")

            if action == "BUY":
                gross = (exit_price - entry_price) * qty
            else:
                gross = (entry_price - exit_price) * qty
            fee = qty * (entry_price + exit_price) * abs(self.cfg.MAKER_FEE)
            net = gross - fee

            indicators = dict(pos.get('entry_indicators') or {})
            indicators["sl_line"] = pos.get('sl')
            indicators["tp_line"] = pos.get('tp1')

            trade = Trade(
                symbol=sym, action=action, entry_price=entry_price, exit_price=exit_price,
                pos_size=qty, gross_pnl=gross, fee=fee, net_pnl=net,
                capital_after=float('nan'), log_return=float('nan'),
                entry_time=entry_time, exit_reason=rsn,
                score=indicators.get("score", float('nan')), lam=float('nan'), liq_warn=False,
                slippage_paid=0.0, entry_optimized=False,
                tri_at_entry=indicators.get("tri", float('nan')),
                dynamic_risk_used=pos.get('dyn_risk', 0.0),
                T_info_at_entry=pos.get('T_info', 0.0),
                exit_time=exit_time, indicators=indicators,
            )

            if self.cfg.EXPORT_TRADES_CSV:
                append_trade_csv_row(trade, self.cfg.TRADES_CSV_PATH)
            if self.cfg.EXPORT_TRADE_HTML:
                ad = self.assets.get(sym)
                fname = f"{exit_time.strftime('%Y%m%d_%H%M%S')}_{sym.replace('/','-').replace(':','-')}.html"
                generate_trade_chart_html(trade, ad, os.path.join(self.cfg.TRADE_HTML_DIR, fname),
                                           self.cfg.TRADE_HTML_CONTEXT_BARS)
        except Exception as e:
            log.warning(f"⚠️ فشل تسجيل تقرير الصفقة المُغلقة لـ {sym} (لا يؤثر على حالة المركز): {e}")

    # ═══════════════════════════ ماسح إشارات الدخول ═══════════════════════════

    def entry_scan_loop(self):
        while not self.stop_event.is_set():
            t0 = time.time()
            try:
                self._scan_and_enter()
            except Exception as e:
                log.error(f"❌ خطأ في entry_scan_loop: {e}")
            elapsed = time.time() - t0
            self.stop_event.wait(max(0.0, self.cfg.ENTRY_SCAN_SECS - elapsed))

    def _scan_and_enter(self):
        cfg = self.cfg
        assets_snapshot = self.assets
        if not assets_snapshot:
            return

        with self.state_lock:
            pend_syms = pending_symbols_set(self.pending_orders)
            open_syms = set(self.open_pos_live.keys())
            in_flight = len(open_syms) + len(pend_syms - open_syms)

        if in_flight >= cfg.MAX_CONCURRENT_ASSETS:
            return

        try:
            bal = self._call(self.exchange.fetch_balance)
            self.cap_live = float(bal['USDT']['free'])
            self.peak_cap_live = max(self.peak_cap_live, self.cap_live)  # [إصلاح D-DD2]
        except Exception:
            pass
        cap_live = self.cap_live

        # [إصلاح D-DD1/D-DD2] قاطع دائرة + مضاعِف مخاطرة الانخفاض في المسار الحي،
        # ليصبح مطابقاً فعلياً لسلوك الباك-تيست (كان غائباً تماماً قبل هذا التدقيق).
        drawdown_live = (self.peak_cap_live - cap_live) / (self.peak_cap_live + 1e-12)
        if _drawdown_halted(drawdown_live, cfg):
            log.warning(f"⛔ تجاوز الانخفاض الحد الأقصى ({drawdown_live*100:.1f}% ≥ "
                        f"{cfg.MAX_DRAWDOWN_HALT*100:.0f}%) — إيقاف فتح صفقات جديدة مؤقتاً.")
            return
        dd_mult_live = _get_risk_multiplier(drawdown_live, cfg)

        sigs = deduplicate_signals(build_signals(assets_snapshot, mode=cfg.mode))
        sigs_ranked = sorted(sigs, key=lambda s: (s.score, s.dynamic_risk), reverse=True)

        for sig in sigs_ranked:
            sym = sig.symbol
            with self.state_lock:
                if _norm_symbol(sym) in self.open_pos_live or _norm_symbol(sym) in pending_symbols_set(self.pending_orders):
                    continue
                open_syms = set(self.open_pos_live.keys())
                pend_syms = pending_symbols_set(self.pending_orders)
                in_flight = len(open_syms) + len(pend_syms - open_syms)
            if in_flight >= cfg.MAX_CONCURRENT_ASSETS:
                break

            if any(abs(self.corr_cache.get((sym, s), 0)) > cfg.CORRELATION_THRESHOLD for s in open_syms):
                continue

            lmt = sig.price
            delta = abs(lmt - sig.sl)
            if delta < 1e-8 or delta < 0.001 * lmt:
                continue
            if cap_live <= cfg.CAPITAL_FLOOR + 0.1:
                continue

            if cfg.SINGULARITY_MODE:
                risk_amt = cap_live * sig.dynamic_risk
            else:
                free_ratio_live = max(0.0, (cap_live - cfg.CAPITAL_FLOOR) / cap_live)
                power_law_scale = np.sqrt(free_ratio_live)
                # [إصلاح D-DD2] كان dd_mult_live مفقوداً هنا مقارنة بالباك-تيست (§15، حيث
                # تُضرَب dynamic_risk * dd_mult * power_law_scale) — أي أن الحساب الحي كان
                # يخاطر بنفس الحجم بغض النظر عن أي انخفاض جارٍ، خلافاً للباك-تيست تماماً.
                risk = float(np.clip(sig.dynamic_risk * dd_mult_live * power_law_scale,
                                      cfg.MIN_RISK, cfg.MAX_RISK))
                risk_amt = (cap_live - cfg.CAPITAL_FLOOR) * risk

            qty_risk_based = risk_amt / delta
            dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)
            max_notional = cap_live * dynamic_leverage
            qty_leverage_based = max_notional / lmt
            qty = min(qty_risk_based, qty_leverage_based)
            if qty * lmt < cfg.MIN_NOTIONAL:
                continue

            live_candle_now = self.ws_engine.get_live_candle(sym) if self.ws_engine else None
            if live_candle_now is not None:
                live_high, live_low = live_candle_now[2], live_candle_now[3]
                if sig.action == "BUY" and live_high >= sig.tp1:
                    continue
                if sig.action == "SELL" and live_low <= sig.tp1:
                    continue

            self._try_enter(sym, sig, qty, lmt, dynamic_leverage)

    def _try_enter(self, sym, sig, qty, lmt, dynamic_leverage):
        cfg = self.cfg
        try:
            sym = _norm_symbol(sym)
            sd = 'buy' if sig.action == 'BUY' else 'sell'

            with self.exchange_sema:
                try:
                    self.exchange.set_margin_mode('isolated', sym)
                except Exception:
                    pass
                try:
                    self.exchange.set_leverage(dynamic_leverage, sym)
                except Exception as e:
                    log.warning(f"⚠️ فشل ضبط الرافعة لـ {sym}: {e}")
                try:
                    open_orders = self.exchange.fetch_open_orders(sym)
                    if open_orders:
                        log.info(f"⚠️ توجد {len(open_orders)} أوامر مفتوحة على {sym} — سيتم إلغاؤها قبل الدخول")
                        for o in open_orders:
                            self.exchange.cancel_order(o['id'], sym)
                except Exception as e:
                    log.warning(f"تحذير: فشل مسح الأوامر السابقة لـ {sym}: {e}")

                # [إصلاح D17/D23] نُمرّر سياق الإشارة الكافي (action + dyn_sl_factor)
                # ليُخزَّن مع أي سجل أمر معلّق يبقى من هذه المحاولة، بحيث لو تأخرت
                # التعبئة أو غمضت حالتها، يستطيع الجهاز الدوري (janitor) أو مطابقة
                # المراكز "تبنّي" النتيجة بمستويات SL/TP حقيقية بدل قيم وهمية.
                #
                # [جديد] نوع أمر الدخول قابل للتعديل عبر CFG.ENTRY_ORDER_TYPE دون
                # أي تأثير على منطق الخروج (منفصل تماماً عبر EXIT_ORDER_TYPE).
                # الافتراضي "limit" يُبقي السلوك الأصلي (execute_quantum_chunks
                # الكمومي التكتيكي) كما هو تماماً — صفر تغيير إن لم تُهيّئه.
                if str(cfg.ENTRY_ORDER_TYPE).lower() == "market":
                    # [إصلاح EXEC-3] نفس الغلاف الآمن المُقسِّم لتلافي -4005 عند
                    # مراكز دخول كبيرة أيضاً (نفس منطق الخروج، معكوس الاتجاه).
                    filled_qty, entry_price, ambiguous_entry = execute_market_order_safe(
                        self.exchange, sym, sd, qty, fallback_price=lmt)
                    # للدخول تحديداً: نُعامل حتى الحالة "الغامضة شبكياً" كإلغاء
                    # نظيف هنا (لا نعيد المحاولة فوراً) بدل تعليق التنفيذ —
                    # الحالة النادرة جداً التي يكون فيها الأمر قد نُفِّذ فعلياً
                    # على المنصة رغم فشل استلام الرد سيلتقطها لاحقاً تلقائياً
                    # `position_reconcile_loop` (يكتشف أي مركز فعلي غير مُسجَّل
                    # محلياً ويُسجِّله بسعر الدخول الحقيقي من المنصة) — فلا يبقى
                    # المركز يتيماً بلا SL/TP.
                    ambiguous_entry = False
                else:
                    filled_qty, entry_price, ambiguous_entry = execute_quantum_chunks(
                        self.exchange, sym, sd, qty, lmt, self.pending_orders,
                        order_meta={'purpose': 'entry', 'action': sig.action,
                                    'dyn_sl_factor': sig.dyn_sl_factor}
                    )

            if ambiguous_entry:
                log.error(f"⚠️ دخول {sym} غامض الحالة — سيُعاد تقييمه عبر التسوية الدورية "
                          f"(سياق الإشارة محفوظ لتُدار بمستويات صحيحة عند الحل)")
                self._persist()
                return
            if filled_qty <= 0 or entry_price <= 0:
                log.warning(f"❌ لم يتم تنفيذ دخول {sym} — تم الإلغاء")
                return
            qty = filled_qty

            with self.exchange_sema:
                try:
                    positions = self.exchange.fetch_positions(symbols=[sym])
                    actual_pos = None
                    amt = 0.0
                    for p in positions:
                        amt = float(p['info'].get('positionAmt', 0))
                        if abs(amt) > 0:
                            actual_pos = p
                            break
                    if actual_pos is None:
                        log.warning(f"⚠️ لم يتكوّن مركز فعلي لـ {sym} رغم التنفيذ — ربما أمر Limit لم يُنفذ بالكامل")
                        try:
                            for o in self.exchange.fetch_open_orders(sym):
                                self.exchange.cancel_order(o['id'], sym)
                        except Exception:
                            pass
                        return
                    qty = abs(amt)
                    # [إصلاح مصدر الحقيقة الوحيد لسعر الدخول] كان الكود يأخذ
                    # الكمية فقط من `fetch_positions` ويُبقي على `entry_price`
                    # المحسوب محلياً (متوسط تعبئة `execute_quantum_chunks`)
                    # لتسجيل المركز وحساب SL/TP — رغم أن المنصة توفّر هنا
                    # مباشرة `entryPrice` الحقيقي والنهائي للمركز الإجمالي
                    # (يراعي أي تعبئة جزئية متأخرة فاتت الحساب المحلي). الآن
                    # نأخذ سعر الدخول من المنصة كمصدر حقيقة وحيد، ونستخدم
                    # القيمة المحلية فقط كخط رجوع احتياطي إن غاب حقل المنصة.
                    platform_entry = None
                    try:
                        pe = actual_pos.get('entryPrice')
                        if not pe:
                            pe = actual_pos.get('info', {}).get('entryPrice')
                        platform_entry = float(pe) if pe else None
                    except Exception:
                        platform_entry = None
                    if platform_entry and platform_entry > 0:
                        if abs(platform_entry - entry_price) / entry_price > 0.0005:
                            log.warning(f"⚠️ سعر الدخول المحلي ({entry_price:.4f}) يختلف عن سعر "
                                        f"المنصة ({platform_entry:.4f}) لـ {sym} — سيُعتمد سعر المنصة.")
                        entry_price = platform_entry
                    log.info(f"✅ مركز مؤكد على {sym} بكمية {qty} | سعر الدخول (منصة)={entry_price:.4f}")
                except Exception as e:
                    log.warning(f"⚠️ تعذر جلب المراكز لـ {sym}: {e}")
                    try:
                        for o in self.exchange.fetch_open_orders(sym):
                            self.exchange.cancel_order(o['id'], sym)
                    except Exception:
                        pass
                    return

            # [تنظيف] استُخدم CFG العامة هنا بدل self.cfg رغم وجود `cfg = self.cfg` محلياً
            # (لاحظه pyflakes: F841 متغير غير مستخدم). لا يُنتج هذا فرقاً في التشغيل الحالي
            # لأن main() يمرر نفس الكائن العام دوماً (CFG هو self.cfg بالمرجع)، لكنه هش:
            # أي استخدام مستقبلي لعدة إعدادات مختلفة في نفس العملية سيكسر هذا بصمت.
            if qty * entry_price < cfg.MIN_NOTIONAL:
                log.warning(f"❌ قيمة المركز الفعلية أقل من الحد الأدنى ({qty * entry_price:.2f} < {cfg.MIN_NOTIONAL})")
                with self.exchange_sema:
                    execute_quantum_chunks(self.exchange, sym, 'sell' if sd == 'buy' else 'buy', qty, entry_price,
                                            order_meta={'purpose': 'safety_flatten'})
                return

            actual_sl, actual_tp = self._sl_tp_from_signal_like(sig.action, entry_price, sig.dyn_sl_factor)

            self._register_position(sym, sig.action, entry_price, qty, actual_sl, actual_tp,
                                     T_info_val=sig.T_info_val, dyn_risk=sig.dynamic_risk)
            log.info(f"✅ {sig.action} {sym} @ {entry_price:.4f} | SL={actual_sl:.4f} TP={actual_tp:.4f} "
                     f"T={sig.T_info_val:.3f} L={dynamic_leverage}x")

        except Exception as e:
            log.error(f"خطأ أثناء الدخول لـ {sym}: {e}")

    # ═══════════════════════════ التشغيل الرئيسي ═══════════════════════════

    def run(self):
        log.info(f"🔴 [{self.cfg.mode.upper()}] بدء التشغيل اللحظي v6.3 (شموع مغلقة فقط + دفتر كمية)")
        self.load_state()
        self.reconcile_startup()
        self.bootstrap()

        loops = [
            ("FeatureLoop", self.feature_loop),
            ("CorrelationLoop", self.correlation_loop),
            ("PendingJanitor", self.pending_janitor_loop),
            ("PositionReconcile", self.position_reconcile_loop),
            ("EntryScanner", self.entry_scan_loop),
        ]
        for name, fn in loops:
            t = threading.Thread(target=fn, name=name, daemon=True)
            t.start()
            self.threads.append(t)

        log.info("🚀 كل الخيوط تعمل الآن: شموع مغلقة فقط تُغذّي القرار الاستراتيجي، "
                 "والسعر اللحظي يُغذّي فقط فحص الوقف/الهدف — مطابقة كاملة لعقد الباك-تيست.")

        try:
            while not self.stop_event.is_set():
                time.sleep(1.0)
        except KeyboardInterrupt:
            log.info("تم إيقاف الروبوت يدوياً.")
        finally:
            self.shutdown()

    def shutdown(self):
        self.stop_event.set()
        for stop_flag in list(self.guardian_stop.values()):
            stop_flag.set()
        if self.ws_engine:
            self.ws_engine.stop()
        for t in self.threads:
            t.join(timeout=5)
        for t in list(self.guardian_threads.values()):
            t.join(timeout=5)
        self.process_pool.shutdown(wait=True, cancel_futures=True)
        self._persist()
        log.info("⏹️ تم إيقاف محرك التداول الحي بأمان.")


def run_live(cfg, exchange):
    """نقطة الدخول المتوافقة مع الواجهة القديمة: تُنشئ محرك v6.3 وتُشغّله."""
    engine = LiveEngine(cfg, exchange)
    engine.run()


# ════════════════════════════════════════════════════════════════
# § 20  نقطة الدخول
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Quantum Thermo Trader v6.3")
    p.add_argument("--mode",        default="backtest", choices=["backtest","testnet","live"])
    p.add_argument("--api-key",     default=os.environ.get("BINANCE_API_KEY",""))
    p.add_argument("--api-secret",  default=os.environ.get("BINANCE_API_SECRET",""))
    p.add_argument("--capital",     type=float, default=None)
    p.add_argument("--base-risk",   type=float, default=None)
    p.add_argument("--max-risk",    type=float, default=None)
    p.add_argument("--min-risk",    type=float, default=None)
    p.add_argument("--lambda-k",    type=float, default=None)
    p.add_argument("--leverage",    type=int,   default=None)
    p.add_argument("--sl-factor",   type=float, default=None)
    p.add_argument("--min-score",   type=int,   default=None)
    p.add_argument("--max-hold",    type=int,   default=None)
    p.add_argument("--topo-div",    type=float, default=None)
    p.add_argument("--cosm-const",  type=float, default=None)
    p.add_argument("--k-min",       type=int,   default=None)
    p.add_argument("--k-max",       type=int,   default=None)
    p.add_argument("--nassets",     type=int, default=None)
    p.add_argument("--maxcon",     type=int, default=None)
    p.add_argument("--entry-order-type", default=None, choices=["limit", "market"],
                    help="نوع أمر الدخول في live/testnet (افتراضي: limit)")
    p.add_argument("--exit-order-type", default=None, choices=["limit", "market"],
                    help="نوع أمر الخروج/الإغلاق في live/testnet (افتراضي: limit)")
    p.add_argument("--no-trades-csv", action="store_true", help="تعطيل تصدير الصفقات إلى CSV")
    p.add_argument("--no-trade-html", action="store_true", help="تعطيل رسوم Plotly HTML للصفقات")
    p.add_argument("--trades-csv-path", default=None, help="مسار ملف CSV للصفقات")
    p.add_argument("--trade-html-dir",  default=None, help="مجلد حفظ رسوم HTML للصفقات")
    p.add_argument("--singularity", action="store_true", help="تفعيل بروتوكول التفرد التراكمي (غير مستخدم حالياً)")
    # [إصلاح OPS-1] اختياري بالكامل (معطَّل افتراضياً — صفر تغيير سلوكي): يُضيف
    # ملف سجل دوّار (Rotating) بجانب مخرجات stdout الحالية دون إزالتها، مفيد
    # لمن يشغّل البوت مباشرة (بدون مُشرِف عمليات كـ systemd/docker يلتقط
    # stdout بنفسه أصلاً) عبر جلسات تشغيل طويلة الأمد — يمنع نمو ملف سجل واحد
    # بلا حدود عبر أسابيع/أشهر (10MB لكل ملف × 5 نسخ احتياطية كحد أقصى).
    p.add_argument("--log-file", default=None,
                    help="مسار ملف سجل دوّار اختياري (بالإضافة لـ stdout الحالي، لا يستبدله)")
    args = p.parse_args()

    if args.log_file:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(args.log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(fh)
        log.info(f"📝 سجل إضافي دوّار مفعَّل: {args.log_file} (10MB × 5 نسخ)")

    CFG.mode = args.mode
    CFG.api_key = args.api_key
    CFG.api_secret = args.api_secret
    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital
    if args.base_risk is not None: CFG.BASE_RISK = args.base_risk; CFG.RISK_PER_TRADE = args.base_risk
    if args.max_risk  is not None: CFG.MAX_RISK  = args.max_risk
    if args.min_risk  is not None: CFG.MIN_RISK  = args.min_risk
    if args.lambda_k  is not None: CFG.LAMBDA_KELLY = args.lambda_k
    if args.leverage  is not None: CFG.LEVERAGE  = args.leverage
    if args.sl_factor is not None: CFG.SL_FACTOR = args.sl_factor
    if args.min_score is not None: CFG.MIN_SCORE = args.min_score
    if args.max_hold  is not None: CFG.MAX_HOLD_BARS = args.max_hold
    if args.topo_div  is not None: CFG.TOPO_DIV_THRESHOLD = args.topo_div
    if args.cosm_const is not None: CFG.COSMOLOGICAL_CONSTANT = args.cosm_const
    if args.k_min     is not None: CFG.K_MIN = args.k_min
    if args.k_max     is not None: CFG.K_MAX = args.k_max
    if args.nassets   is not None: CFG.n_assets = args.nassets
    if args.maxcon   is not None: CFG.MAX_CONCURRENT_ASSETS = args.maxcon
    if args.entry_order_type is not None: CFG.ENTRY_ORDER_TYPE = args.entry_order_type
    if args.exit_order_type is not None: CFG.EXIT_ORDER_TYPE = args.exit_order_type
    if args.no_trades_csv: CFG.EXPORT_TRADES_CSV = False
    if args.no_trade_html: CFG.EXPORT_TRADE_HTML = False
    if args.trades_csv_path is not None: CFG.TRADES_CSV_PATH = args.trades_csv_path
    if args.trade_html_dir  is not None: CFG.TRADE_HTML_DIR  = args.trade_html_dir
    if args.singularity:
        CFG.SINGULARITY_MODE = True
        CFG.timeframe = '1m'
        CFG.TOPO_DIV_THRESHOLD = 0.02
        CFG.MAX_HOLD_BARS = 60

    if CFG.MIN_RISK > CFG.MAX_RISK:
        log.error(f"❌ إعداد غير صالح: MIN_RISK({CFG.MIN_RISK}) > MAX_RISK({CFG.MAX_RISK}) — سيتم التبديل تلقائياً")
        CFG.MIN_RISK, CFG.MAX_RISK = CFG.MAX_RISK, CFG.MIN_RISK

    print("╔"+"═"*70+"╗")
    print("║  محرك التداول الثرموديناميكي الكمي v6.3                          ║")
    print(f"║  الوضع: {CFG.mode.upper():10s}  |  رأس المال: ${CFG.INITIAL_CAPITAL:.2f}              ║")
    print("╠"+"═"*70+"╣")
    print(f"║  ① Boltzmann Kelly: BASE={CFG.BASE_RISK*100:.1f}%  λ={CFG.LAMBDA_KELLY}  [{CFG.MIN_RISK*100:.2f}%–{CFG.MAX_RISK*100:.1f}%]  ║")
    print(f"║  ② Topo-Divergence: ε={CFG.TOPO_DIV_THRESHOLD}  (حتمية هندسية)              ║")
    print(f"║  ③ Dynamic-K:       [{CFG.K_MIN}–{CFG.K_MAX}]  (SNR ∝ 1/m)                     ║")
    print(f"║  ④ Cosmological Λ:  {CFG.COSMOLOGICAL_CONSTANT}  (De Sitter drift)                  ║")
    print(f"║  ⑥ Drawdown Halt:   ≥{CFG.MAX_DRAWDOWN_HALT*100:.0f}% إيقاف كامل  (كان غير مُفعَّل قبل التدقيق) ║")
    print("║  ⑤ T_sync EMA-accel: فلتر التشابك عبر المقاييس                  ║")
    print("╚"+"═"*70+"╝\n")

    if CFG.mode == "backtest":
        run_backtest(CFG)
        return

    try:
        import ccxt
    except ImportError:
        log.error("pip install ccxt")
        return

    if not CFG.api_key or not CFG.api_secret:
        log.error("--api-key و --api-secret مطلوبان للتداول الحي")
        return

    exchange = ccxt.binance({
        'apiKey': CFG.api_key,
        'secret': CFG.api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    if CFG.mode == "testnet":
        exchange.enable_demo_trading(True)

    run_live(CFG, exchange)

if __name__=="__main__":
    main()


