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
from pamir_uart_protocols import PamirUartProtocols
from neopixel_controller import NeoPixelController

pmic_enable = machine.Pin(3, machine.Pin.IN, pull=None)

PRODUCTION = True  #for production flash, set to true for usb debug
UART_DEBUG = False #for UART debug, set to true for UART debug

# Initialize protocol handler
protocol = PamirUartProtocols()

#Legacy Instruction Set (kept for shutdown functionality)
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

# Legacy neopixel functions (kept for backward compatibility)
def init_neopixel(pin=20, num_leds=1, brightness=1.0):
    """Legacy function - use NeoPixelController instead"""
    np = neopixel.NeoPixel(machine.Pin(pin), num_leds)
    np.brightness = min(max(brightness, 0.0), 1.0)
    return np

def set_color(np, color, brightness=None, index=None):
    """Legacy function - use NeoPixelController instead"""
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
uart_lock = _thread.allocate_lock()  # Add lock for UART handling

# Inter-core communication queue for LED commands
led_command_queue = []
led_queue_lock = _thread.allocate_lock()

# LED completion callback function
def led_completion_callback(led_id, sequence_length):
    """Callback function called when LED animations complete"""
    global protocol, uart0, uart_lock, PRODUCTION
    
    try:
        with uart_lock:
            if sequence_length > 0:
                # Send completion acknowledgment
                packet = protocol.create_led_completion_packet(led_id, sequence_length)
                uart0.write(packet)
                if not PRODUCTION:
                    print(f"LED completion ACK sent: LED{led_id}, {sequence_length} commands")
            elif sequence_length < 0:
                # Send error report (sequence_length is negative error code)
                error_code = abs(sequence_length)
                packet = protocol.create_led_error_packet(led_id, error_code)
                uart0.write(packet)
                if not PRODUCTION:
                    print(f"LED error ACK sent: LED{led_id}, error {error_code}")
    except Exception as e:
        print(f"LED acknowledgment failed: {e}")

# Initialize controllers
np_controller = NeoPixelController(pin=20, num_leds=1, default_brightness=0.5, 
                                   completion_callback=led_completion_callback)

def add_led_command_to_queue(command):
    """Thread-safe function to add LED command to inter-core queue"""
    global led_command_queue
    with led_queue_lock:
        led_command_queue.append(command)

def get_led_commands_from_queue():
    """Thread-safe function to get all LED commands from queue"""
    global led_command_queue
    with led_queue_lock:
        commands = led_command_queue.copy()
        led_command_queue.clear()
        return commands

def process_uart_packet(packet_bytes):
    """Process received UART packet and queue appropriate commands"""
    packet_type = protocol.get_packet_type(packet_bytes)
    
    if packet_type == protocol.TYPE_LED:
        # Parse LED packet
        valid, led_data = protocol.parse_led_packet(packet_bytes)
        if valid:
            # Add to LED command queue for core 0 to process
            add_led_command_to_queue(led_data)
            if not PRODUCTION:
                print(f"LED command queued: {led_data}")
        else:
            # Try parsing as LED acknowledgment/status request
            valid_ack, ack_data = protocol.parse_led_acknowledgment(packet_bytes)
            if valid_ack and ack_data['type'] == 'status':
                # Handle LED status request
                add_led_command_to_queue({
                    'type': 'status_request',
                    'led_id': ack_data['led_id'],
                    'status_code': ack_data['status_code']
                })
                if not PRODUCTION:
                    print(f"LED status request: {ack_data}")
    elif packet_type == protocol.TYPE_BUTTON:
        # Handle button packets if needed (currently only send, not receive)
        pass
    # Add other packet types as needed

def handle_neopixel_sequence(np, data):
    """Legacy function - now uses NeoPixelController for better performance"""
    global np_controller
    
    if not isinstance(data, dict) or 'colors' not in data:
        debug_print("[RP2040 DEBUG] Invalid data format or missing 'colors' key\n")
        return
    
    debug_print(f"[RP2040 DEBUG] Processing legacy neopixel sequence\n")
    
    # Use the new controller to handle legacy sequences
    np_controller.handle_legacy_sequence(data)

def test_led_protocol():
    """Test function to verify LED protocol implementation"""
    global protocol, np_controller
    
    print("Testing LED protocol implementation...")
    
    # Test 1: Create LED command packet
    test_packet = protocol.create_led_packet(
        led_id=0, execute=False, r4=15, g4=0, b4=0, time_value=3
    )
    print(f"Test packet: {[hex(b) for b in test_packet]}")
    
    # Test 2: Parse the packet
    valid, led_data = protocol.parse_led_packet(test_packet)
    if valid:
        print(f"Parsed LED data: {led_data}")
    
    # Test 3: Create completion acknowledgment
    ack_packet = protocol.create_led_completion_packet(0, 5)
    print(f"ACK packet: {[hex(b) for b in ack_packet]}")
    
    # Test 4: Parse acknowledgment
    valid_ack, ack_data = protocol.parse_led_acknowledgment(ack_packet)
    if valid_ack:
        print(f"Parsed ACK data: {ack_data}")
    
    print("LED protocol test completed!")


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
    # Get current button states with debouncing
    up_pressed = get_debounced_state(upBTN)
    down_pressed = get_debounced_state(downBTN)
    select_pressed = get_debounced_state(selectBTN)
    power_pressed = False  # Power button logic handled separately
    
    # Create protocol packet according to Pamir UART specification
    packet = protocol.create_button_packet(
        up_pressed=up_pressed,
        down_pressed=down_pressed, 
        select_pressed=select_pressed,
        power_pressed=power_pressed
    )
    
    if not PRODUCTION:
        print(f"Button packet: {[hex(b) for b in packet]}")
        print(f"Button states - UP: {up_pressed}, DOWN: {down_pressed}, SELECT: {select_pressed}")
    
    uart0.write(packet)

