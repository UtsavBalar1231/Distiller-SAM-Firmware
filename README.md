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

The project includes a script uploader (`scriptloarder.sh`) to simplify the firmware deployment process. This script automates uploading the firmware to the RP2040 device and supports multiple firmware versions.

#### Prerequisites

- Linux/macOS environment
- Python 3 with pip
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

The script uploader supports several modes and firmware version selection:

1. **Basic Upload** - Upload the latest firmware files to the RP2040:
```bash
./scriptloarder.sh
```

2. **Specific Version Upload** - Upload a specific firmware version:
```bash
./scriptloarder.sh --version V0.2.2
```

3. **First Time Flash** - Flash the MicroPython firmware to a new RP2040:
```bash
./scriptloarder.sh --first
```

4. **Wipe and Flash** - Wipe the RP2040 and flash a new firmware:
```bash
./scriptloarder.sh --wipe
```

5. **Dry Run** - Check device status without making changes:
```bash
./scriptloarder.sh --dry-run
```

6. **Verbose Mode** - Enable detailed output:
```bash
./scriptloarder.sh --verbose
```

#### Available Options

- `--version <version>` - Specify firmware version (e.g., V0.2.2, V0.1.2)
- `--first` - Flash MicroPython firmware only
- `--wipe` - Wipe device and flash MicroPython
- `--dry-run` - Check device status without making changes
- `--verbose` - Enable verbose output
- `-h, --help` - Show help message

#### Firmware Version Selection

The script automatically detects available firmware versions in the `src/` directory. If no version is specified, it defaults to the latest available version. Available versions include:
- `V0.1.2` - Early firmware version
- `V0.2.0` - Intermediate firmware version
- `V0.2.1` - Updated firmware version
- `V0.2.2` - Latest firmware version
- `DistillerOne` - Specialized firmware variant

The script will:
1. Detect the RP2040 device (in bootloader mode for .uf2 files, or normal mode for .py files)
2. Select the appropriate firmware files from the specified version directory
3. Upload the application files (`main.py`, `eink_driver_sam.py`, and binary files from `bin/`)
4. Show progress and status information

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

```
distiller-sam-firmware/
├── src/                          # Firmware versions
│   ├── V0.1.2/                   # Version 0.1.2 firmware
│   │   ├── main.py
│   │   ├── eink_driver_sam.py
│   │   ├── bin/                  # Binary files for e-ink display
│   │   │   ├── loading1.bin
│   │   │   ├── loading2.bin
│   │   │   └── white.bin
│   │   └── upload.sh
│   ├── V0.2.0/                   # Version 0.2.0 firmware
│   ├── V0.2.1/                   # Version 0.2.1 firmware
│   ├── V0.2.2/                   # Latest firmware version
│   └── DistillerOne/             # Specialized firmware variant
├── ULP/                          # MicroPython firmware files
│   ├── RPI_PICO-20240222-v1.22.2.uf2
│   └── flash_nuke.uf2
├── Tools/                        # Development and debugging utilities
├── Asset/                        # Assets and resources
└── scriptloarder.sh              # Automated firmware deployment script
```

## License

[Specify the license here]

## Contributing

[Contribution guidelines if applicable]

## Contact

[Contact information]