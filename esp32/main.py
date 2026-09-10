"""
=============================================================================
SmartBottle™ AI Vision SCADA - فيرموير متحكم ESP32 (MicroPython Firmware)
=============================================================================
المواصفات التقنية:
  البوردة: ESP32 (NodeMCU / DevKit v1)
  لغة البرمجة: MicroPython
  قناة الاتصال: المنفذ التسلسلي السلكي USB Serial UART (115200 Baud)
  
المسؤوليات والوظائف الهندسية:
  1. حساس المسافة بالموجات فوق الصوتية (HC-SR04):
     رصد اقتراب الزجاجات بدقة عالية ومزامنة توقيت الفحص مع الكاميرا.
  2. محرك السير الناقل (Conveyor DC Motor):
     التحكم في تشغيل وإيقاف السير عبر درايفر L298N أو موسفت.
  3. محرك السيرفو لطرد المعيب (Reject Servo Motor):
     توليد نبضات PWM بتردد 50Hz لدفع الزجاجات المعيبة بزاوية 90 درجة ثم الرجوع التلقائي.
  4. ليدات الحالة الثلاثية (Status LEDs):
     أخضر (مطابق PASS)، أحمر (معيب FAIL)، أزرق (مراجعة REVIEW).
  5. صافرة الإنذار (Alarm Buzzer):
     توليد ترددات صوتية تنبيهية فور اكتشاف أي عيب صناعي.
  6. ريليه إضاءة صندوق الفحص (Box Light Relay):
     تأمين الإضاءة المثالية لحجرة التصوير لضمان دقة الكشف.
  7. معالج الأوامر التسلسلية غير الحاجب (Non-blocking Polling):
     استقبال وتنفيذ الأوامر وتوليد بيانات التليمتري دون تجميد حلقة الحساس.
=============================================================================
"""

import sys
import time
import uselect
from machine import Pin, PWM, time_pulse_us

# =============================================================================
# 📌 جدول التوصيل الكهربائي للعتاد (Hardware Pin Configuration)
# =============================================================================
# 1. ليدات الحالة الثلاثية (عبر مقاومات حماية 220Ω)
LED_GREEN_PIN = 2   # مؤشر المطابقة والنجاح (PASS)
LED_RED_PIN   = 4   # مؤشر وجود عيب والإنذار (FAIL)
LED_BLUE_PIN  = 5   # مؤشر المراجعة والمعالجة (REVIEW)

# 2. صافرة التنبيه الصوتية (Active / Passive Buzzer)
BUZZER_PIN    = 18  # القطب الموجب للصافرة (+)

# 3. حساس المسافة بالموجات فوق الصوتية (HC-SR04)
# ⚠️ ملاحظة هندسية: خط ECHO يدخل عبر مقسم جهد (Voltage Divider) لحماية مدخل ESP32 (3.3V)
TRIG_PIN      = 19  # مخرج نبضة الإرسال (Trigger)
ECHO_PIN      = 21  # مدخل نبضة الاستقبال (Echo)

# 4. محرك السير الناقل (L298N Motor Driver / Relay / MOSFET)
MOTOR_PIN     = 22  # إشارة التحكم بتشغيل المحرك (IN1)

# 5. محرك السيرفو لفرز وطرد الزجاجات المعيبة (SG90 / MG995 / MG996R)
SERVO_PIN     = 23  # سلك إشارة التحكم بالسيرفو (PWM 50Hz)

# 6. ريليه إضاءة صندوق الفحص الصناعي (GPIO 13 / 25)
BOX_LIGHT_PIN = 13  # إشارة تفعيل الريليه

# =============================================================================
# ⚙️ معايرة نبضات السيرفو (Servo PWM Calibration - 50Hz = 20ms Period)
# =============================================================================
# في MicroPython، نطاق الدورة duty_u16 يتراوح من 0 إلى 65535
# المحركات الشائعة (SG90/MG995) تستجيب لنبضات بين 0.5ms (0 درجة) و 2.5ms (180 درجة)
SERVO_FREQ         = 50
DUTY_HOME_0_DEG    = 1638  # ~0.5ms (وضع البداية / فتح مسار السير للزجاجة السليمة)
DUTY_REJECT_90_DEG = 4915  # ~1.5ms (زاوية الرفض 90 درجة لدفع الزجاجة المعيبة)
DUTY_MAX_180_DEG   = 8192  # ~2.5ms (أقصى زاوية 180 درجة)

