"""
LinMan - Linux Device Manager (Compatibility Edition)
A standalone device manager that relies on system tools rather than external libraries.

Dependencies:
    pip install PySide6 pyudev

Features:
- FIX: Deep Parent Search (Fixes USB Audio/Net devices appearing as generic USB)
- "Show Hidden Devices" toggle (Hides tty/lo/loops by default)
- Uses system commands (lspci, lsusb) for name resolution
- No external database downloads required
- Root Actions (Unbind, Modprobe) via pkexec

"""

import sys
import socket
import os
import re
import subprocess
import shutil
from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
                               QMessageBox, QVBoxLayout, QWidget, QDialog, QLabel,
                               QFormLayout, QToolBar, QStyle, QTabWidget, QGroupBox,
                               QLineEdit, QTextEdit, QFrame, QStyleFactory, QMenu,
                               QDialogButtonBox, QHBoxLayout, QPushButton, QComboBox,
                               QHeaderView)
from PySide6.QtCore import Qt, QSize, QSocketNotifier, Slot, QTimer
from PySide6.QtGui import QIcon, QAction, QFont, QPalette, QColor, QPainter, QPixmap

import pyudev

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
    def ghost_icon(icon):
        pixmap = icon.pixmap(32, 32)
        ghost = QPixmap(pixmap.size())
        ghost.fill(Qt.transparent)
        painter = QPainter(ghost)
        painter.setOpacity(0.5)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return QIcon(ghost)

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

        msg = []
        if is_hidden: msg.append("This device is hidden/disconnected.")
        if driver: msg.append(f"This device is working properly.\nDriver: {driver}")
        else: msg.append("No driver is loaded for this device.")

        status_text.setPlainText("\n".join(msg))
        status_text.setReadOnly(True)
        status_text.setMaximumHeight(80)
        status_text.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0; border: none;")
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
        driver_layout.addRow("Kernel Module:", QLabel(f"<b>{driver_name}</b>"))
        driver_group.setLayout(driver_layout)
        layout.addWidget(driver_group)

        actions_group = QGroupBox("Actions (Root)")
        actions_layout = QVBoxLayout()

        btn_unbind = QPushButton(f"Unbind Driver")
        btn_unbind.clicked.connect(self.action_unbind)
        if not driver_name or driver_name == 'None': btn_unbind.setEnabled(False)

        btn_reprobe = QPushButton("Rescan/Reprobe")
        btn_reprobe.clicked.connect(self.action_reprobe)

        btn_unload = QPushButton(f"Unload Module (modprobe -r)")
        btn_unload.clicked.connect(self.action_unload_module)
        if not driver_name or driver_name == 'None': btn_unload.setEnabled(False)

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
        combo.addItems(["SysFS Path", "Device Path", "Subsystem", "Driver", "Udev Attributes"])
        val_text = QTextEdit()
        val_text.setReadOnly(True)
        val_text.setStyleSheet("font-family: Monospace; background-color: #2b2b2b;")

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

    def action_unbind(self):
        driver = self.device_data.get('DRIVER')
        subsystem = self.device_data.get('SUBSYSTEM')
        dev_id = os.path.basename(self.device_data.get('SYS_PATH'))
        path = f"/sys/bus/{subsystem}/drivers/{driver}/unbind"
        if QMessageBox.question(self, "Confirm", f"Unbind {dev_id}?") == QMessageBox.Yes:
            self.run_root_command(f"echo '{dev_id}' > {path}")

    def action_reprobe(self):
        sys_path = self.device_data.get('SYS_PATH')
        self.run_root_command(f"echo add > {sys_path}/uevent")

    def action_unload_module(self):
        mod = self.device_data.get('DRIVER')
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
        view_menu = menubar.addMenu("View")
        self.action_show_hidden = QAction("Show Hidden Devices", checkable=True)
        self.action_show_hidden.toggled.connect(self.toggle_hidden_devices)
        view_menu.addAction(self.action_show_hidden)
        view_menu.addAction("Refresh", self.refresh_devices)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setStyleSheet("QToolBar { background-color: #2d2d30; border-bottom: 1px solid #3f3f46; padding: 5px; }")
        toolbar.setIconSize(QSize(24, 24))
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

        self.tree.setStyleSheet("""
            QTreeWidget {
                border: none; background-color: #1e1e1e;
                color: #e0e0e0; selection-background-color: #0078d4;
            }
            QTreeWidget::item { height: 28px; border: none; padding-left: 5px; }
            QTreeWidget::item:hover:!selected { background-color: #2a2d2e; }
            QTreeWidget::item:selected { background-color: #0078d4; color: white; }
        """)

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

    def is_device_hidden(self, device, category):
        name = device.sys_name

        # 1. HIDE ALL TTYs by default, EXCEPT USB/ACM
        if category == 'Ports (COM & LPT)':
            if name.startswith(('ttyUSB', 'ttyACM')): return False
            return True

        # 2. Hide Loopback/Virtual Net
        if category == 'Network adapters':
            if name == 'lo': return True
            if any(x in name for x in ['virbr', 'docker', 'veth', 'tun', 'tap']): return True

        # 3. Hide Virtual Disks
        if category == 'Disk drives':
            if name.startswith(('loop', 'ram', 'dm-')): return True

        return False

    def refresh_devices(self):
        self.root_item.takeChildren()
        self.categories = {}
        unique_devices = {}

        # --- 1. Base Hardware (PCI) ---
        for device in self.context.list_devices(subsystem='pci'):
            # Try to get name from udev DB first (fastest)
            ven = device.properties.get('ID_VENDOR_FROM_DATABASE')
            dev = device.properties.get('ID_MODEL_FROM_DATABASE')

            # If missing, try lspci (most accurate)
            if not ven or not dev:
                slot_name = device.sys_name # e.g. 0000:00:1f.6
                l_ven, l_dev = self.resolver.get_pci_name(slot_name)
                if l_ven: ven = l_ven
                if l_dev: dev = l_dev

            # Fallback to hex
            if not ven: ven = device.properties.get('ID_VENDOR_ID', 'Unknown Vendor')
            if not dev: dev = device.properties.get('ID_MODEL_ID', 'Unknown Device')

            cat = self.determine_pci_category(device)
            self.add_entry(unique_devices, device, dev, ven, cat, 'pci', device.properties.get('DRIVER', ''))

        # --- 2. USB ---
        for device in self.context.list_devices(subsystem='usb'):
            if device.device_type == 'usb_device':
                ven = device.properties.get('ID_VENDOR_FROM_DATABASE', device.properties.get('ID_VENDOR', 'USB Vendor'))
                dev = device.properties.get('ID_MODEL_FROM_DATABASE', device.properties.get('ID_MODEL', 'USB Device'))
                self.add_entry(unique_devices, device, dev, ven, 'Universal Serial Bus controllers', 'usb', device.properties.get('DRIVER', ''))

        # --- 3. Subsystems ---

        # Display Adapters (DRM Fix)
        for device in self.context.list_devices(subsystem='drm'):
            parent = device.parent
            if parent and parent.device_path in unique_devices:
                unique_devices[parent.device_path]['category'] = 'Display adapters'

        # Network
        for device in self.context.list_devices(subsystem='net'):
            self.handle_child(unique_devices, device, 'Network adapters')

        # Sound - RECURSIVE PARENT SEARCH FIX for USB Headsets
        for device in self.context.list_devices(subsystem='sound'):
            if 'card' in device.sys_name:
                curr = device
                # Walk up tree to find physical parent (fixes USB Interface issue)
                while curr.parent:
                    curr = curr.parent
                    if curr.device_path in unique_devices:
                        unique_devices[curr.device_path]['category'] = 'Sound, video and game controllers'
                        break

        # Disk
        for device in self.context.list_devices(subsystem='block'):
            if device.device_type == 'disk':
                self.handle_child(unique_devices, device, 'Disk drives', force_new=True)

        # Bluetooth
        for device in self.context.list_devices(subsystem='bluetooth'):
            if 'hci' in device.sys_name:
                parent = device.parent
                if parent and parent.device_path in unique_devices:
                    unique_devices[parent.device_path]['category'] = 'Bluetooth'
                    unique_devices[parent.device_path]['name'] = 'Bluetooth Adapter'

        # TTY (COM Ports)
        for device in self.context.list_devices(subsystem='tty'):
             self.handle_child(unique_devices, device, 'Ports (COM & LPT)', force_new=True, fmt="Communications Port ({})")

        # Input
        for device in self.context.list_devices(subsystem='input'):
            if device.sys_name.startswith('input'):
                props = device.properties
                cat = None
                if props.get('ID_INPUT_KEYBOARD') == '1': cat = 'Keyboards'
                elif props.get('ID_INPUT_MOUSE') == '1': cat = 'Mice and other pointing devices'
                if cat:
                    name = props.get('NAME', 'Input Device').strip('"')
                    self.add_entry(unique_devices, device, name, '', cat, 'input', '')

        # Batteries
        for device in self.context.list_devices(subsystem='power_supply'):
            if device.properties.get('POWER_SUPPLY_TYPE') == 'Battery':
                self.add_entry(unique_devices, device, f"Battery ({device.sys_name})", '', 'Batteries', 'power', 'battery')

        # Processors
        try:
            with open('/proc/cpuinfo') as f:
                model = next((line.split(':')[1].strip() for line in f if "model name" in line), "Processor")
            for i in range(os.cpu_count() or 1):
                path = f"/sys/devices/system/cpu/cpu{i}"
                unique_devices[path] = {
                    'name': model, 'vendor': 'Intel/AMD', 'category': 'Processors',
                    'sys_path': path, 'subsystem': 'cpu', 'driver': 'processor', 'is_hidden': False
                }
        except: pass

        # --- Render ---
        for data in sorted(unique_devices.values(), key=lambda x: (x['category'], x['name'])):
            if data.get('is_hidden') and not self.show_hidden: continue
            self.add_device_to_tree(data)
        self.root_item.setExpanded(True)

    def add_entry(self, db, device, name, vendor, cat, sub, driver, is_hidden=False):
        db[device.device_path] = {
            'name': name, 'vendor': vendor, 'category': cat,
            'sys_path': device.sys_path, 'subsystem': sub,
            'driver': driver, 'is_hidden': is_hidden, 'devpath': device.device_path
        }

    def handle_child(self, db, device, category, force_new=False, fmt="{}"):
        hidden = self.is_device_hidden(device, category)
        if not force_new:
            # Recursive check up to 3 levels to find physical parent
            curr = device
            found_parent = False
            for _ in range(3):
                parent = curr.parent
                if parent and parent.device_path in db:
                    db[parent.device_path]['category'] = category
                    if not db[parent.device_path]['driver']:
                        db[parent.device_path]['driver'] = device.properties.get('DRIVER', '')
                    found_parent = True
                    break
                if parent: curr = parent
                else: break
            if found_parent: return

        name = device.properties.get('ID_MODEL', device.sys_name).replace('_', ' ')
        if fmt != "{}": name = fmt.format(device.sys_name)
        self.add_entry(db, device, name, device.properties.get('ID_VENDOR', ''), category, device.subsystem, device.properties.get('DRIVER', ''), hidden)

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
            '05': 'Memory technology devices', '06': 'System devices',
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

        # Smart Icon Selection
        icon = self.get_device_icon(cat_name)
        if data.get('is_hidden'): icon = IconFactory.ghost_icon(icon)
        d_item.setIcon(0, icon)

        prop_data = {
            'MODEL': data['name'], 'VENDOR': data['vendor'], 'CATEGORY': cat_name,
            'SYS_PATH': data.get('sys_path'), 'SUBSYSTEM': data.get('subsystem'),
            'DRIVER': data.get('driver'), 'DEVPATH': data.get('devpath'),
            'IS_HIDDEN': data.get('is_hidden')
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
        menu = QMenu(self)
        menu.addAction("Properties", lambda: self.show_properties(item, 0))
        menu.exec(self.tree.mapToGlobal(position))

def main():
    app = QApplication(sys.argv)

    # Dark Theme
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(32, 32, 32))
    palette.setColor(QPalette.WindowText, QColor(240, 240, 240))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(32, 32, 32))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(240, 240, 240))
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, QColor(240, 240, 240))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(0, 120, 215))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    app.setStyle("Fusion")

    app.setStyleSheet("""
        QMainWindow { background-color: #202020; }
        QMenu { background-color: #2b2b2b; border: 1px solid #353535; color: #f0f0f0; }
        QMenu::item:selected { background-color: #0078d4; }
        QDialog { background-color: #202020; }
        QGroupBox { border: 1px solid #353535; margin-top: 10px; border-radius: 4px; padding-top: 15px; color: #f0f0f0; }
        QLabel { color: #f0f0f0; }
        QPushButton { background-color: #353535; border: 1px solid #454545; color: #f0f0f0; padding: 6px; border-radius: 4px; }
        QPushButton:hover { background-color: #454545; border-color: #0078d4; }
        QPushButton:disabled { color: #666; }
        QTabWidget::pane { border: 1px solid #353535; background: #202020; }
        QTabBar::tab { background: #2b2b2b; color: #f0f0f0; padding: 8px 16px; border: 1px solid #353535; }
        QTabBar::tab:selected { background: #353535; }
        QHeaderView::section { background-color: #2b2b2b; color: #f0f0f0; padding: 4px; border: 1px solid #353535; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
