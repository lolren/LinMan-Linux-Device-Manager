"""
LinMan - Linux Device Manager
A comprehensive device manager for Linux systems with Windows Device Manager-like interface

Features:
- Real-time device detection using udev
- USB device identification using lsusb
- GPU detection with inxi integration
- Windows-style dark theme interface
- Hardware monitoring and management

Author: Claude AI Assistant
"""

import sys
import socket
import os
import subprocess
from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
                               QMessageBox, QVBoxLayout, QWidget, QDialog, QLabel,
                               QFormLayout, QToolBar, QStyle, QTabWidget, QGroupBox,
                               QLineEdit, QTextEdit, QFrame, QStyleFactory, QMenu,
                               QDialogButtonBox, QHBoxLayout, QPushButton, QComboBox,
                               QHeaderView, QTableWidget, QTableWidgetItem, QSplitter,
                               QScrollArea)
from PySide6.QtCore import Qt, QSize, QSocketNotifier, Slot, QTimer, QThread, Signal
from PySide6.QtGui import QIcon, QAction, QFont, QPalette, QColor, QPixmap, QPainter
import pyudev

# Windows Device Manager Category Mapping
CATEGORY_MAP = {
    'net': ('Network adapters', 'network-wired', '📡'),
    'sound': ('Sound, video and game controllers', 'audio-card', '🔊'),
    'video4linux': ('Cameras', 'camera-web', '📷'),
    'input': ('Keyboards', 'input-keyboard', '⌨️'),
    'hid': ('Mice and other pointing devices', 'input-mouse', '🖱️'),
    'usb': ('Universal Serial Bus controllers', 'drive-removable-media', '🔌'),
    'block': ('Disk drives', 'drive-harddisk', '💾'),
    'graphics': ('Display adapters', 'video-display', '🖥️'),
    'drm': ('Display adapters', 'video-display', '🖥️'),
    'bluetooth': ('Bluetooth', 'bluetooth', '📶'),
    'pci': ('System devices', 'computer-chip', '⚙️'),
    'pnp': ('System devices', 'computer-chip', '⚙️'),
    'printer': ('Print queues', 'printer', '🖨️'),
    'scsi': ('Storage controllers', 'drive-harddisk-system', '💿'),
    'tty': ('Ports', 'serial-port', '🔌'),
    'webcams': ('Imaging devices', 'camera-web', '📷'),
    'com_ports': ('Ports (COM & LPT)', 'serial-port', '🔌'),
    'thermal': ('System devices', 'temperature', '🌡️'),
    'firmware': ('System devices', 'computer-chip', '🔧'),
    'acpi': ('System devices', 'computer-chip', '🔧'),
    'dmi': ('System devices', 'computer-chip', '🔧'),
    'leds': ('System devices', 'computer-chip', '🔧')
}

# Priority subsystems to show (important devices) - include graphics/drm for GPU detection
IMPORTANT_SUBSYSTEMS = {
    'net', 'sound', 'video4linux', 'input', 'hid', 'usb', 'block',
    'bluetooth', 'pci', 'printer', 'scsi', 'tty', 'graphics', 'drm',
    'thermal', 'firmware', 'acpi', 'dmi'
}

