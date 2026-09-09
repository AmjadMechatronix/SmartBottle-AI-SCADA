"""
=============================================================================
Smart Bottle Inspection System - ESP32 MicroPython Firmware
=============================================================================
Board: ESP32 (NodeMCU / DevKit v1)
Language: MicroPython
Communication: USB Serial UART (115200 baud)

Hardware Responsibilities:
  1. Ultrasonic Sensor (HC-SR04): Bottle proximity detection

  2. Conveyor DC Motor: via L298N / Relay / MOSFET Driver

  3. Reject Servo Motor: SG90 / MG995 / MG996R (PWM)

  4. Status LEDs: Green (PASS), Red (FAIL), Blue (REVIEW/BUSY)

  5. Buzzer: Audible alarm for defective bottles

  6. Serial Protocol: Two-way command processing & telemetry

  
=============================================================================
"""

import sys
import time
import uselect
from machine import Pin, PWM, time_pulse_us

# =============================================================================
# 📌 PIN CONFIGURATION (Matches your exact hardware wiring)
# =============================================================================
# Status LEDs
LED_GREEN_PIN = 2   # Green LED (PASS) - عبر مقاومة 220Ω
LED_RED_PIN   = 4   # Red LED (FAIL / Alarm) - عبر مقاومة 220Ω
LED_BLUE_PIN  = 5   # Blue LED (REVIEW / Processing) - عبر مقاومة 220Ω

# Alarm Buzzer
BUZZER_PIN    = 18  # Active/Passive Buzzer (+)

# Ultrasonic Sensor (HC-SR04)
# ⚠️ خط ECHO يدخل عبر Voltage Divider (مقسم جهد) لحماية مدخل ESP32 3.3V
TRIG_PIN      = 19  # Trigger output
ECHO_PIN      = 21  # Echo input (عبر Voltage Divider)

# Conveyor Motor Driver (L298N / Relay / MOSFET)
MOTOR_PIN     = 22  # Motor Driver IN / Signal

# Reject Mechanism Servo Motor (SG90 / MG995 / MG996R)
SERVO_PIN     = 23  # Servo Signal (PWM 50Hz)

# Inspection Box Light Relay
BOX_LIGHT_PIN = 13  # Relay IN for Box Light (GPIO 25)

# =============================================================================
# ⚙️ SERVO PWM CALIBRATION (50Hz = 20ms period)
# =============================================================================
SERVO_FREQ         = 50
# MicroPython duty_u16 range: 0 - 65535
# SG90 / MG995 typical pulses: 0.5ms (0 deg) to 2.5ms (180 deg)
DUTY_HOME_0_DEG    = 1638  # ~0.5ms (Home / Normal pass position)
DUTY_REJECT_90_DEG = 4915  # ~1.5ms (Reject angle / Push bottle)
DUTY_MAX_180_DEG   = 8192  # ~2.5ms

# =============================================================================
# 🚀 HARDWARE INITIALIZATION
# =============================================================================
# 1. LEDs Setup
led_green = Pin(LED_GREEN_PIN, Pin.OUT, value=0)
led_red   = Pin(LED_RED_PIN, Pin.OUT, value=0)
led_blue  = Pin(LED_BLUE_PIN, Pin.OUT, value=0)

# 2. Buzzer Setup
buzzer = Pin(BUZZER_PIN, Pin.OUT, value=0)

# 3. Motor Setup
motor = Pin(MOTOR_PIN, Pin.OUT, value=1) # Default: Conveyor Running

# 3b. Box Light Relay Setup (GPIO 25)
# Set to False because relay is Active HIGH (1 = ON, 0 = OFF)
RELAY_ACTIVE_LOW = False
box_light_relay = Pin(BOX_LIGHT_PIN, Pin.OUT)
box_light_state = False

def set_box_light(state_on):
    global box_light_state
    box_light_state = state_on
    if RELAY_ACTIVE_LOW:
        box_light_relay.value(0 if state_on else 1)
    else:
        box_light_relay.value(1 if state_on else 0)

set_box_light(False) # Ensure light is OFF initially

# 4. Ultrasonic Sensor Setup
trig = Pin(TRIG_PIN, Pin.OUT, value=0)
echo = Pin(ECHO_PIN, Pin.IN)

# 5. Servo Setup
servo_pwm = PWM(Pin(SERVO_PIN), freq=SERVO_FREQ)
servo_pwm.duty_u16(DUTY_HOME_0_DEG)

# Global State
current_distance_cm = 999.0
detect_threshold_cm = 45.0 # Default threshold (supports up to 45cm)
bottle_detected = False
servo_state = "HOME" # "HOME" or "REJECT"
reject_start_time = 0
reject_active = False

# USB Serial Non-blocking Poller
poll_obj = uselect.poll()
poll_obj.register(sys.stdin, uselect.POLLIN)

