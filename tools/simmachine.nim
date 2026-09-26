# The Milestone 1 machine as the simulator CLI (sim.nim) and its tests
# (simtest.nim) set it up: slot card kinds by name, the ROM image (boot ROM
# + kernel, built as the hardware's ROM chip holds it), the console's text,
# and a blank FAT image for the storage card.

import os
import std/tempfiles
import std/exitprocs
import osproc
import strutils
import simcards

const
  simRoot = currentSourcePath().parentDir.parentDir
  CardKindNames* = "hdmi, eink, eink750, io, storage, wifi, empty"

var privDir = ""

proc romDir*(): string =
  ## This process's own build directory (build/rom-PID-*, made on first use,
  ## removed at exit): the kernel, its map, the boot ROM and the ROM images
  ## built here. Tests and sims running side by side each have their own, so
  ## none overwrites another's (kernel/assemble.sh once built in kernel/ for
  ## all of them).
  if privDir.len == 0:
    createDir(simRoot / "build")
    privDir = createTempDir("rom-" & $getCurrentProcessId() & "-", "", simRoot / "build")
    let d = privDir
    addExitProc(proc () = removeDir(d))
  privDir

proc cardKind*(name: string): int =
  ## Slot card kind by name (the native emulator's names), 0 = empty slot,
  ## -1 = unknown.
  case name.strip.toLowerAscii
  of "hdmi": CardGpu
  of "eink": CardEink
  of "eink750": CardEink750
  of "io": CardIo
  of "storage": CardStorage
  of "wifi": CardWifi
  of "empty", "none", "-": 0
  else: -1

proc run(cmd, what: string) =
  let r = execCmdEx(cmd)
  if r.exitCode != 0:
    raise newException(IOError, what & ": " & r.output)

proc buildBootRom*(): string =
  ## Assemble rom/boot.s into romDir()/boot.bin.
  result = romDir() / "boot.bin"
  run("python3 " & quoteShell(simRoot / "tools" / "as.py") & " " &
      quoteShell(simRoot / "rom" / "boot.s") & " " & quoteShell(result) &
      " 0xe000,0xe600,0x0f00", "boot ROM")

proc makeRom*(boot, kernel, dest: string): string =
  ## The ROM image: the boot ROM and the kernel with its header (tools/mkrom.py).
  createDir(dest.parentDir)
  run("python3 " & quoteShell(simRoot / "tools" / "mkrom.py") & " " &
      quoteShell(boot) & " " & quoteShell(kernel) & " -o " & quoteShell(dest), "mkrom")
  dest

proc buildKernel*(dir = ""): string =
  ## Assemble the real kernel (kernel/assemble.sh) into `dir` (default
  ## romDir()): its kernel.o, the path returned, and kernel.map beside it.
  let d = if dir.len > 0: dir else: romDir()
  run("bash " & quoteShell(simRoot / "kernel" / "assemble.sh") & " " & quoteShell(d), "kernel build")
  d / "kernel.o"

proc kernelMapPath*(): string =
  ## The map of the kernel buildKernel built last (in romDir())
  romDir() / "kernel.map"

proc buildKernelRom*(): string =
  ## The real kernel and the boot ROM as the ROM chip holds them:
  ## romDir()/kernel.rom.
  makeRom(buildBootRom(), buildKernel(), romDir() / "kernel.rom")

proc screenLines*(g: SimCard): seq[string] =
  ## The graphics card's text screen, one string per row, trailing blanks cut.
  for row in 0..29:
    var line = ""
    for col in 0..79:
      let ch = int(simcard_gpu_cell(g, cint(col), cint(row))) and 0xff
      line.add(if ch == 0: ' ' else: char(ch))
    result.add(line.strip(leading = false))

proc makeFatImage*(path: string; kb = 32768) =
  ## A blank FAT volume, as a PC formats a card (mkfs.fat, from dosfstools).
  if findExe("mkfs.fat").len == 0:
    raise newException(IOError, "mkfs.fat (dosfstools) is not installed; make the image with " &
                       "`mkfs.fat -C " & path & " 32768` or tools/fatcheck.py blank")
  if path.parentDir.len > 0:
    createDir(path.parentDir)
  run("mkfs.fat -C " & quoteShell(path) & " " & $kb, "mkfs.fat")
