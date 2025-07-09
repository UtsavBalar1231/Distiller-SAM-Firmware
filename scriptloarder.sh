#!/bin/bash

# Simple RP2040 Firmware Loader
# Supports basic RP2040 mass storage flashing and MicroPython file upload

show_usage() {
	echo "Usage: $0 [OPTIONS]"
	echo ""
	echo "Simple RP2040 firmware and file uploader:"
	echo ""
	echo "  Basic Upload - Upload files to RP2040:"
	echo "    ./scriptloarder.sh"
	echo ""
	echo "  First Time Flash - Flash MicroPython firmware:"
	echo "    ./scriptloarder.sh --first"
	echo ""
	echo "  Wipe and Flash - Complete device reset:"
	echo "    ./scriptloarder.sh --wipe"
	echo ""
	echo "Options:"
	echo "  -h, --help     Show this help message"
	echo "  -v, --verbose  Enable verbose output"
	echo "      --first    Flash MicroPython firmware only"
	echo "      --wipe     Wipe device and flash MicroPython"
	echo "      --dry-run  Check device status without making changes"
	echo "      --version  Specify firmware version (e.g. --version V0.2.2)"
	echo ""
	echo "Instructions:"
	echo "1. Hold BOOTSEL button while connecting RP2040 for firmware flashing"
	echo "2. Connect normally for MicroPython file upload"
	echo "3. Use --dry-run to verify device is ready before flashing"
	echo "4. Use --version to select firmware version from src/ directory"
}

# Parse arguments
VERBOSE=false
FIRST_TIME_FLASH=false
WIPE_AND_FLASH=false
DRY_RUN=false
FIRMWARE_VERSION=""

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

# Check for conflicting modes
if [[ "$FIRST_TIME_FLASH" == true && "$WIPE_AND_FLASH" == true ]]; then
	echo "ERROR: Cannot use both --first and --wipe modes"
	exit 1
fi

# Mode conflict check
# (dry-run check is at end of script after function definitions)

# Install ampy if needed (for MicroPython files)
install_ampy() {
	if ! command -v ampy >/dev/null 2>&1; then
		echo "Installing ampy for MicroPython file upload..."
		local os=$(detect_os)

		# Try different pip commands based on OS
		if [[ "$os" == "Linux" ]]; then
			# On Linux, try pip3 first, then pip, then python3 -m pip
			if command -v pip3 >/dev/null 2>&1; then
				pip3 install --user adafruit-ampy
			elif command -v pip >/dev/null 2>&1; then
				pip install --user adafruit-ampy
			elif command -v python3 >/dev/null 2>&1; then
				python3 -m pip install --user adafruit-ampy
			else
				echo "ERROR: pip not found. Please install Python and pip first."
				echo "On Ubuntu/Debian: sudo apt install python3-pip"
				echo "On Fedora/CentOS: sudo dnf install python3-pip"
				echo "On Arch: sudo pacman -S python-pip"
				exit 1
			fi
		else
			# macOS or other
			if command -v pip3 >/dev/null 2>&1; then
				pip3 install adafruit-ampy
			elif command -v pip >/dev/null 2>&1; then
				pip install adafruit-ampy
			else
				echo "ERROR: pip not found. Please install Python and pip first."
				exit 1
			fi
		fi
	fi
}

# Detect operating system
detect_os() {
	case "$(uname -s)" in
	Linux*)
		echo "Linux"
		;;
	Darwin*)
		echo "macOS"
		;;
	*)
		echo "Unknown"
		;;
	esac
}

