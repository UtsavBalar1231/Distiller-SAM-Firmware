#!/usr/bin/env python3
"""
UART Monitor for RP2040 SAM Firmware Debugging

This script monitors the UART output from the RP2040 to help debug
communication issues between the kernel driver and firmware.

Usage: python3 uart_monitor.py [device]
"""

import sys
import time
import signal
import argparse
import re
from datetime import datetime
from collections import defaultdict
import serial


def signal_handler(sig, frame):  # pylint: disable=unused-argument
    """Handle interrupt signal for clean exit."""
    print("\nUART monitor stopped.")
    print_statistics()
    sys.exit(0)


# Global statistics tracking
stats = {
    "total_lines": 0,
    "uart_rx_packets": 0,
    "uart_tx_packets": 0,
    "valid_packets": 0,
    "invalid_packets": 0,
    "packet_types": defaultdict(int),
    "start_time": time.time(),
}


def print_statistics():
    """Print packet statistics summary"""
    duration = time.time() - stats["start_time"]
    print("\n" + "=" * 60)
    print("UART MONITOR STATISTICS")
    print("=" * 60)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Total lines: {stats['total_lines']}")
    print(f"RX packets: {stats['uart_rx_packets']}")
    print(f"TX packets: {stats['uart_tx_packets']}")
    print(f"Valid packets: {stats['valid_packets']}")
    print(f"Invalid packets: {stats['invalid_packets']}")

    if stats["packet_types"]:
        print("Packet types received:")
        for ptype, count in stats["packet_types"].items():
            print(f"  {ptype}: {count}")

    if stats["uart_rx_packets"] > 0:
        rate = stats["uart_rx_packets"] / duration
        print(f"Average RX rate: {rate:.2f} packets/second")

    print("=" * 60)


def parse_line(line):
    """Parse UART monitor line and extract packet information."""
    stats["total_lines"] += 1

    # Parse different debug message types
    if "[UART-RX]" in line:
        stats["uart_rx_packets"] += 1
        # Extract packet bytes
        match = re.search(r"\[([0-9A-Fa-f ]+)\]", line)
        if match:
            packet_hex = match.group(1)
            return f"RX: [{packet_hex}]"

    elif "[UART-TX]" in line:
        stats["uart_tx_packets"] += 1
        # Extract packet bytes
        match = re.search(r"\[([0-9A-Fa-f ]+)\]", line)
        if match:
            packet_hex = match.group(1)
            return f"TX: [{packet_hex}]"

    elif "[UART-RAW-RX]" in line:
        # Raw data reception
        match = re.search(r"\[([0-9A-Fa-f ]+)\]", line)
        if match:
            packet_hex = match.group(1)
            return f"RAW RX: [{packet_hex}]"

    elif "VALID packet received" in line:
        stats["valid_packets"] += 1
        return "VALID packet from CM5"

    elif "INVALID packet checksum" in line:
        stats["invalid_packets"] += 1
        return "INVALID packet from CM5"

    elif "Processing packet type:" in line:
        # Extract packet type
        match = re.search(r"0x([0-9A-Fa-f]+)", line)
        if match:
            packet_type = match.group(1)
            type_name = get_packet_type_name(packet_type)
            stats["packet_types"][type_name] += 1
            return f"Processing {type_name} packet (0x{packet_type})"

    elif "Packet stats:" in line:
        return line.split("Packet stats: ")[1]

    elif "===" in line:
        return line

    elif "Heartbeat ping sent" in line:
        return "Heartbeat ping sent to kernel driver"

    # Return original line if no special parsing needed
    return line


def get_packet_type_name(hex_type):
    """Convert hex packet type to human-readable name"""
    try:
        type_val = int(hex_type, 16) & 0xE0
        type_map = {
            0x00: "BUTTON",
            0x20: "LED",
            0x40: "POWER",
            0x60: "DISPLAY",
            0x80: "DEBUG_CODE",
            0xA0: "DEBUG_TEXT",
            0xC0: "SYSTEM",
            0xE0: "EXTENDED",
        }
        return type_map.get(type_val, f"UNKNOWN_{hex_type}")
    except ValueError:
        return f"UNKNOWN_{hex_type}"


def main():
    """Main function to run the UART monitor."""
    parser = argparse.ArgumentParser(description="Monitor RP2040 SAM UART output")
    parser.add_argument(
        "device",
        nargs="?",
        default="/dev/ttyACM0",
        help="Serial device (default: /dev/ttyACM0)",
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Read timeout in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--packet-debug",
        action="store_true",
        help="Enable enhanced packet debugging output",
    )

    args = parser.parse_args()

    # Register signal handler for clean exit
    signal.signal(signal.SIGINT, signal_handler)

    print("RP2040 SAM UART Monitor - Enhanced CM5 <-> RP2040 Packet Debugger")
    print(f"Device: {args.device}")
    print(f"Baud rate: {args.baud}")
    print(f"Timeout: {args.timeout}s")
    print(f"Packet debug: {args.packet_debug}")
    print("=" * 70)
    print("Monitoring for CM5 -> RP2040 packet communication")
    print("Green messages = Valid packets received")
    print("Red messages = Invalid/corrupted packets")
    print("Statistics will be shown on exit (Ctrl+C)")
    print("=" * 70)

    try:
        # Open serial connection
        ser = serial.Serial(args.device, args.baud, timeout=args.timeout)
        print(f"Connected to {args.device}")

        # Monitor loop
        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                    if line:
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                        if args.packet_debug:
                            # Enhanced packet debugging
                            parsed_line = parse_line(line)
                            print(f"[{timestamp}] {parsed_line}")
                        else:
                            # Regular output
                            print(f"[{timestamp}] {line}")

                        # Print periodic statistics updates
                        if stats["total_lines"] % 100 == 0 and stats["total_lines"] > 0:
                            print(
                                f"Stats: {stats['uart_rx_packets']} RX, "
                                f"{stats['valid_packets']} valid, {stats['invalid_packets']} invalid"
                            )

                except UnicodeDecodeError as e:
                    print(f"Error reading line: {e}")

            time.sleep(0.01)  # Small delay to prevent high CPU usage

    except serial.SerialException as e:
        print(f"Serial error: {e}")
        print("Make sure the device is connected and accessible")
        sys.exit(1)
    except KeyboardInterrupt:
        print("UART monitor interrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
