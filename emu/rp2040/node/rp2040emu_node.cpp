// rp2040emu.node: the native RP2040 (librp2040emu) and the card-test harness
// (harness/: the Emu loop, SlotHost, TMDS capture) as a Node addon, for
// test/emu/rp2040native.mjs. Every function takes the handle create()
// returned as its first argument. The per-cycle work (PIO, the slot host's
// bit timing, TMDS capture, the PPB write trap, cycle counting) is native;
// JS is called only for the rare events: a slot-host script's next
// operation, pin listeners, SPI/I2C device callbacks, USB CDC data, the trap
// firing and every-N-cycles callbacks.
//
// runUntil(h, cond, ns) calls cond() where the JS Emu does (every 64 steps),
// but only when some JS callback (or a UART byte) has run since it was last
// called; otherwise it reuses the last answer. So cond must depend only on
// state that JS callbacks change (as every card test's does).

#include <node_api.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "emu.h"
#include "sdcard.h"
#include "slothost.h"
#include "tmds.h"
#include "usb/cdc.h"
#include "usb/cdchost.h"
#include "usb/usbkbd.h"

using namespace rp2040js;
using rp2040js::harness::Emu;
using rp2040js::harness::SlotHost;
using rp2040js::harness::TmdsCapture;

namespace {

/** a JS exception is pending: unwind to the N-API entry point */
struct JsException {};

void check(napi_env env, napi_status s) {
  if (s == napi_ok) return;
  bool pending = false;
  napi_is_exception_pending(env, &pending);
  if (pending) throw JsException{};
  const napi_extended_error_info *info = nullptr;
  napi_get_last_error_info(env, &info);
  throw std::runtime_error(std::string("N-API: ") + (info && info->error_message ? info->error_message : "error"));
}

struct Ref {
  napi_ref ref = nullptr;
  explicit operator bool() const { return ref != nullptr; }
};

struct Harness {
  napi_env env;
  Emu emu;
  bool dirty = true;  // a JS callback ran since cond() was last called

  // per-cycle hooks, called in this order (the order the tests chain them)
  std::unique_ptr<SlotHost> host;
  Ref hostResume;
  struct Trap {
    bool installed = false, armed = false, haveAt = false;
    uint32_t offset = 0, mask = 0;
    double k = 0, at = 0, cycles = 0;
    Ref fire;
  } trap;
  struct Every {
    uint64_t n, count = 0;
    Ref fn;
  };
  std::vector<Every> every;
  Ref jsOnCycle;

  std::unique_ptr<TmdsCapture> tmds;
  std::unique_ptr<rp2040js::harness::SdSocket> sd;
  std::vector<std::unique_ptr<UsbKeyboard>> keyboards;
  std::unique_ptr<USBCDC> cdc;
  Ref cdcOnData, cdcOnConnected;
  std::unique_ptr<rp2040js::CdcHost> cdcHost;
  std::vector<Ref> cdcHostOnData;
  Ref cdcHostOnConnected;
  std::array<Ref, 2> spiTx;
  std::array<std::array<Ref, 3>, 2> i2cCb;  // onConnect, onWriteByte, onReadByte
  std::map<int64_t, std::function<void()>> unlisten;
  int64_t nextListener = 0;

  Harness(napi_env env, const std::string &elf, double mhz, double core1Slow)
      : env(env), emu(elf, mhz, core1Slow) {
    emu.onUartByte = [this](uint32_t) { dirty = true; };
  }

  void hold(Ref &r, napi_value fn) {
    if (r.ref) {
      napi_delete_reference(env, r.ref);
      r.ref = nullptr;
    }
    napi_valuetype t;
    check(env, napi_typeof(env, fn, &t));
    if (t == napi_function) check(env, napi_create_reference(env, fn, 1, &r.ref));
  }

  /** call a held JS function; `use` gets its result inside the handle scope */
  template <class Use>
  void call(const Ref &r, size_t argc, const std::function<void(napi_value *)> &args, Use &&use) {
    dirty = true;
    napi_handle_scope scope;
    check(env, napi_open_handle_scope(env, &scope));
    struct Close {
      napi_env env;
      napi_handle_scope s;
      ~Close() { napi_close_handle_scope(env, s); }
    } close{env, scope};
    napi_value fn, global, result;
    check(env, napi_get_reference_value(env, r.ref, &fn));
    check(env, napi_get_global(env, &global));
    napi_value argv[4];
    if (args) args(argv);
    check(env, napi_call_function(env, global, fn, argc, argv, &result));
    use(result);
  }
  void call0(const Ref &r) {
    call(r, 0, nullptr, [](napi_value) {});
  }