# =============================================================================
# 🚀 تهيئة منافذ العتاد (Hardware Peripheral Setup)
# =============================================================================
# تهيئة الليدات كمخارج رقمية بقيمة ابتدائية 0 (مطفأة)
led_green = Pin(LED_GREEN_PIN, Pin.OUT, value=0)
led_red   = Pin(LED_RED_PIN, Pin.OUT, value=0)
led_blue  = Pin(LED_BLUE_PIN, Pin.OUT, value=0)

# تهيئة الصافرة كمخرج رقمي
buzzer = Pin(BUZZER_PIN, Pin.OUT, value=0)

# تهيئة السير الناقل: القيمة الافتراضية 1 (شغال باستمرار لنقل الزجاجات)
motor = Pin(MOTOR_PIN, Pin.OUT, value=1)

# تهيئة ريليه إضاءة الصندوق (Active HIGH: 1 = تشغيل، 0 = إطفاء)
RELAY_ACTIVE_LOW = False
box_light_relay = Pin(BOX_LIGHT_PIN, Pin.OUT)
box_light_state = False

def set_box_light(state_on):
    """التحكم بتشغيل وإطفاء إضاءة صندوق الفحص."""
    global box_light_state
    box_light_state = state_on
    if RELAY_ACTIVE_LOW:
        box_light_relay.value(0 if state_on else 1)
    else:
        box_light_relay.value(1 if state_on else 0)

set_box_light(False)  # الإضاءة مطفأة افتراضياً عند الإقلاع

# تهيئة حساس الألتراسونيك
trig = Pin(TRIG_PIN, Pin.OUT, value=0)
echo = Pin(ECHO_PIN, Pin.IN)

# تهيئة إشارة الـ PWM لمحرك السيرفو ووضعه في زاوية البداية (Home)
servo_pwm = PWM(Pin(SERVO_PIN), freq=SERVO_FREQ)
servo_pwm.duty_u16(DUTY_HOME_0_DEG)

# متغيرات الحالة الداخلية
current_distance_cm = 999.0
detect_threshold_cm = 45.0  # عتبة رصد وجود زجاجة (بالسنتيمتر)
bottle_detected = False
servo_state = "HOME"
reject_start_time = 0
reject_active = False

# مقاطع القراءة غير الحاجبة للمنفذ التسلسلي (uselect Poller)
poll_obj = uselect.poll()
poll_obj.register(sys.stdin, uselect.POLLIN)

# =============================================================================
# 🛠️ دوال تشغيل وحدات العتاد (Hardware Driver Routines)
# =============================================================================
def set_leds(green=False, red=False, blue=False):
    """التحكم بحالة الليدات الثلاثة معاً."""
    led_green.value(1 if green else 0)
    led_red.value(1 if red else 0)
    led_blue.value(1 if blue else 0)

def beep(duration_ms=150, freq=2500):
    """
    مشغل الصافرة الهجين:
    يدعم الصافرات السالبة (Passive Buzzer عبر توليد نغمة مربعة PWM)
    والصافرات الموجبة (Active Buzzer عبر جهد رقمي نبضي).
    """
    try:
        buzz_pwm = PWM(Pin(BUZZER_PIN), freq=freq)
        buzz_pwm.duty_u16(32768)  # دورة عمل 50%
        time.sleep_ms(duration_ms)
        buzz_pwm.deinit()
        Pin(BUZZER_PIN, Pin.OUT, value=0)
    except Exception:
        b_pin = Pin(BUZZER_PIN, Pin.OUT)
        b_pin.value(1)
        time.sleep_ms(duration_ms)
        b_pin.value(0)

def set_servo_angle(angle):
    """
    ضبط زاوية دوران السيرفو بدقة عبر الاستيفاء الخطي (Linear Interpolation).
    الزاوية بين 0 و 180 درجة.
    """
    global servo_state
    if angle <= 0:
        servo_pwm.duty_u16(DUTY_HOME_0_DEG)
        servo_state = "HOME"
    elif angle >= 180:
        servo_pwm.duty_u16(DUTY_MAX_180_DEG)
        servo_state = "MAX"
    else:
        duty = int(DUTY_HOME_0_DEG + (angle / 180.0) * (DUTY_MAX_180_DEG - DUTY_HOME_0_DEG))
        servo_pwm.duty_u16(duty)
        servo_state = f"ANGLE_{angle}"

