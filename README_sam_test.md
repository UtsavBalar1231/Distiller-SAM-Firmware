# SAM Protocol Test Script

This Python script allows you to test the Pamir SAM UART protocol communication between a Raspberry Pi and the RP2040 microcontroller.

## Features

- **Button Event Monitoring**: Automatically receives and displays button press/release events from the RP2040
- **LED Control**: Send RGB color commands to control LEDs on the device
- **Battery/Power Monitoring**: Request and display power metrics (current, voltage, battery percentage, temperature)
- **Communication Testing**: Ping functionality to test connectivity

## Prerequisites

1. **Hardware**: Pamir AI CM5 device with RP2040 running SAM firmware
2. **Driver**: The `pamir-ai-sam` kernel driver must be loaded
3. **Permissions**: Access to `/dev/pamir-sam` device (may need sudo)

## Installation

1. Make the script executable:
```bash
chmod +x sam_protocol_test.py
```

2. Ensure you have Python 3.6+ installed (usually pre-installed on Raspberry Pi OS)

## Usage

### Basic Usage

Run the script with:
```bash
sudo python3 sam_protocol_test.py
```

Or if you have proper permissions:
```bash
python3 sam_protocol_test.py
```

### Available Commands

Once the script is running, you can use these interactive commands:

#### LED Control
- `r 15` - Set LED to full red intensity
- `g 8` - Set LED to medium green intensity  
- `b 3` - Set LED to low blue intensity
- `w 10` - Set LED to white (intensity 10)
- `off` - Turn off LED
- `blink r 15` - Blink LED in red
- `blink g 8` - Blink LED in green
- `blink b 5` - Blink LED in blue

#### Power/Battery Monitoring
- `power` - Request all power metrics from RP2040

#### Communication Testing
- `ping` - Test connectivity with RP2040

#### Information Commands
- `stats` - Show communication statistics
- `help` - Display command help
- `quit` - Exit the program

### Example Session

```
Pamir SAM Protocol Test Script
==============================
Successfully opened /dev/pamir-sam
Receive thread started

Sending initial ping...
TX: C00000C0

Available commands:
  r, g, b <0-15>  - Set LED to red, green, or blue (0-15 intensity)
  w <0-15>        - Set LED to white (0-15 intensity)  
  off             - Turn off LED
  blink r/g/b <0-15> - Blink LED in red/green/blue
  power           - Request power/battery metrics
  ping            - Send ping command
  stats           - Show communication statistics
  help            - Show this help
  quit            - Exit program

Button events will be displayed automatically when pressed.

sam> r 15
Setting LED to red (intensity 15)...
TX: 2FF020DF

sam> power
Requesting power metrics...
TX: 80000080
RX: 40FA0000BA - POWER: current_ma = 250
RX: 504B004B9B - POWER: battery_percent = 75
RX: 60190019F9 - POWER: temperature_celsius = 25.0°C
RX: 70D80F00E7 - POWER: voltage_mv = 4056

sam> RX: 01000001 - BUTTONS: UP pressed
RX: 00000000 - BUTTONS: All released

sam> stats

==================================================
COMMUNICATION STATISTICS
==================================================
Packets sent:     3
Packets received: 6
Button events:    2

Latest Power Metrics:
  current_ma: 250
  battery_percent: 75
  temperature_celsius: 25.0°C
  voltage_mv: 4056
==================================================

sam> quit
```

## Protocol Details

### Button Events
The script automatically displays button events as they occur:
- UP, DOWN, SELECT, POWER buttons are supported
- Shows which buttons are pressed and when they're released
- Events are received from RP2040 automatically

### LED Control
- Color intensity ranges from 0-15 (4-bit per channel)
- LED ID 15 controls all LEDs (default)
- Static colors and blinking animations supported
- Commands are sent immediately to RP2040

### Power Metrics
- Current draw in milliamps (mA)
- Battery percentage (0-100%)
- Temperature in Celsius
- Voltage in millivolts (mV)
- Metrics are requested on-demand from RP2040

## Troubleshooting

### Device Not Found
```
Error: Device /dev/pamir-sam not found
```
**Solution**: Ensure the pamir-ai-sam driver is loaded:
```bash
sudo modprobe pamir-ai-sam debug=3
lsmod | grep pamir
```

### Permission Denied
```
Error: Permission denied accessing /dev/pamir-sam
```
**Solution**: Run with sudo or add user to appropriate group:
```bash
sudo python3 sam_protocol_test.py
```

### No Communication
If you don't see responses from RP2040:
1. Check that RP2040 firmware is running
2. Verify UART connections
3. Enable driver debugging:
```bash
sudo modprobe pamir-ai-sam debug=3
dmesg -w | grep pamir
```

### Invalid Packets
If you see "INVALID CHECKSUM" messages:
- Check for electrical interference
- Verify baud rate (should be 115200)
- Ensure firmware protocol version matches

## Exit

Press `Ctrl+C` or type `quit` to exit the script safely.

## Files

- `sam_protocol_test.py` - Main test script
- `README_sam_test.md` - This documentation 