  void updateOnCycle() {
    const bool any = host || trap.installed || !every.empty() || jsOnCycle;
    if (!any) {
      emu.onCycle = nullptr;
      return;
    }
    emu.onCycle = [this] {
      if (host) host->tick();
      if (trap.installed && trap.armed) {
        trap.cycles++;
        if (trap.haveAt && trap.cycles - trap.at >= trap.k) {
          trap.armed = false;
          call0(trap.fire);
        }
      }
      for (size_t i = 0; i < every.size(); i++) {
        if (++every[i].count % every[i].n == 0) call0(every[i].fn);
      }
      if (jsOnCycle) call0(jsOnCycle);
    };
  }
};

// ------------------------------------------------------------ argument helpers
struct Args {
  napi_env env;
  size_t argc = 8;
  napi_value argv[8];
  Harness *h = nullptr;
  Args(napi_env env, napi_callback_info info, bool handle = true) : env(env) {
    check(env, napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr));
    if (handle) {
      if (argc < 1) throw std::runtime_error("missing handle");
      void *p = nullptr;
      check(env, napi_get_value_external(env, argv[0], &p));
      h = static_cast<Harness *>(p);
    }
  }
  napi_value at(size_t i) {
    if (i >= argc) {
      napi_value u;
      napi_get_undefined(env, &u);
      return u;
    }
    return argv[i];
  }
  double num(size_t i) {
    double v;
    check(env, napi_get_value_double(env, at(i), &v));
    return v;
  }
  uint32_t u32(size_t i) {
    uint32_t v;
    check(env, napi_get_value_uint32(env, at(i), &v));
    return v;
  }
  int64_t i64(size_t i) {
    int64_t v;
    check(env, napi_get_value_int64(env, at(i), &v));
    return v;
  }
  bool boolean(size_t i) {
    napi_value b;
    check(env, napi_coerce_to_bool(env, at(i), &b));
    bool v;
    check(env, napi_get_value_bool(env, b, &v));
    return v;
  }
  std::string str(size_t i) {
    size_t n;
    check(env, napi_get_value_string_utf8(env, at(i), nullptr, 0, &n));
    std::string s(n, '\0');
    check(env, napi_get_value_string_utf8(env, at(i), s.data(), n + 1, &n));
    return s;
  }
};

napi_value undefined(napi_env env) {
  napi_value u;
  napi_get_undefined(env, &u);
  return u;
}
napi_value number(napi_env env, double v) {
  napi_value r;
  check(env, napi_create_double(env, v, &r));
  return r;
}
napi_value boolean(napi_env env, bool v) {
  napi_value r;
  check(env, napi_get_boolean(env, v, &r));
  return r;
}
napi_value array(napi_env env, const std::vector<uint32_t> &v) {
  napi_value a;
  check(env, napi_create_array_with_length(env, v.size(), &a));
  for (size_t i = 0; i < v.size(); i++) check(env, napi_set_element(env, a, i, number(env, v[i])));
  return a;
}
std::vector<uint32_t> toVector(napi_env env, napi_value a) {
  uint32_t n;
  check(env, napi_get_array_length(env, a, &n));
  std::vector<uint32_t> v(n);
  for (uint32_t i = 0; i < n; i++) {
    napi_value e;
    check(env, napi_get_element(env, a, i, &e));
    int32_t x;  // a JS `>>` sees ToInt32 of the number
    check(env, napi_get_value_int32(env, e, &x));
    v[i] = static_cast<uint32_t>(x);
  }
  return v;
}

template <class F>
napi_value guard(napi_env env, F &&f) {
  try {
    return f();
  } catch (const JsException &) {
    return nullptr;
  } catch (const std::exception &e) {
    bool pending = false;
    napi_is_exception_pending(env, &pending);
    if (!pending) napi_throw_error(env, nullptr, e.what());
    return nullptr;
  }
}

#define ENTRY(name) napi_value name(napi_env env, napi_callback_info info)

// ------------------------------------------------------------ the emulator
ENTRY(create) {
  return guard(env, [&] {
    Args a(env, info, false);
    auto *h = new Harness(env, a.str(0), a.num(1), a.num(2));
    napi_value ext;
    check(env, napi_create_external(
                   env, h, [](napi_env, void *p, void *) { delete static_cast<Harness *>(p); }, nullptr, &ext));
    return ext;
  });
}

