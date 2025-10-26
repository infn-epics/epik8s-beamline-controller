# Quick Start Guide

## Running the Example

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run with example configuration**:
   ```bash
   python main.py
   ```

3. **Test the PVs** (in another terminal):
   ```bash
   # List all PVs
   caget SPARC:SPARC:MONITOR_01:ENABLE
   caget SPARC:SPARC:LOGGER_01:ENABLE
   
   # Set input values for monitoring task
   caput SPARC:SPARC:MONITOR_01:INPUT1 1.5
   caput SPARC:SPARC:MONITOR_01:INPUT2 2.3
   caput SPARC:SPARC:MONITOR_01:INPUT3 1.8
   
   # Read the result
   caget SPARC:SPARC:MONITOR_01:OUTPUT_RESULT
   caget SPARC:SPARC:MONITOR_01:SAMPLE_COUNT
   
   # Disable a task
   caput SPARC:SPARC:MONITOR_01:ENABLE 0
   
   # Re-enable
   caput SPARC:SPARC:MONITOR_01:ENABLE 1
   ```

## Creating Your First Task

### 1. Create task file: `tasks/my_first_task.py`

```python
import cothread
from task_base import TaskBase

class MyFirstTask(TaskBase):
    def initialize(self):
        self.logger.info("My first task starting!")
        self.counter = 0
    
    def run(self):
        while self.running:
            if self.get_pv('ENABLE'):
                # Read input
                value = self.get_pv('INPUT') or 0.0
                
                # Process
                result = value * 2.0
                self.counter += 1
                
                # Write outputs
                self.set_pv('OUTPUT', result)
                self.set_pv('COUNTER', self.counter)
            
            cothread.Sleep(1.0)
    
    def cleanup(self):
        self.logger.info(f"Task stopped after {self.counter} cycles")
    
    def handle_pv_write(self, pv_name, value):
        if pv_name == 'INPUT':
            self.logger.info(f"Input changed to {value}")
```

### 2. Add to `config.yaml`:

```yaml
tasks:
  - name: "my_task"
    module: "my_first_task"
    parameters:
      # Add any parameters your task needs
    pvs:
      inputs:
        INPUT:
          type: float
          value: 0.0
          unit: "V"
          prec: 2
      outputs:
        OUTPUT:
          type: float
          value: 0.0
          unit: "V"
          prec: 2
        COUNTER:
          type: int
          value: 0
```

### 3. Run and test:

```bash
python main.py

# In another terminal
caput SPARC:SPARC:MY_TASK:INPUT 5.0
caget SPARC:SPARC:MY_TASK:OUTPUT
caget SPARC:SPARC:MY_TASK:COUNTER
```

## Tips for Development

### Using External PVs

If your task needs to read/write PVs from other IOCs:

```python
from epics import caget, caput

def run(self):
    while self.running:
        # Read from external IOC
        external_value = caget("OTHER:IOC:PV:NAME")
        
        # Write to external IOC
        caput("OTHER:IOC:COMMAND", 1)
        
        cothread.Sleep(1.0)
```

### Averaging and Buffering

```python
def initialize(self):
    self.buffer = []
    self.buffer_size = self.parameters.get('buffer_size', 10)

def run(self):
    while self.running:
        value = self.get_pv('INPUT')
        
        # Add to buffer
        self.buffer.append(value)
        if len(self.buffer) > self.buffer_size:
            self.buffer.pop(0)
        
        # Calculate average
        import numpy as np
        avg = np.mean(self.buffer)
        self.set_pv('AVERAGE', avg)
        
        cothread.Sleep(0.1)
```

### Implementing Interlocks

