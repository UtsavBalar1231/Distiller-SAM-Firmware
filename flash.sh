#!/bin/bash

# Simplified RP2040 Firmware Loader

show_usage() {
	cat <<EOF
Usage: $0 [OPTIONS]

RP2040 firmware and file uploader:
  ./flash.sh           - Upload files to RP2040
  ./flash.sh --first   - Flash MicroPython firmware
  ./flash.sh --wipe    - Wipe device and flash MicroPython

Options:
  -h, --help     Show this help
  -v, --verbose  Enable verbose output
  --first        Flash MicroPython firmware only
  --wipe         Wipe device and flash MicroPython
  --dry-run      Check device status
  --version VER  Specify firmware version

Instructions:
1. Hold BOOTSEL while connecting for firmware flashing
2. Connect normally for MicroPython file upload
EOF
}

# Global variables
VERBOSE=false
FIRST_TIME_FLASH=false
WIPE_AND_FLASH=false
DRY_RUN=false
FIRMWARE_VERSION=""

# Parse arguments
while [[ $# -gt 0 ]]; do
	case $1 in
	-h | --help)
		show_usage
		exit 0
		;;
	-v | --verbose)
		VERBOSE=true
		shift
		;;
	--first)
		FIRST_TIME_FLASH=true
		shift
		;;
	--wipe)
		WIPE_AND_FLASH=true
		shift
		;;
	--dry-run)
		DRY_RUN=true
		shift
		;;
	--version)
		FIRMWARE_VERSION="$2"
		shift 2
		;;
	*)
		echo "Unknown option: $1"
		show_usage
		exit 1
		;;
	esac
done

# Conflict check
[[ "$FIRST_TIME_FLASH" == true && "$WIPE_AND_FLASH" == true ]] && {
	echo "ERROR: Cannot use both --first and --wipe"
	exit 1
}

# Detect OS
detect_os() {
	case "$(uname -s)" in
	Linux*) echo "Linux" ;;
	Darwin*) echo "macOS" ;;
	*) echo "Unknown" ;;
	esac
}

# Install ampy if needed
install_ampy() {
	command -v ampy >/dev/null 2>&1 && return 0
	echo "Installing ampy..."

	local pip_cmd=""
	for cmd in pip3 pip "python3 -m pip"; do
		if command -v ${cmd%% *} >/dev/null 2>&1; then
			pip_cmd="$cmd"
			break
		fi
	done

	[[ -z "$pip_cmd" ]] && {
		echo "ERROR: pip not found. Install Python and pip first."
		exit 1
	}

	$pip_cmd install ${pip_cmd:0:4} == "pip3" && echo "--user" || echo ""} adafruit-ampy
}

# Find RPI-RP2 drive
find_rp2_drive() {
	local os=$(detect_os)
	local paths=()

	if [[ "$os" == "macOS" ]]; then
		paths=("/Volumes/RPI-RP2" "/Volumes")
	else
		paths=("/media/$USER/RPI-RP2" "/mnt/RPI-RP2" "/run/media/$USER/RPI-RP2" "/media" "/mnt" "/run/media/$USER")
	fi

	# Check direct paths first
	for path in "${paths[@]:0:3}"; do
		[[ -d "$path" && -w "$path" ]] && {
			echo "$path"
			return 0
		}
	done

	# Search in base directories
	for base in "${paths[@]:3}"; do
		[[ -d "$base" ]] || continue
		local found=$(find "$base" -name "RPI-RP2" -type d 2>/dev/null | head -1)
		if [[ -n "$found" && -w "$found" ]]; then
			[[ -f "$found/INDEX.HTM" || -f "$found/INFO_UF2.TXT" ]] && {
				echo "$found"
				return 0
			}
		fi
	done

	# Check mount output
	local mount_point=$(mount | grep -i "rpi-rp2" | awk '{print $3}' | head -1)
	[[ -n "$mount_point" && -d "$mount_point" && -w "$mount_point" ]] && {
		echo "$mount_point"
		return 0
	}

	return 1
}

# Find MicroPython device
find_micropython_device() {
	local os=$(detect_os)
	local patterns=()

	if [[ "$os" == "macOS" ]]; then
		patterns=("/dev/tty.usb*" "/dev/tty.usbmodem*")
	else
		patterns=("/dev/ttyACM*" "/dev/ttyUSB*")
	fi

	for pattern in "${patterns[@]}"; do
		for device in $pattern; do
			[[ -e "$device" && -r "$device" && -w "$device" ]] && {
				echo "$device"
				return 0
			}
		done
	done

	return 1
}

# Test MicroPython connection
test_micropython() {
	local device="$1"
	timeout 3 python3 -c "
import serial, time
try:
    ser = serial.Serial('$device', 115200, timeout=1)
    ser.write(b'\\r\\n')
    time.sleep(0.1)
    ser.write(b'print(\"test\")\\r\\n')
    time.sleep(0.1)
    response = ser.read(100)
    ser.close()
    exit(0 if b'test' in response or b'>>>' in response else 1)
except:
    exit(1)
" 2>/dev/null
}

# Wait for device
wait_for_device() {
	local mode="$1"
	local timeout=30
	local count=0

	echo "Waiting for device in $mode mode..."

	while [[ $count -lt $timeout ]]; do
		if [[ "$mode" == "bootloader" ]]; then
			local device=$(find_rp2_drive)
			[[ -n "$device" ]] && {
				echo "✓ Device found: $device"
				return 0
			}
		else
			local device=$(find_micropython_device)
			[[ -n "$device" ]] && {
				sleep 2 # Let device stabilize
				test_micropython "$device" && {
					echo "✓ MicroPython ready: $device"
					return 0
				}
			}
		fi

		sleep 1
		((count++))
		[[ $((count % 10)) -eq 0 ]] && echo "Still waiting... ($count/$timeout seconds)"
	done

	echo "✗ Timeout waiting for $mode device"
	return 1
}

