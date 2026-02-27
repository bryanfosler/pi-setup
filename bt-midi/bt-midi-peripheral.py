#!/usr/bin/env python3
"""
bt-midi-peripheral.py

Runs the Pi as a BLE MIDI peripheral (Bluetooth LE MIDI, MMA spec).
Mac/iOS will see "Pi BT MIDI" in Audio MIDI Setup → Bluetooth.

Bridges bidirectionally:
  ALSA virtual port "Pi BT MIDI" ↔ BLE MIDI characteristic

Usage:
  python3 bt-midi-peripheral.py

Dependencies:
  sudo apt-get install python3-dbus python3-gi gir1.2-glib-2.0 bluez
  pip3 install python-rtmidi
"""

import sys
import time
import threading
import logging

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

try:
    import rtmidi
except ImportError:
    sys.exit("Missing: pip3 install python-rtmidi")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── BLE MIDI spec (MMA/AMEI) ───────────────────────────────────────────────────
MIDI_SERVICE_UUID = "03b80e5a-ede8-4b33-a751-6ce34ec4c700"
MIDI_IO_CHAR_UUID = "7772e5db-3868-4112-a1a9-f2669d106bf3"
DEVICE_NAME = "Pi BT MIDI"

# ── D-Bus interface constants ──────────────────────────────────────────────────
BLUEZ_SERVICE        = "org.bluez"
GATT_MANAGER_IFACE   = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADV_IFACE         = "org.bluez.LEAdvertisement1"
GATT_SERVICE_IFACE   = "org.bluez.GattService1"
GATT_CHRC_IFACE      = "org.bluez.GattCharacteristic1"
DBUS_OM_IFACE        = "org.freedesktop.DBus.ObjectManager"
DBUS_PROPS_IFACE     = "org.freedesktop.DBus.Properties"
ADAPTER_IFACE        = "org.bluez.Adapter1"


# ── BLE MIDI packet encoding / decoding ───────────────────────────────────────

def encode_ble_midi(midi_bytes):
    """Pack MIDI bytes into a BLE MIDI packet with a 13-bit timestamp."""
    ts = int(time.monotonic() * 1000) & 0x1FFF       # 13-bit ms
    header  = 0x80 | ((ts >> 7) & 0x3F)              # bits 12-7
    ts_byte = 0x80 | (ts & 0x7F)                     # bits  6-0
    return bytes([header, ts_byte]) + bytes(midi_bytes)


def decode_ble_midi(data):
    """
    Decode a BLE MIDI packet into a list of MIDI messages (each a bytearray).

    Packet layout:
      [Header] [Timestamp] [Status] [Data...] [Timestamp] [Status] [Data...] ...
    Header/timestamp bytes have MSB=1; MIDI data bytes have MSB=0.
    """
    if len(data) < 3:
        return []

    messages = []
    i = 1             # skip header byte
    running_status = None

    while i < len(data):
        # Timestamp byte (MSB=1, required before each MIDI message)
        if not (data[i] & 0x80):
            i += 1
            continue
        i += 1        # consume timestamp

        if i >= len(data):
            break

        # Status or running-status data byte
        if data[i] & 0x80:
            running_status = data[i]
            status = data[i]
            i += 1
        elif running_status:
            status = running_status
        else:
            i += 1
            continue

        # SysEx
        if status == 0xF0:
            sysex = [status]
            while i < len(data):
                b = data[i]
                i += 1
                if b & 0x80:          # timestamp byte or SysEx end
                    if b == 0xF7 or (i < len(data) and data[i] == 0xF7):
                        sysex.append(0xF7)
                        break
                    # embedded timestamp → next byte is SysEx end or data
                    continue
                sysex.append(b)
                if b == 0xF7:
                    break
            messages.append(bytearray(sysex))
            running_status = None
            continue

        # Number of data bytes expected
        stype = status & 0xF0
        if stype in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
            n_data = 2
        elif stype in (0xC0, 0xD0):
            n_data = 1
        elif status == 0xF2:          # Song Position Pointer
            n_data = 2
        elif status == 0xF3:          # Song Select
            n_data = 1
        else:
            n_data = 0                # single-byte realtime/system

        msg = [status]
        while len(msg) - 1 < n_data and i < len(data):
            if data[i] & 0x80:        # timestamp or status = stop collecting
                break
            msg.append(data[i])
            i += 1

        if len(msg) == 1 + n_data:
            messages.append(bytearray(msg))

    return messages


