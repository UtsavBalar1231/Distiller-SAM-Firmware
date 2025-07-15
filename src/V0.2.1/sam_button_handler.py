"""
SAM Button Input Handler for RP2040

This module handles button input events and sends them to the Linux host
using the SAM protocol. Includes hardware debouncing and state tracking.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import machine
import time
from micropython import const
from sam_protocol import (
    SAMProtocolHandler,
    BTN_UP_MASK,
    BTN_DOWN_MASK,
    BTN_SELECT_MASK,
    BTN_POWER_MASK,
)

# Debounce configuration
DEBOUNCE_TIME_MS = const(50)
LONG_PRESS_TIME_MS = const(2000)
SHUTDOWN_PRESS_TIME_MS = const(10000)


class SAMButtonHandler:
    """Handles button input events for SAM protocol."""

    def __init__(self, protocol_handler, debug_callback=None):
        self.protocol = protocol_handler
        self.debug_callback = debug_callback

        # Button pin configuration (from original main.py)
        self.select_btn = machine.Pin(16, machine.Pin.IN, machine.Pin.PULL_DOWN)
        self.up_btn = machine.Pin(17, machine.Pin.IN, machine.Pin.PULL_DOWN)
        self.down_btn = machine.Pin(18, machine.Pin.IN, machine.Pin.PULL_DOWN)

        # Button state tracking
        self.last_button_state = 0
        self.button_press_times = {}
        self.long_press_sent = {}
        self.last_debounce_time = {}

        # Initialize state tracking
        for btn_name in ["select", "up", "down"]:
            self.button_press_times[btn_name] = 0
            self.long_press_sent[btn_name] = False
            self.last_debounce_time[btn_name] = 0

        # Setup interrupts
        self._setup_interrupts()

        self._debug_print("Button handler initialized")

    def _debug_print(self, message):
        """Send debug message if callback is available."""
        if self.debug_callback:
            self.debug_callback(f"[Button Handler] {message}")

    def _setup_interrupts(self):
        """Setup button interrupt handlers."""
        self.select_btn.irq(
            trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
            handler=self._button_interrupt_handler,
        )
        self.up_btn.irq(
            trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
            handler=self._button_interrupt_handler,
        )
        self.down_btn.irq(
            trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING,
            handler=self._button_interrupt_handler,
        )

    def _button_interrupt_handler(self, pin):
        """Handle button interrupts with debouncing."""
        current_time = time.ticks_ms()

        # Determine which button triggered the interrupt
        btn_name = None
        if pin == self.select_btn:
            btn_name = "select"
        elif pin == self.up_btn:
            btn_name = "up"
        elif pin == self.down_btn:
            btn_name = "down"

        if btn_name is None:
            return

        # Debounce check
        if (
            time.ticks_diff(current_time, self.last_debounce_time[btn_name])
            < DEBOUNCE_TIME_MS
        ):
            return

        self.last_debounce_time[btn_name] = current_time

        # Process button state change after debounce delay
        machine.Timer(-1).init(
            period=DEBOUNCE_TIME_MS,
            mode=machine.Timer.ONE_SHOT,
            callback=lambda t: self._process_button_state_change(),
        )

    def _debounce_button(self, pin):
        """Debounce a button by checking state stability."""
        initial_state = pin.value()
        time.sleep_ms(DEBOUNCE_TIME_MS)
        return pin.value() == initial_state

    def _get_current_button_state(self):
        """Get current debounced button state."""
        state = 0

        if self.select_btn.value() and self._debounce_button(self.select_btn):
            state |= BTN_SELECT_MASK
        if self.up_btn.value() and self._debounce_button(self.up_btn):
            state |= BTN_UP_MASK
        if self.down_btn.value() and self._debounce_button(self.down_btn):
            state |= BTN_DOWN_MASK

        return state

    def _process_button_state_change(self):
        """Process button state changes and send events."""
        current_state = self._get_current_button_state()
        current_time = time.ticks_ms()

        # Check for state changes
        if current_state != self.last_button_state:
            self._debug_print(
                f"Button state change: {self.last_button_state:02X} -> {current_state:02X}"
            )

            # Send button event
            success = self.protocol.send_button_event(current_state)
            if success:
                self._debug_print(f"Sent button event: {current_state:02X}")
            else:
                self._debug_print(f"Failed to send button event: {current_state:02X}")

            # Track button press times for long press detection
            self._update_press_tracking(current_state, current_time)

            self.last_button_state = current_state

    def _update_press_tracking(self, current_state, current_time):
        """Update button press time tracking for long press detection."""
        # Check for button presses (transitions from 0 to 1)
        state_changes = current_state ^ self.last_button_state

        buttons = [
            ("select", BTN_SELECT_MASK),
            ("up", BTN_UP_MASK),
            ("down", BTN_DOWN_MASK),
        ]

        for btn_name, btn_mask in buttons:
            if state_changes & btn_mask:  # State changed for this button
                if current_state & btn_mask:  # Button pressed
                    self.button_press_times[btn_name] = current_time
                    self.long_press_sent[btn_name] = False
                    self._debug_print(f"{btn_name} button pressed")
                else:  # Button released
                    press_duration = time.ticks_diff(
                        current_time, self.button_press_times[btn_name]
                    )
                    self._debug_print(
                        f"{btn_name} button released after {press_duration}ms"
                    )
                    self.button_press_times[btn_name] = 0

    def check_long_press(self):
        """Check for long press conditions and handle special actions."""
        current_time = time.ticks_ms()

        buttons = [
            ("select", BTN_SELECT_MASK),
            ("up", BTN_UP_MASK),
            ("down", BTN_DOWN_MASK),
        ]

        for btn_name, btn_mask in buttons:
            if (
                self.button_press_times[btn_name] > 0
                and not self.long_press_sent[btn_name]
            ):

                press_duration = time.ticks_diff(
                    current_time, self.button_press_times[btn_name]
                )

                if press_duration >= LONG_PRESS_TIME_MS:
                    self._debug_print(
                        f"{btn_name} long press detected ({press_duration}ms)"
                    )
                    self.long_press_sent[btn_name] = True

                    # Send long press event (using power mask to indicate long press)
                    long_press_state = self.last_button_state | BTN_POWER_MASK
                    self.protocol.send_button_event(long_press_state)

    def check_shutdown_sequence(self):
        """Check for shutdown button sequence (UP + SELECT for 10 seconds)."""
        current_time = time.ticks_ms()

        # Check if both UP and SELECT are pressed
        up_pressed = self.last_button_state & BTN_UP_MASK
        select_pressed = self.last_button_state & BTN_SELECT_MASK

        if up_pressed and select_pressed:
            # Both buttons pressed, check duration
            up_press_time = self.button_press_times.get("up", 0)
            select_press_time = self.button_press_times.get("select", 0)

            if up_press_time > 0 and select_press_time > 0:
                # Use the more recent press time as the start
                start_time = max(up_press_time, select_press_time)
                duration = time.ticks_diff(current_time, start_time)

                if duration >= SHUTDOWN_PRESS_TIME_MS:
                    self._debug_print(f"Shutdown sequence detected ({duration}ms)")
                    # Send shutdown event
                    shutdown_state = BTN_UP_MASK | BTN_SELECT_MASK | BTN_POWER_MASK
                    self.protocol.send_button_event(shutdown_state)
                    return True

        return False

    def get_button_state(self):
        """Get current button state for external polling."""
        return self.last_button_state

    def manual_button_check(self):
        """Manually check button state (for polling mode)."""
        current_state = self._get_current_button_state()
        current_time = time.ticks_ms()

        if current_state != self.last_button_state:
            self._process_button_state_change()

        # Check for long press conditions
        self.check_long_press()

        return current_state
