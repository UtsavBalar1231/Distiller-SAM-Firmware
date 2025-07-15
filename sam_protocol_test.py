#!/usr/bin/env python3
"""
Pamir SAM Protocol Test Script
Tests communication with RP2040 via SAM protocol.

Features:
- Receive and display button events from RP2040
- Send RGB LED commands to RP2040
- Request and display battery/power information
"""

import os
import sys
import time
import threading
import signal
from typing import Optional, Tuple, Dict, Any

# Protocol constants based on documentation
TYPE_BUTTON = 0x00      # 0b000xxxxx
TYPE_LED = 0x20         # 0b001xxxxx  
TYPE_POWER = 0x40       # 0b010xxxxx
TYPE_SYSTEM = 0xC0      # 0b110xxxxx

# Power command types
POWER_CMD_REQUEST_METRICS = 0x80
POWER_CMD_CURRENT = 0x40
POWER_CMD_BATTERY = 0x50
POWER_CMD_TEMP = 0x60
POWER_CMD_VOLTAGE = 0x70

# Button bit masks
BUTTON_UP = 0x01
BUTTON_DOWN = 0x02
BUTTON_SELECT = 0x04
BUTTON_POWER = 0x08

# LED addressing
LED_ALL = 15  # Special ID for all LEDs

class SAMProtocol:
    """SAM Protocol handler for Raspberry Pi side communication."""
    
    def __init__(self, device_path: str = "/dev/pamir-sam"):
        """Initialize the SAM protocol handler."""
        self.device_path = device_path
        self.device = None
        self.running = False
        self.receive_thread = None
        
        # Statistics
        self.packets_sent = 0
        self.packets_received = 0
        self.button_events = 0
        self.power_metrics = {}
        
    def calculate_checksum(self, packet_bytes: bytes) -> int:
        """Calculate XOR checksum for packet (first 3 bytes)."""
        return packet_bytes[0] ^ packet_bytes[1] ^ packet_bytes[2]
    
    def create_packet(self, type_flags: int, data0: int, data1: int) -> bytes:
        """Create a 4-byte protocol packet with checksum."""
        packet = bytes([type_flags, data0, data1, 0])
        checksum = self.calculate_checksum(packet)
        return bytes([type_flags, data0, data1, checksum])
    
    def validate_packet(self, packet: bytes) -> bool:
        """Validate packet checksum."""
        if len(packet) != 4:
            return False
        expected_checksum = self.calculate_checksum(packet[:3])
        return packet[3] == expected_checksum
    
    def get_packet_type(self, packet: bytes) -> int:
        """Extract packet type from type_flags byte."""
        return packet[0] & 0xE0  # Upper 3 bits
    
    def open_device(self) -> bool:
        """Open the SAM character device."""
        try:
            if not os.path.exists(self.device_path):
                print(f"Error: Device {self.device_path} not found")
                print("Make sure the pamir-ai-sam driver is loaded and device exists")
                return False
                
            self.device = open(self.device_path, "rb+", buffering=0)
            print(f"Successfully opened {self.device_path}")
            return True
            
        except PermissionError:
            print(f"Error: Permission denied accessing {self.device_path}")
            print("Try running with sudo or add your user to the appropriate group")
            return False
        except Exception as e:
            print(f"Error opening device: {e}")
            return False
    
    def close_device(self):
        """Close the SAM character device."""
        if self.device:
            self.device.close()
            self.device = None
    
    def send_packet(self, packet: bytes) -> bool:
        """Send a packet to the RP2040."""
        try:
            if not self.device:
                print("Error: Device not open")
                return False
                
            self.device.write(packet)
            self.packets_sent += 1
            print(f"TX: {packet.hex().upper()}")
            return True
            
        except Exception as e:
            print(f"Error sending packet: {e}")
            return False
    
    def receive_packet(self) -> Optional[bytes]:
        """Receive a packet from the RP2040 (non-blocking)."""
        try:
            if not self.device:
                return None
                
            # Try to read 4 bytes
            packet = self.device.read(4)
            if len(packet) == 4:
                self.packets_received += 1
                return packet
            elif len(packet) > 0:
                print(f"Warning: Partial packet received ({len(packet)} bytes)")
            return None
            
        except Exception as e:
            print(f"Error receiving packet: {e}")
            return None
    
    def decode_button_packet(self, packet: bytes) -> Dict[str, bool]:
        """Decode button state from packet."""
        button_state = packet[0] & 0x0F  # Lower 4 bits
        return {
            'up': bool(button_state & BUTTON_UP),
            'down': bool(button_state & BUTTON_DOWN), 
            'select': bool(button_state & BUTTON_SELECT),
            'power': bool(button_state & BUTTON_POWER)
        }
    
    def decode_power_packet(self, packet: bytes) -> Optional[Tuple[str, int]]:
        """Decode power metrics from packet."""
        packet_type = packet[0] & 0xF0
        
        # Convert 16-bit little-endian value
        value = packet[1] | (packet[2] << 8)
        
        if packet_type == POWER_CMD_CURRENT:
            return ("current_ma", value)
        elif packet_type == POWER_CMD_BATTERY:
            return ("battery_percent", value)
        elif packet_type == POWER_CMD_TEMP:
            # Temperature in 0.1°C, convert to °C
            temp_celsius = value / 10.0 if value < 32768 else (value - 65536) / 10.0
            return ("temperature_celsius", temp_celsius)
        elif packet_type == POWER_CMD_VOLTAGE:
            return ("voltage_mv", value)
        
        return None
    
    def process_received_packet(self, packet: bytes):
        """Process a received packet and print information."""
        if not self.validate_packet(packet):
            print(f"RX: {packet.hex().upper()} (INVALID CHECKSUM)")
            return
            
        packet_type = self.get_packet_type(packet)
        print(f"RX: {packet.hex().upper()}", end="")
        
        if packet_type == TYPE_BUTTON:
            buttons = self.decode_button_packet(packet)
            pressed = [name for name, state in buttons.items() if state]
            if pressed:
                print(f" - BUTTONS: {', '.join(pressed).upper()} pressed")
            else:
                print(" - BUTTONS: All released")
            self.button_events += 1
            
        elif packet_type == TYPE_POWER:
            power_info = self.decode_power_packet(packet)
            if power_info:
                metric, value = power_info
                self.power_metrics[metric] = value
                if metric == "temperature_celsius":
                    print(f" - POWER: {metric} = {value:.1f}°C")
                else:
                    print(f" - POWER: {metric} = {value}")
            else:
                print(" - POWER: Unknown power packet")
                
        elif packet_type == TYPE_SYSTEM:
            print(" - SYSTEM: System command response")
            
        else:
            print(f" - UNKNOWN: Type 0x{packet_type:02X}")
    
    def receive_thread_func(self):
        """Background thread to continuously receive packets."""
        print("Receive thread started")
        
        while self.running:
            packet = self.receive_packet()
            if packet:
                self.process_received_packet(packet)
            else:
                time.sleep(0.01)  # Small delay to prevent busy waiting
                
        print("Receive thread stopped")
    
    def start_receiving(self):
        """Start the packet receiving thread."""
        if self.receive_thread and self.receive_thread.is_alive():
            return
            
        self.running = True
        self.receive_thread = threading.Thread(target=self.receive_thread_func, daemon=True)
        self.receive_thread.start()
    
    def stop_receiving(self):
        """Stop the packet receiving thread."""
        self.running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=1.0)
    
    # LED Control Methods
    def send_led_command(self, led_id: int = LED_ALL, red: int = 0, green: int = 0, 
                        blue: int = 0, time_value: int = 0) -> bool:
        """
        Send LED color command.
        
        Args:
            led_id: LED ID (0-15, or 15 for all LEDs)
            red: Red component (0-15)
            green: Green component (0-15) 
            blue: Blue component (0-15)
            time_value: Animation time value (0-15, 0=static)
        """
        # Clamp values to 4-bit range
        red = max(0, min(15, red))
        green = max(0, min(15, green))
        blue = max(0, min(15, blue))
        time_value = max(0, min(15, time_value))
        led_id = max(0, min(15, led_id))
        
        type_flags = TYPE_LED | led_id
        data0 = (red << 4) | green
        data1 = (blue << 4) | time_value
        
        packet = self.create_packet(type_flags, data0, data1)
        return self.send_packet(packet)
    
    def set_led_color(self, red: int, green: int, blue: int, led_id: int = LED_ALL):
        """Set LED to static color."""
        return self.send_led_command(led_id, red, green, blue, 0)
    
    def set_led_blink(self, red: int, green: int, blue: int, speed: int = 5, led_id: int = LED_ALL):
        """Set LED to blink with color."""
        return self.send_led_command(led_id, red, green, blue, speed)
    
    # Power Management Methods
    def request_power_metrics(self) -> bool:
        """Request all power metrics from RP2040."""
        packet = self.create_packet(POWER_CMD_REQUEST_METRICS, 0x00, 0x00)
        return self.send_packet(packet)
    
    def send_ping(self) -> bool:
        """Send ping command to test communication."""
        packet = self.create_packet(TYPE_SYSTEM, 0x00, 0x00)
        return self.send_packet(packet)
    
    def print_statistics(self):
        """Print communication statistics."""
        print("\n" + "="*50)
        print("COMMUNICATION STATISTICS")
        print("="*50)
        print(f"Packets sent:     {self.packets_sent}")
        print(f"Packets received: {self.packets_received}")
        print(f"Button events:    {self.button_events}")
        
        if self.power_metrics:
            print("\nLatest Power Metrics:")
            for metric, value in self.power_metrics.items():
                if metric == "temperature_celsius":
                    print(f"  {metric}: {value:.1f}°C")
                else:
                    print(f"  {metric}: {value}")
        print("="*50)