# ── ALSA MIDI port ─────────────────────────────────────────────────────────────

class AlsaBridge:
    """Virtual ALSA MIDI in/out port named 'Pi BT MIDI'."""

    def __init__(self):
        self.midi_in  = rtmidi.MidiIn()
        self.midi_out = rtmidi.MidiOut()
        self.midi_in.open_virtual_port(DEVICE_NAME)
        self.midi_out.open_virtual_port(DEVICE_NAME)
        log.info("ALSA virtual port opened: '%s'", DEVICE_NAME)

    def send(self, midi_bytes):
        """Send bytes out the ALSA port (to whatever is connected on the Mac)."""
        self.midi_out.send_message(list(midi_bytes))

    def poll(self):
        """Return the next incoming ALSA MIDI message or None."""
        return self.midi_in.get_message()

    def close(self):
        self.midi_in.close_port()
        self.midi_out.close_port()


# ── D-Bus GATT helpers ─────────────────────────────────────────────────────────

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"


# ── BLE MIDI Characteristic ────────────────────────────────────────────────────

class MidiCharacteristic(dbus.service.Object):
    PATH = "/com/pi/midi/service0/char0"

    def __init__(self, bus, alsa):
        self.alsa = alsa
        self.notifying = False
        dbus.service.Object.__init__(self, bus, self.PATH)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service":    dbus.ObjectPath("/com/pi/midi/service0"),
                "UUID":       MIDI_IO_CHAR_UUID,
                "Flags":      dbus.Array(["read", "write-without-response", "notify"], signature="s"),
            }
        }

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        # Return an empty BLE MIDI packet (timestamp only, no messages)
        ts = int(time.monotonic() * 1000) & 0x1FFF
        return dbus.Array([0x80 | ((ts >> 7) & 0x3F), 0x80 | (ts & 0x7F)], signature="y")

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        """Incoming BLE MIDI from Mac/iOS → ALSA."""
        data = bytes(value)
        messages = decode_ble_midi(data)
        for msg in messages:
            log.debug("BLE→ALSA: %s", msg.hex())
            self.alsa.send(msg)

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        log.info("Client subscribed to notifications")

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False
        log.info("Client unsubscribed from notifications")

    def notify_midi(self, midi_bytes):
        """ALSA → BLE MIDI notification to connected client."""
        if not self.notifying:
            return
        packet = encode_ble_midi(midi_bytes)
        value = dbus.Array(list(packet), signature="y")
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])
        log.debug("ALSA→BLE: %s", bytes(midi_bytes).hex())

    @dbus.service.signal(DBUS_PROPS_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


# ── BLE MIDI Service ───────────────────────────────────────────────────────────

class MidiService(dbus.service.Object):
    PATH = "/com/pi/midi/service0"

    def __init__(self, bus, alsa):
        self.chrc = MidiCharacteristic(bus, alsa)
        dbus.service.Object.__init__(self, bus, self.PATH)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    def get_characteristics(self):
        return [self.chrc]

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID":    MIDI_SERVICE_UUID,
                "Primary": dbus.Boolean(True),
            }
        }

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]


# ── GATT Application ───────────────────────────────────────────────────────────

class MidiApplication(dbus.service.Object):
    PATH = "/com/pi/midi"

    def __init__(self, bus, alsa):
        self.service = MidiService(bus, alsa)
        dbus.service.Object.__init__(self, bus, self.PATH)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        resp = {}
        resp[self.service.get_path()] = self.service.get_properties()
        for chrc in self.service.get_characteristics():
            resp[chrc.get_path()] = chrc.get_properties()
        return resp


