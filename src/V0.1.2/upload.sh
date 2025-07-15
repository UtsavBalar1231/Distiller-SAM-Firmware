#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Function to wait for RPI-RP2 device
wait_for_rp2() {
  echo "Waiting for RPI-RP2 device..."
  while true; do
    if [ -d "/Volumes/RPI-RP2" ]; then
      echo "RPI-RP2 device found!"
      return 0
    fi
    sleep 1
  done
}

# Function to wait for RPI-RP2 device to disappear
wait_for_rp2_disappear() {
  echo "Waiting for RPI-RP2 device to disappear..."
  while [ -d "/Volumes/RPI-RP2" ]; do
    sleep 1
  done
  echo "RPI-RP2 device disappeared"
}

# Install pv if it is not installed
install_dependencies() {
  if ! command_exists brew; then
    echo "Homebrew is not installed. Please install Homebrew first."
    exit 1
  fi

  if ! command_exists pv; then
    echo "Installing pv..."
    brew install pv
  fi
}

# Check and install dependencies
install_dependencies

# Check if --wipe option is provided
if [ "$1" == "--wipe" ]; then
  echo "Wipe mode enabled. Will flash firmware first."
  
  # Wait for RPI-RP2 device
  wait_for_rp2
  
  # Copy flash_nuke.uf2
  echo "Copying flash_nuke.uf2..."
  cp "$SCRIPT_DIR/ULP/flash_nuke.uf2" /Volumes/RPI-RP2/
  
  # Wait for device to disappear and reappear
  wait_for_rp2_disappear
  echo "Waiting for device to reappear..."
  sleep 5
  wait_for_rp2
  
  # Copy MicroPython firmware
  echo "Copying MicroPython firmware..."
  cp "$SCRIPT_DIR/ULP/RPI_PICO-20250415-v1.25.0.uf2" /Volumes/RPI-RP2/
  
  # Wait for device to disappear
  wait_for_rp2_disappear
  echo "Waiting for device to initialize..."
  sleep 3
elif [ "$1" == "--first" ]; then
  echo "First time flash mode enabled. Will flash MicroPython firmware only."
  
  # Wait for RPI-RP2 device
  wait_for_rp2
  
  # Copy MicroPython firmware
  echo "Copying MicroPython firmware..."
  cp "$SCRIPT_DIR/ULP/RPI_PICO-20250415-v1.25.0.uf2" /Volumes/RPI-RP2/
  
  # Wait for device to disappear
  wait_for_rp2_disappear
  echo "Waiting for device to initialize..."
  sleep 3
fi

# Define the files and commands
files=("bin/loading1.bin" "bin/loading2.bin" "eink_driver_sam.py" "pd_version/main.py")
port="/dev/tty.usb*"

# Total number of files
total_files=${#files[@]}

# Function to display loading bar
display_loading_bar() {
  progress=$(($1 * 100 / $total_files))
  bar=$(printf "%-${progress}s" "#" | tr ' ' '#')
  echo -ne "Progress: [${bar}] ${progress}%\r"
}

# Iterate over each file and upload with progress bar
for ((i = 0; i < total_files; i++)); do
  file=${files[$i]}
  echo "Uploading $file"
  ampy --port $port put "$SCRIPT_DIR/$file"
  display_loading_bar $((i + 1))
done

# Move to a new line after the progress bar
echo -e "\nAll files uploaded successfully."
