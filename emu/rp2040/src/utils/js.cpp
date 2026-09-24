#include "js.h"

#include <cstdio>
#include <cstdlib>

namespace rp2040js {

void consoleWarn(const std::string &message) { std::fprintf(stderr, "%s\n", message.c_str()); }

void consoleError(const std::string &message) { std::fprintf(stderr, "%s\n", message.c_str()); }

void todoPortAbort(const char *tsFile, const char *what) {
  std::fprintf(stderr, "rp2040emu: %s is not ported yet (TODO(port): %s)\n", what, tsFile);
  std::fflush(stderr);
  std::abort();
}

}  // namespace rp2040js
