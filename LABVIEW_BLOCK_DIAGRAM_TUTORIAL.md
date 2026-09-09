 المرجع الهندسي الشامل لبناء وتوصيل الـ Block Diagram في LabVIEW
**SmartBottle™ AI SCADA System | Complete Pin-to-Pin LabVIEW Wiring Tutorial**

تم إعداد هذا الملف كمرجع منفصل وتفصيلي دقيق، يشرح لك كل بلوك (VI) بالاسم الإنجليزي ومكانه في القائمة، وكل طرف توصيل (Terminal) وسلك ولونه بالكامل، لتتمكن من بنائه في LabVIEW خطوة بخطوة وبدون أي حيرة.

---

## 🖼️ المخطط العام للبلوكات البرمجية (Schematic Overview)

![مخطط توصيل البلوكات البرمجية في LabVIEW](C:\Users\mo\.gemini\antigravity-ide\brain\88a16530-211c-4703-805c-7ed1c9cd0a91\labview_block_diagram_schematic_1788891159440.jpg)

يتكون المخطط من **4 أقسام رئيسية** داخل حلقة تكرار واحدة (**While Loop**):
1. **القسم الأول**: حلقة التكرار والتوقيت وزر الإيقاف.
2. **القسم الثاني (المسار العلوي)**: مسار قراءة الحساسات والذكاء الاصطناعي وتفكيك الـ JSON.
3. **القسم الثالث (المسار السفلي)**: مسار قراءة صورة الكاميرا ومربعات الفحص وعرضها على الشاشة.
4. **القسم الرابع**: أزرار التحكم بالمحرك وذراع الطرد (Actuators Control).

---

## 🧱 القسم 1: حلقة التكرار الرئيسية والتوقيت (Main Loop & Timing)

### 1.1 البلوكات المطلوبة:
1. **`While Loop`**:
   - **مسار السحب**: `Functions Palette` ➔ `Programming` ➔ `Structures` ➔ `While Loop`.
   - **الوظيفة**: الإطار المستطيل الكبير الذي ستضع بداخله كل شيء ليتكرر باستمرار.
2. **`Wait (ms)`**:
   - **مسار السحب**: `Functions Palette` ➔ `Programming` ➔ `Timing` ➔ `Wait (ms)`.
   - **الوظيفة**: يضبط سرعة التحديث كل `100` ملي ثانية (10 هرتز) لمنع إشغال المعالج.
3. **`Stop Button`**:
   - يوجد تلقائياً أو اسحبه من: `Controls Palette` ➔ `Modern` ➔ `Boolean` ➔ `Stop Button`.

### 1.2 التوصيل:
- ضع **`Wait (ms)`** داخل الـ While Loop في الأسفل.
- اضغط كليك يمين على طرفه الأيسر واختر **`Create` ➔ `Constant`** واكتب القيمة: **`100`**.
- اسحب سلكاً من مخرج زر **`Stop`** إلى النقطة الحمراء الدائرية الصغيرة (**Conditional Terminal**) في أسفل يمين الـ While Loop.

---

## 📡 القسم 2: مسار قراءة الحساسات والـ JSON (Telemetry Pipeline)

هذا المسار يجلب جميع القياسات اللحظية (مسافة الألتراسونيك، نسبة الجودة، لمبات PASS و FAIL، وجميع العدادات) كل 100ms.