ENTRY(ns) {
  return guard(env, [&] {
    Args a(env, info);
    return number(env, a.h->emu.ns());
  });
}

ENTRY(uart) {
  return guard(env, [&] {
    Args a(env, info);
    // String.fromCharCode per byte: latin-1
    const std::string &u = a.h->emu.uart;
    std::u16string s(u.begin(), u.end());
    for (size_t i = 0; i < u.size(); i++) s[i] = static_cast<unsigned char>(u[i]);
    napi_value r;
    check(env, napi_create_string_utf16(env, s.data(), s.size(), &r));
    return r;
  });
}

ENTRY(runUntil) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    napi_value cond = a.at(1);
    const double ns = a.num(2);
    bool last = false;
    h.dirty = true;
    auto test = [&]() -> bool {
      if (!h.dirty) return last;
      h.dirty = false;
      napi_handle_scope scope;
      check(env, napi_open_handle_scope(env, &scope));
      napi_value global, r;
      napi_get_global(env, &global);
      const napi_status s = napi_call_function(env, global, cond, 0, nullptr, &r);
      if (s != napi_ok) {
        napi_close_handle_scope(env, scope);
        check(env, s);
      }
      napi_value b;
      napi_coerce_to_bool(env, r, &b);
      napi_get_value_bool(env, b, &last);
      napi_close_handle_scope(env, scope);
      return last;
    };
    return boolean(env, h.emu.runUntil(test, ns));
  });
}

ENTRY(setOnCycle) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->hold(a.h->jsOnCycle, a.at(1));
    a.h->updateOnCycle();
    return undefined(env);
  });
}

// every(h, n, fn): fn() on every nth cycle from now (a counter of onCycle calls)
ENTRY(every) {
  return guard(env, [&] {
    Args a(env, info);
    Harness::Every e{static_cast<uint64_t>(a.num(1)), 0, {}};
    a.h->hold(e.fn, a.at(2));
    if (e.n < 1) throw std::runtime_error("every: n must be >= 1");
    a.h->every.push_back(std::move(e));
    a.h->updateOnCycle();
    return undefined(env);
  });
}

// ------------------------------------------------------------ PPB write trap
ENTRY(trapInstall) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    h.trap = Harness::Trap{};
    h.trap.installed = true;
    h.trap.offset = a.u32(1);
    h.trap.mask = a.u32(2);
    h.emu.mcu->ppb.onWrite = [&h](uint32_t offset, uint32_t value) {
      auto &t = h.trap;
      if (t.armed && !t.haveAt && offset == t.offset && (value & t.mask)) {
        t.at = t.cycles;
        t.haveAt = true;
      }
    };
    h.updateOnCycle();
    return undefined(env);
  });
}
ENTRY(trapArm) {
  return guard(env, [&] {
    Args a(env, info);
    auto &t = a.h->trap;
    t.armed = true;
    t.haveAt = false;
    t.at = 0;
    t.cycles = 0;
    t.k = a.num(1);
    a.h->hold(t.fire, a.at(2));
    return undefined(env);
  });
}
ENTRY(trapDisarm) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->trap.armed = false;
    return undefined(env);
  });
}
ENTRY(trapRemove) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->trap.installed = a.h->trap.armed = false;
    a.h->emu.mcu->ppb.onWrite = nullptr;
    a.h->updateOnCycle();
    return undefined(env);
  });
}

// irqMaxWait(h, irq, reset): the most cycles core 0's interrupt `irq` has
// waited from pending to its exception entry; reset: start again from 0
ENTRY(irqMaxWait) {
  return guard(env, [&] {
    Args a(env, info);
    auto &core = a.h->emu.mcu->core0;
    const uint32_t irq = a.u32(1);
    if (irq >= 32) throw std::runtime_error("irqMaxWait: irq must be < 32");
    const double wait = core.irqMaxWait[irq];
    if (a.boolean(2)) core.irqMaxWait[irq] = 0;
    return number(env, wait);
  });
}

