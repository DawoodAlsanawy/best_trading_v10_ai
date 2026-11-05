لرفع هذا البوت وتشغيله على AWS ليعمل بشكل مستمر على المدى الطويل، ستحتاج إلى اتباع دليل شامل يغطي كل خطوة. سأفترض أن البوت الذي تستخدمه هو `trading_2_live4_claude2_v4_micro.py` وأنك ستعمل على نظام Ubuntu.

### **الخطوة 1: إنشاء حساب AWS واختيار المنطقة**

1.  اذهب إلى [aws.amazon.com](https://aws.amazon.com) وأنشئ حساباً جديداً (أو سجل الدخول إذا كان لديك حساب).
2.  بعد الدخول، في أعلى اليمين، اختر **المنطقة (Region)** الأقرب إليك جغرافياً. هذا يقلل من زمن الوصول (Latency) إلى منصة Binance. على سبيل المثال، إذا كنت في الشرق الأوسط، قد تختار `me-south-1` (البحرين) أو `eu-central-1` (فرانكفورت).

### **الخطوة 2: إطلاق خادم EC2 (Instance)**

هذه هي الخطوة الأهم. اتبع الخطوات التالية بدقة:

1.  في وحدة التحكم (Console)، اكتب **EC2** في شريط البحث واختر خدمة **EC2**.
2.  انقر على زر **Launch instance** البرتقالي.
3.  **اختيار نظام التشغيل (AMI):** في قسم `Name`، اكتب اسماً للخادم (مثلاً `TradingBot`). في قسم `Application and OS Images (Amazon Machine Image)`، اختر **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type**. هذا هو الخيار الأكثر شيوعاً وسهولة للاستخدام.
4.  **نوع الخادم (Instance Type):** في قسم `Instance type`، اختر **`t2.micro`** أو **`t3.micro`**. هذان النوعان مؤهلان للاستخدام المجاني (Free Tier) لمدة 12 شهراً (بحد أقصى 750 ساعة شهرياً)، وهما كافيان لتشغيل بوت Python.
5.  **إنشاء مفتاح SSH (Key Pair):**
    *   في قسم `Key pair (login)`، انقر على **Create new key pair**.
    *   اكتب اسماً للمفتاح (مثلاً `trading-bot-key`).
    *   اختر نوع المفتاح `RSA` وصيغة الملف `.pem`.
    *   انقر **Create key pair**. سيتم تنزيل ملف (مثلاً `trading-bot-key.pem`) إلى جهازك. **احتفظ بهذا الملف بأمان شديد؛ ستحتاجه للاتصال بالخادم، ولا يمكن استعادته إذا فُقد.**
6.  **إعدادات الشبكة (Network Settings):**
    *   انقر على **Edit** بجانب `Network settings`.
    *   في قسم `Firewall (security groups)`، اترك `Create security group` محدداً.
    *   **يجب أن يكون لديك قاعدة واحدة فقط مسموح بها:** `SSH` على المنفذ `22`. في عمود `Source type`، اختر **`My IP`** بدلاً من `Anywhere`. هذا يضمن أن الخادم يقبل اتصالات SSH فقط من عنوان IP الخاص بك، مما يزيد الأمان بشكل كبير.
    *   لا تحتاج إلى فتح أي منافذ أخرى (مثل 80 أو 443) لأن البوت سيتصل بالخارج (إلى Binance) ولن يستقبل اتصالات واردة.
7.  **إعدادات التخزين (Configure Storage):** القيمة الافتراضية (8 GiB) كافية جداً.
8.  **مراجعة وإطلاق:** راجع ملخص الإعدادات في الجانب الأيمن. إذا كان كل شيء صحيحاً، انقر على الزر البرتقالي **Launch instance**.
9.  **انتظر بدء التشغيل:** انقر على **View all instances** وانتظر حتى تصبح حالة الخادم `Running` وتصبح فحوصات الحالة (`Status checks`) `2/2 passed`. قد يستغرق هذا بضع دقائق.

### **الخطوة 3: الاتصال بالخادم عبر SSH**

1.  في قائمة الخوادم (Instances)، انقر على الخادم الذي أنشأته.
2.  انسخ **Public IPv4 address** (عنوان IP العام).
3.  افتح Terminal (على Mac/Linux) أو PuTTY (على Windows) على جهازك.
4.  انتقل إلى المجلد الذي يحتوي على ملف `trading-bot-key.pem`.
5.  **غيّر صلاحيات الملف (مهم جداً للأمان):** في Terminal، نفّذ:
    ```bash
    chmod 400 trading-bot-key.pem
    ```
6.  **اتصل بالخادم:** استخدم الأمر التالي (مع استبدال `YOUR_PUBLIC_IP` بعنوان IP الذي نسخته):
    ```bash
    ssh -i "trading-bot-key.pem" ubuntu@YOUR_PUBLIC_IP
    ```
    إذا كان هذا أول اتصال، سيُطلب منك تأكيد البصمة. اكتب `yes` واضغط Enter.

### **الخطوة 4: تثبيت Python والاعتماديات على الخادم**

أنت الآن داخل الخادم. نفّذ الأوامر التالية بالترتيب:

1.  **تحديث النظام:**
    ```bash
    sudo apt update && sudo apt upgrade -y
    ```
2.  **تثبيت Python، pip، وأداة إنشاء البيئات الافتراضية:**
    ```bash
    sudo apt install -y python3 python3-pip python3-venv git
    ```
    هذا يثبت Python 3.10 و pip و `venv` و `git`.
3.  **تثبيت الاعتماديات الأساسية للنظام:** البوت يحتاج إلى مكتبات مثل `numpy`, `pandas`, `scikit-learn`, `ccxt`. قد تحتاج بعضها إلى أدوات بناء. للاحتياط، نفّذ:
    ```bash
    sudo apt install -y build-essential libssl-dev libffi-dev
    ```

### **الخطوة 5: رفع كود البوت إلى الخادم**

هناك طريقتان. الطريقة الأولى (والأسهل) هي استخدام `scp` من جهازك المحلي.

1.  **من جهازك المحلي** (وليس من داخل الخادم)، افتح Terminal جديداً في المجلد الذي يحتوي على ملفات البوت وملف المفتاح.
2.  انسخ ملف البوت إلى خادمك (استبدل `YOUR_PUBLIC_IP`):
    ```bash
    scp -i "trading-bot-key.pem" trading_2_live4_claude2_v4_micro.py ubuntu@YOUR_PUBLIC_IP:~/
    ```
    هذا ينسخ الملف إلى المجلد الرئيسي (`home`) للمستخدم `ubuntu` على الخادم.

**الطريقة الثانية (للمشاريع الكبيرة):** إذا كان مشروعك يحتوي على عدة ملفات (مثل ملفات `analytics`، `asset_cache`، إلخ)، فمن الأفضل استخدام `git`. يمكنك رفع الكود إلى مستودع GitHub خاص، ثم من داخل الخادم:
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

### **الخطوة 6: إعداد البيئة الافتراضية (Virtual Environment) وتثبيت المكتبات**

ارجع إلى جلسة SSH على الخادم.

1.  **إنشاء بيئة افتراضية:**
    ```bash
    python3 -m venv venv
    ```
    هذا ينشئ مجلداً اسمه `venv` يحتوي على نسخة معزولة من Python.
2.  **تفعيل البيئة الافتراضية:**
    ```bash
    source venv/bin/activate
    ```
    ستلاحظ أن موجه الأوامر أصبح يبدأ بـ `(venv)`.
3.  **تثبيت مكتبات Python المطلوبة:**
    ```bash
    pip install numpy pandas scikit-learn ccxt scipy matplotlib
    ```
    *ملاحظة: إذا كان البوت يستخدم `numba`، أضف `numba` إلى القائمة. إذا كان يستخدم `plotly` أو `pyarrow` للتحليلات، أضفهما أيضاً.*

### **الخطوة 7: تشغيل البوت بشكل دائم (24/7) باستخدام `systemd`**

لا يمكنك الاعتماد على جلسة SSH، لأنها ستُغلق عند إغلاق جهازك. الحل هو `systemd`، وهو مدير الخدمات في Linux. سيقوم بتشغيل البوت تلقائياً عند إقلاع الخادم، وإعادة تشغيله إذا توقف لأي سبب.

1.  **إنشاء ملف خدمة:**
    ```bash
    sudo nano /etc/systemd/system/tradingbot.service
    ```
2.  **الصق المحتوى التالي** في الملف (هذا الملف يخبر النظام بكيفية تشغيل البوت). **يجب عليك تعديل أمر `ExecStart` ليتطابق مع أمر التشغيل الفعلي الذي تريده** (مع مفاتيح API، إلخ).

    ```ini
    [Unit]
    Description=Trading Bot Service
    After=network.target

    [Service]
    User=ubuntu
    Group=ubuntu
    WorkingDirectory=/home/ubuntu
    # هذا هو أمر التشغيل. ضع أمرك الكامل هنا.
    # مثال: ExecStart=/home/ubuntu/venv/bin/python3 /home/ubuntu/trading_2_live4_claude2_v4_micro.py --mode live --api-key ... --api-secret ...
    ExecStart=/home/ubuntu/venv/bin/python3 /home/ubuntu/trading_2_live4_claude2_v4_micro.py --mode live [YOUR_OTHER_ARGS]
    Restart=always
    RestartSec=10
    StandardOutput=append:/home/ubuntu/bot.log
    StandardError=append:/home/ubuntu/bot.log

    [Install]
    WantedBy=multi-user.target
    ```
    *   `User=ubuntu`: يجب أن يكون `ubuntu`.
    *   `WorkingDirectory`: يجب أن يكون `/home/ubuntu` (حيث يوجد ملف البوت).
    *   `ExecStart`: هذا هو السطر الأهم. يجب أن يشير إلى **Python الموجود داخل البيئة الافتراضية** (`/home/ubuntu/venv/bin/python3`) وليس Python العام. ثم مسار ملف البوت، ثم جميع الوسائط (arguments) التي تريد تشغيله بها.
    *   `Restart=always`: هذا يضمن إعادة تشغيل البوت تلقائياً إذا انهار لأي سبب.
    *   `StandardOutput` و `StandardError`: يقومان بتوجيه جميع مخرجات البوت (بما في ذلك الأخطاء) إلى ملف `bot.log` لتتمكن من مراجعتها لاحقاً.

3.  **حفظ الملف والخروج:** اضغط `Ctrl+X`، ثم `Y`، ثم `Enter`.
4.  **إعادة تحميل `systemd` لقراءة الملف الجديد:**
    ```bash
    sudo systemctl daemon-reload
    ```
5.  **تفعيل الخدمة لتعمل عند الإقلاع:**
    ```bash
    sudo systemctl enable tradingbot.service
    ```
6.  **بدء الخدمة الآن:**
    ```bash
    sudo systemctl start tradingbot.service
    ```

### **الخطوة 8: التحقق من حالة البوت ومراقبة السجلات**

1.  **التحقق من أن الخدمة تعمل:**
    ```bash
    sudo systemctl status tradingbot.service
    ```
    يجب أن ترى `Active: active (running)` باللون الأخضر.

2.  **مراقبة السجلات (Logs) في الوقت الفعلي:**
    ```bash
    tail -f /home/ubuntu/bot.log
    ```
    سيعرض هذا السجل كل ما يفعله البوت. يمكنك الخروج منه بـ `Ctrl+C`.

3.  **مراقبة مخرجات `systemd` نفسها (للتأكد من عدم وجود أخطاء في التشغيل):**
    ```bash
    sudo journalctl -u tradingbot.service -f
    ```

### **الخطوة 9: إدارة الخدمة (أوامر مفيدة)**

*   **إيقاف البوت مؤقتاً:**
    ```bash
    sudo systemctl stop tradingbot.service
    ```
*   **إعادة تشغيل البوت (بعد تحديث الكود أو الإعدادات):**
    ```bash
    sudo systemctl restart tradingbot.service
    ```
*   **تعطيل التشغيل التلقائي عند الإقلاع:**
    ```bash
    sudo systemctl disable tradingbot.service
    ```

### **الخطوة 10: تحديث البوت (للمستقبل)**

عندما تريد تحديث الكود:

1.  أوقف الخدمة: `sudo systemctl stop tradingbot.service`
2.  ارفع الملف الجديد إلى الخادم باستخدام `scp` (كما في الخطوة 5).
3.  أعد تشغيل الخدمة: `sudo systemctl start tradingbot.service`

### **الخطوة 11: اعتبارات الأمان والصيانة (مهمة جداً)**

*   **مفاتيح API:** **لا تضع مفاتيح API الخاصة بك مباشرة في ملف `tradingbot.service`** إذا كان ذلك ممكناً. بدلاً من ذلك، استخدم متغيرات البيئة (Environment Variables). يمكنك إنشاء ملف `.env` في مجلد `/home/ubuntu` يحتوي على مفاتيحك، ثم في ملف الخدمة، أضف السطر `EnvironmentFile=/home/ubuntu/.env`، وفي البوت، اقرأ المفاتيح باستخدام `os.environ.get('BINANCE_API_KEY')`.
*   **صلاحيات المفاتيح:** تأكد من أن مفاتيح API التي أنشأتها في Binance **لا تمتلك صلاحية السحب (Withdrawal)**. يجب أن تكون صلاحيتها "Read" و "Trade" فقط. هذا يحمي أموالك حتى لو سُرقت المفاتيح.
*   **المراقبة:** راقب ملف `bot.log` بشكل دوري (مرة كل يوم أو يومين) للتأكد من عدم وجود أخطاء متكررة أو سلوك غير متوقع.
*   **النسخ الاحتياطي:** احتفظ بنسخة من ملفات البوت وملف `symbol_meta_live.json` (الذي يحفظ حالة الرموز) على جهازك المحلي. يمكنك عمل نسخة احتياطية من الخادم باستخدام `scp`:
    ```bash
    scp -i "trading-bot-key.pem" ubuntu@YOUR_PUBLIC_IP:~/symbol_meta_live.json .
    ```

باتباع هذه الخطوات، سيكون البوت الخاص بك جاهزاً للعمل على AWS بشكل مستمر. تذكر أن تعيد تشغيل الخدمة (`sudo systemctl restart tradingbot.service`) بعد أي تعديل على ملف البوت أو إعداداته.