# Interrupt handler for down button
def button_handler(pin):
    if debounce(pin):
        send_button_state()

def loading_terminator(pin):
    #Reserved for future use
    pass


# Set up interrupt handlers
selectBTN.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=button_handler)
upBTN.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=button_handler)
downBTN.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=button_handler)
sam_interrupt.irq(trigger=machine.Pin.IRQ_RISING, handler=loading_terminator)

# Legacy neopixel for backward compatibility (if needed)
np = init_neopixel(pin=20, num_leds=1, brightness=0.5)
debug_print(f"[RP2040 DEBUG] Initialized NeoPixel Controller and legacy support\n")

einkStatus.high() # provide power to eink
einkMux.high() # SAM CONTROL E-INK

# Initialize e-ink display
eink = einkDSP_SAM()

debug_print("StartScreen\n")

# Shared flag to coordinate thread handoff
thread_handoff_complete = False

# Thread to handle both eink and UART tasks
def core1_task():
    global einkRunning, thread_handoff_complete
    
    # First, run the eink task
    try:
        einkRunning = True
        if eink.init == False:
            eink.re_init()
        
        eink.epd_init_fast()
            
        try:
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
    
    # Start UART packet reception loop (Core 1)
    print("Starting UART reception loop on Core 1")
    uart_buffer = bytearray()
    
    while True:
        try:
            wdt.feed()
            
            # Check for incoming UART data
            if uart0.any():
                with uart_lock:
                    data = uart0.read()
                    if data:
                        uart_buffer.extend(data)
                        
                        # Process complete 4-byte packets
                        while len(uart_buffer) >= 4:
                            packet = bytes(uart_buffer[:4])
                            uart_buffer = uart_buffer[4:]
                            
                            # Validate and process packet
                            if protocol.validate_packet(packet)[0]:
                                process_uart_packet(packet)
                            else:
                                if not PRODUCTION:
                                    print(f"Invalid packet: {[hex(b) for b in packet]}")
            
            utime.sleep_ms(1)  # Small delay to prevent overwhelming the CPU
            
        except Exception as e:
            print(f"UART reception error: {e}")
            utime.sleep_ms(10)

# Start the combined thread on core1
_thread.start_new_thread(core1_task, ())
print("Started core1 task")

# Clean main loop
while True:
    wdt.feed()
    
    # Only proceed with normal operation after handoff is complete
    if thread_handoff_complete:
        # Process LED commands from queue (Core 0)
        led_commands = get_led_commands_from_queue()
        for command in led_commands:
            try:
                if command.get('type') == 'status_request':
                    # Handle LED status request
                    led_id = command['led_id']
                    status_code = command.get('status_code', 0)
                    
                    # Get controller status
                    controller_status = np_controller.get_status()
                    
                    # Send status response based on status_code
                    if status_code == 0:  # General status
                        status_value = 1 if controller_status['animation_running'] else 0
                    elif status_code == 1:  # Queue length
                        status_value = controller_status['queue_length']
                    elif status_code == 2:  # Brightness
                        status_value = int(controller_status['brightness'] * 255)
                    else:  # Unknown status code
                        status_value = 0
                    
                    # Send status packet
                    with uart_lock:
                        packet = protocol.create_led_status_packet(led_id, status_code, status_value)
                        uart0.write(packet)
                        if not PRODUCTION:
                            print(f"LED status response: LED{led_id}, code{status_code}, value{status_value}")
                
                elif command.get('execute'):
                    # Execute all queued LED commands
                    np_controller.execute_queue()
                else:
                    # Add command to neopixel controller queue
                    led_id = command['led_id']
                    if led_id == 15:  # Convert protocol LED_ALL to controller format
                        led_id = 255
                    
                    # Determine animation mode based on time_value and other factors
                    time_value = command['time_value']
                    if time_value == 0:
                        mode = np_controller.MODE_STATIC
                    elif time_value <= 5:
                        mode = np_controller.MODE_BLINK
                    elif time_value <= 10:
                        mode = np_controller.MODE_FADE
                    else:
                        mode = np_controller.MODE_RAINBOW
                    
                    np_controller.add_to_queue(
                        led_id=led_id,
                        mode=mode,
                        color_data=command['color'],
                        time_value=time_value
                    )
                    
                    if not PRODUCTION:
                        print(f"LED command added to controller queue: LED{led_id}, color{command['color']}, mode{mode}")
                        
            except Exception as e:
                print(f"Error processing LED command: {e}")
                # Send error report
                try:
                    error_led_id = command.get('led_id', 0)
                    if error_led_id == 15:  # Convert protocol LED_ALL back
                        error_led_id = 255
                    np_controller.send_error_report(error_led_id, 1, str(e))
                except:
                    pass  # Don't let error reporting crash the system
        
        # Existing button handling code
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






