// The whole CUPC/8 machine on the native emulator (emu/machine, build/emu-
// machine/machine.node): the same machine and the same API as machine.mjs's
// Machine, cycle for cycle, with each RP2040 card on its own thread.
//
//   const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage' } });
//   m.sd.insert('card.img', { writeMs: 5 });   // not in machine.mjs: the storage card's microSD
//   m.powerOn();  await m.runAsync(3e9);  m.screen()
//
// With sysctl: true, the system card's two USB serial ports: the first is a
// TCP port for cupc8.py (m.sysctlPort, as machine.mjs), the second is the
// console (doc/proposals/usb-console.md), m.console:
//   m.console.open()  m.console.write('list\r')  await m.runAsync(1e8)  m.console.read()
//   m.console.close()  await m.console.listen(port)   (a TCP client is the terminal)
//
// test_e2e.mjs uses it with CUPC8_EMU=native. CUPC8_EMU_THREADS=0 runs the
// cards serially (the same result, slower). Build:
//   tools/emu_build.sh && cmake -G Ninja -S emu/machine -B build/emu-machine && ninja -C build/emu-machine

import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import { createRequire } from 'node:module';
import path from 'node:path';
import { kernelRom, ROOT } from './romimage.mjs';

const native = createRequire(import.meta.url)(path.join(ROOT, 'build/emu-machine/machine.node'));

// QEMU user networking's port forwards: 'tcp:8080:80' makes the PC's
// 127.0.0.1:8080 reach the card's port 80 (hostfwd)
function hostfwd(forward) {
  return forward.map((f) => {
    const m = /^(tcp|udp):(\d+):(\d+)$/.exec(f);
    if (!m) throw new Error(`machinenative: forward '${f}' is not tcp|udp:HOSTPORT:CARDPORT`);
    return `,hostfwd=${m[1]}:127.0.0.1:${m[2]}-:${m[3]}`;
  }).join('');
}

// The Wi-Fi card's QEMU (tools/qemu_build.sh: Espressif's, with the cupc8
// chardev and slot SPI device), in step with the machine: icount (one
// instruction 8 ns, and an idle guest's clock jumps to its next timer), the
// guest's random numbers from a fixed seed, and the cupc8 chardev's FIFOs,
// which the native EspCard drives (emu/machine/README.md, "The Wi-Fi card").
// pcap: a file for the guest's network traffic (QEMU's filter-dump; guest
// times, plus a whole-seconds offset of the wall clock at start).
function startEsp(image, forward = [], pcap = null) {
  const qemu = path.join(ROOT, 'build/qemu-esp/bin/qemu-system-riscv32');
  if (!fs.existsSync(qemu)) throw new Error(`machinenative: no ${qemu}: run tools/qemu_build.sh`);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-esp-'));
  const fifo = path.join(dir, 'uart1');
  execFileSync('mkfifo', [fifo + '.in', fifo + '.out']);
  const flash = path.join(dir, 'flash.bin');
  fs.copyFileSync(image, flash);
  const proc = spawn(qemu, ['-nographic', '-machine', 'esp32c3', '-monitor', 'none',
    '-icount', 'shift=3,sleep=off', '-seed', '1',
    '-drive', `file=${flash},if=mtd,format=raw`, '-nic', 'user,id=net0,model=open_eth' + hostfwd(forward),
    ...(pcap ? ['-object', `filter-dump,id=dump,netdev=net0,file=${pcap}`] : []),
    '-serial', 'file:' + path.join(dir, 'uart0.log'), '-chardev', `cupc8,id=lockstep,path=${fifo}`],
  { stdio: 'ignore' });
  const tx = fs.openSync(fifo + '.in', 'w');
  const rx = fs.openSync(fifo + '.out', 'r');
  return { proc, tx, rx };
}

