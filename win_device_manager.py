"""
LinMan - Linux Device Manager (Professional Edition)
A comprehensive device manager for Linux systems.

Features:
- "Show Hidden Devices" toggle (View Menu)
- Smart Icon mapping (uses System Theme first)
- Real-time device detection (udev)
- Native ID resolution (hwdata/pci.ids)
- Root Actions (Unbind, Modprobe, etc.)
- Windows 11-style Dark Theme with scaled UI

"""

import sys
import socket
import os
import re
import subprocess
from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
                               QMessageBox, QVBoxLayout, QWidget, QDialog, QLabel,
                               QFormLayout, QToolBar, QStyle, QTabWidget, QGroupBox,
                               QLineEdit, QTextEdit, QFrame, QStyleFactory, QMenu,
                               QDialogButtonBox, QHBoxLayout, QPushButton, QComboBox,
                               QHeaderView, QTableWidget, QTableWidgetItem)
from PySide6.QtCore import Qt, QSize, QSocketNotifier, Slot, QTimer
from PySide6.QtGui import QIcon, QAction, QFont, QPalette, QColor, QPainter, QPixmap

import pyudev

# Try to import hwdata for ID resolution
try:
    import hwdata
    HAS_HWDATA = True
except ImportError:
    HAS_HWDATA = False

