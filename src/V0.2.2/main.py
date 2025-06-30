#Author: PamirAI 
#Date: 2025-05-05
#Version: 0.1.0
#Description: This is the main program for the RP2040 SAM

import machine
import utime
from eink_driver_sam import einkDSP_SAM
import _thread
from machine import WDT
import math
import neopixel
import json

utime.sleep_ms(100)
# Reset PMIC, DO NO REMOVE THIS BLOCK
pmic_enable = machine.Pin(3, machine.Pin.IN, pull=None)
# END OF PMIC RESET BLOCK

PRODUCTION = True  #for production flash, set to true for usb debug
UART_DEBUG = False #for UART debug, set to true for UART debug

#Instruction Set
EncodeTable = {"BTN_UP": 0b00000001, "BTN_DOWN": 0b00000010, "BTN_SELECT": 0b00000100, "SHUT_DOWN": 0b00001000}
USB_SWITCH_TABLE = {"SAM_USB": [0,0], "SOM_USB": [1,0]} # S, OE_N
# usb_switch_oe_n = machine.Pin(19, machine.Pin.OUT, value = 0)
usb_switch_s = machine.Pin(23, machine.Pin.OUT, value = 0)

def switch_usb(usb_type):
    if usb_type in USB_SWITCH_TABLE:
        S, _ = USB_SWITCH_TABLE[usb_type]
        usb_switch_s.value(S)
        # usb_switch_oe_n.value(OE_N)
    else:
        print(f"Invalid USB type: {usb_type}")


wdt = WDT(timeout=2000)
# Set up GPIO pins
selectBTN = machine.Pin(16, machine.Pin.IN, machine.Pin.PULL_DOWN)
upBTN = machine.Pin(17, machine.Pin.IN, machine.Pin.PULL_DOWN)
downBTN = machine.Pin(18, machine.Pin.IN, machine.Pin.PULL_DOWN)
einkStatus = machine.Pin(9, machine.Pin.OUT)
einkMux = machine.Pin(22, machine.Pin.OUT)
sam_interrupt = machine.Pin(2, machine.Pin.OUT)
# Debounce time in milliseconds
debounce_time = 50

if PRODUCTION:
    switch_usb("SOM_USB") # Disable SAM USB
# Setup UART0 on GPIO0 (TX) and GPIO1 (RX)
uart0 = machine.UART(0, baudrate=115200, tx=machine.Pin(0), rx=machine.Pin(1))
einkMux.low()  # EINK OFF
einkStatus.low()  # SOM CONTROL E-INK

print("Starting...")

# Function to handle UART debug messages
def debug_print(message):
    if UART_DEBUG:
        uart0.write(message)
    print(message)

# Begin of neopixel
def init_neopixel(pin=20, num_leds=1, brightness=1.0):
    np = neopixel.NeoPixel(machine.Pin(pin), num_leds)
    np.brightness = min(max(brightness, 0.0), 1.0)  # 限制亮度范围
    return np

# Neopixel set color
def set_color(np, color, brightness=None, index=None):
    if brightness is not None:
        np.brightness = min(max(brightness, 0.0), 1.0)
    r = int(color[0] * np.brightness)
    g = int(color[1] * np.brightness)
    b = int(color[2] * np.brightness)
    if index is None:
        for i in range(len(np)):
            np[i] = (r, g, b)
    else:
        np[index] = (r, g, b)
    np.write()

# Add lock for shared variable
eink_lock = _thread.allocate_lock()
einkRunning = False
neopixel_lock = _thread.allocate_lock()  # Add lock for neopixel operations
uart_lock = _thread.allocate_lock()  # Add lock for UART handling
current_neopixel_thread = None  # Track current neopixel thread
neopixel_running = False  # Flag to control current neopixel sequence

