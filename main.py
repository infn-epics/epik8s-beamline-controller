#!/usr/bin/env python3
"""
Modular Beamline Controller Application
Manages multiple tasks in dedicated threads with soft IOC integration using softioc library.
Creates Ophyd device instances for each IOC/device defined in values.yaml.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List
import yaml
from importlib import import_module
import cothread

from task_base import TaskBase
from ophyd_device_factory import OphydDeviceFactory


class BeamlineController:
    """Main controller for beamline tasks."""
    
    def __init__(self, config_path: str, values_path: str):
        """
        Initialize the beamline controller.
        
        Args:
            config_path: Path to config.yaml
            values_path: Path to values.yaml (beamline configuration)
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.values_path = values_path
        
        # Load configurations
        self.config = self._load_yaml(config_path)
        self.beamline_values = self._load_yaml(values_path)
        
        # Task management
        self.tasks: List[TaskBase] = []
        
        # Ophyd device management
        self.ophyd_devices: Dict[str, object] = {}
        self.ophyd_factory = OphydDeviceFactory()
        
    def _load_yaml(self, path: str) -> Dict:
        """Load YAML configuration file."""
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load {path}: {e}")
            raise
    
    def _load_task_class(self, task_name: str):
        """
        Dynamically load task class from tasks module.
        
        Args:
            task_name: Name of the task module (e.g., 'example_task')
            
        Returns:
            Task class
        """
        try:
            module = import_module(f"tasks.{task_name}")
            # Get class with same name as module (CamelCase)
            class_name = ''.join(word.capitalize() for word in task_name.split('_'))
            return getattr(module, class_name)
        except Exception as e:
            self.logger.error(f"Failed to load task {task_name}: {e}")
            raise
    
    def initialize_ophyd_devices(self):
        """Initialize Ophyd devices from IOC configuration in values.yaml."""
        self.logger.info("Initializing Ophyd devices from beamline configuration...")
        
        # Get IOC configurations from values.yaml
        epics_config = self.beamline_values.get('epicsConfiguration', {})
        iocs = epics_config.get('iocs', [])
        
        for ioc_config in iocs:
            ioc_name = ioc_config.get('name')
            if not ioc_name:
                continue
            
            # Check if IOC is disabled
            if ioc_config.get('disable', False):
                self.logger.debug(f"Skipping disabled IOC: {ioc_name}")
                continue
            
            # Get device group to determine Ophyd class
            devgroup = ioc_config.get('devgroup')
            devtype = ioc_config.get('devtype')
            
            if not devgroup:
                self.logger.debug(f"IOC {ioc_name} has no devgroup, skipping Ophyd creation")
                continue
            
            # Get IOC prefix for PV construction
            ioc_prefix = ioc_config.get('iocprefix', '')
            beamline = self.beamline_values.get('beamline', 'BEAMLINE').upper()
            namespace = self.beamline_values.get('namespace', 'DEFAULT').upper()
            
            # Get devices list (for IOCs with multiple devices)
            devices = ioc_config.get('devices', [])
            
            try:
                if devices:
                    # Create Ophyd instance for each device
                    for device_config in devices:
                        device_name = device_config.get('name')
                        if not device_name:
                            continue
                        
                        # Construct full PV prefix
                        pv_prefix = f"{ioc_prefix}:{device_name}"
                        
                        # Create Ophyd device
                        ophyd_device = self.ophyd_factory.create_device(
                            devgroup=devgroup,
                            devtype=devtype,
                            prefix=pv_prefix,
                            name=device_name,
                            config=device_config
                        )
                        
                        if ophyd_device:
                            device_key = f"{ioc_name}_{device_name}"
                            self.ophyd_devices[device_key] = ophyd_device
                            self.logger.info(f"Created Ophyd device: {device_key} ({devgroup}/{devtype})")
                else:
                    # Single device IOC
                    pv_prefix = f"{beamline}:{namespace}:{ioc_prefix}"
                    
                    # Create Ophyd device
                    ophyd_device = self.ophyd_factory.create_device(
                        devgroup=devgroup,
                        devtype=devtype,
                        prefix=pv_prefix,
                        name=ioc_name,
                        config=ioc_config
                    )
                    
                    if ophyd_device:
                        self.ophyd_devices[ioc_name] = ophyd_device
                        self.logger.info(f"Created Ophyd device: {ioc_name} ({devgroup}/{devtype})")
                        
            except Exception as e:
                self.logger.error(f"Failed to create Ophyd device for {ioc_name}: {e}", exc_info=True)
        
        self.logger.info(f"Created {len(self.ophyd_devices)} Ophyd devices")
    
    def initialize_tasks(self):
        """Initialize all tasks from configuration."""
        self.logger.info("Initializing tasks...")
        
        task_configs = self.config.get('tasks', {})
        
        for task_config in task_configs:
            task_name = task_config.get('name')
            task_module = task_config.get('module')
            
            if not task_name or not task_module:
                self.logger.warning(f"Skipping invalid task configuration: {task_config}")
                continue
            
            try:
                # Load task class
                TaskClass = self._load_task_class(task_module)
                
                # Get task-specific parameters
                parameters = task_config.get('parameters', {})
                
                # Get PV definitions for this task
                pv_definitions = task_config.get('pvs', {})
                
                # Create task instance
                task = TaskClass(
                    name=task_name,
                    parameters=parameters,
                    pv_definitions=pv_definitions,
                    beamline_config=self.beamline_values,
                    ophyd_devices=self.ophyd_devices
                )
                
                self.tasks.append(task)
                self.logger.info(f"Initialized task: {task_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize task {task_name}: {e}", exc_info=True)
    
    def start_tasks(self):
        """Start all tasks."""
        self.logger.info("Starting tasks...")
        
        for task in self.tasks:
            try:
                task.start()
                self.logger.info(f"Started task: {task.name}")
            except Exception as e:
                self.logger.error(f"Failed to start task {task.name}: {e}", exc_info=True)
    
    def stop_tasks(self):
        """Stop all tasks gracefully."""
        self.logger.info("Stopping tasks...")
        
        for task in self.tasks:
            try:
                task.stop()
            except Exception as e:
                self.logger.error(f"Error stopping task {task.name}: {e}", exc_info=True)
        
        self.logger.info("All tasks stopped")
    
    def run(self):
        """Main run loop."""
        try:
            self.initialize_ophyd_devices()
            self.initialize_tasks()
            self.start_tasks()
            
            self.logger.info("Beamline Controller running. Press Ctrl+C to stop.")
            
            # Run the cothread dispatcher
            cothread.WaitForQuit()
                
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            self.stop_tasks()


def setup_logging(level: str = 'INFO'):
    """Configure logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Beamline Controller Application')
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to config.yaml'
    )
    parser.add_argument(
        '--values',
        type=str,
        default='values.yaml',
        help='Path to values.yaml (beamline configuration)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Create and run controller
    controller = BeamlineController(args.config, args.values)
    controller.run()


if __name__ == '__main__':
    main()
