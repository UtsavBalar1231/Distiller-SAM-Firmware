"""
SAM Protocol Core Implementation for RP2040

This module implements the 4-byte packet protocol for bidirectional
communication between the RP2040 microcontroller and Linux host system.

Packet Format: [type_flags (1B)] [data (2B)] [checksum (1B)]

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import struct
import time
from micropython import const

# Protocol constants
PACKET_SIZE = const(4)

# Message types (3 most significant bits)
TYPE_BUTTON = const(0x00)  # 0b000xxxxx - MCU → Host: Button state changes
TYPE_LED = const(0x20)  # 0b001xxxxx - Host ↔ MCU: LED control
TYPE_POWER = const(0x40)  # 0b010xxxxx - Host ↔ MCU: Power management
TYPE_DISPLAY = const(0x60)  # 0b011xxxxx - Host ↔ MCU: Display control
TYPE_DEBUG_CODE = const(0x80)  # 0b100xxxxx - MCU → Host: Debug codes
TYPE_DEBUG_TEXT = const(0xA0)  # 0b101xxxxx - MCU → Host: Debug text
TYPE_SYSTEM = const(0xC0)  # 0b110xxxxx - Host ↔ MCU: System commands
TYPE_RESERVED = const(0xE0)  # 0b111xxxxx - Reserved for future use
TYPE_MASK = const(0xE0)  # 0b11100000

# Button event flags (5 least significant bits)
BTN_UP_MASK = const(0x01)
BTN_DOWN_MASK = const(0x02)
BTN_SELECT_MASK = const(0x04)
BTN_POWER_MASK = const(0x08)

# LED control flags
LED_CMD_IMMEDIATE = const(0x00)
LED_CMD_SEQUENCE = const(0x10)
LED_MODE_STATIC = const(0x00)
LED_MODE_BLINK = const(0x04)
LED_MODE_FADE = const(0x08)
LED_MODE_RAINBOW = const(0x0C)
LED_MODE_MASK = const(0x0C)

# Power management commands
POWER_CMD_QUERY = const(0x00)
POWER_CMD_SET = const(0x10)
POWER_CMD_SLEEP = const(0x20)
POWER_CMD_SHUTDOWN = const(0x30)
POWER_CMD_CURRENT = const(0x40)
POWER_CMD_BATTERY = const(0x50)
POWER_CMD_TEMP = const(0x60)
POWER_CMD_VOLTAGE = const(0x70)
POWER_CMD_REQUEST_METRICS = const(0x80)

# System control actions
SYSTEM_PING = const(0x00)
SYSTEM_RESET = const(0x01)
SYSTEM_VERSION = const(0x02)
SYSTEM_STATUS = const(0x03)
SYSTEM_CONFIG = const(0x04)

# Debug text flags
DEBUG_FIRST_CHUNK = const(0x10)
DEBUG_CONTINUE = const(0x08)
DEBUG_CHUNK_MASK = const(0x07)


class SAMPacket:
    """Represents a SAM protocol packet."""

    def __init__(self, type_flags=0, data0=0, data1=0, checksum=None):
        self.type_flags = type_flags
        self.data0 = data0
        self.data1 = data1
        self.checksum = checksum if checksum is not None else self._calculate_checksum()

    def _calculate_checksum(self):
        """Calculate XOR checksum for the packet."""
        return self.type_flags ^ self.data0 ^ self.data1

    def verify_checksum(self):
        """Verify packet checksum integrity."""
        return self.checksum == self._calculate_checksum()

    def to_bytes(self):
        """Convert packet to bytes for transmission."""
        return struct.pack(
            "BBBB", self.type_flags, self.data0, self.data1, self.checksum
        )

    @classmethod
    def from_bytes(cls, data):
        """Create packet from received bytes."""
        if len(data) != PACKET_SIZE:
            raise ValueError(
                f"Invalid packet size: {len(data)}, expected {PACKET_SIZE}"
            )

        type_flags, data0, data1, checksum = struct.unpack("BBBB", data)
        return cls(type_flags, data0, data1, checksum)

    def get_type(self):
        """Extract message type from packet."""
        return self.type_flags & TYPE_MASK

    def get_flags(self):
        """Extract flags from packet."""
        return self.type_flags & ~TYPE_MASK

    def __repr__(self):
        return f"SAMPacket(type={self.get_type():02X}, flags={self.get_flags():02X}, data=[{self.data0:02X}, {self.data1:02X}], checksum={self.checksum:02X})"


class SAMProtocolHandler:
    """Core SAM protocol handler for RP2040."""

    def __init__(self, uart, debug_callback=None):
        self.uart = uart
        self.debug_callback = debug_callback
        self.rx_buffer = bytearray()
        self.handlers = {}
        self.packet_stats = [0] * 8  # Statistics per message type
        self.last_ping_time = 0
        self._setup_handlers()

    def _setup_handlers(self):
        """Initialize message type handlers."""
        # Handlers will be registered by specific modules
        pass

    def register_handler(self, message_type, handler_func):
        """Register a handler function for a specific message type."""
        self.handlers[message_type] = handler_func
        self._debug_print(f"Registered handler for type {message_type:02X}")

    def _debug_print(self, message):
        """Send debug message if callback is available."""
        if self.debug_callback:
            self.debug_callback(f"[SAM Protocol] {message}")

    def send_packet(self, packet):
        """Send a SAM packet to the host."""
        if not isinstance(packet, SAMPacket):
            raise ValueError("Expected SAMPacket instance")

        # Ensure checksum is correct
        packet.checksum = packet._calculate_checksum()
        data = packet.to_bytes()

        try:
            self.uart.write(data)
            self._debug_print(f"Sent: {packet}")
            return True
        except Exception as e:
            self._debug_print(f"Send error: {e}")
            return False

    def process_received_data(self):
        """Process any received UART data."""
        if not self.uart.any():
            return

        # Read available data
        new_data = self.uart.read()
        if new_data:
            self.rx_buffer.extend(new_data)

        # Process complete packets
        while len(self.rx_buffer) >= PACKET_SIZE:
            try:
                packet_data = bytes(self.rx_buffer[:PACKET_SIZE])
                packet = SAMPacket.from_bytes(packet_data)

                if packet.verify_checksum():
                    self._process_packet(packet)
                    # Update statistics
                    msg_type_index = (packet.get_type() >> 5) & 0x07
                    self.packet_stats[msg_type_index] += 1
                else:
                    self._debug_print(f"Checksum error: {packet}")

                # Remove processed packet from buffer
                self.rx_buffer = self.rx_buffer[PACKET_SIZE:]

            except (ValueError, IndexError) as e:
                self._debug_print(f"Packet parsing error: {e}")
                # Remove one byte and try again (resync)
                self.rx_buffer = self.rx_buffer[1:]

    def _process_packet(self, packet):
        """Process a received packet."""
        msg_type = packet.get_type()
        self._debug_print(f"Received: {packet}")

        # Call registered handler
        if msg_type in self.handlers:
            try:
                self.handlers[msg_type](packet)
            except Exception as e:
                self._debug_print(f"Handler error for type {msg_type:02X}: {e}")
        else:
            self._debug_print(f"No handler for message type {msg_type:02X}")

    def send_button_event(self, button_state):
        """Send button state change to host."""
        packet = SAMPacket(type_flags=TYPE_BUTTON, data0=button_state, data1=0x00)
        return self.send_packet(packet)

    def send_debug_code(self, category, code, param=0):
        """Send debug code to host."""
        packet = SAMPacket(
            type_flags=TYPE_DEBUG_CODE | (category & 0x1F), data0=code, data1=param
        )
        return self.send_packet(packet)

    def send_debug_text(self, text, chunk_num=0, is_first=True, is_continue=False):
        """Send debug text message to host."""
        flags = 0
        if is_first:
            flags |= DEBUG_FIRST_CHUNK
        if is_continue:
            flags |= DEBUG_CONTINUE
        flags |= chunk_num & DEBUG_CHUNK_MASK

        # Encode text into 2 bytes (UTF-8 truncated or ASCII)
        text_bytes = text.encode("utf-8")[:2]
        data0 = text_bytes[0] if len(text_bytes) > 0 else 0
        data1 = text_bytes[1] if len(text_bytes) > 1 else 0

        packet = SAMPacket(type_flags=TYPE_DEBUG_TEXT | flags, data0=data0, data1=data1)
        return self.send_packet(packet)

    def send_power_response(self, command, value):
        """Send power management response to host."""
        packet = SAMPacket(
            type_flags=TYPE_POWER | command,
            data0=(value >> 8) & 0xFF,
            data1=value & 0xFF,
        )
        return self.send_packet(packet)

    def send_system_response(self, action, response_code, data=0):
        """Send system command response to host."""
        packet = SAMPacket(
            type_flags=TYPE_SYSTEM | action, data0=response_code, data1=data
        )
        return self.send_packet(packet)

    def send_ping_response(self):
        """Send ping response to host."""
        current_time = time.ticks_ms()
        self.last_ping_time = current_time
        return self.send_system_response(SYSTEM_PING, 0x00, 0x01)

    def get_statistics(self):
        """Get protocol statistics."""
        return {
            "button_packets": self.packet_stats[0],
            "led_packets": self.packet_stats[1],
            "power_packets": self.packet_stats[2],
            "display_packets": self.packet_stats[3],
            "debug_code_packets": self.packet_stats[4],
            "debug_text_packets": self.packet_stats[5],
            "system_packets": self.packet_stats[6],
            "reserved_packets": self.packet_stats[7],
            "last_ping_time": self.last_ping_time,
        }