// ------------------------------------------------------------ pins
ENTRY(pinSet) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->emu.mcu->gpio.at(a.u32(1)).setInputValue(a.boolean(2));
    return undefined(env);
  });
}
// bit 0 inputValue, 1 outputEnable, 2 outputValue
ENTRY(pinGet) {
  return guard(env, [&] {
    Args a(env, info);
    GPIOPin &p = a.h->emu.mcu->gpio.at(a.u32(1));
    return number(env, (p.inputValue() ? 1 : 0) | (p.outputEnable() ? 2 : 0) | (p.outputValue() ? 4 : 0));
  });
}
ENTRY(pinListen) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    auto ref = std::make_shared<Ref>();
    h.hold(*ref, a.at(2));
    const int64_t id = h.nextListener++;
    auto remove = h.emu.mcu->gpio.at(a.u32(1)).addListener([&h, ref](GPIOPinState state, GPIOPinState old) {
      h.call(*ref, 2,
             [&](napi_value *argv) {
               argv[0] = number(h.env, static_cast<double>(state));
               argv[1] = number(h.env, static_cast<double>(old));
             },
             [](napi_value) {});
    });
    h.unlisten[id] = std::move(remove);
    return number(env, static_cast<double>(id));
  });
}
ENTRY(pinUnlisten) {
  return guard(env, [&] {
    Args a(env, info);
    auto it = a.h->unlisten.find(a.i64(1));
    if (it != a.h->unlisten.end()) {
      auto f = std::move(it->second);
      a.h->unlisten.erase(it);
      f();
    }
    return undefined(env);
  });
}

// ------------------------------------------------------------ SPI, I2C, ADC
ENTRY(spiOnTransmit) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    const uint32_t i = a.u32(1);
    h.hold(h.spiTx.at(i), a.at(2));
    if (!h.spiTx[i]) {
      h.emu.mcu->spi[i].onTransmit = nullptr;
    } else {
      h.emu.mcu->spi[i].onTransmit = [&h, i](uint32_t v) {
        h.call(h.spiTx[i], 1, [&](napi_value *argv) { argv[0] = number(h.env, v); }, [](napi_value) {});
      };
    }
    return undefined(env);
  });
}
ENTRY(spiComplete) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->emu.mcu->spi.at(a.u32(1)).completeTransmit(a.u32(2));
    return undefined(env);
  });
}
// i2cOn(h, i, which, fn): which 0 onConnect(addr, mode), 1 onWriteByte(v), 2 onReadByte(ack)
ENTRY(i2cOn) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    const uint32_t i = a.u32(1), which = a.u32(2);
    Ref &r = h.i2cCb.at(i).at(which);
    h.hold(r, a.at(3));
    RPI2C &bus = h.emu.mcu->i2c[i];
    if (!r) throw std::runtime_error("i2cOn: a function is required");
    if (which == 0) {
      bus.onConnect = [&h, &r](uint32_t addr, I2CMode mode) {
        h.call(r, 2,
               [&](napi_value *argv) {
                 argv[0] = number(h.env, addr);
                 argv[1] = number(h.env, static_cast<double>(mode));
               },
               [](napi_value) {});
      };
    } else if (which == 1) {
      bus.onWriteByte = [&h, &r](uint32_t v) {
        h.call(r, 1, [&](napi_value *argv) { argv[0] = number(h.env, v); }, [](napi_value) {});
      };
    } else {
      bus.onReadByte = [&h, &r](bool ack) {
        h.call(r, 1, [&](napi_value *argv) { argv[0] = boolean(h.env, ack); }, [](napi_value) {});
      };
    }
    return undefined(env);
  });
}
// i2cComplete(h, i, which, v): 0 completeConnect(ack), 1 completeWrite(ack), 2 completeRead(value)
ENTRY(i2cComplete) {
  return guard(env, [&] {
    Args a(env, info);
    RPI2C &bus = a.h->emu.mcu->i2c.at(a.u32(1));
    const uint32_t which = a.u32(2);
    if (which == 0) bus.completeConnect(a.boolean(3));
    else if (which == 1) bus.completeWrite(a.boolean(3));
    else bus.completeRead(a.u32(3));
    return undefined(env);
  });
}
ENTRY(adcSet) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->emu.mcu->adc.channelValues.at(a.u32(1)) = a.u32(2);
    return undefined(env);
  });
}
ENTRY(adcGet) {
  return guard(env, [&] {
    Args a(env, info);
    return number(env, a.h->emu.mcu->adc.channelValues.at(a.u32(1)));
  });
}