# Find RPI-RP2 drive (bootloader mode)
find_rp2_drive() {
	local os=$(detect_os)

	# Define search paths based on OS
	local search_paths=()
	if [[ "$os" == "macOS" ]]; then
		search_paths=(
			"/Volumes/RPI-RP2"
			"/Volumes"
		)
	elif [[ "$os" == "Linux" ]]; then
		search_paths=(
			"/media/$USER/RPI-RP2"
			"/mnt/RPI-RP2"
			"/run/media/$USER/RPI-RP2"
			"/media"
			"/mnt"
			"/run/media/$USER"
			"/run/mount"
		)
	else
		# Generic fallback
		search_paths=(
			"/media/$USER/RPI-RP2"
			"/mnt/RPI-RP2"
			"/Volumes/RPI-RP2"
			"/media"
			"/mnt"
			"/Volumes"
		)
	fi

	# Check direct mount points first
	for mount_point in "${search_paths[@]:0:3}"; do
		if [[ -d "$mount_point" && -w "$mount_point" ]]; then
			echo "$mount_point"
			return 0
		fi
	done

	# Search all possible mount locations
	for base_path in "${search_paths[@]:3}"; do
		if [[ -d "$base_path" ]]; then
			# Look for RPI-RP2 directory
			local rp2_path=$(find "$base_path" -name "RPI-RP2" -type d 2>/dev/null | head -1)
			if [[ -n "$rp2_path" ]]; then
				# Verify it's actually the RP2040 bootloader by checking for characteristic files
				if [[ -f "$rp2_path/INDEX.HTM" || -f "$rp2_path/INFO_UF2.TXT" ]]; then
					if [[ -w "$rp2_path" ]]; then
						echo "$rp2_path"
						return 0
					else
						echo "Found RPI-RP2 at $rp2_path but no write permission" >&2
					fi
				fi
			fi
		fi
	done

	# Last resort: check mount command output
	local mount_point=$(mount | grep -i "rpi-rp2\|RPI-RP2" | awk '{print $3}' | head -1)
	if [[ -n "$mount_point" && -d "$mount_point" && -w "$mount_point" ]]; then
		echo "$mount_point"
		return 0
	fi

	echo ""
}

# Find MicroPython device
find_micropython_device() {
	local os=$(detect_os)

	# Define device patterns based on OS
	local device_patterns=()
	if [[ "$os" == "macOS" ]]; then
		device_patterns=("/dev/tty.usb*" "/dev/tty.usbmodem*" "/dev/tty.SLAB_USBtoUART*")
	elif [[ "$os" == "Linux" ]]; then
		device_patterns=("/dev/ttyACM*" "/dev/ttyUSB*")
	else
		# Generic fallback
		device_patterns=("/dev/ttyACM*" "/dev/ttyUSB*" "/dev/tty.usb*")
	fi

	# Try common serial devices
	for pattern in "${device_patterns[@]}"; do
		for device in $pattern; do
			if [[ -e "$device" ]]; then
				echo "$device"
				return 0
			fi
		done
	done
	echo ""
}

# Check if device is accessible and has proper permissions
check_device_access() {
	local device="$1"

	if [[ ! -e "$device" ]]; then
		echo "Device $device does not exist"
		return 1
	fi

	if [[ ! -r "$device" || ! -w "$device" ]]; then
		echo "No read/write permission for $device"
		echo "Try: sudo chmod 666 $device"
		# Check which group owns the device
		local device_group=$(stat -c %G "$device" 2>/dev/null)
		if [[ -n "$device_group" ]]; then
			echo "Or add user to $device_group group: sudo usermod -a -G $device_group $USER"
		else
			local os=$(detect_os)
			if [[ "$os" == "Linux" ]]; then
				echo "Or add user to serial group:"
				echo "  Ubuntu/Debian: sudo usermod -a -G dialout $USER"
				echo "  Arch Linux: sudo usermod -a -G uucp $USER"
				echo "  Fedora/CentOS: sudo usermod -a -G dialout $USER"
				echo "Then logout and login again for changes to take effect."
			elif [[ "$os" == "macOS" ]]; then
				echo "On macOS, you may need to install drivers for your USB-to-serial adapter."
			fi
		fi
		return 1
	fi

	return 0
}

# Test if MicroPython is actually running on the device
test_micropython_connection() {
	local device="$1"

	# Try to get MicroPython version (quick test)
	timeout 3 python3 -c "
import serial
import time
try:
    ser = serial.Serial('$device', 115200, timeout=1)
    ser.write(b'\r\n')
    time.sleep(0.1)
    ser.write(b'print(\"test\")\r\n')
    time.sleep(0.1)
    response = ser.read(100)
    ser.close()
    if b'test' in response or b'>>>' in response:
        exit(0)
    else:
        exit(1)
except Exception:
    exit(1)
" 2>/dev/null

	return $?
}

# Wait for device to appear in bootloader mode
wait_for_bootloader() {
	local timeout=${1:-30}
	local count=0

	echo "Waiting for device to appear in bootloader mode..."
	while [[ $count -lt $timeout ]]; do
		local rp2_drive=$(find_rp2_drive)
		if [[ -n "$rp2_drive" ]]; then
			echo "✓ Device found in bootloader mode at: $rp2_drive"
			return 0
		fi
		sleep 1
		((count++))
		if [[ $((count % 5)) -eq 0 ]]; then
			echo "Still waiting... ($count/$timeout seconds)"
		fi
	done

	echo "✗ Timeout waiting for bootloader mode"
	return 1
}