// The system card's console port, the PC's side: open() is a terminal
// opening it (DTR; the card then sets HOST and starts moving the rings), and
// what the card sends collects until read(). Like the protocol port, bytes
// move only between runs.
class Console {
  constructor(m) {
    this.m = m;
    this.isOpen = false;
    this.buf = [];
  }
  open() {
    native.consoleOpen(this.m.h, true);
    this.isOpen = true;
  }
  close() {
    native.consoleOpen(this.m.h, false);
    this.isOpen = false;
  }
  // bytes (a string, Buffer or array) typed on the PC
  write(data) {
    native.cdcWrite(this.m.h, Buffer.from(data), 1);
  }
  // everything the card sent since the last read(), as a Buffer
  read() {
    this.m.flush();
    const b = Buffer.concat(this.buf);
    this.buf = [];
    return b;
  }
  received(b) {
    if (this.client) this.client.write(b);
    else this.buf.push(b);
  }
  // a TCP port for a terminal (cupc8.py console --port tcp:127.0.0.1:N, or
  // nc): a connection opens the console, and its end closes it
  listen(port = 0) {
    return new Promise((resolve) => {
      this.server = net.createServer((sock) => {
        this.client?.destroy();
        this.client = sock;
        this.open();
        sock.on('data', (d) => this.write(d));
        sock.on('close', () => {
          if (this.client !== sock) return;
          this.client = null;
          this.close();
        });
        sock.on('error', () => {});
      });
      this.server.listen(port, '127.0.0.1', () => resolve(this.server.address().port));
    });
  }
}

