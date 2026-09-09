"""
=============================================================================
Smart Bottle Inspection System - High-Level ESP32 Controller
=============================================================================
Provides clean, high-level Python API for industrial hardware operations:
  - Inspection Actuations: actuate_pass(), actuate_fail(), actuate_review()
  - Actuator Controls: motor_on(), motor_off(), servo_reject(), servo_home()
  - Indicators & Alarms: set_led(), trigger_buzzer()
  - Telemetry: get_distance(), get_status()
=============================================================================
"""

import logging
import json
import urllib.request
import config
from hardware.serial_manager import SerialManager

logger = logging.getLogger("ESP32Controller")

class ESP32Controller:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ESP32Controller, cls).__new__(cls)
            cls._instance.serial_manager = SerialManager()
            cls._instance.wifi_ip = getattr(config, "ESP32_CONTROLLER_IP", None)
            cls._instance.comm_mode = getattr(config, "ESP32_COMM_MODE", "AUTO")
        return cls._instance

    def send_command(self, cmd):
        """
        Unified Command Dispatcher:
        Tries Wi-Fi REST API if configured and enabled, otherwise falls back to Serial UART.
        """
        cmd_clean = cmd.strip().upper()
        mode = getattr(config, "ESP32_COMM_MODE", "AUTO")
        wifi_url = getattr(config, "ESP32_CONTROLLER_IP", None)

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
                    logger.warning(f"⚠️ Wi-Fi command error: {e}")
                    return {"status": "error", "error": str(e), "channel": "WIFI"}

        # Fallback to USB Serial
        return self.serial_manager.send_command(cmd_clean)

    # ==========================================
    # High-Level Inspection Actuation Routines
    # ==========================================
    def actuate_pass(self):
        """Actuate Normal / PASS behavior: Green LED ON, Motor running, Servo Home."""
        logger.info("🟢 ACTUATION: PASS (Green LED | Conveyor Running | Servo Home)")
        return self.send_command("PASS")

    def actuate_fail(self, angle=None):
        """Actuate Defect / FAIL behavior: Red LED ON, Buzzer beep, Servo Reject bottle."""
        ang = angle if angle is not None else getattr(config, "SERVO_REJECT_ANGLE", 90)
        logger.warning(f"🔴 ACTUATION: FAIL / DEFECT (Red LED | Buzzer Alarm | Servo Reject {ang}°)")
        if ang == 90:
            return self.send_command("FAIL")
        return self.send_command(f"FAIL:{ang}")

    def actuate_review(self):
        """Actuate Low-Confidence / REVIEW behavior: Blue LED ON, Flag for operator."""
        logger.info("🔵 ACTUATION: REVIEW / UNCERTAIN (Blue LED | Pass without reject)")
        return self.send_command("REVIEW")

    # ==========================================
    # Direct Actuator & Motor Controls
    # ==========================================
    def motor_on(self):
        """Turn Conveyor DC Motor ON."""
        logger.info("⚙️ Motor: ON")
        return self.send_command("MOTOR_ON")

    def motor_off(self):
        """Turn Conveyor DC Motor OFF."""
        logger.info("⚙️ Motor: OFF")
        return self.send_command("MOTOR_OFF")

    def relay_on(self):
        """Turn Industrial Relay ON (GPIO 25)."""
        logger.info("⚡ Relay: ON")
        return self.send_command("RELAY_ON")

    def relay_off(self):
        """Turn Industrial Relay OFF (GPIO 25)."""
        logger.info("⚡ Relay: OFF")
        return self.send_command("RELAY_OFF")

    def servo_reject(self, angle=None):
        """Trigger Servo Reject arm sweep."""
        ang = angle if angle is not None else getattr(config, "SERVO_REJECT_ANGLE", 90)
        logger.info(f"🦾 Servo: REJECT Sweep ({ang}°)")
        if ang == 90:
            return self.send_command("REJECT")
        return self.send_command(f"REJECT:{ang}")

    def servo_home(self, angle=None):
        """Return Servo to Home position."""
        ang = angle if angle is not None else getattr(config, "SERVO_HOME_ANGLE", 0)
        logger.info(f"🦾 Servo: HOME Position ({ang}°)")
        if ang == 0:
            return self.send_command("SERVO_HOME")
        return self.send_command(f"SERVO:{ang}")

    def set_servo_angle(self, angle):
        """Directly set Servo angle (0-180 deg)."""
        logger.info(f"🦾 Servo: Set Angle {angle}°")
        return self.send_command(f"SERVO:{angle}")

    # ==========================================
    # Indicators & Alarms
    # ==========================================
    def set_led(self, color):
        """Set LED status color ('green', 'red', 'blue', 'off')."""
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
        """Trigger buzzer alarm beep."""
        return self.send_command("BUZZER")

    # ==========================================
    # Telemetry & Status
    # ==========================================
    def get_distance(self):
        """Request live ultrasonic distance reading (cm)."""
        self.send_command("DISTANCE")
        status = self.serial_manager.get_status()
        return status.get("distance_cm", 999.0)

    def get_status(self):
        """Get full hardware status snapshot."""
        return self.serial_manager.get_status()

    def reset(self):
        """Reset hardware actuators to default ready state."""
        logger.info("🔄 Hardware Reset Requested")
        return self.send_command("RESET")

    def set_bottle_callback(self, on_detected=None, on_cleared=None):
        """Register event callbacks for ultrasonic proximity trigger."""
        if on_detected:
            self.serial_manager.on_bottle_detected_cb = on_detected
        if on_cleared:
            self.serial_manager.on_bottle_cleared_cb = on_cleared
