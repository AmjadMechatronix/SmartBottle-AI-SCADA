"""
=============================================================================
SmartBottle™ AI Vision SCADA - مدير الاتصال التسلسلي (Hardware Serial Manager)
=============================================================================
الوظيفة البرمجية والهندسية:
  1. إدارة طبقة تجريد العتاد (Hardware Abstraction Layer - HAL) بين بايثون ومتحكم ESP32.
  2. الاكتشاف التلقائي لمنفذ الاتصال (Auto Port Detection): فحص منافذ الـ COM والتعرف
     على شرائح الـ USB-UART الشهيرة (CH340, CP2102, FTDI, Espressif).
  3. خيط خلفي ذكي لإعادة الاتصال التلقائي (Auto-Reconnect Thread) دون تجميد الواجهة.
  4. محاكاة العتاد الافتراضية الشفافة (Virtual Hardware Fallback Mode):
     إذا لم يكن متحكم ESP32 موصولاً فيزيائياً بالحاسوب، يعمل النظام بنمط محاكاة ذكي
     يحاكي الليدات، السيرفو، السير الناقل، والحساسات؛ مما يتيح تجربة النظام واختباره بالكامل.
  5. معالجة الإشارات اللحظية وأحداث حساس الألتراسونيك واستدعاء الدوال التنبيهية (Callbacks).
=============================================================================
"""

import time
import threading
import logging
import json
import serial
import serial.tools.list_ports
import config

# تكوين مسجل الأحداث لطبقة الاتصال التسلسلي
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SerialManager")


