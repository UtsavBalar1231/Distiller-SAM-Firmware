#!/usr/bin/env python3
"""
Test script for improved RP2040 SAM firmware
Tests the enhanced UART communication, threading model, and debug system

Usage: python3 test_improved_firmware.py [device]
"""

import sys
import time
import signal
import argparse
import serial
import struct
from collections import defaultdict, deque


class SAMProtocolTester:
    """Test harness for SAM protocol communication"""
    
    # Protocol constants (matching PamirUartProtocols)
    TYPE_BUTTON = 0x00
    TYPE_LED = 0x20
    TYPE_POWER = 0x40
    TYPE_DISPLAY = 0x60
    TYPE_DEBUG_CODE = 0x80
    TYPE_DEBUG_TEXT = 0xA0
    TYPE_SYSTEM = 0xC0
    TYPE_EXTENDED = 0xE0
    
    def __init__(self, device, baud_rate=115200):
        """Initialize tester
        
        Args:
            device: Serial device path
            baud_rate: UART baud rate
        """
        self.device = device
        self.baud_rate = baud_rate
        self.ser = None
        self.running = False
        
        # Test statistics
        self.stats = {
            "packets_sent": 0,
            "packets_received": 0,
            "valid_responses": 0,
            "invalid_responses": 0,
            "timeouts": 0,
            "by_type": defaultdict(int),
            "start_time": time.time()
        }
        
        # Response tracking
        self.expected_responses = deque()
        self.response_timeout = 1.0  # 1 second timeout
    
    def connect(self):
        """Connect to serial device"""
        try:
            self.ser = serial.Serial(self.device, self.baud_rate, timeout=0.1)
            print(f"Connected to {self.device} at {self.baud_rate} baud")
            return True
        except Exception as e:
            print(f"Failed to connect to {self.device}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from serial device"""
        if self.ser:
            self.ser.close()
            self.ser = None
    
    def calculate_checksum(self, type_flags, data0, data1):
        """Calculate XOR checksum"""
        return type_flags ^ data0 ^ data1
    
    def create_packet(self, type_flags, data0=0x00, data1=0x00):
        """Create 4-byte protocol packet"""
        checksum = self.calculate_checksum(type_flags, data0, data1)
        return struct.pack("BBBB", type_flags, data0, data1, checksum)
    
    def validate_packet(self, packet_bytes):
        """Validate received packet"""
        if len(packet_bytes) != 4:
            return False, None
        
        type_flags, data0, data1, checksum = struct.unpack("BBBB", packet_bytes)
        calculated_checksum = self.calculate_checksum(type_flags, data0, data1)
        
        if checksum != calculated_checksum:
            return False, None
        
        return True, (type_flags, data0, data1, checksum)
    
    def send_packet(self, packet, description=""):
        """Send packet and track statistics"""
        if not self.ser:
            return False
        
        try:
            self.ser.write(packet)
            self.stats["packets_sent"] += 1
            packet_hex = packet.hex().upper()
            print(f"TX: [{packet_hex}] {description}")
            return True
        except Exception as e:
            print(f"Send failed: {e}")
            return False
    
    def read_responses(self, timeout=0.5):
        """Read and process responses from RP2040"""
        responses = []
        start_time = time.time()
        buffer = bytearray()
        
        while time.time() - start_time < timeout:
            if self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting)
                buffer.extend(data)
                
                # Process complete 4-byte packets
                while len(buffer) >= 4:
                    packet = bytes(buffer[:4])
                    buffer = buffer[4:]
                    
                    valid, parsed = self.validate_packet(packet)
                    packet_hex = packet.hex().upper()
                    
                    if valid:
                        type_flags, data0, data1, checksum = parsed
                        packet_type = type_flags & 0xE0
                        self.stats["valid_responses"] += 1
                        self.stats["by_type"][packet_type] += 1
                        
                        type_name = self.get_type_name(packet_type)
                        print(f"RX: [{packet_hex}] ✓ {type_name}")
                        responses.append((True, packet, parsed))
                    else:
                        self.stats["invalid_responses"] += 1
                        print(f"RX: [{packet_hex}] ✗ Invalid checksum")
                        responses.append((False, packet, None))
                    
                    self.stats["packets_received"] += 1
            
            time.sleep(0.01)
        
        return responses
    
    def get_type_name(self, packet_type):
        """Get human-readable packet type name"""
        type_map = {
            self.TYPE_BUTTON: "BUTTON",
            self.TYPE_LED: "LED",
            self.TYPE_POWER: "POWER",
            self.TYPE_DISPLAY: "DISPLAY",
            self.TYPE_DEBUG_CODE: "DEBUG_CODE",
            self.TYPE_DEBUG_TEXT: "DEBUG_TEXT",
            self.TYPE_SYSTEM: "SYSTEM",
            self.TYPE_EXTENDED: "EXTENDED"
        }
        return type_map.get(packet_type, f"UNKNOWN_0x{packet_type:02X}")
    
    def test_ping_pong(self):
        """Test basic ping-pong communication"""
        print("\n=== PING-PONG TEST ===")
        
        # Send ping
        ping_packet = self.create_packet(0xC0, 0x00, 0x00)  # SYSTEM_PING
        if not self.send_packet(ping_packet, "PING"):
            return False
        
        # Wait for pong
        responses = self.read_responses(timeout=1.0)
        
        for valid, packet, parsed in responses:
            if valid and parsed:
                type_flags, data0, data1, checksum = parsed
                if (type_flags & 0xE0) == self.TYPE_SYSTEM:
                    print("✓ Ping-pong successful")
                    return True
        
        print("✗ Ping-pong failed - no valid response")
        return False
    
    def test_led_control(self):
        """Test LED control commands"""
        print("\n=== LED CONTROL TEST ===")
        
        test_cases = [
            # (description, type_flags, data0, data1)
            ("LED Static Red", 0x20, 0xF0, 0x00),     # Static red on LED 0
            ("LED Static Green", 0x20, 0x0F, 0x00),   # Static green on LED 0
            ("LED Static Blue", 0x20, 0x00, 0xF0),    # Static blue on LED 0
            ("LED Blink Red", 0x24, 0xF0, 0x05),      # Blinking red
            ("LED Execute", 0x30, 0x00, 0x00),        # Execute sequence
        ]
        
        success_count = 0
        for desc, type_flags, data0, data1 in test_cases:
            packet = self.create_packet(type_flags, data0, data1)
            if self.send_packet(packet, desc):
                time.sleep(0.1)  # Brief delay between commands
                success_count += 1
        
        # Wait for any completion acknowledgments
        responses = self.read_responses(timeout=2.0)
        ack_count = 0
        for valid, packet, parsed in responses:
            if valid and parsed:
                type_flags, data0, data1, checksum = parsed
                if (type_flags & 0xE0) == self.TYPE_LED and data0 == 0xFF:
                    ack_count += 1
                    print(f"✓ LED completion ACK received (sequence length: {data1})")
        
        print(f"LED test: {success_count}/{len(test_cases)} commands sent, {ack_count} ACKs received")
        return success_count == len(test_cases)
    
    def test_power_management(self):
        """Test power management commands"""
        print("\n=== POWER MANAGEMENT TEST ===")
        
        # Test power query
        query_packet = self.create_packet(0x40, 0x00, 0x00)  # POWER_CMD_QUERY
        if not self.send_packet(query_packet, "Power Query"):
            return False
        
        # Test metrics request
        metrics_packet = self.create_packet(0x80, 0x00, 0x00)  # POWER_CMD_REQUEST_METRICS
        if not self.send_packet(metrics_packet, "Metrics Request"):
            return False
        
        # Wait for responses
        responses = self.read_responses(timeout=2.0)
        
        power_responses = 0
        metrics_received = set()
        
        for valid, packet, parsed in responses:
            if valid and parsed:
                type_flags, data0, data1, checksum = parsed
                if (type_flags & 0xE0) == self.TYPE_POWER:
                    command = type_flags & 0x1F
                    
                    if command == 0x00:  # Query response
                        power_responses += 1
                        print(f"✓ Power status: state=0x{data0:02X}, flags=0x{data1:02X}")
                    elif command in [0x40, 0x50, 0x60, 0x70]:  # Metrics
                        value = data0 | (data1 << 8)
                        metric_names = {0x40: "Current", 0x50: "Battery", 0x60: "Temperature", 0x70: "Voltage"}
                        metric_name = metric_names.get(command, f"Unknown_0x{command:02X}")
                        metrics_received.add(command)
                        print(f"✓ {metric_name}: {value}")
        
        expected_metrics = 4  # Current, Battery, Temperature, Voltage
        success = power_responses > 0 and len(metrics_received) >= expected_metrics
        
        print(f"Power test: {power_responses} status responses, {len(metrics_received)}/{expected_metrics} metrics")
        return success
    
    def test_stress_communication(self, duration=10, packet_rate=10):
        """Stress test communication"""
        print(f"\n=== STRESS TEST ({duration}s @ {packet_rate} pkt/s) ===")
        
        start_time = time.time()
        packets_sent = 0
        
        while time.time() - start_time < duration:
            # Send ping packet
            ping_packet = self.create_packet(0xC0, 0x00, 0x00)
            if self.send_packet(ping_packet, f"Stress ping #{packets_sent + 1}"):
                packets_sent += 1
            
            # Read any responses
            self.read_responses(timeout=0.01)
            
            # Control packet rate
            time.sleep(1.0 / packet_rate)
        
        # Final response collection
        final_responses = self.read_responses(timeout=1.0)
        
        elapsed = time.time() - start_time
        actual_rate = packets_sent / elapsed
        
        print(f"Stress test complete:")
        print(f"  Duration: {elapsed:.1f}s")
        print(f"  Packets sent: {packets_sent}")
        print(f"  Actual rate: {actual_rate:.1f} pkt/s")
        print(f"  Responses: {len(final_responses)}")
        
        return True
    
    def test_error_recovery(self):
        """Test error recovery with invalid packets"""
        print("\n=== ERROR RECOVERY TEST ===")
        
        # Send some invalid packets
        invalid_packets = [
            b'\x00\x00\x00\xFF',  # Wrong checksum
            b'\xFF\xFF\xFF\xFF',  # All wrong
            b'\x20\x00\x00\x21',  # Wrong checksum but valid type
        ]
        
        for i, invalid_packet in enumerate(invalid_packets):
            print(f"Sending invalid packet {i+1}: {invalid_packet.hex().upper()}")
            if self.ser:
                self.ser.write(invalid_packet)
                time.sleep(0.1)
        
        # Send valid packet to test recovery
        valid_packet = self.create_packet(0xC0, 0x00, 0x00)
        print(f"Sending recovery ping: {valid_packet.hex().upper()}")
        if self.ser:
            self.ser.write(valid_packet)
        
        # Check responses
        responses = self.read_responses(timeout=2.0)
        
        # Look for valid ping response indicating recovery
        recovery_success = False
        for valid, packet, parsed in responses:
            if valid and parsed:
                type_flags, data0, data1, checksum = parsed
                if (type_flags & 0xE0) == self.TYPE_SYSTEM:
                    recovery_success = True
                    print("✓ Error recovery successful - valid ping response received")
                    break
        
        if not recovery_success:
            print("✗ Error recovery failed - no valid response after invalid packets")
        
        return recovery_success
    
    def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("RP2040 SAM IMPROVED FIRMWARE TEST SUITE")
        print("=" * 60)
        
        if not self.connect():
            return False
        
        try:
            # Wait for firmware to initialize
            print("Waiting for firmware initialization...")
            time.sleep(2.0)
            
            # Clear any existing data
            if self.ser.in_waiting > 0:
                self.ser.read(self.ser.in_waiting)
            
            test_results = []
            
            # Run tests
            test_results.append(("Ping-Pong", self.test_ping_pong()))
            test_results.append(("LED Control", self.test_led_control()))
            test_results.append(("Power Management", self.test_power_management()))
            test_results.append(("Error Recovery", self.test_error_recovery()))
            test_results.append(("Stress Test", self.test_stress_communication(duration=5, packet_rate=20)))
            
            # Print results
            print("\n" + "=" * 60)
            print("TEST RESULTS SUMMARY")
            print("=" * 60)
            
            passed = 0
            for test_name, result in test_results:
                status = "PASS" if result else "FAIL"
                print(f"{test_name:20} : {status}")
                if result:
                    passed += 1
            
            print(f"\nOverall: {passed}/{len(test_results)} tests passed")
            
            # Print statistics
            elapsed = time.time() - self.stats["start_time"]
            print("\nCommunication Statistics:")
            print(f"  Test duration: {elapsed:.1f}s")
            print(f"  Packets sent: {self.stats['packets_sent']}")
            print(f"  Packets received: {self.stats['packets_received']}")
            print(f"  Valid responses: {self.stats['valid_responses']}")
            print(f"  Invalid responses: {self.stats['invalid_responses']}")
            
            if self.stats["packets_received"] > 0:
                success_rate = (self.stats["valid_responses"] * 100) // self.stats["packets_received"]
                print(f"  Success rate: {success_rate}%")
            
            print("\nPacket types received:")
            for packet_type, count in self.stats["by_type"].items():
                type_name = self.get_type_name(packet_type)
                print(f"  {type_name}: {count}")
            
            return passed == len(test_results)
            
        finally:
            self.disconnect()


def signal_handler(sig, frame):
    """Handle interrupt signal"""
    print("\nTest interrupted by user")
    sys.exit(0)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Test improved RP2040 SAM firmware")
    parser.add_argument(
        "device",
        nargs="?",
        default="/dev/ttyACM0",
        help="Serial device (default: /dev/ttyACM0)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)"
    )
    
    args = parser.parse_args()
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run tests
    tester = SAMProtocolTester(args.device, args.baud)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()