export class Machine {
  // forward: port forwards to the Wi-Fi card, ['tcp:8080:80', 'udp:5353:53'];
  // pcap: a file for the Wi-Fi card's network traffic
  static async create({ slots = { 1: 'hdmi', 2: 'io' }, rom = null, sysctl = false, pwrHi = true,
    hostVbus = true, hostPort = true,
    ioOverload = false,     // a short on the IO card's port: its switch holds FAULT low while EN is high
    resetButtonPressed = false,
    usbOrientation = 'A', chipsetFlash = null, cpuFlash = null, ccLine = 1,
    threaded = process.env.CUPC8_EMU_THREADS !== '0', spiLog = false, forward = [], pcap = null } = {}) {
    const m = new Machine();
    // Co-simulation suites can build the ROM in their Python harness and
    // provide it here. This also avoids Node's synchronous subprocess
    // restriction in sandboxed verification environments.
    const suppliedRom = process.env.CUPC8_TEST_ROM &&
      fs.readFileSync(process.env.CUPC8_TEST_ROM);
    m.rom = rom ?? suppliedRom ?? kernelRom();
    const wifi = Object.entries(slots).filter(([, k]) => k === 'wifi');
    if (wifi.length > 1) throw new Error('machinenative: one Wi-Fi card at most');
    if (forward.length && !wifi.length) throw new Error('machinenative: forward needs a Wi-Fi card');
    hostfwd(forward);                    // a bad entry throws before QEMU starts
    if (wifi.length) m.esp = startEsp(path.join(ROOT, 'build/esp32c3-qemu/flash.bin'), forward, pcap);
    const netlistTop = process.env.CUPC8_COSIM_TOP && JSON.parse(fs.readFileSync(process.env.CUPC8_COSIM_TOP, 'utf8'));
    if (!['A', 'B'].includes(usbOrientation))
      throw new Error('machinenative: USB orientation must be A or B');
    if (netlistTop && (!netlistTop.runtime || !netlistTop.boards?.includes('main')))
      throw new Error('machinenative: invalid schematic-derived top');
    const trips = netlistTop?.runtime.cc_trip_volts;
    if (netlistTop && (!Array.isArray(trips) || trips.length !== 2 || trips.some(v => !Number.isFinite(v))))
      throw new Error('machinenative: invalid Type-C comparator model');
    // pwrHi names the host source class. For the netlist top, drive the
    // comparator with the worst 3 A minimum or 1.5 A maximum CC voltage.
    const pwrHiAtFpga = netlistTop ? (pwrHi ? 1.524 : 1.090) >= Math.max(...trips) : pwrHi;
    if (netlistTop && ['vbus_on', 'nfault_low'].some((k) => typeof netlistTop.runtime.io_vbus?.[k] !== 'boolean'))
      throw new Error('machinenative: missing routed IO VBUS switch model');
    if (netlistTop && typeof netlistTop.runtime.io_usb_host !== 'boolean')
      throw new Error('machinenative: invalid IO USB host path');
    if (netlistTop && typeof netlistTop.runtime.storage_sd_socket !== 'boolean')
      throw new Error('machinenative: invalid storage SD socket path');
    if (netlistTop && (typeof netlistTop.runtime.gpu_hdmi_link !== 'boolean' ||
                      typeof netlistTop.runtime.eink_panel_link !== 'boolean'))
      throw new Error('machinenative: invalid display output path');
    if (netlistTop && typeof netlistTop.runtime.por_connected !== 'boolean')
      throw new Error('machinenative: invalid supervisor reset path');
    if (netlistTop && typeof netlistTop.runtime.cpu_clock_connected !== 'boolean')
      throw new Error('machinenative: invalid CPU clock path');
    if (netlistTop && typeof netlistTop.runtime.cpu_reset_connected !== 'boolean')
      throw new Error('machinenative: invalid CPU reset path');
    if (netlistTop && typeof netlistTop.runtime.chipset_clock_connected !== 'boolean')
      throw new Error('machinenative: invalid chipset clock path');
    if (netlistTop && (typeof netlistTop.runtime.cpu_control_connected?.strobe !== 'boolean' ||
                      typeof netlistTop.runtime.cpu_control_connected?.rw !== 'boolean'))
      throw new Error('machinenative: invalid CPU control route model');
    if (netlistTop && typeof netlistTop.runtime.cpu_ready_connected !== 'boolean')
      throw new Error('machinenative: invalid CPU /RDY route model');
    if (netlistTop && typeof netlistTop.runtime.cpu_sync_connected !== 'boolean')
      throw new Error('machinenative: invalid CPU SYNC route model');
    if (netlistTop && (typeof netlistTop.runtime.cpu_status_connected?.halted !== 'boolean' ||
                      typeof netlistTop.runtime.cpu_status_connected?.waiting !== 'boolean'))
      throw new Error('machinenative: invalid CPU status route model');
    if (netlistTop && (!Array.isArray(netlistTop.runtime.cpu_irq_connected) ||
                      netlistTop.runtime.cpu_irq_connected.length !== 4 ||
                      netlistTop.runtime.cpu_irq_connected.some((connected) =>
                        typeof connected !== 'boolean')))
      throw new Error('machinenative: invalid CPU IRQ route model');
    if (netlistTop && (!Array.isArray(netlistTop.runtime.cpu_tmr_exp_connected) ||
                      netlistTop.runtime.cpu_tmr_exp_connected.length !== 2 ||
                      netlistTop.runtime.cpu_tmr_exp_connected.some((connected) =>
                        typeof connected !== 'boolean')))
      throw new Error('machinenative: invalid CPU timer expiry route model');
    if (netlistTop && typeof netlistTop.runtime.sysctl_manual_reset_connected !== 'boolean')
      throw new Error('machinenative: invalid system manual-reset route model');
    if (netlistTop && typeof netlistTop.runtime.button_manual_reset_connected !== 'boolean')
      throw new Error('machinenative: invalid reset-button route model');
    if (netlistTop && (typeof netlistTop.runtime.system_usb_connected?.A !== 'boolean' ||
                      typeof netlistTop.runtime.system_usb_connected?.B !== 'boolean' ||
                      typeof netlistTop.runtime.system_usb_complete !== 'boolean'))
      throw new Error('machinenative: invalid system USB route model');
    if (netlistTop && typeof netlistTop.runtime.sysctl_usb_vbus_connected !== 'boolean')
      throw new Error('machinenative: invalid system USB VBUS sense route model');
    if (netlistTop && (typeof netlistTop.runtime.sysctl_usb_vbus_contacts?.A !== 'boolean' ||
                      typeof netlistTop.runtime.sysctl_usb_vbus_contacts?.B !== 'boolean'))
      throw new Error('machinenative: invalid system USB VBUS contact model');
    if (typeof hostVbus !== 'boolean')
      throw new Error('machinenative: hostVbus must be boolean');
    if (typeof hostPort !== 'boolean')
      throw new Error('machinenative: hostPort must be boolean');
    if (typeof resetButtonPressed !== 'boolean')
      throw new Error('machinenative: resetButtonPressed must be boolean');
    const gpoLedLinks = netlistTop?.runtime.gpo_led_connected ?? Array(8).fill(true);
    if (!Array.isArray(gpoLedLinks) || gpoLedLinks.length !== 8 ||
        gpoLedLinks.some((connected) => typeof connected !== 'boolean'))
      throw new Error('machinenative: invalid GPO LED route model');
    m.gpoLedLinks = gpoLedLinks;
    const boardKind = { hdmi: 'gpu', io: 'io', storage: 'storage', wifi: 'wifi',
      eink: 'eink', eink750: 'eink' };
    const boot = netlistTop?.runtime.qspi_boot_connected;
    if (netlistTop && !['system', 'gpu', 'io', 'storage', 'eink'].every((kind) =>
      typeof boot?.[kind] === 'boolean'))
      throw new Error('machinenative: missing routed QSPI boot prerequisites');
    // A disconnected MCU-to-flash path prevents that card firmware from
    // starting. The digital model leaves the physically fitted card inert;
    // it does not predict RP2040 boot-ROM fallback or analog open-pin levels.
    // The 12 MHz crystal network is a second boot prerequisite of the same
    // kind: with an open leg the RP2040 has no clock and its firmware never
    // runs. Oscillator start-up margin is analog and is not modeled.
    const crystal = netlistTop?.runtime.crystal_connected;
    if (netlistTop && !['system', 'gpu', 'io', 'storage', 'eink'].every((kind) =>
      typeof crystal?.[kind] === 'boolean'))
      throw new Error('machinenative: missing routed crystal boot prerequisites');
    // The FPGA configuration chain (emu/machine/fpgaconfig.h): CRESET_B,
    // CDONE and both configuration flashes, each link from routed copper.
    const FPGA_LINKS = ['chipsetConfigCopper', 'cpuConfigCopper', 'chipsetCreset', 'cpuCreset',
      'chipsetCdoneSysctl', 'cpuCdoneSysctl', 'cpuCdoneCard', 'cpuCdoneMain', 'cpuCdonePullup',
      'fl0Sysctl', 'fl1Sysctl', 'cdoneLed'];
    const fpgaLinks = netlistTop?.runtime.fpga_links;
    if (netlistTop && !FPGA_LINKS.every((k) => typeof fpgaLinks?.[k] === 'boolean'))
      throw new Error('machinenative: missing routed FPGA configuration links');
    // sysctl's two TCA9555s (emu/machine: Tca9555) on the routed I2C bus. U14
    // P10 is the CPU card's PRSNT2_n (its PRSNT1-PRSNT2 loop, grounded on the
    // main board); P11/P12 the CPU card's ID straps. U14 port 0 carries the
    // slots' PRSNT2_n (a fitted card's loop pulls it low over the routed
    // copper of both boards). Only the CPU presence bit is read by firmware;
    // the rest is visible through expanders().
    const i2c = netlistTop?.runtime.i2c;
    if (netlistTop && (!Array.isArray(i2c?.expanders) || typeof i2c.cpu_present_link !== 'boolean' ||
      !i2c.card_loops || !i2c.slot_presence.every((x) => typeof x.link === 'boolean')))
      throw new Error('machinenative: missing routed I2C expander model');
    const expanders = i2c ? i2c.expanders.filter((x) => x.link).map((x) => {
      const inputs = [0xff, 0xff];
      if (x.address === 0x21) {
        // a slot reads present (PRSNT2_n low) when a card is fitted, its own
        // PRSNT loop is whole and the slot's copper reaches the expander
        for (const { slot, bit, link } of i2c.slot_presence)
          if (bit !== null && slots[slot] && link && i2c.card_loops[boardKind[slots[slot]]]) inputs[0] &= ~(1 << bit);
        if (i2c.cpu_present_link) inputs[1] &= ~1;
        // an ID strap tied to GND on the CPU card reads 0 when its copper reaches the expander
        for (const { bit, level, link } of i2c.card_id) if (!level && link) inputs[1] &= ~(1 << bit);
      }
      return { address: x.address, inputs };
    }) : null;
    // sysctl's ADC (GPIO26-28): the source's CC voltage on the attached CC
    // line (`ccLine`: the power cable's orientation; the other line has only
    // Rd), and the 1V2 rail through R100. Open copper reads 0 V.
    const adc = netlistTop?.runtime.sysctl_adc;
    if (netlistTop && !['cc1', 'cc2', 'v1v2'].every((k) => typeof adc?.[k] === 'boolean'))
      throw new Error('machinenative: missing routed sysctl ADC paths');
    if (![1, 2].includes(ccLine)) throw new Error('machinenative: ccLine must be 1 or 2');
    const ccVolts = pwrHi ? 1.524 : 1.090;
    const sysctlAdcVolts = adc ? [adc.cc1 && ccLine === 1 ? ccVolts : 0,
      adc.cc2 && ccLine === 2 ? ccVolts : 0, adc.v1v2 ? 1.2 : 0] : null;
    const boots = (kind) => boot[kind] !== false && crystal[kind] !== false;
    const activeSlots = netlistTop ? Object.fromEntries(Object.entries(slots).filter(([, kind]) =>
      boots(boardKind[kind]))) : slots;
    const activeSysctl = sysctl && (!netlistTop || boots('system'));
    let memoryWiring = netlistTop?.runtime;
    if (netlistTop) {
      const links = netlistTop.runtime.card_slot_links;
      const signals = ['sck', 'mosi', 'cs', 'miso', 'irq'];
      if (!links || !['gpu', 'io', 'storage', 'wifi', 'eink'].every((kind) =>
        signals.every((signal) => typeof links[kind]?.[signal] === 'boolean')))
        throw new Error('machinenative: missing routed card slot links');
      const slotWiring = netlistTop.runtime.slots.map((mainLink, index) => {
        const installed = slots[index + 1];
        if (!installed) return mainLink;
        const kind = boardKind[installed];
        if (!kind) throw new Error(`machinenative: unknown installed card ${installed}`);
        const cardLink = links[kind];
        return { ...mainLink, ...Object.fromEntries(signals.map((signal) =>
          [`${signal}_connected`, mainLink[`${signal}_connected`] && cardLink[signal]])) };
      });
      memoryWiring = { ...netlistTop.runtime, slots: slotWiring };
    }
    // the card programming port (emu/machine ProgPort): an SWD target in each
    // slot holding an RP2040 card, reachable through the muxes when the copper
    // is whole. Without the netlist top every wire is whole.
    const prog = netlistTop?.runtime.prog_port;
    if (netlistTop && !(Array.isArray(prog?.channel) && Array.isArray(prog?.sel_bit) &&
      Array.isArray(prog?.slot_legs) && prog?.card))
      throw new Error('machinenative: missing routed programming port');
    const progPort = activeSysctl ? {
      selBit: prog?.sel_bit ?? [0, 1, 2], selWhole: prog?.sel_whole ?? [true, true, true],
      clk: prog?.clk ?? true, io: prog?.io ?? true, channel: prog?.channel ?? [0, 1, 2, 3, 4, 5],
      targets: [1, 2, 3, 4, 5, 6].map((slot) => {
        const kind = boardKind[activeSlots[slot]];
        if (!kind || kind === 'wifi') return false;
        return prog ? Boolean(prog.slot_legs[slot - 1] && prog.card[kind]) : true;
      }),
    } : null;
    m.h = native.create({ slots: activeSlots, rom: m.rom, sysctl: activeSysctl, pwrHi: pwrHiAtFpga, root: ROOT, threaded, spiLog,
      sysctlHostVbus: hostVbus && (netlistTop?.runtime.sysctl_usb_vbus_contacts[usbOrientation] ?? true),
      // the keyboard needs VBUS: the switch enable and its output copper
      ioUsbHost: (netlistTop?.runtime.io_usb_host ?? true) && (netlistTop?.runtime.io_vbus?.vbus_on ?? true),
      ioVbusNfaultLow: ioOverload || (netlistTop?.runtime.io_vbus?.nfault_low ?? false),
      storageSdSocket: netlistTop?.runtime.storage_sd_socket ?? true,
      gpuHdmiLink: netlistTop?.runtime.gpu_hdmi_link ?? true,
      einkPanelLink: netlistTop?.runtime.eink_panel_link ?? true,
      porConnected: netlistTop?.runtime.por_connected ?? true,
      cpuClockConnected: netlistTop?.runtime.cpu_clock_connected ?? true,
      cpuResetConnected: netlistTop?.runtime.cpu_reset_connected ?? true,
      cpuStrobeConnected: netlistTop?.runtime.cpu_control_connected.strobe ?? true,
      cpuRwConnected: netlistTop?.runtime.cpu_control_connected.rw ?? true,
      cpuReadyConnected: netlistTop?.runtime.cpu_ready_connected ?? true,
      cpuSyncConnected: netlistTop?.runtime.cpu_sync_connected ?? true,
      cpuHaltedConnected: netlistTop?.runtime.cpu_status_connected.halted ?? true,
      cpuWaitingConnected: netlistTop?.runtime.cpu_status_connected.waiting ?? true,
      sysctlResetConnected: netlistTop?.runtime.sysctl_manual_reset_connected ?? true,
      resetButtonConnected: netlistTop?.runtime.button_manual_reset_connected ?? true,
      resetButtonPressed,
      chipsetClockConnected: netlistTop?.runtime.chipset_clock_connected ?? true,
      memoryWiring,
      ...(fpgaLinks ? { fpga: fpgaLinks } : {}),
      ...(expanders ? { expanders } : {}),
      ...(sysctlAdcVolts ? { sysctlAdcVolts } : {}),
      ...(progPort ? { progPort } : {}),
      ...(chipsetFlash ? { chipsetFlash } : {}),
      ...(cpuFlash ? { cpuFlash } : {}),
      espTx: m.esp?.tx ?? -1, espRx: m.esp?.rx ?? -1 });
    m.kinds = { ...activeSlots };
    m.boardKind = boardKind;
    m.cardLeds = netlistTop?.runtime.card_leds ?? null;
    m.railLeds = netlistTop?.runtime.rail_leds ?? null;
    m.hasSysctl = sysctl;              // fitted (its firmware may not boot: the indicators do not care)
    m.fittedKinds = Object.values(slots);
    if (netlistTop && !['main', 'cpu', 'system', 'gpu', 'io', 'storage', 'wifi', 'eink'].every((board) =>
      Array.isArray(m.railLeds?.[board])))
      throw new Error('machinenative: missing routed rail indicator paths');
    if (netlistTop && !['system', 'gpu', 'io', 'storage', 'eink'].every((kind) =>
      Array.isArray(m.cardLeds?.[kind])))
      throw new Error('machinenative: missing routed card LED paths');
    if (hostPort && activeSysctl && (netlistTop?.runtime.system_usb_connected[usbOrientation] ?? true)) {
      m.sysctlPort = await m.listen();
      m.console = new Console(m);
    }
    if (Object.values(activeSlots).includes('io') && (netlistTop?.runtime.io_usb_host ?? true) &&
        (netlistTop?.runtime.io_vbus?.vbus_on ?? true)) {
      const h = m.h;
      m.keyboard = {
        press: (mods, ...keys) => native.press(h, mods, keys),
        get state() { return native.keyboard(h); },
      };
    }
    if (Object.values(activeSlots).includes('storage') && (netlistTop?.runtime.storage_sd_socket ?? true)) {
      // the storage card's microSD socket (emu/rp2040/harness/sdcard.h): an
      // image file goes in (written through as blocks are programmed), comes out
      const h = m.h;
      m.sd = {
        insert: (image, opts = {}) => native.sdInsert(h, image, opts),
        remove: () => native.sdRemove(h),
        card: () => native.sdCard(h),
      };
    }
    return m;
  }

