# Beamline Controller

A modular Python application for managing beamline control tasks with EPICS soft IOC integration. Each task runs in a dedicated thread and exposes PVs (Process Variables) for monitoring and control.

## Features

- **Modular Task Architecture**: Each task is a separate Python module with defined inputs/outputs
- **EPICS Soft IOC Integration**: Every task creates its own soft IOC with PVs using the `softioc` library (pythonSoftIOC)
- **Ophyd Device Integration**: Automatically creates Ophyd device instances for all IOCs/devices defined in values.yaml
- **Device Abstraction**: Tasks can access motors, BPMs, and other devices through high-level Ophyd interfaces
- **Cothread-Based Execution**: Tasks run using cooperative threading via cothread
- **Enable/Disable Control**: Each task has a built-in ENABLE PV for runtime control
- **YAML Configuration**: Simple configuration via YAML files
- **Beamline Integration**: Access to full beamline configuration from values.yaml

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd epik8s-beamline-controller
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure EPICS base is installed** (required for softioc):
   - Set `EPICS_BASE` environment variable
   - Set `EPICS_HOST_ARCH` environment variable
   - Add EPICS binaries to PATH

## Usage

### Basic Usage

Run the controller with default configuration files:

```bash
python main.py
```

### Custom Configuration

Specify custom configuration files:

```bash
python main.py --config my_config.yaml --values my_values.yaml --log-level DEBUG
```

### Command Line Options

- `--config`: Path to config.yaml (default: `config.yaml`)
- `--values`: Path to values.yaml (default: `values.yaml`)
- `--log-level`: Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)

## Configuration

### config.yaml

Defines the tasks to run and their configurations:

```yaml
tasks:
  - name: "monitor_01"
    module: "monitoring_task"  # Python module in tasks/ directory
    parameters:
      update_rate: 2.0  # Task-specific parameters
      calculation_type: "average"
    pvs:
      inputs:
        INPUT1:
          type: float
          value: 0.0
          unit: "V"
          prec: 3
      outputs:
        OUTPUT_RESULT:
          type: float
          value: 0.0
          unit: "V"
          prec: 3
```

### values.yaml

Contains the beamline configuration (can reference your existing SPARC configuration).

**Important**: The controller reads the `epicsConfiguration.iocs` section and creates Ophyd device instances for each IOC based on:
- `devgroup`: Device group (e.g., 'mag', 'diag', 'vac', 'ps')
- `devtype`: Device type (e.g., 'tml', 'bpm', 'dante')
- Device naming follows the pattern: `{beamline}:{namespace}:{iocprefix}:{device_name}`

## Ophyd Device Integration

The controller automatically creates Ophyd device instances from your values.yaml IOC configuration. Each task receives a dictionary of these devices.

### Accessing Ophyd Devices in Tasks

```python
def initialize(self):
    # Get a specific device
    motor = self.get_device('tml-ch1')
    if motor:
        position = motor.position
        motor.move(10.0, wait=False)
    
    # List all available devices
    devices = self.list_devices()
    self.logger.info(f"Available devices: {devices}")
    
    # Get devices by type (if implemented)
    motors = self.get_devices_by_type('mag')
```

### Supported Device Types

The factory supports these device types from `infn_ophyd_hal`:

- **Motors** (`devgroup='mag'`):
  - `devtype='tml'`: TML motors (OphydTmlMotor)
  
- **BPMs** (`devgroup='diag'`):
  - `devtype='bpm'`, `'libera-spe'`, `'libera-sppp'`: Beam Position Monitors (SppOphydBpm)
  
- **Power Supplies** (`devgroup='ps'`):
  - `devtype='sim'`: Simulated power supply (OphydPSSim)
  - `devtype='dante'`: Dante magnet power supply (OphydPSDante)
  - `devtype='generic'`: Generic power supply (OphydPS)

### Device Naming Convention

Devices are named based on the IOC configuration:
- Single device IOCs: Named by IOC name (e.g., `"tml-ch1"`)
- Multi-device IOCs: Named as `"{ioc_name}_{device_name}"` (e.g., `"llrfs01_device1"`)

### Adding Custom Device Types

You can register custom Ophyd device types:

```python
from ophyd_device_factory import OphydDeviceFactory

factory = OphydDeviceFactory()
factory.register_device_type('custom_group', 'custom_type', MyOphydClass)
```

## Creating Custom Tasks

### 1. Create a Task Module

Create a new Python file in the `tasks/` directory (e.g., `my_custom_task.py`):

```python
from task_base import TaskBase
from typing import Any

class MyCustomTask(TaskBase):
    """My custom task implementation."""
    
    def initialize(self):
        """Initialize the task."""
        # Get parameters from config
        self.my_param = self.parameters.get('my_param', 'default')
        
        # Access beamline config
        beamline = self.beamline_config.get('beamline', 'unknown')
        
        self.logger.info(f"Task initialized with param: {self.my_param}")
    
    def run(self):
        """Main execution loop."""
        import cothread
        while self.running:
            # Check if enabled
            if self.get_pv('ENABLE'):
                # Read input PVs
                input_val = self.get_pv('MY_INPUT') or 0.0
                
                # Do processing
                result = input_val * 2.0
                
                # Write output PVs
                self.set_pv('MY_OUTPUT', result)
            
            cothread.Sleep(1.0)
    
    def cleanup(self):
        """Cleanup when stopping."""
        self.logger.info("Task stopped")
    
    def handle_pv_write(self, pv_name: str, value: Any):
        """Handle PV writes."""
        if pv_name == 'MY_INPUT':
            self.logger.debug(f"Input changed to {value}")
```

