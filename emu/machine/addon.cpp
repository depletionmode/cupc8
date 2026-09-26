// machine.node: the native whole machine (machine.h) for Node; the API is
// wrapped by test/emu/machinenative.mjs into machine.mjs's Machine.
//
//   const h = create({ slots: { 1: 'hdmi' }, rom, sysctl, root, espTx, espRx, threaded, spiLog })
//   powerOn(h)  runFor(h, ns)  ns(h)  state(h)  frame(h)  screen(h)  type(h, text)
//   press(h, mods, key)  cdcWrite(h, buffer, port)  cdcRead(h, port)  setThreaded(h, on)
//   consoleOpen(h, on)   (the system card's ports: 0 the sysctl protocol, 1 the console)
//   stats(h)  cards(h)  spiLog(h, slot)  keyboard(h)  destroy(h)
//   sdInsert(h, image, {highCapacity, writeProtect, initMs, readUs, writeMs, ncr})
//   sdRemove(h)  sdCard(h) -> null | {initialised, blocks, violations, stats}
#include <node_api.h>

#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>

#include "../../soc/emu/board.h"
#include "machine.h"

using machine::Machine;

#define CALL(e)                                         \
  do {                                                  \
    if ((e) != napi_ok) {                               \
      napi_throw_error(env, nullptr, "napi: " #e);      \
      return nullptr;                                   \
    }                                                   \
  } while (0)

namespace {

struct Args {
  napi_value argv[4];
  size_t argc = 4;
};

bool getArgs(napi_env env, napi_callback_info info, Args &a) {
  return napi_get_cb_info(env, info, &a.argc, a.argv, nullptr, nullptr) == napi_ok;
}

Machine *handle(napi_env env, napi_value v) {
  void *p = nullptr;
  if (napi_get_value_external(env, v, &p) != napi_ok || !p) throw std::runtime_error("not a machine handle");
  Machine *m = static_cast<std::unique_ptr<Machine> *>(p)->get();
  if (!m) throw std::runtime_error("the machine has been destroyed");
  return m;
}

std::unique_ptr<Machine> *holder(napi_env env, napi_value v) {
  void *p = nullptr;
  if (napi_get_value_external(env, v, &p) != napi_ok || !p) throw std::runtime_error("not a machine handle");
  return static_cast<std::unique_ptr<Machine> *>(p);
}

napi_value prop(napi_env env, napi_value o, const char *k) {
  napi_value v = nullptr;
  bool has = false;
  napi_has_named_property(env, o, k, &has);
  if (has) napi_get_named_property(env, o, k, &v);
  return v;
}

bool isType(napi_env env, napi_value v, napi_valuetype t) {
  napi_valuetype got;
  return v && napi_typeof(env, v, &got) == napi_ok && got == t;
}

std::string str(napi_env env, napi_value v) {
  size_t n = 0;
  napi_get_value_string_utf8(env, v, nullptr, 0, &n);
  std::string s(n, '\0');
  napi_get_value_string_utf8(env, v, s.data(), n + 1, &n);
  return s;
}

napi_value num(napi_env env, double d) {
  napi_value v;
  napi_create_double(env, d, &v);
  return v;
}

napi_value jsstr(napi_env env, const std::string &s) {
  napi_value v;
  napi_create_string_utf8(env, s.data(), s.size(), &v);
  return v;
}

napi_value buffer(napi_env env, const void *data, size_t n) {
  napi_value v;
  void *out;
  napi_create_buffer_copy(env, n, data, &out, &v);
  return v;
}

void set(napi_env env, napi_value o, const char *k, napi_value v) { napi_set_named_property(env, o, k, v); }

// every entry point: C++ exceptions become JS errors
template <class F>
napi_value guard(napi_env env, F &&f) {
  try {
    return f();
  } catch (const std::exception &e) {
    napi_throw_error(env, nullptr, e.what());
    return nullptr;
  }
}

napi_value js_create(napi_env env, napi_callback_info info) {
  Args a;
  CALL(getArgs(env, info, a) ? napi_ok : napi_generic_failure);
  return guard(env, [&]() -> napi_value {
    napi_value o = a.argv[0];
    Machine::Options opt;
    if (napi_value slots = prop(env, o, "slots"); isType(env, slots, napi_object)) {
      napi_value keys;
      napi_get_property_names(env, slots, &keys);
      uint32_t n;
      napi_get_array_length(env, keys, &n);
      for (uint32_t i = 0; i < n; i++) {
        napi_value k, v;
        napi_get_element(env, keys, i, &k);
        napi_get_property(env, slots, k, &v);
        napi_value ks;
        napi_coerce_to_string(env, k, &ks);
        opt.slots[std::stoi(str(env, ks))] = str(env, v);
      }
    }
    if (napi_value rom = prop(env, o, "rom")) {
      void *data;
      size_t len;
      if (napi_get_buffer_info(env, rom, &data, &len) != napi_ok) throw std::runtime_error("rom: not a Buffer");
      opt.rom.assign(static_cast<uint8_t *>(data), static_cast<uint8_t *>(data) + len);
    }
    auto flag = [&](const char *k, bool dflt) {
      napi_value v = prop(env, o, k);
      bool b = dflt;
      if (isType(env, v, napi_boolean)) napi_get_value_bool(env, v, &b);
      return b;
    };
    auto integer = [&](const char *k, int dflt) {
      napi_value v = prop(env, o, k);
      int32_t i = dflt;
      if (isType(env, v, napi_number)) napi_get_value_int32(env, v, &i);
      return i;
    };
    opt.sysctl = flag("sysctl", false);
    opt.threaded = flag("threaded", true);
    opt.spiLog = flag("spiLog", false);
    opt.espTx = integer("espTx", -1);
    opt.espRx = integer("espRx", -1);
    if (napi_value r = prop(env, o, "root"); isType(env, r, napi_string)) opt.root = str(env, r);
    auto *h = new std::unique_ptr<Machine>(std::make_unique<Machine>(opt));
    napi_value ext;
    napi_create_external(
        env, h, [](napi_env, void *p, void *) { delete static_cast<std::unique_ptr<Machine> *>(p); }, nullptr, &ext);
    return ext;
  });
}

#define ENTRY(name, ...)                                            \
  napi_value name(napi_env env, napi_callback_info info) {           \
    Args a;                                                          \
    CALL(getArgs(env, info, a) ? napi_ok : napi_generic_failure);    \
    return guard(env, [&]() -> napi_value {                          \
      Machine *m = handle(env, a.argv[0]);                           \
      (void)m;                                                       \
      __VA_ARGS__                                                    \
    });                                                              \
  }

ENTRY(js_powerOn, { m->powerOn(); return nullptr; })

ENTRY(js_runFor, {
  double ns;
  napi_get_value_double(env, a.argv[1], &ns);
  m->runFor(ns);
  return nullptr;
})

ENTRY(js_ns, { return num(env, m->ns()); })

ENTRY(js_setThreaded, {
  bool on = true;
  napi_get_value_bool(env, a.argv[1], &on);
  m->setThreaded(on);
  return nullptr;
})

ENTRY(js_state, {
  const auto s = m->state();
  napi_value o;
  napi_create_object(env, &o);
  set(env, o, "pc", num(env, s.pc));
  set(env, o, "sp", num(env, s.sp));
  set(env, o, "r0", num(env, s.r0));
  set(env, o, "r1", num(env, s.r1));
  set(env, o, "halted", num(env, s.halted));
  set(env, o, "nrst", num(env, s.nrst));
  set(env, o, "gpo", num(env, s.gpo));
  return o;
})

ENTRY(js_frame, {
  const auto f = m->frame();
  napi_value o;
  napi_create_object(env, &o);
  if (!f.error.empty()) {
    set(env, o, "error", jsstr(env, f.error));
  } else {
    // a Uint32Array over a copy of the pixels, as tmds.mjs's frame() returns
    napi_value ab, arr;
    void *data;
    napi_create_arraybuffer(env, f.rgb.size() * 4, &data, &ab);
    std::memcpy(data, f.rgb.data(), f.rgb.size() * 4);
    napi_create_typedarray(env, napi_uint32_array, f.rgb.size(), ab, 0, &arr);
    set(env, o, "rgb", arr);
    set(env, o, "firstLine", num(env, static_cast<double>(f.firstLine)));
  }
  return o;
})

ENTRY(js_screen, {
  std::string err;
  const auto rows = m->screen(&err);
  napi_value o;
  napi_create_object(env, &o);
  if (!err.empty()) {
    set(env, o, "error", jsstr(env, err));
  } else {
    napi_value arr;
    napi_create_array_with_length(env, rows.size(), &arr);
    for (size_t i = 0; i < rows.size(); i++) napi_set_element(env, arr, static_cast<uint32_t>(i), jsstr(env, rows[i]));
    set(env, o, "text", arr);
  }
  return o;
})

// the e-ink panel's glass: { w, h, seq, grey: Uint8Array (0 black ... 255
// white), refreshes: [clean, fast, grey, partial], busy, errors, error,
// partialsSinceFull, bytesWithoutCs, asleep (the controller in deep sleep,
// 1/0) }, or null with no e-ink card
ENTRY(js_panel, {
  machine::EinkPanel *p = m->panel();
  napi_value o;
  if (!p) {
    napi_get_null(env, &o);
    return o;
  }
  const auto pic = p->picture();
  napi_create_object(env, &o);
  set(env, o, "w", num(env, pic.w));
  set(env, o, "h", num(env, pic.h));
  set(env, o, "seq", num(env, pic.seq));
  napi_value ab, arr;
  void *data;
  napi_create_arraybuffer(env, pic.grey.size(), &data, &ab);
  std::memcpy(data, pic.grey.data(), pic.grey.size());
  napi_create_typedarray(env, napi_uint8_array, pic.grey.size(), ab, 0, &arr);
  set(env, o, "grey", arr);
  napi_value r;
  napi_create_array_with_length(env, 4, &r);
  for (uint32_t i = 0; i < 4; i++) napi_set_element(env, r, i, num(env, p->m.refreshes[i]));
  set(env, o, "refreshes", r);
  set(env, o, "busy", num(env, p->m.busy_op));
  set(env, o, "errors", num(env, p->m.errors));
  set(env, o, "error", jsstr(env, p->m.error));
  set(env, o, "partialsSinceFull", num(env, p->m.partials_since_full));
  set(env, o, "maxPartialsBetweenFulls", num(env, p->m.max_partials_between_fulls));
  set(env, o, "bytesWithoutCs", num(env, p->bytesWithoutCs));
  set(env, o, "asleep", num(env, p->m.asleep ? 1 : 0));
  return o;
})

ENTRY(js_panelScreen, {
  std::string err;
  const auto rows = m->panelScreen(&err);
  napi_value o;
  napi_create_object(env, &o);
  if (!err.empty()) {
    set(env, o, "error", jsstr(env, err));
  } else {
    napi_value arr;
    napi_create_array_with_length(env, rows.size(), &arr);
    for (size_t i = 0; i < rows.size(); i++) napi_set_element(env, arr, static_cast<uint32_t>(i), jsstr(env, rows[i]));
    set(env, o, "text", arr);
  }
  return o;
})

ENTRY(js_type, {
  m->type(str(env, a.argv[1]));
  return nullptr;
})

ENTRY(js_press, {
  if (!m->keyboard) throw std::runtime_error("no IO card (no keyboard)");
  // press(h, mods, [k1..k6]): UsbKeyboard.press(mods, ...keys)
  uint32_t mods = 0;
  napi_get_value_uint32(env, a.argv[1], &mods);
  std::vector<uint32_t> keys;
  bool isArr = false;
  if (a.argc > 2) napi_is_array(env, a.argv[2], &isArr);
  if (isArr) {
    uint32_t n;
    napi_get_array_length(env, a.argv[2], &n);
    for (uint32_t i = 0; i < n; i++) {
      napi_value v;
      napi_get_element(env, a.argv[2], i, &v);
      uint32_t k = 0;  // undefined / NaN: Uint8Array.from stores 0
      if (isType(env, v, napi_number)) napi_get_value_uint32(env, v, &k);
      keys.push_back(k);
    }
  }
  m->keyboard->press(mods, keys);
  return nullptr;
})

// the port: argument i, 0 (the sysctl protocol) if absent, or 1 (the console)
static uint32_t port(napi_env env, const Args &a, size_t i) {
  uint32_t p = 0;
  if (a.argc > i && isType(env, a.argv[i], napi_number)) napi_get_value_uint32(env, a.argv[i], &p);
  if (p > 1) throw std::runtime_error("the system card has ports 0 and 1");
  return p;
}

ENTRY(js_cdcWrite, {
  if (!m->sysctl) throw std::runtime_error("no system card");
  void *data;
  size_t len;
  if (napi_get_buffer_info(env, a.argv[1], &data, &len) != napi_ok) throw std::runtime_error("cdcWrite: not a Buffer");
  auto *b = static_cast<uint8_t *>(data);
  auto &q = m->sysctl->toCard[port(env, a, 2)];
  q.insert(q.end(), b, b + len);
  return nullptr;
})

ENTRY(js_cdcRead, {
  const uint32_t p = port(env, a, 1);
  if (!m->sysctl || m->sysctl->fromCard[p].empty()) {
    napi_value u;
    napi_get_null(env, &u);
    return u;
  }
  napi_value v = buffer(env, m->sysctl->fromCard[p].data(), m->sysctl->fromCard[p].size());
  m->sysctl->fromCard[p].clear();
  return v;
})

ENTRY(js_consoleOpen, {
  if (!m->sysctl) throw std::runtime_error("no system card");
  bool on = false;
  napi_get_value_bool(env, a.argv[1], &on);
  m->sysctl->openConsole(on);
  return nullptr;
})

ENTRY(js_stats, {
  napi_value o;
  napi_create_object(env, &o);
  set(env, o, "idleWindows", num(env, static_cast<double>(m->stats.idleWindows)));
  set(env, o, "busyIterations", num(env, static_cast<double>(m->stats.busyIterations)));
  set(env, o, "idleClocks", num(env, static_cast<double>(m->stats.idleClocks)));
  set(env, o, "busyClocks", num(env, static_cast<double>(m->stats.busyClocks)));
  set(env, o, "threaded", [&] { napi_value b; napi_get_boolean(env, m->threaded(), &b); return b; }());
  return o;
})

ENTRY(js_cards, {
  napi_value arr;
  napi_create_array(env, &arr);
  uint32_t i = 0;
  auto add = [&](int slot, const std::string &kind, machine::Emu *e, const machine::Rp2040Card *rc = nullptr,
                 const machine::EspCard *esp = nullptr) {
    napi_value o;
    napi_create_object(env, &o);
    set(env, o, "slot", num(env, slot));
    set(env, o, "kind", jsstr(env, kind));
    if (esp) set(env, o, "ns", num(env, static_cast<double>(esp->guestNs)));  // QEMU's clock at its last answer
    if (rc) {
      set(env, o, "csRises", num(env, static_cast<double>(rc->csRises)));
      set(env, o, "csEdges", num(env, static_cast<double>(rc->csEdges)));
    }
    if (e) {
      set(env, o, "ns", num(env, e->ns()));
      set(env, o, "uart", jsstr(env, e->uart));
      set(env, o, "cycles", [&] {
        napi_value c;
        napi_create_array_with_length(env, 2, &c);
        napi_set_element(env, c, 0, num(env, e->mcu->core0.cycles));
        napi_set_element(env, c, 1, num(env, e->mcu->core1.cycles));
        return c;
      }());
    }
    napi_set_element(env, arr, i++, o);
  };
  if (m->sysctl) add(0, "sysctl", &m->sysctl->e);
  for (auto &[slot, c] : m->cards) add(slot, c->kind, c->emu(), dynamic_cast<const machine::Rp2040Card *>(c.get()),
                                       dynamic_cast<const machine::EspCard *>(c.get()));
  return arr;
})

ENTRY(js_spiLog, {
  int32_t slot = 0;
  napi_get_value_int32(env, a.argv[1], &slot);
  napi_value arr;
  napi_create_array(env, &arr);
  for (auto &[s, c] : m->cards) {
    if (s != slot) continue;
    uint32_t i = 0;
    for (auto &f : c->log) {
      napi_value o, bytes, miso;
      napi_create_object(env, &o);
      set(env, o, "start", num(env, f.start));
      set(env, o, "ns", num(env, f.ns));
      napi_create_array_with_length(env, f.bytes.size(), &bytes);
      for (size_t j = 0; j < f.bytes.size(); j++) napi_set_element(env, bytes, static_cast<uint32_t>(j), num(env, f.bytes[j]));
      napi_create_array_with_length(env, f.miso.size(), &miso);
      for (size_t j = 0; j < f.miso.size(); j++) napi_set_element(env, miso, static_cast<uint32_t>(j), num(env, f.miso[j]));
      set(env, o, "bytes", bytes);
      set(env, o, "miso", miso);
      set(env, o, "extra", num(env, f.extra));
      napi_set_element(env, arr, i++, o);
    }
  }
  return arr;
})

ENTRY(js_keyboard, {
  napi_value o;
  if (!m->keyboard) {
    napi_get_null(env, &o);
    return o;
  }
  napi_create_object(env, &o);
  auto &k = *m->keyboard;
  set(env, o, "addr", num(env, k.addr));
  set(env, o, "configured", num(env, k.configured));
  set(env, o, "protocol", num(env, k.protocol));
  set(env, o, "pending", num(env, static_cast<double>(k.reports.size())));
  napi_value leds;
  napi_create_array_with_length(env, k.leds.size(), &leds);
  for (size_t j = 0; j < k.leds.size(); j++) {
    napi_value v;
    if (k.leds[j] < 0)
      napi_get_undefined(env, &v);
    else
      v = num(env, k.leds[j]);
    napi_set_element(env, leds, static_cast<uint32_t>(j), v);
  }
  set(env, o, "leds", leds);
  return o;
})

rp2040js::harness::SdSocket &socket(Machine *m) {
  auto *s = m->sd();
  if (!s) throw std::runtime_error("no storage card (no microSD socket)");
  return *s;
}

ENTRY(js_sdInsert, {
  rp2040js::harness::SdCard::Options o;
  if (a.argc > 2 && isType(env, a.argv[2], napi_object)) {
    auto b = [&](const char *k, bool &out) {
      napi_value v = prop(env, a.argv[2], k);
      if (isType(env, v, napi_boolean)) napi_get_value_bool(env, v, &out);
    };
    auto d = [&](const char *k, double scale, double &out) {
      napi_value v = prop(env, a.argv[2], k);
      if (isType(env, v, napi_number)) {
        napi_get_value_double(env, v, &out);
        out *= scale;
      }
    };
    b("highCapacity", o.highCapacity);
    b("writeProtect", o.writeProtect);
    d("initMs", 1e6, o.initNs);
    d("readUs", 1e3, o.readNs);
    d("writeMs", 1e6, o.writeNs);
    double ncr = o.ncr;
    d("ncr", 1, ncr);
    o.ncr = static_cast<unsigned>(ncr);
  }
  socket(m).insert(str(env, a.argv[1]), o);
  return nullptr;
})

ENTRY(js_sdRemove, {
  socket(m).remove();
  return nullptr;
})

ENTRY(js_sdCard, {
  napi_value o;
  auto *c = socket(m).card();
  if (!c) {
    napi_get_null(env, &o);
    return o;
  }
  napi_create_object(env, &o);
  napi_value b;
  napi_get_boolean(env, c->initialised(), &b);
  set(env, o, "initialised", b);
  set(env, o, "blocks", num(env, static_cast<double>(c->blocks())));
  napi_value v;
  napi_create_array_with_length(env, c->violations.size(), &v);
  for (size_t j = 0; j < c->violations.size(); j++) napi_set_element(env, v, static_cast<uint32_t>(j), jsstr(env, c->violations[j]));
  set(env, o, "violations", v);
  napi_value st;
  napi_create_object(env, &st);
  set(env, st, "commands", num(env, static_cast<double>(c->stats.commands)));
  set(env, st, "blocksRead", num(env, static_cast<double>(c->stats.blocksRead)));
  set(env, st, "blocksWritten", num(env, static_cast<double>(c->stats.blocksWritten)));
  set(env, st, "crcErrors", num(env, static_cast<double>(c->stats.crcErrors)));
  set(env, st, "illegal", num(env, static_cast<double>(c->stats.illegal)));
  set(env, st, "busyNs", num(env, c->stats.busyNs));
  set(env, st, "maxHz", num(env, c->stats.maxHz));
  set(env, st, "maxHzBeforeInit", num(env, c->stats.maxHzBeforeInit));
  set(env, o, "stats", st);
  return o;
})

napi_value js_destroy(napi_env env, napi_callback_info info) {
  Args a;
  CALL(getArgs(env, info, a) ? napi_ok : napi_generic_failure);
  return guard(env, [&]() -> napi_value {
    holder(env, a.argv[0])->reset();
    return nullptr;
  });
}

napi_value init(napi_env env, napi_value exports) {
  const struct {
    const char *name;
    napi_callback fn;
  } fns[] = {
      {"create", js_create},   {"powerOn", js_powerOn},   {"runFor", js_runFor},     {"ns", js_ns},
      {"state", js_state},     {"frame", js_frame},       {"screen", js_screen},     {"type", js_type},
      {"press", js_press},     {"cdcWrite", js_cdcWrite}, {"cdcRead", js_cdcRead}, {"consoleOpen", js_consoleOpen},   {"setThreaded", js_setThreaded},
      {"stats", js_stats},     {"cards", js_cards},       {"spiLog", js_spiLog},     {"keyboard", js_keyboard},
      {"destroy", js_destroy}, {"sdInsert", js_sdInsert}, {"sdRemove", js_sdRemove}, {"sdCard", js_sdCard},
      {"panel", js_panel}, {"panelScreen", js_panelScreen},
  };
  for (auto &f : fns) {
    napi_value v;
    CALL(napi_create_function(env, f.name, NAPI_AUTO_LENGTH, f.fn, nullptr, &v));
    CALL(napi_set_named_property(env, exports, f.name, v));
  }
  return exports;
}

}  // namespace

NAPI_MODULE(NODE_GYP_MODULE_NAME, init)