class PropertiesDialog(QDialog):
    def __init__(self, device_data, icon, parent=None):
        super().__init__(parent)
        self.device_data = device_data
        self.icon = icon
        self.setWindowTitle("Device Properties")
        self.setMinimumSize(600, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setup_dialog_styling()
        self.setup_ui()

    def setup_dialog_styling(self):
        """Fix properties dialog styling to prevent white text on white background"""
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                color: #000000;
            }
            QLabel {
                color: #000000;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
            }
            QPushButton {
                background-color: #f3f3f3;
                border: 1px solid #d1d1d1;
                padding: 8px 18px;
                border-radius: 3px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                color: #000000;
                min-height: 28px;
            }
            QPushButton:hover {
                background-color: #e5f3ff;
                border: 1px solid #0078d4;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #cce4f7;
                border: 1px solid #0078d4;
                color: #000000;
            }
            QPushButton:default {
                background-color: #0078d4;
                color: white;
                border: 1px solid #0078d4;
            }
            QPushButton:default:hover {
                background-color: #106ebe;
                border: 1px solid #106ebe;
                color: white;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #d1d1d1;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                background-color: white;
                color: #000000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                background-color: white;
                color: #000000;
                font-size: 11pt;
            }
            QTextEdit {
                border: 1px solid #d1d1d1;
                border-radius: 3px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                background-color: white;
                padding: 6px;
                color: #000000;
            }
            QLineEdit {
                border: 1px solid #d1d1d1;
                padding: 6px 8px;
                border-radius: 3px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                background-color: white;
                color: #000000;
            }
            QComboBox {
                border: 1px solid #d1d1d1;
                padding: 6px 8px;
                border-radius: 3px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                background-color: white;
                color: #000000;
                min-width: 80px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #d1d1d1;
                background-color: white;
                color: #000000;
                selection-background-color: #0078d4;
                selection-color: white;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
            }
            QTabWidget::pane {
                border: 1px solid #9b9b9b;
                background-color: white;
                top: -2px;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                border: 1px solid #9b9b9b;
                border-bottom: none;
                padding: 6px 16px;
                margin-right: -1px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                color: #000000;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 1px solid white;
                position: relative;
                color: #000000;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
                color: #000000;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e5f3ff;
                color: #000000;
            }
            QTableWidget {
                border: 1px solid #d1d1d1;
                background-color: white;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                gridline-color: #e5e5e5;
                color: #000000;
            }
            QTableWidget::item {
                padding: 6px 8px;
                color: #000000;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QHeaderView::section {
                background-color: #f3f3f3;
                border: 1px solid #d1d1d1;
                padding: 6px 8px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                font-weight: bold;
                color: #000000;
            }
        """)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Icon and device name at the top
        header_layout = QHBoxLayout()

        icon_label = QLabel()
        icon_label.setPixmap(self.icon.pixmap(32, 32))

        name_text = self.device_data.get('MODEL', 'Unknown Device')
        # Don't truncate the name in the dialog - let it wrap if needed
        name_label = QLabel(f"<b>{name_text}</b>")
        name_label.setStyleSheet("font-size: 11pt; font-weight: bold; font-family: 'Segoe UI', Arial, sans-serif; color: #000000;")
        name_label.setWordWrap(True)

        header_layout.addWidget(icon_label)
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Create tab widget
        self.tabs = QTabWidget()

        # Windows-style tabs with proper text colors
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #9b9b9b;
                background-color: white;
                top: -2px;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                border: 1px solid #9b9b9b;
                border-bottom: none;
                padding: 6px 16px;
                margin-right: -1px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                color: #000000;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 1px solid white;
                position: relative;
                color: #000000;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
                color: #000000;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e5f3ff;
                color: #000000;
            }
        """)

        self.tabs.addTab(self.create_general_tab(), "General")
        self.tabs.addTab(self.create_driver_tab(), "Driver")
        self.tabs.addTab(self.create_details_tab(), "Details")
        self.tabs.addTab(self.create_events_tab(), "Events")

        layout.addWidget(self.tabs)

        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def create_general_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # Device information section
        info_group = QGroupBox("Device information")
        info_layout = QFormLayout()
        info_layout.setLabelAlignment(Qt.AlignLeft)
        info_layout.setFormAlignment(Qt.AlignLeft)

        device_type = self.device_data.get('CATEGORY', 'Unknown device')
        manufacturer = self.device_data.get('VENDOR_ENC', self.device_data.get('VENDOR', 'Standard system devices'))
        location = f"Location {self.device_data.get('DEVPATH', 'Unknown')}"

        type_label = QLabel(device_type)
        type_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")
        mfg_label = QLabel(manufacturer)
        mfg_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")
        loc_label = QLabel(location)
        loc_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")

        info_layout.addRow("Device type:", type_label)
        info_layout.addRow("Manufacturer:", mfg_label)
        info_layout.addRow("Location:", loc_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Device status section
        status_group = QGroupBox("Device status")
        status_layout = QVBoxLayout()

        status_text = QTextEdit()
        status_text.setPlainText("The device is working properly.")
        status_text.setReadOnly(True)
        status_text.setMaximumHeight(80)
        status_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #d0d0d0;
                color: #000000;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
            }
        """)

        status_layout.addWidget(status_text)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Troubleshoot button
        troubleshoot_btn = QPushButton("Troubleshoot...")
        troubleshoot_btn.setMaximumWidth(120)
        layout.addWidget(troubleshoot_btn)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_driver_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)

        # Driver details
        driver_group = QGroupBox("Driver details")
        driver_layout = QFormLayout()

        provider_label = QLabel("Linux Kernel")
        provider_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")
        date_label = QLabel("N/A")
        date_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")
        version_label = QLabel(os.uname().release)
        version_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")
        signer_label = QLabel("N/A")
        signer_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt;")

        driver_layout.addRow("Driver Provider:", provider_label)
        driver_layout.addRow("Driver Date:", date_label)
        driver_layout.addRow("Driver Version:", version_label)
        driver_layout.addRow("Digital Signer:", signer_label)

        driver_group.setLayout(driver_layout)
        layout.addWidget(driver_group)

        # Driver buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        driver_details_btn = QPushButton("Driver Details...")
        update_driver_btn = QPushButton("Update Driver...")
        rollback_btn = QPushButton("Roll Back Driver")
        disable_btn = QPushButton("Disable Device")
        uninstall_btn = QPushButton("Uninstall Device")

        for btn in [driver_details_btn, update_driver_btn, rollback_btn, disable_btn, uninstall_btn]:
            btn.setMaximumWidth(200)
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_details_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)

        # Property dropdown
        prop_layout = QHBoxLayout()
        prop_label = QLabel("Property:")
        prop_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; font-weight: bold;")
        prop_layout.addWidget(prop_label)

        property_combo = QComboBox()
        property_combo.addItems([
            "Device description",
            "Hardware Ids",
            "Compatible Ids",
            "Device Class",
            "Driver",
            "Enumerator"
        ])
        property_combo.setMinimumWidth(200)
        prop_layout.addWidget(property_combo)
        prop_layout.addStretch()

        layout.addLayout(prop_layout)

        # Value display
        value_label = QLabel("Value:")
        value_label.setStyleSheet("color: #000000; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; font-weight: bold;")
        layout.addWidget(value_label)

        value_text = QTextEdit()
        value_text.setPlainText(f"{self.device_data.get('DEVPATH', '')}\nVendor: {self.device_data.get('VENDOR', 'N/A')}\nModel: {self.device_data.get('MODEL', 'N/A')}")
        value_text.setReadOnly(True)
        value_text.setMaximumHeight(200)
        value_text.setStyleSheet("""
            QTextEdit {
                color: #000000;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
            }
        """)
        layout.addWidget(value_text)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_events_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)

        # Events list
        events_label = QLabel("Information")
        events_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #000000; font-family: 'Segoe UI', Arial, sans-serif;")
        layout.addWidget(events_label)

        events_table = QTableWidget()
        events_table.setColumnCount(4)
        events_table.setHorizontalHeaderLabels(["Date and Time", "Source", "Event ID", "Task Category"])
        events_table.horizontalHeader().setStretchLastSection(True)
        events_table.setMaximumHeight(300)

        # Add some sample events
        sample_events = [
            ["", "Device Manager", "20001", "Device configured"],
            ["", "Device Manager", "20003", "Device started"],
            ["", "Device Manager", "20002", "Device installed"]
        ]

        events_table.setRowCount(len(sample_events))
        for row, event in enumerate(sample_events):
            for col, value in enumerate(event):
                events_table.setItem(row, col, QTableWidgetItem(value))

        layout.addWidget(events_table)
        widget.setLayout(layout)
        return widget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinMan - Linux Device Manager")
        self.resize(1100, 700)
        self.setMinimumSize(1000, 650)

        # Try to set Windows-like icon
        self.setWindowIcon(QIcon.fromTheme("computer"))

        # Cache for detected GPUs to ensure they persist
        self.cached_gpu_devices = []

        # Device information cache from hwinfo
        self.hwinfo_devices = {}
        self.refresh_hwinfo_devices()

        # Setup backend
        self.context = pyudev.Context()
        self.categories = {}

        # Setup UI
        self.setup_ui()

        # Initialize device tree
        self.refresh_devices()

        # Setup hotplug monitoring
        self.setup_monitor()

    def setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Menu bar
        self.create_menu_bar()

        # Toolbar
        self.create_toolbar()

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(19)
        self.tree.setAnimated(False)
        self.tree.itemDoubleClicked.connect(self.show_properties)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Set column width to prevent text truncation
        self.tree.setColumnWidth(0, 800)  # Wide enough for long GPU names
        self.tree.setColumnCount(1)

        # Set larger font for better readability
        font = QFont("Segoe UI", 11)
        if not font.exactMatch():
            font = QFont("Arial", 11)
        self.tree.setFont(font)

        # Set larger icon size
        self.tree.setIconSize(QSize(20, 20))

        # Dark theme tree widget with proper contrast and text display
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #3f3f46;
                background-color: #1e1e1e;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 11pt;
                color: #ffffff;
                selection-background-color: #0078d4;
                selection-color: white;
                outline: none;
                alternate-background-color: #252526;
            }
            QTreeWidget::item {
                min-height: 32px;
                height: 32px;
                border: none;
                padding: 6px 4px 6px 4px;
                color: #ffffff;
                text-align: left;
            }
            QTreeWidget::item:selected {
                background-color: #0078d4;
                color: white;
                border: none;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #2a2d2e;
                color: #ffffff;
                border: none;
            }
            QTreeWidget::branch {
                background: transparent;
                color: #ffffff;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOSIgaGVpZ2h0PSI5IiB2aWV3Qm94PSIwIDAgOSA5IiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cGF0aCBkPSJNMCAxTDEgMUw2IDVMNiA2TDEgNkwwIDZaIiBmaWxsPSIjZmZmZmZmIi8+Cjwvc3ZnPg==);
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                border-image: none;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOSIgaGVpZ2h0PSI5IiB2aWV3Qm94PSIwIDAgOSA5IiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cGF0aCBkPSJNMSAwTDYgMEw2IDFMMSAxWiIgZmlsbD0iI2ZmZmZmZiIvPgo8L3N2Zz4K);
            }
        """)

        main_layout.addWidget(self.tree)

        # Initialize root item
        self.root_item = QTreeWidgetItem(self.tree)
        self.root_item.setText(0, socket.gethostname())
        # Use a guaranteed visible computer icon
        computer_icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.root_item.setIcon(0, computer_icon)
        self.root_item.setExpanded(True)

    def create_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Exit", self.close)

        # Action menu
        action_menu = menubar.addMenu("Action")
        action_menu.addAction("Scan for hardware changes", self.refresh_devices)
        action_menu.addSeparator()
        action_menu.addAction("Add legacy hardware")
        action_menu.setEnabled(False)

        # View menu
        view_menu = menubar.addMenu("View")
        view_menu.addAction("Devices by type")
        view_menu.addAction("Devices by connection")
        view_menu.addSeparator()
        view_menu.addAction("Show hidden devices")

        # Help menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About Device Manager", self.show_about)

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        # Dark theme toolbar with proper contrast
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #2d2d30;
                border: none;
                border-bottom: 1px solid #3f3f46;
                spacing: 2px;
                padding: 4px;
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                color: #ffffff;
                padding: 6px 10px;
                margin: 1px;
                font-size: 11pt;
                font-family: "Segoe UI", Arial, sans-serif;
                min-width: 70px;
                max-width: 90px;
            }
            QToolButton:hover {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                color: white;
            }
            QToolButton:pressed {
                background-color: #005a9e;
                border: 1px solid #005a9e;
                color: white;
            }
        """)

        self.addToolBar(toolbar)

        # Back/Forward buttons
        back_action = QAction(self.style().standardIcon(QStyle.SP_ArrowBack), "Back", self)
        toolbar.addAction(back_action)

        forward_action = QAction(self.style().standardIcon(QStyle.SP_ArrowForward), "Forward", self)
        toolbar.addAction(forward_action)

        toolbar.addSeparator()

        # Computer properties
        props_action = QAction(self.style().standardIcon(QStyle.SP_ComputerIcon), "Properties", self)
        toolbar.addAction(props_action)

        toolbar.addSeparator()

        # Scan for hardware changes
        scan_action = QAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Scan for\nhardware\nchanges", self)
        scan_action.triggered.connect(self.refresh_devices)
        toolbar.addAction(scan_action)

        # Export action
        export_action = QAction(self.style().standardIcon(QStyle.SP_DialogSaveButton), "Export", self)
        toolbar.addAction(export_action)

    def setup_monitor(self):
        """Setup udev monitoring for hotplug events"""
        try:
            self.monitor = pyudev.Monitor.from_netlink(self.context)
            self.monitor.filter_by(subsystem='usb')
            self.monitor.filter_by(subsystem='input')
            self.monitor.filter_by(subsystem='net')
            self.monitor.filter_by(subsystem='block')

            self.notifier = QSocketNotifier(self.monitor.fileno(), QSocketNotifier.Read)
            self.notifier.activated.connect(self.on_hardware_change)
            self.monitor.start()
        except Exception as e:
            print(f"Warning: Could not setup hotplug monitoring: {e}")

    @Slot()
    def on_hardware_change(self):
        """Handle hardware change events"""
        try:
            self.monitor.receive_device()
            QTimer.singleShot(500, self.refresh_devices)
        except Exception as e:
            print(f"Error handling hardware change: {e}")

    def refresh_devices(self):
        """Refresh the device tree using hwinfo for comprehensive hardware detection."""
        # Save expanded states
        expanded_states = {}
        for i in range(self.root_item.childCount()):
            child = self.root_item.child(i)
            expanded_states[child.text(0)] = child.isExpanded()

        # Clear and rebuild
        self.root_item.takeChildren()
        self.categories = {}

        # Refresh hwinfo data
        self.refresh_hwinfo_devices()

        # Add GPU detection (as supplement to hwinfo)
        gpu_devices = self.detect_gpus()

        # Create devices from hwinfo data
        for category, devices in self.hwinfo_devices.items():
            # Get category mapping
            cat_name, icon_name, emoji = CATEGORY_MAP.get(category, CATEGORY_MAP.get('pci', ('System devices', 'computer-chip', '⚙️')))

            # Create category if it doesn't exist
            if cat_name not in self.categories:
                cat_item = QTreeWidgetItem(self.root_item)
                cat_item.setText(0, f"{emoji} {cat_name}")

                # Create proper icon with fallbacks
                icon = self.create_category_icon(icon_name, category)
                cat_item.setIcon(0, icon)
                cat_item.setExpanded(False)
                self.categories[cat_name] = cat_item

                # Restore expanded state
                if expanded_states.get(cat_name, False):
                    cat_item.setExpanded(True)

            for device_info in devices:
                # Create a mock device object for compatibility
                device = self.create_mock_device_from_hwinfo(category, device_info)
                if device:
                    # Add device to category
                    parent_item = self.add_device_to_tree(device, self.categories[cat_name], cat_name)

                    # For disks with partitions, add partitions as child items
                    if device.info.get('is_disk') and device.info.get('partitions'):
                        for partition_info in device.info['partitions']:
                            partition_device = self.create_mock_device_from_hwinfo(category, partition_info)
                            if partition_device:
                                self.add_device_to_tree(partition_device, parent_item, cat_name)

        # Add GPUs only if Display adapters category doesn't already exist from hwinfo
        if gpu_devices and "Display adapters" not in self.categories:
            cat_name = "Display adapters"
            cat_item = QTreeWidgetItem(self.root_item)
            cat_item.setText(0, f"🖥️ {cat_name}")
            icon = self.create_category_icon('video-card', 'graphics')
            cat_item.setIcon(0, icon)
            cat_item.setExpanded(False)
            self.categories[cat_name] = cat_item

            # Restore expanded state
            if expanded_states.get(cat_name, False):
                cat_item.setExpanded(True)

            for gpu_device in gpu_devices:
                self.add_device_to_tree(gpu_device, self.categories[cat_name], cat_name)
  
        # Expand root only, keep categories collapsed by default
        self.root_item.setExpanded(True)
        # Categories remain collapsed for better visibility

    def should_show_device(self, device):
        """Filter devices to show only important hardware."""
        subsystem = device.subsystem

        # Skip subsystems that are less important
        if subsystem not in IMPORTANT_SUBSYSTEMS:
            # But allow graphics/drm for GPU detection
            if subsystem not in ['graphics', 'drm']:
                return False

        # Skip virtual/container devices
        if 'virtual' in device.sys_name.lower():
            return False

        # Skip some internal system devices
        if subsystem == 'platform':
            return False

        # For USB, only show actual devices, not hubs and controllers
        if subsystem == 'usb':
            if device.get('DEVTYPE') == 'usb_device':
                return True
            return False

        # For block devices, show only physical disk drives
        if subsystem == 'block':
            # Skip virtual devices, partitions, and system devices
            if device.sys_name.startswith(('loop', 'ram', 'dm-', 'zram', 'md', 'nvme')):
                # For NVMe, allow only the main device (not partitions)
                if device.sys_name.startswith('nvme') and not device.sys_name.endswith('p'):
                    return True
                return False

            # Skip partitions (devices with numbers at the end)
            import re
            if re.match(r'.*\d+$', device.sys_name):
                # For nvme, allow nvme0n1 but not nvme0n1p1, etc.
                if 'nvme' in device.sys_name and 'p' not in device.sys_name:
                    return True
                return False

            # Skip CD/DVD drives
            if device.sys_name.startswith('sr'):
                return False

            # Only show main disk devices (sda, sdb, nvme0n1, etc.)
            if re.match(r'^[sh]d[a-z]$', device.sys_name) or \
               re.match(r'^nvme\d+n\d+$', device.sys_name):
                return True

            return False

        # For input devices, show only actual keyboards and mice
        if subsystem == 'input':
            # Look for specific device types
            if device.sys_name.startswith('mouse'):
                return True
            # Look for keyboards by excluding common non-keyboard input devices
            if device.sys_name.startswith(('event', 'input')):
                # Skip joystick/gamepad devices
                if 'js' in device.sys_name:
                    return False
                # For keyboards, we need to be more selective - show only a few input devices
                # to represent the keyboard(s)
                return device.sys_name in ['event0', 'event1', 'event2', 'event3']  # Common keyboard events
            return False

        # For HID devices, show only actual mice and keyboards with proper categorization
        if subsystem == 'hid':
            if ':' in device.sys_name:
                # Check if we have lsusb info for this device
                device_key = self.get_usb_device_key_from_hid_id(device.sys_name)
                if device_key and device_key in self.usb_devices_info:
                    device_info = self.usb_devices_info[device_key]
                    # Store device type info for later use in categorization
                    setattr(device, '_is_keyboard', device_info['is_keyboard'])
                    setattr(device, '_is_mouse', device_info['is_mouse'])
                    return True
                # Fallback: show USB HID devices anyway
                return True
            return False

    def get_usb_device_key_from_hid_id(self, hid_id):
        """Convert HID device ID to USB device key format."""
        try:
            # Convert "0003:046D:C077.0001" to "046d:c077"
            parts = hid_id.split(':')
            if len(parts) >= 3:
                vendor_hex = parts[1].lower()
                product_hex = parts[2].split('.')[0].lower()
                return f"{vendor_hex}:{product_hex}"
        except:
            pass
        return None

    def refresh_hwinfo_devices(self):
        """Parse hwinfo output to get comprehensive hardware information."""
        try:
            result = subprocess.run(['hwinfo', '--short'], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                self.hwinfo_devices = {}
                current_category = None
                current_devices = []

                for line in result.stdout.strip().split('\n'):
                    line = line.strip()

                    # Detect category headers (ending with colon)
                    if line.endswith(':'):
                        if current_category and current_devices:
                            self.hwinfo_devices[current_category] = current_devices

                        current_category = line[:-1].lower()  # Remove colon and lowercase
                        current_devices = []

                        # Map hwinfo categories to our subsystem names
                        category_mapping = {
                            'cpu': 'pci',
                            'keyboard': 'input',
                            'mouse': 'hid',
                            'monitor': 'pci',
                            'graphics card': 'graphics',
                            'sound': 'sound',
                            'storage': 'block',
                            'network': 'net',
                            'network interface': 'net',
                            'disk': 'block',
                            'partition': 'block',
                            'usb controller': 'pci',
                            'bridge': 'pci',
                            'memory': 'pci',
                            'unknown': 'pci'
                        }

                        current_category = category_mapping.get(current_category, current_category)
                        continue

                    # Skip empty lines and non-device lines
                    if not line or line.startswith('--') or line.startswith('  '):
                        continue

                    # Parse device line
                    device_info = {
                        'name': line.strip(),
                        'original_category': current_category
                    }

                    # Extract device path if available
                    if ' /dev/' in line:
                        parts = line.split('  ', 1)
                        if len(parts) >= 2:
                            device_info['name'] = parts[1].strip()
                            device_info['path'] = parts[0].strip()

                    current_devices.append(device_info)

                # Add the last category
                if current_category and current_devices:
                    self.hwinfo_devices[current_category] = current_devices

        except Exception as e:
            print(f"Error parsing hwinfo: {e}")
            self.hwinfo_devices = {}

        # Process disks and partitions hierarchically
        self.process_disk_hierarchy()

        # Filter network devices to show only physical interfaces
        self.filter_network_devices()

        # Add multimedia and serial devices
        self.detect_multimedia_devices()

        # Debug: Print hwinfo categories found
        print(f"HwInfo categories detected: {list(self.hwinfo_devices.keys())}")
        for category, devices in self.hwinfo_devices.items():
            print(f"  {category}: {len(devices)} devices")

    def process_disk_hierarchy(self):
        """Process disks and partitions to create hierarchical structure using multiple detection methods."""
        disks = self.hwinfo_devices.get('block', [])

        # Fallback: if hwinfo doesn't detect drives properly, use lsblk
        try:
            result = subprocess.run(['lsblk', '-J'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                import json
                lsblk_data = json.loads(result.stdout)

                hierarchical_disks = []

                for disk in lsblk_data.get('blockdevices', []):
                    if disk.get('type') == 'disk' and disk.get('name', '').startswith('sd'):
                        # Create disk entry
                        disk_name = disk.get('model', 'Unknown Drive')
                        disk_size = disk.get('size', 'Unknown')
                        disk_path = f"/dev/{disk['name']}"

                        # Try multiple methods to get drive name
                        display_name = self.get_drive_model_name(disk_path, disk['name'])

                        # Find hwinfo entry for this disk to get vendor info
                        hwinfo_name = None
                        for hw_disk in disks:
                            if hw_disk.get('path') == disk_path:
                                hwinfo_name = hw_disk.get('name', display_name)
                                break

                        display_name = hwinfo_name or display_name

                        # Process partitions
                        disk_partitions = []
                        for child in disk.get('children', []):
                            if child.get('type') == 'part':
                                part_size = child.get('size', 'Unknown')
                                part_name = child.get('name', 'Unknown')
                                mount_points = child.get('mountpoints', [])
                                if mount_points and mount_points[0]:
                                    mount_point = mount_points[0]
                                else:
                                    mount_point = "Not mounted"

                                enhanced_part_name = f"{part_name} ({part_size}) - {mount_point}"

                                disk_partitions.append({
                                    'name': part_name,
                                    'path': f"/dev/{part_name}",
                                    'enhanced_name': enhanced_part_name,
                                    'size': part_size,
                                    'mountpoint': mount_point,
                                    'original_category': 'block'
                                })

                        disk_entry = {
                            'name': display_name,
                            'path': disk_path,
                            'enhanced_name': f"{display_name} ({disk_size}) - {len(disk_partitions)} partitions",
                            'size': disk_size,
                            'is_disk': True,
                            'partitions': disk_partitions,
                            'original_category': 'block'
                        }

                        hierarchical_disks.append(disk_entry)

                # Replace block devices with hierarchical structure
                if hierarchical_disks:
                    self.hwinfo_devices['block'] = hierarchical_disks
                    print(f"Using lsblk detection: Found {len(hierarchical_disks)} disks")
                    return

        except Exception as e:
            print(f"Error with lsblk fallback: {e}")

        # Fallback to original hwinfo parsing if lsblk fails
        disk_devices = [d for d in disks if d.get('path', '').startswith('/dev/sd') and not d.get('path', '').endswith('1')]
        partition_devices = [d for d in disks if d.get('path', '').startswith('/dev/sd') and d.get('path', '')[-1:].isdigit()]

        hierarchical_disks = []

        for disk in disk_devices:
            disk_path = disk.get('path', '')
            disk_name = disk.get('name', 'Unknown Drive')

            disk_prefix = disk_path
            disk_partitions = []

            for partition in partition_devices:
                part_path = partition.get('path', '')
                if part_path.startswith(disk_path):
                    try:
                        result = subprocess.run(['lsblk', '-bno', 'SIZE,TYPE', part_path],
                                              capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            size_info = result.stdout.strip().split('\n')[0]
                            size_bytes = int(size_info.split()[0])
                            size_gb = size_bytes / (1024**3)

                            mount_result = subprocess.run(['lsblk', '-no', 'MOUNTPOINT', part_path],
                                                       capture_output=True, text=True, timeout=5)
                            mount_point = mount_result.stdout.strip() or "Not mounted"

                            part_name = f"{partition['name']} ({size_gb:.1f} GB) - {mount_point}"
                            partition['enhanced_name'] = part_name
                    except:
                        partition['enhanced_name'] = partition['name']

                    disk_partitions.append(partition)

            disk['enhanced_name'] = f"{disk_name} ({len(disk_partitions)} partitions)"
            disk['is_disk'] = True
            disk['partitions'] = disk_partitions
            hierarchical_disks.append(disk)

        if hierarchical_disks:
            self.hwinfo_devices['block'] = hierarchical_disks

    def filter_network_devices(self):
        """Filter network devices to show only physical network interfaces by default."""
        if 'net' not in self.hwinfo_devices:
            return

        network_devices = self.hwinfo_devices['net']
        filtered_devices = []

        # Virtual/hidden interface patterns to exclude
        virtual_patterns = [
            'lo',           # loopback
            'virbr',        # libvirt bridges
            'docker',       # docker bridges
            'br-',          # bridges
            'veth',         # virtual ethernet
            'tun',          # tunnel interfaces
            'tap',          # TAP interfaces
            'tailscale',    # VPN
            'wireguard',    # VPN
            'wg',           # WireGuard
            'pi',           # Pi-hole
            'utun',         # user tunnel
            'awdl',         # Apple Wireless Direct Link
            'llw',          # link-local wireless
            'anpi',         # Apple network
            'ipsec',        # IPsec tunnels
            'gif',          # generic tunnel interface
            'stf',          # 6to4 tunnel interface
            'ppp',          # PPP interfaces
            'sl',           # SLIP interfaces
            'plip',         # PLIP interfaces
            'dummy',        # dummy interfaces
            'bond',         # bonded interfaces (may want to show these)
            'team',         # team interfaces
            'vlan',         # VLAN interfaces (may want to show these)
        ]

        for device in network_devices:
            device_name = device.get('name', '').lower()
            device_path = device.get('path', '').lower()

            # Check if this is a virtual interface that should be hidden
            should_hide = False
            for pattern in virtual_patterns:
                if pattern in device_name or pattern in device_path:
                    should_hide = True
                    break

            # Show physical network interfaces and some important virtual ones
            if not should_hide:
                # Additional check: show wireless interfaces (usually start with wlan, wlp, etc.)
                if (device_name.startswith('wl') or
                    device_name.startswith('en') or
                    device_name.startswith('eth') or
                    device_name.startswith('wlan') or
                    'wireless' in device_name.lower() or
                    'ethernet' in device_name.lower() or
                    'wifi' in device_name.lower()):
                    filtered_devices.append(device)

        self.hwinfo_devices['net'] = filtered_devices
        print(f"Filtered network devices: {len(network_devices)} -> {len(filtered_devices)}")

    def detect_multimedia_devices(self):
        """Detect webcams and COM ports (serial devices) with device paths."""
        # Detect webcams (video devices)
        webcams = self.detect_webcams()
        if webcams:
            if 'webcams' not in self.hwinfo_devices:
                self.hwinfo_devices['webcams'] = []
            self.hwinfo_devices['webcams'].extend(webcams)
            print(f"Webcams detected: {len(webcams)}")

        # Detect COM ports (serial devices)
        com_ports = self.detect_com_ports()
        if com_ports:
            if 'com_ports' not in self.hwinfo_devices:
                self.hwinfo_devices['com_ports'] = []
            self.hwinfo_devices['com_ports'].extend(com_ports)
            print(f"COM ports detected: {len(com_ports)}")

    def detect_webcams(self):
        """Detect webcams using multiple methods."""
        webcams = []

        # Method 1: Check /dev/video* devices
        try:
            result = subprocess.run(['find', '/dev', '-name', 'video*', '-type', 'c'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                video_devices = result.stdout.strip().split('\n')
                for video_path in video_devices:
                    if video_path and os.path.exists(video_path):
                        device_name = os.path.basename(video_path)

                        # Get webcam info using lsusb
                        webcam_name = self.get_webcam_name_from_lsusb()
                        if webcam_name:
                            display_name = f"{webcam_name} ({device_name})"
                        else:
                            display_name = f"Webcam ({device_name})"

                        webcams.append({
                            'name': display_name,
                            'path': video_path,
                            'device_path': video_path,
                            'enhanced_name': display_name,
                            'original_category': 'webcams',
                            'is_webcam': True
                        })
        except Exception as e:
            print(f"Error detecting webcams: {e}")

        return webcams

    def detect_com_ports(self):
        """Detect COM ports (serial devices) with proper filtering."""
        com_ports = []

        # Method 1: Check /dev/ttyS* (traditional serial ports) - hide legacy ports by default
        # Modern systems rarely use these, so we'll skip them unless clearly needed
        # This prevents showing unused legacy COM1-COM8 ports on most systems
        pass

        # Method 2: Check /dev/ttyUSB* (USB serial adapters)
        try:
            result = subprocess.run(['find', '/dev', '-name', 'ttyUSB*', '-type', 'c'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                usb_serial_devices = result.stdout.strip().split('\n')
                for serial_path in usb_serial_devices:
                    if serial_path and os.path.exists(serial_path):
                        device_name = os.path.basename(serial_path)

                        # Get USB serial info
                        port_info = self.get_usb_serial_info(serial_path)

                        # Create proper display name using Linux device name
                        if port_info and port_info.strip():
                            # Port info already includes proper formatting
                            display_name = f"{device_name} {port_info}"
                        else:
                            display_name = device_name

                        com_ports.append({
                            'name': display_name,
                            'path': serial_path,
                            'device_path': serial_path,
                            'enhanced_name': display_name,
                            'original_category': 'com_ports',
                            'is_com_port': True,
                            'MODEL': display_name,  # Add MODEL to prevent "Unknown" prefix
                            'VENDOR': '',
                            'SYSNAME': device_name,
                            'DEVPATH': serial_path,
                            'CATEGORY': 'Serial Port'
                        })
        except Exception as e:
            print(f"Error detecting USB serial ports: {e}")

        return com_ports

    def get_webcam_name_from_lsusb(self):
        """Get webcam name from lsusb output."""
        try:
            result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if any(keyword in line.lower() for keyword in ['camera', 'webcam', 'cam', 'video']):
                        # Extract device name
                        if ':' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                desc_part = ':'.join(parts[2:]).strip()
                                # Clean up common webcam descriptions
                                desc_part = desc_part.replace('Webcam ', '').replace('Camera ', '')
                                return desc_part
        except Exception:
            pass
        return None

    def get_serial_port_info(self, device_path):
        """Get additional information about serial port."""
        try:
            # Try to get device info from udevadm
            result = subprocess.run(['udevadm', 'info', '--query=property', '--name', device_path],
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'ID_MODEL=' in line:
                        model = line.split('=')[1]
                        return f"- {model}"
                    elif 'ID_VENDOR=' in line:
                        vendor = line.split('=')[1]
                        return f"- {vendor}"
        except Exception:
            pass
        return ""

    def get_usb_serial_info(self, device_path):
        """Get information about USB serial adapter."""
        try:
            # Get USB device info
            result = subprocess.run(['udevadm', 'info', '--query=property', '--name', device_path],
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                vendor = ""
                model = ""
                for line in result.stdout.split('\n'):
                    if 'ID_VENDOR=' in line:
                        vendor = line.split('=')[1].replace('_', ' ')
                    elif 'ID_MODEL=' in line:
                        model = line.split('=')[1].replace('_', ' ')

                if vendor and model:
                    return f"- {vendor} {model}"
                elif vendor:
                    return f"- {vendor}"
                elif model:
                    return f"- {model}"
        except Exception:
            pass
        return ""

    def get_drive_model_name(self, disk_path, disk_name):
        """Get drive model name using multiple detection methods."""
        # Method 1: Try reading model from /sys/block/
        try:
            sys_name = disk_name.split('/')[-1]
            model_path = f"/sys/block/{sys_name}/device/model"
            if os.path.exists(model_path):
                with open(model_path, 'r') as f:
                    model = f.read().strip()
                    if model and model != 'Unknown':
                        return model
        except Exception:
            pass

        # Method 2: Try using lsblk with model flag
        try:
            result = subprocess.run(['lsblk', '-dno', 'MODEL', disk_path],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                model = result.stdout.strip()
                if model and model != '':
                    return model
        except Exception:
            pass

        # Method 3: Try using hdparm to get model info
        try:
            result = subprocess.run(['hdparm', '-I', disk_path],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout
                # Parse model from hdparm output
                for line in output.split('\n'):
                    if 'Model Number:' in line:
                        model = line.split('Model Number:')[1].strip()
                        if model:
                            return model
        except Exception:
            pass

        # Method 4: Try using smartctl to get model info
        try:
            result = subprocess.run(['smartctl', '-i', disk_path],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout
                # Parse model from smartctl output
                for line in output.split('\n'):
                    if 'Device Model:' in line:
                        model = line.split('Device Model:')[1].strip()
                        if model:
                            return model
                    elif 'Model:' in line:
                        model = line.split('Model:')[1].strip()
                        if model:
                            return model
        except Exception:
            pass

        # Method 5: Try reading from /dev/disk/by-id/
        try:
            disk_id_name = disk_name
            by_id_path = f"/dev/disk/by-id/"
            if os.path.exists(by_id_path):
                for file in os.listdir(by_id_path):
                    if file.startswith('ata-') and disk_id_name in os.path.realpath(f"{by_id_path}/{file}"):
                        # Extract model from ata- name
                        model_part = file[4:]  # Remove 'ata-'
                        model_part = model_part.split('_')[0] if '_' in model_part else model_part
                        if model_part and len(model_part) > 3:
                            return model_part.replace('-', ' ')
        except Exception:
            pass

        # Method 6: Try using udevadm info for device details
        try:
            result = subprocess.run(['udevadm', 'info', '--query=property', '--name', disk_path],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                output = result.stdout
                for line in output.split('\n'):
                    if 'ID_MODEL=' in line:
                        model = line.split('ID_MODEL=')[1].strip()
                        if model and model != '':
                            return model
                    elif 'ID_MODEL_ENC=' in line:
                        model = line.split('ID_MODEL_ENC=')[1].strip()
                        if model and model != '':
                            return model
        except Exception:
            pass

        # Method 7: Try using lshw for comprehensive hardware info
        try:
            result = subprocess.run(['lshw', '-class', 'disk', '-short'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout
                for line in output.split('\n'):
                    if disk_path in line or disk_name in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            # Extract model from lshw output
                            model = ' '.join(parts[2:])
                            if model and model != disk_name and len(model) > 3:
                                return model
        except Exception:
            pass

        # Method 8: Try reading from /sys/block directly with more paths
        try:
            sys_name = disk_name.split('/')[-1]
            # Try different paths that might contain model info
            model_paths = [
                f"/sys/block/{sys_name}/device/model",
                f"/sys/block/{sys_name}/device/vendor",
                f"/sys/block/{sys_name}/queue/rotational"
            ]

            for path in model_paths:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        content = f.read().strip()
                        if content and content != '0' and len(content) > 2:  # Skip "0" from rotational file
                            return content
        except Exception:
            pass

        # Method 9: Try using fdisk to identify disk
        try:
            result = subprocess.run(['fdisk', '-l', disk_path],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                output = result.stdout
                for line in output.split('\n'):
                    if 'Disk' in line and disk_path in line:
                        # Extract model from fdisk output line
                        parts = line.split(',')
                        if len(parts) > 1:
                            model_part = parts[0].replace('Disk', '').strip()
                            if model_part and len(model_part) > len(disk_path):
                                return model_part.split(disk_path)[1].strip()
        except Exception:
            pass

        # Method 10: Try using dmesg to find device identification
        try:
            result = subprocess.run(['dmesg', '|', 'grep', '-i', disk_name],
                                  capture_output=True, text=True, timeout=5, shell=True)
            if result.returncode == 0:
                output = result.stdout
                for line in output.split('\n'):
                    if any(keyword in line.lower() for keyword in ['model', 'vendor', 'samsung', 'hitachi', 'western', 'seagate', 'toshiba']):
                        # Extract potential model name
                        words = line.split()
                        for i, word in enumerate(words):
                            if word.lower() in ['model:', 'vendor:', 'model']:
                                if i + 1 < len(words):
                                    potential_model = words[i + 1]
                                    if len(potential_model) > 3:
                                        return potential_model
        except Exception:
            pass

        return f"{disk_name} Drive"  # Fallback

    def clean_network_device_name(self, device_name):
        """Clean up network device names from hwinfo output."""
        # Remove extra whitespace and clean up the name
        cleaned = device_name.strip()

        # If it looks like raw hwinfo output, try to extract just the interface name
        if 'network interface' in cleaned.lower() or 'network adapter' in cleaned.lower():
            # Extract just the interface name (first word before spaces)
            parts = cleaned.split()
            if parts:
                return parts[0]

        # Remove common suffixes
        suffixes_to_remove = ['network interface', 'network adapter', 'ethernet network interface', 'wireless adapter']
        for suffix in suffixes_to_remove:
            if cleaned.lower().endswith(suffix.lower()):
                cleaned = cleaned[:-len(suffix)].strip()

        # Clean up multiple spaces
        while '  ' in cleaned:
            cleaned = cleaned.replace('  ', ' ')

        return cleaned.strip()

    def get_network_device_name(self, device):
        """Get proper network device name using multiple detection methods."""
        interface_name = device.sys_name

        # Method 1: Try to get hardware info from ethtool
        try:
            result = subprocess.run(['ethtool', '-i', interface_name],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                output = result.stdout
                driver = ''
                for line in output.split('\n'):
                    if line.startswith('driver:'):
                        driver = line.split('driver:')[1].strip()
                    elif line.startswith('bus-info:'):
                        bus_info = line.split('bus-info:')[1].strip()
                        if driver and bus_info:
                            return f"{interface_name} ({driver} - {bus_info})"
        except Exception:
            pass

        # Method 2: Try to get device info from /sys/class/net/
        try:
            net_path = f"/sys/class/net/{interface_name}"
            if os.path.exists(net_path):
                # Read device info from sysfs
                uevent_path = f"{net_path}/device/uevent"
                if os.path.exists(uevent_path):
                    with open(uevent_path, 'r') as f:
                        content = f.read()
                        driver = ''
                        vendor = ''
                        device_name = ''

                        for line in content.split('\n'):
                            if line.startswith('DRIVER='):
                                driver = line.split('=')[1]
                            elif line.startswith('ID_VENDOR_FROM_DATABASE='):
                                vendor = line.split('=')[1].replace('_', ' ')
                            elif line.startswith('ID_MODEL_FROM_DATABASE='):
                                device_name = line.split('=')[1].replace('_', ' ')

                        if device_name and vendor:
                            return f"{device_name} ({interface_name})"
                        elif driver:
                            return f"{interface_name} ({driver})"
        except Exception:
            pass

        # Method 3: Try using lspci for network devices
        try:
            result = subprocess.run(['lspci', '-v'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout
                lines = output.split('\n')
                for i, line in enumerate(lines):
                    if interface_name in line.lower() or 'ethernet' in line.lower():
                        # Look for device name in surrounding lines
                        for j in range(max(0, i-3), min(len(lines), i+4)):
                            if lines[j].strip() and any(brand in lines[j] for brand in ['Intel', 'Realtek', 'Broadcom', 'Qualcomm', 'Atheros', 'Marvell']):
                                device_line = lines[j]
                                # Extract device name
                                if ':' in device_line:
                                    device_name = device_line.split(':')[-1].strip()
                                    if device_name and len(device_name) > 5:
                                        return f"{device_name} ({interface_name})"
        except Exception:
            pass

        # Method 4: Use hwinfo directly for network devices
        try:
            result = subprocess.run(['hwinfo', '--network'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout
                lines = output.split('\n')
                device_name = ''
                for i, line in enumerate(lines):
                    if interface_name in line:
                        # Look for device name in previous lines
                        for j in range(max(0, i-10), i):
                            if 'Model:' in lines[j]:
                                device_name = lines[j].split('Model:')[1].strip()
                                break
                            elif 'Device:' in lines[j] and 'Intel' in lines[j]:
                                device_name = lines[j].split('Device:')[1].strip()
                                break

                        if device_name:
                            return f"{device_name} ({interface_name})"
        except Exception:
            pass

        # Fallback: Just return the interface name
        return interface_name

    def create_mock_device_from_hwinfo(self, category, device_info):
        """Create a mock device object from hwinfo data for compatibility."""
        class MockDevice:
            def __init__(self, category, info):
                self.subsystem = category
                self.sys_name = device_info.get('path', f"{category}_{len(info.get('name', ''))}")
                self.NAME = device_info.get('enhanced_name', device_info['name'])
                self.device_path = device_info.get('path', f"/sys/class/{category}")
                self.info = info

            def get(self, key, default=''):
                # Map hwinfo data to standard udev attributes
                if key == 'ID_MODEL_FROM_DATABASE':
                    return self.info.get('enhanced_name', self.info['name'])
                elif key == 'ID_MODEL':
                    return self.info.get('enhanced_name', self.info['name'])
                elif key == 'ID_VENDOR_FROM_DATABASE':
                    # Extract vendor from device name
                    name = self.info.get('enhanced_name', self.info['name'])
                    for vendor in ['Intel', 'AMD', 'NVIDIA', 'ATI', 'Logitech', 'Dell', 'Samsung', 'Hitachi']:
                        if vendor.lower() in name.lower():
                            return vendor
                    return 'Unknown'
                elif key == 'ID_VENDOR':
                    return self.get('ID_VENDOR_FROM_DATABASE', 'Unknown')
                else:
                    return default

        return MockDevice(category, device_info)

    def detect_gpus(self):
        """Detect GPUs using only the most reliable method with filtering."""
        gpu_devices = []

        # Use inxi as the primary and only method - it's the most reliable
        gpu_devices.extend(self.detect_gpus_inxi())

        # Remove duplicates and filter to real GPUs only
        gpu_devices = self.filter_real_gpus(gpu_devices)

        # If we found GPUs, cache them for future use
        if gpu_devices:
            self.cached_gpu_devices = gpu_devices.copy()
        # If no GPUs found but we have cached ones, use the cache
        elif self.cached_gpu_devices:
            gpu_devices = self.cached_gpu_devices.copy()

        # Add debug output
        print(f"GPU Detection Results:")
        for i, gpu in enumerate(gpu_devices):
            vendor = getattr(gpu, 'VENDOR', 'Unknown')
            model = getattr(gpu, 'MODEL', 'Unknown')
            print(f"  GPU {i+1}: {vendor} {model}")
        print(f"Total GPUs detected: {len(gpu_devices)}")

        return gpu_devices

    def filter_real_gpus(self, gpu_devices):
        """Filter GPU list to show only real GPUs and remove duplicates."""
        real_gpus = []
        seen_models = set()

        for gpu in gpu_devices:
            vendor = getattr(gpu, 'VENDOR', '').upper()
            model = getattr(gpu, 'MODEL', '').upper()

            # Skip non-GPU devices
            if 'WEBCAM' in model or 'CAMERA' in model or 'USB' in model:
                continue

            # Skip generic entries
            if 'UNKNOWN' in vendor or len(vendor) < 2:
                continue

            # Skip if model is too generic
            if 'UNKNOWN' in model or len(model) < 5:
                continue

            # Create a unique identifier for deduplication
            gpu_id = f"{vendor}_{model}".replace(' ', '_').upper()

            if gpu_id not in seen_models:
                seen_models.add(gpu_id)
                real_gpus.append(gpu)

        return real_gpus

    def find_pci_parent(self, device):
        """Find PCI parent path for a device."""
        try:
            current = device
            while hasattr(current, 'parent') and getattr(current, 'parent', None):
                if current.subsystem == 'pci':
                    return current
                current = getattr(current, 'parent', None)
        except Exception:
            pass
        return None

    def is_graphics_device(self, pci_device):
        """Check if PCI device is a graphics controller."""
        # Check PCI class
        pci_class = pci_device.get('PCI_CLASS')
        if pci_class and pci_class.startswith('03'):  # 0x03 = Display controller class
            return True

        # Check device name for GPU manufacturers
        dev_name = str(pci_device.get('ID_MODEL_FROM_DATABASE', '')).lower()
        if any(gpu_term in dev_name for gpu_term in ['nvidia', 'geforce', 'radeon', 'radeon', 'intel', 'ati', 'amd', 'radeon']):
            return True

        return False

    def get_gpu_info_from_pci(self, pci_device):
        """Extract GPU information from PCI device."""
        gpu_info = {}
        try:
            vendor = pci_device.get('ID_VENDOR_FROM_DATABASE', 'Unknown')
            model = pci_device.get('ID_MODEL_FROM_DATABASE', 'Unknown GPU')

            # Clean up GPU names
            if 'corporation' in vendor.lower():
                vendor = vendor.replace('Corporation', '').strip()
            if 'inc.' in vendor.lower():
                vendor = vendor.replace('Inc.', '').strip()

            gpu_info['VENDOR'] = vendor
            gpu_info['MODEL'] = model
            gpu_info['DEVPATH'] = pci_device.device_path
            gpu_info['SUBSYSTEM'] = 'graphics'
            gpu_info['ID_VENDOR_ID'] = pci_device.get('ID_VENDOR_ID', '')
            gpu_info['ID_MODEL_ID'] = pci_device.get('ID_MODEL_ID', '')
            return gpu_info
        except Exception:
            return None

    def create_gpu_device_from_pci(self, pci_device):
        """Create a GPU device object from PCI device."""
        gpu_info = self.get_gpu_info_from_pci(pci_device)
        if not gpu_info:
            return None

        return type('GPUPCIDevice', (), {
            'subsystem': 'graphics',
            'sys_name': f"gpu_{pci_device.sys_name}",
            'device_path': pci_device.device_path,
            'properties': pci_device.properties,
            'get': pci_device.get,
            **gpu_info
        })()

    def detect_gpus_system_commands(self):
        """GPU detection using reliable system commands."""
        gpu_devices = []

        # Method 1: Use inxi - it's the most reliable
        gpu_devices.extend(self.detect_gpus_inxi())

        # Method 2: Use lshw if inxi fails
        if not gpu_devices:
            gpu_devices.extend(self.detect_gpus_lshw())

        # Method 3: Fallback to lspci
        if not gpu_devices:
            gpu_devices.extend(self.detect_gpus_lspci())

        return gpu_devices

    def detect_gpus_inxi(self):
        """Detect GPUs using inxi command."""
        gpu_devices = []

        try:
            result = subprocess.run(['inxi', '-G'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Strip ANSI color codes from inxi output
                import re
                clean_output = re.sub(r'\x1f|\x1b\[[0-9;]*m', '', result.stdout)
                lines = clean_output.split('\n')
                current_gpu = {}

                for line in lines:
                    line = line.strip()

                    # Detect GPU devices (exclude webcams and other devices)
                    if 'Device-' in line:
                        if current_gpu and 'vendor' in current_gpu and 'model' in current_gpu and current_gpu.get('has_driver', False):
                            # Create GPU device from previous GPU
                            gpu_device = self.create_gpu_device(current_gpu, f"inxi_{len(gpu_devices)}")
                            gpu_devices.append(gpu_device)

                        current_gpu = {}

                        # Skip webcams and other non-GPU devices
                        if 'Webcam' in line or 'Camera' in line or 'type USB' in line:
                            continue

                        # Extract GPU info from inxi line
                        if 'Intel' in line:
                            current_gpu['vendor'] = 'Intel'
                            current_gpu['model'] = self.extract_intel_gpu_model(line)
                        elif 'AMD' in line or 'Radeon' in line or 'Ellesmere' in line:
                            current_gpu['vendor'] = 'AMD'
                            current_gpu['model'] = self.extract_amd_gpu_model(line)
                        elif 'NVIDIA' in line:
                            current_gpu['vendor'] = 'NVIDIA'
                            current_gpu['model'] = self.extract_nvidia_gpu_model(line)
                        elif 'Nvidia' in line:
                            current_gpu['vendor'] = 'NVIDIA'
                            current_gpu['model'] = self.extract_nvidia_gpu_model(line)

                    # Handle driver info that comes on the next line (indented)
                    elif line.strip().startswith('driver:') and current_gpu:
                        # This confirms it's a real GPU device with a driver
                        current_gpu['has_driver'] = True

                # Add the last GPU if there is one
                if current_gpu and 'vendor' in current_gpu and 'model' in current_gpu and current_gpu.get('has_driver', False):
                    gpu_device = self.create_gpu_device(current_gpu, f"inxi_{len(gpu_devices)}")
                    gpu_devices.append(gpu_device)

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"inxi detection error: {e}")

        return gpu_devices

    def detect_gpus_lshw(self):
        """Detect GPUs using lshw command."""
        gpu_devices = []

        try:
            result = subprocess.run(['lshw', '-c', 'display'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                current_gpu = {}

                for line in result.stdout.split('\n'):
                    line = line.strip()

                    if line.startswith('*-display'):
                        if current_gpu and 'vendor' in current_gpu and 'model' in current_gpu:
                            gpu_device = self.create_gpu_device(current_gpu, f"lshw_{len(gpu_devices)}")
                            gpu_devices.append(gpu_device)
                        current_gpu = {}
                    elif line.startswith('vendor:'):
                        vendor = line.split(':', 1)[1].strip()
                        if 'Intel' in vendor:
                            current_gpu['vendor'] = 'Intel'
                        elif 'Advanced Micro Devices' in vendor or 'AMD' in vendor or 'ATI' in vendor:
                            current_gpu['vendor'] = 'AMD'
                        elif 'NVIDIA' in vendor or 'Nvidia' in vendor:
                            current_gpu['vendor'] = 'NVIDIA'
                        else:
                            current_gpu['vendor'] = vendor
                    elif line.startswith('product:'):
                        current_gpu['model'] = line.split(':', 1)[1].strip()

                # Add the last GPU if there is one
                if current_gpu and 'vendor' in current_gpu and 'model' in current_gpu:
                    gpu_device = self.create_gpu_device(current_gpu, f"lshw_{len(gpu_devices)}")
                    gpu_devices.append(gpu_device)

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"lshw detection error: {e}")

        return gpu_devices

    def detect_gpus_lspci(self):
        """Detect GPUs using lspci command."""
        gpu_devices = []

        try:
            result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'VGA' in line or 'Display' in line or '3D' in line:
                        self.parse_gpu_from_lspci(line, gpu_devices)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"lspci detection error: {e}")

        return gpu_devices

    def extract_intel_gpu_model(self, line):
        """Extract Intel GPU model from inxi output."""
        if 'Intel' in line:
            # Extract everything between Intel and 'driver'
            parts = line.split('Intel')
            if len(parts) > 1:
                gpu_part = parts[1]
                if 'driver' in gpu_part:
                    model = gpu_part.split('driver')[0].strip()
                else:
                    model = gpu_part.strip()
                # Clean up common Intel naming
                return model.replace('Corporation', '').replace('Inc.', '').strip()
        return "Intel Graphics"

    def extract_amd_gpu_model(self, line):
        """Extract AMD GPU model from inxi output."""
        # Handle specific GPU model from this system
        if 'Ellesmere' in line:
            return 'Radeon RX 470/480/570/580/590'

        if 'Radeon' in line:
            # Extract Radeon model name
            if '[' in line and ']' in line:
                # Extract from brackets [AMD/ATI] ModelName
                bracket_start = line.find('[')
                bracket_end = line.find(']')
                if bracket_start != -1 and bracket_end != -1:
                    inside_brackets = line[bracket_start+1:bracket_end]
                    if 'AMD' in inside_brackets:
                        model_part = line[bracket_end+1:].strip()
                        # Clean up the model name
                        model_part = model_part.split('driver')[0].strip()
                        return model_part.replace('Corporation', '').strip()

        # Fallback: extract AMD/ATI model
        if 'AMD' in line and 'driver' in line:
            amd_start = line.find('AMD')
            if amd_start != -1:
                after_amd = line[amd_start:]
                model_part = after_amd.split('driver')[0].strip()
                return model_part.replace('Corporation', '').replace('Inc.', '').strip()
        elif 'ATI' in line and 'driver' in line:
            ati_start = line.find('ATI')
            if ati_start != -1:
                after_ati = line[ati_start:]
                model_part = after_ati.split('driver')[0].strip()
                return model_part.replace('Technologies', '').replace('Inc.', '').strip()

        return "AMD Graphics"

    def extract_nvidia_gpu_model(self, line):
        """Extract NVIDIA GPU model from inxi output."""
        if 'NVIDIA' in line or 'Nvidia' in line:
            # Extract everything after NVIDIA/Nvidia until 'driver'
            nvidia_start = line.find('NVIDIA')
            if nvidia_start == -1:
                nvidia_start = line.find('Nvidia')

            if nvidia_start != -1:
                gpu_part = line[nvidia_start:]
                if 'driver' in gpu_part:
                    model = gpu_part.split('driver')[0].strip()
                else:
                    model = gpu_part.strip()
                return model.replace('Corporation', '').replace('Inc.', '').strip()

        return "NVIDIA Graphics"

    def create_gpu_device(self, gpu_info, sys_prefix):
        """Create a GPU device object from GPU information."""
        vendor = gpu_info.get('vendor', 'Unknown')
        model = gpu_info.get('model', 'Unknown GPU')

        # Create a clean sys_name based on vendor and model
        clean_model = model.replace(' ', '_').replace('-', '_').replace('/', '_')[:20]
        sys_name = f"gpu_{vendor.lower()}_{clean_model}"

        return type('SystemGPU', (), {
            'subsystem': 'graphics',
            'sys_name': sys_name,
            'device_path': f"/sys/class/drm/{vendor.lower()}",
            'VENDOR': vendor,
            'MODEL': model,
            'CATEGORY': 'Display adapters',
            'get': lambda self, k, default='': {
                'VENDOR': vendor,
                'MODEL': model,
                'DEVPATH': f"/sys/class/drm/{vendor.lower()}",
                'SUBSYSTEM': 'graphics',
                'CATEGORY': 'Display adapters'
            }.get(k, default)
        })()

    def parse_gpu_from_lspci(self, lspci_line, gpu_devices):
        """Parse GPU information from lspci output."""
        try:
            parts = lspci_line.split(':')
            if len(parts) >= 3:
                address = parts[0].strip()
                rest = ':'.join(parts[1:]).strip()

                # Extract vendor and model
                vendor = 'Unknown'
                model = rest

                # Known GPU vendor detection
                if 'Intel' in rest:
                    vendor = 'Intel'
                    # Extract Intel GPU model name
                    if 'Corporation' in rest:
                        model_parts = rest.split('Corporation')
                        if len(model_parts) > 1:
                            model = model_parts[1].strip()
                elif 'NVIDIA' in rest or 'nVidia' in rest:
                    vendor = 'NVIDIA'
                    if 'Corporation' in rest:
                        model_parts = rest.split('Corporation')
                        if len(model_parts) > 1:
                            model = model_parts[1].strip()
                elif 'Advanced Micro Devices' in rest or 'AMD' in rest or 'Radeon' in rest:
                    vendor = 'AMD'
                    if 'Advanced Micro Devices' in rest:
                        model_parts = rest.split('Advanced Micro Devices')
                        if len(model_parts) > 1:
                            model = model_parts[1].strip()
                    elif '[' in rest and ']' in rest:
                        model = rest.split('[')[0].strip()

                # Clean up model name
                if 'Corporation' in model:
                    model = model.replace('Corporation', '').strip()
                if 'Inc.' in model:
                    model = model.replace('Inc.', '').strip()

                # Create GPU device
                gpu_device = type('LSPCIGPU', (), {
                    'subsystem': 'graphics',
                    'sys_name': f"pci_{address.replace(':', '_')}",
                    'device_path': f"/sys/bus/pci/devices/{address}",
                    'VENDOR': vendor,
                    'MODEL': model,
                    'get': lambda self, k, default='': {'MODEL': model, 'VENDOR': vendor, 'DEVPATH': f"/sys/bus/pci/devices/{address}"}.get(k, default)
                })()
                gpu_devices.append(gpu_device)

        except Exception as e:
            print(f"Error parsing lspci line: {e}")

    def create_category_icon(self, icon_name, subsystem):
        """Create icon for category with proper fallbacks"""
        # Try theme icon first
        icon = QIcon.fromTheme(icon_name)

        if icon.isNull():
            # Use subsystem-specific standard icons as fallbacks
            subsystem_map = {
                'net': QStyle.SP_ComputerIcon,
                'sound': QStyle.SP_DesktopIcon,
                'block': QStyle.SP_DriveHDIcon,
                'usb': QStyle.SP_DriveCDIcon,
                'input': QStyle.SP_ComputerIcon,
                'hid': QStyle.SP_ComputerIcon,
                'video4linux': QStyle.SP_FileDialogDetailedView,
                'graphics': QStyle.SP_DesktopIcon,
                'drm': QStyle.SP_DesktopIcon,
                'bluetooth': QStyle.SP_ComputerIcon,
                'printer': QStyle.SP_FileDialogDetailedView,
                'pci': QStyle.SP_ComputerIcon,
                'scsi': QStyle.SP_DriveHDIcon,
                'thermal': QStyle.SP_FileDialogDetailedView,
            }

            standard_icon = subsystem_map.get(subsystem, QStyle.SP_DirIcon)
            icon = self.style().standardIcon(standard_icon)

        return icon

    def add_device_to_tree(self, device, parent_item, category):
        """Add a device to the tree widget"""
        # Initialize variables
        vendor = ''
        model = ''

        # Special handling for COM ports - use the pre-formatted name
        if hasattr(device, 'info') and device.info.get('is_com_port'):
            display_name = device.info.get('name', device.sys_name)
        else:
            # Initialize variables
            model = device.get('ID_MODEL_FROM_DATABASE') or device.get('ID_MODEL') or device.sys_name
            vendor = device.get('ID_VENDOR_FROM_DATABASE') or device.get('ID_VENDOR') or ''

            # Special handling for network devices
            if hasattr(device, 'subsystem') and device.subsystem == 'net':
                display_name = self.get_network_device_name(device)
            # Special handling for HID devices with USB IDs
            elif hasattr(device, 'subsystem') and device.subsystem == 'hid' and ':' in device.sys_name:
                display_name = self.get_usb_hid_device_name(device.sys_name)
            else:
                # Clean up names and handle special cases
                if model:
                    # Special handling for network interfaces
                    if category == "Network adapters":
                        model = self.clean_network_device_name(model)
                    else:
                        model = model.replace('_', ' ').title()
                if vendor:
                    vendor = vendor.replace('_', ' ').title()

                # Create display name - don't truncate unnecessarily
                if vendor and model and not model.startswith(vendor):
                    display_name = f"{vendor} {model}"
                else:
                    display_name = model

        # Don't truncate display name - let the tree widget handle it
        # Create tree item with proper icon
        item = QTreeWidgetItem(parent_item)
        item.setText(0, display_name)

        # Set tooltip with full name for reference
        item.setToolTip(0, display_name)

        # Get appropriate device icon
        device_icon = self.get_device_icon(device)
        item.setIcon(0, device_icon)

        # Store device data
        device_data = {
            'MODEL': display_name,
            'VENDOR': vendor,
            'VENDOR_ENC': device.get('ID_VENDOR_ENC', vendor),
            'SUBSYSTEM': device.subsystem,
            'DEVPATH': device.device_path,
            'CATEGORY': category,
            'SYSNAME': device.sys_name,
            'DEVTYPE': device.get('DEVTYPE', ''),
            'ID_VENDOR_ID': device.get('ID_VENDOR_ID', ''),
            'ID_MODEL_ID': device.get('ID_MODEL_ID', '')
        }

        item.setData(0, Qt.UserRole, device_data)

        return item

    def show_context_menu(self, position):
        """Show context menu for device items."""
        item = self.tree.itemAt(position)
        if not item:
            return

        # Create context menu
        context_menu = QMenu(self)

        # Add copy actions
        copy_name_action = QAction("Copy Name", self)
        copy_name_action.triggered.connect(lambda: self.copy_device_info(item, 'name'))
        context_menu.addAction(copy_name_action)

        copy_details_action = QAction("Copy Details", self)
        copy_details_action.triggered.connect(lambda: self.copy_device_info(item, 'details'))
        context_menu.addAction(copy_details_action)

        # Add separator
        context_menu.addSeparator()

        # Add device actions
        properties_action = QAction("Properties", self)
        properties_action.triggered.connect(lambda: self.show_properties(item, 0))
        context_menu.addAction(properties_action)

        # Show menu
        context_menu.exec(self.tree.mapToGlobal(position))

    def copy_device_info(self, item, info_type):
        """Copy device information to clipboard."""
        device_data = item.data(0, Qt.UserRole)
        if not device_data:
            return

        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()

        if info_type == 'name':
            # Copy just the device name
            device_name = item.text(0)
            clipboard.setText(device_name)
        elif info_type == 'details':
            # Copy detailed device information
            details = []
            details.append(f"Device: {device_data.get('MODEL', 'Unknown')}")
            details.append(f"Vendor: {device_data.get('VENDOR', 'Unknown')}")
            details.append(f"Category: {device_data.get('CATEGORY', 'Unknown')}")
            details.append(f"Subsystem: {device_data.get('SUBSYSTEM', 'Unknown')}")
            details.append(f"Device Path: {device_data.get('DEVPATH', 'Unknown')}")
            details.append(f"SysFS Name: {device_data.get('SYSNAME', 'Unknown')}")
            details.append(f"Device Type: {device_data.get('DEVTYPE', 'Unknown')}")
            details.append(f"Vendor ID: {device_data.get('ID_VENDOR_ID', 'Unknown')}")
            details.append(f"Model ID: {device_data.get('ID_MODEL_ID', 'Unknown')}")

            details_text = '\n'.join(details)
            clipboard.setText(details_text)

    def refresh_usb_device_info(self):
        """Parse lsusb output to get accurate USB device names and types."""
        try:
            result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.usb_devices_info = {}
                for line in result.stdout.strip().split('\n'):
                    # Parse lines like: "Bus 001 Device 003: ID 046d:c077 Logitech, Inc. Mouse"
                    if 'ID ' in line:
                        id_part = line.split('ID ')[1].split()[0]  # 046d:c077
                        description = ' '.join(line.split('ID ')[1].split()[2:])  # Logitech, Inc. Mouse

                        vendor_hex, product_hex = id_part.lower().split(':')
                        self.usb_devices_info[f"{vendor_hex}:{product_hex}"] = {
                            'description': description,
                            'vendor_hex': vendor_hex,
                            'product_hex': product_hex,
                            'is_keyboard': 'keyboard' in description.lower() or 'kbd' in description.lower(),
                            'is_mouse': 'mouse' in description.lower() or 'track' in description.lower()
                        }
        except Exception as e:
            print(f"Error parsing lsusb: {e}")
            self.usb_devices_info = {}

    def get_usb_hid_device_name(self, device_id):
        """Get device name from USB database using lsusb data."""
        try:
            # Parse device ID like "0003:046D:C077.0001"
            parts = device_id.split(':')
            if len(parts) >= 3:
                vendor_hex = parts[1].lower()
                product_hex = parts[2].split('.')[0].lower()
                device_key = f"{vendor_hex}:{product_hex}"

                # Look up in our USB device cache from lsusb
                if device_key in self.usb_devices_info:
                    return self.usb_devices_info[device_key]['description']

                # Fallback to generic naming
                return f"USB Input Device ({vendor_hex}:{product_hex})"
        except:
            pass

        return "USB Input Device"

    def get_device_icon(self, device):
        """Get appropriate icon for device"""
        subsystem = device.subsystem

        # Map subsystems to standard Qt icons - using only basic guaranteed icons
        subsystem_icon_map = {
            'net': QStyle.SP_ComputerIcon,
            'sound': QStyle.SP_DesktopIcon,
            'block': QStyle.SP_DriveHDIcon,
            'usb': QStyle.SP_DriveCDIcon,
            'input': QStyle.SP_ComputerIcon,
            'hid': QStyle.SP_ComputerIcon,
            'video4linux': QStyle.SP_FileDialogDetailedView,
            'graphics': QStyle.SP_DesktopIcon,
            'drm': QStyle.SP_DesktopIcon,
            'bluetooth': QStyle.SP_ComputerIcon,
            'printer': QStyle.SP_FileDialogDetailedView,
            'pci': QStyle.SP_ComputerIcon,
            'scsi': QStyle.SP_DriveHDIcon,
            'thermal': QStyle.SP_FileDialogDetailedView,
        }

        standard_icon = subsystem_icon_map.get(subsystem, QStyle.SP_FileIcon)
        return self.style().standardIcon(standard_icon)

    def show_properties(self, item, column):
        """Show properties dialog for selected device"""
        # Only show for leaf nodes (actual devices)
        if item.childCount() > 0 or item == self.root_item:
            return

        device_data = item.data(0, Qt.UserRole)
        icon = item.icon(0)

        if device_data:
            dialog = PropertiesDialog(device_data, icon, self)
            dialog.exec()

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Device Manager",
                         "Windows Device Manager Clone\n\n"
                         "A Linux implementation of the Windows Device Manager\n"
                         "using PySide6 and udev for device enumeration.\n\n"
                         "Provides real-time device monitoring and management.")

def main():
    """
    LinMan - Linux Device Manager
    A comprehensive device manager for Linux systems with Windows Device Manager-like interface
    """
    # Create application
    app = QApplication(sys.argv)

    # Try to use Windows-like style
    try:
        style_found = False
        for style_name in QStyleFactory.keys():
            if "windows" in style_name.lower():
                app.setStyle(style_name)
                style_found = True
                break
        if not style_found and "fusion" in QStyleFactory.keys():
            app.setStyle("fusion")
    except:
        pass

    # Set Dark Theme application stylesheet for proper contrast
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2d2d30;
            color: #ffffff;
        }

        /* Menu Bar */
        QMenuBar {
            background-color: #2d2d30;
            color: #ffffff;
            border-bottom: 1px solid #3f3f46;
            padding: 2px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
        }
        QMenuBar::item {
            padding: 5px 12px;
            background-color: transparent;
            border-radius: 3px;
            color: #ffffff;
        }
        QMenuBar::item:selected {
            background-color: #0078d4;
            color: white;
        }

        /* Menu */
        QMenu {
            background-color: #2d2d30;
            color: #ffffff;
            border: 1px solid #3f3f46;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            padding: 3px;
        }
        QMenu::item {
            padding: 8px 20px 8px 25px;
            border-radius: 3px;
            color: #ffffff;
        }
        QMenu::item:selected {
            background-color: #0078d4;
            color: white;
        }
        QMenu::separator {
            height: 1px;
            background-color: #3f3f46;
            margin: 4px 8px;
        }

        /* Group Box */
        QGroupBox {
            font-weight: bold;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 12px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            background-color: #2d2d30;
            color: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background-color: #2d2d30;
            color: #ffffff;
            font-size: 11pt;
        }

        /* Push Button */
        QPushButton {
            background-color: #3f3f46;
            border: 1px solid #5a5a5a;
            color: #ffffff;
            padding: 8px 18px;
            border-radius: 3px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            min-height: 28px;
        }
        QPushButton:hover {
            background-color: #0078d4;
            border: 1px solid #0078d4;
            color: white;
        }
        QPushButton:pressed {
            background-color: #005a9e;
            border: 1px solid #005a9e;
            color: white;
        }
        QPushButton:default {
            background-color: #0078d4;
            color: white;
            border: 1px solid #0078d4;
        }
        QPushButton:default:hover {
            background-color: #106ebe;
            border: 1px solid #106ebe;
            color: white;
        }

        /* Label */
        QLabel {
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            color: #ffffff;
            background-color: transparent;
        }

        /* Line Edit */
        QLineEdit {
            border: 1px solid #3f3f46;
            color: #ffffff;
            padding: 6px 8px;
            border-radius: 3px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            background-color: #1e1e1e;
        }
        QLineEdit:focus {
            border: 1px solid #0078d4;
        }

        /* Text Edit */
        QTextEdit {
            border: 1px solid #3f3f46;
            color: #ffffff;
            border-radius: 3px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            background-color: #1e1e1e;
            padding: 6px;
        }
        QTextEdit:focus {
            border: 1px solid #0078d4;
        }

        /* Combo Box */
        QComboBox {
            border: 1px solid #3f3f46;
            color: #ffffff;
            padding: 6px 8px;
            border-radius: 3px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            background-color: #1e1e1e;
            min-width: 80px;
        }
        QComboBox:focus {
            border: 1px solid #0078d4;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
            background-color: #3f3f46;
        }
        QComboBox::down-arrow {
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDFMNiA2TDExIDFaIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMS41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
        }
        QComboBox QAbstractItemView {
            border: 1px solid #3f3f46;
            background-color: #1e1e1e;
            color: #ffffff;
            selection-background-color: #0078d4;
            selection-color: white;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
        }

        /* Table Widget */
        QTableWidget {
            border: 1px solid #3f3f46;
            background-color: #1e1e1e;
            color: #ffffff;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            gridline-color: #3f3f46;
        }
        QTableWidget::item {
            padding: 6px 8px;
            color: #ffffff;
            background-color: #1e1e1e;
        }
        QTableWidget::item:selected {
            background-color: #0078d4;
            color: white;
        }
        QHeaderView::section {
            background-color: #2d2d30;
            color: #ffffff;
            border: 1px solid #3f3f46;
            padding: 6px 8px;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11pt;
            font-weight: bold;
        }
    """)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()