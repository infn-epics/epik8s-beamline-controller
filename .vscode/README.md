# VS Code Configuration

This directory contains VS Code configuration files for the Beamline Controller project.

## Debug Configurations (launch.json)

### Available Configurations:

1. **Beamline Controller** (Default)
   - Runs with DEBUG logging
   - Uses default config.yaml and values.yaml
   - Sets EPICS environment for localhost
   - Shows all code including libraries (justMyCode: false)

2. **Beamline Controller (INFO level)**
   - Runs with INFO logging
   - Uses default config.yaml and values.yaml
   - Only debugs your code (justMyCode: true)

3. **Beamline Controller (Custom Config)**
   - Prompts for custom config files
   - Allows selecting log level
   - Flexible for testing different configurations

4. **Beamline Controller (SPARC)**
   - Pre-configured for SPARC beamline
   - Uses values.yaml from ../epik8-sparc/deploy/
   - Sets SPARC-specific EPICS environment
   - Includes proxy settings for LNF network

5. **Python: Current File**
   - Debug currently open Python file
   - Useful for testing individual task modules

## How to Use

### Running with Debugger:

1. Open the Debug panel (⇧⌘D or Ctrl+Shift+D)
2. Select a configuration from the dropdown
3. Press F5 or click the green play button
4. Set breakpoints by clicking in the gutter next to line numbers

### Keyboard Shortcuts:

- **F5**: Start debugging
- **⇧F5**: Stop debugging
- **⌘⇧F5**: Restart debugging
- **F9**: Toggle breakpoint
- **F10**: Step over
- **F11**: Step into
- **⇧F11**: Step out
- **F5**: Continue

## Tasks (tasks.json)

Available tasks (⌘⇧P > "Tasks: Run Task"):

- **Run Beamline Controller**: Run normally with INFO logging
- **Run Beamline Controller (DEBUG)**: Run with DEBUG logging
- **Install Dependencies**: Install packages from requirements.txt
- **Create Virtual Environment**: Create a new venv
- **Run Tests**: Execute pytest
- **Format Code (Black)**: Auto-format all Python files
- **Lint Code (Flake8)**: Check code style

## Settings (settings.json)

Default settings include:

- Python interpreter path (venv/bin/python)
- Enable Flake8 linting
- Enable Black formatting
- Format on save
- Hide __pycache__ and .pyc files
- Configure Python analysis paths

**Note**: `settings.json` is in .gitignore so you can customize it locally without affecting the repository.

## Customizing for Your Environment

### For Different Beamlines:

Create a new configuration in `launch.json`:

```json
{
    "name": "Beamline Controller (MyBeamline)",
    "type": "debugpy",
    "request": "launch",
    "program": "${workspaceFolder}/main.py",
    "console": "integratedTerminal",
    "args": [
        "--config", "config.yaml",
        "--values", "/path/to/mybeamline/values.yaml",
        "--log-level", "INFO"
    ],
    "env": {
        "PYTHONPATH": "${workspaceFolder}",
        "EPICS_CA_ADDR_LIST": "your.broadcast.address"
    }
}
```

### Setting EPICS Environment:

Edit the `env` section in your chosen configuration:

```json
"env": {
    "PYTHONPATH": "${workspaceFolder}",
    "EPICS_BASE": "/path/to/epics/base",
    "EPICS_HOST_ARCH": "linux-x86_64",
    "EPICS_CA_ADDR_LIST": "192.168.1.255",
    "EPICS_CA_AUTO_ADDR_LIST": "NO",
    "EPICS_CA_MAX_ARRAY_BYTES": "10000000"
}
```

## Troubleshooting

### Debugger Not Starting

- Make sure Python extension is installed in VS Code
- Check that `debugpy` is installed: `pip install debugpy`
- Verify Python interpreter is selected (⌘⇧P > "Python: Select Interpreter")

### Import Errors

- Check PYTHONPATH in configuration
- Verify virtual environment is activated
- Check that dependencies are installed

### EPICS Connection Issues

- Verify EPICS_CA_ADDR_LIST is correct
- Check network connectivity
- Ensure IOCs are running