// ------------------------------------------------------------ USB
ENTRY(kbdCreate) {
  return guard(env, [&] {
    Args a(env, info);
    UsbKeyboard::Options o;
    o.speed = a.u32(1);
    o.interval = a.u32(2);
    a.h->keyboards.push_back(std::make_unique<UsbKeyboard>(o));
    return number(env, static_cast<double>(a.h->keyboards.size() - 1));
  });
}
ENTRY(kbdPress) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->keyboards.at(a.u32(1))->press(a.u32(2), toVector(env, a.at(3)));
    return undefined(env);
  });
}
// { speed, addr, configured, protocol, leds }
ENTRY(kbdState) {
  return guard(env, [&] {
    Args a(env, info);
    UsbKeyboard &k = *a.h->keyboards.at(a.u32(1));
    napi_value o, leds;
    check(env, napi_create_object(env, &o));
    check(env, napi_set_named_property(env, o, "speed", number(env, k.speed_)));
    check(env, napi_set_named_property(env, o, "addr", number(env, k.addr)));
    check(env, napi_set_named_property(env, o, "configured", number(env, k.configured)));
    check(env, napi_set_named_property(env, o, "protocol", number(env, k.protocol)));
    check(env, napi_create_array_with_length(env, k.leds.size(), &leds));
    for (size_t i = 0; i < k.leds.size(); i++)
      check(env, napi_set_element(env, leds, i, k.leds[i] < 0 ? undefined(env) : number(env, k.leds[i])));
    check(env, napi_set_named_property(env, o, "leds", leds));
    return o;
  });
}
ENTRY(usbAttach) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->emu.mcu->usbCtrl.attachDevice(a.h->keyboards.at(a.u32(1)).get());
    return undefined(env);
  });
}
// the USB controller's SIE_CTRL (its PULLUP_EN bit is the D+ pull-up)
ENTRY(usbSieCtrl) {
  return guard(env, [&] {
    Args a(env, info);
    return number(env, a.h->emu.mcu->usbCtrl.readUint32(0x4c));  // SIE_CTRL: a plain read
  });
}
ENTRY(usbDetach) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->emu.mcu->usbCtrl.detachDevice();
    return undefined(env);
  });
}
ENTRY(cdcCreate) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    h.cdc = std::make_unique<USBCDC>(h.emu.mcu->usbCtrl);
    return undefined(env);
  });
}
// cdcOn(h, which, fn): 0 onSerialData(Uint8Array), 1 onDeviceConnected()
ENTRY(cdcOn) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    if (!h.cdc) throw std::runtime_error("no USBCDC");
    if (a.u32(1) == 0) {
      h.hold(h.cdcOnData, a.at(2));
      if (!h.cdcOnData) {
        h.cdc->onSerialData = nullptr;
      } else {
        h.cdc->onSerialData = [&h](const std::vector<uint8_t> &buf) {
          h.call(h.cdcOnData, 1,
                 [&](napi_value *argv) {
                   void *data;
                   napi_value ab;
                   check(h.env, napi_create_arraybuffer(h.env, buf.size(), &data, &ab));
                   if (!buf.empty()) std::memcpy(data, buf.data(), buf.size());
                   check(h.env, napi_create_typedarray(h.env, napi_uint8_array, buf.size(), ab, 0, &argv[0]));
                 },
                 [](napi_value) {});
        };
      }
    } else {
      h.hold(h.cdcOnConnected, a.at(2));
      if (!h.cdcOnConnected) h.cdc->onDeviceConnected = nullptr;
      else h.cdc->onDeviceConnected = [&h] { h.call0(h.cdcOnConnected); };
    }
    return undefined(env);
  });
}
ENTRY(cdcSend) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->cdc->sendSerialByte(a.u32(1));
    return undefined(env);
  });
}
ENTRY(cdcTxCount) {
  return guard(env, [&] {
    Args a(env, info);
    return number(env, a.h->cdc->txFIFO.itemCount());
  });
}

