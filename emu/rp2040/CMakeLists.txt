cmake_minimum_required(VERSION 3.16)
project(rp2040emu LANGUAGES CXX)

# A faithful C++17 port of rp2040js (with the cupc8 dual-core patch); see README.md.
#
# Build flags ("Build" in README.md). The library is built twice from the same
# sources: rp2040emu, plain -O2 (what emu/machine links, and test_periph_diff,
# whose -Wl,--wrap of RP2040::setInterrupt needs calls between object files),
# and rp2040emu_fast for rp2040run, rp2040emu.node and the other tests, with
#   RP2040EMU_LTO=ON       link-time optimisation (default on where supported)
#   RP2040EMU_NATIVE=ON    -march=native (default off: the binaries then only run
#                          on this kind of CPU)
#   RP2040EMU_PGO=generate|use  profile-guided optimisation with the profile in
#                          RP2040EMU_PGO_DIR; tools/pgo.sh builds, trains on the
#                          card images and rebuilds (default: none)
# Every target gets -ffp-contract=off: the port's float arithmetic must round
# exactly as JS's does, so no fused multiply-adds (-march=native has FMA).

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

option(RP2040EMU_LTO "link-time optimisation for rp2040emu_fast and its users" ON)
option(RP2040EMU_NATIVE "-march=native for rp2040emu_fast and its users" OFF)
set(RP2040EMU_PGO "" CACHE STRING "profile-guided optimisation of rp2040emu_fast and its users: generate, use or empty")
set_property(CACHE RP2040EMU_PGO PROPERTY STRINGS "" generate use)
set(RP2040EMU_PGO_DIR "${CMAKE_CURRENT_BINARY_DIR}/pgo-profile" CACHE PATH "the profile directory (RP2040EMU_PGO)")

set(RP2040EMU_WARN -Wall -Wextra)
set(RP2040EMU_CODEGEN -O2 -ffp-contract=off)

# the flags of the fast targets: compile and link options (LTO generates code at link time)
set(_fast_flags ${RP2040EMU_CODEGEN})
if(RP2040EMU_NATIVE)
  list(APPEND _fast_flags -march=native)
endif()
if(RP2040EMU_PGO STREQUAL "generate" OR RP2040EMU_PGO STREQUAL "use")
  if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    message(FATAL_ERROR "RP2040EMU_PGO supports GCC only (this is ${CMAKE_CXX_COMPILER_ID})")
  endif()
  # profile files are named after the object paths below the build directory,
  # so that a training build elsewhere matches (tools/pgo.sh)
  list(APPEND _fast_flags "-fprofile-prefix-path=${CMAKE_CURRENT_BINARY_DIR}")
  if(RP2040EMU_PGO STREQUAL "generate")
    list(APPEND _fast_flags "-fprofile-generate=${RP2040EMU_PGO_DIR}" -fprofile-update=single)
  else()
    # code the training did not run (USB, the tests' own code) keeps -O2 as it is
    list(APPEND _fast_flags "-fprofile-use=${RP2040EMU_PGO_DIR}" -fprofile-partial-training
         -Wno-missing-profile)
  endif()
elseif(NOT RP2040EMU_PGO STREQUAL "")
  message(FATAL_ERROR "RP2040EMU_PGO must be generate, use or empty, not ${RP2040EMU_PGO}")
endif()
set(_fast_ipo OFF)
if(RP2040EMU_LTO)
  include(CheckIPOSupported)
  check_ipo_supported(RESULT _fast_ipo OUTPUT _ipo_msg LANGUAGES CXX)
  if(NOT _fast_ipo)
    message(STATUS "rp2040emu: no link-time optimisation (${_ipo_msg})")
  endif()
endif()
# a production target: the fast flags and, if on, LTO
function(rp2040emu_fast_target target)
  target_compile_options(${target} PRIVATE ${_fast_flags})
  target_link_options(${target} PRIVATE ${_fast_flags})
  if(_fast_ipo)
    set_property(TARGET ${target} PROPERTY INTERPROCEDURAL_OPTIMIZATION TRUE)
  endif()
endfunction()

