"""
=============================================================================
SmartBottle™ AI Vision SCADA - واجهة التحكم العليا (High-Level ESP32 Controller)
=============================================================================
الوظيفة البرمجية والهندسية:
  1. توفير واجهة برمجية تطبيقية (High-Level Python API) نظيفة وسهلة الاستخدام
     لكافة عمليات التحكم الصناعي بالعتاد.
  2. دعم الإرسال المزدوج الهجين (Hybrid Dual-Channel Dispatcher):
     إمكانية إرسال الأوامر عبر شبكة الـ Wi-Fi (REST API) أو عبر منفذ USB Serial تلقائياً.
  3. استدعاء روتينات العمليات الصناعية بنقرة واحدة:
     - `actuate_pass()`: الزجاجة مطابقة -> إضاءة الليد الأخضر واستمرار السير.
     - `actuate_fail()`: الزجاجة معيبة -> إضاءة الأحمر، صافرة الإنذار، ودفع ذراع السيرفو.
     - `actuate_review()`: حالة غير مؤكدة -> إضاءة الأزرق للمراجعة البشرية.
  4. دوال التحكم اليدوي المباشر بالمحرك، ريليه الإضاءة، زوايا السيرفو، وصافرة الإنذار.
=============================================================================
"""

import logging
import json
import urllib.request
import config
from hardware.serial_manager import SerialManager

# إعداد مسجل أحداث واجهة تحكم العتاد
logger = logging.getLogger("ESP32Controller")


