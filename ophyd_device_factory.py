#!/usr/bin/env python3
"""
Factory for creating Ophyd device instances based on device group and type.
"""

import logging
from typing import Dict, Any, Optional


class OphydDeviceFactory:
    """Factory for creating Ophyd devices based on device configuration."""
    
    def __init__(self):
        """Initialize the factory."""
        self.logger = logging.getLogger(__name__)
        self._device_map = {}
        self._register_default_devices()
    
    def _register_default_devices(self):
        """Register default device types."""
        try:
            # Import infn_ophyd_hal if available
            from infn_ophyd_hal import OphydTmlMotor, SppOphydBpm
            from infn_ophyd_hal import OphydPS, OphydPSSim, OphydPSDante
            
            # Register motor devices
            self._device_map[('mot', 'tml')] = OphydTmlMotor
            self._device_map[('mot', 'motor')] = OphydTmlMotor
            
            # Register BPM devices
            self._device_map[('diag', 'bpm')] = SppOphydBpm
            self._device_map[('diag', 'libera-spe')] = SppOphydBpm
            self._device_map[('diag', 'libera-sppp')] = SppOphydBpm
            
            # Register power supply devices
            self._device_map[('mag', 'sim')] = OphydPSSim
            self._device_map[('mag', 'dante')] = OphydPSDante
            self._device_map[('mag', 'generic')] = OphydPS
            
            self.logger.info("Registered infn_ophyd_hal device types")
            
        except ImportError as e:
            self.logger.warning(f"Could not import infn_ophyd_hal: {e}")
            self.logger.warning("Ophyd device creation will be limited")
    
    def register_device_type(self, devgroup: str, devtype: str, device_class):
        """
        Register a custom device type.
        
        Args:
            devgroup: Device group (e.g., 'motor', 'diag', 'vac')
            devtype: Device type (e.g., 'tml', 'bpm')
            device_class: Ophyd device class to instantiate
        """
        key = (devgroup, devtype)
        self._device_map[key] = device_class
        self.logger.info(f"Registered device type: {devgroup}/{devtype}")
    
    def create_device(self, devgroup: str, devtype: str, prefix: str, 
                     name: str, config: Dict[str, Any]) -> Optional[object]:
        """
        Create an Ophyd device instance.
        
        Args:
            devgroup: Device group (e.g., 'motor', 'diag', 'vac')
            devtype: Device type (e.g., 'tml', 'bpm')
            prefix: EPICS PV prefix
            name: Device name
            config: Additional configuration from values.yaml
            
        Returns:
            Ophyd device instance or None if type not supported
        """
        # Try exact match first
        key = (devgroup, devtype)
        device_class = self._device_map.get(key)
        
        # Try with just devgroup if devtype not found
        if not device_class:
            key = (devgroup, 'generic')
            device_class = self._device_map.get(key)
        
        if not device_class:
            self.logger.warning(
                f"No Ophyd class registered for {devgroup}/{devtype}, "
                f"device {name} will not be created"
            )
            return None
        
        try:
            # Extract additional parameters from config
            kwargs = {
                'prefix': prefix,
                'name': name,
            }
            
            # Add POI (Points of Interest) for motors if available
            if 'poi' in config or 'iocinit' in config:
                kwargs['poi'] = config.get('poi', config.get('iocinit', []))
            
            # Create device instance
            device = device_class(**kwargs)
            
            self.logger.debug(f"Created {device_class.__name__} for {name} with prefix {prefix}")
            return device
            
        except Exception as e:
            self.logger.error(
                f"Failed to create device {name} ({devgroup}/{devtype}): {e}",
                exc_info=True
            )
            return None
    
    def get_supported_types(self) -> list:
        """
        Get list of supported (devgroup, devtype) combinations.
        
        Returns:
            List of tuples (devgroup, devtype)
        """
        return list(self._device_map.keys())
