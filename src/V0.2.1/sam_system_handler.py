"""
SAM System Commands Handler for RP2040

This module handles system control commands from the Linux host including
ping, reset, version exchange, status queries, and configuration commands.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import time
import gc
import machine
from micropython import const
from sam_protocol import (
    TYPE_SYSTEM,
    SYSTEM_PING,
    SYSTEM_RESET,
    SYSTEM_VERSION,
    SYSTEM_STATUS,
    SYSTEM_CONFIG,
)

# Firmware version constants
FIRMWARE_VERSION_MAJOR = const(1)
FIRMWARE_VERSION_MINOR = const(0)
FIRMWARE_VERSION_PATCH = const(0)

# System status codes
STATUS_OK = const(0x00)
STATUS_ERROR = const(0x01)
STATUS_BUSY = const(0x02)
STATUS_INITIALIZING = const(0x03)
STATUS_SHUTDOWN = const(0x04)

# Configuration parameters
CONFIG_DEBUG_LEVEL = const(0x01)
CONFIG_POWER_POLL_INTERVAL = const(0x02)
CONFIG_LED_BRIGHTNESS = const(0x03)
CONFIG_DISPLAY_MODE = const(0x04)
CONFIG_UART_BAUD = const(0x05)
CONFIG_WATCHDOG_TIMEOUT = const(0x06)

# Reset modes
RESET_MODE_SOFT = const(0x00)
RESET_MODE_HARD = const(0x01)
RESET_MODE_BOOTLOADER = const(0x02)


class SAMSystemHandler:
    """Handles system control commands for SAM protocol."""

    def __init__(self, protocol_handler, debug_handler=None, debug_callback=None):
        self.protocol = protocol_handler
        self.debug_handler = debug_handler
        self.debug_callback = debug_callback

        # System state
        self.system_status = STATUS_INITIALIZING
        self.host_version = {"major": 0, "minor": 0, "patch": 0}
        self.last_ping_time = 0
        self.uptime_start = time.ticks_ms()

        # Configuration storage
        self.config = {
            CONFIG_DEBUG_LEVEL: 2,  # info level
            CONFIG_POWER_POLL_INTERVAL: 1000,  # 1 second
            CONFIG_LED_BRIGHTNESS: 128,  # 50% brightness
            CONFIG_DISPLAY_MODE: 0,  # Full refresh mode
            CONFIG_UART_BAUD: 115200,  # Standard baud rate
            CONFIG_WATCHDOG_TIMEOUT: 2000,  # 2 seconds
        }

        # Statistics
        self.stats = {
            "ping_count": 0,
            "reset_count": 0,
            "version_requests": 0,
            "status_requests": 0,
            "config_requests": 0,
            "invalid_commands": 0,
        }

        # Register handler with protocol
        self.protocol.register_handler(TYPE_SYSTEM, self._handle_system_packet)

        # Send initial system ready notification
        self._send_system_ready()

        self._debug_print("System handler initialized")

    def _debug_print(self, message):
        """Send debug message if callback is available."""
        if self.debug_callback:
            self.debug_callback(f"[System Handler] {message}")

    def _handle_system_packet(self, packet):
        """Handle incoming system command packets."""
        try:
            flags = packet.get_flags()
            action = flags & 0x0F  # Lower 4 bits
            param1 = packet.data0
            param2 = packet.data1

            self._debug_print(
                f"System command: action={action:02X}, params: {param1:02X}, {param2:02X}"
            )

            if action == SYSTEM_PING:
                self._handle_ping(param1, param2)
            elif action == SYSTEM_RESET:
                self._handle_reset(param1, param2)
            elif action == SYSTEM_VERSION:
                self._handle_version(param1, param2)
            elif action == SYSTEM_STATUS:
                self._handle_status(param1, param2)
            elif action == SYSTEM_CONFIG:
                self._handle_config(param1, param2)
            else:
                self._debug_print(f"Unknown system action: {action:02X}")
                self.stats["invalid_commands"] += 1
                self._send_system_response(action, 0xFF, 0xFF)  # Error response

        except Exception as e:
            self._debug_print(f"Error handling system packet: {e}")
            if self.debug_handler:
                self.debug_handler.log_exception(e)
            self._send_system_response(SYSTEM_STATUS, STATUS_ERROR, 0xFF)

    def _handle_ping(self, sequence, reserved):
        """Handle ping command."""
        self.stats["ping_count"] += 1
        self.last_ping_time = time.ticks_ms()

        # Send ping response with same sequence number
        self._send_system_response(SYSTEM_PING, sequence, 0x00)

        self._debug_print(f"Ping response sent (seq={sequence})")

        if self.debug_handler:
            self.debug_handler.log_comm_event(0x04, sequence)  # Response sent

    def _handle_reset(self, reset_mode, reason):
        """Handle reset command."""
        self.stats["reset_count"] += 1

        self._debug_print(f"Reset requested: mode={reset_mode}, reason={reason}")

        if self.debug_handler:
            self.debug_handler.log_system_event(0x04, reset_mode)  # Reset requested

        # Send acknowledgment before reset
        self._send_system_response(SYSTEM_RESET, 0x00, reset_mode)

        # Brief delay to ensure response is sent
        time.sleep_ms(100)

        if reset_mode == RESET_MODE_SOFT:
            self._perform_soft_reset()
        elif reset_mode == RESET_MODE_HARD:
            self._perform_hard_reset()
        elif reset_mode == RESET_MODE_BOOTLOADER:
            self._perform_bootloader_reset()
        else:
            self._debug_print(f"Invalid reset mode: {reset_mode}")
            self._send_system_response(SYSTEM_RESET, 0xFF, reset_mode)

    def _handle_version(self, request_type, reserved):
        """Handle version request/exchange."""
        self.stats["version_requests"] += 1

        if request_type == 0x00:  # Version request
            # Send our version
            self._send_system_response(
                SYSTEM_VERSION, FIRMWARE_VERSION_MAJOR, FIRMWARE_VERSION_MINOR
            )

            # Send extended version with patch number
            extended_packet = self.protocol.SAMPacket(
                type_flags=0xE1,  # TYPE_EXTENDED | extended version
                data0=FIRMWARE_VERSION_PATCH,
                data1=0x00,
            )
            self.protocol.send_packet(extended_packet)

            self._debug_print(
                f"Version sent: {FIRMWARE_VERSION_MAJOR}.{FIRMWARE_VERSION_MINOR}.{FIRMWARE_VERSION_PATCH}"
            )

        elif request_type == 0x01:  # Host version info
            # Store host version
            self.host_version["major"] = reserved
            self.host_version["minor"] = 0  # Will be updated by extended packet

            self._debug_print(f"Host version received: {reserved}.x.x")

            # Send acknowledgment
            self._send_system_response(SYSTEM_VERSION, 0x01, 0x00)

        else:
            self._debug_print(f"Invalid version request type: {request_type}")
            self._send_system_response(SYSTEM_VERSION, 0xFF, request_type)

        if self.debug_handler:
            self.debug_handler.log_version_exchange(
                FIRMWARE_VERSION_MAJOR, FIRMWARE_VERSION_MINOR, FIRMWARE_VERSION_PATCH
            )

    def _handle_status(self, query_type, param):
        """Handle status query."""
        self.stats["status_requests"] += 1

        if query_type == 0x00:  # General status
            self._send_system_response(SYSTEM_STATUS, self.system_status, 0x00)

        elif query_type == 0x01:  # Uptime query
            uptime_ms = time.ticks_diff(time.ticks_ms(), self.uptime_start)
            uptime_seconds = uptime_ms // 1000

            # Send uptime in seconds (16-bit value)
            self._send_system_response(
                SYSTEM_STATUS, (uptime_seconds >> 8) & 0xFF, uptime_seconds & 0xFF
            )

        elif query_type == 0x02:  # Memory status
            free_mem = gc.mem_free()
            allocated_mem = gc.mem_alloc()

            # Send free memory in KB
            free_kb = free_mem // 1024
            self._send_system_response(
                SYSTEM_STATUS, (free_kb >> 8) & 0xFF, free_kb & 0xFF
            )

            if self.debug_handler:
                self.debug_handler.log_memory_usage(free_mem)

        elif query_type == 0x03:  # Temperature status
            # Get temperature from power handler if available
            try:
                temp_adc = machine.ADC(4)
                adc_reading = temp_adc.read_u16()
                voltage = (adc_reading / 65535) * 3.3
                temp_celsius = 27 - (voltage - 0.706) / 0.001721
                temp_int = int(temp_celsius)

                self._send_system_response(SYSTEM_STATUS, temp_int, 0x00)
            except:
                self._send_system_response(SYSTEM_STATUS, 25, 0x00)  # Default 25°C

        elif query_type == 0x04:  # Statistics query
            # Send ping count
            self._send_system_response(
                SYSTEM_STATUS,
                (self.stats["ping_count"] >> 8) & 0xFF,
                self.stats["ping_count"] & 0xFF,
            )

        else:
            self._debug_print(f"Invalid status query type: {query_type}")
            self._send_system_response(SYSTEM_STATUS, 0xFF, query_type)

        self._debug_print(f"Status query handled: type={query_type}")

    def _handle_config(self, action, param):
        """Handle configuration commands."""
        self.stats["config_requests"] += 1

        if action == 0x00:  # Get configuration
            if param in self.config:
                value = self.config[param]
                self._send_system_response(
                    SYSTEM_CONFIG, (value >> 8) & 0xFF, value & 0xFF
                )
                self._debug_print(f"Config get: param={param:02X}, value={value}")
            else:
                self._send_system_response(SYSTEM_CONFIG, 0xFF, param)
                self._debug_print(f"Invalid config parameter: {param:02X}")

        elif action == 0x01:  # Set configuration
            config_param = (param >> 4) & 0x0F
            config_value = param & 0x0F

            if config_param in self.config:
                old_value = self.config[config_param]
                self.config[config_param] = config_value

                # Apply configuration change
                self._apply_config_change(config_param, config_value)

                self._send_system_response(SYSTEM_CONFIG, 0x00, config_param)
                self._debug_print(
                    f"Config set: param={config_param:02X}, {old_value} -> {config_value}"
                )
            else:
                self._send_system_response(SYSTEM_CONFIG, 0xFF, config_param)
                self._debug_print(f"Invalid config parameter: {config_param:02X}")

        else:
            self._debug_print(f"Invalid config action: {action:02X}")
            self._send_system_response(SYSTEM_CONFIG, 0xFF, action)

    def _apply_config_change(self, param, value):
        """Apply configuration change."""
        if param == CONFIG_DEBUG_LEVEL and self.debug_handler:
            self.debug_handler.set_debug_level(value)
        elif param == CONFIG_WATCHDOG_TIMEOUT:
            # Update watchdog timeout (would need watchdog reference)
            pass
        # Add other configuration applications as needed

    def _send_system_response(self, action, data0, data1):
        """Send system command response to host."""
        success = self.protocol.send_system_response(action, data0, data1)
        if not success:
            self._debug_print(f"Failed to send system response for action {action:02X}")

    def _send_system_ready(self):
        """Send system ready notification."""
        self.system_status = STATUS_OK
        self._send_system_response(SYSTEM_STATUS, STATUS_OK, 0x00)

        if self.debug_handler:
            self.debug_handler.log_startup_sequence()

        self._debug_print("System ready notification sent")

    def _perform_soft_reset(self):
        """Perform soft reset."""
        self._debug_print("Performing soft reset")
        if self.debug_handler:
            self.debug_handler.log_shutdown_sequence()

        # Cleanup and reset
        machine.soft_reset()

    def _perform_hard_reset(self):
        """Perform hard reset."""
        self._debug_print("Performing hard reset")
        if self.debug_handler:
            self.debug_handler.log_shutdown_sequence()

        # Hard reset
        machine.reset()

    def _perform_bootloader_reset(self):
        """Perform bootloader reset."""
        self._debug_print("Performing bootloader reset")
        if self.debug_handler:
            self.debug_handler.log_shutdown_sequence()

        # Enter bootloader mode (implementation depends on hardware)
        # For now, perform a hard reset
        machine.reset()

    def periodic_update(self):
        """Perform periodic system updates."""
        current_time = time.ticks_ms()

        # Check for ping timeout (if host expects regular pings)
        if self.last_ping_time > 0:
            ping_age = time.ticks_diff(current_time, self.last_ping_time)
            if ping_age > 30000:  # 30 seconds without ping
                self._debug_print("Ping timeout detected")
                if self.debug_handler:
                    self.debug_handler.log_comm_event(
                        0x05, 0x00
                    )  # Communication timeout

    def set_system_status(self, status):
        """Set system status."""
        if status in [
            STATUS_OK,
            STATUS_ERROR,
            STATUS_BUSY,
            STATUS_INITIALIZING,
            STATUS_SHUTDOWN,
        ]:
            old_status = self.system_status
            self.system_status = status
            self._debug_print(f"System status changed: {old_status} -> {status}")
        else:
            self._debug_print(f"Invalid system status: {status}")

    def get_system_info(self):
        """Get comprehensive system information."""
        uptime_ms = time.ticks_diff(time.ticks_ms(), self.uptime_start)

        return {
            "firmware_version": {
                "major": FIRMWARE_VERSION_MAJOR,
                "minor": FIRMWARE_VERSION_MINOR,
                "patch": FIRMWARE_VERSION_PATCH,
            },
            "host_version": self.host_version.copy(),
            "system_status": self.system_status,
            "uptime_ms": uptime_ms,
            "free_memory": gc.mem_free(),
            "allocated_memory": gc.mem_alloc(),
            "config": self.config.copy(),
            "statistics": self.stats.copy(),
        }

    def get_statistics(self):
        """Get system handler statistics."""
        return self.stats.copy()

    def reset_statistics(self):
        """Reset system statistics."""
        self.stats = {
            "ping_count": 0,
            "reset_count": 0,
            "version_requests": 0,
            "status_requests": 0,
            "config_requests": 0,
            "invalid_commands": 0,
        }
        self._debug_print("System statistics reset")

    def cleanup(self):
        """Cleanup system handler resources."""
        self.set_system_status(STATUS_SHUTDOWN)

        if self.debug_handler:
            self.debug_handler.log_shutdown_sequence()

        self._debug_print("System handler cleanup completed")