# Check device status
check_device_status() {
	echo "=== DEVICE STATUS ==="

	# Check bootloader mode
	local rp2_drive=$(find_rp2_drive)
	if [[ -n "$rp2_drive" ]]; then
		echo "✓ RP2040 in BOOTLOADER mode: $rp2_drive"
		return 0
	fi

	# Check MicroPython mode
	local device=$(find_micropython_device)
	if [[ -n "$device" ]]; then
		echo "✓ Serial device found: $device"
		if command -v python3 >/dev/null 2>&1 && python3 -c "import serial" 2>/dev/null; then
			if test_micropython "$device"; then
				echo "✓ MicroPython responding"
				return 0
			else
				echo "✗ Device not responding to MicroPython"
				return 1
			fi
		else
			echo "? Cannot test MicroPython (python3/pyserial missing)"
			return 0
		fi
	fi

	echo "✗ No RP2040 device found"
	echo "Connect device: BOOTSEL for firmware, normal for files"
	return 1
}

# Flash UF2 file
flash_uf2() {
	local file="$1"
	local rp2_drive=$(find_rp2_drive)

	[[ -z "$rp2_drive" ]] && {
		echo "ERROR: Device not in bootloader mode"
		echo "Hold BOOTSEL while connecting"
		return 1
	}

	echo "Flashing $file..."
	if cp "$file" "$rp2_drive/"; then
		echo "✓ Flashed successfully"
		sleep 3
		return 0
	else
		echo "✗ Flash failed"
		return 1
	fi
}

# Upload Python file
upload_python() {
	local file="$1"
	local device=$(find_micropython_device)

	[[ -z "$device" ]] && {
		echo "ERROR: MicroPython device not found"
		return 1
	}

	echo "Uploading $file..."
	if ampy --port "$device" put "$file"; then
		echo "✓ Uploaded successfully"
		return 0
	else
		echo "✗ Upload failed"
		return 1
	fi
}

# Get firmware version
get_firmware_version() {
	if [[ -n "$FIRMWARE_VERSION" ]]; then
		echo "$FIRMWARE_VERSION"
	else
		find src/ -maxdepth 1 -type d -name "V*" | sed 's|src/||' | sort -V | tail -1
	fi
}

# Get files to process
get_files() {
	if [[ "$FIRST_TIME_FLASH" == true ]]; then
		echo "ULP/RPI_PICO-20240222-v1.22.2.uf2"
	elif [[ "$WIPE_AND_FLASH" == true ]]; then
		echo "ULP/flash_nuke.uf2"
	else
		local version=$(get_firmware_version)
		local verdir="src/$version"
		[[ -d "$verdir" ]] || {
			echo "ERROR: Version directory $verdir not found"
			exit 1
		}

		find "$verdir" -name "*.py" -o -name "*.bin"
	fi
}

# Handle wipe and flash
handle_wipe_flash() {
	echo "=== WIPE AND FLASH ==="

	# Step 1: Wipe
	echo "Step 1: Wiping device..."
	flash_uf2 "ULP/flash_nuke.uf2" || return 1

	# Step 2: Wait for reboot
	echo "Step 2: Waiting for reboot..."
	wait_for_device "bootloader" || return 1

	# Step 3: Flash MicroPython
	echo "Step 3: Installing MicroPython..."
	flash_uf2 "ULP/RPI_PICO-20240222-v1.22.2.uf2" || return 1

	# Step 4: Wait for MicroPython
	# echo "Step 4: Waiting for MicroPython..."
	# wait_for_device "micropython" || return 1

	echo "✓ Device wiped and flashed successfully"
}

# Main execution
main() {
	# Handle special modes
	[[ "$DRY_RUN" == true ]] && {
		check_device_status
		exit $?
	}
	[[ "$WIPE_AND_FLASH" == true ]] && {
		handle_wipe_flash
		exit $?
	}

	# Show mode
	if [[ "$FIRST_TIME_FLASH" == true ]]; then
		echo "MODE: First time flash"
	else
		echo "MODE: Basic upload"
	fi

	# Get and validate files
	files=($(get_files))
	available_files=()

	for file in "${files[@]}"; do
		[[ -f "$file" ]] && available_files+=("$file") || echo "WARNING: $file not found"
	done

	[[ ${#available_files[@]} -eq 0 ]] && {
		echo "ERROR: No files found"
		exit 1
	}

	# Install ampy if needed
	for file in "${available_files[@]}"; do
		[[ "$file" == *.py ]] && {
			install_ampy
			break
		}
	done

	# Process files
	echo "Processing ${#available_files[@]} files..."
	local success=0

	for file in "${available_files[@]}"; do
		case "$file" in
		*.uf2) flash_uf2 "$file" && ((success++)) ;;
		*.py | *.bin) upload_python "$file" && ((success++)) ;;
		*) echo "WARNING: Unknown file type: $file" ;;
		esac
	done

	# Summary
	echo "=== SUMMARY ==="
	echo "Processed: ${#available_files[@]} files"
	echo "Successful: $success files"

	if [[ $success -eq ${#available_files[@]} ]]; then
		echo "✓ All files processed successfully"
	else
		echo "✗ Some files failed"
		echo "Try: $0 --dry-run"
	fi
}

main
