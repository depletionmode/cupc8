cmake_minimum_required(VERSION 3.16)
project(rp2040emu LANGUAGES CXX)

# A faithful C++17 port of rp2040js (with the cupc8 dual-core patch); see README.md.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(DEFINED ENV{CUPC8_SDK})
  set(_sdk "$ENV{CUPC8_SDK}")
else()
  set(_sdk "$ENV{HOME}/.local/share/cupc8-sdk")
endif()
set(RP2040JS_DIR "${_sdk}/rp2040js" CACHE PATH "patched rp2040js checkout (for demo/bootrom.ts)")

file(GLOB_RECURSE RP2040EMU_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")
add_library(rp2040emu STATIC ${RP2040EMU_SOURCES})
target_include_directories(rp2040emu PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_compile_options(rp2040emu PRIVATE -O2 -Wall -Wextra)

# the B1 bootrom, extracted from rp2040js at build time
set(BOOTROM_TS "${RP2040JS_DIR}/demo/bootrom.ts")
if(NOT EXISTS "${BOOTROM_TS}")
  message(FATAL_ERROR "rp2040js bootrom not found: ${BOOTROM_TS} (set RP2040JS_DIR or CUPC8_SDK)")
endif()
set(BOOTROM_INC "${CMAKE_CURRENT_BINARY_DIR}/generated/bootrom_b1.inc")
add_custom_command(
  OUTPUT "${BOOTROM_INC}"
  COMMAND ${CMAKE_COMMAND} -DIN=${BOOTROM_TS} -DOUT=${BOOTROM_INC}
          -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/extract_bootrom.cmake"
  DEPENDS "${BOOTROM_TS}" "${CMAKE_CURRENT_SOURCE_DIR}/cmake/extract_bootrom.cmake"
  COMMENT "Extracting the B1 bootrom from rp2040js"
  VERBATIM)

add_executable(rp2040run tools/rp2040run.cpp "${BOOTROM_INC}")
target_include_directories(rp2040run PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_compile_options(rp2040run PRIVATE -O2 -Wall -Wextra)
target_link_libraries(rp2040run PRIVATE rp2040emu)

# PIO differential test against rp2040js (driven by test/pio/pio_diff.mjs)
add_executable(test_pio_diff test/pio/test_pio_diff.cpp)
target_compile_options(test_pio_diff PRIVATE -O2 -Wall -Wextra)
target_link_libraries(test_pio_diff PRIVATE rp2040emu)