```
+---------------------------------------------------------------------------------------------------------+
|                                    Telemetry Pipeline Wiring                                            |
|                                                                                                         |
|  [String Constant]                 [HTTP GET.vi]                  [Unflatten From JSON]                 |
|  "http://127.0.0.1:..."            +-----------+                  +-------------------+                 |
|  ===================(Pink Wire)===>| url       |                  |                   |                 |
|                                    |           |                  |                   |                 |
|                                    |   body    |==(Pink Wire)====>| JSON string       |                 |
|                                    +-----------+                  |                   |===(Yellow Cluster Wire)===+
|                                                                   | type and defaults |                           |
|                                 [Cluster Constant]===============>+-------------------+                           |
|                                                                                                                   |
|                                                                                           [Unbundle By Name]      |
|                                                                                           +----------------+      |
|                                                                           +==============>| input cluster  |      |
|                                                                           |               |                |      |
|                                                                           |   (Orange)===>| pass_rate      |====> [Gauge: Pass Rate %]
|                                                                           |   (Orange)===>| distance_cm    |====> [Slide] & [Waveform Chart]
|                                                                           |   (Green) ===>| is_pass        |====> [PASS LED]
|                                                                           |   (Green) ===>| is_fail        |====> [FAIL LED]
|                                                                           |   (Green) ===>| esp32_online   |====> [ESP32 ONLINE LED]
|                                                                           |   (Green) ===>| bottle_present |====> [BOTTLE IN STATION LED]
|                                                                           |   (Blue)  ===>| total          |====> [Numeric: Total]
|                                                                           |   (Blue)  ===>| good           |====> [Numeric: Good]
|                                                                           |   (Blue)  ===>| defective      |====> [Numeric: Defective]
|                                                                           |   (Blue)  ===>| cap_missing    |====> [Numeric: Cap Missing]
|                                                                           |   (Blue)  ===>| damaged_plastic|====> [Numeric: Damaged Body]
|                                                                           |   (Blue)  ===>| label_missing  |====> [Numeric: Label Missing]
|                                                                           |               +----------------+
+---------------------------------------------------------------------------------------------------------+
```

### 2.1 البلوكات المطلوبة ومساراتها في القوائم:

1. **`String Constant`**:
   - **المسار**: `Programming` ➔ `String` ➔ `String Constant`.
   - **القيمة داخله**: اكتب النص التالي بالكامل:
     `http://127.0.0.1:5000/api/labview/telemetry`
2. **`HTTP Client GET.vi`**:
   - **المسار**: `Data Communication` ➔ `Protocols` ➔ `HTTP Client` ➔ `GET.vi`.
   - **الشكل**: أيقونة كرة أرضية زرقاء بسهم أخضر وسهم مكتوب عليه `GET`.
3. **`Unflatten From JSON.vi`**:
   - **المسار**: `Programming` ➔ `String` ➔ `Flatten/Unflatten String` ➔ `Unflatten From JSON`.
   - **الشكل**: أيقونة رمادية مكتوب عليها `{JSON}` وبجانبها سهم فك أصفر.
4. **`Unbundle By Name`**:
   - **المسار**: `Programming` ➔ `Cluster, Class, & Variant` ➔ `Unbundle By Name`.
   - **الشكل**: مستطيل أصفر به أسهم سوداء وملونة.

---

### 2.2 خطوات التوصيل الدقيقة (سلكاً بسلك):

1. **توصيل رابط الـ URL إلى الـ GET**:
   - اسحب سلكاً من الـ `String Constant` (سلك وردي Pink) إلى طرف **`url`** في دالة `GET.vi` (يقع في أعلى يسار الأيقونة).
2. **توصيل مخرج الاستجابة إلى فك الـ JSON**:
   - ابحث عن طرف **`body`** في دالة `GET.vi` (يقع في أسفل يمين الأيقونة).
   - اسحب سلكاً وردياً منه إلى طرف **`JSON string`** في دالة `Unflatten From JSON` (يقع في منتصف الجهة اليسرى).
3. **إنشاء عنقود المتغيرات (Type and Defaults Cluster)**:
   - اضغط كليك يمين بالماوس مباشرة على الطرف العلوي الأيسر لدالة `Unflatten From JSON` (اسمه `type and defaults`).
   - اختر من القائمة: **`Create` ➔ `Constant`**.
   - سيظهر لك مربع عنقود رمادي (Cluster).
   - ضع بداخله المتغيرات التالية بالأسماء الإنجليزية المطابقة تماماً للسيرفر:
     - **أرقام عشرية (DBL - بلون برتقالي)**:
       - `pass_rate`
       - `distance_cm`
       - `fps`
       - `confidence`
     - **أرقام صحيحة (I32 - بلون أزرق)**:
       - `total`
       - `good`
       - `defective`
       - `cap_missing`
       - `damaged_plastic`
       - `label_missing`
     - **قيم منطقية (Boolean - بلون أخضر)**:
       - `is_pass`
       - `is_fail`
       - `esp32_online`
       - `bottle_present`