def handle_neopixel_sequence(np, data):
    global neopixel_running
    
    if not isinstance(data, dict) or 'colors' not in data:
        debug_print("[RP2040 DEBUG] Invalid data format or missing 'colors' key\n")
        return
    
    neopixel_running = True
    colors = data.get('colors', {})
    debug_print(f"[RP2040 DEBUG] Processing {len(colors)} color sequences\n")
    
    # Sort the sequence numbers to process them in order
    sequence_numbers = sorted([int(k) for k in colors.keys()])
    
    for seq_num in sequence_numbers:
        if not neopixel_running:  # Check if we should terminate
            break
        try:
            color_data = colors[str(seq_num)]
            if len(color_data) >= 5:
                r, g, b, brightness, delay = color_data
                debug_print(f"[RP2040 DEBUG] Sequence {seq_num}: Setting LED to RGB({r},{g},{b}) with brightness {brightness}\n")
                with neopixel_lock:
                    # Always set the first LED (index 0)
                    set_color(np, [r, g, b], brightness, 0)
                debug_print(f"[RP2040 DEBUG] Color set: {r}, {g}, {b}, brightness: {brightness}, delay: {delay}\n")
                utime.sleep(delay)
        except (ValueError, IndexError) as e:
            error_msg = f"Error processing sequence {seq_num}: {e}"
            print(error_msg)
            debug_print(f"[RP2040 DEBUG] {error_msg}\n")
    
    neopixel_running = False


# Function to debounce button press
def debounce(pin):
    state = pin.value()
    utime.sleep_ms(debounce_time)
    if pin.value() != state:
        return False
    return True

def get_debounced_state(pin):
    return pin.value() and debounce(pin) 

def send_button_state():
    state_byte = 0
    state_byte |= get_debounced_state(selectBTN) * EncodeTable["BTN_SELECT"]
    state_byte |= get_debounced_state(upBTN)  * EncodeTable["BTN_UP"]
    state_byte |= get_debounced_state(downBTN) * EncodeTable["BTN_DOWN"]
    if not PRODUCTION:
        print(f"state_byte: {state_byte}")
    uart0.write(bytes([state_byte]))

# Interrupt handler for down button
def button_handler(pin):
    if debounce(pin):
        send_button_state()

def loading_terminator(pin):
    global einkRunning
    if einkRunning:
        einkRunning = False
        eink.de_init()


# Set up interrupt handlers
selectBTN.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=button_handler)
upBTN.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=button_handler)
downBTN.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=button_handler)
sam_interrupt.irq(trigger=machine.Pin.IRQ_RISING, handler=loading_terminator)

# Initialize neopixel with just 1 LED
np = init_neopixel(pin=20, num_leds=1, brightness=0.5)
debug_print(f"[RP2040 DEBUG] Initialized {len(np)} NeoPixel\n")
neopixel_running = True

einkStatus.high() # provide power to eink
einkMux.high() # SAM CONTROL E-INK

# Initialize e-ink display
eink = einkDSP_SAM()

debug_print("StartScreen\n")

# Shared flag to coordinate thread handoff
thread_handoff_complete = False

