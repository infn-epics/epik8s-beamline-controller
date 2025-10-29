#!/usr/bin/env python3
"""
Generate OPI (BOB) file dynamically from configuration.

This script reads the task configuration and generates a corresponding
CS-Studio BOY/Phoebus display file with detailed task panels.
"""

import argparse
import yaml
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom


def create_widget(widget_type, **attrs):
    """Create a widget element with attributes."""
    widget = ET.Element('widget', typeId=widget_type, version='1.0.0')
    for key, value in attrs.items():
        elem = ET.SubElement(widget, key)
        elem.text = str(value)
    return widget


def create_label(x, y, width, height, text, bold=False, size=10):
    """Create a label widget."""
    widget = create_widget(
        'org.csstudio.opibuilder.widgets.Label',
        x=x, y=y, width=width, height=height, text=text
    )
    
    if bold or size != 10:
        font = ET.SubElement(widget, 'font')
        ET.SubElement(font, 'opifont.name').text = 'Arial'
        ET.SubElement(font, 'opifont.size').text = str(size)
        if bold:
            ET.SubElement(font, 'opifont.style').text = 'bold'
    
    return widget


def create_bool_button(x, y, width, height, pv_name, text='Enable'):
    """Create a boolean button widget."""
    return create_widget(
        'org.csstudio.opibuilder.widgets.BoolButton',
        x=x, y=y, width=width, height=height,
        pv_name=pv_name, text=text
    )


def create_text_input(x, y, width, height, pv_name, read_only=True):
    """Create a text input widget."""
    return create_widget(
        'org.csstudio.opibuilder.widgets.TextInput',
        x=x, y=y, width=width, height=height,
        pv_name=pv_name, read_only=str(read_only).lower()
    )


def create_action_button(x, y, width, height, text, target_file):
    """Create an action button that opens another display."""
    widget = create_widget(
        'org.csstudio.opibuilder.widgets.ActionButton',
        x=x, y=y, width=width, height=height, text=text
    )
    
    # Add action to open related display
    actions = ET.SubElement(widget, 'actions')
    action = ET.SubElement(actions, 'action', type='OPEN_DISPLAY')
    ET.SubElement(action, 'path').text = target_file
    ET.SubElement(action, 'target').text = 'TAB'
    ET.SubElement(action, 'description').text = text
    
    return widget


