"""
SAM Power Management Handler for RP2040

This module handles power management commands and provides power metrics
monitoring according to the SAM protocol specification.

Author: Pamir AI
Date: 2025-07-14
Version: 1.0.0
"""

import time
import machine
from micropython import const
from sam_protocol import (
    TYPE_POWER,
    POWER_CMD_QUERY,
    POWER_CMD_SET,
    POWER_CMD_SLEEP,
    POWER_CMD_SHUTDOWN,
    POWER_CMD_CURRENT,
    POWER_CMD_BATTERY,
    POWER_CMD_TEMP,
    POWER_CMD_VOLTAGE,
    POWER_CMD_REQUEST_METRICS,
)

# Power management constants
BATTERY_ADC_PIN = const(29)  # Typical RP2040 battery monitoring pin
TEMP_SENSOR_PIN = const(4)  # Temperature sensor ADC pin
VOLTAGE_DIVIDER_RATIO = const(2.0)  # Voltage divider ratio for battery monitoring
ADC_REFERENCE_VOLTAGE = const(3.3)  # RP2040 ADC reference voltage
ADC_RESOLUTION = const(65535)  # 16-bit ADC resolution

# Battery constants
BATTERY_MIN_VOLTAGE = const(3.0)  # Minimum battery voltage (0%)
BATTERY_MAX_VOLTAGE = const(4.2)  # Maximum battery voltage (100%)

# Power states
POWER_STATE_ACTIVE = const(0)
POWER_STATE_SLEEP = const(1)
POWER_STATE_SHUTDOWN = const(2)