class SerialManager:
    """
    فئة إدارة الاتصال التسلسلي ثنائية القنوات (Hardware + Virtual Simulation).
    تعتمد نمط التصميم الأحادي (Singleton) مع أقفال التزامن لمنع التضارب في القراءة والكتابة.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """ضمان إنشاء كائن وحيد مشترك لمدير الاتصال في كافة خيوط التطبيق."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SerialManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, port=None, baudrate=None):
        if self._initialized:
            return
        self._initialized = True

        # استيراد إعدادات المنفذ والسرعة
        self.configured_port = port or config.SERIAL_PORT
        self.baudrate = baudrate or config.SERIAL_BAUDRATE
        self.serial_conn = None
        self.active_port = None
        self.is_connected = False
        self.is_running = True
        self.io_lock = threading.Lock()

        # ذاكرة الحالة اللحظية للعتاد (Telemetry Cache)
        self.last_status = {
            "esp32": "OFFLINE",           # حالة الاتصال الفيزيائي
            "distance_cm": 999.0,          # المسافة المقروءة من حساس الألتراسونيك
            "bottle_detected": False,      # هل توجد زجاجة أمام الحساس حالياً
            "motor": True,                 # حالة محرك السير الناقل (True = شغال)
            "servo": "HOME",               # وضع محرك السيرفو ("HOME" أو "REJECT")
            "led_green": 0,                # مؤشر النجاح الأخضر
            "led_red": 0,                  # مؤشر العيب الأحمر
            "led_blue": 0,                 # مؤشر المراجعة الأزرق
            "buzzer": 0,                   # صافرة الإنذار الصوتية
            "relay": False,                # ريليه إضاءة صندوق الفحص
            "box_light": "OFF",            # حالة إضاءة الصندوق
            "port": "NONE",                # اسم المنفذ الفعلي
            "is_simulated": False          # هل النظام يعمل بنمط المحاكاة الافتراضية
        }

        # دوال الاستدعاء التنبيهية لأحداث وصول ومغادرة الزجاجة (Event Callbacks)
        self.distance_threshold = getattr(config, 'BOTTLE_DETECT_DISTANCE_CM', 50.0)
        self.on_bottle_detected_cb = None
        self.on_bottle_cleared_cb = None

        # تشغيل خيط القراءة وإعادة الاتصال في الخلفية
        self.reader_thread = threading.Thread(target=self._connection_and_read_loop, daemon=True)
        self.reader_thread.start()

    def _find_esp32_port(self):
        """
        البحث الذكي التلقائي عن منفذ COM المتصل به متحكم ESP32
        عبر فحص معرفات العتاد وشرائح التحويل USB-to-UART.
        """
        ports = serial.tools.list_ports.comports()
        for p in ports:
            desc = p.description.lower()
            hwid = p.hwid.lower()
            # فحص الشرائح الشائعة في بوردات ESP32
            if any(k in desc or k in hwid for k in ["ch340", "cp210", "ftdi", "usb serial", "uart", "espressif"]):
                return p.device
        if ports:
            # إذا لم يتم التعرف على اسم الشريحة، يتم تجربة أول منفذ متاح كخيار بديل
            return ports[0].device
        return None

    def connect(self):
        """
        محاولة فتح قناة الاتصال التسلسلي مع متحكم ESP32 الحقيقي.
        في حال تعذر ذلك، يتم التحول إلى نمط المحاكاة بسلاسة.
        """
        with self.io_lock:
            if self.serial_conn and self.serial_conn.is_open:
                return True

            target_port = self.configured_port
            if target_port == "AUTO":
                target_port = self._find_esp32_port()

            if not target_port:
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
                self.last_status["is_simulated"] = True
                return False

            try:
                self.serial_conn = serial.Serial(
                    port=target_port,
                    baudrate=self.baudrate,
                    timeout=config.SERIAL_TIMEOUT,
                    write_timeout=config.SERIAL_TIMEOUT
                )
                time.sleep(1.5)  # انتظار إعادة إقلاع البوردة بعد الاتصال (DTR/RTS Reset)
                self.active_port = target_port
                self.is_connected = True
                self.last_status["esp32"] = "ONLINE"
                self.last_status["port"] = target_port
                self.last_status["is_simulated"] = False
                logger.info(f"✅ تم الاتصال بنجاح بمتحكم ESP32 على المنفذ: {target_port}")
                
                # إرسال نبضة اختبار للتأكد من استجابة الميكروبايثون
                self._send_raw("PING\n")
                return True
            except Exception as e:
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
                self.last_status["is_simulated"] = True
                logger.warning(f"⚠️ تعذر فتح المنفذ التسلسلي {target_port}: {e} (التحول لنمط المحاكاة)")
                return False

    def disconnect(self):
        """إغلاق المنفذ التسلسلي بأمان."""
        with self.io_lock:
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
            self.serial_conn = None
            self.is_connected = False
            self.last_status["esp32"] = "OFFLINE"

    def _send_raw(self, data_str):
        """إرسال سلسلة بايتات نصية مباشرة عبر المنفذ التسلسلي المفتوح."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(data_str.encode("utf-8"))
                self.serial_conn.flush()
                return True
            except Exception as e:
                logger.error(f"خطأ أثناء إرسال البيانات التسلسلية: {e}")
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
        return False

    def send_command(self, cmd):
        """
        الدالة العمومية لإرسال الأوامر مع دعم الحماية المزدوجة:
        إذا كان العتاد موصولاً يتم إرسال الأمر الحقيقي وتحديث الحالة،
        وإذا لم يكن موصولاً يتم تنفيذ الأمر في العتاد الافتراضي (Simulation).
        """
        cmd = cmd.strip().upper()
        logger.info(f"📡 إرسال أمر للهاردوير: {cmd}")

        # في حال وجود اتصال فيزيائي نشط
        if self.is_connected:
            with self.io_lock:
                success = self._send_raw(f"{cmd}\n")
                if success:
                    self._simulate_hardware_command(cmd)
                    return {"status": "success", "mode": "hardware", "command": cmd}

        # في حال العمل بنمط المحاكاة الافتراضية
        self._simulate_hardware_command(cmd)
        return {"status": "success", "mode": "simulated", "command": cmd}

    def _simulate_hardware_command(self, cmd):
        """
        تحديث الحالة الداخلية للنظام بنمط المحاكاة الذكي:
        يتيح تجربة كافة وظائف SCADA بدقة متناهية دون الحاجة لعتاد حقيقي.
        """
        if cmd == "PASS":
            self.last_status["led_green"] = 1
            self.last_status["led_red"] = 0
            self.last_status["led_blue"] = 0
            self.last_status["servo"] = "HOME"
            self.last_status["buzzer"] = 0
            self.last_status["motor"] = True
        elif cmd.startswith("FAIL") or cmd.startswith("REJECT"):
            ang = 90
            if ":" in cmd:
                try: 
                    ang = int(cmd.split(":")[1])
                except Exception: 
                    pass
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 1
            self.last_status["led_blue"] = 0
            self.last_status["servo"] = f"REJECT_{ang}"
            self.last_status["buzzer"] = 1
            # محاكاة رجوع ذراع السيرفو تلقائياً بعد 1.2 ثانية
            threading.Timer(1.2, lambda: self.last_status.update({"servo": "HOME", "buzzer": 0})).start()
        elif cmd.startswith("SERVO:"):
            try:
                ang = int(cmd.split(":")[1])
                self.last_status["servo"] = f"ANGLE_{ang}"
            except Exception: 
                pass
        elif cmd == "REVIEW":
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 0
            self.last_status["led_blue"] = 1
            self.last_status["servo"] = "HOME"
            self.last_status["buzzer"] = 0
        elif cmd == "MOTOR_ON":
            self.last_status["motor"] = True
        elif cmd == "MOTOR_OFF":
            self.last_status["motor"] = False
        elif cmd == "SERVO_HOME":
            self.last_status["servo"] = "HOME"
        elif cmd == "GREEN":
            self.last_status["led_green"] = 1
            self.last_status["led_red"] = 0
            self.last_status["led_blue"] = 0
        elif cmd == "RED":
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 1
            self.last_status["led_blue"] = 0
        elif cmd == "BLUE":
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 0
            self.last_status["led_blue"] = 1
        elif cmd == "LEDS_OFF":
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 0
            self.last_status["led_blue"] = 0
        elif cmd == "BUZZER":
            self.last_status["buzzer"] = 1
            threading.Timer(0.2, lambda: self.last_status.update({"buzzer": 0})).start()
        elif cmd in ["RELAY_ON", "LIGHT_ON", "BOX_LIGHT_ON"]:
            self.last_status["relay"] = True
            self.last_status["box_light"] = "ON"
        elif cmd in ["RELAY_OFF", "LIGHT_OFF", "BOX_LIGHT_OFF"]:
            self.last_status["relay"] = False
            self.last_status["box_light"] = "OFF"
        elif cmd == "RESET":
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 0
            self.last_status["led_blue"] = 0
            self.last_status["buzzer"] = 0
            self.last_status["servo"] = "HOME"
            self.last_status["motor"] = True

    def _connection_and_read_loop(self):
        """
        خيط خلفي دائم (Daemon Thread):
        يقوم بالقراءة المستمرة لبيانات التليمتري الواردة من ESP32،
        وإعادة محاولة الاتصال التلقائي في حال انقطاع السلك.
        """
        while self.is_running:
            if not self.is_connected:
                self.connect()
                time.sleep(config.AUTO_RECONNECT_INTERVAL)
                continue

            try:
                if self.serial_conn and self.serial_conn.is_open:
                    line = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
                    if line:
                        self._handle_incoming_telemetry(line)
                else:
                    self.is_connected = False
            except Exception as e:
                logger.warning(f"انقطع الاتصال التسلسلي مؤقتاً: {e}")
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
                time.sleep(1.0)

    def _handle_incoming_telemetry(self, line):
        """
        تحليل وتفكيك الرسائل الواردة من متحكم ESP32 (MicroPython Telemetry Parser).
        """
        logger.info(f"📥 استجابة من ESP32: {line}")
        
        # 1. حدث رصد وصول الزجاجة بواسطة الألتراسونيك
        if line == "EVENT:BOTTLE_DETECTED":
            self.last_status["bottle_detected"] = True
            logger.info("🍼 حدث: تم رصد وصول زجاجة إلى محطة الفحص")
            if self.on_bottle_detected_cb:
                try:
                    self.on_bottle_detected_cb()
                except Exception as e:
                    logger.error(f"خطأ في دالة on_bottle_detected: {e}")
                    
        # 2. حدث مغادرة الزجاجة
        elif line == "EVENT:BOTTLE_CLEARED":
            self.last_status["bottle_detected"] = False
            if self.on_bottle_cleared_cb:
                try:
                    self.on_bottle_cleared_cb()
                except Exception as e:
                    logger.error(f"خطأ في دالة on_bottle_cleared: {e}")
                    
        # 3. بيانات الحالة المجمعة (JSON Status)
        elif line.startswith("STATUS:"):
            try:
                json_str = line[7:]
                status_dict = json.loads(json_str)
                self.last_status.update(status_dict)
                self.last_status["esp32"] = "ONLINE"
                self.last_status["is_simulated"] = False
            except Exception:
                pass
                
        # 4. تأكيدات ريليه الإضاءة
        elif line in ["ACK:LIGHT_ON", "ACK:RELAY_ON"]:
            self.last_status["relay"] = True
            self.last_status["box_light"] = "ON"
        elif line in ["ACK:LIGHT_OFF", "ACK:RELAY_OFF"]:
            self.last_status["relay"] = False
            self.last_status["box_light"] = "OFF"
            
        # 5. قراءة المسافة اللحظية من حساس الألتراسونيك
        elif line.startswith("DISTANCE:"):
            try:
                val = float(line.split(":")[1])
                self.last_status["distance_cm"] = val
                is_present = (1.0 < val <= self.distance_threshold)
                if is_present != self.last_status.get("bottle_detected", False):
                    self.last_status["bottle_detected"] = is_present
                    if is_present and self.on_bottle_detected_cb:
                        self.on_bottle_detected_cb()
                    elif not is_present and self.on_bottle_cleared_cb:
                        self.on_bottle_cleared_cb()
            except Exception:
                pass

    def get_status(self):
        """
        استخراج لقطة حالة العتاد بتنسيق قياسي ومقروء للمشغل البشري وواجهات SCADA.
        """
        st = dict(self.last_status)
        
        # تحويل القيم المنطقية إلى نصوص واضحة
        if isinstance(st.get("motor"), bool):
            st["motor"] = "ON" if st["motor"] else "OFF"
        
        if st.get("led_green"):
            st["led"] = "GREEN"
        elif st.get("led_red"):
            st["led"] = "RED"
        elif st.get("led_blue"):
            st["led"] = "BLUE"
        else:
            st["led"] = "OFF"
            
        if isinstance(st.get("buzzer"), (int, bool)):
            st["buzzer"] = "ON" if st["buzzer"] else "OFF"
            
        return st
