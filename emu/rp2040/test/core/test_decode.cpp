// test_decode: CortexM0Core's decode table against the if/else chain it was
// generated from (EMU-005, `decode`).
//
//   test_decode [--seed N] [--wide-samples N]
//
// 1. CortexM0Core::verifyDecodeTable(): for all 65536 opcodes, the table's
//    entry branch is one no earlier branch of the chain can precede, for every
//    second halfword the decoder can pass (0, or all 65536 for a 32-bit
//    instruction).
// 2. Execution: every opcode (and, for the 32-bit ones, --wide-samples second
//    halfwords: every class of the chain's opcode2 tests plus random ones) runs
//    on two chips in the same random state, one through executeInstruction()
//    (the table) and one through executeInstructionChain() (the chain from its
//    first branch); the core state, the returned cycles, the logger messages,
//    breakpoints and an SRAM hash must be the same.
//
// Prints one line, PASS or FAIL, and exits 0 on PASS.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "rp2040.h"
#include "utils/logging.h"

using namespace rp2040js;

namespace {

class CaptureLogger : public Logger {
 public:
  std::string text;
  void debug(const std::string &c, const std::string &m) override { text += "d:" + c + ":" + m + "|"; }
  void warn(const std::string &c, const std::string &m) override { text += "w:" + c + ":" + m + "|"; }
  void error(const std::string &c, const std::string &m) override { text += "e:" + c + ":" + m + "|"; }
  void info(const std::string &c, const std::string &m) override { text += "i:" + c + ":" + m + "|"; }
};

uint32_t rngState = 1;
uint32_t rnd() {
  // xorshift32
  rngState ^= rngState << 13;
  rngState ^= rngState >> 17;
  rngState ^= rngState << 5;
  return rngState;
}

constexpr uint32_t CODE = 0x20001000;
constexpr uint32_t DATA_LO = 0x20010000, DATA_HI = 0x20011000;
constexpr uint32_t STACK = 0x20020000;

struct Chip {
  std::unique_ptr<RP2040> mcu = std::make_unique<RP2040>();
  std::shared_ptr<CaptureLogger> log = std::make_shared<CaptureLogger>();
  std::string breaks;
  uint32_t bl = 0;
  Chip() {
    mcu->logger = log;
    mcu->onBreak = [this](uint32_t code) { breaks += std::to_string(code) + ","; };
    mcu->core0.blTaken = [this](CortexM0Core &, bool blx) { bl += blx ? 2 : 1; };
  }
};

std::string state(Chip &c, const std::string &delta) {
  CortexM0Core &k = c.mcu->core0;
  std::string s;
  char b[64];
  for (uint32_t r : k.registers) {
    snprintf(b, sizeof b, "%x ", r);
    s += b;
  }
  snprintf(b, sizeof b, "%x %x %x %d %d %d %d %.0f ", k.bankedSP, k.xPSR(), k.IPSR, k.PM, static_cast<int>(k.SPSEL),
           k.nPRIV, static_cast<int>(k.currentMode), k.cycles);
  s += b;
  snprintf(b, sizeof b, "%x %x %d %d %d %d %d ", k.pendingInterrupts, k.enabledInterrupts, k.pendingNMI,
           k.pendingPendSV, k.pendingSVCall, k.pendingSystick, k.interruptsUpdated);
  s += b;
  snprintf(b, sizeof b, "%x %x %x %d %d %d %u ", k.VTOR, k.SHPR2, k.SHPR3, k.eventRegistered, k.waiting,
           k.waitingForEvent, k.breakRewind);
  s += b;
  uint32_t h = 0x811c9dc5;
  for (uint32_t a = DATA_LO; a < DATA_HI; a += 4) h = (h ^ c.mcu->readUint32(a)) * 16777619u;
  for (uint32_t a = STACK - 0x400; a < STACK + 0x400; a += 4) h = (h ^ c.mcu->readUint32(a)) * 16777619u;
  snprintf(b, sizeof b, "%x %u ", h, c.bl);
  s += b;
  s += delta + " b" + c.breaks + " L" + c.log->text;
  c.breaks.clear();
  c.log->text.clear();
  c.bl = 0;
  return s;
}

uint32_t randValue() {
  switch (rnd() % 8) {
    case 0:
      return 0;
    case 1:
      return 0xffffffff;
    case 2:
      return rnd() % 64;
    case 3:
    case 4:
      return DATA_LO + (rnd() % (DATA_HI - DATA_LO - 0x100));
    default:
      return rnd();
  }
}

}  // namespace

