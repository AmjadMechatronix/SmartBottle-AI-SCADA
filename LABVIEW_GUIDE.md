# دليل التوصيل البرمجي الكامل في LabVIEW (Block Diagram Step-by-Step)
**SmartBottle™ AI SCADA System | National Instruments LabVIEW Wiring Guide**

---

## 🖼️ 1. المخطط الهندسي الشامل للتوصيل (Block Diagram Schematic)

إليك المخطط الكامل للـ **Block Diagram** (`Ctrl + E`)؛ يوضح بالضبط كل بلوك (VI) أين يوضع، وكيف يتم توصيل الأسلاك الملونة من بدايتها إلى نهايتها:

![مخطط توصيل البلوكات البرمجية في LabVIEW](C:\Users\mo\.gemini\antigravity-ide\brain\88a16530-211c-4703-805c-7ed1c9cd0a91\labview_block_diagram_schematic_1788891159440.jpg)

---

## 🧱 2. قائمة البلوكات (VIs) وأماكنها في القوائم (Palette Locations)

افتح شاشة الـ **Block Diagram** بالضغط على `Ctrl + E`. انقر بزر الفأرة الأيمن في أي مكان فارغ لفتح قائمة الدوال (**Functions Palette**)، واسحب البلوكات التالية:

| اسم البلوك (VI Name) | الأيقونة والشكل | المسار في القوائم (Palette Path) | الوظيفة |
| :--- | :--- | :--- | :--- |
| **While Loop** | إطار رمادي مستطيل به زر إيقاف أحمر | `Programming` ➔ `Structures` ➔ `While Loop` | حلقة التكرار المستمر لتحديث الواجهة |
| **HTTP GET.vi** | كرة أرضية زرقاء بسهم أخضر مكتوب عليه `GET` | `Data Communication` ➔ `Protocols` ➔ `HTTP Client` ➔ `GET.vi` | جلب البيانات اللحظية وصورة الكاميرا |
| **Unflatten From JSON.vi** | أيقونة مكتوب عليها `{JSON}` وبجانبها سهم فك | `Programming` ➔ `String` ➔ `Flatten/Unflatten String` ➔ `Unflatten From JSON` | تحويل نص الـ JSON إلى قيم وحساسات |
| **Unbundle By Name** | مستطيل أصفر به أسهم ملونة | `Programming` ➔ `Cluster, Class, & Variant` ➔ `Unbundle By Name` | تفكيك الحساسات والعدادات كلٌ على حدة |
| **Draw Flattened Pixmap** | أيقونة مربعات ألوان شاشة بيكسل | `Programming` ➔ `Graphics & Sound` ➔ `Picture Functions` ➔ `Draw Flattened Pixmap.vi` | تحويل بايتات الـ JPEG إلى صورة معروضة |
| **Wait (ms)** | شكل ساعة توقيت صغيرة | `Programming` ➔ `Timing` ➔ `Wait (ms)` | ضبط سرعة التحديث (100ms) لمنع إجهاد المعالج |
| **String Constant** | صندوق نصي وردي | `Programming` ➔ `String` ➔ `String Constant` | كتابة روابط الـ API |

---

## 🔌 3. خطوات التوصيل خطوة بخطوة بالأسلاك (Step-by-Step Wiring)

### أولاً: إنشاء حلقة التكرار الرئيسية (Main Loop)
1. اسحب **`While Loop`** واجعل حجمه كبيراً يغطي مساحة العمل.
2. اسحب **`Wait (ms)`** وضعه بالداخل، وانقر بالزر الأيمن على طرفه الأيسر واختر **`Create Constant`** واكتب الرقم `100`.
3. وصل زر الإيقاف **`Stop`** بنقطة الشرط الحمراء للـ While Loop في الأسفل.

---

### ثانياً: مسار قراءة الحساسات والعدادات (Telemetry Pipeline - المسار العلوي)

```
[String URL] ──(Pink Wire)──► [HTTP GET] ──(Pink Wire Body)──► [Unflatten From JSON] ──(Yellow Wire)──► [Unbundle By Name]
                                                                        ▲
[Cluster Type Default] ─────────────────────────────────────────────────┘
```

1. **إضافة رابط البيانات**:
   - اسحب **`String Constant`** واكتب بداخله الرابط التالي:
     `http://127.0.0.1:5000/api/labview/telemetry`
2. **استدعاء الـ GET**:
   - اسحب بلوك **`GET.vi`** (الأول)، وصل سلك الرابط الوردي بالطرف العلوي الأيسر المسمى **`url`**.
3. **فك تشفير الـ JSON**:
   - اسحب بلوك **`Unflatten From JSON.vi`**.
   - وصل الطرف السفلي الأيمن من الـ GET (المسمى **`body`** - سلك وردي) بالطرف الأوسط الأيسر المسمى **`JSON string`**.
