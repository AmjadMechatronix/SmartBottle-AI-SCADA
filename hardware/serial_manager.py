"""
=============================================================================
Smart Bottle Inspection System - Hardware Serial Manager
=============================================================================
Manages low-level USB Serial connection with ESP32 (MicroPython).
Includes automatic port detection, auto-reconnect thread, thread-safe I/O,
and transparent virtual fallback mode when physical hardware is not connected.
=============================================================================
"""

import time
import threading
import logging
import json
import serial
import serial.tools.list_ports
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SerialManager")

class SerialManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SerialManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, port=None, baudrate=None):
        if self._initialized:
            return
        self._initialized = True

        self.configured_port = port or config.SERIAL_PORT
        self.baudrate = baudrate or config.SERIAL_BAUDRATE
        self.serial_conn = None
        self.active_port = None
        self.is_connected = False
        self.is_running = True
        self.io_lock = threading.Lock()

        # Telemetry Cache
        self.last_status = {
            "esp32": "OFFLINE",
            "distance_cm": 999.0,
            "bottle_detected": False,
            "motor": True,
            "servo": "HOME",
            "led_green": 0,
            "led_red": 0,
            "led_blue": 0,
            "buzzer": 0,
            "relay": False,
            "box_light": "OFF",
            "port": "NONE",
            "is_simulated": False
        }

        # Event Callbacks
        self.distance_threshold = getattr(config, 'BOTTLE_DETECT_DISTANCE_CM', 50.0)
        self.on_bottle_detected_cb = None
        self.on_bottle_cleared_cb = None

        # Start Background Reader & Reconnect Thread
        self.reader_thread = threading.Thread(target=self._connection_and_read_loop, daemon=True)
        self.reader_thread.start()

    def _find_esp32_port(self):
        """Auto-detect ESP32 / USB Serial COM ports."""
        ports = serial.tools.list_ports.comports()
        for p in ports:
            desc = p.description.lower()
            hwid = p.hwid.lower()
            # Common ESP32 USB-to-UART chips: CH340, CP210x, FTDI, USB Serial
            if any(k in desc or k in hwid for k in ["ch340", "cp210", "ftdi", "usb serial", "uart", "espressif"]):
                return p.device
        if ports:
            # Fallback to first available port if port description is generic
            return ports[0].device
        return None

    def connect(self):
        """Attempt to connect to physical ESP32."""
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
                time.sleep(1.5) # Wait for ESP32 boot/reset
                self.active_port = target_port
                self.is_connected = True
                self.last_status["esp32"] = "ONLINE"
                self.last_status["port"] = target_port
                self.last_status["is_simulated"] = False
                logger.info(f"✅ ESP32 Connected successfully on port: {target_port}")
                
                # Test ping
                self._send_raw("PING\n")
                return True
            except Exception as e:
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
                self.last_status["is_simulated"] = True
                logger.warning(f"⚠️ Could not open serial port {target_port}: {e}")
                return False

    def disconnect(self):
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
        """Send string over serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(data_str.encode("utf-8"))
                self.serial_conn.flush()
                return True
            except Exception as e:
                logger.error(f"Serial write error: {e}")
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
        return False

    def send_command(self, cmd):
        """Thread-safe public command sender with virtual hardware fallback."""
        cmd = cmd.strip().upper()
        logger.info(f"📡 Sending Hardware Command: {cmd}")

        # If physical ESP32 is connected, transmit over Serial
        if self.is_connected:
            with self.io_lock:
                success = self._send_raw(f"{cmd}\n")
                if success:
                    self._simulate_hardware_command(cmd)
                    return {"status": "success", "mode": "hardware", "command": cmd}

        # Virtual simulation fallback
        self._simulate_hardware_command(cmd)
        return {"status": "success", "mode": "simulated", "command": cmd}

    def _simulate_hardware_command(self, cmd):
        """Update internal state in simulation mode when physical hardware is not present."""
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
                try: ang = int(cmd.split(":")[1])
                except Exception: pass
            self.last_status["led_green"] = 0
            self.last_status["led_red"] = 1
            self.last_status["led_blue"] = 0
            self.last_status["servo"] = f"REJECT_{ang}"
            self.last_status["buzzer"] = 1
            # Simulate auto-return of servo
            threading.Timer(1.2, lambda: self.last_status.update({"servo": "HOME", "buzzer": 0})).start()
        elif cmd.startswith("SERVO:"):
            try:
                ang = int(cmd.split(":")[1])
                self.last_status["servo"] = f"ANGLE_{ang}"
            except Exception: pass
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
        """Background thread handling continuous serial telemetry reading & auto-reconnect."""
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
                logger.warning(f"Serial read interrupted: {e}")
                self.is_connected = False
                self.last_status["esp32"] = "OFFLINE"
                time.sleep(1.0)

    def _handle_incoming_telemetry(self, line):
        """Parse events and status from ESP32."""
        logger.info(f"📥 ESP32 RESP: {line}")
        if line == "EVENT:BOTTLE_DETECTED":
            self.last_status["bottle_detected"] = True
            logger.info("🍼 EVENT: Bottle Detected by Ultrasonic Sensor")
            if self.on_bottle_detected_cb:
                try:
                    self.on_bottle_detected_cb()
                except Exception as e:
                    logger.error(f"Error in on_bottle_detected callback: {e}")
        elif line == "EVENT:BOTTLE_CLEARED":
            self.last_status["bottle_detected"] = False
            if self.on_bottle_cleared_cb:
                try:
                    self.on_bottle_cleared_cb()
                except Exception as e:
                    logger.error(f"Error in on_bottle_cleared callback: {e}")
        elif line.startswith("STATUS:"):
            try:
                json_str = line[7:]
                status_dict = json.loads(json_str)
                self.last_status.update(status_dict)
                self.last_status["esp32"] = "ONLINE"
                self.last_status["is_simulated"] = False
            except Exception:
                pass
        elif line in ["ACK:LIGHT_ON", "ACK:RELAY_ON"]:
            self.last_status["relay"] = True
            self.last_status["box_light"] = "ON"
        elif line in ["ACK:LIGHT_OFF", "ACK:RELAY_OFF"]:
            self.last_status["relay"] = False
            self.last_status["box_light"] = "OFF"
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
        """Return current hardware status snapshot with standardized fields."""
        st = dict(self.last_status)
        
        # Computed human-friendly string fields
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
