#!/usr/bin/env python3
"""
Motor control task - demonstrates using Ophyd motor devices

This task:
- Monitors motors using Ophyd device instances
- Detects when motors are moving
- Logs motor name and position when movement is detected
"""

import cothread
from typing import Any
from task_base import TaskBase


class MotorControlTask(TaskBase):
    """Task for monitoring motors using Ophyd devices."""
    
    def initialize(self):
        """Initialize the motor control task."""
        self.logger.info("Initializing motor control task")
        
        # Get task parameters
        self.update_rate = self.parameters.get('update_rate', 1.0)
        self.motor_names = self.parameters.get('motor_names', [])
        
        # Get motor devices from Ophyd devices
        self.motors = {}
        for motor_name in self.motor_names:
            motor_device = self.get_device(motor_name)
            if motor_device:
                self.motors[motor_name] = motor_device
                self.logger.info(f"Found motor device: {motor_name}")
            else:
                self.logger.warning(f"Motor device not found: {motor_name}")
        
        if not self.motors:
            self.logger.warning("No motor devices found!")
        
        # Log available devices
        available_devices = self.list_devices()
        self.logger.info(f"Available Ophyd devices: {available_devices}")
        
        # Track previous moving state to detect changes
        self.previous_moving_state = {}
        for motor_name in self.motors.keys():
            self.previous_moving_state[motor_name] = False
        
        self.logger.info(f"Initialized with {len(self.motors)} motors")
    
    def run(self):
        """Main task execution loop."""
        self.logger.info("Starting motor control task execution")
        
        while self.running:
            # Only process if task is enabled
            if not self.get_pv('ENABLE'):
                self.logger.debug("Task disabled, skipping cycle")
                cothread.Sleep(1.0 / self.update_rate)
                continue
            
            try:
                self._monitor_motors()
            except Exception as e:
                self.logger.error(f"Error in processing cycle: {e}", exc_info=True)
                self.set_pv('STATUS', f"ERROR: {str(e)}")
            
            # Sleep based on update rate
            cothread.Sleep(1.0 / self.update_rate)
    
    def _monitor_motors(self):
        """Monitor motors and detect movement."""
        for motor_name, motor in self.motors.items():
            try:
                # Check if motor is moving
                is_moving = motor.moving
                position = motor.position
                
                # Detect state change from not moving to moving
                if is_moving and not self.previous_moving_state[motor_name]:
                    self.logger.info(f"Motor {motor_name} started moving - Position: {position}")
                
                # Detect state change from moving to not moving
                elif not is_moving and self.previous_moving_state[motor_name]:
                    self.logger.info(f"Motor {motor_name} stopped - Final position: {position}")
                
                # Log position while moving
                elif is_moving:
                    self.logger.info(f"Motor {motor_name} is moving - Current position: {position}")
                
                # Update tracking state
                self.previous_moving_state[motor_name] = is_moving
                
                # Update PVs if they exist
                pv_name = f"{motor_name}_POS"
                if pv_name in self.pvs:
                    self.set_pv(pv_name, position)
                
                pv_moving = f"{motor_name}_MOVING"
                if pv_moving in self.pvs:
                    self.set_pv(pv_moving, int(is_moving))
                
            except Exception as e:
                self.logger.error(f"Error monitoring {motor_name}: {e}")
    
    def cleanup(self):
        """Cleanup when task stops."""
        self.logger.info("Cleaning up motor control task")
        self.set_pv('STATUS', 'Stopped')
    
    def handle_pv_write(self, pv_name: str, value: Any):
        """
        Handle PV writes.
        
        Args:
            pv_name: Name of the PV that was written
            value: New value
        """
        self.logger.debug(f"PV {pv_name} set to {value}")