// the composite CDC host (usb/cdchost.h, test/emu/cdchost.mjs)
ENTRY(cdcHostCreate) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    h.cdcHost = std::make_unique<rp2040js::CdcHost>(h.emu.mcu->usbCtrl, a.u32(1));
    h.cdcHostOnData.resize(a.u32(1));
    return undefined(env);
  });
}
// cdcHostOn(h, which, port, fn): 0 port's onSerialData(Uint8Array), 1 onDeviceConnected()
ENTRY(cdcHostOn) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    if (!h.cdcHost) throw std::runtime_error("no CdcHost");
    const uint32_t port = a.u32(2);
    if (a.u32(1) == 0) {
      if (port >= h.cdcHost->ports.size()) throw std::runtime_error("CdcHost: no such port");
      Ref &r = h.cdcHostOnData[port];
      h.hold(r, a.at(3));
      if (!r) {
        h.cdcHost->ports[port].onSerialData = nullptr;
      } else {
        h.cdcHost->ports[port].onSerialData = [&h, &r](const std::vector<uint8_t> &buf) {
          h.call(r, 1,
                 [&](napi_value *argv) {
                   void *data;
                   napi_value ab;
                   check(h.env, napi_create_arraybuffer(h.env, buf.size(), &data, &ab));
                   if (!buf.empty()) std::memcpy(data, buf.data(), buf.size());
                   check(h.env, napi_create_typedarray(h.env, napi_uint8_array, buf.size(), ab, 0, &argv[0]));
                 },
                 [](napi_value) {});
        };
      }
    } else {
      h.hold(h.cdcHostOnConnected, a.at(3));
      if (!h.cdcHostOnConnected) h.cdcHost->onDeviceConnected = nullptr;
      else h.cdcHost->onDeviceConnected = [&h] { h.call0(h.cdcHostOnConnected); };
    }
    return undefined(env);
  });
}
// cdcHostSend(h, port, byte)
ENTRY(cdcHostSend) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->cdcHost->sendSerialByte(a.u32(2), a.u32(1));
    return undefined(env);
  });
}
ENTRY(cdcHostTxCount) {
  return guard(env, [&] {
    Args a(env, info);
    return number(env, a.h->cdcHost->ports.at(a.u32(1)).txFIFO.itemCount());
  });
}
// cdcHostLines(h, port, value): SET_CONTROL_LINE_STATE
ENTRY(cdcHostLines) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->cdcHost->setLines(a.u32(1), a.u32(2));
    return undefined(env);
  });
}
ENTRY(cdcHostPorts) {
  return guard(env, [&] {
    Args a(env, info);
    return number(env, a.h->cdcHost->portCount());
  });
}

// ------------------------------------------------------------ TMDS capture
ENTRY(tmdsCreate) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->tmds = std::make_unique<TmdsCapture>(a.h->emu);
    return undefined(env);
  });
}
ENTRY(tmdsStart) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->tmds->start();
    return undefined(env);
  });
}
ENTRY(tmdsStop) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->tmds->stop();
    return undefined(env);
  });
}
// [Uint16Array blue, green, red, Float64Array times]
ENTRY(tmdsData) {
  return guard(env, [&] {
    Args a(env, info);
    TmdsCapture &t = *a.h->tmds;
    napi_value out;
    check(env, napi_create_array_with_length(env, 4, &out));
    for (uint32_t lane = 0; lane < 3; lane++) {
      const auto &l = t.lanes[lane];
      void *data;
      napi_value ab, ta;
      check(env, napi_create_arraybuffer(env, l.size() * 2, &data, &ab));
      if (!l.empty()) std::memcpy(data, l.data(), l.size() * 2);
      check(env, napi_create_typedarray(env, napi_uint16_array, l.size(), ab, 0, &ta));
      check(env, napi_set_element(env, out, lane, ta));
    }
    void *data;
    napi_value ab, ta;
    check(env, napi_create_arraybuffer(env, t.times.size() * 8, &data, &ab));
    if (!t.times.empty()) std::memcpy(data, t.times.data(), t.times.size() * 8);
    check(env, napi_create_typedarray(env, napi_float64_array, t.times.size(), ab, 0, &ta));
    check(env, napi_set_element(env, out, 3, ta));
    return out;
  });
}

