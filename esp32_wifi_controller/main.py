"""
=============================================================================
Smart Bottle Inspection System - ESP32 Network / Wi-Fi Controller Firmware
=============================================================================
Board: ESP32 (NodeMCU / DevKit v1)
Language: MicroPython
Network: Wi-Fi (SSID: Future2027) + HTTP REST API Server
Fallback: USB Serial UART (115200 baud)

Hardware Responsibilities:
  1. Wi-Fi Connection & HTTP REST Server (Port 80)
  2. Conveyor DC Motor (L298N / Driver on GPIO 22)
  3. Additional Industrial Relay (GPIO 25)
  4. Reject Servo Motor (SG90 / MG995 / MG996R on GPIO 23)
  5. Ultrasonic Sensor (HC-SR04 on Trig 19, Echo 21)
  6. Status LEDs: Green (GPIO 2), Red (GPIO 4), Blue (GPIO 5)
  7. Buzzer Alarm (GPIO 18)
=============================================================================
"""

import sys
import time
import network
import socket
import uselect
from machine import Pin, PWM, time_pulse_us

# =============================================================================
# 🌐 WI-FI NETWORK CONFIGURATION
# =============================================================================
WIFI_SSID = "Future2027"
WIFI_PASS = ""  # شبكة مفتوحة بدون كلمة سر
SERVER_PORT = 80

# =============================================================================
# 📌 PIN CONFIGURATION
# =============================================================================
LED_GREEN_PIN = 2   # Green LED (PASS)
LED_RED_PIN   = 4   # Red LED (FAIL / Alarm)
LED_BLUE_PIN  = 5   # Blue LED (REVIEW)

BUZZER_PIN    = 18  # Alarm Buzzer (+)
TRIG_PIN      = 19  # Ultrasonic Trigger
ECHO_PIN      = 21  # Ultrasonic Echo

MOTOR_PIN     = 22  # Conveyor Motor Driver IN / Signal
SERVO_PIN     = 23  # Reject Servo PWM
RELAY_PIN     = 25  # Additional Relay (e.g. Pump / Light / Valve)

# =============================================================================
# ⚙️ SERVO PWM CALIBRATION (50Hz)
# =============================================================================
SERVO_FREQ         = 50
DUTY_HOME_0_DEG    = 1638  # ~0.5ms (Home / Normal pass position)
DUTY_REJECT_90_DEG = 4915  # ~1.5ms (Reject angle)
DUTY_MAX_180_DEG   = 8192  # ~2.5ms

# =============================================================================
# 🚀 HARDWARE INITIALIZATION
# =============================================================================
led_green = Pin(LED_GREEN_PIN, Pin.OUT, value=0)
led_red   = Pin(LED_RED_PIN, Pin.OUT, value=0)
led_blue  = Pin(LED_BLUE_PIN, Pin.OUT, value=0)

buzzer = Pin(BUZZER_PIN, Pin.OUT, value=0)
# Additional Relay / Box Light Setup (GPIO 25)
RELAY_ACTIVE_LOW = False
relay = Pin(RELAY_PIN, Pin.OUT)
relay_state = False

def set_box_light(state_on):
    global relay_state
    relay_state = state_on
    if RELAY_ACTIVE_LOW:
        relay.value(0 if state_on else 1)
    else:
        relay.value(1 if state_on else 0)

set_box_light(False) # Default: Light OFF

trig = Pin(TRIG_PIN, Pin.OUT, value=0)
echo = Pin(ECHO_PIN, Pin.IN)

servo_pwm = PWM(Pin(SERVO_PIN), freq=SERVO_FREQ)
servo_pwm.duty_u16(DUTY_HOME_0_DEG)

current_distance_cm = 999.0
bottle_detected = False
servo_state = "HOME"
reject_active = False
reject_start_time = 0

# Serial Poller
serial_poll = uselect.poll()
serial_poll.register(sys.stdin, uselect.POLLIN)

# =============================================================================
# 📶 WI-FI CONNECTION ROUTINE
# =============================================================================
wlan = network.WLAN(network.STA_IF)