class SAMPowerHandler:
    """Handles power management commands for SAM protocol."""

    def __init__(self, protocol_handler, debug_callback=None):
        self.protocol = protocol_handler
        self.debug_callback = debug_callback

        # Initialize ADC for power monitoring
        self.battery_adc = machine.ADC(BATTERY_ADC_PIN)
        self.temp_adc = machine.ADC(TEMP_SENSOR_PIN)

        # Power state tracking
        self.power_state = POWER_STATE_ACTIVE
        self.last_metrics_time = 0
        self.metrics_interval_ms = 1000  # Default 1 second

        # Power metrics cache
        self.current_ma = 0
        self.battery_percent = 0
        self.temperature_dc = 250  # 25.0°C in deci-celsius
        self.voltage_mv = 0

        # Boot notification tracking
        self.boot_notification_sent = False

        # Register handler with protocol
        self.protocol.register_handler(TYPE_POWER, self._handle_power_packet)

        # Send boot notification
        self._send_boot_notification()

        self._debug_print("Power handler initialized")

    def _debug_print(self, message):
        """Send debug message if callback is available."""
        if self.debug_callback:
            self.debug_callback(f"[Power Handler] {message}")

    def _handle_power_packet(self, packet):
        """Handle incoming power management packets."""
        try:
            flags = packet.get_flags()
            command = flags & 0xF0  # Upper 4 bits

            self._debug_print(f"Power command: {command:02X}")

            if command == POWER_CMD_QUERY:
                self._handle_power_query(packet)
            elif command == POWER_CMD_SET:
                self._handle_power_set(packet)
            elif command == POWER_CMD_SLEEP:
                self._handle_power_sleep(packet)
            elif command == POWER_CMD_SHUTDOWN:
                self._handle_power_shutdown(packet)
            elif command == POWER_CMD_CURRENT:
                self._handle_current_request(packet)
            elif command == POWER_CMD_BATTERY:
                self._handle_battery_request(packet)
            elif command == POWER_CMD_TEMP:
                self._handle_temperature_request(packet)
            elif command == POWER_CMD_VOLTAGE:
                self._handle_voltage_request(packet)
            elif command == POWER_CMD_REQUEST_METRICS:
                self._handle_metrics_request(packet)
            else:
                self._debug_print(f"Unknown power command: {command:02X}")
                self._send_power_response(command, 0xFF, 0xFF)  # Error response

        except Exception as e:
            self._debug_print(f"Error handling power packet: {e}")
            self._send_power_response(POWER_CMD_QUERY, 0xFF, 0xFF)

    def _handle_power_query(self, packet):
        """Handle power status query."""
        self._update_all_metrics()
        self._send_power_response(
            POWER_CMD_QUERY, self.power_state, self.battery_percent
        )
        self._debug_print(
            f"Sent power status: state={self.power_state}, battery={self.battery_percent}%"
        )

    def _handle_power_set(self, packet):
        """Handle power state set command."""
        new_state = packet.data0
        param = packet.data1

        if new_state in [POWER_STATE_ACTIVE, POWER_STATE_SLEEP, POWER_STATE_SHUTDOWN]:
            old_state = self.power_state
            self.power_state = new_state
            self._debug_print(f"Power state changed: {old_state} -> {new_state}")
            self._send_power_response(POWER_CMD_SET, new_state, 0x00)
        else:
            self._debug_print(f"Invalid power state: {new_state}")
            self._send_power_response(POWER_CMD_SET, 0xFF, 0xFF)

    def _handle_power_sleep(self, packet):
        """Handle sleep command."""
        self.power_state = POWER_STATE_SLEEP
        self._debug_print("Entering sleep mode")
        self._send_power_response(POWER_CMD_SLEEP, 0x00, 0x00)

        # Implement sleep mode (reduce power consumption)
        # Note: Actual sleep implementation would depend on hardware requirements

    def _handle_power_shutdown(self, packet):
        """Handle shutdown command."""
        self.power_state = POWER_STATE_SHUTDOWN
        self._debug_print("Shutdown command received")
        self._send_power_response(POWER_CMD_SHUTDOWN, 0x00, 0x00)

        # Implement shutdown sequence
        # Note: Actual shutdown would coordinate with external PMIC

    def _handle_current_request(self, packet):
        """Handle current measurement request."""
        current = self._measure_current()
        self._send_power_response(
            POWER_CMD_CURRENT, (current >> 8) & 0xFF, current & 0xFF
        )
        self._debug_print(f"Sent current measurement: {current}mA")

    def _handle_battery_request(self, packet):
        """Handle battery percentage request."""
        battery_percent = self._measure_battery_percentage()
        self._send_power_response(POWER_CMD_BATTERY, battery_percent, 0x00)
        self._debug_print(f"Sent battery percentage: {battery_percent}%")

    def _handle_temperature_request(self, packet):
        """Handle temperature request."""
        temp_dc = self._measure_temperature()
        self._send_power_response(POWER_CMD_TEMP, (temp_dc >> 8) & 0xFF, temp_dc & 0xFF)
        self._debug_print(f"Sent temperature: {temp_dc/10:.1f}°C")

    def _handle_voltage_request(self, packet):
        """Handle voltage request."""
        voltage = self._measure_voltage()
        self._send_power_response(
            POWER_CMD_VOLTAGE, (voltage >> 8) & 0xFF, voltage & 0xFF
        )
        self._debug_print(f"Sent voltage: {voltage}mV")

    def _handle_metrics_request(self, packet):
        """Handle comprehensive metrics request."""
        self._update_all_metrics()

        # Send all metrics in sequence
        self._send_power_response(
            POWER_CMD_CURRENT, (self.current_ma >> 8) & 0xFF, self.current_ma & 0xFF
        )
        time.sleep_ms(10)

        self._send_power_response(POWER_CMD_BATTERY, self.battery_percent, 0x00)
        time.sleep_ms(10)

        self._send_power_response(
            POWER_CMD_TEMP,
            (self.temperature_dc >> 8) & 0xFF,
            self.temperature_dc & 0xFF,
        )
        time.sleep_ms(10)

        self._send_power_response(
            POWER_CMD_VOLTAGE, (self.voltage_mv >> 8) & 0xFF, self.voltage_mv & 0xFF
        )

        self._debug_print("Sent complete metrics set")

    def _measure_current(self):
        """Measure current consumption in milliamps."""
        # Placeholder implementation - would require current sensing hardware
        # For now, return a simulated value based on power state
        if self.power_state == POWER_STATE_ACTIVE:
            self.current_ma = 150  # 150mA active
        elif self.power_state == POWER_STATE_SLEEP:
            self.current_ma = 10  # 10mA sleep
        else:
            self.current_ma = 5  # 5mA shutdown

        return self.current_ma

    def _measure_battery_percentage(self):
        """Measure battery charge percentage."""
        voltage = self._measure_voltage() / 1000.0  # Convert to volts

        # Linear approximation of battery percentage
        if voltage >= BATTERY_MAX_VOLTAGE:
            self.battery_percent = 100
        elif voltage <= BATTERY_MIN_VOLTAGE:
            self.battery_percent = 0
        else:
            percentage = (
                (voltage - BATTERY_MIN_VOLTAGE)
                / (BATTERY_MAX_VOLTAGE - BATTERY_MIN_VOLTAGE)
            ) * 100
            self.battery_percent = int(percentage)

        return self.battery_percent

    def _measure_temperature(self):
        """Measure temperature in deci-celsius (0.1°C units)."""
        try:
            # Read RP2040 internal temperature sensor
            adc_reading = self.temp_adc.read_u16()
            voltage = (adc_reading / ADC_RESOLUTION) * ADC_REFERENCE_VOLTAGE

            # RP2040 temperature calculation (from datasheet)
            # T = 27 - (V - 0.706)/0.001721
            temp_celsius = 27 - (voltage - 0.706) / 0.001721
            self.temperature_dc = int(temp_celsius * 10)  # Convert to deci-celsius

        except Exception as e:
            self._debug_print(f"Temperature measurement error: {e}")
            self.temperature_dc = 250  # Default 25.0°C

        return self.temperature_dc

    def _measure_voltage(self):
        """Measure battery voltage in millivolts."""
        try:
            # Read battery voltage through voltage divider
            adc_reading = self.battery_adc.read_u16()
            voltage = (adc_reading / ADC_RESOLUTION) * ADC_REFERENCE_VOLTAGE

            # Account for voltage divider
            battery_voltage = voltage * VOLTAGE_DIVIDER_RATIO
            self.voltage_mv = int(battery_voltage * 1000)  # Convert to mV

        except Exception as e:
            self._debug_print(f"Voltage measurement error: {e}")
            self.voltage_mv = 3700  # Default 3.7V

        return self.voltage_mv

    def _update_all_metrics(self):
        """Update all power metrics."""
        self._measure_current()
        self._measure_battery_percentage()
        self._measure_temperature()
        self._measure_voltage()
        self.last_metrics_time = time.ticks_ms()

    def _send_power_response(self, command, data0, data1):
        """Send power management response to host."""
        success = self.protocol.send_power_response(command, (data0 << 8) | data1)
        if not success:
            self._debug_print(
                f"Failed to send power response for command {command:02X}"
            )

    def _send_boot_notification(self):
        """Send boot notification to host."""
        if not self.boot_notification_sent:
            # Send boot notification as a power query with special flag
            boot_packet = self.protocol.SAMPacket(
                type_flags=TYPE_POWER | POWER_CMD_QUERY,
                data0=0xB0,  # Boot notification flag
                data1=0x07,  # Boot notification code
            )

            if self.protocol.send_packet(boot_packet):
                self.boot_notification_sent = True
                self._debug_print("Boot notification sent")
            else:
                self._debug_print("Failed to send boot notification")

    def periodic_update(self):
        """Perform periodic power metrics update."""
        current_time = time.ticks_ms()

        if (
            time.ticks_diff(current_time, self.last_metrics_time)
            >= self.metrics_interval_ms
        ):
            self._update_all_metrics()

            # Optionally send metrics update to host
            # This could be enabled based on host configuration

    def get_metrics(self):
        """Get current power metrics."""
        return {
            "current_ma": self.current_ma,
            "battery_percent": self.battery_percent,
            "temperature_dc": self.temperature_dc,
            "voltage_mv": self.voltage_mv,
            "power_state": self.power_state,
            "last_update": self.last_metrics_time,
        }

    def set_metrics_interval(self, interval_ms):
        """Set power metrics update interval."""
        self.metrics_interval_ms = max(100, interval_ms)  # Minimum 100ms
        self._debug_print(f"Metrics interval set to {self.metrics_interval_ms}ms")

    def enter_sleep_mode(self):
        """Enter sleep mode to reduce power consumption."""
        self.power_state = POWER_STATE_SLEEP
        self._debug_print("Entering sleep mode")

        # Implement actual sleep mode power reduction
        # This would typically involve:
        # - Reducing CPU frequency
        # - Disabling unnecessary peripherals
        # - Configuring wake-up sources

    def wake_from_sleep(self):
        """Wake from sleep mode."""
        if self.power_state == POWER_STATE_SLEEP:
            self.power_state = POWER_STATE_ACTIVE
            self._debug_print("Waking from sleep mode")

    def cleanup(self):
        """Cleanup power handler resources."""
        self._debug_print("Power handler cleanup completed")