def servo_home():
    """إرجاع السيرفو إلى زاوية الصفر لفتح مسار السير الناقل."""
    global reject_active
    set_servo_angle(0)
    reject_active = False

def trigger_reject(duration_ms=1200, angle=90):
    """تفعيل ذراع السيرفو لضرب وطرد الزجاجة المعيبة مع توقيت رجوع آلي."""
    global reject_active, reject_start_time
    set_servo_angle(angle)
    reject_active = True
    reject_start_time = time.ticks_ms()

def read_distance_cm():
    """
    قراءة المسافة بالسنتيمتر من حساس HC-SR04:
      1. إرسال نبضة إطلاق مدتها 10 ميكروثانية على رجل Trig.
      2. قياس زمن ارتداد النبضة على رجل Echo بالمايكروثانية.
      3. حساب المسافة اعتماداً على سرعة الصوت (343 م/ث): المسافة = (الزمن * 0.0343) / 2.
    """
    samples = []
    for _ in range(3):
        trig.value(0)
        time.sleep_us(2)
        trig.value(1)
        time.sleep_us(10)
        trig.value(0)

        try:
            duration_us = time_pulse_us(echo, 1, 30000)
            if duration_us > 0:
                dist = (duration_us * 0.0343) / 2.0
                if 1.0 <= dist <= 400.0:
                    samples.append(dist)
        except Exception:
            pass
        time.sleep_ms(8)

    if samples:
        return round(min(samples), 1)
    return 999.0

# =============================================================================
# 🚦 روتينات الاستجابة الصناعية (Inspection Actuation Routines)
# =============================================================================
def actuate_pass():
    """الزجاجة سليمة: ليد أخضر، إيقاف الصافرة، استمرار دوران السير، والسيرفو في وضع المرور."""
    set_leds(green=True, red=False, blue=False)
    Pin(BUZZER_PIN, Pin.OUT, value=0)
    motor.value(1)
    servo_home()
    print("ACK:PASS")

def actuate_fail(angle=90):
    """الزجاجة معيبة: ليد أحمر، نغمة إنذار صوتية، وتفعيل ذراع السيرفو لرفض الزجاجة."""
    set_leds(green=False, red=True, blue=False)
    trigger_reject(duration_ms=1400, angle=angle)
    beep(250, 2600)
    print(f"ACK:FAIL:{angle}")

def actuate_review():
    """حالة غير مؤكدة: ليد أزرق، السماح بمرورها للفحص البشري دون تعطيل السير."""
    set_leds(green=False, red=False, blue=True)
    buzzer.value(0)
    servo_home()
    print("ACK:REVIEW")

def get_status_json():
    """توليد سلسلة JSON مصغرة تلخص حالة كافة الحساسات والمشغلات."""
    return (
        f'{{"esp32":"ONLINE","distance_cm":{current_distance_cm},'
        f'"bottle_detected":{str(bottle_detected).lower()},'
        f'"motor":{"true" if motor.value() else "false"},'
        f'"box_light":{"true" if box_light_relay.value() else "false"},'
        f'"relay":{"true" if box_light_relay.value() else "false"},'
        f'"servo":"{servo_state}",'
        f'"led_green":{led_green.value()},'
        f'"led_red":{led_red.value()},'
        f'"led_blue":{led_blue.value()},'
        f'"buzzer":{buzzer.value()}}}'
    )