  // the system card's USB CDC as a TCP port (machine.mjs SysctlCard.listen)
  listen() {
    return new Promise((resolve) => {
      this.server = net.createServer((sock) => {
        this.client = sock;
        sock.on('data', (d) => native.cdcWrite(this.h, d));
      });
      this.server.listen(0, '127.0.0.1', () => resolve(this.server.address().port));
    });
  }

  // what the card sent on its CDC while the machine ran (machine.mjs writes it
  // as it comes; the socket only sends it when the event loop runs anyway)
  flush() {
    const b = native.cdcRead(this.h, 0);
    if (b) this.client?.write(b);
    const c = this.console && native.cdcRead(this.h, 1);
    if (c) this.console.received(c);
  }

  powerOn() {
    native.powerOn(this.h);
  }

  // run the machine for `ns` of emulated time
  runFor(ns) {
    native.runFor(this.h, ns);
    this.flush();
  }

  stop() {
    if (this.h) native.destroy(this.h);
    this.h = null;
    this.server?.close();
    this.client?.destroy();
    this.console?.server?.close();
    this.console?.client?.destroy();
    if (this.esp) {
      this.esp.proc.kill('SIGKILL');  // a lockstep QEMU waits on its FIFO and would not stop on SIGTERM
      fs.closeSync(this.esp.tx);
      fs.closeSync(this.esp.rx);
    }
  }