# Wait for device to appear as MicroPython serial device
wait_for_micropython() {
	local timeout=${1:-30}
	local count=0

	echo "Waiting for MicroPython device to appear..."
	while [[ $count -lt $timeout ]]; do
		local device=$(find_micropython_device)
		if [[ -n "$device" ]]; then
			# Wait a bit more for device to stabilize
			sleep 2
			if check_device_access "$device" && test_micropython_connection "$device"; then
				echo "✓ MicroPython device ready at: $device"
				return 0
			fi
		fi
		sleep 1
		((count++))
		if [[ $((count % 5)) -eq 0 ]]; then
			echo "Still waiting... ($count/$timeout seconds)"
		fi
	done

	echo "✗ Timeout waiting for MicroPython device"
	return 1
}

# Validate device requirements for current mode
validate_device_requirements() {
	if [[ "$FIRST_TIME_FLASH" == true || "$WIPE_AND_FLASH" == true ]]; then
		# These modes need bootloader mode
		local rp2_drive=$(find_rp2_drive)
		if [[ -z "$rp2_drive" ]]; then
			echo "ERROR: Device must be in bootloader mode for this operation"
			echo "Hold BOOTSEL button while connecting device"
			return 1
		fi
	else
		# Default mode needs MicroPython device
		local device=$(find_micropython_device)
		if [[ -z "$device" ]]; then
			echo "ERROR: MicroPython device not found for file upload"
			echo "Device must be running MicroPython firmware"
			echo "Try: $0 --first (to flash MicroPython firmware)"
			return 1
		fi

		if ! check_device_access "$device"; then
			echo "ERROR: Cannot access MicroPython device"
			return 1
		fi
	fi
	return 0
}

# Check device status for dry-run
check_device_status() {
	echo "=== DEVICE STATUS CHECK ==="

	# Check for bootloader mode
	local rp2_drive=$(find_rp2_drive)
	if [[ -n "$rp2_drive" ]]; then
		echo "✓ RP2040 found in BOOTLOADER mode at: $rp2_drive"
		echo "  Ready for .uf2 firmware flashing"
		if [[ -f "$rp2_drive/INDEX.HTM" ]]; then
			echo "  Bootloader files detected: INDEX.HTM"
		fi
		if [[ -f "$rp2_drive/INFO_UF2.TXT" ]]; then
			echo "  Bootloader files detected: INFO_UF2.TXT"
		fi
		return 0
	fi

	# Check for MicroPython mode
	local device=$(find_micropython_device)
	if [[ -n "$device" ]]; then
		echo "✓ Serial device found at: $device"

		if ! check_device_access "$device"; then
			echo "✗ Device access issues (see above)"
			return 1
		fi

		echo "  Checking if MicroPython is running..."

		# Check if python3 and pyserial are available for testing
		if command -v python3 >/dev/null 2>&1; then
			if python3 -c "import serial" 2>/dev/null; then
				if test_micropython_connection "$device"; then
					echo "✓ MicroPython is responding"
					echo "  Ready for .py file upload"
					return 0
				else
					echo "✗ Device not responding to MicroPython commands"
					echo "  Device may need MicroPython firmware flashed first"
					return 1
				fi
			else
				echo "? Cannot test MicroPython (pyserial not installed)"
				echo "  Install with: pip install pyserial"
				echo "  Device permissions look OK for manual testing"
				return 0
			fi
		else
			echo "? Cannot test MicroPython (python3 not found)"
			echo "  Device permissions look OK for manual testing"
			return 0
		fi
	fi

	echo "✗ No RP2040 device found"
	echo "  Make sure device is connected"
	echo "  For firmware flashing: Hold BOOTSEL while connecting"
	echo "  For file upload: Connect normally with MicroPython running"
	return 1
}

# Flash UF2 file
flash_uf2() {
	local file="$1"

	if [[ "$VERBOSE" == true ]]; then
		echo "DEBUG: Searching for RPI-RP2 drive..."
		echo "DEBUG: Available mounts:"
		mount | grep -E "(media|mnt|Volumes)" | head -10
		echo "DEBUG: Looking for RPI-RP2 directories:"
		find /media /mnt /run/media 2>/dev/null | grep -i rpi-rp2 | head -5 || echo "None found in standard locations"
	fi

	local rp2_drive=$(find_rp2_drive)

	if [[ -z "$rp2_drive" ]]; then
		echo "ERROR: RP2040 not found in bootloader mode"
		echo "Hold BOOTSEL button while connecting device"
		echo ""
		echo "DEBUG: Please check where your RPI-RP2 device is mounted:"
		echo "Run: mount | grep -i rpi"
		echo "Or: find /media /mnt /run/media -name '*RPI*' 2>/dev/null"
		return 1
	fi

	echo "Flashing $file to $rp2_drive..."
	if cp "$file" "$rp2_drive/"; then
		echo "SUCCESS: Flashed $file"
		echo "Device will reboot automatically"
		sleep 5 # Wait for reboot
		return 0
	else
		echo "ERROR: Failed to flash $file"
		return 1
	fi
}