// ------------------------------------------------------------ microSD socket
// sdCreate(h): the socket on SPI1 (storage card pins); sdInsert(h, image,
// {highCapacity, writeProtect, initMs, readUs, writeMs, ncr}); sdRemove(h);
// sdCard(h) -> null | {initialised, busy, blocks, violations, stats}
rp2040js::harness::SdSocket &sdSocket(Harness &h) {
  if (!h.sd) throw std::runtime_error("no SD socket: call sdCreate first");
  return *h.sd;
}
ENTRY(sdCreate) {
  return guard(env, [&] {
    Args a(env, info);
    a.h->sd = std::make_unique<rp2040js::harness::SdSocket>(*a.h->emu.mcu);
    return undefined(env);
  });
}
ENTRY(sdInsert) {
  return guard(env, [&] {
    Args a(env, info);
    rp2040js::harness::SdCard::Options o;
    napi_value opts = a.at(2);
    napi_valuetype t;
    check(env, napi_typeof(env, opts, &t));
    if (t == napi_object) {
      auto get = [&](const char *k, napi_value &v) {
        bool has = false;
        check(env, napi_has_named_property(env, opts, k, &has));
        if (has) check(env, napi_get_named_property(env, opts, k, &v));
        return has;
      };
      napi_value v;
      auto flag = [&](const char *k, bool &out) {
        if (get(k, v)) {
          napi_value b;
          check(env, napi_coerce_to_bool(env, v, &b));
          check(env, napi_get_value_bool(env, b, &out));
        }
      };
      auto num = [&](const char *k, double scale, double &out) {
        if (get(k, v)) {
          check(env, napi_get_value_double(env, v, &out));
          out *= scale;
        }
      };
      flag("highCapacity", o.highCapacity);
      flag("writeProtect", o.writeProtect);
      num("initMs", 1e6, o.initNs);
      num("readUs", 1e3, o.readNs);
      num("writeMs", 1e6, o.writeNs);
      double ncr = o.ncr;
      num("ncr", 1, ncr);
      o.ncr = static_cast<unsigned>(ncr);
    }
    sdSocket(*a.h).insert(a.str(1), o);
    return undefined(env);
  });
}
ENTRY(sdRemove) {
  return guard(env, [&] {
    Args a(env, info);
    sdSocket(*a.h).remove();
    return undefined(env);
  });
}
ENTRY(sdCard) {
  return guard(env, [&] {
    Args a(env, info);
    auto *c = sdSocket(*a.h).card();
    napi_value o;
    if (!c) {
      check(env, napi_get_null(env, &o));
      return o;
    }
    check(env, napi_create_object(env, &o));
    auto put = [&](napi_value obj, const char *k, napi_value v) { check(env, napi_set_named_property(env, obj, k, v)); };
    put(o, "initialised", boolean(env, c->initialised()));
    put(o, "busy", boolean(env, c->busy(a.h->emu.ns())));
    put(o, "blocks", number(env, static_cast<double>(c->blocks())));
    napi_value v;
    check(env, napi_create_array_with_length(env, c->violations.size(), &v));
    for (size_t j = 0; j < c->violations.size(); j++) {
      napi_value sv;
      check(env, napi_create_string_utf8(env, c->violations[j].data(), c->violations[j].size(), &sv));
      check(env, napi_set_element(env, v, static_cast<uint32_t>(j), sv));
    }
    put(o, "violations", v);
    napi_value st;
    check(env, napi_create_object(env, &st));
    put(st, "commands", number(env, static_cast<double>(c->stats.commands)));
    put(st, "blocksRead", number(env, static_cast<double>(c->stats.blocksRead)));
    put(st, "blocksWritten", number(env, static_cast<double>(c->stats.blocksWritten)));
    put(st, "crcErrors", number(env, static_cast<double>(c->stats.crcErrors)));
    put(st, "illegal", number(env, static_cast<double>(c->stats.illegal)));
    put(st, "busyNs", number(env, c->stats.busyNs));
    put(st, "maxHz", number(env, c->stats.maxHz));
    put(st, "maxHzBeforeInit", number(env, c->stats.maxHzBeforeInit));
    put(o, "stats", st);
    return o;
  });
}

// ------------------------------------------------------------ slot host
// hostCreate(h, clkDiv, csSetupNs, byteGapNs, frameGapNs, resume): resume(result)
// is the script's generator.next(result); it returns the next operation:
// undefined (done), a number (wait ns), or [op, ...args] with op 1 byte(out),
// 2 select, 3 deselect, 4 frame(bytes), 5 read(tries, retryNs).
napi_value resultValue(napi_env env, const SlotHost::Result &r) {
  switch (r.kind) {
    case SlotHost::Result::Number:
      return number(env, r.number);
    case SlotHost::Result::Bytes:
      return array(env, r.bytes);
    case SlotHost::Result::Attempts: {
      napi_value a;
      check(env, napi_create_array_with_length(env, r.attempts.size(), &a));
      for (size_t i = 0; i < r.attempts.size(); i++) check(env, napi_set_element(env, a, i, array(env, r.attempts[i])));
      return a;
    }
    default:
      return undefined(env);
  }
}

