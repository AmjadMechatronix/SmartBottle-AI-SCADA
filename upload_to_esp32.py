"""
=============================================================================
SmartBottle™ AI Vision SCADA - أداة حرق فيرموير ESP32 (Firmware Uploader)
=============================================================================
الوظيفة البرمجية والهندسية:
  تقوم هذه الأداة برفع ملف كود المتحكم (esp32/main.py) مباشرة إلى ذاكرة فلاش
  متحكم ESP32 عبر كابل USB Serial باستخدام بروتوكول Raw REPL في بيئة MicroPython:
  
  1. البحث الآلي عن منفذ الـ COM المتصل به بوردة ESP32.
  2. إرسال إشارات المقاطعة (Ctrl+C) لإيقاف أي حلقة برمجية تعمل حالياً على البوردة.
  3. الدخول في وضع المبرمج الخام (MicroPython Raw REPL Mode عبر Ctrl+A).
  4. فتح ملف :main.py في ذاكرة المتحكم وكتابة البايتات على أجزاء متتالية (Chunks).
  5. إعادة تشغيل البوردة برمجياً (machine.reset()) لتبدأ بتنفيذ الكود الجديد فوراً.
=============================================================================
"""

import sys
import os
import time
import serial
import serial.tools.list_ports

# ضبط ترميز الطرفية لدعم UTF-8 على ويندوز
sys.stdout.reconfigure(encoding='utf-8')

print("=============================================================")
print("📤 أداة حرق فيرموير ESP32 - نظام الفحص الذكي للزجاجات")
print("=============================================================")

# -----------------------------------------------------------------------------
# 1. البحث عن منافذ الـ COM المتصلة
# -----------------------------------------------------------------------------
ports = [p.device for p in serial.tools.list_ports.comports()]
print(f"🔍 المنافذ التسلسلية المكتشفة: {ports}")

# اختيار المنفذ المستهدف (يفضل COM5 إن وجد، أو أول منفذ متاح)
esp32_port = "COM5" if "COM5" in ports else (ports[0] if ports else None)

if not esp32_port:
    print("❌ لم يتم العثور على أي منفذ تسلسلي. يرجى توصيل بوردة ESP32 بكابل USB.")
    sys.exit(1)

print(f"🎯 المنفذ المستهدف لـ ESP32: {esp32_port}")

# التحقق من وجود ملف الفيرموير
firmware_file = os.path.join("esp32", "main.py")
if not os.path.exists(firmware_file):
    print(f"❌ لم يتم العثور على ملف الفيرموير: {firmware_file}")
    sys.exit(1)

print(f"📄 ملف الفيرموير المراد رفعه: {firmware_file}")
print("🚀 بدء الرفع عبر بروتوكول MicroPython Raw REPL...")

# -----------------------------------------------------------------------------
# 2. الاتصال بـ MicroPython عبر بروتوكول Raw REPL
# -----------------------------------------------------------------------------
try:
    s = serial.Serial()
    s.port = esp32_port
    s.baudrate = 115200
    s.dtr = False
    s.rts = False
    s.timeout = 2.0
    s.open()
    time.sleep(1.2)

    # مقاطعة أي برنامج يعمل حالياً (إرسال Ctrl+C مرتين)
    s.write(b'\r\x03\x03')
    time.sleep(0.3)
    s.read_all()

    # الدخول في وضع Raw REPL (إرسال Ctrl+A)
    s.write(b'\r\x01')
    time.sleep(0.3)
    resp = s.read_all()
    if b'raw REPL' not in resp:
        s.write(b'\r\x03\x01')
        time.sleep(0.5)
        resp = s.read_all()

    if b'raw REPL' not in resp:
        raise RuntimeError(f"تعذر الدخول في وضع Raw REPL. استجابة البوردة: {resp}")

    print("🔌 تم الاتصال بـ MicroPython Raw REPL بنجاح.")

    # -------------------------------------------------------------------------
    # 3. كتابة محتوى الكود إلى ملف :main.py في ذاكرة الفلاش
    # -------------------------------------------------------------------------
    with open(firmware_file, 'rb') as f:
        code_bytes = f.read()

    print(f"📦 جارٍ كتابة {len(code_bytes)} بايت إلى ملف :main.py على ESP32...")
    s.write(b"f = open('main.py', 'wb')\r\n\x04")
    time.sleep(0.2)
    s.read_all()

    # إرسال الكود على هيئة حزم بحجم 256 بايت لضمان الاستقرار
    chunk_size = 256
    for i in range(0, len(code_bytes), chunk_size):
        chunk = code_bytes[i:i+chunk_size]
        cmd = f"f.write({repr(chunk)})\r\n\x04".encode('ascii')
        s.write(cmd)
        time.sleep(0.04)
        s.read_all()

    # إغلاق الملف بعد اكتمال الكتابة
    s.write(b"f.close()\r\n\x04")
    time.sleep(0.2)
    s.read_all()

    print("✅ تم حفظ الفيرموير بنجاح على ذاكرة ESP32 (:main.py)!")
    
    # -------------------------------------------------------------------------
    # 4. إعادة تشغيل البوردة برمجياً لتشغيل الكود الجديد
    # -------------------------------------------------------------------------
    print("🔄 جارٍ إعادة تشغيل ESP32 لتفعيل التحديثات...")
    s.write(b"import machine; machine.reset()\r\n\x04")
    time.sleep(0.8)
    s.close()
    print("🎉 اكتملت العملية! البوردة تعمل الآن بالفيرموير المحدث.")
except Exception as e:
    print(f"❌ حدث خطأ أثناء رفع الفيرموير: {e}")
    sys.exit(1)