# --- Backend: ID Resolution ---
class HardwareResolver:
    def __init__(self):
        self.pci_ids = {}
        self.usb_ids = {}
        self.has_hwdata = HAS_HWDATA

        if self.has_hwdata:
            try:
                self.pci_db = hwdata.PCI()
                self.usb_db = hwdata.USB()
            except Exception:
                self.has_hwdata = False

        if not self.has_hwdata:
            self._load_ids(['/usr/share/hwdata/pci.ids', '/usr/share/misc/pci.ids'], self.pci_ids)
            self._load_ids(['/usr/share/hwdata/usb.ids', '/usr/share/misc/usb.ids'], self.usb_ids)

    def _load_ids(self, filepaths, target_dict):
        found_path = next((p for p in filepaths if os.path.exists(p)), None)
        if not found_path: return

        current_vendor = None
        try:
            with open(found_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('#') or not line.strip(): continue
                    if not line.startswith('\t') and not line.startswith('C'):
                        parts = line.strip().split(maxsplit=1)
                        if len(parts) == 2:
                            current_vendor = parts[0].lower()
                            target_dict[current_vendor] = {'name': parts[1], 'devices': {}}
                    elif line.startswith('\t') and not line.startswith('\t\t') and current_vendor:
                        parts = line.strip().split(maxsplit=1)
                        if len(parts) == 2:
                            device_id = parts[0].lower()
                            target_dict[current_vendor]['devices'][device_id] = parts[1]
        except Exception: pass

    def get_name(self, subsystem, vendor_id, device_id):
        if not vendor_id or not device_id: return None, None
        vendor_id = str(vendor_id).lower().replace('0x', '')
        device_id = str(device_id).lower().replace('0x', '')

        if self.has_hwdata:
            try:
                if subsystem == 'pci':
                    return self.pci_db.get_vendor(vendor_id), self.pci_db.get_device(vendor_id, device_id)
                elif subsystem == 'usb':
                    return self.usb_db.get_vendor(vendor_id), self.usb_db.get_device(vendor_id, device_id)
            except: pass

        db = self.pci_ids if subsystem == 'pci' else self.usb_ids
        if vendor_id in db:
            vendor_name = db[vendor_id]['name']
            device_name = db[vendor_id]['devices'].get(device_id, None)
            return vendor_name, device_name
        return None, None

# --- Helper: Icon Factory ---
class IconFactory:
    """Gets standard Linux system icons with fallback to Qt standards"""
    @staticmethod
    def get(name_list, fallback_style_standard):
        # Try finding a theme icon first (e.g., 'input-keyboard')
        for name in name_list:
            if QIcon.hasThemeIcon(name):
                return QIcon.fromTheme(name)

        # Fallback to internal Qt icon
        return QApplication.style().standardIcon(fallback_style_standard)

    @staticmethod
    def ghost_icon(icon):
        """Creates a semi-transparent version of an icon for hidden devices"""
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
        self.setMinimumSize(600, 650)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Header
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

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 11))
        self.tabs.addTab(self.create_general_tab(), "General")
        self.tabs.addTab(self.create_driver_tab(), "Kernel / Driver")
        self.tabs.addTab(self.create_details_tab(), "Details")
        layout.addWidget(self.tabs)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def create_general_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(20)

        info_group = QGroupBox("Device Information")
        info_layout = QFormLayout()
        info_layout.setLabelAlignment(Qt.AlignLeft)

        info_layout.addRow("Device Type:", QLabel(self.device_data.get('CATEGORY', 'Unknown')))
        info_layout.addRow("Manufacturer:", QLabel(self.device_data.get('VENDOR', 'Standard system devices')))
        info_layout.addRow("Location:", QLabel(os.path.basename(self.device_data.get('SYS_PATH', 'Unknown'))))

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        status_group = QGroupBox("Device Status")
        status_layout = QVBoxLayout()
        status_text = QTextEdit()

        driver = self.device_data.get('DRIVER')
        is_hidden = self.device_data.get('IS_HIDDEN', False)

        msg = []
        if is_hidden:
            msg.append("This device is hidden (Virtual or Disconnected).")

        if driver:
            msg.append(f"This device is working properly.\nBound to driver: {driver}")
        else:
            msg.append("No proprietary or specific driver is currently bound.")

        status_text.setPlainText("\n".join(msg))
        status_text.setReadOnly(True)
        status_text.setMaximumHeight(100)
        status_text.setStyleSheet("background-color: #252526; color: #e0e0e0; border: 1px solid #3f3f46;")
        status_layout.addWidget(status_text)
        status_group.setLayout(status_layout)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_driver_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        driver_group = QGroupBox("Kernel Module")
        driver_layout = QFormLayout()

        driver_name = self.device_data.get('DRIVER', 'None')

        driver_layout.addRow("Current Driver:", QLabel(f"<b>{driver_name}</b>"))
        driver_layout.addRow("Kernel Version:", QLabel(os.uname().release))
        driver_group.setLayout(driver_layout)
        layout.addWidget(driver_group)

        actions_group = QGroupBox("Management Actions (Requires Root)")
        actions_layout = QVBoxLayout()

        btn_unbind = QPushButton(f"Unbind Driver ({driver_name})")
        btn_unbind.clicked.connect(self.action_unbind)
        if not driver_name or driver_name == 'None': btn_unbind.setEnabled(False)

        btn_reprobe = QPushButton("Reprobe Device")
        btn_reprobe.clicked.connect(self.action_reprobe)

        btn_unload = QPushButton(f"Unload Module ({driver_name})")
        btn_unload.clicked.connect(self.action_unload_module)
        if not driver_name or driver_name == 'None': btn_unload.setEnabled(False)

        btn_reload = QPushButton(f"Reload Module ({driver_name})")
        btn_reload.clicked.connect(self.action_reload_module)
        if not driver_name or driver_name == 'None': btn_reload.setEnabled(False)

        actions_layout.addWidget(btn_unbind)
        actions_layout.addWidget(btn_reprobe)
        actions_layout.addWidget(self.create_separator())
        actions_layout.addWidget(btn_unload)
        actions_layout.addWidget(btn_reload)

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
        val_text.setStyleSheet("font-family: Consolas, Monospace; background-color: #252526;")

        def update_text(idx):
            if idx == 0: val_text.setText(self.device_data.get('SYS_PATH', ''))
            elif idx == 1: val_text.setText(self.device_data.get('DEVPATH', ''))
            elif idx == 2: val_text.setText(self.device_data.get('SUBSYSTEM', ''))
            elif idx == 3: val_text.setText(self.device_data.get('DRIVER', 'None'))
            elif idx == 4: val_text.setText(str(self.device_data))

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
            QMessageBox.information(self, "Success", "Command executed successfully.")
            return True
        except subprocess.CalledProcessError:
            QMessageBox.warning(self, "Error", "Action failed or cancelled.")
            return False

    def action_unbind(self):
        driver = self.device_data.get('DRIVER')
        subsystem = self.device_data.get('SUBSYSTEM')
        dev_id = os.path.basename(self.device_data.get('SYS_PATH'))
        if not driver or not subsystem: return
        path = f"/sys/bus/{subsystem}/drivers/{driver}/unbind"
        if QMessageBox.question(self, "Confirm", f"Unbind {dev_id} from {driver}?") == QMessageBox.Yes:
            self.run_root_command(f"echo '{dev_id}' > {path}")

    def action_reprobe(self):
        sys_path = self.device_data.get('SYS_PATH')
        self.run_root_command(f"echo add > {sys_path}/uevent")

    def action_unload_module(self):
        mod = self.device_data.get('DRIVER')
        if QMessageBox.question(self, "Confirm", f"Run 'modprobe -r {mod}'?") == QMessageBox.Yes:
            self.run_root_command(f"modprobe -r {mod}")

    def action_reload_module(self):
        mod = self.device_data.get('DRIVER')
        if QMessageBox.question(self, "Confirm", f"Reload module '{mod}'?") == QMessageBox.Yes:
            self.run_root_command(f"modprobe -r {mod} && modprobe {mod}")


# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinMan - Linux Device Manager")
        self.resize(1100, 800)
        self.setWindowIcon(QIcon.fromTheme("computer"))

        self.context = pyudev.Context()
        self.resolver = HardwareResolver()
        self.categories = {}
        self.show_hidden = False # Default state

        self.setup_ui()
        self.setup_monitor()

        QTimer.singleShot(100, self.refresh_devices)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Menubar ---
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Exit", self.close)

        view_menu = menubar.addMenu("View")
        self.action_show_hidden = QAction("Show Hidden Devices", checkable=True)
        self.action_show_hidden.toggled.connect(self.toggle_hidden_devices)
        view_menu.addAction(self.action_show_hidden)
        view_menu.addSeparator()
        view_menu.addAction("Refresh", self.refresh_devices)

        # --- Toolbar ---
        toolbar = QToolBar()
        toolbar.setStyleSheet("QToolBar { background-color: #2d2d30; border-bottom: 1px solid #3f3f46; padding: 6px; }")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        scan_action = QAction(QIcon.fromTheme("view-refresh", self.style().standardIcon(QStyle.SP_BrowserReload)), "Scan", self)
        scan_action.triggered.connect(self.refresh_devices)
        toolbar.addAction(scan_action)

        # --- Tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(24)
        self.tree.setAnimated(True)
        self.tree.itemDoubleClicked.connect(self.show_properties)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Bigger Font
        font = QFont("Segoe UI", 12)
        if not font.exactMatch(): font = QFont("Arial", 12)
        self.tree.setFont(font)
        self.tree.setIconSize(QSize(22, 22))

        self.tree.setStyleSheet("""
            QTreeWidget {
                border: none; background-color: #1e1e1e;
                color: #e0e0e0; selection-background-color: #0078d4;
                alternate-background-color: #252526;
            }
            QTreeWidget::item { height: 32px; border: none; padding-left: 6px; }
            QTreeWidget::item:hover:!selected { background-color: #2a2d2e; }
            QTreeWidget::item:selected { background-color: #0078d4; color: white; }
        """)

        layout.addWidget(self.tree)

        self.root_item = QTreeWidgetItem(self.tree)
        self.root_item.setText(0, socket.gethostname())
        self.root_item.setIcon(0, QIcon.fromTheme("computer", self.style().standardIcon(QStyle.SP_ComputerIcon)))
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
        """Logic to define what constitutes a 'Hidden' device"""
        name = device.sys_name

        # Network Hidden
        if category == 'Network adapters':
            if name == 'lo': return True
            if any(x in name for x in ['virbr', 'docker', 'veth', 'tun', 'tap', 'br-']): return True

        # Disk Hidden
        if category == 'Disk drives':
            if name.startswith('loop'): return True
            if name.startswith('ram'): return True
            if name.startswith('dm-'): return True

        # TTY Hidden
        if category == 'Ports (COM & LPT)':
            # Real hardware usually has resources, virtual TTYs don't
            if 'ttyS' in name and not os.path.exists(f"/sys/class/tty/{name}/device/resources"):
                return True
            # PTYs are hidden
            if 'pt' in name: return True

        return False

    def refresh_devices(self):
        self.root_item.takeChildren()
        self.categories = {}
        unique_devices = {}

        # --- 1. Base Hardware (PCI) ---
        for device in self.context.list_devices(subsystem='pci'):
            self.process_device(device, 'pci', unique_devices)

        # --- 2. USB ---
        for device in self.context.list_devices(subsystem='usb'):
            if device.device_type == 'usb_device':
                self.process_device(device, 'usb', unique_devices)

        # --- 3. Graphics / DRM ---
        for device in self.context.list_devices(subsystem='drm'):
            parent = device.parent
            if parent and parent.device_path in unique_devices:
                unique_devices[parent.device_path]['category'] = 'Display adapters'

        # --- 4. Subsystem Logic ---
        # Network
        for device in self.context.list_devices(subsystem='net'):
            self.process_child_device(device, 'Network adapters', unique_devices)

        # Block
        for device in self.context.list_devices(subsystem='block'):
            if device.device_type == 'disk':
                self.process_child_device(device, 'Disk drives', unique_devices, force_new=True)

        # Sound
        for device in self.context.list_devices(subsystem='sound'):
            if 'card' in device.sys_name:
                parent = device.parent
                if parent and parent.device_path in unique_devices:
                    unique_devices[parent.device_path]['category'] = 'Sound, video and game controllers'

        # Bluetooth
        for device in self.context.list_devices(subsystem='bluetooth'):
            if 'hci' in device.sys_name:
                parent = device.parent
                if parent and parent.device_path in unique_devices:
                    unique_devices[parent.device_path]['category'] = 'Bluetooth'
                    unique_devices[parent.device_path]['name'] = 'Bluetooth Adapter'

        # COM Ports
        for device in self.context.list_devices(subsystem='tty'):
             self.process_child_device(device, 'Ports (COM & LPT)', unique_devices, force_new=True, name_fmt="Communications Port ({})")

        # Input
        for device in self.context.list_devices(subsystem='input'):
            if device.sys_name.startswith('input'):
                props = device.properties
                cat = None
                if props.get('ID_INPUT_KEYBOARD') == '1': cat = 'Keyboards'
                elif props.get('ID_INPUT_MOUSE') == '1': cat = 'Mice and other pointing devices'

                if cat:
                    name = props.get('NAME', 'Input Device').strip('"')
                    unique_devices[device.device_path] = self.create_device_entry(device, name, '', cat, 'input', '')

        # Batteries
        for device in self.context.list_devices(subsystem='power_supply'):
            if device.properties.get('POWER_SUPPLY_TYPE') == 'Battery':
                name = f"System Battery ({device.sys_name})"
                unique_devices[device.device_path] = self.create_device_entry(device, name, 'Generic', 'Batteries', 'power', 'battery')

        # Processors
        try:
            with open('/proc/cpuinfo') as f:
                model = next((line.split(':')[1].strip() for line in f if "model name" in line), "Processor")
            for i in range(os.cpu_count() or 1):
                unique_devices[f"cpu_{i}"] = {
                    'name': model, 'vendor': 'Intel/AMD', 'category': 'Processors',
                    'sys_path': f"/sys/devices/system/cpu/cpu{i}", 'subsystem': 'cpu',
                    'driver': 'processor', 'is_hidden': False
                }
        except: pass

        # --- Render ---
        for data in sorted(unique_devices.values(), key=lambda x: (x['category'], x['name'])):
            is_hidden = data.get('is_hidden', False)
            if is_hidden and not self.show_hidden:
                continue
            self.add_device_to_tree(data)

        self.root_item.setExpanded(True)

    # --- Device Processing Helpers ---
    def create_device_entry(self, device, name, vendor, category, subsystem, driver, is_hidden=False):
        return {
            'name': name, 'vendor': vendor, 'category': category,
            'sys_path': device.sys_path, 'subsystem': subsystem,
            'driver': driver, 'is_hidden': is_hidden
        }

    def process_device(self, device, subsystem, device_dict):
        """Process base PCI/USB devices"""
        if subsystem == 'pci':
            pci_id = device.properties.get('PCI_ID', ':')
            vid, pid = pci_id.split(':') if ':' in pci_id else (None, None)
            ven, dev = self.resolver.get_name('pci', vid, pid)
            if not ven: ven = device.properties.get('ID_VENDOR_FROM_DATABASE', 'Unknown Vendor')
            if not dev: dev = device.properties.get('ID_MODEL_FROM_DATABASE', 'Unknown Device')
            cat = self.determine_pci_category(device)
        else: # USB
            vid, pid = device.properties.get('ID_VENDOR_ID'), device.properties.get('ID_MODEL_ID')
            ven, dev = self.resolver.get_name('usb', vid, pid)
            if not ven: ven = device.properties.get('ID_VENDOR', 'USB Vendor')
            if not dev: dev = device.properties.get('ID_MODEL', 'USB Device')
            cat = 'Universal Serial Bus controllers'

        device_dict[device.device_path] = self.create_device_entry(
            device, dev, ven, cat, subsystem, device.properties.get('DRIVER', '')
        )

    def process_child_device(self, device, category, device_dict, force_new=False, name_fmt="{}"):
        """Handle logical devices (net/disk/tty)"""
        is_hidden = self.is_device_hidden(device, category)

        if not force_new:
            # Try to update parent first
            parent = device.parent
            if parent and parent.device_path in device_dict:
                entry = device_dict[parent.device_path]
                entry['category'] = category
                if not entry['driver']: entry['driver'] = device.properties.get('DRIVER', '')
                return

        # If we are here, create a new entry (logical device or virtual)
        name = device.properties.get('ID_MODEL', device.sys_name).replace('_', ' ')
        if name_fmt != "{}": name = name_fmt.format(device.sys_name)

        vendor = device.properties.get('ID_VENDOR', '')

        device_dict[device.device_path] = self.create_device_entry(
            device, name, vendor, category, device.subsystem,
            device.properties.get('DRIVER', ''), is_hidden
        )

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

        # Icon Logic
        icon = self.get_device_icon(cat_name)
        if data.get('is_hidden'):
            icon = IconFactory.ghost_icon(icon)
        d_item.setIcon(0, icon)

        prop_data = {
            'MODEL': data['name'], 'VENDOR': data['vendor'], 'CATEGORY': cat_name,
            'SYS_PATH': data.get('sys_path'), 'SUBSYSTEM': data.get('subsystem'),
            'DRIVER': data.get('driver'), 'DEVPATH': data.get('sys_path'),
            'IS_HIDDEN': data.get('is_hidden')
        }
        d_item.setData(0, Qt.UserRole, prop_data)

    def get_category_icon(self, category):
        # Map categories to Theme names first, standard icons second
        mapping = {
            'Network adapters': (['network-wired', 'network-workgroup'], QStyle.SP_ComputerIcon),
            'Display adapters': (['video-display', 'video-x-generic'], QStyle.SP_DesktopIcon),
            'Disk drives': (['drive-harddisk', 'media-optical'], QStyle.SP_DriveHDIcon),
            'Processors': (['cpu', 'computer'], QStyle.SP_ComputerIcon),
            'Sound, video and game controllers': (['audio-card', 'multimedia-player'], QStyle.SP_MediaVolume),
            'Universal Serial Bus controllers': (['drive-removable-media', 'media-flash'], QStyle.SP_DriveCDIcon),
            'Keyboards': (['input-keyboard'], QStyle.SP_ComputerIcon),
            'Mice and other pointing devices': (['input-mouse'], QStyle.SP_ComputerIcon),
            'Bluetooth': (['bluetooth', 'network-wireless'], QStyle.SP_DriveNetIcon),
            'Batteries': (['battery'], QStyle.SP_TitleBarNormalButton),
            'Ports (COM & LPT)': (['modem'], QStyle.SP_ComputerIcon),
        }

        if category in mapping:
            names, fallback = mapping[category]
            return IconFactory.get(names, fallback)
        return IconFactory.get(['folder'], QStyle.SP_DirIcon)

    def get_device_icon(self, category):
        # Specific Device Icons
        mapping = {
            'Display adapters': (['video-display'], QStyle.SP_DesktopIcon),
            'Network adapters': (['network-card'], QStyle.SP_ComputerIcon),
            'Keyboards': (['input-keyboard'], QStyle.SP_ComputerIcon),
            'Mice and other pointing devices': (['input-mouse'], QStyle.SP_ComputerIcon),
            'Sound, video and game controllers': (['audio-card'], QStyle.SP_MediaVolume),
            'Bluetooth': (['bluetooth'], QStyle.SP_DriveNetIcon),
            'Disk drives': (['drive-harddisk'], QStyle.SP_DriveHDIcon),
            'Universal Serial Bus controllers': (['drive-removable-media-usb'], QStyle.SP_DriveCDIcon),
        }

        if category in mapping:
            names, fallback = mapping[category]
            return IconFactory.get(names, fallback)
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

    # Windows 11-ish Dark Palette
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
    palette.setColor(QPalette.Highlight, QColor(0, 120, 215)) # Windows Blue
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyle("Fusion")

    # Global CSS
    app.setStyleSheet("""
        QMainWindow { background-color: #202020; }
        QMenuBar { background-color: #202020; color: #f0f0f0; border-bottom: 1px solid #353535; }
        QMenuBar::item:selected { background-color: #353535; }
        QMenu { background-color: #2b2b2b; border: 1px solid #353535; color: #f0f0f0; padding: 5px; }
        QMenu::item { padding: 5px 20px; }
        QMenu::item:selected { background-color: #0078d4; }
        QDialog { background-color: #202020; color: #f0f0f0; }
        QGroupBox { border: 1px solid #353535; margin-top: 10px; border-radius: 4px; padding-top: 15px; color: #f0f0f0; font-weight: bold; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QLabel { color: #f0f0f0; }
        QPushButton { background-color: #353535; border: 1px solid #454545; color: #f0f0f0; padding: 6px 12px; border-radius: 4px; }
        QPushButton:hover { background-color: #454545; border-color: #0078d4; }
        QPushButton:disabled { background-color: #252525; color: #666666; }
        QTabWidget::pane { border: 1px solid #353535; background: #202020; }
        QTabBar::tab { background: #2b2b2b; color: #f0f0f0; padding: 8px 16px; border: 1px solid #353535; margin-right: 2px; }
        QTabBar::tab:selected { background: #353535; border-bottom-color: #353535; }
        QHeaderView::section { background-color: #2b2b2b; color: #f0f0f0; padding: 4px; border: 1px solid #353535; }
        QComboBox { background-color: #353535; border: 1px solid #454545; color: #f0f0f0; padding: 4px; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