class ESP32Controller:
    """
    الفئة العليا للتحكم بالعتاد الصناعي.
    تطبق نمط التصميم الأحادي (Singleton) لتوحيد قنوات التحكم عبر النظام.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """إنشاء نسخة أحادية مشتركة من متحكم العتاد."""
        if cls._instance is None:
            cls._instance = super(ESP32Controller, cls).__new__(cls)
            cls._instance.serial_manager = SerialManager()
            cls._instance.wifi_ip = getattr(config, "ESP32_CONTROLLER_IP", None)
            cls._instance.comm_mode = getattr(config, "ESP32_COMM_MODE", "AUTO")
        return cls._instance

    def send_command(self, cmd):
        """
        موجّه الأوامر الموحد (Unified Command Dispatcher):
        يحاول أولاً إرسال الأمر عبر شبكة الـ Wi-Fi REST API،
        وفي حال تعذر ذلك أو كان النمط USB، يتم الإرسال عبر المنفذ التسلسلي Serial UART.
        """
        cmd_clean = cmd.strip().upper()
        mode = getattr(config, "ESP32_COMM_MODE", "AUTO")
        wifi_url = getattr(config, "ESP32_CONTROLLER_IP", None)

        # 1. محاولة الإرسال عبر شبكة Wi-Fi إن كانت مفعلة
        if mode in ["WIFI", "AUTO"] and wifi_url:
            try:
                base_url = wifi_url.rstrip("/")
                endpoint = f"{base_url}/api/{cmd_clean.lower()}"
                req = urllib.request.Request(endpoint, headers={"User-Agent": "SmartBottle/1.0"})
                with urllib.request.urlopen(req, timeout=0.6) as resp:
                    raw = resp.read().decode("utf-8")
                    try:
                        parsed = json.loads(raw)
                        return {"status": "success", "data": parsed, "channel": "WIFI"}
                    except Exception:
                        return {"status": "success", "raw": raw, "channel": "WIFI"}
            except Exception as e:
                if mode == "WIFI":
                    logger.warning(f"⚠️ خطأ أثناء إرسال أمر Wi-Fi: {e}")
                    return {"status": "error", "error": str(e), "channel": "WIFI"}

        # 2. التحول التلقائي للمنفذ التسلسلي السلكي (USB Serial Fallback)
        return self.serial_manager.send_command(cmd_clean)

    # =========================================================================
    # 1. روتينات الاستجابة الصناعية لنتائج الفحص (Inspection Actuation Routines)
    # =========================================================================
    def actuate_pass(self):
        """
        إجراء المطابقة (PASS):
        الزجاجة سليمة: ليد أخضر ON، محرك السير شغال، ذراع السيرفو في وضع المرور الطبيعي (Home).
        """
        logger.info("🟢 ACTUATION: PASS (Green LED | Conveyor Running | Servo Home)")
        return self.send_command("PASS")

    def actuate_fail(self, angle=None):
        """
        إجراء الرفض (FAIL):
        الزجاجة معيبة: ليد أحمر ON، إطلاق صافرة الإنذار، وتفعيل ذراع السيرفو لرفض الزجاجة.
        """
        ang = angle if angle is not None else getattr(config, "SERVO_REJECT_ANGLE", 90)
        logger.warning(f"🔴 ACTUATION: FAIL / DEFECT (Red LED | Buzzer Alarm | Servo Reject {ang}°)")
        if ang == 90:
            return self.send_command("FAIL")
        return self.send_command(f"FAIL:{ang}")

    def actuate_review(self):
        """
        إجراء المراجعة البشرية (REVIEW):
        حالة غير مؤكدة: ليد أزرق ON، السماح بمرورها مع تنبيه المشغل على لوحة SCADA.
        """
        logger.info("🔵 ACTUATION: REVIEW / UNCERTAIN (Blue LED | Pass without reject)")
        return self.send_command("REVIEW")

    # =========================================================================
    # 2. التحكم المباشر بالمحركات والميكانيكا (Actuator & Motor Direct Controls)
    # =========================================================================
    def motor_on(self):
        """تشغيل محرك السير الناقل (Conveyor Motor ON)."""
        logger.info("⚙️ Motor: ON")
        return self.send_command("MOTOR_ON")

    def motor_off(self):
        """إيقاف محرك السير الناقل (Conveyor Motor OFF)."""
        logger.info("⚙️ Motor: OFF")
        return self.send_command("MOTOR_OFF")

    def relay_on(self):
        """تشغيل ريليه إضاءة صندوق الفحص الصناعي (Relay GPIO 25 ON)."""
        logger.info("⚡ Relay: ON")
        return self.send_command("RELAY_ON")

    def relay_off(self):
        """إطفاء ريليه إضاءة صندوق الفحص الصناعي (Relay GPIO 25 OFF)."""
        logger.info("⚡ Relay: OFF")
        return self.send_command("RELAY_OFF")

    def servo_reject(self, angle=None):
        """تفعيل ضربة ذراع السيرفو لطرد الزجاجة المعيبة فوراً."""
        ang = angle if angle is not None else getattr(config, "SERVO_REJECT_ANGLE", 90)
        logger.info(f"🦾 Servo: REJECT Sweep ({ang}°)")
        if ang == 90:
            return self.send_command("REJECT")
        return self.send_command(f"REJECT:{ang}")

    def servo_home(self, angle=None):
        """إرجاع ذراع السيرفو لوضع البداية (0 درجة) لفتح مسار السير."""
        ang = angle if angle is not None else getattr(config, "SERVO_HOME_ANGLE", 0)
        logger.info(f"🦾 Servo: HOME Position ({ang}°)")
        if ang == 0:
            return self.send_command("SERVO_HOME")
        return self.send_command(f"SERVO:{ang}")

    def set_servo_angle(self, angle):
        """توجيه ذراع السيرفو إلى زاوية مخصصة بدقة (من 0 إلى 180 درجة)."""
        logger.info(f"🦾 Servo: Set Angle {angle}°")
        return self.send_command(f"SERVO:{angle}")

    # =========================================================================
    # 3. إشارات المؤشرات والإنذار (Indicators & Alarms)
    # =========================================================================
    def set_led(self, color):
        """
        التحكم بليدات الحالة الثلاثية:
          - 'green': ليد أخضر (مطابق)
          - 'red': ليد أحمر (معيب)
          - 'blue': ليد أزرق (مراجعة)
          - 'off': إطفاء الليدات
        """
        color = color.lower()
        if color == "green":
            return self.send_command("GREEN")
        elif color == "red":
            return self.send_command("RED")
        elif color == "blue":
            return self.send_command("BLUE")
        else:
            return self.send_command("LEDS_OFF")

    def trigger_buzzer(self, duration_ms=200):
        """إطلاق نغمة إنذار صوتية عبر الصافرة للتنبيه بوجود زجاجة معيبة."""
        return self.send_command("BUZZER")

    # =========================================================================
    # 4. قراءات الحساسات والتليمتري (Telemetry & Sensor Status)
    # =========================================================================
    def get_distance(self):
        """طلب قراءة المسافة اللحظية من حساس الألتراسونيك (بالسنتيمتر)."""
        self.send_command("DISTANCE")
        status = self.serial_manager.get_status()
        return status.get("distance_cm", 999.0)

    def get_status(self):
        """استخراج تقرير الحالة الكامل والمفصل لكافة مكونات العتاد."""
        return self.serial_manager.get_status()

    def reset(self):
        """إعادة تعيين كافة المشغلات والمحركات إلى وضع الجاهزية الافتراضي."""
        logger.info("🔄 طلب إعادة تعيين العتاد (Hardware Reset)")
        return self.send_command("RESET")

    def set_bottle_callback(self, on_detected=None, on_cleared=None):
        """ربط دوال الاستجابة لأحداث اقتراب وابتعاد الزجاجة عن الحساس."""
        if on_detected:
            self.serial_manager.on_bottle_detected_cb = on_detected
        if on_cleared:
            self.serial_manager.on_bottle_cleared_cb = on_cleared
