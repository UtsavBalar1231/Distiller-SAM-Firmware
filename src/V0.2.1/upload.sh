#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
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

# Function to wait for RPI-RP2 device
wait_for_rp2() {
  echo "Waiting for RPI-RP2 device..."
  local os=$(detect_os)
  
  while true; do
    if [[ "$os" == "macOS" ]]; then
      if [ -d "/Volumes/RPI-RP2" ]; then
        echo "RPI-RP2 device found!"
        return 0
      fi
    elif [[ "$os" == "Linux" ]]; then
      for mount_point in "/media/$USER/RPI-RP2" "/mnt/RPI-RP2" "/run/media/$USER/RPI-RP2"; do
        if [ -d "$mount_point" ]; then
          echo "RPI-RP2 device found at $mount_point!"
          export RPI_RP2_PATH="$mount_point"
          return 0
        fi
      done
    fi
    sleep 1
  done
}

# Function to wait for RPI-RP2 device to disappear
wait_for_rp2_disappear() {
  echo "Waiting for RPI-RP2 device to disappear..."
  local os=$(detect_os)
  
  while true; do
    local found=false
    if [[ "$os" == "macOS" ]]; then
      if [ -d "/Volumes/RPI-RP2" ]; then
        found=true
      fi
    elif [[ "$os" == "Linux" ]]; then
      for mount_point in "/media/$USER/RPI-RP2" "/mnt/RPI-RP2" "/run/media/$USER/RPI-RP2"; do
        if [ -d "$mount_point" ]; then
          found=true
          break
        fi
      done
    fi
    
    if [[ "$found" == "false" ]]; then
      echo "RPI-RP2 device disappeared"
      return 0
    fi
    sleep 1
  done
}

# Get RPI-RP2 path based on OS
get_rp2_path() {
  local os=$(detect_os)
  
  if [[ "$os" == "macOS" ]]; then
    echo "/Volumes/RPI-RP2"
  elif [[ "$os" == "Linux" ]]; then
    if [[ -n "$RPI_RP2_PATH" ]]; then
      echo "$RPI_RP2_PATH"
    else
      for mount_point in "/media/$USER/RPI-RP2" "/mnt/RPI-RP2" "/run/media/$USER/RPI-RP2"; do
        if [ -d "$mount_point" ]; then
          echo "$mount_point"
          return 0
        fi
      done
    fi
  fi
}

# Install dependencies based on OS
install_dependencies() {
  local os=$(detect_os)
  
  if [[ "$os" == "macOS" ]]; then
    if ! command_exists brew; then
      echo "Homebrew is not installed. Please install Homebrew first."
      exit 1
    fi
    
    if ! command_exists pv; then
      echo "Installing pv..."
      brew install pv
    fi
  elif [[ "$os" == "Linux" ]]; then
    if ! command_exists pv; then
      echo "Installing pv..."
      if command_exists apt-get; then
        sudo apt-get update && sudo apt-get install -y pv
      elif command_exists dnf; then
        sudo dnf install -y pv
      elif command_exists pacman; then
        sudo pacman -S --noconfirm pv
      elif command_exists zypper; then
        sudo zypper install -y pv
      else
        echo "Unable to install pv automatically. Please install it manually."
        echo "Progress bar will be disabled."
      fi
    fi
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
  local rp2_path=$(get_rp2_path)
  cp "$SCRIPT_DIR/ULP/flash_nuke.uf2" "$rp2_path/"
  
  # Wait for device to disappear and reappear
  wait_for_rp2_disappear
  echo "Waiting for device to reappear..."
  sleep 5
  wait_for_rp2
  
  # Copy MicroPython firmware
  echo "Copying MicroPython firmware..."
  rp2_path=$(get_rp2_path)
  cp "$SCRIPT_DIR/ULP/RPI_PICO-20240222-v1.22.2.uf2" "$rp2_path/"
  
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
  local rp2_path=$(get_rp2_path)
  cp "$SCRIPT_DIR/ULP/RPI_PICO-20240222-v1.22.2.uf2" "$rp2_path/"
  
  # Wait for device to disappear
  wait_for_rp2_disappear
  echo "Waiting for device to initialize..."
  sleep 3
fi

# Define the files and commands
files=("bin/loading1.bin" "bin/loading2.bin" "eink_driver_sam.py" "main.py")

# Set port based on OS
local os=$(detect_os)
if [[ "$os" == "macOS" ]]; then
  port="/dev/tty.usb*"
elif [[ "$os" == "Linux" ]]; then
  # Try to find the actual device
  for device in /dev/ttyACM* /dev/ttyUSB*; do
    if [ -e "$device" ]; then
      port="$device"
      break
    fi
  done
  
  # Fallback to pattern if no device found
  if [[ -z "$port" ]]; then
    port="/dev/ttyACM*"
  fi
else
  port="/dev/ttyACM*"
fi

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
