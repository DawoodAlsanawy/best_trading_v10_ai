import json
import math

def analyze_log(filepath):
    trades = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                # تخطي سطر الميتا داتا
                if data.get('_meta'): continue
                trades.append(data)
    except FileNotFoundError:
        print(f"❌ لم يتم العثور على الملف: {filepath}")
        return

    if not trades:
        print("❌ لا توجد صفقات في الملف.")
        return

    # --- الحسابات الإحصائية ---
    total_trades = len(trades)
    wins = [t for t in trades if t.get('net_pnl', 0) > 0]
    losses = [t for t in trades if t.get('net_pnl', 0) <= 0]
    
    win_rate = (len(wins) / total_trades) * 100
    
    # حساب الخسائر المتتالية (Losing Streak)
    max_losing_streak = 0
    current_streak = 0
    for t in trades:
        if t.get('net_pnl', 0) <= 0:
            current_streak += 1
            if current_streak > max_losing_streak:
                max_losing_streak = current_streak
        else:
            current_streak = 0

    # مسافة الوقف (SL Distance %)
    sl_distances = [t.get('sl_dist_frac', 0) * 100 for t in trades if t.get('sl_dist_frac')]
    avg_sl_pct = sum(sl_distances) / len(sl_distances) if sl_distances else 0
    max_sl_pct = max(sl_distances) if sl_distances else 0
    min_sl_pct = min(sl_distances) if sl_distances else 0

    # القيمة الاسمية (Notional Size)
    notionals = [t.get('entry_price', 0) * t.get('pos_size', 0) for t in trades]
    avg_notional = sum(notionals) / len(notionals) if notionals else 0

    # تحليل أسباب الخروج
    exit_reasons = {}
    for t in trades:
        reason = str(t.get('exit_reason', 'Unknown')).split('(')[0].strip()
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    # --- طباعة التقرير ---
    print("\n" + "="*50)
    print(" 📊 تحليل بيانات الباكتيست لتحدي الـ 1 دولار ")
    print("="*50)
    print(f"🔹 إجمالي الصفقات      : {total_trades}")
    print(f"🔹 نسبة النجاح (Win%)  : {win_rate:.2f}%")
    print(f"🔹 أقصى خسائر متتالية : {max_losing_streak} صفقات خاسرة متتالية")
    print("-" * 50)
    print(f"⚠️ متوسط مسافة الوقف (SL) : {avg_sl_pct:.3f}% من السعر")
    print(f"⚠️ أوسع مسافة وقف (Max)   : {max_sl_pct:.3f}% من السعر")
    print(f"⚠️ أضيق مسافة وقف (Min)   : {min_sl_pct:.3f}% من السعر")
    print("-" * 50)
    print(f"💰 متوسط حجم الصفقة (Notional): ${avg_notional:.2f}")
    print("-" * 50)
    print("🚪 أسباب الخروج:")
    for r, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
        print(f"   - {r}: {count} صفقة ({count/total_trades*100:.1f}%)")
    print("="*50)

if __name__ == "__main__":
    analyze_log("trades_log_backtest.jsonl")