int main(int argc, char **argv) {
  uint32_t samples = 48;
  for (int i = 1; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "--seed")) rngState = static_cast<uint32_t>(strtoul(argv[i + 1], nullptr, 0)) | 1;
    if (!strcmp(argv[i], "--wide-samples")) samples = static_cast<uint32_t>(strtoul(argv[i + 1], nullptr, 0));
  }

  const uint32_t badTable = CortexM0Core::verifyDecodeTable();
  if (badTable) {
    printf("FAIL decode: %u opcodes whose table entry the chain contradicts\n", badTable);
    return 1;
  }

  Chip a, b;
  // the chain's opcode2 tests look at bits 15..4 (BL: 15, 14, 12; DMB/DSB/ISB: 15..4;
  // MRS, UDF.W: 15..12; MSR: 15..8): these values meet each of them both ways
  std::vector<uint32_t> classes = {0x0000, 0xf000, 0xd000, 0xc000, 0xe000, 0x8f50, 0x8f40, 0x8f60, 0x8f55,
                                   0x8f45, 0x8f6f, 0x8f70, 0x8e50, 0x8000, 0x8800, 0x8812, 0x8900, 0xa000,
                                   0xafff, 0xb000, 0x9000, 0x4000, 0x0f50, 0xffff};
  uint64_t cases = 0, mismatches = 0;
  for (uint32_t opcode = 0; opcode < 0x10000; opcode++) {
    const bool wide = opcode >> 12 == 0b1111 || opcode >> 11 == 0b11101;
    const uint32_t n = wide ? static_cast<uint32_t>(classes.size()) + samples : 1;
    for (uint32_t j = 0; j < n; j++) {
      const uint32_t opcode2 = !wide ? rnd() & 0xffff : j < classes.size() ? classes[j] : rnd() & 0xffff;
      // the same random state on both chips
      std::vector<uint32_t> regs(16);
      for (uint32_t r = 0; r < 13; r++) regs[r] = randValue();
      regs[13] = STACK - (rnd() % 64) * 4;
      regs[14] = rnd() % 4 == 0 ? 0xfffffff9 : randValue();
      const uint32_t pc = CODE + (rnd() % 64) * 2;
      regs[15] = pc;
      const uint32_t flags = rnd();
      const bool handler = rnd() % 4 == 0;
      const uint32_t fill = rnd();
      for (Chip *c : {&a, &b}) {
        CortexM0Core &k = c->mcu->core0;
        for (uint32_t r = 0; r < 16; r++) k.registers[r] = regs[r];
        k.N = flags & 1;
        k.Z = flags & 2;
        k.C = flags & 4;
        k.V = flags & 8;
        k.PM = flags & 16;
        k.currentMode = handler ? ExecutionMode::Mode_Handler : ExecutionMode::Mode_Thread;
        k.IPSR = handler ? 16 + (flags >> 8) % 32 : 0;
        k.eventRegistered = flags & 32;
        k.waiting = false;
        k.waitingForEvent = false;
        k.interruptsUpdated = false;
        k.pendingSVCall = false;
        k.VTOR = 0x20000000;
        for (uint32_t w = 0; w < 64; w++) c->mcu->writeUint32(0x20000000 + 4 * w, (CODE + 0x100) | 1);
        c->mcu->writeUint32(DATA_LO + (fill % 0x1000 & ~3u), fill);
        c->mcu->writeUint16(pc, opcode);
        c->mcu->writeUint16(pc + 2, opcode2);
      }
      std::string da, db;
      try {
        da = std::to_string(a.mcu->core0.executeInstruction());
      } catch (const std::range_error &) {
        da = "RangeError";
      }
      try {
        db = std::to_string(b.mcu->core0.executeInstructionChain());
      } catch (const std::range_error &) {
        db = "RangeError";
      }
      const std::string sa = state(a, da), sb = state(b, db);
      cases++;
      if (sa != sb) {
        if (mismatches++ < 5) {
          printf("MISMATCH opcode %04x opcode2 %04x\n  table: %s\n  chain: %s\n", opcode, opcode2,
                 sa.substr(0, 400).c_str(), sb.substr(0, 400).c_str());
        }
      }
    }
  }
  if (mismatches) {
    printf("FAIL decode: %llu of %llu executions differ\n", static_cast<unsigned long long>(mismatches),
           static_cast<unsigned long long>(cases));
    return 1;
  }
  printf("PASS decode: table verified for all 65536 opcodes; %llu executions table = chain\n",
         static_cast<unsigned long long>(cases));
  return 0;
}
