# System card USB VBUS sense, routed digital model

The system card is self-powered. Host VBUS is sensed at both Type-C VBUS
contacts, reduced by R10 (10 kΩ) and R22 (100 kΩ), then switches Q1
(2N7002). R23 (10 kΩ) pulls the RP2040 GPIO29 input high without host
VBUS. With host VBUS, Q1 pulls `USB_nVBUS` low; the real sysctl firmware
then enables its USB device. `hw/cosim/gen_top.py` binds the exact netlist
pads and values before passing `sysctl_usb_vbus_connected` to the native
machine.

On the current routed system board, the six checked copper legs are:

| Net | From | To | Route (mm) |
| --- | --- | --- | ---: |
| USB_VBUS | J1.A4B9 | R10.1 | 33.430 |
| USB_VBUS | J1.B4A9 | R10.1 | 36.801 |
| VBUS_GATE | R10.2 | Q1.1 | 5.089 |
| VBUS_GATE | R10.2 | R22.1 | 3.183 |
| USB_nVBUS | Q1.3 | U1.41 | 35.263 |
| USB_nVBUS | R23.2 | U1.41 | 32.216 |

`test/hw/test_cosim_sysctl_vbus.py` changes each resistor value in a private
netlist copy and removes R10.2's two launch tracks in a private PCB copy.
The open path restores all three strict coverage gaps. Its generated top
drives GPIO29 high; the native sysctl firmware does not answer PING. The
intact routed path with host VBUS answers PING in both Type-C orientations,
and absence of host VBUS does not. A private open of J1.A4B9 leaves
orientation B operational but suppresses PING in orientation A; strict
coverage still rejects that incomplete branch. The native probe runs with
an erased ROM to isolate sysctl USB behavior from the chipset boot path.

The model uses an ideal digital threshold for Q1. It does not establish
transistor corner behavior, USB VBUS voltage limits, ESD behavior, supply
integrity or physical return continuity. The `+3V3` and `GND` nets remain
in strict unmodeled coverage; the Type-C CDC D+/D− route is checked by its
separate model.
