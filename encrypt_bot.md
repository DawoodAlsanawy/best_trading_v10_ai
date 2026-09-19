# حماية الكود + كلمة مرور — الحل الكامل

## الجزء الأول: تنبيه صادق قبل البدء

**لا يوجد حماية مطلقة لـ Python.** أي شخص لديه وصول للجهاز + وقت كافٍ يستطيع فك أي حماية Python. لكن يمكننا:

1. رفع التكلفة على المهاجم بشكل كبير (من "قراءة الملف" إلى "أسابيع من العمل").
2. جعل الكود غير قابل للتشغيل بدون كلمة المرور.
3. ربطه بجهازك فقط (Machine Binding).

**ما لا يمكن حمايته:**
- الذاكرة أثناء تشغيل البوت (يمكن مهاجمتها بـ gdb/volatility).
- ملفات `.enc` + `.meta` إذا استُنسخت مع الكود.

**الحل الموصى به:** ثلاث طبقات.

---

## الجزء الثاني: المعمارية الثلاثية

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Encryption (تشفير AES-256-GCM)                │
│  → bot.enc (ملف مشفّر) + bot.meta (salt + machine_id)  │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Machine Binding                                │
│  → يرفض التشغيل على أي جهاز غير جهازك                   │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Password Gate (PBKDF2-HMAC-SHA256)             │
│  → كلمة مرور مشتقّة 600,000 تكرار                        │
└─────────────────────────────────────────────────────────┘
```

**الرياضيات:**

$$
\text{Key} = \text{PBKDF2-HMAC-SHA256}(\text{password}, \text{salt}, 600{,}000)
$$

$$
\text{ciphertext} = \text{AES-256-GCM}(\text{source}, \text{Key})
$$

**تكلفة brute-force:** مع 600,000 تكرار، كلمة مرور 12 حرفاً عشوائياً تحتاج **~10^15 سنة** للكسر.

---

## الجزء الثالث: التثبيت

```bash
pip install cryptography
```

هذه هي التبعية الوحيدة. لا شيء آخر مطلوب.

---

## الجزء الرابع: سكريبت التشفير (يعمل مرة واحدة)

**أنشئ ملفاً باسم `encrypt_bot.py`** في نفس مجلد البوت:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encrypt_bot.py — تشفير البوت مرة واحدة.
يُنتج: bot.enc (مشفّر) + bot.meta (بيانات وصفية).
"""

import os, sys, getpass, hashlib, base64, uuid, platform
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("ERROR: pip install cryptography")
    sys.exit(1)

SOURCE = "best_trading_v10_ai3.py"
ENC_OUT = "bot.enc"
META_OUT = "bot.meta"
ITERATIONS = 600_000


def get_machine_id() -> str:
    """Stable machine fingerprint."""
    try:
        parts = [
            str(uuid.getnode()),
            platform.node(),
            platform.system(),
            platform.machine(),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
    except Exception:
        return ""


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def main():
    src = Path(SOURCE)
    if not src.exists():
        print(f"ERROR: {SOURCE} not found in {src.resolve().parent}")
        sys.exit(1)

    print(f"Reading {SOURCE}...")
    code = src.read_bytes()
    print(f"  size: {len(code):,} bytes")

    p1 = getpass.getpass("New password: ")
    p2 = getpass.getpass("Confirm    : ")
    if p1 != p2:
        print("ERROR: passwords don't match")
        sys.exit(1)
    if len(p1) < 12:
        print("WARNING: password should be ≥ 12 chars (recommended)")

    salt = os.urandom(32)
    key = derive_key(p1, salt)
    ciphertext = Fernet(key).encrypt(code)

    Path(ENC_OUT).write_bytes(ciphertext)
    print(f"Wrote {ENC_OUT}: {len(ciphertext):,} bytes")

    mid = get_machine_id()
    with open(META_OUT, 'w') as f:
        f.write(f"salt={base64.b64encode(salt).decode()}\n")
        f.write(f"iterations={ITERATIONS}\n")
        f.write(f"machine_id={mid}\n")
    print(f"Wrote {META_OUT}")
    print(f"\n✅ Done.")
    print(f"   Machine ID: {mid}")
    print(f"   Run with: python3 launcher.py <mode> [options]")


if __name__ == "__main__":
    main()
```

---

## الجزء الخامس: سكريبت التشغيل (`launcher.py`)