4. **تحديد عنقود البيانات (Cluster Type Constant)**:
   - لكي يعرف LabVIEW أسماء المتغيرات تلقائياً:
     - انقر بالزر الأيمن على طرف **`type and defaults`** (أعلى يسار دالة `Unflatten From JSON`).
     - اختر **`Create` ➔ `Constant`**.
     - ستظهر لك كتلة Cluster رمادية، يمكنك إضافة العناصر التالية بداخلها:
       - `distance_cm` (رقمي Double)
       - `pass_rate` (رقمي Double)
       - `fps` (رقمي Double)
       - `total` (رقمي I32)
       - `good` (رقمي I32)
       - `defective` (رقمي I32)
       - `cap_missing` (رقمي I32)
       - `damaged_plastic` (رقمي I32)
       - `label_missing` (رقمي I32)
       - `is_pass` (منطقي Boolean)
       - `is_fail` (منطقي Boolean)
       - `esp32_online` (منطقي Boolean)
       - `bottle_present` (منطقي Boolean)
5. **توزيع الأسلاك إلى الشاشة (Unbundle By Name)**:
   - اسحب بلوك **`Unbundle By Name`**.
   - وصل مخرج `value` (السلك الأصفر المخطط) من دالة الـ JSON بمدخل الـ `Unbundle By Name`.
   - انقر على أسفل بلوك الـ Unbundle واسحبه لأسفل بالماوس ليظهر لك عدة صفوف.
   - انقر على اسم كل صف واختر المتغير المناسب وقم بتوصيل السلك إلى العنصر المقابل في واجهتك:
     - سلك `pass_rate` (برتقالي) ➔ يذهب إلى عداد **`Quality Gauge`**.
     - سلك `distance_cm` (برتقالي) ➔ يذهب إلى مؤشر **`Distance Slide`** وإلى مخطط **`Waveform Chart`**.
     - سلك `is_pass` (أخضر) ➔ يذهب إلى لمبة **`PASS LED`**.
     - سلك `is_fail` (أخضر) ➔ يذهب إلى لمبة **`FAIL LED`**.
     - سلك `esp32_online` (أخضر) ➔ يذهب إلى لمبة **`ESP32 ONLINE`**.
     - سلك `bottle_present` (أخضر) ➔ يذهب إلى لمبة **`BOTTLE IN STATION`**.
     - أسلاك `total` و `good` و `defective` (زرقاء) ➔ تذهب للعدادات الرقمية.

---

### ثالثاً: مسار عرض صورة الكاميرا ومربعات الفحص (Camera Snapshot Pipeline - المسار السفلي)

```
[String URL] ──(Pink Wire)──► [HTTP GET] ──(Body)──► [Draw Flattened Pixmap] ──(Picture Wire)──► [2D Picture]
```

1. اسحب بلوك **`GET.vi`** ثانٍ وضعه في الجزء السفلي داخل الـ While Loop.
2. اسحب **`String Constant`** واكتب بداخله رابط الصورة المباشر:
   `http://127.0.0.1:5000/api/labview/snapshot.jpg`
   ووصله بمدخل `url`.
3. من قائمة `Graphics & Sound ➔ Picture Functions`، اسحب بلوك **`Draw Flattened Pixmap.vi`**.
4. وصل مخرج `body` (سلك البايتات الوردي) القادم من دالة الـ GET بمدخل `data` في بلوك الـ Pixmap.
5. وصل مخرج دالة Pixmap بسلك مباشر إلى عنصر شاشة **`2D Picture`** على واجهتك.

---

### رابعاً: توصيل أزرار التحكم بالمحرك وذراع الطرد (Hardware Actuators)

للتحكم المباشر في السير الناقل أو إطلاق ذراع الطرد:
1. **زر الطرد الفوري (Manual Reject Sweep)**:
   - اسحب **`Case Structure`** من `Programming ➔ Structures`.
   - وصل زر `Manual Reject Sweep` بمدخل علامة الاستفهام الخضراء للـ Case Structure.
   - داخل حالة **`True`**: ضع دالة `GET.vi` برابط:
     `http://127.0.0.1:5000/api/hardware/servo?action=reject`
   - في حالة `False`: اتركها فارغة.
2. **مفتاح محرك السير (Conveyor Motor Switch)**:
   - ضع Case Structure موصولة بمفتاح السير:
     - داخل `True`: استدعاء `GET.vi` برابط `http://127.0.0.1:5000/api/hardware/motor?action=on`
     - داخل `False`: استدعاء `GET.vi` برابط `http://127.0.0.1:5000/api/hardware/motor?action=off`

---

## ⚡ 4. التشغيل والاختبار الفوري

1. تأكد أن سيرفر المشروع قيد التشغيل (`python server.py`).
2. في شاشة LabVIEW، اضغط على زر السهم الأبيض في الأعلى (**Run `Ctrl + R`**).
3. **ستلاحظ فوراً:**
   - شاشة الكاميرا تبدأ ببث صور الزجاجات مع مربعات الذكاء الاصطناعي الخضراء.
   - مؤشر المسافة HC-SR04 يتحرك لحظياً مع اقتراب أو ابتعاد الزجاجة.
   - لمبات `PASS` أو `FAIL` تضيء وتومض فور رصد عيب بالزجاجة.
   - مؤشر نسبة الجودة والعدادات تُحدّث تلقائياً!