  // runFor, giving Node's event loop a turn every `slice` (the TCP port for
  // cupc8.py, child processes)
  async runAsync(ns, slice = 2e6) {
    const end = this.ns + ns;
    while (this.ns < end) {
      this.runFor(Math.min(slice, end - this.ns));
      await new Promise((r) => setImmediate(r));
    }
  }

  // run until cond() holds, yielding to the event loop; false after `ns`
  async runUntil(cond, ns, slice = 2e6) {
    const end = this.ns + ns;
    while (this.ns < end) {
      if (cond()) return true;
      await this.runAsync(Math.min(slice, end - this.ns), slice);
    }
    return cond();
  }

  get ns() {
    return native.ns(this.h);
  }

  // the cards' firmware-driven indicator LEDs: [{slot (0: system card), kind,
  // net, gpio, lit, rises}]. With the netlist top an LED whose copper is open
  // never lights; `net` is the MCU-side net the top bound to that GPIO.
  leds() {
    return native.leds(this.h).map(({ slot, gpio, level, rises }) => {
      const kind = slot === 0 ? 'system' : this.boardKind[this.kinds[slot]];
      const row = this.cardLeds ? this.cardLeds[kind]?.find((r) => r.gpio === gpio) : null;
      const connected = this.cardLeds ? Boolean(row?.connected) : true;
      return { slot, kind, gpio, net: row?.net ?? null, lit: connected && level,
        rises: connected ? rises : 0 };
    });
  }