```python
def run(self):
    while self.running:
        # Read values
        temperature = caget("DEVICE:TEMP")
        pressure = caget("DEVICE:PRESSURE")
        
        # Check limits
        temp_ok = temperature < self.get_pv('TEMP_LIMIT')
        pressure_ok = pressure < self.get_pv('PRESSURE_LIMIT')
        
        # Update interlock status
        interlock_ok = temp_ok and pressure_ok
        self.set_pv('INTERLOCK_OK', int(interlock_ok))
        
        # Take action if needed
        if not interlock_ok:
            caput("DEVICE:SHUTDOWN", 1)
            self.logger.warning("Interlock triggered!")
        
        cothread.Sleep(1.0)
```

## Accessing Beamline Configuration

Your task can access the full `values.yaml` configuration:

```python
def initialize(self):
    # Get beamline name
    beamline = self.beamline_config.get('beamline', 'unknown')
    
    # Access nested configuration
    epics_config = self.beamline_config.get('epicsConfiguration', {})
    address_list = epics_config.get('address_list', '')
    
    self.logger.info(f"Running on {beamline} beamline")
    self.logger.info(f"EPICS address list: {address_list}")
```

## Debugging

### Enable debug logging:

```bash
python main.py --log-level DEBUG
```

### Check PV values:

```bash
# Monitor a PV for changes
camonitor SPARC:SPARC:MY_TASK:OUTPUT

# Get detailed PV info
cainfo SPARC:SPARC:MY_TASK:OUTPUT
```

### Common Issues

1. **PVs not found**: Check EPICS_CA_ADDR_LIST environment variable
2. **Task not running**: Check logs for errors in initialize() or run()
3. **Import errors**: Make sure all dependencies are installed

## Next Steps

- Look at `tasks/laser_synch_task.py` for a more complex example
- Look at `tasks/motor_control_task.py` for Ophyd device usage example
- Read the full README.md for detailed documentation
- Customize `values.yaml` with your beamline configuration

## Using Ophyd Devices

### Example: Motor Control Task

Create a task that controls motors through Ophyd:

```python
import cothread
from task_base import TaskBase

class MyMotorTask(TaskBase):
    def initialize(self):
        # Get motor device from Ophyd
        self.motor1 = self.get_device('tml-ch1')
        self.motor2 = self.get_device('tml-ch2')
        
        if not self.motor1:
            self.logger.error("Motor not found!")
    
    def run(self):
        while self.running:
            if self.get_pv('ENABLE'):
                # Read motor position
                pos = self.motor1.position
                self.set_pv('MOTOR_POS', pos)
                
                # Check for move command
                if self.get_pv('MOVE_CMD'):
                    target = self.get_pv('TARGET')
                    self.logger.info(f"Moving to {target}")
                    self.motor1.move(target, wait=False)
                    self.set_pv('MOVE_CMD', 0)
            
            cothread.Sleep(0.5)
    
    def cleanup(self):
        # Stop motors on exit
        if self.motor1:
            self.motor1.stop()
```

### Checking Available Devices

```python
def initialize(self):
    # List all Ophyd devices created from values.yaml
    available = self.list_devices()
    self.logger.info(f"Available Ophyd devices: {available}")
    
    # Example output:
    # ['tml-ch1', 'tml-ch2', 'tml-ch3', 
    #  'orbit_PLXBPM01', 'orbit_PLXBPM02',
    #  'vac-gunvpc_GUNSIP00']
```

### Device Types from values.yaml

The controller creates Ophyd devices for IOCs with `devgroup` set:

```yaml
# In values.yaml
epicsConfiguration:
  iocs:
    - name: "tml-ch1"
      devgroup: "mag"     # Creates motor device
      devtype: "tml"
      iocprefix: "TML-CH1"
      # ... other config
    
    - name: "orbit"
      devgroup: "diag"    # Creates BPM devices
      devtype: "bpm"
      devices:
        - name: "PLXBPM01"
        - name: "PLXBPM02"
```

This creates devices you can access in your tasks:
- `self.get_device('tml-ch1')` → TML motor
- `self.get_device('orbit_PLXBPM01')` → First BPM
- `self.get_device('orbit_PLXBPM02')` → Second BPM