def generate_task_detail_panel(task, prefix, output_dir):
    """Generate a detailed panel for a specific task showing all PVs."""
    task_name = task.get('name', 'task')
    task_pv_prefix = f"{prefix}:{task_name.upper()}"
    
    # Create display
    display = ET.Element('display',
                        typeId='org.csstudio.opibuilder.Display',
                        version='1.0.0')
    
    # Get PV definitions
    pv_defs = task.get('pvs', {})
    inputs = pv_defs.get('inputs', {})
    outputs = pv_defs.get('outputs', {})
    
    # Calculate display size
    total_pvs = len(inputs) + len(outputs) + 6  # +6 for built-in PVs
    row_height = 30
    section_height = 40
    display_height = 80 + (total_pvs * row_height) + (2 * section_height)
    
    ET.SubElement(display, 'name').text = f'{task_name} - Detail Panel'
    ET.SubElement(display, 'width').text = '800'
    ET.SubElement(display, 'height').text = str(display_height)
    
    # Title
    display.append(create_label(10, 10, 500, 30,
                                f'Task: {task_name}',
                                bold=True, size=16))
    
    y = 50
    
    # Built-in control PVs section
    display.append(create_label(10, y, 200, 30,
                                'Control & Status',
                                bold=True, size=12))
    y += 35
    
    # ENABLE
    display.append(create_label(20, y, 150, 25, 'Enable'))
    display.append(create_bool_button(180, y, 80, 25,
                                     f"{task_pv_prefix}:ENABLE",
                                     'Enable'))
    y += row_height
    
    # STATUS
    display.append(create_label(20, y, 150, 25, 'Status'))
    display.append(create_text_input(180, y, 150, 25,
                                    f"{task_pv_prefix}:STATUS"))
    y += row_height
    
    # MESSAGE
    display.append(create_label(20, y, 150, 25, 'Message'))
    display.append(create_text_input(180, y, 500, 25,
                                    f"{task_pv_prefix}:MESSAGE"))
    y += row_height
    
    # RUN or CYCLE_COUNT
    parameters = task.get('parameters', {})
    mode = parameters.get('mode', 'continuous')
    if isinstance(mode, str):
        mode = mode.lower()
    is_triggered = (mode == 'triggered' or parameters.get('triggered', False))
    
    if is_triggered:
        display.append(create_label(20, y, 150, 25, 'Trigger'))
        display.append(create_bool_button(180, y, 80, 25,
                                         f"{task_pv_prefix}:RUN",
                                         'Trigger'))
    else:
        display.append(create_label(20, y, 150, 25, 'Cycle Count'))
        display.append(create_text_input(180, y, 100, 25,
                                        f"{task_pv_prefix}:CYCLE_COUNT"))
    y += row_height + 10
    
    # Input PVs section
    if inputs:
        display.append(create_label(10, y, 200, 30,
                                    'Input Parameters',
                                    bold=True, size=12))
        y += 35
        
        for pv_name, pv_config in inputs.items():
            pv_type = pv_config.get('type', 'float')
            unit = pv_config.get('unit', '')
            label_text = f"{pv_name}" + (f" ({unit})" if unit else "")
            
            display.append(create_label(20, y, 150, 25, label_text))
            
            # Input PVs are writable (outputs from IOC perspective)
            if pv_type == 'bool':
                display.append(create_bool_button(180, y, 80, 25,
                                                 f"{task_pv_prefix}:{pv_name}",
                                                 pv_name))
            else:
                display.append(create_text_input(180, y, 150, 25,
                                                f"{task_pv_prefix}:{pv_name}",
                                                read_only=False))
            
            # Show current value
            display.append(create_text_input(340, y, 150, 25,
                                            f"{task_pv_prefix}:{pv_name}",
                                            read_only=True))
            y += row_height
        
        y += 10
    
    # Output PVs section
    if outputs:
        display.append(create_label(10, y, 200, 30,
                                    'Output Values',
                                    bold=True, size=12))
        y += 35
        
        for pv_name, pv_config in outputs.items():
            unit = pv_config.get('unit', '')
            label_text = f"{pv_name}" + (f" ({unit})" if unit else "")
            
            display.append(create_label(20, y, 150, 25, label_text))
            display.append(create_text_input(180, y, 200, 25,
                                            f"{task_pv_prefix}:{pv_name}",
                                            read_only=True))
            y += row_height
    
    # Pretty print and save
    xml_str = ET.tostring(display, encoding='unicode')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ')
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    pretty_xml = '\n'.join(lines)
    
    # Write to file
    output_file = output_dir / f"{task_name}_detail.bob"
    with open(output_file, 'w') as f:
        f.write(pretty_xml)
    
    return output_file.name