# Upload Python file
upload_python() {
	local file="$1"
	local device=$(find_micropython_device)

	if [[ -z "$device" ]]; then
		echo "ERROR: MicroPython device not found"
		echo "Make sure device is running MicroPython firmware and connected normally (not in BOOTSEL mode)"
		return 1
	fi

	# Check device access and permissions
	if ! check_device_access "$device"; then
		echo "ERROR: Cannot access $device"
		return 1
	fi

	echo "Uploading $file via $device..."
	if [[ "$VERBOSE" == true ]]; then
		echo "Command: ampy --port $device put $file"
	fi

	if ampy --port "$device" put "$file"; then
		echo "SUCCESS: Uploaded $file"
		return 0
	else
		echo "ERROR: Failed to upload $file"
		echo "This usually means:"
		echo "1. Device is not running MicroPython firmware"
		echo "2. Device is in bootloader mode (disconnect and reconnect without BOOTSEL)"
		echo "3. Another program is using the serial port"
		echo ""
		echo "Try flashing MicroPython first with: $0 --first"
		return 1
	fi
}

# Helper: List available firmware versions in src/
list_firmware_versions() {
	find src/ -maxdepth 1 -mindepth 1 -type d | sed 's|src/||' | grep -E '^[Vv][0-9]+\.[0-9]+(\.[0-9]+)?$' | sort -V
}

# Helper: Get latest firmware version
get_latest_firmware_version() {
	list_firmware_versions | tail -n 1
}

