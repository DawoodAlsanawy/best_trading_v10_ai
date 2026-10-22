import os

TARGET_FILE = "trading_2_live4_v2_GTX.py"

def main():
    print("=" * 60)
    print(" 🛠️  QTT Bot Auto-Fixer - Cleaning up the code")
    print("=" * 60)

    if not os.path.exists(TARGET_FILE):
        print(f"[ERROR] File '{TARGET_FILE}' not found in the current directory.")
        return

    # قراءة الكود الأصلي
    with open(TARGET_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    original_length = len(lines)
    print(f"[*] Read {original_length} lines from {TARGET_FILE}")

    # 1️⃣ الإصلاح الأول: حذف الكود المكرر في نهاية الملف
    end_idx = -1
    for i in range(len(lines)):
        if "if __name__" in lines[i] and "__main__" in lines[i]:
            # البحث عن استدعاء الدالة main() مباشرة تحتها
            for j in range(i, min(i + 5, len(lines))):
                if "main()" in lines[j]:
                    end_idx = j
                    break
            if end_idx != -1:
                break
    
    if end_idx != -1 and end_idx < len(lines) - 5: # إذا كان هناك كود طويل بعد النهاية
        lines = lines[:end_idx + 1]
        print(f"[OK] ✔️ Removed duplicate code (Truncated to {len(lines)} lines).")
    else:
        print("[INFO] No duplicate code found at the end.")

    # 2️⃣ الإصلاح الثاني: حذف البلوك الهجومي القديم (Leftover)
    # سنبحث عن سجل الدخول القديم "[Reversal-Aggressive]" (الكود الجديد يستخدم [Rev-Aggressive])
    bad_marker_idx = -1
    for i, line in enumerate(lines):
        if "[Reversal-Aggressive]" in line:
            bad_marker_idx = i
            break
            
    if bad_marker_idx != -1:
        start_del = -1
        # الصعود للأعلى للعثور على بداية الـ try
        for i in range(bad_marker_idx, -1, -1):
            if lines[i].strip() == "try:":
                start_del = i
                break
                
        end_del = -1
        # النزول للأسفل للعثور على نهاية البلوك عند حفظ البيانات
        for i in range(bad_marker_idx, len(lines)):
            if "save_reversal_watchers()" in lines[i]:
                end_del = i
                break
                
        if start_del != -1 and end_del != -1:
            del lines[start_del : end_del + 1]
            print("[OK] ✔️ Removed leftover aggressive execution block perfectly.")
        else:
            print("[WARNING] Found the marker but couldn't find bounds to delete.")
    else:
        print("[INFO] Leftover aggressive block not found (might be fixed already).")

    # حفظ الملف بعد التعديل
    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    print(f"\n[SUCCESS] File repaired! New size: {len(lines)} lines.")
    print("=" * 60)
    print("🚀 You can now run your bot safely!")

if __name__ == "__main__":
    main()