def connect_wifi():
    wlan.active(True)
    if not wlan.isconnected():
        print(f"📡 Connecting to Wi-Fi: {WIFI_SSID}...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        attempts = 0
        while not wlan.isconnected() and attempts < 25:
            led_blue.value(1)
            time.sleep_ms(200)
            led_blue.value(0)
            time.sleep_ms(200)
            attempts += 1
            print(".", end="")
        print("")
        
    if wlan.isconnected():
        ip_info = wlan.ifconfig()
        print("=" * 55)
        print("✅ Wi-Fi Connected Successfully!")
        print(f"🎯 ESP32 Controller IP: {ip_info[0]}")
        print(f"🌐 REST API Base URL:  http://{ip_info[0]}/api/")
        print("=" * 55)
        led_blue.value(1)
        time.sleep_ms(500)
        led_blue.value(0)
        return ip_info[0]
    else:
        print("⚠️ Failed to connect to Wi-Fi. Operating in Serial-only mode.")
        return None

# =============================================================================
# 🛠️ HARDWARE DRIVER FUNCTIONS
# =============================================================================
def set_leds(green=False, red=False, blue=False):
    led_green.value(1 if green else 0)
    led_red.value(1 if red else 0)
    led_blue.value(1 if blue else 0)

def beep(duration_ms=150, freq=2500):
    try:
        buzz_pwm = PWM(Pin(BUZZER_PIN), freq=freq)
        buzz_pwm.duty_u16(32768)
        time.sleep_ms(duration_ms)
        buzz_pwm.deinit()
        Pin(BUZZER_PIN, Pin.OUT, value=0)
    except Exception:
        b_pin = Pin(BUZZER_PIN, Pin.OUT)
        b_pin.value(1)
        time.sleep_ms(duration_ms)
        b_pin.value(0)

def set_servo_angle(angle):
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
    global reject_active
    set_servo_angle(0)
    reject_active = False

def trigger_reject(duration_ms=1200, angle=90):
    global reject_active, reject_start_time
    set_servo_angle(angle)
    reject_active = True
    reject_start_time = time.ticks_ms()

def read_distance_cm():
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    try:
        duration_us = time_pulse_us(echo, 1, 30000)
        if duration_us > 0:
            return round((duration_us * 0.0343) / 2.0, 1)
    except Exception:
        pass
    return 999.0

# Inspection Routines
def actuate_pass():
    set_leds(green=True, red=False, blue=False)
    Pin(BUZZER_PIN, Pin.OUT, value=0)
    motor.value(1)
    servo_home()
    print("ACK:PASS")

def actuate_fail(angle=90):
    set_leds(green=False, red=True, blue=False)
    trigger_reject(duration_ms=1400, angle=angle)
    beep(250, 2600)
    print(f"ACK:FAIL:{angle}")

def actuate_review():
    set_leds(green=False, red=False, blue=True)
    buzzer.value(0)
    servo_home()
    print("ACK:REVIEW")

def get_status_json():
    return (
        f'{{"esp32":"ONLINE","mode":"WIFI","ip":"{wlan.ifconfig()[0] if wlan.isconnected() else "NONE"}",'
        f'"distance_cm":{current_distance_cm},"bottle_detected":{str(bottle_detected).lower()},'
        f'"motor":{"true" if motor.value() else "false"},"relay":{"true" if relay.value() else "false"},'
        f'"servo":"{servo_state}",'
        f'"led_green":{led_green.value()},"led_red":{led_red.value()},"led_blue":{led_blue.value()},'
        f'"buzzer":{buzzer.value()}}}'
    )

# =============================================================================
# 📥 COMMAND PROCESSOR (Used by both HTTP and USB Serial)
# =============================================================================
def process_command(cmd):
    cmd = cmd.strip().upper()
    if not cmd:
        return "ERROR:EMPTY"

    if cmd == "PING":
        return "PONG"
    elif cmd in ["PASS", "ACTUATE_PASS"]:
        actuate_pass()
        return "ACK:PASS"
    elif cmd.startswith("FAIL") or cmd.startswith("REJECT") or cmd.startswith("ACTUATE_FAIL"):
        target_angle = 90
        if ":" in cmd:
            try:
                target_angle = int(cmd.split(":")[1])
            except Exception:
                target_angle = 90
        actuate_fail(angle=target_angle)
        return f"ACK:FAIL:{target_angle}"
    elif cmd.startswith("SERVO:") or cmd.startswith("SERVO_ANGLE:"):
        try:
            target_angle = int(cmd.split(":")[1])
            set_servo_angle(target_angle)
            return f"ACK:SERVO:{target_angle}"
        except Exception:
            return "ERROR:INVALID_ANGLE"
    elif cmd in ["REVIEW", "ACTUATE_REVIEW"]:
        actuate_review()
        return "ACK:REVIEW"
    elif cmd == "MOTOR_ON":
        motor.value(1)
        return "ACK:MOTOR_ON"
    elif cmd == "MOTOR_OFF":
        motor.value(0)
        return "ACK:MOTOR_OFF"
    elif cmd in ["RELAY_ON", "LIGHT_ON", "BOX_LIGHT_ON"]:
        set_box_light(True)
        return "ACK:LIGHT_ON"
    elif cmd in ["RELAY_OFF", "LIGHT_OFF", "BOX_LIGHT_OFF"]:
        set_box_light(False)
        return "ACK:LIGHT_OFF"
    elif cmd == "SERVO_HOME":
        servo_home()
        return "ACK:SERVO_HOME"
    elif cmd == "GREEN":
        set_leds(green=True, red=False, blue=False)
        return "ACK:GREEN"
    elif cmd == "RED":
        set_leds(green=False, red=True, blue=False)
        return "ACK:RED"
    elif cmd == "BLUE":
        set_leds(green=False, red=False, blue=True)
        return "ACK:BLUE"
    elif cmd == "LEDS_OFF":
        set_leds(green=False, red=False, blue=False)
        return "ACK:LEDS_OFF"
    elif cmd == "BUZZER":
        beep(140, 2400)
        return "ACK:BUZZER"
    elif cmd == "STATUS":
        return get_status_json()
    elif cmd == "DISTANCE":
        d = read_distance_cm()
        return f'{{"distance_cm":{d}}}'
    elif cmd == "RESET":
        set_leds(green=False, red=False, blue=False)
        servo_home()
        motor.value(1)
        relay.value(0)
        return "ACK:RESET"
    else:
        return "ERROR:UNKNOWN_CMD"

# =============================================================================
# 🌐 LIGHTWEIGHT HTTP REST API SERVER (Socket)
# =============================================================================
server_socket = None

def init_http_server():
    global server_socket
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', SERVER_PORT))
        server_socket.listen(5)
        server_socket.setblocking(False)
        print(f"🚀 HTTP Server listening on port {SERVER_PORT}...")
    except Exception as e:
        print(f"⚠️ HTTP Server init error: {e}")
        server_socket = None

def handle_http_clients():
    if server_socket is None:
        return

    try:
        conn, addr = server_socket.accept()
    except Exception:
        return

    try:
        conn.settimeout(0.5)
        request_bytes = conn.recv(512)
        if not request_bytes:
            conn.close()
            return

        request_str = request_bytes.decode('utf-8', 'ignore')
        first_line = request_str.split('\r\n')[0]
        parts = first_line.split(' ')
        if len(parts) < 2:
            conn.close()
            return

        method = parts[0]
        path = parts[1].split('?')[0].strip('/')
        
        cmd = None
        if path in ["api/pass", "pass"]:
            cmd = "PASS"
        elif path in ["api/fail", "fail"]:
            cmd = "FAIL"
        elif path in ["api/review", "review"]:
            cmd = "REVIEW"
        elif path in ["api/motor/on", "motor/on"]:
            cmd = "MOTOR_ON"
        elif path in ["api/motor/off", "motor/off"]:
            cmd = "MOTOR_OFF"
        elif path in ["api/relay/on", "relay/on"]:
            cmd = "RELAY_ON"
        elif path in ["api/relay/off", "relay/off"]:
            cmd = "RELAY_OFF"
        elif path in ["api/servo/reject", "servo/reject"]:
            cmd = "REJECT"
        elif path.startswith("api/servo/reject/") or path.startswith("servo/reject/"):
            val = path.split('/')[-1]
            cmd = f"REJECT:{val}"
        elif path.startswith("api/servo/set/") or path.startswith("api/servo/angle/"):
            val = path.split('/')[-1]
            cmd = f"SERVO:{val}"
        elif path in ["api/servo/home", "servo/home"]:
            cmd = "SERVO_HOME"
        elif path in ["api/status", "status"]:
            cmd = "STATUS"
        elif path in ["api/distance", "distance"]:
            cmd = "DISTANCE"
        elif path.startswith("api/cmd/"):
            cmd = path.replace("api/cmd/", "")

        if cmd:
            response_body = process_command(cmd)
            is_json = response_body.startswith('{')
            content_type = "application/json" if is_json else "text/plain"
            header = (
                "HTTP/1.1 200 OK\r\n"
                f"Content-Type: {content_type}\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n\r\n"
            )
            conn.sendall(header.encode() + response_body.encode())
        else:
            header = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nRoute Not Found"
            conn.sendall(header.encode())

    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

# =============================================================================
# 🔄 MAIN REAL-TIME SCHEDULING LOOP
# =============================================================================
connect_wifi()
init_http_server()

last_ultrasonic_time = 0
last_wifi_check = 0

print("\n🎉 ESP32 Network Controller is fully running & ready for commands!")

while True:
    now = time.ticks_ms()

    # 1. Handle HTTP Clients (Wireless REST Requests)
    handle_http_clients()

    # 2. Handle USB Serial Commands (Wired Fallback)
    if serial_poll.poll(0):
        line = sys.stdin.readline()
        if line:
            resp = process_command(line)
            print(resp)

    # 3. Servo Auto-Return Timer (1.2 - 1.4s reject duration)
    if reject_active and time.ticks_diff(now, reject_start_time) > 1400:
        servo_home()

    # 4. Periodic Ultrasonic Sampling (Every 150ms)
    if time.ticks_diff(now, last_ultrasonic_time) > 150:
        last_ultrasonic_time = now
        d = read_distance_cm()
        current_distance_cm = d
        if 1.0 < d <= 25.0 and not bottle_detected:
            bottle_detected = True
            print(f"EVENT:BOTTLE_DETECTED:{d}")
        elif (d > 27.0 or d < 1.0) and bottle_detected:
            bottle_detected = False
            print(f"EVENT:BOTTLE_CLEARED:{d}")

    # 5. Periodic Wi-Fi Reconnect Watchdog (Every 10 seconds)
    if time.ticks_diff(now, last_wifi_check) > 10000:
        last_wifi_check = now
        if not wlan.isconnected():
            print("⚠️ Wi-Fi disconnected! Reconnecting...")
            wlan.connect(WIFI_SSID, WIFI_PASS)

    time.sleep_ms(5)