# =============================================================================
# 📥 معالج بروتوكول الأوامر التسلسلية (Serial Command Protocol Processor)
# =============================================================================
def process_command(cmd):
    """تفسير وتنفيذ الأوامر النصية الواردة عبر المنفذ التسلسلي من خادم بايثون."""
    cmd = cmd.strip().upper()
    if not cmd:
        return

    if cmd == "PING":
        print("PONG")
    elif cmd == "PASS":
        actuate_pass()
    elif cmd.startswith("FAIL") or cmd.startswith("REJECT"):
        target_angle = 90
        if ":" in cmd:
            try: target_angle = int(cmd.split(":")[1])
            except Exception: target_angle = 90
        actuate_fail(angle=target_angle)
    elif cmd.startswith("SERVO:") or cmd.startswith("SERVO_ANGLE:"):
        try:
            target_angle = int(cmd.split(":")[1])
            set_servo_angle(target_angle)
            print(f"ACK:SERVO:{target_angle}")
        except Exception:
            print("ERR:INVALID_ANGLE")
    elif cmd == "REVIEW":
        actuate_review()
    elif cmd == "MOTOR_ON":
        motor.value(1)
        print("ACK:MOTOR_ON")
    elif cmd == "MOTOR_OFF":
        motor.value(0)
        print("ACK:MOTOR_OFF")
    elif cmd in ["RELAY_ON", "LIGHT_ON", "BOX_LIGHT_ON"]:
        set_box_light(True)
        print("ACK:LIGHT_ON")
    elif cmd in ["RELAY_OFF", "LIGHT_OFF", "BOX_LIGHT_OFF"]:
        set_box_light(False)
        print("ACK:LIGHT_OFF")
    elif cmd == "SERVO_HOME":
        servo_home()
        print("ACK:SERVO_HOME")
    elif cmd == "GREEN":
        set_leds(green=True, red=False, blue=False)
        print("ACK:GREEN")
    elif cmd == "RED":
        set_leds(green=False, red=True, blue=False)
        print("ACK:RED")
    elif cmd == "BLUE":
        set_leds(green=False, red=False, blue=True)
        print("ACK:BLUE")
    elif cmd == "LEDS_OFF":
        set_leds(green=False, red=False, blue=False)
        print("ACK:LEDS_OFF")
    elif cmd == "BUZZER":
        beep(140, 2400)
        time.sleep_ms(50)
        beep(140, 3200)
        print("ACK:BUZZER")
    elif cmd == "BUZZER_ON":
        Pin(BUZZER_PIN, Pin.OUT, value=1)
        print("ACK:BUZZER_ON")
    elif cmd == "BUZZER_OFF":
        Pin(BUZZER_PIN, Pin.OUT, value=0)
        print("ACK:BUZZER_OFF")
    elif cmd == "DISTANCE":
        d = read_distance_cm()
        print(f"DISTANCE:{d}")
    elif cmd.startswith("THRESHOLD:"):
        global detect_threshold_cm
        try:
            val = float(cmd.split(":")[1])
            if 5.0 <= val <= 200.0:
                detect_threshold_cm = val
                print(f"ACK:THRESHOLD:{detect_threshold_cm}")
        except Exception:
            print("ERR:INVALID_THRESHOLD")
    elif cmd == "STATUS":
        print(f"STATUS:{get_status_json()}")
    elif cmd == "RESET":
        set_leds(green=False, red=False, blue=False)
        buzzer.value(0)
        servo_home()
        motor.value(1)
        print("ACK:RESET")
    else:
        print(f"ERR:UNKNOWN_CMD:{cmd}")

# =============================================================================
# 🔄 حلقة التشغيل اللحظية الرئيسية (Main Real-Time Executive Loop)
# =============================================================================
print("SMART_BOTTLE_ESP32_READY")

# إشارة ترحيب ضوئية عند الإقلاع
set_leds(green=True, red=True, blue=True)
time.sleep_ms(300)
set_leds(green=True, red=False, blue=False)  # مؤشر الجاهزية

last_sensor_read_time = 0
last_telemetry_time = 0

while True:
    now = time.ticks_ms()

    # 1. قراءة غير حاجبة للأوامر التسلسلية الواردة عبر USB
    if poll_obj.poll(0):
        line = sys.stdin.readline()
        if line:
            process_command(line)

    # 2. قراءة دورية لحساس الألتراسونيك (كل 60ms)
    if time.ticks_diff(now, last_sensor_read_time) >= 60:
        dist = read_distance_cm()
        current_distance_cm = dist
        new_bottle_detected = (1.0 < current_distance_cm <= detect_threshold_cm)
        if new_bottle_detected != bottle_detected:
            bottle_detected = new_bottle_detected
            if bottle_detected:
                print("EVENT:BOTTLE_DETECTED")
            else:
                print("EVENT:BOTTLE_CLEARED")
        last_sensor_read_time = now

    # 3. بث قراءة المسافة اللحظية كل 100ms لتحديث واجهة SCADA وراسم الإشارة
    if time.ticks_diff(now, last_telemetry_time) >= 100:
        print("DISTANCE:{:.1f}".format(current_distance_cm))
        last_telemetry_time = now

    # 4. التحقق من توقيت رجوع ذراع السيرفو التلقائي بعد انتهاء الطرد (1200ms)
    if reject_active and time.ticks_diff(now, reject_start_time) >= 1200:
        servo_home()

    # تأخير دقيق للحفاظ على برودة المعالج مع الحفاظ على سرعة الاستجابة اللحظية
    time.sleep_ms(10)