SlotHost::Op opValue(napi_env env, napi_value v) {
  SlotHost::Op o;
  napi_valuetype t;
  check(env, napi_typeof(env, v, &t));
  if (t == napi_undefined) {
    o.kind = SlotHost::Op::Done;
    return o;
  }
  if (t == napi_number) {
    o.kind = SlotHost::Op::Wait;
    check(env, napi_get_value_double(env, v, &o.ns));
    return o;
  }
  bool isArray = false;
  check(env, napi_is_array(env, v, &isArray));
  if (!isArray) throw std::runtime_error("SlotHost: a script yielded something that is not a number");
  auto el = [&](uint32_t i) {
    napi_value e;
    check(env, napi_get_element(env, v, i, &e));
    return e;
  };
  auto dbl = [&](uint32_t i) {
    double d;
    check(env, napi_get_value_double(env, el(i), &d));
    return d;
  };
  switch (static_cast<int>(dbl(0))) {
    case 1: {
      o.kind = SlotHost::Op::Byte;
      int32_t x;
      check(env, napi_get_value_int32(env, el(1), &x));
      o.bytes = {static_cast<uint32_t>(x)};
      break;
    }
    case 2:
      o.kind = SlotHost::Op::Select;
      break;
    case 3:
      o.kind = SlotHost::Op::Deselect;
      break;
    case 4:
      o.kind = SlotHost::Op::Frame;
      o.bytes = toVector(env, el(1));
      break;
    case 5:
      o.kind = SlotHost::Op::Read;
      o.tries = dbl(1);
      o.ns = dbl(2);
      break;
    default:
      throw std::runtime_error("SlotHost: unknown operation");
  }
  return o;
}

ENTRY(hostCreate) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    h.host = std::make_unique<SlotHost>(h.emu, a.num(1), a.num(2), a.num(3), a.num(4));
    h.hold(h.hostResume, a.at(5));
    h.updateOnCycle();
    return undefined(env);
  });
}
ENTRY(hostConfig) {
  return guard(env, [&] {
    Args a(env, info);
    SlotHost &s = *a.h->host;
    s.clkDiv = a.num(1);
    s.csSetupNs = a.num(2);
    s.byteGapNs = a.num(3);
    s.frameGapNs = a.num(4);
    return undefined(env);
  });
}
ENTRY(hostRun) {
  return guard(env, [&] {
    Args a(env, info);
    Harness &h = *a.h;
    h.host->run([&h](const SlotHost::Result &r) {
      SlotHost::Op o;
      h.call(h.hostResume, 1, [&](napi_value *argv) { argv[0] = resultValue(h.env, r); },
             [&](napi_value next) { o = opValue(h.env, next); });
      return o;
    });
    return undefined(env);
  });
}

}  // namespace

static napi_value Init(napi_env env, napi_value exports) {
  const napi_property_descriptor props[] = {
#define FN(name) {#name, nullptr, name, nullptr, nullptr, nullptr, napi_default, nullptr}
      FN(create),     FN(ns),          FN(uart),        FN(runUntil),   FN(setOnCycle), FN(every),
      FN(trapInstall), FN(trapArm),    FN(trapDisarm),  FN(trapRemove), FN(pinSet),     FN(pinGet),
      FN(pinListen),  FN(pinUnlisten), FN(spiOnTransmit), FN(spiComplete), FN(i2cOn),  FN(i2cComplete),
      FN(adcSet),     FN(adcGet),      FN(kbdCreate),   FN(kbdPress),   FN(kbdState),   FN(usbAttach),
      FN(usbDetach),  FN(cdcCreate),   FN(cdcOn),       FN(cdcSend),    FN(cdcTxCount), FN(tmdsCreate),
      FN(tmdsStart),  FN(tmdsStop),    FN(tmdsData),    FN(hostCreate), FN(hostConfig), FN(hostRun),
      FN(sdCreate),   FN(sdInsert),    FN(sdRemove),    FN(sdCard),     FN(irqMaxWait),
      FN(usbSieCtrl),    FN(cdcHostCreate), FN(cdcHostOn), FN(cdcHostSend), FN(cdcHostTxCount), FN(cdcHostLines), FN(cdcHostPorts),
#undef FN
  };
  napi_define_properties(env, exports, sizeof props / sizeof props[0], props);
  return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
