"""
=============================================================================
SmartBottle™ AI Vision SCADA - أداة حرق فيرموير متحكم الواي فاي (Wi-Fi Uploader)
=============================================================================
الوظيفة البرمجية والهندسية:
  تقوم هذه الأداة برفع ملف كود المتحكم الشبكي (esp32_wifi_controller/main.py)
  إلى بوردة ESP32 باستخدام أداة ميكروبايثون الرسمية (mpremote):
  
  1. اكتشاف المنافذ التسلسلية المتصلة وتحديد المنفذ المستهدف.
  2. نسخ ملف main.py إلى الذاكرة الرئيسية للمتحكم.
  3. إعادة تشغيل البوردة برمجياً لتبدأ بالاتصال بشبكة Wi-Fi وتشغيل خادم REST API (Port 80).
=============================================================================
"""

import sys
import os
import subprocess
import time
import serial.tools.list_ports

# ضبط ترميز الطرفية لدعم UTF-8 على ويندوز
sys.stdout.reconfigure(encoding='utf-8')

print("=============================================================")
print("🌐 أداة حرق فيرموير متحكم الواي فاي اللاسلكي (ESP32 Wi-Fi Controller)")
print("=============================================================")

# -----------------------------------------------------------------------------
# 1. فحص المنافذ التسلسلية المتاحة
# -----------------------------------------------------------------------------
ports = [p.device for p in serial.tools.list_ports.comports()]
print(f"🔍 المنافذ المكتشفة: {ports}")

if not ports:
    print("❌ لم يتم العثور على أي منفذ. يرجى توصيل بوردة ESP32 بكابل USB.")
    sys.exit(1)

# اختيار المنفذ المستهدف
target_port = ports[0] if len(ports) == 1 else None
if not target_port:
    print("\n⚠️ تم اكتشاف عدة منافذ، سيتم استخدام المنفذ الأول افتراضياً:")
    for i, p in enumerate(ports):
        print(f"   [{i+1}] {p}")
    target_port = ports[0]

firmware_file = os.path.join("esp32_wifi_controller", "main.py")
if not os.path.exists(firmware_file):
    print(f"❌ لم يتم العثور على ملف الكود: {firmware_file}")
    sys.exit(1)

print(f"🎯 المنفذ المستهدف: {target_port}")
print(f"📄 ملف الكود المراد رفعه: {firmware_file}")
print("🚀 جارٍ رفع الفيرموير عبر mpremote إلى (:main.py)...")
print("⚠️ تنبيه: يرجى التأكد من إغلاق برنامج Thonny IDE لتفادي قفل المنفذ.")

# -----------------------------------------------------------------------------
# 2. تنفيذ أمر الرفع عبر أداة mpremote
# -----------------------------------------------------------------------------
cmd = [sys.executable, "-m", "mpremote", "connect", target_port, "fs", "cp", firmware_file, ":main.py"]
try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode == 0:
        print("✅ تم رفع الفيرموير اللاسلكي بنجاح إلى ESP32!")
        print("🔄 جارٍ إعادة تشغيل البوردة للدخول في وضع شبكة Wi-Fi...")
        subprocess.run([sys.executable, "-m", "mpremote", "connect", target_port, "reset"], capture_output=True)
        print("🎉 تعمل البوردة الآن! يمكنك مراقبة عنوان الـ IP الممنوح لها عبر الطرفية.")
    else:
        print(f"⚠️ ظهرت رسالة أثناء الرفع (رمز الخروج: {res.returncode}):")
        print(res.stderr or res.stdout)
        if "could not open port" in (res.stderr or "").lower() or "permissionerror" in (res.stderr or "").lower():
            print("💡 تذكير: أغلق برنامج Thonny IDE أو أي برنامج يراقب المنفذ ثم أعد المحاولة.")
except Exception as e:
    print(f"❌ حدث خطأ أثناء الرفع: {e}")