# Thread to handle both eink and UART tasks
def core1_task():
    global einkRunning, thread_handoff_complete, neopixel_running
    
    # First, run the eink task
    try:
        einkRunning = True
        if eink.init == False:
            eink.re_init()
        
        # Step 1: Initialize with fast refresh for first image
        eink.epd_init_fast()
            
        try:
            # Step 2: Display first image with fast refresh
            # eink.PIC_display(None, './loading1.bin')
            
            # Step 3: Set this image as base map for partial refresh (Arduino pattern)
            # This is equivalent to EPD_SetRAMValue_BaseMap in Arduino
            with open('./loading1.bin', 'rb') as f:
                base_image = f.read()
            eink.epd_set_basemap(base_image)
            
        except OSError:
            print("Loading files not found")
            einkRunning = False
        
        repeat = 0
        while True:
            with eink_lock:
                if not einkRunning or repeat >= 3:
                    break
            
            # Use partial refresh display (following Arduino EPD_Dis_PartAll pattern)
            try:
                with open('./loading2.bin', 'rb') as f:
                    image2_data = f.read()
                eink.epd_display_part_all(image2_data)
                utime.sleep_ms(50)  # Short delay between frames
                
                with open('./loading1.bin', 'rb') as f:
                    image1_data = f.read()
                eink.epd_display_part_all(image1_data)
                utime.sleep_ms(50)
            except OSError:
                print("Animation files not found")
                break
                
            wdt.feed()
            repeat += 1
        
        eink.de_init()
        with eink_lock:
            einkRunning = False
        einkMux.low()
        print("Eink Task Completed")
    except Exception as e:
        print(f"Exception in eink task: {e}")
        eink.de_init()
        with eink_lock:
            einkRunning = False
        einkMux.low()
    
    # Signal that eink is done and we can transition to UART
    thread_handoff_complete = True
    
    # Now run the UART task
    debug_print("[RP2040 DEBUG] Starting UART handling on core1\n")
    uart_buffer = ""
    
    # UART handling loop
    while True:
        try:
            if uart0.any():
                raw_data = uart0.read(1)
                if raw_data:
                    uart_buffer += raw_data.decode('utf-8')
                    if uart_buffer.endswith('\n'):
                        debug_print(f"[RP2040 DEBUG] Complete data received: {uart_buffer}\n")
                        try:
                            data = json.loads(uart_buffer.strip())
                            debug_print(f"[RP2040 DEBUG] Parsed JSON: {data}\n")
                            if isinstance(data, dict):
                                function_type = data.get('Function')
                                debug_print(f"[RP2040 DEBUG] Function type: {function_type}\n")
                                if function_type == 'NeoPixel':
                                    # Execute NeoPixel sequence directly in this thread
                                    neopixel_running = False  # Stop any ongoing sequence
                                    utime.sleep_ms(10)  # Brief pause for cleanup
                                    handle_neopixel_sequence(np, data)  # Direct execution, no new thread
                                    debug_print("[Task] Neopixel Completed\n")
                                else:
                                    debug_print("Invalid function type\n")
                        except Exception as e:
                            debug_print(f"[RP2040 DEBUG] JSON decode error: {str(e)}\n")
                            # Handle non-JSON data as before
                            try:
                                int_data = uart_buffer.strip()
                                debug_print(f"[RP2040 DEBUG] Non-JSON data: {int_data}\n")
                            except ValueError:
                                debug_print("Invalid data received\n")
                                print(f"Invalid data received: {uart_buffer}")
                        uart_buffer = ""
        except Exception as e:
            debug_print(f"[RP2040 DEBUG] Error in UART handling: {str(e)}\n")
            print(f"Error in UART handling: {e}")
            uart_buffer = ""
        
        wdt.feed()
        utime.sleep_ms(1)

# Start the combined thread on core1
_thread.start_new_thread(core1_task, ())
print("Started core1 task")

# Clean main loop
while True:
    wdt.feed()
    
    # Only proceed with normal operation after handoff is complete
    if thread_handoff_complete:
        if debounce(upBTN) and selectBTN.value() == 1:
            start_time = utime.ticks_ms()
            while utime.ticks_diff(utime.ticks_ms(), start_time) < 10000:
                if upBTN.value() == 0 or selectBTN.value() == 0:
                    break
                if utime.ticks_diff(utime.ticks_ms(), start_time) >= 2000:
                    uart0.write(f"{EncodeTable['SHUT_DOWN']}\n")
                wdt.feed()
                utime.sleep_ms(10)
            if utime.ticks_diff(utime.ticks_ms(), start_time) >= 10000:
                einkStatus.low()  
                einkMux.low() # SOM CONTROL E-INK
                uart0.write("xSAM_USB\n")
                if PRODUCTION:
                    switch_usb("SAM_USB")
                einkRunning = False
    
    utime.sleep_ms(1)