file(GLOB_RECURSE RP2040EMU_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")
# position-independent so that the Node addon below can link it; hidden
# visibility so that, inside a shared object, calls between its functions are
# direct and can be inlined (default visibility makes every one interposable,
# which made the addon ~1.7x slower than rp2040run)
foreach(_lib rp2040emu rp2040emu_fast)
  add_library(${_lib} STATIC ${RP2040EMU_SOURCES})
  set_target_properties(${_lib} PROPERTIES POSITION_INDEPENDENT_CODE ON
                        CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)
  target_include_directories(${_lib} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
  target_compile_options(${_lib} PRIVATE ${RP2040EMU_WARN})
endforeach()
target_compile_options(rp2040emu PRIVATE ${RP2040EMU_CODEGEN})
rp2040emu_fast_target(rp2040emu_fast)

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
target_compile_options(rp2040run PRIVATE ${RP2040EMU_WARN})
rp2040emu_fast_target(rp2040run)
target_link_libraries(rp2040run PRIVATE rp2040emu_fast)

# a test driver, on the fast library (what rp2040run and the addon run)
function(rp2040emu_test target source)
  add_executable(${target} ${source})
  target_compile_options(${target} PRIVATE ${RP2040EMU_WARN})
  rp2040emu_fast_target(${target})
  target_link_libraries(${target} PRIVATE rp2040emu_fast)
endfunction()

# PIO differential test against rp2040js (driven by test/pio/pio_diff.mjs)
rp2040emu_test(test_pio_diff test/pio/test_pio_diff.cpp)

# utils/js.h's fast ToUint32 / Math.round against their plain definitions
rp2040emu_test(test_js_numbers test/js/test_js_numbers.cpp)

# USB differential test: test/usb/usb_diff.mjs drives rp2040js and this replay
# driver with the same ops and compares traces:
#   node emu/rp2040/test/usb/usb_diff.mjs build/emu-native/test_usb_diff
rp2040emu_test(test_usb_diff test/usb/test_usb_diff.cpp)

# differential test of the CortexM0Core / PPB port against rp2040js (driven by test/core/core-diff.mjs)
rp2040emu_test(test_core_diff test/core/test_core_diff.cpp)

# the decode table against the if/else chain it was generated from (exhaustive)
rp2040emu_test(test_decode test/core/test_decode.cpp)

# Peripheral differential test (dma, uart, spi, i2c, timer, watchdog, rtc, adc,
# pwm, timer32) against rp2040js, driven by test/periph/periph_diff.mjs:
#   node emu/rp2040/test/periph/periph_diff.mjs --cxx build/emu-native/test_periph_diff
# RP2040::setInterrupt is wrapped at link time so the test can trace IRQ changes
# (on the plain library: with LTO the calls would not go through the symbol).
add_executable(test_periph_diff test/periph/test_periph_diff.cpp)
target_compile_options(test_periph_diff PRIVATE ${RP2040EMU_CODEGEN} ${RP2040EMU_WARN})
target_link_libraries(test_periph_diff PRIVATE rp2040emu)
target_link_options(test_periph_diff PRIVATE "-Wl,--wrap=_ZN8rp2040js6RP204012setInterruptEjb")

# The card-test harness (harness/: test/emu/rp2040emu.mjs's Emu loop, the slot
# host of slothost.mjs, TMDS capture) and its Node addon rp2040emu.node, for
# test/emu/rp2040native.mjs (CUPC8_EMU=native). The harness needs C++20
# (coroutines); the addon is built only if Node's headers are found.
# rp2040harness is on the plain library (emu/machine links it),
# rp2040harness_fast on the fast one (the addon).
foreach(_lib rp2040harness rp2040harness_fast)
  add_library(${_lib} STATIC harness/emu.cpp harness/slothost.cpp "${BOOTROM_INC}")
  set_target_properties(${_lib} PROPERTIES CXX_STANDARD 20 POSITION_INDEPENDENT_CODE ON
                        CXX_VISIBILITY_PRESET hidden VISIBILITY_INLINES_HIDDEN ON)
  target_include_directories(${_lib} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/harness"
                             PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
  target_compile_options(${_lib} PRIVATE ${RP2040EMU_WARN})
endforeach()
target_compile_options(rp2040harness PRIVATE ${RP2040EMU_CODEGEN})
target_link_libraries(rp2040harness PUBLIC rp2040emu)
rp2040emu_fast_target(rp2040harness_fast)
target_link_libraries(rp2040harness_fast PUBLIC rp2040emu_fast)

# RP2040::runSteps (the Emu loop in one function) against Emu::step() on the card images
add_executable(test_runsteps test/core/test_runsteps.cpp)
set_target_properties(test_runsteps PROPERTIES CXX_STANDARD 20)
target_compile_options(test_runsteps PRIVATE ${RP2040EMU_WARN})
rp2040emu_fast_target(test_runsteps)
target_link_libraries(test_runsteps PRIVATE rp2040harness_fast)

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
  target_compile_options(rp2040emu_node PRIVATE ${RP2040EMU_WARN})
  rp2040emu_fast_target(rp2040emu_node)
  target_link_libraries(rp2040emu_node PRIVATE rp2040harness_fast)
  if(APPLE)
    target_link_options(rp2040emu_node PRIVATE -undefined dynamic_lookup)
  endif()
else()
  message(STATUS "node_api.h not found: not building rp2040emu.node")
endif()
