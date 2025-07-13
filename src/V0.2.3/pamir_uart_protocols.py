#Author: PamirAI 
#Date: 2025-07-13
#Version: 0.2.3
#Description: Pamir SAM UART Protocol implementation for RP2040

import struct

class PamirUartProtocols:
    
    # Message type constants (3 MSB of type_flags)
    TYPE_BUTTON = 0x00      # 0b000xxxxx - Button state change events
    TYPE_LED = 0x20         # 0b001xxxxx - LED control commands and status
    TYPE_POWER = 0x40       # 0b010xxxxx - Power management and metrics
    TYPE_DISPLAY = 0x60     # 0b011xxxxx - E-ink display control and status
    TYPE_DEBUG_CODE = 0x80  # 0b100xxxxx - Numeric debug codes
    TYPE_DEBUG_TEXT = 0xA0  # 0b101xxxxx - Text debug messages
    TYPE_SYSTEM = 0xC0      # 0b110xxxxx - Core system control commands
    TYPE_EXTENDED = 0xE0    # 0b111xxxxx - Extended commands
    
    # Button bit masks
    BTN_UP = 0x01       # Bit 0
    BTN_DOWN = 0x02     # Bit 1
    BTN_SELECT = 0x04   # Bit 2
    BTN_POWER = 0x08    # Bit 3
    
    # LED command flags (5 LSB of type_flags)
    LED_CMD_QUEUE = 0x00    # Queue instruction (E=0)
    LED_CMD_EXECUTE = 0x10  # Execute sequence (E=1)
    
    # LED modes/commands
    LED_MODE_STATIC = 0x00   # Static color
    LED_MODE_BLINK = 0x04    # Blinking
    LED_MODE_FADE = 0x08     # Fade in/out
    LED_MODE_RAINBOW = 0x0C  # Rainbow cycle
    LED_MODE_SEQUENCE = 0x10 # Custom sequence
    
    # Special LED IDs
    LED_ALL = 0x0F          # Broadcast to all LEDs (ID 15)
    
    def __init__(self):
        pass
    
    def calculate_checksum(self, type_flags, data0, data1):
        """Calculate XOR checksum for packet"""
        return type_flags ^ data0 ^ data1
    
    def create_packet(self, type_flags, data0=0x00, data1=0x00):
        """Create a 4-byte protocol packet with checksum"""
        checksum = self.calculate_checksum(type_flags, data0, data1)
        return struct.pack('BBBB', type_flags, data0, data1, checksum)
    
    def validate_packet(self, packet_bytes):
        """Validate packet checksum and return parsed data"""
        if len(packet_bytes) != 4:
            return False, None
        
        type_flags, data0, data1, checksum = struct.unpack('BBBB', packet_bytes)
        calculated_checksum = self.calculate_checksum(type_flags, data0, data1)
        
        if checksum != calculated_checksum:
            return False, None
        
        return True, (type_flags, data0, data1, checksum)
    
    def create_button_packet(self, up_pressed=False, down_pressed=False, 
                           select_pressed=False, power_pressed=False):
        """Create button event packet according to protocol specification
        
        Args:
            up_pressed: UP button state (True=pressed, False=released)
            down_pressed: DOWN button state (True=pressed, False=released)
            select_pressed: SELECT button state (True=pressed, False=released)
            power_pressed: POWER button state (True=pressed, False=released)
        
        Returns:
            bytes: 4-byte packet ready for UART transmission
        """
        # Start with TYPE_BUTTON (0b000xxxxx)
        type_flags = self.TYPE_BUTTON
        
        # Set button state bits in the 5 LSB
        if up_pressed:
            type_flags |= self.BTN_UP
        if down_pressed:
            type_flags |= self.BTN_DOWN
        if select_pressed:
            type_flags |= self.BTN_SELECT
        if power_pressed:
            type_flags |= self.BTN_POWER
        
        # Data bytes are reserved (set to 0x00 as per spec)
        return self.create_packet(type_flags, 0x00, 0x00)
    
    def parse_button_packet(self, packet_bytes):
        """Parse button packet and return button states
        
        Args:
            packet_bytes: 4-byte packet from UART
        
        Returns:
            tuple: (valid, button_states) where button_states is dict with button states
        """
        valid, parsed = self.validate_packet(packet_bytes)
        if not valid:
            return False, None
        
        type_flags, data0, data1, checksum = parsed
        
        # Check if this is a button packet
        if (type_flags & 0xE0) != self.TYPE_BUTTON:
            return False, None
        
        # Extract button states from the 5 LSB
        button_states = {
            'up': bool(type_flags & self.BTN_UP),
            'down': bool(type_flags & self.BTN_DOWN),
            'select': bool(type_flags & self.BTN_SELECT),
            'power': bool(type_flags & self.BTN_POWER)
        }
        
        return True, button_states
    
    def create_led_packet(self, led_id=0, execute=False, mode=0, r4=0, g4=0, b4=0, time_value=0):
        """Create LED control packet according to protocol specification
        
        Args:
            led_id: LED identifier (0-15, 15 for all LEDs)
            execute: True to execute sequence, False to queue
            mode: LED mode (static, blink, fade, rainbow, sequence)
            r4: Red component (4-bit, 0-15)
            g4: Green component (4-bit, 0-15)
            b4: Blue component (4-bit, 0-15)
            time_value: Time/speed parameter (4-bit, 0-15)
            
        Returns:
            bytes: 4-byte packet ready for UART transmission
        """
        # Start with TYPE_LED (0b001xxxxx)
        type_flags = self.TYPE_LED
        
        # Add execute flag (bit 4)
        if execute:
            type_flags |= self.LED_CMD_EXECUTE
        
        # Add LED ID (bits 3-0)
        type_flags |= (led_id & 0x0F)
        
        # Pack color data: data[0] = RRRRGGGG, data[1] = BBBBTTTT
        data0 = ((r4 & 0x0F) << 4) | (g4 & 0x0F)
        data1 = ((b4 & 0x0F) << 4) | (time_value & 0x0F)
        
        return self.create_packet(type_flags, data0, data1)
    
    def create_led_completion_packet(self, led_id, sequence_length):
        """Create LED completion acknowledgment packet according to protocol specification
        
        Args:
            led_id: LED identifier that completed (0-15)
            sequence_length: Number of commands executed (0-255)
            
        Returns:
            bytes: 4-byte acknowledgment packet ready for UART transmission
        """
        # Start with TYPE_LED | LED_CMD_EXECUTE | LED_ID
        type_flags = self.TYPE_LED | self.LED_CMD_EXECUTE | (led_id & 0x0F)
        
        # data[0] = 0xFF (completion indicator as per spec)
        # data[1] = sequence length that was executed
        data0 = 0xFF
        data1 = min(255, max(0, sequence_length))  # Clamp to byte range
        
        return self.create_packet(type_flags, data0, data1)
    
    def create_led_error_packet(self, led_id, error_code):
        """Create LED error report packet
        
        Args:
            led_id: LED identifier that had error (0-15)
            error_code: Error code (1-255)
            
        Returns:
            bytes: 4-byte error packet ready for UART transmission
        """
        # Start with TYPE_LED | LED_CMD_EXECUTE | LED_ID
        type_flags = self.TYPE_LED | self.LED_CMD_EXECUTE | (led_id & 0x0F)
        
        # data[0] = 0xFE (error indicator)
        # data[1] = error code
        data0 = 0xFE
        data1 = min(255, max(1, error_code))  # Error codes 1-255
        
        return self.create_packet(type_flags, data0, data1)
    
    def create_led_status_packet(self, led_id, status_code, status_value=0):
        """Create LED status report packet
        
        Args:
            led_id: LED identifier (0-15)
            status_code: Status type code
            status_value: Optional status value
            
        Returns:
            bytes: 4-byte status packet ready for UART transmission
        """
        # Start with TYPE_LED | LED_CMD_EXECUTE | LED_ID
        type_flags = self.TYPE_LED | self.LED_CMD_EXECUTE | (led_id & 0x0F)
        
        # data[0] = status code (0x00-0xFD, avoiding 0xFE=error, 0xFF=completion)
        # data[1] = status value
        data0 = min(0xFD, max(0, status_code))
        data1 = status_value & 0xFF
        
        return self.create_packet(type_flags, data0, data1)
    
    def parse_led_packet(self, packet_bytes):
        """Parse LED packet and return LED command data
        
        Args:
            packet_bytes: 4-byte packet from UART
            
        Returns:
            tuple: (valid, led_data) where led_data is dict with LED command info
        """
        valid, parsed = self.validate_packet(packet_bytes)
        if not valid:
            return False, None
        
        type_flags, data0, data1, checksum = parsed
        
        # Check if this is an LED packet
        if (type_flags & 0xE0) != self.TYPE_LED:
            return False, None
        
        # Extract LED command fields
        execute = bool(type_flags & self.LED_CMD_EXECUTE)
        led_id = type_flags & 0x0F
        
        # Extract color data
        r4 = (data0 >> 4) & 0x0F
        g4 = data0 & 0x0F
        b4 = (data1 >> 4) & 0x0F
        time_value = data1 & 0x0F
        
        led_data = {
            'execute': execute,
            'led_id': led_id,
            'color': (r4, g4, b4),
            'time_value': time_value,
            'delay_ms': (time_value + 1) * 100
        }
        
        return True, led_data
    
    def parse_led_acknowledgment(self, packet_bytes):
        """Parse LED acknowledgment/status packet
        
        Args:
            packet_bytes: 4-byte packet from UART
            
        Returns:
            tuple: (valid, ack_data) where ack_data contains acknowledgment info
        """
        valid, parsed = self.validate_packet(packet_bytes)
        if not valid:
            return False, None
        
        type_flags, data0, data1, checksum = parsed
        
        # Check if this is an LED packet with execute flag
        if (type_flags & 0xE0) != self.TYPE_LED or not (type_flags & self.LED_CMD_EXECUTE):
            return False, None
        
        led_id = type_flags & 0x0F
        
        # Determine acknowledgment type based on data[0]
        if data0 == 0xFF:
            # Completion acknowledgment
            ack_type = 'completion'
            sequence_length = data1
            ack_data = {
                'type': ack_type,
                'led_id': led_id,
                'sequence_length': sequence_length
            }
        elif data0 == 0xFE:
            # Error report
            ack_type = 'error'
            error_code = data1
            ack_data = {
                'type': ack_type,
                'led_id': led_id,
                'error_code': error_code
            }
        else:
            # Status report
            ack_type = 'status'
            status_code = data0
            status_value = data1
            ack_data = {
                'type': ack_type,
                'led_id': led_id,
                'status_code': status_code,
                'status_value': status_value
            }
        
        return True, ack_data
    
    def get_packet_type(self, packet_bytes):
        """Get the message type from a packet
        
        Args:
            packet_bytes: 4-byte packet
            
        Returns:
            int: Message type (3 MSB of type_flags) or None if invalid
        """
        if len(packet_bytes) != 4:
            return None
        
        type_flags = packet_bytes[0]
        return type_flags & 0xE0