### 2. Add Task to config.yaml

```yaml
tasks:
  - name: "custom_task_01"
    module: "my_custom_task"  # Module name (without .py)
    parameters:
      my_param: "custom_value"
    pvs:
      inputs:
        MY_INPUT:
          type: float
          value: 0.0
      outputs:
        MY_OUTPUT:
          type: float
          value: 0.0
```

### 3. Run the Controller

```bash
python main.py
```

## PV Naming Convention

PVs are automatically prefixed based on the beamline configuration:

```
{BEAMLINE}:{NAMESPACE}:{TASK_NAME}:{PV_NAME}
```

For example, with SPARC beamline:
- `SPARC:SPARC:MONITOR_01:INPUT1`
- `SPARC:SPARC:MONITOR_01:OUTPUT_RESULT`
- `SPARC:SPARC:MONITOR_01:ENABLE`

## Built-in PVs

Every task automatically has these standard PVs:

- **ENABLE**: Boolean (0/1) - Enable/disable task execution
- **STATUS**: Multistate (INIT/RUN/PAUSED/END/ERROR) - Current task state
- **MESSAGE**: String - Status messages and error descriptions
- **CYCLE_COUNT**: Integer - Execution cycle counter (continuous tasks only)
- **RUN**: Boolean button - Trigger execution (triggered tasks only)

**Note**: These PV names are reserved and should not be defined in your task's `pvs.inputs` or `pvs.outputs` configuration.

## Generating OPI/BOB Display

The project includes a script to automatically generate CS-Studio BOY/Phoebus display files from your configuration:

```bash
# Generate OPI from default config
python generate_opi.py

# Specify custom config and output
python generate_opi.py --config my_config.yaml --values my_values.yaml --output my_display.bob
```

The generated display includes:
- Enable buttons for each task
- Status indicators showing current state
- Cycle counters (for continuous tasks)
- Trigger buttons (for triggered tasks)
- Message displays showing task status/errors

After running the script, open `test.bob` in Phoebus or CS-Studio to monitor and control your tasks.

## PV Types

Supported PV types in configuration:

- `float`: Floating point value (creates `aIn`/`aOut` records)
- `int`: Integer value (creates `longIn`/`longOut` records)
- `string`: String value (creates `stringIn`/`stringOut` records)
- `bool`: Boolean type (creates `boolIn`/`boolOut` records)

Optional PV fields:

- `value`: Initial value
- `unit`: Engineering unit (EGU field)
- `prec`: Precision (for float)
- `znam`/`onam`: Zero/One names (for bool)
- `low`/`high`: Display limits (LOPR/HOPR fields)

## Example Tasks

### Monitoring Task

Reads multiple inputs, performs calculations, and updates outputs:

```bash
# Access PVs
caget SPARC:SPARC:MONITOR_01:INPUT1
caput SPARC:SPARC:MONITOR_01:INPUT1 5.5
caget SPARC:SPARC:MONITOR_01:OUTPUT_RESULT
```

### Data Logging Task

Logs data to files at regular intervals:

```bash
# Check log status
caget SPARC:SPARC:LOGGER_01:LOG_COUNT
caget SPARC:SPARC:LOGGER_01:LAST_LOG_TIME

# Disable logging
caput SPARC:SPARC:LOGGER_01:ENABLE 0
```

## Architecture

```
main.py
├── Loads config.yaml and values.yaml
├── Creates BeamlineController
└── For each task:
    ├── Loads task module dynamically
    ├── Creates task instance with parameters and PV definitions
    ├── Task creates PVs using softioc builder
    ├── Task initializes IOC (builder.LoadDatabase, softioc.iocInit)
    └── Task runs in cothread
        ├── Runs task.initialize()
        └── Runs task.run() loop using cothread.Sleep()
```

## Task Lifecycle

1. **Initialization**: `initialize()` called once at startup
2. **Execution**: `run()` called in cothread (use `cothread.Sleep()` for delays)
3. **PV Updates**: `handle_pv_write()` called when input PVs are written
4. **Cleanup**: `cleanup()` called when stopping

## Development Tips

1. **Logging**: Use `self.logger` for consistent logging
2. **Thread Safety**: cothread handles cooperative threading automatically
3. **PV Access**: Always use `self.get_pv()` and `self.set_pv()` methods
4. **Enable Check**: Check `self.get_pv('ENABLE')` in your run loop and `self.running` flag
5. **Parameters**: Access task parameters via `self.parameters`
6. **Beamline Config**: Access beamline data via `self.beamline_config`
7. **Sleep**: Use `cothread.Sleep()` instead of `time.sleep()`
8. **External PVs**: Use `epics.caget()` and `epics.caput()` to interact with other IOCs

## Troubleshooting

### PVs Not Visible

- Check EPICS environment variables (`EPICS_CA_ADDR_LIST`, etc.)
- Verify PV prefix in logs
- Use `cainfo` or `pvget` to test connectivity

### Task Not Starting

- Check logs for errors during initialization
- Verify task module name matches file name
- Ensure all required parameters are provided

### Import Errors

- Verify all dependencies are installed: `pip install -r requirements.txt`
- Check Python path includes project root

## License

[Add your license information here]

## Contributors

Main controller of the beamline activities