def print_help():
    """Print available commands."""
    print("\nAvailable commands:")
    print("  r, g, b <0-15>  - Set LED to red, green, or blue (0-15 intensity)")
    print("  w <0-15>        - Set LED to white (0-15 intensity)")
    print("  off             - Turn off LED")
    print("  blink r/g/b <0-15> - Blink LED in red/green/blue")
    print("  power           - Request power/battery metrics")
    print("  ping            - Send ping command")
    print("  stats           - Show communication statistics")
    print("  help            - Show this help")
    print("  quit            - Exit program")
    print("\nButton events will be displayed automatically when pressed.")


def main():
    """Main test program."""
    print("Pamir SAM Protocol Test Script")
    print("==============================")
    
    # Initialize protocol handler
    sam = SAMProtocol()
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nShutting down...")
        sam.stop_receiving()
        sam.close_device()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Open device
    if not sam.open_device():
        sys.exit(1)
    
    # Start receiving packets
    sam.start_receiving()
    
    # Send initial ping to test communication
    print("\nSending initial ping...")
    sam.send_ping()
    
    print_help()
    
    # Interactive command loop
    try:
        while True:
            try:
                cmd = input("\nsam> ").strip().lower()
                
                if not cmd:
                    continue
                    
                parts = cmd.split()
                
                if cmd == "quit" or cmd == "exit":
                    break
                    
                elif cmd == "help":
                    print_help()
                    
                elif cmd == "stats":
                    sam.print_statistics()
                    
                elif cmd == "ping":
                    print("Sending ping...")
                    sam.send_ping()
                    
                elif cmd == "power":
                    print("Requesting power metrics...")
                    sam.request_power_metrics()
                    
                elif cmd == "off":
                    print("Turning LED off...")
                    sam.set_led_color(0, 0, 0)
                    
                elif parts[0] in ['r', 'red'] and len(parts) == 2:
                    intensity = int(parts[1])
                    print(f"Setting LED to red (intensity {intensity})...")
                    sam.set_led_color(intensity, 0, 0)
                    
                elif parts[0] in ['g', 'green'] and len(parts) == 2:
                    intensity = int(parts[1])
                    print(f"Setting LED to green (intensity {intensity})...")
                    sam.set_led_color(0, intensity, 0)
                    
                elif parts[0] in ['b', 'blue'] and len(parts) == 2:
                    intensity = int(parts[1])
                    print(f"Setting LED to blue (intensity {intensity})...")
                    sam.set_led_color(0, 0, intensity)
                    
                elif parts[0] in ['w', 'white'] and len(parts) == 2:
                    intensity = int(parts[1])
                    print(f"Setting LED to white (intensity {intensity})...")
                    sam.set_led_color(intensity, intensity, intensity)
                    
                elif parts[0] == "blink" and len(parts) == 3:
                    color = parts[1].lower()
                    intensity = int(parts[2])
                    speed = 5  # Default blink speed
                    
                    if color in ['r', 'red']:
                        print(f"Blinking LED red (intensity {intensity})...")
                        sam.set_led_blink(intensity, 0, 0, speed)
                    elif color in ['g', 'green']:
                        print(f"Blinking LED green (intensity {intensity})...")
                        sam.set_led_blink(0, intensity, 0, speed)
                    elif color in ['b', 'blue']:
                        print(f"Blinking LED blue (intensity {intensity})...")
                        sam.set_led_blink(0, 0, intensity, speed)
                    else:
                        print("Invalid color. Use r, g, or b")
                        
                else:
                    print("Unknown command. Type 'help' for available commands.")
                    
            except ValueError:
                print("Invalid number format. Use integers 0-15 for intensity.")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error processing command: {e}")
                
    finally:
        print("\nCleaning up...")
        sam.stop_receiving()
        sam.close_device()
        sam.print_statistics()


if __name__ == "__main__":
    main() 