# ── BLE Advertisement ──────────────────────────────────────────────────────────

class MidiAdvertisement(dbus.service.Object):
    PATH = "/com/pi/midi/advertisement0"

    def __init__(self, bus):
        self.ad_type = "peripheral"
        dbus.service.Object.__init__(self, bus, self.PATH)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADV_IFACE:
            raise InvalidArgsException()
        return {
            "Type":        dbus.String(self.ad_type),
            "ServiceUUIDs": dbus.Array([MIDI_SERVICE_UUID], signature="s"),
            "LocalName":   dbus.String(DEVICE_NAME),
            "Includes":    dbus.Array(["tx-power"], signature="s"),
        }

    @dbus.service.method(LE_ADV_IFACE)
    def Release(self):
        log.info("Advertisement released")


# ── Adapter helpers ────────────────────────────────────────────────────────────

def find_adapter(bus):
    """Return the path of the first bluetooth adapter that supports GATT."""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE, "/"), DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for path, ifaces in objects.items():
        if GATT_MANAGER_IFACE in ifaces:
            return path
    return None


def configure_adapter(bus, adapter_path):
    """Set adapter powered, discoverable, and set the local name."""
    adapter_props = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE, adapter_path), DBUS_PROPS_IFACE
    )
    adapter_props.Set(ADAPTER_IFACE, "Powered",       dbus.Boolean(True))
    adapter_props.Set(ADAPTER_IFACE, "Discoverable",  dbus.Boolean(True))
    adapter_props.Set(ADAPTER_IFACE, "Pairable",      dbus.Boolean(True))
    adapter_props.Set(ADAPTER_IFACE, "Alias",         dbus.String(DEVICE_NAME))
    log.info("Adapter configured: %s → '%s'", adapter_path, DEVICE_NAME)


# ── ALSA poll thread ───────────────────────────────────────────────────────────

def alsa_poll_loop(alsa, chrc, stop_event):
    """Poll ALSA for incoming MIDI and forward to BLE characteristic."""
    while not stop_event.is_set():
        msg = alsa.poll()
        if msg:
            data, _ = msg
            chrc.notify_midi(data)
        else:
            time.sleep(0.001)   # 1 ms


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # Find adapter
    adapter_path = find_adapter(bus)
    if not adapter_path:
        log.error("No bluetooth adapter found — is bluez running?")
        sys.exit(1)

    configure_adapter(bus, adapter_path)

    # Open ALSA bridge
    alsa = AlsaBridge()

    # Build GATT application
    app = MidiApplication(bus, alsa)

    # Register GATT application
    gatt_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE, adapter_path), GATT_MANAGER_IFACE
    )
    gatt_manager.RegisterApplication(
        app.get_path(), {},
        reply_handler=lambda: log.info("GATT application registered"),
        error_handler=lambda e: log.error("GATT registration failed: %s", e),
    )

    # Register advertisement
    adv = MidiAdvertisement(bus)
    adv_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE, adapter_path), LE_ADV_MANAGER_IFACE
    )
    adv_manager.RegisterAdvertisement(
        adv.get_path(), {},
        reply_handler=lambda: log.info("Advertisement registered — '%s' is now visible", DEVICE_NAME),
        error_handler=lambda e: log.error("Advertisement registration failed: %s", e),
    )

    # Start ALSA poll thread
    stop_event = threading.Event()
    poll_thread = threading.Thread(
        target=alsa_poll_loop,
        args=(alsa, app.service.chrc, stop_event),
        daemon=True,
    )
    poll_thread.start()

    log.info("BLE MIDI peripheral running — connect from Audio MIDI Setup → Bluetooth")
    log.info("ALSA port: '%s'", DEVICE_NAME)

    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        stop_event.set()
        alsa.close()


if __name__ == "__main__":
    main()
