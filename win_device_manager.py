"""
LinMan - Linux Device Manager (Deep Inspection Edition)
A standalone device manager for hardware diagnostics.

Dependencies:
    pip install PySide6 pyudev

Features:
- Monitors: Native EDID parsing (reads /sys/class/drm/.../edid) for real model names
- RAM: Reads individual sticks via DMI (requires root/pkexec)
- Webcams: Uses V4L product names
- Native Look & Feel
- "Yellow Bang" (!) Icon logic
- Root Actions via pkexec

"""

import sys
import socket
import os
import re
import subprocess
import shutil
import struct
from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
                               QMessageBox, QVBoxLayout, QWidget, QDialog, QLabel,
                               QFormLayout, QToolBar, QStyle, QTabWidget, QGroupBox,
                               QLineEdit, QTextEdit, QFrame, QStyleFactory, QMenu,
                               QDialogButtonBox, QHBoxLayout, QPushButton, QComboBox,
                               QHeaderView)
from PySide6.QtCore import Qt, QSize, QSocketNotifier, Slot, QTimer
from PySide6.QtGui import QIcon, QAction, QFont, QPalette, QColor, QPainter, QPixmap

import pyudev

# --- CONFIGURATION ---
GITHUB_URL = "https://github.com/your_username/LinMan_Project"
VERSION = "1.2.0"

# --- Backend: EDID Parser (Monitors) ---
class EdidParser:
    @staticmethod
    def get_monitor_name(sys_path):
        edid_path = os.path.join(sys_path, "edid")
        if not os.path.exists(edid_path): return None

        try:
            with open(edid_path, 'rb') as f:
                edid = f.read()

            if len(edid) < 128: return None

            # Walk through the 4 descriptors in the EDID block
            # Descriptors start at byte 54, 72, 90, 108
            for i in [54, 72, 90, 108]:
                # Monitor Name tag is 0xFC, header is 00 00 00 FC 00
                if edid[i:i+4] == b'\x00\x00\x00\xfc':
                    # Text usually ends with \n (0x0a)
                    text = edid[i+5:i+18].decode('cp437', 'ignore').split('\x0a')[0]
                    return text.strip()
        except: pass
        return None

# --- Backend: DMI Parser (RAM) ---
class DmiParser:
    @staticmethod
    def get_ram_modules():
        """Runs dmidecode to get RAM info. Requires Root."""
        modules = []
        try:
            # Try running without pkexec first (in case we are already root)
            cmd = ['dmidecode', '-t', '17']
            if os.geteuid() != 0:
                cmd = ['pkexec'] + cmd

            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8')

            current_stick = {}
            for line in output.splitlines():
                line = line.strip()
                if "Memory Device" in line:
                    if current_stick: modules.append(current_stick)
                    current_stick = {'Name': 'Unknown RAM', 'Size': 'Unknown', 'Type': 'Unknown', 'Speed': 'Unknown'}
                elif not current_stick:
                    continue

                if ":" in line:
                    k, v = [x.strip() for x in line.split(':', 1)]
                    if k == "Size": current_stick['Size'] = v
                    elif k == "Type": current_stick['Type'] = v
                    elif k == "Speed": current_stick['Speed'] = v
                    elif k == "Manufacturer": current_stick['Manufacturer'] = v
                    elif k == "Part Number": current_stick['Part'] = v
                    elif k == "Locator": current_stick['Slot'] = v

            if current_stick: modules.append(current_stick)

        except:
            # Fallback if user denies root or tool missing
            pass

        return modules

# --- Backend: Native System Resolver ---
class SystemResolver:
    def __init__(self):
        self.has_lspci = shutil.which('lspci') is not None
        self.pci_cache = {}

    def get_pci_name(self, pci_slot_name):
        if not self.has_lspci or not pci_slot_name: return None, None
        if pci_slot_name in self.pci_cache: return self.pci_cache[pci_slot_name]

        try:
            output = subprocess.check_output(
                ['lspci', '-s', pci_slot_name, '-vmm'],
                stderr=subprocess.DEVNULL
            ).decode('utf-8')

            vendor = None
            device = None
            for line in output.splitlines():
                if line.startswith('Vendor:'): vendor = line.split(':', 1)[1].strip()
                elif line.startswith('Device:'): device = line.split(':', 1)[1].strip()

            self.pci_cache[pci_slot_name] = (vendor, device)
            return vendor, device
        except: return None, None