# Determine files based on mode and version
get_files() {
	if [[ "$FIRST_TIME_FLASH" == true ]]; then
		echo "ULP/RPI_PICO-20240222-v1.22.2.uf2"
	elif [[ "$WIPE_AND_FLASH" == true ]]; then
		echo "ULP/flash_nuke.uf2"
	else
		if [[ -n "$FIRMWARE_VERSION" ]]; then
			verdir="src/$FIRMWARE_VERSION"
		else
			verdir="src/$(get_latest_firmware_version)"
		fi
		if [[ -d "$verdir" ]]; then
			for f in "$verdir"/eink_driver_sam.py "$verdir"/main.py "$verdir"/bin/*.bin; do
				[[ -f "$f" ]] && echo "$f"
			done
		else
			echo "WARNING: Firmware version directory $verdir not found"
		fi
	fi
}

# Handle wipe and flash sequence
handle_wipe_sequence() {
	echo "=== WIPE AND FLASH SEQUENCE ==="

	# Step 1: Validate device is in bootloader mode
	if ! validate_device_requirements; then
		return 1
	fi

	# Step 2: Flash nuke firmware
	echo ""
	echo "Step 1/3: Wiping device firmware..."
	if ! flash_uf2 "ULP/flash_nuke.uf2"; then
		echo "ERROR: Failed to wipe device"
		return 1
	fi

	# Step 3: Wait for device to reboot into bootloader mode
	echo ""
	echo "Step 2/3: Waiting for device to reboot..."
	if ! wait_for_bootloader 30; then
		echo "ERROR: Device did not reboot into bootloader mode"
		echo "Try disconnecting and reconnecting with BOOTSEL pressed"
		return 1
	fi

	# Step 4: Flash MicroPython firmware
	echo ""
	echo "Step 3/3: Installing MicroPython firmware..."
	if ! flash_uf2 "ULP/RPI_PICO-20240222-v1.22.2.uf2"; then
		echo "ERROR: Failed to flash MicroPython firmware"
		return 1
	fi

	# Step 5: Wait for MicroPython to be ready
	echo ""
	echo "Waiting for MicroPython to be ready..."
	if ! wait_for_micropython 30; then
		echo "ERROR: MicroPython device not ready"
		echo "You may need to run '$0 --first' to flash MicroPython again"
		return 1
	fi

	# Step 6: Upload firmware files
	echo ""
	echo "Uploading firmware files..."

	# Determine firmware version
	local verdir
	if [[ -n "$FIRMWARE_VERSION" ]]; then
		verdir="src/$FIRMWARE_VERSION"
	else
		verdir="src/$(get_latest_firmware_version)"
	fi

	if [[ ! -d "$verdir" ]]; then
		echo "ERROR: Firmware version directory $verdir not found"
		return 1
	fi

	# Install ampy for file upload
	install_ampy

	# Upload files
	local upload_success=0
	local upload_total=0

	for file in "$verdir"/eink_driver_sam.py "$verdir"/main.py "$verdir"/bin/*.bin; do
		if [[ -f "$file" ]]; then
			((upload_total++))
			echo ""
			if upload_python "$file"; then
				((upload_success++))
			fi
		fi
	done

	echo ""
	echo "=== WIPE AND FLASH COMPLETE ==="
	echo "Files uploaded: $upload_success/$upload_total"

	if [[ $upload_success -eq $upload_total ]]; then
		echo "SUCCESS: Device wiped and firmware installed successfully"
		return 0
	else
		echo "WARNING: Some files failed to upload"
		return 1
	fi
}

# Main execution
main() {
	# Show mode
	if [[ "$FIRST_TIME_FLASH" == true ]]; then
		echo "MODE: First time flash - Installing MicroPython firmware"
	elif [[ "$WIPE_AND_FLASH" == true ]]; then
		echo "MODE: Wipe and flash - Complete device reset"
		# Handle wipe sequence specially
		handle_wipe_sequence
		exit $?
	else
		echo "MODE: Basic upload - Uploading files"
	fi

	# Validate device requirements
	if ! validate_device_requirements; then
		exit 1
	fi

	# Firmware version selection
	if [[ -z "$FIRMWARE_VERSION" && "$FIRST_TIME_FLASH" != true ]]; then
		FIRMWARE_VERSION="$(get_latest_firmware_version)"
		echo "No firmware version specified. Using latest: $FIRMWARE_VERSION"
	elif [[ -n "$FIRMWARE_VERSION" && ! -d "src/$FIRMWARE_VERSION" ]]; then
		echo "ERROR: Specified firmware version src/$FIRMWARE_VERSION does not exist."
		echo "Available versions:"
		list_firmware_versions
		exit 1
	fi

	# Get files to process
	files=($(get_files))

	# Check which files exist
	available_files=()
	for file in "${files[@]}"; do
		if [[ -f "$file" ]]; then
			available_files+=("$file")
		else
			echo "WARNING: $file not found, skipping"
		fi
	done

	if [[ ${#available_files[@]} -eq 0 ]]; then
		echo "ERROR: No files found to process"
		exit 1
	fi

	# Install ampy if we have Python files
	for file in "${available_files[@]}"; do
		if [[ "$file" == *.py ]]; then
			install_ampy
			break
		fi
	done

	# Process files
	echo ""
	echo "Processing ${#available_files[@]} files..."
	success_count=0

	for file in "${available_files[@]}"; do
		echo ""
		case "$file" in
		*.uf2)
			if flash_uf2 "$file"; then
				((success_count++))
			fi
			;;
		*.py)
			if upload_python "$file"; then
				((success_count++))
			fi
			;;
		*.bin)
			if upload_python "$file"; then
				((success_count++))
			fi
			;;
		*)
			echo "WARNING: Unknown file type: $file"
			;;
		esac
	done

	# Summary
	echo ""
	echo "=== SUMMARY ==="
	echo "Processed: ${#available_files[@]} files"
	echo "Successful: $success_count files"
	echo "Failed: $((${#available_files[@]} - success_count)) files"

	if [[ $success_count -eq ${#available_files[@]} ]]; then
		echo "SUCCESS: All files processed successfully"
	else
		echo "WARNING: Some files failed to process"
		echo ""
		echo "Troubleshooting tips:"
		echo "- Run '$0 --dry-run' to check device status"
		echo "- For .py files: Make sure device is running MicroPython"
		echo "- For .uf2 files: Hold BOOTSEL while connecting device"
		local os=$(detect_os)
		if [[ "$os" == "Linux" ]]; then
			echo "- Check permissions:"
			echo "  Ubuntu/Debian: sudo usermod -a -G dialout $USER"
			echo "  Arch Linux: sudo usermod -a -G uucp $USER"
			echo "  Then logout and login again"
		elif [[ "$os" == "macOS" ]]; then
			echo "- Check USB drivers are installed for your device"
		fi
	fi
}

# Handle dry-run mode (after all functions are defined)
if [[ "$DRY_RUN" == true ]]; then
	echo "DRY RUN MODE - Checking device status without making changes"
	echo ""
	check_device_status
	exit $?
fi

# Run main function
main