4. **توصيل الـ Cluster إلى `Unbundle By Name`**:
   - وصل طرف **`value`** (المخرج الأوسط لدالة `Unflatten From JSON` - سلك أصفر مخطط) بطرف **`input cluster`** لدالة `Unbundle By Name`.
   - انقر بالماوس على الحافة السفلية لمستطيل `Unbundle By Name` واسحبها لأسفل حتى تتسع لـ 12 سطراً.
   - انقر على اسم كل سطر واختر المتغير المطلوب.
5. **توصيل الأسلاك إلى عناصر الواجهة (Front Panel Indicators)**:
   - سلك **`pass_rate`** (برتقالي) ➔ وصله بعداد **`Gauge`** (Quality Rate).
   - سلك **`distance_cm`** (برتقالي) ➔ وصله بمؤشر **`Slide`**، وفرّع منه سلكاً إلى **`Waveform Chart`**.
   - سلك **`is_pass`** (أخضر) ➔ وصله بلمبة **`PASS` LED**.
   - سلك **`is_fail`** (أخضر) ➔ وصله بلمبة **`FAIL` LED**.
   - سلك **`esp32_online`** (أخضر) ➔ وصله بلمبة **`ESP32 ONLINE` LED**.
   - سلك **`bottle_present`** (أخضر) ➔ وصله بلمبة **`BOTTLE IN STATION` LED**.
   - الأسلاك الزرقاء الستة (`total`, `good`, `defective`, `cap_missing`, `damaged_plastic`, `label_missing`) ➔ وصل كل سلك بالعداد الرقمي المقابل له.

---

## 📷 القسم 3: مسار عرض صورة الكاميرا المباشرة (Camera Pipeline)

هذا المسار يجلب صورة الزجاجة المحددة بمربعات الـ YOLO الخضراء ويعرضها على شاشة الـ 2D Picture.

```
+---------------------------------------------------------------------------------------------------------+
|                                    Camera Pipeline Wiring                                               |
|                                                                                                         |
|  [String Constant]                [HTTP GET.vi (2)]              [Draw Flattened Pixmap.vi]             |
|  "http://.../snapshot.jpg"        +-----------+                  +------------------------+             |
|  =================(Pink Wire)====>| url       |                  |                        |             |
|                                   |           |                  |                        |             |
|                                   |   body    |==(Pink Wire)====>| data (pixmap)          |             |
|                                   +-----------+                  |                        |             |
|                                                                  |  new picture (output)  |             |
|                                                                  +-----------+------------+             |
|                                                                              |                          |
|                                                                       (Special Picture Wire)            |
|                                                                              |                          |
|                                                                              v                          |
|                                                                  [2D Picture Indicator]                 |
+---------------------------------------------------------------------------------------------------------+
```

### 3.1 البلوكات المطلوبة ومساراتها:
1. **`String Constant`**:
   - **المسار**: `Programming` ➔ `String` ➔ `String Constant`.
   - **النص بداخله**: `http://127.0.0.1:5000/api/labview/snapshot.jpg`
2. **`HTTP Client GET.vi` (النسخة الثانية)**:
   - **المسار**: `Data Communication` ➔ `Protocols` ➔ `HTTP Client` ➔ `GET.vi`.
3. **`Draw Flattened Pixmap.vi`**:
   - **المسار**: `Programming` ➔ `Graphics & Sound` ➔ `Picture Functions` ➔ `Draw Flattened Pixmap.vi`.
   - **الشكل**: أيقونة شاشة مربعة متعددة الألوان مكتوب عليها `Imap` أو `Pixmap`.
4. **`2D Picture`**:
   - هذا العنصر موجود مسبقاً في شاشتك (من `Controls` ➔ `Modern` ➔ `Graph` ➔ `2D Picture`).

### 3.2 التوصيل:
1. اسحب سلكاً وردياً من الـ `String Constant` إلى طرف **`url`** في دالة `GET.vi` الثانية.
2. اسحب سلكاً وردياً من طرف **`body`** في دالة `GET.vi` إلى طرف **`data`** في دالة `Draw Flattened Pixmap.vi`.
3. اسحب سلكاً من مخرج **`new picture`** في دالة الـ Pixmap إلى أيقونة شاشة **`2D Picture`** الخاصة بواجهتك.

---

## 🎛️ القسم 4: أزرار التحكم بالمحرك وذراع الطرد (Actuators Control)

لربط مفتاح تشغيل المحرك وزر الطرد اليدوي وإضاءة الصندوق:

```
                          [Conveyor Motor Toggle Switch]
                                        |
                                  (Green Wire)
                                        |
                                        v
                           +------------------------+
                           | Case Structure [True]  |
                           |   [HTTP GET.vi]        |
                           |   "http://.../motor?action=on"
                           +------------------------+
                           | Case Structure [False] |
                           |   [HTTP GET.vi]        |
                           |   "http://.../motor?action=off"
                           +------------------------+
```

### 4.1 التوصيل:
1. **مفتاح محرك السير (Conveyor Motor Switch)**:
   - اسحب **`Case Structure`** من `Programming` ➔ `Structures`.
   - وصل أيقونة مفتاح `Conveyor Motor` بمحدد الحالة (علامة الاستفهام الخضراء `?`).
   - داخل حالة **`True`**: ضع بلوك `GET.vi` برابط:
     `http://127.0.0.1:5000/api/hardware/motor?action=on`
   - داخل حالة **`False`**: ضع بلوك `GET.vi` برابط:
     `http://127.0.0.1:5000/api/hardware/motor?action=off`
2. **زر الطرد الفوري (Manual Reject Sweep Button)**:
   - اسحب **`Case Structure`** ثانية وصل زر `Manual Reject Sweep` بمحدد الحالة (`?`).
   - داخل حالة **`True`**: ضع بلوك `GET.vi` برابط:
     `http://127.0.0.1:5000/api/hardware/servo?action=reject`
   - داخل حالة **`False`**: اتركها فارغة (لا تفعل شيئاً).
3. **مفتاح إضاءة الصندوق (Inspection Light Switch)**:
   - بنفس الطريقة ضع `Case Structure`:
     - داخل `True`: بلوك `GET.vi` برابط `http://127.0.0.1:5000/api/hardware/relay?action=on`
     - داخل `False`: بلوك `GET.vi` برابط `http://127.0.0.1:5000/api/hardware/relay?action=off`

---

## 🚀 ملخص التوصيل السريع (Cheat Sheet)

| من البلوك والطرف (From) | إلى البلوك والطرف (To) | لون السلك في LabVIEW |
| :--- | :--- | :--- |
| `String (telemetry URL)` | `GET.vi ➔ url` | وردي (Pink) |
| `GET.vi ➔ body` | `Unflatten From JSON ➔ JSON string` | وردي (Pink) |
| `Cluster Constant` | `Unflatten From JSON ➔ type and defaults` | أصفر مخطط (Cluster) |
| `Unflatten From JSON ➔ value` | `Unbundle By Name ➔ input cluster` | أصفر مخطط (Cluster) |
| `Unbundle ➔ pass_rate` | `Gauge Indicator` | برتقالي (Double) |
| `Unbundle ➔ distance_cm` | `Slide Indicator` & `Waveform Chart` | برتقالي (Double) |
| `Unbundle ➔ is_pass` | `PASS Round LED` | أخضر (Boolean) |
| `Unbundle ➔ is_fail` | `FAIL Round LED` | أخضر (Boolean) |
| `Unbundle ➔ esp32_online` | `ESP32 ONLINE Round LED` | أخضر (Boolean) |
| `Unbundle ➔ bottle_present` | `BOTTLE IN STATION Round LED` | أخضر (Boolean) |
| `Unbundle ➔ total / good / defective` | `Numeric Indicators` | أزرق (I32) |
| `String (snapshot.jpg URL)` | `GET.vi (2) ➔ url` | وردي (Pink) |
| `GET.vi (2) ➔ body` | `Draw Flattened Pixmap ➔ data` | وردي (Pink) |
| `Draw Flattened Pixmap ➔ picture` | `2D Picture Display` | سلك صورة مركب |
| `Numeric Constant (100)` | `Wait (ms) ➔ milliseconds to wait` | أزرق (I32) |
| `Stop Button` | `While Loop ➔ Conditional Terminal` | أخضر (Boolean) |

---

> 💡 **نصيحة للمبتدئين:** لتنظيم وتجميل الأسلاك تلقائياً في LabVIEW بعد التوصيل، اضغط على اختصار لوحة المفاتيح:
> **`Ctrl + U` (Clean Up Diagram)** وسيقوم LabVIEW برسم وتنسيق جميع الأسلاك بشكل هندسي مستقيم وأنيق للغاية!
