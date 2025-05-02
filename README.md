# Distiller-SAM-Firmware

## Overview

Distiller-SAM-Firmware is a firmware project for a device that utilizes a combination of a Raspberry Pi Pico (RP2040) and a SAM (System on Module) to control an e-ink display, manage power, handle user input, and communicate between components. The firmware manages various hardware components including buttons, an e-ink display, LEDs, and a battery management system.

## Architecture

The system consists of:

1. **RP2040 Microcontroller** - Handles the primary firmware logic, button inputs, and communication with other components
2. **E-ink Display** - A 240x416 pixel display managed through a custom driver
3. **Button Interface** - Three physical buttons (Up, Down, Select) for user input
4. **Communication** - UART interface between RP2040 and SAM
5. **Battery Management** - Interface for battery monitoring
6. **NeoPixel LED** - For visual status indicators
7. **Fan Control** - Components for temperature management

## Key Components

### Main Controller

The main controller manages power states, button input, and communication between components. It implements:
- Button debouncing
- Power management routines
- E-ink display sequencing
- UART communication with the SAM module

### E-ink Driver

A custom driver (`eink_driver_sam.py`) manages the e-ink display through SPI communication, providing:
- Display initialization (full and partial refresh modes)
- Image loading and display from binary files
- Power management for the display

### Battery Management

The `battery.py` module provides an interface to the battery management system, allowing:
- Voltage monitoring
- Temperature reading
- Remaining capacity estimation

## Development

### Setup

1. Clone the repository:
```bash
git clone https://github.com/your-username/Distiller-SAM-Firmware.git
cd Distiller-SAM-Firmware
```

2. Install the required MicroPython firmware to the RP2040:
   - Use the firmware in the ULP folder: `RPI_PICO-20240222-v1.22.2.uf2`

3. Deploy the firmware files to the RP2040 using your preferred MicroPython deployment method

### Script Uploader

The project includes a script uploader (`scriptloarder.sh`) to simplify the firmware deployment process. This script automates uploading the firmware to the RP2040 device.

#### Prerequisites

- macOS environment (the script uses macOS-specific paths)
- Homebrew installed
- The `ampy` utility for uploading files to MicroPython devices

#### Installation

1. Install the required dependencies:
```bash
pip install adafruit-ampy
```

2. Make the script executable:
```bash
chmod +x scriptloarder.sh
```

#### Usage

The script uploader supports several modes:

1. **Basic Upload** - Upload the firmware files to the RP2040:
```bash
./scriptloarder.sh
```

2. **First Time Flash** - Flash the MicroPython firmware to a new RP2040:
```bash
./scriptloarder.sh --first
```

3. **Wipe and Flash** - Wipe the RP2040 and flash a new firmware:
```bash
./scriptloarder.sh --wipe
```

The script will:
1. Wait for the RP2040 device to be detected
2. Copy the necessary firmware files
3. Upload the application files (`main.py`, `eink_driver_sam.py`, and binary files)
4. Show a progress bar during the upload process

### Hardware Requirements

- Raspberry Pi Pico (RP2040)
- SAM Module
- E-ink Display (240x416)
- Battery and BMS
- Button inputs
- NeoPixel RGB LED

## Configuration

The system has configurable parameters in the main scripts:
- `PRODUCTION` flag to enable/disable USB debugging
- `UART_DEBUG` flag for UART debugging output
- Watchdog timeout settings
- Button debounce timing

## Files Structure

- `main.py` - Primary firmware for the RP2040
- `eink_driver_sam.py` - E-ink display driver
- `battery.py` - Battery management system interface
- `cm4/` - SAM module firmware
- `ULP/` - MicroPython firmware files
- `Fan/` - Fan control components
- `tools/` - Development and debugging utilities
- `scriptloarder.sh` - Script to automate firmware deployment
- `Bin/` - Binary files for the e-ink display

## License

[Specify the license here]

## Contributing

[Contribution guidelines if applicable]

## Contact

[Contact information]