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
# position-independent so that the Node addon below can link it; hidden
# visibility so that, inside a shared object, calls between its functions are
# direct and can be inlined (default visibility makes every one interposable,
# which made the addon ~1.7x slower than rp2040run)
set_target_properties(rp2040emu PROPERTIES POSITION_INDEPENDENT_CODE ON
                      CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)
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

# utils/js.h's fast ToUint32 / Math.round against their plain definitions
add_executable(test_js_numbers test/js/test_js_numbers.cpp)
target_compile_options(test_js_numbers PRIVATE -O2 -Wall -Wextra)
target_link_libraries(test_js_numbers PRIVATE rp2040emu)

# USB differential test: test/usb/usb_diff.mjs drives rp2040js and this replay
# driver with the same ops and compares traces:
#   node emu/rp2040/test/usb/usb_diff.mjs build/emu-native/test_usb_diff
add_executable(test_usb_diff test/usb/test_usb_diff.cpp)
target_compile_options(test_usb_diff PRIVATE -O2 -Wall -Wextra)
target_link_libraries(test_usb_diff PRIVATE rp2040emu)

# differential test of the CortexM0Core / PPB port against rp2040js (driven by test/core/core-diff.mjs)
add_executable(test_core_diff test/core/test_core_diff.cpp)
target_compile_options(test_core_diff PRIVATE -O2 -Wall -Wextra)
target_link_libraries(test_core_diff PRIVATE rp2040emu)

# Peripheral differential test (dma, uart, spi, i2c, timer, watchdog, rtc, adc,
# pwm, timer32) against rp2040js, driven by test/periph/periph_diff.mjs:
#   node emu/rp2040/test/periph/periph_diff.mjs --cxx build/emu-native/test_periph_diff
# RP2040::setInterrupt is wrapped at link time so the test can trace IRQ changes.
add_executable(test_periph_diff test/periph/test_periph_diff.cpp)
target_compile_options(test_periph_diff PRIVATE -O2 -Wall -Wextra)
target_link_libraries(test_periph_diff PRIVATE rp2040emu)
target_link_options(test_periph_diff PRIVATE "-Wl,--wrap=_ZN8rp2040js6RP204012setInterruptEjb")

# The card-test harness (harness/: test/emu/rp2040emu.mjs's Emu loop, the slot
# host of slothost.mjs, TMDS capture) and its Node addon rp2040emu.node, for
# test/emu/rp2040native.mjs (CUPC8_EMU=native). The harness needs C++20
# (coroutines); the addon is built only if Node's headers are found.
add_library(rp2040harness STATIC harness/emu.cpp harness/slothost.cpp "${BOOTROM_INC}")
set_target_properties(rp2040harness PROPERTIES CXX_STANDARD 20 POSITION_INDEPENDENT_CODE ON
                      CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)
target_include_directories(rp2040harness PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/harness"
                           PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_compile_options(rp2040harness PRIVATE -O2 -Wall -Wextra)
target_link_libraries(rp2040harness PUBLIC rp2040emu)

find_program(NODE_EXECUTABLE node)
if(NODE_EXECUTABLE)
  get_filename_component(_node_bin "${NODE_EXECUTABLE}" REALPATH)
  get_filename_component(_node_prefix "${_node_bin}" DIRECTORY)
  get_filename_component(_node_prefix "${_node_prefix}" DIRECTORY)
  set(NODE_INCLUDE_DIR "${_node_prefix}/include/node" CACHE PATH "Node's C headers (node_api.h)")
endif()
if(NODE_INCLUDE_DIR AND EXISTS "${NODE_INCLUDE_DIR}/node_api.h")
  add_library(rp2040emu_node MODULE node/rp2040emu_node.cpp)
  set_target_properties(rp2040emu_node PROPERTIES CXX_STANDARD 20 PREFIX "" OUTPUT_NAME rp2040emu SUFFIX ".node"
                        CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)
  target_include_directories(rp2040emu_node PRIVATE "${NODE_INCLUDE_DIR}")
  target_compile_definitions(rp2040emu_node PRIVATE NODE_GYP_MODULE_NAME=rp2040emu)
  target_compile_options(rp2040emu_node PRIVATE -O2 -Wall -Wextra)
  target_link_libraries(rp2040emu_node PRIVATE rp2040harness)
  if(APPLE)
    target_link_options(rp2040emu_node PRIVATE -undefined dynamic_lookup)
  endif()
else()
  message(STATUS "node_api.h not found: not building rp2040emu.node")
endif()