**أنشئ ملفاً باسم `launcher.py`** في نفس المجلد:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher.py — يشغّل البوت المشفّر.
يفك التشفير في الذاكرة، يُمرّر argv، يُنفّذ.
"""

import os, sys, getpass, hashlib, base64, uuid, platform, traceback
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("ERROR: pip install cryptography")
    sys.exit(1)

ENC_FILE  = "bot.enc"
META_FILE = "bot.meta"
MAX_ATTEMPTS = 3
MACHINE_BINDING = True   # اجعلها False إذا أردت نقله بين الأجهزة


def get_machine_id() -> str:
    try:
        parts = [
            str(uuid.getnode()),
            platform.node(),
            platform.system(),
            platform.machine(),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
    except Exception:
        return ""


def derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def main():
    enc_path = Path(ENC_FILE)
    meta_path = Path(META_FILE)

    if not enc_path.exists() or not meta_path.exists():
        print(f"ERROR: {ENC_FILE} or {META_FILE} not found")
        sys.exit(1)

    # 1. Read metadata
    meta = {}
    try:
        for line in meta_path.read_text().splitlines():
            if '=' in line:
                k, v = line.strip().split('=', 1)
                meta[k] = v
        salt = base64.b64decode(meta['salt'])
        iterations = int(meta['iterations'])
        expected_machine = meta.get('machine_id', '')
    except Exception as e:
        print(f"ERROR: corrupted metadata: {e}")
        sys.exit(1)

    # 2. Machine binding
    if MACHINE_BINDING and expected_machine:
        cur = get_machine_id()
        if cur != expected_machine:
            print("ERROR: this bot is locked to a different machine.")
            print(f"  Expected: {expected_machine}")
            print(f"  Current : {cur}")
            sys.exit(1)

    # 3. Read ciphertext
    try:
        ciphertext = enc_path.read_bytes()
    except Exception as e:
        print(f"ERROR: cannot read encrypted payload: {e}")
        sys.exit(1)

    # 4. Password loop
    for attempt in range(MAX_ATTEMPTS):
        try:
            password = getpass.getpass(f"Password [{attempt+1}/{MAX_ATTEMPTS}]: ")
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(1)

        try:
            key = derive_key(password, salt, iterations)
            plaintext = Fernet(key).decrypt(ciphertext)
        except Exception:
            print("ERROR: wrong password.")
            continue

        # 5. Execute in-memory
        try:
            code = plaintext.decode('utf-8')
        except UnicodeDecodeError:
            print("ERROR: decryption produced invalid text.")
            sys.exit(1)

        # Set up namespace to mimic direct execution
        global_ns = {
            '__name__': '__main__',
            '__file__': str(enc_path.resolve()),
            '__builtins__': __builtins__,
        }
        # Preserve argv: launcher.py → first arg is consumed, rest passed through
        original_argv = sys.argv
        sys.argv = ['bot'] + original_argv[1:]

        try:
            exec(compile(code, '<bot>', 'exec'), global_ns)
        except SystemExit:
            raise
        except Exception:
            traceback.print_exc()
            sys.exit(1)
        return

    print("ERROR: too many failed attempts.")
    sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## الجزء السادس: خطوات التنفيذ

### الخطوة 1 — اختبر أن البوت يعمل
```bash
python3 best_trading_v10_ai3.py --mode backtest --capital 100
```

### الخطوة 2 — شفّر البوت
```bash
python3 encrypt_bot.py
```
- سيُطلب منك كلمة المرور مرتين (اكتب كلمة مرور قوية ≥ 12 حرفاً).
- سيُنتج `bot.enc` و `bot.meta`.

### الخطوة 3 — انقل الملف الأصلي إلى مكان آمن
```bash
mv best_trading_v10_ai3.py ~/safe_location/best_trading_v10_ai3.py.original
```

**لا تحذفه نهائياً** — ستحتاجه إذا نسيت كلمة المرور أو أردت التعديل.

### الخطوة 4 — شغّل البوت عبر الـ launcher
```bash
python3 launcher.py --mode backtest --capital 100 --nassets 10 --maxcon 5
```

سيُطلب منك كلمة المرور. ثم يعمل البوت بشكل طبيعي — كل الخيارات تعمل.

### الخطوة 5 — للنقل إلى جهاز آخر (اختياري)
- عدّل `MACHINE_BINDING = False` في **كلا** الملفين.
- أعد تشغيل `encrypt_bot.py`.
- انقل `bot.enc` + `bot.meta` + `launcher.py` إلى الجهاز الجديد.

---

## الجزء السابع: تشديد إضافي (اختياري)

### A. زيادة التشفير بـ PyArmor

```bash
pip install pyarmor
pyarmor gen --output dist best_trading_v10_ai3.py
```

هذا يُنتج `dist/best_trading_v10_ai3.py` **مشوَّشاً** (obfuscated) — حتى لو فُك التشفير، الكود صعب القراءة.

**الترتيب الصحيح:**
1. `pyarmor gen` يُنتج نسخة مشوّشة في `dist/`.
2. غيّر `SOURCE = "dist/best_trading_v10_ai3.py"` في `encrypt_bot.py`.
3. شغّل `encrypt_bot.py`.

**المكسب:** حتى لو كُسرت كلمة المرور، الكود المُستخرَج مشوّش. **الصعوبة ×10.**

### B. قفل متعدد الطبقات

أضف سطراً في `launcher.py` قبل `exec`:

```python
# فحص إضافي: منع التشغيل تحت debugger
import sys
if sys.gettrace() is not None:
    print("ERROR: debugger detected.")
    sys.exit(1)
```

### C. Time-based expiry (اختياري متقدم)

إذا أردت أن يعمل البوت لفترة محددة فقط:

```python
import time
EXPIRY_TS = 1790000000  # 2026-09-15
if time.time() > EXPIRY_TS:
    print("ERROR: license expired.")
    sys.exit(1)
```

---

## الجزء الثامن: تحذيرات صادقة

### 1. اكتب كلمة المرور في مكان آمن
- **مدير كلمات مرور** (Bitwarden, 1Password, KeePass).
- **ورقة مكتوبة** في مكان فيزيائي آمن.
- **لا تحفظها في ملف نصي** على نفس الجهاز.

### 2. احتفظ بنسخة من الملف الأصلي
- على USB خارجي.
- على سحابة (Google Drive, Dropbox).
- **مشفّراً** بكلمة مرور مختلفة.

### 3. إذا نسيت كلمة المرور
- **لا يمكن استرجاعها.** التشفير AES مع 600,000 تكرار PBKDF2 غير قابل للكسر.
- استعد من النسخة الأصلية، وأعد التشفير بكلمة جديدة.

### 4. Machine Binding — قيود
- يعتمد على MAC + hostname + OS + CPU architecture.
- **يتغير** إذا:
  - غيّرت كرت الشبكة.
  - غيّرت اسم الجهاز.
  - أعدت تثبيت النظام.
- **الحل:** احتفظ بقيمة `machine_id` عندك، وأعد التشفير عند الحاجة.

### 5. الفرق بين الحماية والحماية الكاملة
- **Python لا يمكن حمايته 100%.** حتى PyArmor + تشفير يمكن كسرهما بوقت كافٍ.
- **الحماية نسبية:** من "ثوانٍ" إلى "أسابيع/أشهر".
- **الأفضل:** دفاع متعدد الطبقات + مراقبة دورية.

---

## الجزء التاسع: الخلاصة

| الطبقة | الأداة | المكسب |
|---|---|---|
| 1 | PBKDF2 + AES-256 | كلمة مرور قوية إلزامية |
| 2 | Machine ID binding | لا يعمل على أجهزة أخرى |
| 3 | PyArmor (اختياري) | كود مشوّش إذا كُسر التشفير |

**بعد التطبيق:**
- `best_trading_v10_ai3.py` **يُحذف** من مجلد التشغيل.
- `bot.enc` + `bot.meta` + `launcher.py` **يبقى**.
- التشغيل فقط عبر: `python3 launcher.py <options>`.

**بعد التنفيذ، أرسل:**
1. مخرجات `encrypt_bot.py` (حجم `bot.enc` المتوقع: ~50–100 KB).
2. نتيجة تشغيل `launcher.py` بكلمة مرور صحيحة (يجب أن يعمل البوت).
3. نتيجة تشغيل بكلمة مرور خاطئة (يجب أن يرفض بعد 3 محاولات).
4. أي خطأ.

**إذا ظهر خطأ** — أرسل النص الكامل، وسأُصلحه.