def generate_bob(config_path, values_path, output_path):
    """Generate BOB file from configuration."""
    
    # Load configurations
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Try to load values.yaml for prefix, fallback to config
    try:
        with open(values_path, 'r') as f:
            values = yaml.safe_load(f)
        prefix = values.get('prefix', config.get('prefix', 'BEAMLINE:CONTROL'))
    except FileNotFoundError:
        prefix = config.get('prefix', 'BEAMLINE:CONTROL')
    
    # Get output directory
    output_dir = Path(output_path).parent
    if not output_dir.exists():
        output_dir = Path('.')
    
    # Create root display element
    display = ET.Element('display', 
                        typeId='org.csstudio.opibuilder.Display',
                        version='1.0.0')
    
    # Get task list
    tasks = config.get('tasks', [])
    
    # Calculate display height based on number of tasks
    num_tasks = len(tasks)
    row_height = 30
    header_height = 70
    footer_height = 20
    display_height = header_height + (num_tasks * row_height) + footer_height
    
    ET.SubElement(display, 'name').text = 'Task Control Panel'
    ET.SubElement(display, 'width').text = '1000'
    ET.SubElement(display, 'height').text = str(display_height)
    
    # Add title
    display.append(create_label(10, 10, 300, 30, 
                                'Beamline Task Control & Status',
                                bold=True, size=18))
    
    # Add column headers
    y_header = 50
    display.append(create_label(10, y_header, 150, 20, 'Task Name', bold=True))
    display.append(create_label(170, y_header, 60, 20, 'Enable', bold=True))
    display.append(create_label(240, y_header, 80, 20, 'Status', bold=True))
    display.append(create_label(330, y_header, 60, 20, 'Cycles', bold=True))
    display.append(create_label(400, y_header, 350, 20, 'Message', bold=True))
    display.append(create_label(760, y_header, 100, 20, 'Details', bold=True))
    
    # Generate detail panels and add task rows
    y_start = 80
    for idx, task in enumerate(tasks):
        task_name = task.get('name', f'task_{idx}')
        task_module = task.get('module', '')
        parameters = task.get('parameters', {})
        
        # Generate detail panel for this task
        detail_file = generate_task_detail_panel(task, prefix, output_dir)
        
        # Determine if task is triggered mode
        mode = parameters.get('mode', 'continuous')
        if isinstance(mode, str):
            mode = mode.lower()
        is_triggered = (mode == 'triggered' or parameters.get('triggered', False))
        
        y = y_start + (idx * row_height)
        
        # Construct PV prefix for this task
        task_pv_prefix = f"{prefix}:{task_name.upper()}"
        
        # Task name label
        display.append(create_label(10, y, 150, 20, task_name))
        
        # Enable button
        display.append(create_bool_button(170, y, 60, 20,
                                         f"{task_pv_prefix}:ENABLE",
                                         'Enable'))
        
        # Status indicator
        display.append(create_text_input(240, y, 80, 20,
                                        f"{task_pv_prefix}:STATUS"))
        
        # Cycles counter or Trigger button
        if is_triggered:
            # For triggered tasks, show trigger button instead of cycle count
            display.append(create_bool_button(330, y, 60, 20,
                                             f"{task_pv_prefix}:RUN",
                                             'Trigger'))
        else:
            # For continuous tasks, show cycle count
            display.append(create_text_input(330, y, 60, 20,
                                            f"{task_pv_prefix}:CYCLE_COUNT"))
        
        # Message display
        display.append(create_text_input(400, y, 350, 20,
                                        f"{task_pv_prefix}:MESSAGE"))
        
        # Details button
        display.append(create_action_button(760, y, 100, 20,
                                           'Show Panel',
                                           detail_file))
    
    # Pretty print XML
    xml_str = ET.tostring(display, encoding='unicode')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ')
    
    # Remove extra blank lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    pretty_xml = '\n'.join(lines)
    
    # Write to file
    with open(output_path, 'w') as f:
        f.write(pretty_xml)
    
    print(f"Generated OPI file: {output_path}")
    print(f"  - Prefix: {prefix}")
    print(f"  - Tasks: {num_tasks}")
    for task in tasks:
        task_name = task.get('name', 'unknown')
        task_module = task.get('module', 'unknown')
        mode = task.get('parameters', {}).get('mode', 'continuous')
        pv_defs = task.get('pvs', {})
        num_inputs = len(pv_defs.get('inputs', {}))
        num_outputs = len(pv_defs.get('outputs', {}))
        detail_file = f"{task_name}_detail.bob"
        print(f"    * {task_name} ({task_module}) - {mode}")
        print(f"      Inputs: {num_inputs}, Outputs: {num_outputs}")
        print(f"      Detail panel: {detail_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate BOB/OPI file from task configuration'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='tests/test-config.yaml',
        help='Path to config.yaml file (default: tests/test-config.yaml)'
    )
    parser.add_argument(
        '--values',
        type=str,
        default='tests/sparc-beamline.yaml',
        help='Path to values.yaml file (default: tests/sparc-beamline.yaml)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='test.bob',
        help='Output BOB file path (default: test.bob)'
    )
    
    args = parser.parse_args()
    
    # Check if config exists
    if not Path(args.config).exists():
        print(f"Error: Config file not found: {args.config}")
        return 1
    
    # Generate BOB file
    try:
        generate_bob(args.config, args.values, args.output)
        return 0
    except Exception as e:
        print(f"Error generating OPI: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