  // The rail indicator LEDs (gen_top.py rail_indicator_routes) of the boards
  // in this machine: [{board, led, rail, lit}]. The rail is assumed present
  // (the power tree is analog), so an indicator is lit while the powered
  // machine's copper legs are whole. Without the netlist top: none.
  powerLeds() {
    if (!this.railLeds) return [];
    const boards = new Set(['main', 'cpu']);
    if (this.hasSysctl) boards.add('system');
    for (const kind of this.fittedKinds) boards.add(this.boardKind[kind]);
    return [...boards].flatMap((board) => (this.railLeds[board] ?? []).map((row) =>
      ({ board, led: row.led, rail: row.rail, lit: row.connected })));
  }

  // the IO card's port switch in a slot: {overload, en, nfaultLow, edges: [[card ns, EN level]]}
  // (emu/machine Rp2040Card::vbus), or null with no IO card there
  ioVbus(slot) {
    return native.ioVbus(this.h, slot);
  }

  // the SWD target in a slot (1-6): {resets, calls, flash} as `cupc8.py card
  // flash` left it, or null (no RP2040 card there, or its debug copper is open)
  progTarget(slot) {
    return native.progTarget(this.h, slot);
  }

  // sysctl's expanders now: [{address, pins: [port0, port1]}] (a test hook)
  expanders() {
    return native.expanders(this.h);
  }