# =============================================================================
# 🛠️ HARDWARE DRIVER FUNCTIONS
# =============================================================================
def set_leds(green=False, red=False, blue=False):
    led_green.value(1 if green else 0)
    led_red.value(1 if red else 0)
    led_blue.value(1 if blue else 0)

def beep(duration_ms=150, freq=2500):
    """
    🔊 Dual-Mode Buzzer Driver:
    Supports both Passive Buzzers (requires PWM oscillating tone)
    and Active Buzzers (DC/pulsed voltage).
    """
    try:
        buzz_pwm = PWM(Pin(BUZZER_PIN), freq=freq)
        buzz_pwm.duty_u16(32768)  # 50% duty square wave
        time.sleep_ms(duration_ms)
        buzz_pwm.deinit()
        Pin(BUZZER_PIN, Pin.OUT, value=0)
    except Exception:
        # Fallback to standard digital HIGH
        b_pin = Pin(BUZZER_PIN, Pin.OUT)
        b_pin.value(1)
        time.sleep_ms(duration_ms)
        b_pin.value(0)

def set_servo_angle(angle):
    global servo_state
    # Angle in degrees (0 to 180)
    if angle <= 0:
        servo_pwm.duty_u16(DUTY_HOME_0_DEG)
        servo_state = "HOME"
    elif angle >= 180:
        servo_pwm.duty_u16(DUTY_MAX_180_DEG)
        servo_state = "MAX"
    else:
        # Linear interpolation between 0 and 180 deg
        duty = int(DUTY_HOME_0_DEG + (angle / 180.0) * (DUTY_MAX_180_DEG - DUTY_HOME_0_DEG))
        servo_pwm.duty_u16(duty)
        servo_state = f"ANGLE_{angle}"

def servo_home():
    global reject_active
    set_servo_angle(0)
    reject_active = False

def trigger_reject(duration_ms=1200, angle=90):
    global reject_active, reject_start_time
    set_servo_angle(angle)
    reject_active = True
    reject_start_time = time.ticks_ms()

def read_distance_cm():
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
# 🚦 HIGH-LEVEL INSPECTION ACTUATION ROUTINES
# =============================================================================
def actuate_pass():
    set_leds(green=True, red=False, blue=False)
    Pin(BUZZER_PIN, Pin.OUT, value=0)
    motor.value(1) # Keep conveyor moving
    servo_home()
    print("ACK:PASS")

def actuate_fail(angle=90):
    set_leds(green=False, red=True, blue=False)
    trigger_reject(duration_ms=1400, angle=angle)
    # Auditory alert tone
    beep(250, 2600)
    print(f"ACK:FAIL:{angle}")

def actuate_review():
    set_leds(green=False, red=False, blue=True)
    buzzer.value(0)
    # In review, we do not reject blindly; allow bottle to pass or stop for manual check
    servo_home()
    print("ACK:REVIEW")

def get_status_json():
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
# 📥 SERIAL COMMAND PROTOCOL PROCESSOR
# =============================================================================
def process_command(cmd):
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
            try:
                target_angle = int(cmd.split(":")[1])
            except Exception:
                target_angle = 90
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
        # Multi-chirp tone (2400Hz then 3200Hz) - audible on passive & active buzzers
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
# 🔄 MAIN REAL-TIME SYSTEM LOOP
# =============================================================================
print("SMART_BOTTLE_ESP32_READY")
set_leds(green=True, red=True, blue=True) # Startup test blink
time.sleep_ms(300)
set_leds(green=True, red=False, blue=False) # Ready state

last_sensor_read_time = 0
last_telemetry_time = 0

while True:
    now = time.ticks_ms()

    # 1. Non-blocking Serial Input Check
    if poll_obj.poll(0):
        line = sys.stdin.readline()
        if line:
            process_command(line)

    # 2. Periodic Ultrasonic Reading (Every 60ms)
    if time.ticks_diff(now, last_sensor_read_time) >= 60:
        dist = read_distance_cm()
        current_distance_cm = dist
        # Bottle threshold dynamically matched with detect_threshold_cm
        new_bottle_detected = (1.0 < current_distance_cm <= detect_threshold_cm)
        if new_bottle_detected != bottle_detected:
            bottle_detected = new_bottle_detected
            if bottle_detected:
                print("EVENT:BOTTLE_DETECTED")
            else:
                print("EVENT:BOTTLE_CLEARED")
        last_sensor_read_time = now

    # 3. Continuous Distance Synchronization (Every 100ms for fast real-time updates)
    if time.ticks_diff(now, last_telemetry_time) >= 100:
        print("DISTANCE:{:.1f}".format(current_distance_cm))
        last_telemetry_time = now

    # 4. Servo Auto-Return Timing Check
    if reject_active and time.ticks_diff(now, reject_start_time) >= 1200:
        servo_home()

    # Small delay to keep CPU cool while maintaining responsiveness
    time.sleep_ms(10)
