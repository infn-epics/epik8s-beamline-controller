#!/usr/bin/env python3
"""
IOC Status Task - Monitors ArgoCD applications for IOC status and control.

This task periodically checks the status of ArgoCD applications in the namespace,
creates PVs for each devgroup showing IOC lists, and provides status/control PVs
for each IOC (sync status, health status, timestamps, and START/STOP/RESTART controls).
"""

import cothread
import time
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
from task_base import TaskBase
from softioc import builder

try:
    from kubernetes import client, config as k8s_config
    from kubernetes.client.rest import ApiException

    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    print("Warning: kubernetes library not available. IocStatusTask will not function.")


class IocMngTask(TaskBase):
    """
    Task that monitors ArgoCD applications for IOC status.

    Features:
    - Periodically polls ArgoCD applications in the namespace
    - Creates PV waveforms for each devgroup listing IOC names
    - For each IOC, creates status PVs:
      - Sync status (Synced, OutOfSync, Unknown)
      - Health status (Healthy, Progressing, Degraded, Missing, Unknown)
      - Application status (Running, Suspended, etc.)
      - Last sync timestamp
      - Last health change timestamp
    - For each IOC, creates control PVs:
      - START: Sync the application
      - STOP: Suspend the application
      - RESTART: Hard restart (delete and recreate)
    """

    def __init__(
        self,
        name: str,
        parameters: Dict[str, Any],
        pv_definitions: Dict[str, Any],
        beamline_config: Dict[str, Any],
        ophyd_devices: Dict[str, object] = None,
        prefix: str = None,
    ):
        """Initialize the IOC status task."""
        super().__init__(
            name, parameters, pv_definitions, beamline_config, ophyd_devices, prefix
        )

        # Kubernetes API client
        self.api = None
        self.k8s_namespace = None

        # IOC tracking
        self.devgroups = {}  # devgroup -> list of IOC names
        self.ioc_status = {}  # ioc_name -> status dict
        self.ioc_pvs = {}  # ioc_name -> dict of PV objects

        # Status tracking for change detection
        self.last_health_status = {}  # ioc_name -> health status
        self.last_health_change_time = {}  # ioc_name -> timestamp

        # Control action queue
        self.control_queue = []
        self.control_lock = threading.Lock()

    def initialize(self):
        """Initialize the IOC status monitoring task."""
        self.logger.info("Initializing IOC status task")

        # Check if kubernetes is available
        if not KUBERNETES_AVAILABLE:
            self.logger.error("Kubernetes library not available. Task cannot function.")
            self.set_status("ERROR")
            self.set_message("Kubernetes library not available")
            return

        # Get configuration parameters
        self.update_rate = self.parameters.get(
            "update_rate", 0.05
        )  # Hz (default: every 2 seconds)
        self.argocd_namespace = self.parameters.get("argocd_namespace", "argocd")

        # Get namespace from beamline config
        self.k8s_namespace = self.beamline_config.get("namespace", "default")

        # Get devgroups and IOCs from beamline config
        self._parse_beamline_config()

        # Initialize Kubernetes client
        try:
            # Try in-cluster config first
            k8s_config.load_incluster_config()
            self.logger.info("Loaded in-cluster Kubernetes configuration")
        except Exception as e:
            self.logger.warning(f"Could not load in-cluster config: {e}")
            try:
                # Fall back to kubeconfig
                k8s_config.load_kube_config()
                self.logger.info("Loaded Kubernetes configuration from kubeconfig")
            except Exception as e2:
                self.logger.error(f"Could not load Kubernetes configuration: {e2}")
                self.set_status("ERROR")
                self.set_message("Failed to load Kubernetes config")
                return

        self.api = client.CustomObjectsApi()

        # Create PVs for devgroups and IOCs
        self._create_ioc_pvs()

        self.logger.info(
            f"Monitoring {len(self.ioc_status)} IOCs in {len(self.devgroups)} devgroups"
        )
        self.logger.info(f"Update rate: {self.update_rate} Hz")
        self.logger.info(f"ArgoCD namespace: {self.argocd_namespace}")
        self.logger.info(f"K8s namespace: {self.k8s_namespace}")

    def _parse_beamline_config(self):
        """Parse beamline configuration to extract devgroups and IOCs."""
        # Look for 'iocs' section in beamline_config
        iocs_config = self.beamline_config.get("iocs", {})

        if not iocs_config:
            self.logger.warning("No 'iocs' section found in beamline configuration")
            return

        # Group IOCs by devgroup
        for ioc_name, ioc_data in iocs_config.items():
            if isinstance(ioc_data, dict):
                devgroup = ioc_data.get("devgroup", "default")
            else:
                devgroup = "default"

            if devgroup not in self.devgroups:
                self.devgroups[devgroup] = []

            self.devgroups[devgroup].append(ioc_name)

            # Initialize IOC status
            self.ioc_status[ioc_name] = {
                "app_status": "Unknown",
                "sync_status": "Unknown",
                "health_status": "Unknown",
                "last_sync_time": "Never",
                "last_health_change": "Never",
                "devgroup": devgroup,
            }

        self.logger.info(
            f"Found {len(self.devgroups)} devgroups with {len(self.ioc_status)} IOCs total"
        )

    def _create_ioc_pvs(self):
        """Create PVs for devgroups and individual IOCs using softioc builder."""
        # Set device name prefix
        builder.SetDeviceName(self.pv_prefix)

        # Create waveform PVs for each devgroup
        for devgroup, ioc_list in self.devgroups.items():
            pv_name = f"DEVGROUP_{devgroup.upper()}_IOCS"

            # Create a waveform of strings (char waveform with max length)
            # Join IOC names with commas
            ioc_list_str = ",".join(ioc_list)
            max_len = max(len(ioc_list_str) + 100, 1000)  # Allow room for growth

            pv = builder.WaveformIn(pv_name, initial_value=ioc_list_str, length=max_len)
            self.pvs[pv_name] = pv

            self.logger.info(
                f"Created devgroup PV: {pv_name} with {len(ioc_list)} IOCs"
            )

        # Create status and control PVs for each IOC
        for ioc_name in self.ioc_status.keys():
            self._create_ioc_specific_pvs(ioc_name)

    def _create_ioc_specific_pvs(self, ioc_name: str):
        """Create status and control PVs for a specific IOC."""
        ioc_prefix = ioc_name.upper().replace("-", "_")

        ioc_pv_dict = {}

        # Status PVs (readonly from IOC perspective)
        # Application status
        ioc_pv_dict["APP_STATUS"] = builder.stringIn(
            f"{ioc_prefix}_APP_STATUS", initial_value="Unknown"
        )

        # Sync status (mbbi: Synced=0, OutOfSync=1, Unknown=2, Error=3)
        ioc_pv_dict["SYNC_STATUS"] = builder.mbbIn(
            f"{ioc_prefix}_SYNC_STATUS",
            initial_value=2,
            ZRST="Synced",
            ONST="OutOfSync",
            TWST="Unknown",
            THST="Error",
        )

        # Health status (mbbi: Healthy=0, Progressing=1, Degraded=2, Missing=3, Unknown=4, Warning=5, Error=6)
        ioc_pv_dict["HEALTH_STATUS"] = builder.mbbIn(
            f"{ioc_prefix}_HEALTH_STATUS",
            initial_value=4,
            ZRST="Healthy",
            ONST="Progressing",
            TWST="Degraded",
            THST="Missing",
            FRST="Unknown",
            FVST="Warning",
            SXST="Error",
        )

        # Timestamps
        ioc_pv_dict["LAST_SYNC_TIME"] = builder.stringIn(
            f"{ioc_prefix}_LAST_SYNC_TIME", initial_value="Never"
        )

        ioc_pv_dict["LAST_HEALTH_CHANGE"] = builder.stringIn(
            f"{ioc_prefix}_LAST_HEALTH_CHANGE", initial_value="Never"
        )

        # Control PVs (writable buttons)
        ioc_pv_dict["START"] = builder.boolOut(
            f"{ioc_prefix}_START",
            initial_value=0,
            on_update=lambda value, ioc=ioc_name: self._on_control_action(
                ioc, "START", value
            ),
        )

        ioc_pv_dict["STOP"] = builder.boolOut(
            f"{ioc_prefix}_STOP",
            initial_value=0,
            on_update=lambda value, ioc=ioc_name: self._on_control_action(
                ioc, "STOP", value
            ),
        )

        ioc_pv_dict["RESTART"] = builder.boolOut(
            f"{ioc_prefix}_RESTART",
            initial_value=0,
            on_update=lambda value, ioc=ioc_name: self._on_control_action(
                ioc, "RESTART", value
            ),
        )

        self.ioc_pvs[ioc_name] = ioc_pv_dict

        self.logger.debug(f"Created PVs for IOC: {ioc_name}")

    def _on_control_action(self, ioc_name: str, action: str, value: Any):
        """Handle control button presses."""
        try:
            pressed = bool(value)
        except Exception:
            pressed = False

        if not pressed:
            return

        # Reset the button immediately
        button_pv = self.ioc_pvs[ioc_name].get(action)
        if button_pv:
            try:
                button_pv.set(0)
            except Exception:
                pass

        # Queue the action for processing
        with self.control_lock:
            self.control_queue.append((ioc_name, action))

        self.logger.info(f"Queued {action} action for IOC: {ioc_name}")

    def run(self):
        """Main task execution loop."""
        self.logger.info("Starting IOC status monitoring loop")

        while self.running:
            # Only process if task is enabled
            enabled = self.get_pv("ENABLE")

            if enabled:
                self._process_cycle()
                self.step_cycle()
            else:
                self.logger.debug("Task disabled, skipping cycle")

            # Sleep based on update rate
            cothread.Sleep(1.0 / self.update_rate)

    def _process_cycle(self):
        """Process one monitoring cycle."""
        try:
            # Update status for all IOCs
            self._update_all_ioc_status()

            # Process any queued control actions
            self._process_control_queue()

            # Update message
            total_iocs = len(self.ioc_status)
            healthy_count = sum(
                1 for s in self.ioc_status.values() if s["health_status"] == "Healthy"
            )
            self.set_message(f"Monitoring {total_iocs} IOCs ({healthy_count} healthy)")

        except Exception as e:
            self.logger.error(f"Error in processing cycle: {e}", exc_info=True)
            self.set_status("ERROR")
            self.set_message(f"Error: {str(e)}")

    def _update_all_ioc_status(self):
        """Update status for all IOCs by querying ArgoCD applications."""
        if not self.api:
            return

        # List all applications in the ArgoCD namespace
        try:
            apps = self.api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.argocd_namespace,
                plural="applications",
            )

            app_items = apps.get("items", [])

            # Create a map of application names to app data
            app_map = {}
            for app in app_items:
                app_name = app["metadata"]["name"]
                app_map[app_name] = app

            # Update status for each tracked IOC
            for ioc_name in self.ioc_status.keys():
                self._update_ioc_status(ioc_name, app_map.get(ioc_name))

        except ApiException as e:
            self.logger.error(f"Error listing ArgoCD applications: {e}")
        except Exception as e:
            self.logger.error(
                f"Unexpected error updating IOC status: {e}", exc_info=True
            )

    def _update_ioc_status(self, ioc_name: str, app_data: Optional[Dict]):
        """Update status for a single IOC."""
        if not app_data:
            # Application not found
            self.ioc_status[ioc_name]["app_status"] = "Missing"
            self.ioc_status[ioc_name]["sync_status"] = "Unknown"
            self.ioc_status[ioc_name]["health_status"] = "Missing"

            self._update_ioc_pvs(ioc_name)
            return

        # Extract status information
        status = app_data.get("status", {})

        # Operation phase (Running, Suspended, etc.)
        operation_state = status.get("operationState", {})
        phase = operation_state.get("phase", "Unknown")
        self.ioc_status[ioc_name]["app_status"] = phase

        # Sync status
        sync = status.get("sync", {})
        sync_status = sync.get("status", "Unknown")
        self.ioc_status[ioc_name]["sync_status"] = sync_status

        # Last sync time
        sync_result = status.get("operationState", {}).get("finishedAt")
        if sync_result:
            try:
                # Parse and format timestamp
                dt = datetime.fromisoformat(sync_result.replace("Z", "+00:00"))
                self.ioc_status[ioc_name]["last_sync_time"] = dt.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except Exception:
                self.ioc_status[ioc_name]["last_sync_time"] = sync_result

        # Health status
        health = status.get("health", {})
        health_status = health.get("status", "Unknown")

        # Detect health status change
        previous_health = self.last_health_status.get(ioc_name, "Unknown")
        if health_status != previous_health:
            self.last_health_status[ioc_name] = health_status
            self.last_health_change_time[ioc_name] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self.ioc_status[ioc_name]["last_health_change"] = (
                self.last_health_change_time[ioc_name]
            )
            self.logger.info(
                f"IOC {ioc_name} health changed: {previous_health} -> {health_status}"
            )

        self.ioc_status[ioc_name]["health_status"] = health_status

        # Update PVs
        self._update_ioc_pvs(ioc_name)

    def _update_ioc_pvs(self, ioc_name: str):
        """Update PV values for a specific IOC."""
        if ioc_name not in self.ioc_pvs:
            return

        status = self.ioc_status[ioc_name]
        pvs = self.ioc_pvs[ioc_name]

        # Update application status
        try:
            pvs["APP_STATUS"].set(status["app_status"])
        except Exception as e:
            self.logger.debug(f"Error setting APP_STATUS for {ioc_name}: {e}")

        # Update sync status
        sync_map = {"Synced": 0, "OutOfSync": 1, "Unknown": 2}
        sync_val = sync_map.get(status["sync_status"], 3)  # 3 = Error
        try:
            pvs["SYNC_STATUS"].set(sync_val)
        except Exception as e:
            self.logger.debug(f"Error setting SYNC_STATUS for {ioc_name}: {e}")

        # Update health status
        health_map = {
            "Healthy": 0,
            "Progressing": 1,
            "Degraded": 2,
            "Missing": 3,
            "Unknown": 4,
            "Warning": 5,
            "Error": 6,
        }
        health_val = health_map.get(status["health_status"], 4)  # 4 = Unknown

        # Map to warning/error if needed based on health status
        if status["health_status"] == "Progressing":
            health_val = 1  # ONST = Progressing
        elif status["health_status"] not in (
            "Healthy",
            "Progressing",
            "Degraded",
            "Missing",
            "Unknown",
        ):
            # For any other status, consider it a warning
            health_val = 5  # FVST = Warning

        try:
            pvs["HEALTH_STATUS"].set(health_val)
        except Exception as e:
            self.logger.debug(f"Error setting HEALTH_STATUS for {ioc_name}: {e}")

        # Update timestamps
        try:
            pvs["LAST_SYNC_TIME"].set(status["last_sync_time"])
        except Exception as e:
            self.logger.debug(f"Error setting LAST_SYNC_TIME for {ioc_name}: {e}")

        try:
            pvs["LAST_HEALTH_CHANGE"].set(status["last_health_change"])
        except Exception as e:
            self.logger.debug(f"Error setting LAST_HEALTH_CHANGE for {ioc_name}: {e}")

    def _process_control_queue(self):
        """Process queued control actions."""
        with self.control_lock:
            queue_copy = self.control_queue[:]
            self.control_queue.clear()

        for ioc_name, action in queue_copy:
            self.logger.info(f"Processing {action} for IOC: {ioc_name}")

            try:
                if action == "START":
                    self._start_ioc(ioc_name)
                elif action == "STOP":
                    self._stop_ioc(ioc_name)
                elif action == "RESTART":
                    self._restart_ioc(ioc_name)
            except Exception as e:
                self.logger.error(
                    f"Error executing {action} for {ioc_name}: {e}", exc_info=True
                )

    def _start_ioc(self, ioc_name: str):
        """Start (sync) an IOC application."""
        try:
            # Trigger a sync operation
            body = {
                "operation": {
                    "initiatedBy": {"username": "beamline-controller"},
                    "sync": {"revision": "HEAD", "prune": True},
                }
            }

            self.api.patch_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.argocd_namespace,
                plural="applications",
                name=ioc_name,
                body=body,
            )
            self.logger.info(f"Started (synced) IOC: {ioc_name}")
        except ApiException as e:
            self.logger.error(f"Error starting IOC {ioc_name}: {e}")

    def _stop_ioc(self, ioc_name: str):
        """Stop (suspend) an IOC application."""
        try:
            # Get current app
            app = self.api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.argocd_namespace,
                plural="applications",
                name=ioc_name,
            )

            # Patch to suspend auto-sync
            body = {"spec": {"syncPolicy": {"automated": None}}}

            self.api.patch_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.argocd_namespace,
                plural="applications",
                name=ioc_name,
                body=body,
            )

            self.logger.info(f"Stopped (suspended auto-sync) IOC: {ioc_name}")
        except ApiException as e:
            self.logger.error(f"Error stopping IOC {ioc_name}: {e}")

    def _restart_ioc(self, ioc_name: str):
        """Restart an IOC application (hard refresh)."""
        try:
            # Trigger a hard refresh by adding annotation
            body = {"metadata": {"annotations": {"argocd.argoproj.io/refresh": "hard"}}}

            self.api.patch_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.argocd_namespace,
                plural="applications",
                name=ioc_name,
                body=body,
            )

            # Also trigger a sync
            sync_body = {
                "operation": {
                    "initiatedBy": {"username": "beamline-controller"},
                    "sync": {"revision": "HEAD", "prune": True},
                }
            }

            self.api.patch_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.argocd_namespace,
                plural="applications",
                name=ioc_name,
                body=sync_body,
            )

            self.logger.info(f"Restarted IOC: {ioc_name}")
        except ApiException as e:
            self.logger.error(f"Error restarting IOC {ioc_name}: {e}")

    def cleanup(self):
        """Cleanup when task stops."""
        self.logger.info("Cleaning up IOC status task")
        self.set_status("END")
        self.set_message("Stopped")

    def handle_pv_write(self, pv_name: str, value: Any):
        """
        Handle writes to specific PVs.

        Args:
            pv_name: Name of the PV that was written
            value: New value
        """
        # Control actions are handled via _on_control_action callbacks
        pass