  state() {
    const state = native.state(this.h);
    state.gpoLeds = this.gpoLedLinks.map((connected, bit) =>
      connected && Boolean(state.gpo & (1 << bit)));
    return state;
  }

  // a whole frame from the GPU's TMDS output: { rgb: Uint32Array(640*480) } or { error }
  frame() {
    const f = native.frame(this.h);
    this.flush();
    return f;
  }

  // the text on screen, 80x30: { text: [...] } or { error }
  screen() {
    const s = native.screen(this.h);
    this.flush();
    return s;
  }

  // the e-ink card's panel: the glass as of its last completed refresh,
  // { w, h, seq, grey: Uint8Array, refreshes, busy, errors, error, ... }, or null
  panel() {
    return native.panel(this.h);
  }

  // the text on the e-ink panel's glass, 80x30: { text: [...] } or { error }
  panelScreen() {
    return native.panelScreen(this.h);
  }

  // type on the USB keyboard: one report per key, then a release
  type(text) {
    native.type(this.h, text);
  }

  // not in machine.mjs: for comparing runs
  setThreaded(on) { native.setThreaded(this.h, on); }
  stats() { return native.stats(this.h); }
  cards() { return native.cards(this.h); }
  spiLog(slot) { return native.spiLog(this.h, slot); }
}
