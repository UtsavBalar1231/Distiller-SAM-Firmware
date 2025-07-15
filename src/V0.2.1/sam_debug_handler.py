"""
SAM Debug Interface Handler for RP2040

This module handles debug code and text message transmission to the Linux host
according to the SAM protocol specification. Provides logging, diagnostics,
and runtime debugging capabilities.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import time
from micropython import const
from sam_protocol import (
    TYPE_DEBUG_CODE,
    TYPE_DEBUG_TEXT,
    DEBUG_FIRST_CHUNK,
    DEBUG_CONTINUE,
    DEBUG_CHUNK_MASK,
)

# Debug categories
DEBUG_CAT_SYSTEM = const(0)
DEBUG_CAT_ERROR = const(1)
DEBUG_CAT_BUTTON = const(2)
DEBUG_CAT_LED = const(3)
DEBUG_CAT_POWER = const(4)
DEBUG_CAT_DISPLAY = const(5)
DEBUG_CAT_COMM = const(6)
DEBUG_CAT_PERFORMANCE = const(7)

# Debug levels
DEBUG_LEVEL_OFF = const(0)
DEBUG_LEVEL_ERROR = const(1)
DEBUG_LEVEL_INFO = const(2)
DEBUG_LEVEL_VERBOSE = const(3)

# Debug codes for different categories
DEBUG_CODES = {
    DEBUG_CAT_SYSTEM: {
        0x01: "System startup",
        0x02: "System initialization complete",
        0x03: "System shutdown initiated",
        0x04: "System reset requested",
        0x05: "Watchdog timeout",
        0x10: "Boot notification sent",
        0x11: "Version exchange complete",
        0x12: "Protocol sync established",
    },
    DEBUG_CAT_ERROR: {
        0x01: "Memory allocation error",
        0x02: "UART communication error",
        0x03: "Checksum validation failed",
        0x04: "Invalid packet received",
        0x05: "Handler exception",
        0x06: "Hardware initialization failed",
        0x07: "Critical system error",
        0xFF: "Unknown error",
    },
    DEBUG_CAT_BUTTON: {
        0x01: "Button press detected",
        0x02: "Button release detected",
        0x03: "Long press detected",
        0x04: "Shutdown sequence initiated",
        0x05: "Button debounce error",
        0x06: "Button state change",
        0x07: "Interrupt handler triggered",
    },
    DEBUG_CAT_LED: {
        0x01: "LED command received",
        0x02: "LED animation started",
        0x03: "LED animation completed",
        0x04: "LED color change",
        0x05: "LED brightness change",
        0x06: "LED mode change",
        0x07: "LED hardware error",
    },
    DEBUG_CAT_POWER: {
        0x01: "Boot started",
        0x02: "Boot complete",
        0x03: "Shutdown initiated",
        0x04: "Shutdown complete",
        0x05: "Sleep mode entered",
        0x06: "Wake from sleep",
        0x07: "Power metrics updated",
        0x08: "Battery low warning",
        0x09: "Temperature warning",
        0x0A: "Voltage warning",
    },
    DEBUG_CAT_DISPLAY: {
        0x01: "Display initialization started",
        0x02: "Display initialization complete",
        0x03: "Display update started",
        0x04: "Display update complete",
        0x05: "Display sleep entered",
        0x06: "Display wake from sleep",
        0x07: "Display error",
        0x08: "Refresh cycle started",
        0x09: "Refresh cycle complete",
    },
    DEBUG_CAT_COMM: {
        0x01: "UART data received",
        0x02: "UART data sent",
        0x03: "Packet processed",
        0x04: "Response sent",
        0x05: "Communication timeout",
        0x06: "Buffer overflow",
        0x07: "Protocol error",
    },
    DEBUG_CAT_PERFORMANCE: {
        0x01: "High CPU usage",
        0x02: "Memory usage warning",
        0x03: "Processing delay",
        0x04: "Queue full",
        0x05: "Thread creation",
        0x06: "Thread completion",
        0x07: "Resource cleanup",
    },
}


class SAMDebugHandler:
    """Handles debug code and text message transmission for SAM protocol."""

    def __init__(self, protocol_handler, debug_level=DEBUG_LEVEL_INFO):
        self.protocol = protocol_handler
        self.debug_level = debug_level

        # Debug message queue
        self.debug_queue = []
        self.max_queue_size = 32

        # Text message chunking state
        self.text_chunk_size = 2  # 2 bytes per packet
        self.current_text_chunks = {}

        # Statistics
        self.debug_stats = {
            "codes_sent": 0,
            "text_messages_sent": 0,
            "queue_overflows": 0,
            "send_errors": 0,
        }

        # Boot-time debug code
        self.send_debug_code(DEBUG_CAT_SYSTEM, 0x01, 0x00)  # System startup

        self._debug_print("Debug handler initialized")

    def _debug_print(self, message):
        """Internal debug print (does not use SAM protocol)."""
        print(f"[Debug Handler] {message}")

    def set_debug_level(self, level):
        """Set the debug logging level."""
        if level in [
            DEBUG_LEVEL_OFF,
            DEBUG_LEVEL_ERROR,
            DEBUG_LEVEL_INFO,
            DEBUG_LEVEL_VERBOSE,
        ]:
            self.debug_level = level
            self._debug_print(f"Debug level set to {level}")
            self.send_debug_code(DEBUG_CAT_SYSTEM, 0x12, level)
        else:
            self._debug_print(f"Invalid debug level: {level}")

    def send_debug_code(self, category, code, param=0):
        """Send debug code to host."""
        if self.debug_level == DEBUG_LEVEL_OFF:
            return False

        # Check if code should be sent based on level
        if not self._should_send_debug(category, code):
            return False

        try:
            success = self.protocol.send_debug_code(category, code, param)
            if success:
                self.debug_stats["codes_sent"] += 1
                self._debug_print(
                    f"Sent debug code: cat={category}, code={code:02X}, param={param:02X}"
                )
            else:
                self.debug_stats["send_errors"] += 1
                self._debug_print(
                    f"Failed to send debug code: cat={category}, code={code:02X}"
                )
            return success
        except Exception as e:
            self._debug_print(f"Error sending debug code: {e}")
            self.debug_stats["send_errors"] += 1
            return False

    def send_debug_text(self, text, category=DEBUG_CAT_SYSTEM):
        """Send debug text message to host (may span multiple packets)."""
        if self.debug_level == DEBUG_LEVEL_OFF:
            return False

        if len(text) == 0:
            return False

        try:
            # Encode text to bytes
            text_bytes = text.encode("utf-8")
            total_chunks = (
                len(text_bytes) + self.text_chunk_size - 1
            ) // self.text_chunk_size

            success_count = 0

            for chunk_idx in range(total_chunks):
                # Calculate chunk boundaries
                start_idx = chunk_idx * self.text_chunk_size
                end_idx = min(start_idx + self.text_chunk_size, len(text_bytes))
                chunk_data = text_bytes[start_idx:end_idx]

                # Determine flags
                is_first = chunk_idx == 0
                is_continue = chunk_idx < total_chunks - 1

                # Pad chunk data to 2 bytes if needed
                if len(chunk_data) < 2:
                    chunk_data = chunk_data + b"\x00" * (2 - len(chunk_data))

                # Send chunk
                success = self.protocol.send_debug_text(
                    chunk_data.decode("utf-8", errors="ignore"),
                    chunk_idx % 8,  # Chunk number (3 bits)
                    is_first,
                    is_continue,
                )

                if success:
                    success_count += 1
                else:
                    self.debug_stats["send_errors"] += 1
                    break

                # Brief delay between chunks
                time.sleep_ms(1)

            if success_count == total_chunks:
                self.debug_stats["text_messages_sent"] += 1
                self._debug_print(
                    f"Sent debug text ({len(text)} chars, {total_chunks} chunks)"
                )
                return True
            else:
                self._debug_print(
                    f"Failed to send complete debug text ({success_count}/{total_chunks} chunks)"
                )
                return False

        except Exception as e:
            self._debug_print(f"Error sending debug text: {e}")
            self.debug_stats["send_errors"] += 1
            return False

    def _should_send_debug(self, category, code):
        """Determine if debug message should be sent based on level."""
        if self.debug_level == DEBUG_LEVEL_OFF:
            return False

        if self.debug_level == DEBUG_LEVEL_ERROR:
            # Only send error messages
            return category == DEBUG_CAT_ERROR

        if self.debug_level == DEBUG_LEVEL_INFO:
            # Send errors and important system messages
            return category in [DEBUG_CAT_ERROR, DEBUG_CAT_SYSTEM, DEBUG_CAT_POWER]

        if self.debug_level == DEBUG_LEVEL_VERBOSE:
            # Send all messages
            return True

        return False

    def log_system_event(self, event_code, param=0):
        """Log system event."""
        self.send_debug_code(DEBUG_CAT_SYSTEM, event_code, param)

    def log_error(self, error_code, param=0):
        """Log error event."""
        self.send_debug_code(DEBUG_CAT_ERROR, error_code, param)

    def log_button_event(self, event_code, param=0):
        """Log button event."""
        self.send_debug_code(DEBUG_CAT_BUTTON, event_code, param)

    def log_led_event(self, event_code, param=0):
        """Log LED event."""
        self.send_debug_code(DEBUG_CAT_LED, event_code, param)

    def log_power_event(self, event_code, param=0):
        """Log power event."""
        self.send_debug_code(DEBUG_CAT_POWER, event_code, param)

    def log_display_event(self, event_code, param=0):
        """Log display event."""
        self.send_debug_code(DEBUG_CAT_DISPLAY, event_code, param)

    def log_comm_event(self, event_code, param=0):
        """Log communication event."""
        self.send_debug_code(DEBUG_CAT_COMM, event_code, param)

    def log_performance_event(self, event_code, param=0):
        """Log performance event."""
        self.send_debug_code(DEBUG_CAT_PERFORMANCE, event_code, param)

    def log_exception(self, exception, category=DEBUG_CAT_ERROR):
        """Log exception with text message."""
        exception_text = f"Exception: {str(exception)}"
        self.send_debug_text(exception_text, category)
        self.send_debug_code(DEBUG_CAT_ERROR, 0x05, 0x00)  # Handler exception

    def log_startup_sequence(self):
        """Log complete startup sequence."""
        self.log_system_event(0x02, 0x00)  # System initialization complete
        self.send_debug_text("SAM Protocol RP2040 Firmware v1.0.0 Ready")

    def log_shutdown_sequence(self):
        """Log shutdown sequence."""
        self.log_system_event(0x03, 0x00)  # System shutdown initiated
        self.send_debug_text("Shutdown sequence started")

    def log_boot_notification(self):
        """Log boot notification."""
        self.log_system_event(0x10, 0x00)  # Boot notification sent
        self.send_debug_text("Boot notification sent to host")

    def log_version_exchange(self, major, minor, patch):
        """Log version exchange."""
        self.log_system_event(0x11, (major << 4) | minor)  # Version exchange
        self.send_debug_text(f"Version: {major}.{minor}.{patch}")

    def log_protocol_sync(self):
        """Log protocol synchronization."""
        self.log_system_event(0x12, 0x00)  # Protocol sync established
        self.send_debug_text("Protocol synchronization established")

    def log_watchdog_feed(self):
        """Log watchdog feed (verbose only)."""
        if self.debug_level == DEBUG_LEVEL_VERBOSE:
            self.log_system_event(0x05, 0x00)  # Watchdog timeout

    def log_memory_usage(self, free_bytes):
        """Log memory usage."""
        if free_bytes < 10000:  # Less than 10KB free
            self.log_performance_event(0x02, (free_bytes >> 8) & 0xFF)
            self.send_debug_text(f"Low memory: {free_bytes} bytes free")

    def log_queue_status(self, queue_size, max_size):
        """Log queue status."""
        if queue_size >= max_size:
            self.log_performance_event(0x04, queue_size)  # Queue full

    def log_thread_lifecycle(self, thread_name, started=True):
        """Log thread creation/completion."""
        if started:
            self.log_performance_event(0x05, 0x00)  # Thread creation
            self.send_debug_text(f"Thread started: {thread_name}")
        else:
            self.log_performance_event(0x06, 0x00)  # Thread completion
            self.send_debug_text(f"Thread completed: {thread_name}")

    def get_debug_code_description(self, category, code):
        """Get human-readable description of debug code."""
        if category in DEBUG_CODES and code in DEBUG_CODES[category]:
            return DEBUG_CODES[category][code]
        return f"Unknown debug code: cat={category}, code={code:02X}"

    def get_statistics(self):
        """Get debug handler statistics."""
        return self.debug_stats.copy()

    def reset_statistics(self):
        """Reset debug statistics."""
        self.debug_stats = {
            "codes_sent": 0,
            "text_messages_sent": 0,
            "queue_overflows": 0,
            "send_errors": 0,
        }
        self._debug_print("Debug statistics reset")

    def cleanup(self):
        """Cleanup debug handler resources."""
        self.log_system_event(0x03, 0x00)  # System shutdown initiated
        self.send_debug_text("Debug handler cleanup")
        self._debug_print("Debug handler cleanup completed")
