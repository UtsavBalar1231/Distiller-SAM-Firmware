"""
SAM Protocol Integrated Main Program for RP2040

This is the main program that integrates the SAM protocol with the existing
CM5 functionality including e-ink display, button handling, LED control,
and power management.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import _thread
import gc
import machine
import utime
from machine import WDT
import neopixel

# Import SAM protocol components
from sam_protocol import SAMProtocolHandler
from sam_button_handler import SAMButtonHandler
from sam_led_handler import SAMLEDHandler
from sam_power_handler import SAMPowerHandler
from sam_display_handler import SAMDisplayHandler
from sam_debug_handler import SAMDebugHandler
from sam_system_handler import SAMSystemHandler

# Import existing drivers
from eink_driver_sam import einkDSP_SAM

# Configuration
PRODUCTION = False
UART_DEBUG = False  # Enable UART debugging
LUT_MODE = True  # Use LUT mode for e-ink display
SAM_PROTOCOL_ENABLED = True  # Enable SAM protocol

# Hardware configuration
UART_BAUD = 115200
NEOPIXEL_PIN = 20
NEOPIXEL_COUNT = 1

# PMIC reset (DO NOT REMOVE)
pmic_enable = machine.Pin(3, machine.Pin.IN, pull=None)

# USB switch configuration
USB_SWITCH_TABLE = {"SAM_USB": [0, 0], "SOM_USB": [1, 0]}  # S, OE_N
usb_switch_s = machine.Pin(23, machine.Pin.OUT, value=0)

# Hardware pins
eink_status = machine.Pin(9, machine.Pin.OUT)
eink_mux = machine.Pin(22, machine.Pin.OUT)
sam_interrupt = machine.Pin(2, machine.Pin.OUT)

# Global variables
sam_protocol = None
sam_handlers = {}
eink_driver = None
system_ready = False
shutdown_requested = False


def switch_usb(usb_type):
    """Switch USB connection between SAM and SOM."""
    if usb_type in USB_SWITCH_TABLE:
        S, _ = USB_SWITCH_TABLE[usb_type]
        usb_switch_s.value(S)
        debug_print(f"USB switched to {usb_type}")
    else:
        debug_print(f"Invalid USB type: {usb_type}")


def debug_print(message):
    """Print debug messages based on configuration."""
    if UART_DEBUG and sam_protocol:
        # Send as debug text via SAM protocol
        if "debug" in sam_handlers:
            sam_handlers["debug"].send_debug_text(message)

    if not PRODUCTION:
        print(f"[MAIN] {message}")


def init_hardware():
    """Initialize hardware components."""
    global eink_driver

    debug_print("Initializing hardware...")

    # Configure USB switch
    if PRODUCTION:
        switch_usb("SOM_USB")  # Default to SOM USB

    # Initialize e-ink display hardware
    eink_mux.low()  # Initially SOM controls e-ink
    eink_status.low()  # Initially powered off

    # Initialize e-ink driver
    eink_driver = einkDSP_SAM()

    debug_print("Hardware initialization complete")


def init_sam_protocol():
    """Initialize SAM protocol and handlers."""
    global sam_protocol, sam_handlers

    if not SAM_PROTOCOL_ENABLED:
        debug_print("SAM protocol disabled")
        return

    debug_print("Initializing SAM protocol...")

    # Initialize UART
    uart0 = machine.UART(0, baudrate=UART_BAUD, tx=machine.Pin(0), rx=machine.Pin(1))

    # Initialize protocol handler
    sam_protocol = SAMProtocolHandler(uart0, debug_print)

    # Initialize debug handler first (needed by others)
    sam_handlers["debug"] = SAMDebugHandler(sam_protocol, debug_level=2)

    # Initialize other handlers
    sam_handlers["button"] = SAMButtonHandler(
        sam_protocol, sam_handlers["debug"].send_debug_text
    )
    sam_handlers["led"] = SAMLEDHandler(
        sam_protocol,
        NEOPIXEL_PIN,
        NEOPIXEL_COUNT,
        sam_handlers["debug"].send_debug_text,
    )
    sam_handlers["power"] = SAMPowerHandler(
        sam_protocol, sam_handlers["debug"].send_debug_text
    )
    sam_handlers["display"] = SAMDisplayHandler(
        sam_protocol, sam_handlers["debug"].send_debug_text
    )
    sam_handlers["system"] = SAMSystemHandler(
        sam_protocol, sam_handlers["debug"], sam_handlers["debug"].send_debug_text
    )

    debug_print("SAM protocol initialization complete")

    # Log startup
    sam_handlers["debug"].log_startup_sequence()


def eink_display_task():
    """E-ink display task - runs the startup animation."""
    global eink_driver, system_ready

    try:
        debug_print("Starting e-ink display task...")

        # Power on display
        eink_status.high()  # Provide power to e-ink
        eink_mux.high()  # SAM controls e-ink

        # Initialize display
        if not eink_driver.init:
            eink_driver.re_init()

        # Choose initialization mode
        if LUT_MODE:
            eink_driver.epd_init_lut()
        else:
            eink_driver.epd_init_fast()

        # Display startup animation
        try:
            eink_driver.PIC_display(None, "./loading1.bin")
        except OSError:
            debug_print("Loading files not found")
            if "debug" in sam_handlers:
                sam_handlers["debug"].log_error(0x06, 0x01)  # Hardware init failed
            return

        if LUT_MODE:
            utime.sleep_ms(1300)  # Allow time for first refresh

        # Animation loop
        repeat = 0
        while repeat < 3 and not shutdown_requested:
            if "debug" in sam_handlers:
                sam_handlers["debug"].log_display_event(
                    0x08, repeat
                )  # Refresh cycle started

            eink_driver.epd_init_part()
            eink_driver.PIC_display("./loading1.bin", "./loading2.bin")
            eink_driver.epd_init_part()
            eink_driver.PIC_display("./loading2.bin", "./loading1.bin")

            repeat += 1
            utime.sleep_ms(100)

        # Cleanup
        eink_driver.de_init()
        eink_mux.low()  # Return control to SOM

        debug_print("E-ink display task completed")

        if "debug" in sam_handlers:
            sam_handlers["debug"].log_display_event(
                0x09, 0x00
            )  # Refresh cycle complete

    except Exception as e:
        debug_print(f"E-ink display task error: {e}")
        if "debug" in sam_handlers:
            sam_handlers["debug"].log_exception(e)

        # Cleanup on error
        try:
            eink_driver.de_init()
            eink_mux.low()
        except:
            pass


def protocol_processing_task():
    """SAM protocol processing task."""
    global sam_protocol, sam_handlers, system_ready

    debug_print("Starting SAM protocol processing task...")

    # Wait for system to be ready
    while not system_ready:
        utime.sleep_ms(10)

    # Main protocol processing loop
    while not shutdown_requested:
        try:
            # Process incoming packets
            if sam_protocol:
                sam_protocol.process_received_data()

            # Periodic updates for handlers
            if "power" in sam_handlers:
                sam_handlers["power"].periodic_update()

            if "system" in sam_handlers:
                sam_handlers["system"].periodic_update()

            # Button long press check
            if "button" in sam_handlers:
                sam_handlers["button"].check_long_press()

                # Check for shutdown sequence
                if sam_handlers["button"].check_shutdown_sequence():
                    debug_print("Shutdown sequence detected")
                    handle_shutdown_sequence()
                    break

            # Brief sleep to prevent busy waiting
            utime.sleep_ms(1)

        except Exception as e:
            debug_print(f"Protocol processing error: {e}")
            if "debug" in sam_handlers:
                sam_handlers["debug"].log_exception(e)
            utime.sleep_ms(10)  # Longer sleep on error

    debug_print("SAM protocol processing task completed")


def handle_shutdown_sequence():
    """Handle the shutdown sequence (UP + SELECT for 10 seconds)."""
    global shutdown_requested

    debug_print("Handling shutdown sequence...")

    shutdown_requested = True

    # Log shutdown
    if "debug" in sam_handlers:
        sam_handlers["debug"].log_shutdown_sequence()

    # Switch to SAM USB for debugging
    if PRODUCTION:
        switch_usb("SAM_USB")

    # Turn off e-ink
    eink_status.low()
    eink_mux.low()

    # Turn off LED
    if "led" in sam_handlers:
        sam_handlers["led"].turn_off()

    # Send shutdown notification
    if "power" in sam_handlers:
        sam_handlers["power"].enter_sleep_mode()

    debug_print("Shutdown sequence completed")


def handle_interrupt(pin):
    """Handle SAM interrupt pin."""
    if pin == sam_interrupt:
        debug_print("SAM interrupt received")
        if "debug" in sam_handlers:
            sam_handlers["debug"].log_system_event(0x05, 0x00)  # External interrupt


def main():
    """Main program entry point."""
    global system_ready, shutdown_requested

    print("Starting SAM Protocol RP2040 Firmware v1.0.0...")

    switch_usb("SOM_USB")  # Default to SOM USB

    # Initialize watchdog
    wdt = WDT(timeout=2000)

    try:
        # Initialize hardware
        init_hardware()

        # Initialize SAM protocol
        init_sam_protocol()

        # Setup interrupt handler
        sam_interrupt.irq(trigger=machine.Pin.IRQ_RISING, handler=handle_interrupt)

        # Start e-ink display task in separate thread
        _thread.start_new_thread(eink_display_task, ())

        # Give display task time to start
        utime.sleep_ms(500)

        # Start protocol processing task
        protocol_task_id = _thread.start_new_thread(protocol_processing_task, ())

        # Mark system as ready
        system_ready = True

        # Main watchdog loop
        while not shutdown_requested:
            wdt.feed()

            # Monitor memory usage
            if "debug" in sam_handlers:
                free_mem = gc.mem_free()
                if free_mem < 10000:  # Less than 10KB
                    sam_handlers["debug"].log_memory_usage(free_mem)

            # Garbage collection
            if gc.mem_free() < 5000:
                gc.collect()
                if "debug" in sam_handlers:
                    sam_handlers["debug"].log_performance_event(
                        0x07, 0x00
                    )  # Resource cleanup

            utime.sleep_ms(100)

        # Cleanup
        debug_print("Shutting down...")

        # Cleanup handlers
        for handler_name, handler in sam_handlers.items():
            try:
                handler.cleanup()
            except:
                pass

        debug_print("Shutdown complete")

    except Exception as e:
        print(f"Fatal error: {e}")
        if "debug" in sam_handlers:
            sam_handlers["debug"].log_exception(e)

        # Emergency cleanup
        try:
            eink_status.low()
            eink_mux.low()
        except:
            pass

        # Reset on fatal error
        utime.sleep_ms(1000)
        machine.reset()


# Legacy compatibility functions for existing code
def send_button_state():
    """Legacy function for button state - now handled by SAM protocol."""
    if "button" in sam_handlers:
        sam_handlers["button"].manual_button_check()


def handle_neopixel_sequence(np, data):
    """Legacy function for neopixel - now handled by SAM protocol."""
    # This is now handled by the SAM LED handler
    pass


def debounce(pin):
    """Legacy debounce function."""
    state = pin.value()
    utime.sleep_ms(50)
    return pin.value() == state


# Entry point
if __name__ == "__main__":
    main()
