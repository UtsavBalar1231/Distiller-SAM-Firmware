"""
SAM Display Control Handler for RP2040

This module handles e-ink display control commands from the Linux host
and integrates with the existing einkDSP_SAM driver.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import time
import machine
from micropython import const
from sam_protocol import TYPE_DISPLAY
from eink_driver_sam import einkDSP_SAM

# Display control commands
DISPLAY_CMD_INIT = const(0x00)
DISPLAY_CMD_CLEAR = const(0x10)
DISPLAY_CMD_UPDATE = const(0x20)
DISPLAY_CMD_SLEEP = const(0x30)
DISPLAY_CMD_STATUS = const(0x40)
DISPLAY_CMD_REFRESH = const(0x50)
DISPLAY_CMD_PARTIAL = const(0x60)
DISPLAY_CMD_CONFIG = const(0x70)

# Display status codes
DISPLAY_STATUS_IDLE = const(0x00)
DISPLAY_STATUS_BUSY = const(0x01)
DISPLAY_STATUS_ERROR = const(0x02)
DISPLAY_STATUS_SLEEPING = const(0x03)

# Display modes
DISPLAY_MODE_FULL = const(0x00)
DISPLAY_MODE_PARTIAL = const(0x01)
DISPLAY_MODE_FAST = const(0x02)
DISPLAY_MODE_LUT = const(0x03)


class SAMDisplayHandler:
    """Handles e-ink display control commands for SAM protocol."""

    def __init__(self, protocol_handler, debug_callback=None):
        self.protocol = protocol_handler
        self.debug_callback = debug_callback

        # Display hardware control pins (from original main.py)
        self.eink_status = machine.Pin(9, machine.Pin.OUT)
        self.eink_mux = machine.Pin(22, machine.Pin.OUT)

        # Display state tracking
        self.display_status = DISPLAY_STATUS_IDLE
        self.display_mode = DISPLAY_MODE_FULL
        self.display_initialized = False
        self.display_sleeping = False

        # E-ink driver instance
        self.eink = None

        # Display operation queue
        self.operation_queue = []
        self.operation_in_progress = False

        # Register handler with protocol
        self.protocol.register_handler(TYPE_DISPLAY, self._handle_display_packet)

        self._debug_print("Display handler initialized")

    def _debug_print(self, message):
        """Send debug message if callback is available."""
        if self.debug_callback:
            self.debug_callback(f"[Display Handler] {message}")

    def _handle_display_packet(self, packet):
        """Handle incoming display control packets."""
        try:
            flags = packet.get_flags()
            command = flags & 0xF0  # Upper 4 bits
            param1 = packet.data0
            param2 = packet.data1

            self._debug_print(
                f"Display command: {command:02X}, params: {param1:02X}, {param2:02X}"
            )

            if command == DISPLAY_CMD_INIT:
                self._handle_display_init(param1, param2)
            elif command == DISPLAY_CMD_CLEAR:
                self._handle_display_clear(param1, param2)
            elif command == DISPLAY_CMD_UPDATE:
                self._handle_display_update(param1, param2)
            elif command == DISPLAY_CMD_SLEEP:
                self._handle_display_sleep(param1, param2)
            elif command == DISPLAY_CMD_STATUS:
                self._handle_display_status(param1, param2)
            elif command == DISPLAY_CMD_REFRESH:
                self._handle_display_refresh(param1, param2)
            elif command == DISPLAY_CMD_PARTIAL:
                self._handle_display_partial(param1, param2)
            elif command == DISPLAY_CMD_CONFIG:
                self._handle_display_config(param1, param2)
            else:
                self._debug_print(f"Unknown display command: {command:02X}")
                self._send_display_response(command, 0xFF, 0xFF)  # Error response

        except Exception as e:
            self._debug_print(f"Error handling display packet: {e}")
            self._send_display_response(DISPLAY_CMD_STATUS, DISPLAY_STATUS_ERROR, 0xFF)

    def _handle_display_init(self, mode, config):
        """Handle display initialization command."""
        try:
            self._power_on_display()

            # Initialize e-ink driver
            if self.eink is None:
                self.eink = einkDSP_SAM()

            if not self.eink.init:
                self.eink.re_init()

            # Initialize based on mode
            if mode == DISPLAY_MODE_LUT:
                self.eink.epd_init_lut()
                self._debug_print("Display initialized with LUT mode")
            elif mode == DISPLAY_MODE_FAST:
                self.eink.epd_init_fast()
                self._debug_print("Display initialized with fast mode")
            elif mode == DISPLAY_MODE_PARTIAL:
                self.eink.epd_init_part()
                self._debug_print("Display initialized with partial mode")
            else:
                self.eink.epd_init()
                self._debug_print("Display initialized with standard mode")

            self.display_mode = mode
            self.display_initialized = True
            self.display_sleeping = False
            self.display_status = DISPLAY_STATUS_IDLE

            self._send_display_response(DISPLAY_CMD_INIT, 0x00, mode)

        except Exception as e:
            self._debug_print(f"Display initialization error: {e}")
            self.display_status = DISPLAY_STATUS_ERROR
            self._send_display_response(DISPLAY_CMD_INIT, 0xFF, 0xFF)

    def _handle_display_clear(self, pattern, delay):
        """Handle display clear command."""
        if not self._check_display_ready():
            return

        try:
            self.display_status = DISPLAY_STATUS_BUSY

            # Clear display
            self.eink.PIC_clear()

            self.display_status = DISPLAY_STATUS_IDLE
            self._send_display_response(DISPLAY_CMD_CLEAR, 0x00, 0x00)
            self._debug_print("Display cleared")

        except Exception as e:
            self._debug_print(f"Display clear error: {e}")
            self.display_status = DISPLAY_STATUS_ERROR
            self._send_display_response(DISPLAY_CMD_CLEAR, 0xFF, 0xFF)

    def _handle_display_update(self, file_id, refresh_mode):
        """Handle display update command."""
        if not self._check_display_ready():
            return

        try:
            self.display_status = DISPLAY_STATUS_BUSY

            # Map file_id to actual file paths
            file_map = {
                0x01: "./loading1.bin",
                0x02: "./loading2.bin",
                0x03: "./white.bin",
            }

            file_path = file_map.get(file_id, "./loading1.bin")

            # Perform display update
            if refresh_mode == 0x01:  # Partial refresh
                self.eink.epd_init_part()
                self.eink.PIC_display(None, file_path)
            else:  # Full refresh
                self.eink.PIC_display(None, file_path)

            self.display_status = DISPLAY_STATUS_IDLE
            self._send_display_response(DISPLAY_CMD_UPDATE, 0x00, file_id)
            self._debug_print(f"Display updated with file {file_id:02X}")

        except Exception as e:
            self._debug_print(f"Display update error: {e}")
            self.display_status = DISPLAY_STATUS_ERROR
            self._send_display_response(DISPLAY_CMD_UPDATE, 0xFF, file_id)

    def _handle_display_sleep(self, sleep_mode, wake_source):
        """Handle display sleep command."""
        try:
            if sleep_mode == 0x01:  # Enter sleep
                if self.eink and self.display_initialized:
                    self.eink.epd_sleep()
                    self.eink.de_init()

                self._power_off_display()
                self.display_sleeping = True
                self.display_status = DISPLAY_STATUS_SLEEPING
                self._debug_print("Display entered sleep mode")
            else:  # Wake from sleep
                self._power_on_display()
                self.display_sleeping = False
                self.display_status = DISPLAY_STATUS_IDLE
                self._debug_print("Display woke from sleep")

            self._send_display_response(DISPLAY_CMD_SLEEP, 0x00, sleep_mode)

        except Exception as e:
            self._debug_print(f"Display sleep error: {e}")
            self.display_status = DISPLAY_STATUS_ERROR
            self._send_display_response(DISPLAY_CMD_SLEEP, 0xFF, sleep_mode)

    def _handle_display_status(self, query_type, reserved):
        """Handle display status query."""
        status_data = 0x00

        if query_type == 0x00:  # General status
            status_data = self.display_status
        elif query_type == 0x01:  # Mode query
            status_data = self.display_mode
        elif query_type == 0x02:  # Busy status
            if self.eink and hasattr(self.eink, "BUSY_PIN"):
                status_data = 0x01 if self.eink.BUSY_PIN.value() == 0 else 0x00
            else:
                status_data = (
                    0x01 if self.display_status == DISPLAY_STATUS_BUSY else 0x00
                )

        self._send_display_response(DISPLAY_CMD_STATUS, status_data, query_type)
        self._debug_print(
            f"Sent display status: {status_data:02X} for query {query_type:02X}"
        )

    def _handle_display_refresh(self, refresh_type, delay_ms):
        """Handle display refresh command."""
        if not self._check_display_ready():
            return

        try:
            self.display_status = DISPLAY_STATUS_BUSY

            if refresh_type == 0x01:  # Partial refresh
                self.eink.epd_init_part()
            elif refresh_type == 0x02:  # Fast refresh
                self.eink.epd_init_fast()
            else:  # Full refresh
                self.eink.epd_init_lut()

            # Apply delay if specified
            if delay_ms > 0:
                time.sleep_ms(delay_ms * 10)  # Convert to actual milliseconds

            self.display_status = DISPLAY_STATUS_IDLE
            self._send_display_response(DISPLAY_CMD_REFRESH, 0x00, refresh_type)
            self._debug_print(f"Display refreshed with type {refresh_type:02X}")

        except Exception as e:
            self._debug_print(f"Display refresh error: {e}")
            self.display_status = DISPLAY_STATUS_ERROR
            self._send_display_response(DISPLAY_CMD_REFRESH, 0xFF, refresh_type)

    def _handle_display_partial(self, x_pos, y_pos):
        """Handle partial display update command."""
        if not self._check_display_ready():
            return

        try:
            self.display_status = DISPLAY_STATUS_BUSY

            # Initialize partial mode
            self.eink.epd_init_part()

            # Perform partial update (simplified - would need actual coordinates)
            self.eink.PIC_display("./loading1.bin", "./loading2.bin")

            self.display_status = DISPLAY_STATUS_IDLE
            self._send_display_response(DISPLAY_CMD_PARTIAL, 0x00, 0x00)
            self._debug_print(f"Partial display update at ({x_pos}, {y_pos})")

        except Exception as e:
            self._debug_print(f"Partial display error: {e}")
            self.display_status = DISPLAY_STATUS_ERROR
            self._send_display_response(DISPLAY_CMD_PARTIAL, 0xFF, 0xFF)

    def _handle_display_config(self, config_type, value):
        """Handle display configuration command."""
        try:
            if config_type == 0x01:  # Set refresh rate
                self._debug_print(f"Display refresh rate config: {value}")
            elif config_type == 0x02:  # Set contrast
                self._debug_print(f"Display contrast config: {value}")
            elif config_type == 0x03:  # Set orientation
                self._debug_print(f"Display orientation config: {value}")
            else:
                self._debug_print(
                    f"Unknown display config: {config_type:02X} = {value:02X}"
                )

            self._send_display_response(DISPLAY_CMD_CONFIG, 0x00, config_type)

        except Exception as e:
            self._debug_print(f"Display config error: {e}")
            self._send_display_response(DISPLAY_CMD_CONFIG, 0xFF, config_type)

    def _check_display_ready(self):
        """Check if display is ready for operations."""
        if self.display_sleeping:
            self._send_display_response(
                DISPLAY_CMD_STATUS, DISPLAY_STATUS_SLEEPING, 0xFF
            )
            self._debug_print("Display command rejected - display sleeping")
            return False

        if not self.display_initialized:
            self._send_display_response(DISPLAY_CMD_STATUS, DISPLAY_STATUS_ERROR, 0xFE)
            self._debug_print("Display command rejected - not initialized")
            return False

        if self.display_status == DISPLAY_STATUS_BUSY:
            self._send_display_response(DISPLAY_CMD_STATUS, DISPLAY_STATUS_BUSY, 0xFD)
            self._debug_print("Display command rejected - busy")
            return False

        return True

    def _power_on_display(self):
        """Power on the e-ink display."""
        self.eink_status.high()  # Provide power to e-ink
        self.eink_mux.high()  # SAM control e-ink
        time.sleep_ms(100)  # Allow power to stabilize
        self._debug_print("Display powered on")

    def _power_off_display(self):
        """Power off the e-ink display."""
        self.eink_mux.low()  # SOM control e-ink
        self.eink_status.low()  # Remove power from e-ink
        self._debug_print("Display powered off")

    def _send_display_response(self, command, status, data):
        """Send display command response to host."""
        from sam_protocol import SAMPacket, TYPE_DISPLAY

        response_packet = SAMPacket(
            type_flags=TYPE_DISPLAY | (command & 0x1F), data0=status, data1=data
        )

        success = self.protocol.send_packet(response_packet)
        if success:
            self._debug_print(
                f"Sent display response: cmd={command:02X}, status={status:02X}"
            )
        else:
            self._debug_print(f"Failed to send display response")

    def is_busy(self):
        """Check if display is currently busy."""
        if self.eink and hasattr(self.eink, "BUSY_PIN"):
            return self.eink.BUSY_PIN.value() == 0
        return self.display_status == DISPLAY_STATUS_BUSY

    def get_status(self):
        """Get current display status."""
        return {
            "status": self.display_status,
            "mode": self.display_mode,
            "initialized": self.display_initialized,
            "sleeping": self.display_sleeping,
            "busy": self.is_busy(),
        }

    def cleanup(self):
        """Cleanup display handler resources."""
        try:
            if self.eink and self.display_initialized:
                self.eink.de_init()
            self._power_off_display()
        except Exception as e:
            self._debug_print(f"Cleanup error: {e}")

        self._debug_print("Display handler cleanup completed")