# --- Helper: Icon Factory ---
class IconFactory:
    @staticmethod
    def get(name_list, fallback_style_standard):
        for name in name_list:
            if QIcon.hasThemeIcon(name): return QIcon.fromTheme(name)
        return QApplication.style().standardIcon(fallback_style_standard)

    @staticmethod
    def apply_overlay(base_icon, mode='normal'):
        pixmap = base_icon.pixmap(32, 32)
        target = QPixmap(pixmap.size())
        target.fill(Qt.transparent)

        painter = QPainter(target)

        if mode == 'ghost':
            painter.setOpacity(0.5)
            painter.drawPixmap(0, 0, pixmap)
        else:
            painter.drawPixmap(0, 0, pixmap)

        if mode == 'warning':
            warn_icon = QApplication.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(16, 16)
            painter.drawPixmap(16, 16, warn_icon)

        painter.end()
        return QIcon(target)

# --- UI: Properties Dialog ---
class PropertiesDialog(QDialog):
    def __init__(self, device_data, icon, parent=None):
        super().__init__(parent)
        self.device_data = device_data
        self.icon = icon
        self.setWindowTitle(f"Properties: {self.device_data.get('MODEL')}")
        self.setMinimumSize(600, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(self.icon.pixmap(64, 64))
        name_text = self.device_data.get('MODEL', 'Unknown Device')
        name_label = QLabel(f"<b>{name_text}</b>")
        name_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        name_label.setWordWrap(True)
        header_layout.addWidget(icon_label)
        header_layout.addWidget(name_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_general_tab(), "General")
        self.tabs.addTab(self.create_driver_tab(), "Driver")
        self.tabs.addTab(self.create_details_tab(), "Details")
        layout.addWidget(self.tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def create_general_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        info_group = QGroupBox("Device Information")
        info_layout = QFormLayout()

        info_layout.addRow("Device Type:", QLabel(self.device_data.get('CATEGORY', 'Unknown')))
        info_layout.addRow("Manufacturer:", QLabel(self.device_data.get('VENDOR', 'Unknown')))
        info_layout.addRow("Location:", QLabel(os.path.basename(self.device_data.get('SYS_PATH', 'Unknown'))))

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        status_group = QGroupBox("Device Status")
        status_layout = QVBoxLayout()
        status_text = QTextEdit()

        driver = self.device_data.get('DRIVER')
        is_hidden = self.device_data.get('IS_HIDDEN', False)
        is_physical = self.device_data.get('IS_PHYSICAL', True)

        msg = []

        if not is_physical:
             msg.append("This is a Virtual/System device.")
             if is_hidden: msg.append("It is hidden by default.")
        elif is_hidden:
            msg.append("This device is currently disconnected or hidden.")

        if driver:
            msg.append("This device is working properly.")
            msg.append(f"Driver loaded: {driver}")
        elif is_physical and not driver:
            msg.append("The drivers for this device are not installed. (Code 28)")
            msg.append("No kernel module is currently bound to this hardware.")
        else:
            msg.append("No driver required.")

        status_text.setPlainText("\n".join(msg))
        status_text.setReadOnly(True)
        status_text.setMaximumHeight(100)
        status_text.setStyleSheet("border: 1px solid palette(mid);")
        status_layout.addWidget(status_text)
        status_group.setLayout(status_layout)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_driver_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        driver_group = QGroupBox("Driver")
        driver_layout = QFormLayout()
        driver_name = self.device_data.get('DRIVER', 'None')

        clean_driver_name = driver_name.split(' ')[0] if driver_name else None

        driver_layout.addRow("Kernel Module:", QLabel(f"<b>{driver_name}</b>"))
        driver_group.setLayout(driver_layout)
        layout.addWidget(driver_group)

        actions_group = QGroupBox("Actions (Root)")
        actions_layout = QVBoxLayout()

        btn_unbind = QPushButton(f"Unbind Driver")
        btn_unbind.clicked.connect(lambda: self.action_unbind(clean_driver_name))

        btn_reprobe = QPushButton("Rescan/Reprobe")
        btn_reprobe.clicked.connect(self.action_reprobe)

        btn_unload = QPushButton(f"Unload Module (modprobe -r)")
        btn_unload.clicked.connect(lambda: self.action_unload_module(clean_driver_name))

        if not clean_driver_name or clean_driver_name == 'None':
            btn_unbind.setEnabled(False)
            btn_unload.setEnabled(False)

        actions_layout.addWidget(btn_unbind)
        actions_layout.addWidget(btn_reprobe)
        actions_layout.addWidget(self.create_separator())
        actions_layout.addWidget(btn_unload)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def create_details_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Property:"))
        combo = QComboBox()
        combo.addItems(["SysFS Path", "Device Path", "Subsystem", "Driver", "Attributes"])
        val_text = QTextEdit()
        val_text.setReadOnly(True)
        val_text.setFont(QFont("Monospace"))

        def update_text(idx):
            keys = ['SYS_PATH', 'DEVPATH', 'SUBSYSTEM', 'DRIVER']
            if idx < 4:
                val_text.setText(str(self.device_data.get(keys[idx], '')))
            else:
                val_text.setText(str(self.device_data))

        combo.currentIndexChanged.connect(update_text)
        update_text(0)

        layout.addWidget(combo)
        layout.addWidget(QLabel("Value:"))
        layout.addWidget(val_text)
        widget.setLayout(layout)
        return widget

    def run_root_command(self, cmd_str):
        try:
            full_cmd = ['pkexec', 'sh', '-c', cmd_str]
            subprocess.check_call(full_cmd)
            QMessageBox.information(self, "Success", "Command executed.")
        except subprocess.CalledProcessError:
            QMessageBox.warning(self, "Error", "Action failed.")

    def action_unbind(self, driver):
        subsystem = self.device_data.get('SUBSYSTEM')
        if "(via parent)" in self.device_data.get('DRIVER', ''):
            QMessageBox.information(self, "Info", "This driver belongs to the parent controller.\nUnbinding it will disable all devices connected to that controller.")

        path = f"/sys/bus/{subsystem}/drivers/{driver}/unbind"
        QMessageBox.information(self, "Manual Step", f"To safely unbind this device, run:\necho '{os.path.basename(self.device_data.get('SYS_PATH'))}' | sudo tee {path}")

    def action_reprobe(self):
        sys_path = self.device_data.get('SYS_PATH')
        self.run_root_command(f"echo add > {sys_path}/uevent")

    def action_unload_module(self, mod):
        if QMessageBox.question(self, "Confirm", f"Unload {mod}?") == QMessageBox.Yes:
            self.run_root_command(f"modprobe -r {mod}")

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinMan - Device Manager")
        self.resize(1100, 800)
        self.setWindowIcon(QIcon.fromTheme("computer"))

        self.context = pyudev.Context()
        self.resolver = SystemResolver()
        self.categories = {}
        self.show_hidden = False

        self.setup_ui()
        self.setup_monitor()
        QTimer.singleShot(100, self.refresh_devices)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Exit", self.close)

        view_menu = menubar.addMenu("View")
        self.action_show_hidden = QAction("Show Hidden Devices", checkable=True)
        self.action_show_hidden.toggled.connect(self.toggle_hidden_devices)
        view_menu.addAction(self.action_show_hidden)
        view_menu.addAction("Refresh", self.refresh_devices)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self.show_about)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        scan_action = QAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Scan", self)
        scan_action.triggered.connect(self.refresh_devices)
        toolbar.addAction(scan_action)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.itemDoubleClicked.connect(self.show_properties)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        font = QFont("Segoe UI", 11)
        if not font.exactMatch(): font = QFont("Arial", 11)
        self.tree.setFont(font)
        self.tree.setIconSize(QSize(20, 20))

        self.tree.setStyleSheet("QTreeWidget::item { padding: 4px; }")

        layout.addWidget(self.tree)
        self.root_item = QTreeWidgetItem(self.tree)
        self.root_item.setText(0, socket.gethostname())
        self.root_item.setIcon(0, self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.root_item.setExpanded(True)

    def setup_monitor(self):
        try:
            self.monitor = pyudev.Monitor.from_netlink(self.context)
            self.monitor.filter_by(subsystem='usb')
            self.monitor.filter_by(subsystem='input')
            self.notifier = QSocketNotifier(self.monitor.fileno(), QSocketNotifier.Read)
            self.notifier.activated.connect(self.on_hardware_change)
            self.monitor.start()
        except: pass

    @Slot()
    def on_hardware_change(self):
        try:
            self.monitor.receive_device()
            QTimer.singleShot(1000, self.refresh_devices)
        except: pass

    def toggle_hidden_devices(self, checked):
        self.show_hidden = checked
        self.refresh_devices()

    def show_about(self):
        QMessageBox.about(self, "About LinMan",
            f"<b>LinMan - Linux Device Manager</b><br>"
            f"Version {VERSION}<br><br>"
            f"A native Hardware Manager for Linux systems.<br><br>"
            f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a>")

    def get_device_status_flags(self, device, category):
        name = device.sys_name
        sys_path = device.sys_path

        is_hidden = False
        is_physical = True

        if '/virtual/' in sys_path:
            is_physical = False
            is_hidden = True

        if category == 'Ports (COM & LPT)':
            if name.startswith(('ttyUSB', 'ttyACM')): is_hidden = False
            else: is_hidden = True

        if category == 'Network adapters':
            if name == 'lo': is_hidden = True
            if any(x in name for x in ['virbr', 'docker', 'veth', 'tun', 'tap', 'tailscale', 'wg']):
                is_hidden = True
                is_physical = False

        if category == 'Disk drives':
            if name.startswith(('loop', 'ram', 'dm-')):
                is_hidden = True
                is_physical = False

        if category == 'Monitors' or category == 'Memory':
            is_physical = True
            is_hidden = False

        return is_hidden, is_physical

    def get_driver_recursive(self, device):
        driver = device.properties.get('DRIVER', '')
        if driver: return driver, False

        curr = device
        steps = 0
        while curr.parent and steps < 4:
            curr = curr.parent
            driver = curr.properties.get('DRIVER', '')
            if driver and driver != 'pcieport':
                return f"{driver} (via parent)", True
            steps += 1
        return '', False

    def refresh_devices(self):
        self.root_item.takeChildren()
        self.categories = {}
        unique_devices = {}

        # --- 1. Base Hardware (PCI) ---
        for device in self.context.list_devices(subsystem='pci'):
            ven = device.properties.get('ID_VENDOR_FROM_DATABASE')
            dev = device.properties.get('ID_MODEL_FROM_DATABASE')
            if not ven or not dev:
                ven, dev = self.resolver.get_pci_name(device.sys_name)
            if not ven: ven = device.properties.get('ID_VENDOR_ID', 'Unknown Vendor')
            if not dev: dev = device.properties.get('ID_MODEL_ID', 'Unknown Device')

            cat = self.determine_pci_category(device)
            driver = device.properties.get('DRIVER', '')

            self.add_entry(unique_devices, device, dev, ven, cat, 'pci', driver)

        # --- 2. USB ---
        for device in self.context.list_devices(subsystem='usb'):
            if device.device_type == 'usb_device':
                ven = device.properties.get('ID_VENDOR_FROM_DATABASE', device.properties.get('ID_VENDOR', 'USB Vendor'))
                dev = device.properties.get('ID_MODEL_FROM_DATABASE', device.properties.get('ID_MODEL', 'USB Device'))
                driver, _ = self.get_driver_recursive(device)
                self.add_entry(unique_devices, device, dev, ven, 'Universal Serial Bus controllers', 'usb', driver)

        # --- 3. Cameras (Webcams) ---
        for device in self.context.list_devices(subsystem='video4linux'):
            if not device.sys_name.startswith('video'): continue

            # Prefer V4L product name (often better than generic USB ID)
            name = device.properties.get('ID_V4L_PRODUCT')
            if not name: name = device.properties.get('ID_MODEL', 'Webcam').replace('_', ' ')

            vendor = device.properties.get('ID_VENDOR', 'Generic')
            driver, _ = self.get_driver_recursive(device)
            self.add_entry(unique_devices, device, name, vendor, 'Cameras', 'video4linux', driver)

        # --- 4. Monitors (DRM EDID) ---
        drm_path = "/sys/class/drm"
        if os.path.exists(drm_path):
            for conn in os.listdir(drm_path):
                if "-" in conn and os.path.exists(f"{drm_path}/{conn}/status"):
                    try:
                        with open(f"{drm_path}/{conn}/status") as f: status = f.read().strip()
                        if status == "connected":
                            # Use EDID parser
                            real_name = EdidParser.get_monitor_name(f"{drm_path}/{conn}")
                            if not real_name: real_name = f"Generic Monitor ({conn})"

                            card_path = os.path.realpath(f"{drm_path}/{conn}")
                            fake_device = type('obj', (object,), {
                                'sys_name': conn,
                                'sys_path': card_path,
                                'device_path': card_path,
                                'properties': {}
                            })
                            self.add_entry(unique_devices, fake_device, real_name, "Standard Monitor Types", "Monitors", "drm", "monitor-driver")
                    except: pass

        # --- 5. Memory (RAM via DMI) ---
        # Try to read sticks
        ram_modules = DmiParser.get_ram_modules()
        if ram_modules:
            for i, mod in enumerate(ram_modules):
                # Only show sticks that are present
                if "No Module" in mod.get('Size', ''): continue

                name = f"{mod.get('Size')} {mod.get('Type')} {mod.get('Speed')}"
                path = f"/sys/devices/system/memory/stick_{i}"
                fake_mem = type('obj', (object,), {'sys_name': f'ram_{i}', 'sys_path': path, 'device_path': path})
                self.add_entry(unique_devices, fake_mem, name, mod.get('Manufacturer', 'Unknown'), "Memory", "memory", "ram")
        else:
            # Fallback to Total System Memory
            try:
                with open('/proc/meminfo') as f:
                    total_mem = next((line.split(':')[1].strip() for line in f if "MemTotal" in line), "Unknown")
                fake_mem = type('obj', (object,), {
                    'sys_name': 'mem_sys', 'sys_path': '/sys/devices/system/memory', 'device_path': '/sys/devices/system/memory/ram'
                })
                self.add_entry(unique_devices, fake_mem, f"System Memory ({total_mem})", "System", "Memory", "memory", "ram")
            except: pass

        # --- 6. Subsystems ---

        for device in self.context.list_devices(subsystem='drm'):
            if device.parent and device.parent.device_path in unique_devices:
                unique_devices[device.parent.device_path]['category'] = 'Display adapters'

        for device in self.context.list_devices(subsystem='net'):
            self.handle_child(unique_devices, device, 'Network adapters')

        for device in self.context.list_devices(subsystem='sound'):
            if 'card' in device.sys_name:
                curr = device
                while curr.parent:
                    curr = curr.parent
                    if curr.device_path in unique_devices:
                        unique_devices[curr.device_path]['category'] = 'Sound, video and game controllers'
                        break

        for device in self.context.list_devices(subsystem='block'):
            if device.device_type == 'disk':
                self.handle_child(unique_devices, device, 'Disk drives', force_new=True)

        for device in self.context.list_devices(subsystem='bluetooth'):
            if 'hci' in device.sys_name:
                if device.parent and device.parent.device_path in unique_devices:
                    unique_devices[device.parent.device_path]['category'] = 'Bluetooth'
                    unique_devices[device.parent.device_path]['name'] = 'Bluetooth Adapter'

        for device in self.context.list_devices(subsystem='tty'):
             self.handle_child(unique_devices, device, 'Ports (COM & LPT)', force_new=True, fmt="Communications Port ({})")

        for device in self.context.list_devices(subsystem='input'):
            if device.sys_name.startswith('input'):
                props = device.properties
                cat = None
                if props.get('ID_INPUT_KEYBOARD') == '1': cat = 'Keyboards'
                elif props.get('ID_INPUT_MOUSE') == '1': cat = 'Mice and other pointing devices'
                if cat:
                    name = props.get('NAME', 'Input Device').strip('"')
                    driver, _ = self.get_driver_recursive(device)
                    self.add_entry(unique_devices, device, name, '', cat, 'input', driver)

        for device in self.context.list_devices(subsystem='power_supply'):
            if device.properties.get('POWER_SUPPLY_TYPE') == 'Battery':
                self.add_entry(unique_devices, device, f"Battery ({device.sys_name})", '', 'Batteries', 'power', 'battery')

        # Processors
        try:
            with open('/proc/cpuinfo') as f:
                model = next((line.split(':')[1].strip() for line in f if "model name" in line), "Processor")
            for i in range(os.cpu_count() or 1):
                path = f"/sys/devices/system/cpu/cpu{i}"
                fake_dev = type('obj', (object,), {'sys_name': f'cpu{i}', 'sys_path': path, 'device_path': path})
                self.add_entry(unique_devices, fake_dev, model, 'Intel/AMD', 'Processors', 'cpu', 'processor')
        except: pass

        # --- Render ---
        for data in sorted(unique_devices.values(), key=lambda x: (x['category'], x['name'])):
            if data.get('is_hidden') and not self.show_hidden: continue
            self.add_device_to_tree(data)
        self.root_item.setExpanded(True)

    def add_entry(self, db, device, name, vendor, cat, sub, driver):
        is_hidden, is_physical = self.get_device_status_flags(device, cat)

        db[device.device_path] = {
            'name': name, 'vendor': vendor, 'category': cat,
            'sys_path': device.sys_path, 'subsystem': sub,
            'driver': driver, 'is_hidden': is_hidden, 'is_physical': is_physical,
            'devpath': device.device_path
        }

    def handle_child(self, db, device, category, force_new=False, fmt="{}"):
        driver, _ = self.get_driver_recursive(device)

        if not force_new:
            curr = device
            found_parent = False
            for _ in range(3):
                parent = curr.parent
                if parent and parent.device_path in db:
                    db[parent.device_path]['category'] = category
                    if not db[parent.device_path]['driver'] and driver:
                        db[parent.device_path]['driver'] = driver
                    found_parent = True
                    break
                if parent: curr = parent
                else: break
            if found_parent: return

        name = device.properties.get('ID_MODEL', device.sys_name).replace('_', ' ')
        if fmt != "{}": name = fmt.format(device.sys_name)
        self.add_entry(db, device, name, device.properties.get('ID_VENDOR', ''), category, device.subsystem, driver)

    def determine_pci_category(self, device):
        pci_class = device.properties.get('PCI_CLASS')
        if not pci_class:
            try:
                with open(f"{device.sys_path}/class", 'r') as f: pci_class = f.read().strip()
            except: pass
        if not pci_class: return 'System devices'
        code = pci_class.lower().replace('0x', '').zfill(6)[0:2]
        return {
            '00': 'Other devices', '01': 'Storage controllers', '02': 'Network adapters',
            '03': 'Display adapters', '04': 'Sound, video and game controllers',
            '05': 'Memory', '06': 'System devices',
            '07': 'Communication controllers', '08': 'System devices',
            '09': 'Input devices', '0c': 'Universal Serial Bus controllers'
        }.get(code, 'System devices')

    def add_device_to_tree(self, data):
        cat_name = data['category']
        if cat_name not in self.categories:
            cat_item = QTreeWidgetItem(self.root_item)
            cat_item.setText(0, cat_name)
            cat_item.setIcon(0, self.get_category_icon(cat_name))
            self.categories[cat_name] = cat_item

        d_item = QTreeWidgetItem(self.categories[cat_name])
        name = re.sub(' +', ' ', f"{data['vendor']} {data['name']}".strip())
        d_item.setText(0, name)

        icon = self.get_device_icon(cat_name)

        if data.get('is_hidden'):
            icon = IconFactory.apply_overlay(icon, 'ghost')

        if data.get('is_physical') and not data.get('driver'):
            icon = IconFactory.apply_overlay(icon, 'warning')

        d_item.setIcon(0, icon)

        prop_data = {
            'MODEL': data['name'], 'VENDOR': data['vendor'], 'CATEGORY': cat_name,
            'SYS_PATH': data.get('sys_path'), 'SUBSYSTEM': data.get('subsystem'),
            'DRIVER': data.get('driver'), 'DEVPATH': data.get('devpath'),
            'IS_HIDDEN': data.get('is_hidden'), 'IS_PHYSICAL': data.get('is_physical')
        }
        d_item.setData(0, Qt.UserRole, prop_data)

    def get_category_icon(self, category):
        mapping = {
            'Network adapters': (['network-wired', 'network-workgroup'], QStyle.SP_ComputerIcon),
            'Display adapters': (['video-display', 'video-x-generic'], QStyle.SP_DesktopIcon),
            'Disk drives': (['drive-harddisk', 'media-optical'], QStyle.SP_DriveHDIcon),
            'Processors': (['cpu', 'computer'], QStyle.SP_ComputerIcon),
            'Sound, video and game controllers': (['audio-card', 'multimedia-player'], QStyle.SP_MediaVolume),
            'Universal Serial Bus controllers': (['drive-removable-media', 'media-flash'], QStyle.SP_DriveCDIcon),
            'Keyboards': (['input-keyboard'], QStyle.SP_ComputerIcon),
            'Mice and other pointing devices': (['input-mouse'], QStyle.SP_ComputerIcon),
            'Bluetooth': (['bluetooth', 'network-wireless'], QStyle.SP_ComputerIcon),
            'Batteries': (['battery'], QStyle.SP_TitleBarNormalButton),
            'Ports (COM & LPT)': (['modem'], QStyle.SP_ComputerIcon),
            'Cameras': (['camera-web', 'camera-photo'], QStyle.SP_ComputerIcon),
            'Monitors': (['video-display'], QStyle.SP_DesktopIcon),
            'Memory': (['memory', 'media-flash'], QStyle.SP_DriveCDIcon),
        }
        if category in mapping:
            return IconFactory.get(mapping[category][0], mapping[category][1])
        return IconFactory.get(['folder'], QStyle.SP_DirIcon)

    def get_device_icon(self, category):
        mapping = {
            'Display adapters': (['video-display'], QStyle.SP_DesktopIcon),
            'Network adapters': (['network-card'], QStyle.SP_ComputerIcon),
            'Keyboards': (['input-keyboard'], QStyle.SP_ComputerIcon),
            'Mice and other pointing devices': (['input-mouse'], QStyle.SP_ComputerIcon),
            'Sound, video and game controllers': (['audio-card'], QStyle.SP_MediaVolume),
            'Bluetooth': (['bluetooth'], QStyle.SP_ComputerIcon),
            'Disk drives': (['drive-harddisk'], QStyle.SP_DriveHDIcon),
            'Universal Serial Bus controllers': (['drive-removable-media-usb'], QStyle.SP_DriveCDIcon),
            'Cameras': (['camera-web'], QStyle.SP_ComputerIcon),
            'Monitors': (['video-display'], QStyle.SP_DesktopIcon),
            'Memory': (['memory'], QStyle.SP_DriveCDIcon),
        }
        if category in mapping:
            return IconFactory.get(mapping[category][0], mapping[category][1])
        return IconFactory.get(['hardware', 'application-x-executable'], QStyle.SP_FileIcon)

    def show_properties(self, item, column):
        if item.childCount() > 0 or item == self.root_item: return
        device_data = item.data(0, Qt.UserRole)
        if device_data:
            dialog = PropertiesDialog(device_data, item.icon(0), self)
            dialog.exec()

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item or item.childCount() > 0: return

        # Get data
        data = item.data(0, Qt.UserRole)

        menu = QMenu(self)

        action_props = menu.addAction("Properties")
        action_props.triggered.connect(lambda: self.show_properties(item, 0))

        menu.addSeparator()

        action_copy_name = menu.addAction("Copy Name")
        action_copy_name.triggered.connect(lambda: QApplication.clipboard().setText(item.text(0)))

        action_copy_path = menu.addAction("Copy Device Path")
        action_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(data.get('SYS_PATH', '')))

        menu.exec(self.tree.mapToGlobal(position))

def main():
    app = QApplication(sys.argv)

    # Enable High DPI
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # Use Fusion as a base because it is the most neutral across Linux distros
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
