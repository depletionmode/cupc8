# Slot cards for the simulator: the real firmware cores (fw/*/core), compiled
# in through the C shim fw/sim/simcards.c.

import os

const fwDir = currentSourcePath().parentDir & "/../fw"

{.passC: "-I" & fwDir & "/common -I" & fwDir & "/gpu/core -I" & fwDir & "/io/core -I" & fwDir & "/sim".}
{.compile: fwDir & "/common/cardproto.c".}
{.compile: fwDir & "/common/font8x8_cp437.c".}
{.compile: fwDir & "/gpu/core/gpu.c".}
{.compile: fwDir & "/io/core/iocard.c".}
{.compile: fwDir & "/sim/simcards.c".}

const
  CardGpu* = 1
  CardIo* = 2
  CardWifi* = 3
  GpuOutW* = 640
  GpuOutH* = 480

type SimCard* = distinct pointer

proc simcard_new*(kind: cint): SimCard {.importc, cdecl.}
proc simcard_free*(c: SimCard) {.importc, cdecl.}
proc simcard_type*(c: SimCard): cint {.importc, cdecl.}
proc simcard_select*(c: SimCard, selected: cint) {.importc, cdecl.}
proc simcard_miso*(c: SimCard): uint8 {.importc, cdecl.}
proc simcard_mosi*(c: SimCard, b: uint8) {.importc, cdecl.}
proc simcard_irq*(c: SimCard): cint {.importc, cdecl.}
proc simcard_tick*(c: SimCard, nowMs: uint32) {.importc, cdecl.}
proc simcard_render*(c: SimCard, rgb: ptr uint32) {.importc, cdecl.}
proc simcard_gpu_cell*(c: SimCard, x, y: cint): cint {.importc, cdecl.}
proc simcard_gpu_pixel*(c: SimCard, x, y: cint): cint {.importc, cdecl.}
proc simcard_gpu_mode*(c: SimCard): cint {.importc, cdecl.}
proc simcard_type_ascii*(c: SimCard, ch: uint8, nowMs: uint32) {.importc, cdecl.}
proc simcard_hid*(c: SimCard, report: ptr uint8, nowMs: uint32) {.importc, cdecl.}

proc isNil*(c: SimCard): bool = pointer(c).isNil
