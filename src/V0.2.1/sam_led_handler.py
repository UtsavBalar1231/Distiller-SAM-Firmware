"""
SAM LED Control Handler for RP2040

This module handles LED control commands from the Linux host and manages
NeoPixel LED animations according to the SAM protocol specification.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import time
import _thread
import machine
import neopixel
from micropython import const
from sam_protocol import (
    TYPE_LED,
    LED_MODE_STATIC,
    LED_MODE_BLINK,
    LED_MODE_FADE,
    LED_MODE_RAINBOW,
    LED_MODE_MASK,
    LED_CMD_IMMEDIATE,
    LED_CMD_SEQUENCE,
)

# LED animation constants
ANIMATION_STEPS = const(32)
BLINK_INTERVAL_MS = const(500)
FADE_STEP_MS = const(50)
RAINBOW_STEP_MS = const(100)


class SAMLEDHandler:
    """Handles LED control commands for SAM protocol."""

    def __init__(self, protocol_handler, pin=20, num_leds=1, debug_callback=None):
        self.protocol = protocol_handler
        self.debug_callback = debug_callback

        # Initialize NeoPixel
        self.np = neopixel.NeoPixel(machine.Pin(pin), num_leds)
        self.num_leds = num_leds

        # LED state tracking
        self.current_mode = LED_MODE_STATIC
        self.current_color = (0, 0, 0)
        self.brightness = 0.5
        self.animation_running = False
        self.animation_thread = None
        self.animation_lock = _thread.allocate_lock()

        # Animation parameters
        self.blink_state = False
        self.fade_direction = 1
        self.fade_brightness = 0.0
        self.rainbow_hue = 0

        # Register handler with protocol
        self.protocol.register_handler(TYPE_LED, self._handle_led_packet)

        self._debug_print("LED handler initialized")

    def _debug_print(self, message):
        """Send debug message if callback is available."""
        if self.debug_callback:
            self.debug_callback(f"[LED Handler] {message}")

    def _handle_led_packet(self, packet):
        """Handle incoming LED control packets."""
        try:
            flags = packet.get_flags()
            command_type = flags & LED_CMD_SEQUENCE
            mode = flags & LED_MODE_MASK

            # Extract RGB values from packet data
            # data0: RG (4 bits each), data1: B + brightness (4 bits each)
            r = (packet.data0 >> 4) & 0x0F
            g = packet.data0 & 0x0F
            b = (packet.data1 >> 4) & 0x0F
            brightness_raw = packet.data1 & 0x0F

            # Scale 4-bit values to 8-bit
            r = r * 17  # 0-15 -> 0-255
            g = g * 17
            b = b * 17
            brightness = brightness_raw / 15.0  # 0-15 -> 0.0-1.0

            self._debug_print(
                f"LED command: mode={mode:02X}, RGB=({r},{g},{b}), brightness={brightness:.2f}"
            )

            if command_type == LED_CMD_IMMEDIATE:
                self._set_led_immediate(mode, r, g, b, brightness)
            else:
                self._debug_print("LED sequence commands not implemented")

            # Send acknowledgment
            self._send_led_response(packet.get_flags(), 0x00)

        except Exception as e:
            self._debug_print(f"Error handling LED packet: {e}")
            self._send_led_response(packet.get_flags(), 0xFF)  # Error response

    def _set_led_immediate(self, mode, r, g, b, brightness):
        """Set LED immediately with specified mode and color."""
        # Stop any running animation
        self._stop_animation()

        # Update state
        self.current_mode = mode
        self.current_color = (r, g, b)
        self.brightness = brightness

        # Start appropriate animation/mode
        if mode == LED_MODE_STATIC:
            self._set_static_color(r, g, b, brightness)
        elif mode == LED_MODE_BLINK:
            self._start_blink_animation(r, g, b, brightness)
        elif mode == LED_MODE_FADE:
            self._start_fade_animation(r, g, b, brightness)
        elif mode == LED_MODE_RAINBOW:
            self._start_rainbow_animation(brightness)
        else:
            self._debug_print(f"Unknown LED mode: {mode:02X}")

    def _set_static_color(self, r, g, b, brightness):
        """Set LED to static color."""
        with self.animation_lock:
            scaled_r = int(r * brightness)
            scaled_g = int(g * brightness)
            scaled_b = int(b * brightness)

            for i in range(self.num_leds):
                self.np[i] = (scaled_r, scaled_g, scaled_b)
            self.np.write()

        self._debug_print(f"Set static color: RGB({scaled_r},{scaled_g},{scaled_b})")

    def _start_blink_animation(self, r, g, b, brightness):
        """Start blinking animation."""
        self.animation_running = True
        self.blink_state = False

        def blink_thread():
            while self.animation_running:
                with self.animation_lock:
                    if self.blink_state:
                        # LED on
                        scaled_r = int(r * brightness)
                        scaled_g = int(g * brightness)
                        scaled_b = int(b * brightness)
                    else:
                        # LED off
                        scaled_r = scaled_g = scaled_b = 0

                    for i in range(self.num_leds):
                        self.np[i] = (scaled_r, scaled_g, scaled_b)
                    self.np.write()

                self.blink_state = not self.blink_state
                time.sleep_ms(BLINK_INTERVAL_MS)

        self.animation_thread = _thread.start_new_thread(blink_thread, ())
        self._debug_print("Started blink animation")

    def _start_fade_animation(self, r, g, b, brightness):
        """Start fade animation."""
        self.animation_running = True
        self.fade_direction = 1
        self.fade_brightness = 0.0

        def fade_thread():
            while self.animation_running:
                with self.animation_lock:
                    # Calculate current fade brightness
                    current_brightness = self.fade_brightness * brightness
                    scaled_r = int(r * current_brightness)
                    scaled_g = int(g * current_brightness)
                    scaled_b = int(b * current_brightness)

                    for i in range(self.num_leds):
                        self.np[i] = (scaled_r, scaled_g, scaled_b)
                    self.np.write()

                # Update fade brightness
                self.fade_brightness += self.fade_direction * (1.0 / ANIMATION_STEPS)

                if self.fade_brightness >= 1.0:
                    self.fade_brightness = 1.0
                    self.fade_direction = -1
                elif self.fade_brightness <= 0.0:
                    self.fade_brightness = 0.0
                    self.fade_direction = 1

                time.sleep_ms(FADE_STEP_MS)

        self.animation_thread = _thread.start_new_thread(fade_thread, ())
        self._debug_print("Started fade animation")

    def _start_rainbow_animation(self, brightness):
        """Start rainbow animation."""
        self.animation_running = True
        self.rainbow_hue = 0

        def rainbow_thread():
            while self.animation_running:
                with self.animation_lock:
                    # Convert HSV to RGB for rainbow effect
                    r, g, b = self._hsv_to_rgb(self.rainbow_hue, 1.0, brightness)

                    for i in range(self.num_leds):
                        self.np[i] = (int(r), int(g), int(b))
                    self.np.write()

                # Update rainbow hue
                self.rainbow_hue = (self.rainbow_hue + 10) % 360
                time.sleep_ms(RAINBOW_STEP_MS)

        self.animation_thread = _thread.start_new_thread(rainbow_thread, ())
        self._debug_print("Started rainbow animation")

    def _hsv_to_rgb(self, h, s, v):
        """Convert HSV color to RGB."""
        h = h / 60.0
        i = int(h)
        f = h - i
        p = v * (1 - s)
        q = v * (1 - s * f)
        t = v * (1 - s * (1 - f))

        if i == 0:
            r, g, b = v, t, p
        elif i == 1:
            r, g, b = q, v, p
        elif i == 2:
            r, g, b = p, v, t
        elif i == 3:
            r, g, b = p, q, v
        elif i == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q

        return r * 255, g * 255, b * 255

    def _stop_animation(self):
        """Stop any running LED animation."""
        if self.animation_running:
            self.animation_running = False
            self._debug_print("Stopped LED animation")

            # Give thread time to exit
            time.sleep_ms(50)

    def _send_led_response(self, original_flags, status_code):
        """Send LED command response to host."""
        from sam_protocol import SAMPacket, TYPE_LED

        response_packet = SAMPacket(
            type_flags=TYPE_LED | (original_flags & 0x1F), data0=status_code, data1=0x00
        )

        success = self.protocol.send_packet(response_packet)
        if success:
            self._debug_print(f"Sent LED response: status={status_code:02X}")
        else:
            self._debug_print(f"Failed to send LED response")

    def set_brightness(self, brightness):
        """Set LED brightness (called from host brightness control)."""
        self.brightness = max(0.0, min(1.0, brightness))

        # If in static mode, update immediately
        if self.current_mode == LED_MODE_STATIC:
            r, g, b = self.current_color
            self._set_static_color(r, g, b, self.brightness)

        self._debug_print(f"Brightness set to {self.brightness:.2f}")

    def get_status(self):
        """Get current LED status."""
        return {
            "mode": self.current_mode,
            "color": self.current_color,
            "brightness": self.brightness,
            "animation_running": self.animation_running,
        }

    def turn_off(self):
        """Turn off LED."""
        self._stop_animation()
        self._set_static_color(0, 0, 0, 0)
        self._debug_print("LED turned off")

    def cleanup(self):
        """Cleanup LED handler resources."""
        self._stop_animation()
        self.turn_off()
        self._debug_print("LED handler cleanup completed")
