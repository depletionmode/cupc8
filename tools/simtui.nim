## CUPC/8 full-screen terminal emulator and debugger.

import deques
import os
import parseopt
import std/monotimes
import strutils
import tables
import times
from unicode import runeLen

import disasm
import guestview
import sim
import simdisplay
import sdl2 as sdl
import symbols
import tui

type
  PaneId = enum pDisasm, pRegs, pStack, pDisplay, pMemory, pLog, pSource, pFuncs, pBreaks
  Mode = enum mNormal, mInput, mEx
  GfxMode = enum gfxAuto, gfxKitty, gfxHalf
  DisplayMode = enum displayEmbedded, displayWindow
  ThemeMode = enum themeAuto, themeDark, themeLight
  DividerKind = enum
    dividerNone, dividerTopBottom, dividerNavCode, dividerCodeCpu,
    dividerCpuDisplay, dividerFuncsBreaks, dividerRegsStack, dividerMemoryLog,
    dividerDisasmSource
  RunGoal = enum goalNone, goalStepOver, goalUntil, goalStepOut
  ConfirmAction = enum confirmNone, confirmReset, confirmQuit
  Watch = object
    address, length: int
    mask: uint8
  Rect = object
    x, y, w, h: int
  ActionKind = enum
    actNone, actFocus, actContinue, actStepIn, actStepOver, actStepOut,
    actReset, actHelp, actToggleBreak, actAddress, actCursor, actDivider
  HitRect = object
    rect: Rect
    kind: ActionKind
    pane: PaneId
    value: int
  Layout = object
    panes: array[PaneId, Rect]
    tooSmall: bool

var
  Blue = 0x015fcfff'u32
  Green = 0x014bd37b'u32
  Red = 0x01ff5f6d'u32
  Yellow = 0x01e5c07b'u32
  Gray = 0x01808a98'u32
  White = 0x01d8dee9'u32
  Background = 0x010f141a'u32
  BarBackground = 0x01202730'u32
  OverlayBackground = 0x01161b22'u32
  imagePath = ""
  mapPath = ""
  symtab: SymTab
  mode = mNormal
  gfxMode = gfxAuto
  displayMode = displayEmbedded
  themeMode = themeAuto
  kittyEnabled = false
  running = false
  runGoal = goalNone
  confirm = confirmNone
  focus = pDisasm
  helpVisible = false
  dirty = true
  stopReason = "loaded"
  mhz = 0.0
  exBuffer = ""
  editActive = false
  editHex = ""
  userBreaks: array[0x10000, bool]
  tempBreak = -1
  stepOverSP = 0
  watchMask: array[0x10000, uint8]
  watches: seq[Watch]
  eventLog = initDeque[string](2048)
  keyFifo = initDeque[int](64)
  hitRects: seq[HitRect]
  disRows: seq[int]
  sourceRows: seq[tuple[line, address: int]]
  disTop = 0x1000
  disCursor = 0x1000
  followPc = true
  navHistory: seq[int]
  memoryTop = 0x2000
  memoryCursor = 0x2000
  logScroll = 0
  sourceTop = 1
  sourceCursor = 1
  sourceFile = ""
  sourceSwap = false
  funcSwap = false
  breakSwap = false
  displaySwap = false
  funcList: seq[tuple[address: int, name: string]]
  funcTop = 0
  funcCursor = 0
  breakList: seq[int]
  breakTop = 0
  breakCursor = 0
  bottomLog = false
  logGpo = true
  logSpi0 = false
  logKey = true
  logSd = true
  lastHookStop = ""
  dragDivider = dividerNone
  topSplitPercent = 68
  navPercent = 18
  cpuPercent = 22
  displayPercent = 26
  codeSourceSplitPercent = 58
  regsSplitPercent = 48
  memorySplitPercent = 56
  funcsBreaksSplitPercent = 62

proc contains(rect: Rect; x, y: int): bool =
  rect.w > 0 and rect.h > 0 and x >= rect.x and y >= rect.y and
    x < rect.x + rect.w and y < rect.y + rect.h

proc autoLightTheme(): bool =
  let colorFgBg = getEnv("COLORFGBG")
  if colorFgBg.len == 0: return false
  let fields = colorFgBg.split(';')
  try:
    parseInt(fields[^1]) in [7, 15]
  except ValueError:
    false

proc applyTheme() =
  let light = themeMode == themeLight or
              (themeMode == themeAuto and autoLightTheme())
  if light:
    Blue = 0x01006b9f'u32
    Green = 0x01087846'u32
    Red = 0x01b32636'u32
    Yellow = 0x01805b00'u32
    Gray = 0x01576570'u32
    White = 0x011e2933'u32
    Background = 0x01f5f7f8'u32
    BarBackground = 0x01dce4e9'u32
    OverlayBackground = 0x01eef2f4'u32
  else:
    Blue = 0x015fcfff'u32
    Green = 0x014bd37b'u32
    Red = 0x01ff5f6d'u32
    Yellow = 0x01e5c07b'u32
    Gray = 0x01808a98'u32
    White = 0x01d8dee9'u32
    Background = 0x010f141a'u32
    BarBackground = 0x01202730'u32
    OverlayBackground = 0x01161b22'u32
  setDefaultColors(White, Background)
  forceRedraw()
  dirty = true

proc setDisplayMode(mode: DisplayMode) =
  if mode == displayWindow:
    deleteKittyImage()
    if display_init(resetFramebuffer = false):
      display_setVisible(true)
      displayMode = displayWindow
      stopReason = "display in SDL window"
    else:
      displayMode = displayEmbedded
      stopReason = "display window failed: " & display_init_error
  else:
    display_setVisible(false)
    displayMode = displayEmbedded
    case gfxMode
    of gfxKitty: kittyEnabled = true
    of gfxHalf: kittyEnabled = false
    of gfxAuto: kittyEnabled = queryKittyGfx()
    resetKittyImage()
    stopReason = "display embedded"
  forceRedraw()
  dirty = true

proc pumpWindowEvents() =
  if displayMode != displayWindow: return
  var event = sdl.defaultEvent
  while sdl.pollEvent(event):
    case event.kind
    of sdl.QuitEvent:
      setDisplayMode(displayEmbedded)
    of sdl.TextInput:
      let input = event.text()
      if input.text[0] != '\0': keyFifo.addLast(ord(input.text[0]))
    of sdl.KeyDown:
      let keyEvent = event.key()
      if keyEvent.repeat: continue
      case keyEvent.keysym.sym
      of sdl.K_RETURN, sdl.K_KP_ENTER: keyFifo.addLast(13)
      of sdl.K_BACKSPACE: keyFifo.addLast(8)
      else: discard
    else: discard

proc addHit(rect: Rect; kind: ActionKind; pane = pDisasm; value = 0) =
  if rect.w > 0 and rect.h > 0:
    hitRects.add(HitRect(rect: rect, kind: kind, pane: pane, value: value))

proc appendLog(tag, message: string) =
  eventLog.addLast("[ins $1] [$2] $3" % [$ins_retired, tag, message])
  while eventLog.len > 2000: discard eventLog.popFirst()
  dirty = true

proc formatAddress(address: int): string = "$" & toHex(address and 0xffff, 4)

proc resolveToken(token: string): int =
  let value = token.strip
  if symtab.byName.hasKey(value): return symtab.byName[value]
  try:
    if value.startsWith("$"): return parseHexInt(value[1..^1]) and 0xffff
    if value.startsWith("0x") or value.startsWith("0X"):
      return parseHexInt(value[2..^1]) and 0xffff
    return parseHexInt(value) and 0xffff
  except ValueError:
    -1

proc cleanupTempBreak() =
  if runGoal == goalStepOut:
    stepOutArmed = false
  if tempBreak >= 0 and not userBreaks[tempBreak and 0xffff]:
    clearBreak(tempBreak)
  tempBreak = -1
  runGoal = goalNone

proc pause(reason: string; cancelGoal = true) =
  running = false
  stopReason = reason
  if cancelGoal: cleanupTempBreak()
  dirty = true

proc rebuildBreakList() =
  breakList.setLen(0)
  for address in 0..userBreaks.high:
    if userBreaks[address]: breakList.add(address)
  if breakCursor >= breakList.len:
    breakCursor = max(0, breakList.high)
  if breakTop > breakCursor: breakTop = max(0, breakCursor)

proc setTempBreak(address: int; goal: RunGoal) =
  cleanupTempBreak()
  tempBreak = address and 0xffff
  setBreak(tempBreak)
  runGoal = goal

proc toggleBreakpoint(address: int) =
  let a = address and 0xffff
  userBreaks[a] = not userBreaks[a]
  if userBreaks[a]:
    setBreak(a)
    appendLog("RUN", "breakpoint set at " & symtab.symbolize(a))
  else:
    if tempBreak != a: clearBreak(a)
    appendLog("RUN", "breakpoint cleared at " & symtab.symbolize(a))
  rebuildBreakList()
  dirty = true

proc rebuildWatchMask() =
  for i in 0..watchMask.high: watchMask[i] = 0
  for watch in watches:
    for offset in 0..<watch.length:
      watchMask[(watch.address + offset) and 0xffff] =
        watchMask[(watch.address + offset) and 0xffff] or watch.mask

proc installMemoryHook() =
  memHook = proc(kind: MemAccessKind; address, value, oldValue: int) =
    let
      a = address and 0xffff
      mask = if kind == maRead: 1'u8 else: 2'u8
    if (watchMask[a] and mask) != 0:
      lastHookStop = "$1 $2 $3→$4" % [
        (if kind == maRead: "read" else: "write"), formatAddress(a),
        toHex(oldValue, 2), toHex(value, 2)]
      appendLog("WATCH", lastHookStop)
      stopRequest = true
    if kind == maWrite and a == 0xf000 and logGpo:
      appendLog("GPO", toBin(value, 8) & " " & toHex(value, 2))
    if (a and 0xff00) == 0xf100:
      let dev = (a shr 4) and 0xf
      if dev == 0 and logSpi0:
        appendLog("SPI0", "$1 reg$2 $3" % [
          (if kind == maRead: "read" else: "write"), $(a and 0xf),
          toHex(value, 2)])
      elif dev == 1 and logSd:
        appendLog("SD", "$1 reg$2 $3" % [
          (if kind == maRead: "read" else: "write"), $(a and 0xf),
          toHex(value, 2)])
      elif dev == 2 and logKey and kind == maRead and (a and 0xf) == 1 and
          value != 0xff:
        appendLog("KEY", "$1 reg$2 $3" % [
          (if kind == maRead: "read" else: "write"), $(a and 0xf),
          toHex(value, 2)])

proc rebuildFuncList() =
  funcList.setLen(0)
  funcTop = 0
  funcCursor = 0
  if not symtab.loaded: return
  var dataNames = initTable[string, bool]()
  for item in symtab.dataSyms:
    dataNames[item.name] = true
  for (address, name) in symtab.sortedSyms:
    if '.' in name or dataNames.hasKey(name): continue
    if address < 0x1000 or address >= 0xf000: continue
    funcList.add((address, name))

proc funcIndexAt(address: int): int =
  result = -1
  for i, fn in funcList:
    if fn.address <= (address and 0xffff): result = i
    else: break

proc syncFuncsToPc() =
  let index = funcIndexAt(PC)
  if index < 0: return
  funcCursor = index

proc loadSymbols(path: string) =
  mapPath = path
  if path.len > 0 and fileExists(path):
    try:
      symtab = loadMap(path)
      appendLog("RUN", "map " & path.extractFilename)
    except ValueError as error:
      symtab = loadMap("")
      appendLog("RUN", error.msg)
  else:
    symtab = loadMap("")
  rebuildFuncList()

proc loadImage(path, explicitMap: string) =
  if not fileExists(path):
    stopReason = "image not found: " & path
    dirty = true
    return
  cleanupTempBreak()
  cpuReset()
  cpuLoadFile(path)
  imagePath = path
  let candidate = if explicitMap.len > 0: explicitMap else: path.changeFileExt("map")
  loadSymbols(candidate)
  disCursor = PC
  disTop = PC
  followPc = true
  stopReason = "loaded " & path.extractFilename
  appendLog("RUN", stopReason)
  dirty = true

proc handleRunExit(exit: RunExit) =
  case exit
  of reCount: discard
  of reBreak:
    let a = PC and 0xffff
    if userBreaks[a]:
      pause("breakpoint " & symtab.symbolize(a))
    elif runGoal == goalStepOver and a == tempBreak and SP != stepOverSP:
      discard # recursion reached the return address at a different depth
    elif a == tempBreak:
      pause((if runGoal == goalUntil: "until " else: "step over ") &
            symtab.symbolize(a))
    else:
      pause("breakpoint " & symtab.symbolize(a))
  of reStop:
    if runGoal == goalStepOut and lastHookStop.len == 0:
      pause("step out " & symtab.symbolize(PC))
    else:
      let reason = if lastHookStop.len > 0: "watchpoint " & lastHookStop else: "stop request"
      lastHookStop.setLen(0)
      pause(reason)
  of reHalted: pause("HALT")
  of rePastImage: pause("PC past image end")

proc stepInto() =
  if running: return
  cleanupTempBreak()
  let exit = cpuRun(1)
  handleRunExit(exit)
  if exit == reCount: stopReason = "step " & symtab.symbolize(PC)
  followPc = true
  dirty = true

proc stepOver() =
  if running: return
  let instruction = disasm(mem, PC)
  if instruction.isCall:
    stepOverSP = SP
    setTempBreak(PC + instruction.len, goalStepOver)
    running = true
    stopReason = "step over"
  else:
    stepInto()
  dirty = true

proc stepOut() =
  if running: return
  cleanupTempBreak()
  stepOutSP = SP
  stepOutArmed = true
  runGoal = goalStepOut
  lastHookStop.setLen(0)
  running = true
  stopReason = "step out"
  dirty = true

proc continueRun() =
  if running: return
  cleanupTempBreak()
  running = true
  stopReason = "running"
  dirty = true

proc runUntil(address: int) =
  if address < 0: return
  setTempBreak(address, goalUntil)
  running = true
  stopReason = "until " & symtab.symbolize(address)
  dirty = true

proc resetCpu() =
  cleanupTempBreak()
  cpuReset()
  cpuLoadFile(imagePath)
  running = false
  stepOutArmed = false
  followPc = true
  disCursor = PC
  stopReason = "reset"
  appendLog("RUN", "reset")
  dirty = true

proc splitH(rect: Rect; leftW, minRight: int): tuple[left, right: Rect] =
  let w = max(0, min(leftW, rect.w - minRight))
  result.left = Rect(x: rect.x, y: rect.y, w: w, h: rect.h)
  result.right = Rect(x: rect.x + w, y: rect.y, w: rect.w - w, h: rect.h)

proc splitHRight(rect: Rect; rightW, minLeft: int): tuple[left, right: Rect] =
  let w = max(0, min(rightW, rect.w - minLeft))
  result.left = Rect(x: rect.x, y: rect.y, w: rect.w - w, h: rect.h)
  result.right = Rect(x: rect.x + rect.w - w, y: rect.y, w: w, h: rect.h)

proc splitV(rect: Rect; topH, minBot: int): tuple[top, bot: Rect] =
  let h = max(0, min(topH, rect.h - minBot))
  result.top = Rect(x: rect.x, y: rect.y, w: rect.w, h: h)
  result.bot = Rect(x: rect.x, y: rect.y + h, w: rect.w, h: rect.h - h)

proc layoutFor(width, height: int): Layout =
  ## One column model for every size:
  ##   [ nav: funcs/breaks | code: disasm(/source) | cpu: regs/stack | display ]
  ##   [ memory                              | log                            ]
  result.tooSmall = width < 80 or height < 24
  if result.tooSmall: return
  var work = Rect(x: 0, y: 1, w: width, h: height - 2)

  if height >= 28:
    let topH = max(10, min(work.h - 6, work.h * topSplitPercent div 100))
    let parts = splitV(work, topH, 6)
    work = parts.top
    if width >= 100:
      let bottom = splitH(parts.bot, max(24, width * memorySplitPercent div 100), 18)
      result.panes[pMemory] = bottom.left
      result.panes[pLog] = bottom.right
    elif bottomLog:
      result.panes[pLog] = parts.bot
    else:
      result.panes[pMemory] = parts.bot

  let
    wantNav = (symtab.loaded or breakList.len > 0) and width >= 110
    wantDisplay = displayMode == displayEmbedded and width >= 124
    wantSourceUnder = symtab.loaded and height >= 34 and not sourceSwap
  var
    navW = if wantNav: max(16, min(28, width * navPercent div 100)) else: 0
    cpuW = max(22, min(32, width * cpuPercent div 100))
    dispW = if wantDisplay: max(22, min(40, width * displayPercent div 100)) else: 0
  if work.w < navW + cpuW + dispW + 28:
    dispW = 0
  if work.w < navW + cpuW + 28:
    navW = 0

  if width < 100:
    let cols = splitH(work, max(24, width * 58 div 100), 20)
    result.panes[pRegs] = cols.right
    if displaySwap:
      result.panes[pDisplay] = cols.left
    elif sourceSwap and symtab.loaded:
      result.panes[pSource] = cols.left
    elif funcSwap:
      result.panes[pFuncs] = cols.left
    elif breakSwap:
      result.panes[pBreaks] = cols.left
    else:
      result.panes[pDisasm] = cols.left
    return

  if navW > 0:
    let navSplit = splitH(work, navW, cpuW + dispW + 28)
    let navParts = splitV(navSplit.left,
                          max(5, navSplit.left.h * funcsBreaksSplitPercent div 100), 5)
    result.panes[pFuncs] = navParts.top
    result.panes[pBreaks] = navParts.bot
    work = navSplit.right
  if dispW > 0:
    let dispSplit = splitHRight(work, dispW, cpuW + 28)
    result.panes[pDisplay] = dispSplit.right
    work = dispSplit.left
  block:
    let cpuSplit = splitHRight(work, cpuW, 28)
    let cpuParts = splitV(cpuSplit.right,
                          max(5, cpuSplit.right.h * regsSplitPercent div 100), 5)
    result.panes[pRegs] = cpuParts.top
    result.panes[pStack] = cpuParts.bot
    work = cpuSplit.left

  if sourceSwap and symtab.loaded:
    result.panes[pSource] = work
  elif wantSourceUnder and work.h >= 16:
    let codeParts = splitV(work,
                           max(8, work.h * codeSourceSplitPercent div 100), 6)
    result.panes[pDisasm] = codeParts.top
    result.panes[pSource] = codeParts.bot
  else:
    result.panes[pDisasm] = work

proc addDividerHits(layout: Layout; width, height: int) =
  if layout.tooSmall: return
  let
    mem = layout.panes[pMemory]
    log = layout.panes[pLog]
    dis = layout.panes[pDisasm]
    src = layout.panes[pSource]
    codeX = if dis.w > 0: dis.x elif src.w > 0: src.x else: -1
    codeH = max(dis.h + (if dis.w > 0 and src.w > 0 and src.x == dis.x: src.h else: 0),
                max(dis.h, src.h))
  if mem.h > 0 or log.h > 0:
    let y = if mem.h > 0: mem.y else: log.y
    addHit(Rect(x: 0, y: max(1, y-1), w: width, h: 2),
           actDivider, value = ord(dividerTopBottom))
  if mem.w > 0 and log.w > 0:
    addHit(Rect(x: max(0, log.x-1), y: log.y, w: 2, h: log.h),
           actDivider, value = ord(dividerMemoryLog))
  if layout.panes[pFuncs].w > 0 and codeX > 0:
    addHit(Rect(x: max(0, codeX-1), y: 1, w: 2, h: max(1, codeH)),
           actDivider, value = ord(dividerNavCode))
  if layout.panes[pFuncs].w > 0 and layout.panes[pBreaks].h > 0:
    addHit(Rect(x: layout.panes[pBreaks].x, y: max(1, layout.panes[pBreaks].y-1),
                w: layout.panes[pBreaks].w, h: 2),
           actDivider, value = ord(dividerFuncsBreaks))
  if layout.panes[pRegs].w > 0 and codeX >= 0:
    addHit(Rect(x: max(0, layout.panes[pRegs].x-1), y: 1, w: 2,
                h: max(1, layout.panes[pRegs].h + layout.panes[pStack].h)),
           actDivider, value = ord(dividerCodeCpu))
  if layout.panes[pStack].h > 0:
    addHit(Rect(x: layout.panes[pStack].x, y: max(1, layout.panes[pStack].y-1),
                w: layout.panes[pStack].w, h: 2),
           actDivider, value = ord(dividerRegsStack))
  if layout.panes[pDisplay].w > 0 and layout.panes[pRegs].w > 0:
    addHit(Rect(x: max(0, layout.panes[pDisplay].x-1), y: 1, w: 2,
                h: layout.panes[pDisplay].h),
           actDivider, value = ord(dividerCpuDisplay))
  if layout.panes[pDisasm].w > 0 and layout.panes[pSource].w > 0 and
      layout.panes[pSource].x == layout.panes[pDisasm].x:
    addHit(Rect(x: layout.panes[pSource].x, y: max(1, layout.panes[pSource].y-1),
                w: layout.panes[pSource].w, h: 2),
           actDivider, value = ord(dividerDisasmSource))

proc updateDivider(kind: DividerKind; x, y: int) =
  let size = tuiSize()
  case kind
  of dividerTopBottom:
    topSplitPercent = max(35, min(82, (y-1)*100 div max(1, size.h-2)))
  of dividerNavCode:
    navPercent = max(12, min(28, x*100 div max(1, size.w)))
  of dividerCodeCpu:
    cpuPercent = max(16, min(36, (size.w-x)*100 div max(1, size.w)))
  of dividerCpuDisplay:
    displayPercent = max(16, min(40, (size.w-x)*100 div max(1, size.w)))
  of dividerRegsStack:
    let layout = layoutFor(size.w, size.h)
    let regs = layout.panes[pRegs]
    let total = regs.h + layout.panes[pStack].h
    regsSplitPercent = max(25, min(75, (y-regs.y)*100 div max(1, total)))
  of dividerMemoryLog:
    memorySplitPercent = max(28, min(75, x*100 div max(1, size.w)))
  of dividerFuncsBreaks:
    let layout = layoutFor(size.w, size.h)
    let funcs = layout.panes[pFuncs]
    let total = funcs.h + layout.panes[pBreaks].h
    funcsBreaksSplitPercent = max(30, min(80, (y-funcs.y)*100 div max(1, total)))
  of dividerDisasmSource:
    let layout = layoutFor(size.w, size.h)
    let dis = layout.panes[pDisasm]
    let total = dis.h + layout.panes[pSource].h
    codeSourceSplitPercent = max(35, min(80, (y-dis.y)*100 div max(1, total)))
  of dividerNone: discard
  dirty = true

proc paneTitle(pane: PaneId): string =
  case pane
  of pDisasm: "1 Disasm"
  of pRegs: "2 Regs"
  of pDisplay: "3 Display"
  of pStack: "4 Stack"
  of pMemory: "5 Memory " & formatAddress(memoryTop)
  of pLog: "6 Log"
  of pSource: "7 Source"
  of pFuncs: "8 Funcs"
  of pBreaks: "9 Breaks"

proc drawPaneFrame(pane: PaneId; rect: Rect) =
  drawBox(rect.x, rect.y, rect.w, rect.h, paneTitle(pane), focus == pane)
  addHit(Rect(x: rect.x, y: rect.y, w: rect.w, h: rect.h), actFocus, pane)

proc addAddressHits(text: string; x, y: int; pane: PaneId) =
  var start = 0
  while start + 5 <= text.len:
    let found = text.find('$', start)
    if found < 0 or found + 4 >= text.len: break
    try:
      let address = parseHexInt(text[found+1..found+4])
      addHit(Rect(x: x+found, y: y, w: 5, h: 1), actAddress, pane, address)
    except ValueError:
      discard
    start = found + 5

proc drawDisassembly(rect: Rect) =
  drawPaneFrame(pDisasm, rect)
  let rows = max(0, rect.h - 2)
  if followPc:
    disCursor = PC and 0xffff
    if symtab.loaded:
      disTop = symtab.prevInsAddr(disCursor, rows div 3)
    else:
      var
        address = 0x1000
        history: seq[int]
      while address < disCursor and address < imageEnd:
        history.add(address)
        address += max(1, disasm(mem, address, collapseCalls = false).len)
      disTop = if history.len == 0: 0x1000
               else: history[max(0, history.len-rows div 3)]
  disRows.setLen(0)
  var address = disTop
  for row in 0..<rows:
    let instruction = disasm(mem, address,
      collapseCalls = not (PC > address and PC < address + 5 and
                           mem[address and 0xffff] == 0x96))
    disRows.add(address)
    var bytes = ""
    for i in 0..<min(instruction.len, 5):
      if i > 0: bytes.add(' ')
      bytes.add(toHex(mem[(address+i) and 0xffff], 2))
    bytes = bytes.alignLeft(14)
    var text = instruction.text
    if instruction.target >= 0 and symtab.loaded:
      text = text.replace(formatAddress(instruction.target), symtab.symbolize(instruction.target))
    let
      marker = (if address == disCursor: ">" else: " ") &
               (if userBreaks[address and 0xffff]: "●" else: " ")
      line = marker & " " & toHex(address, 4) & " " & bytes & " " & text
      color = if address == PC: Green elif not instruction.valid: Red else: White
    putStr(rect.x+1, rect.y+1+row, line, color,
           attrs = if address == disCursor: {caReverse} else: {})
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: max(0, rect.w-2), h: 1),
           actCursor, pDisasm, address)
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: 2, h: 1),
           actToggleBreak, pDisasm, address)
    if instruction.target >= 0:
      addHit(Rect(x: rect.x+min(rect.w-6, 23), y: rect.y+1+row,
                  w: max(0, rect.w-24), h: 1), actAddress, pDisasm,
             instruction.target)
    address = (address + max(1, instruction.len)) and 0xffff

proc drawRegs(rect: Rect) =
  drawPaneFrame(pRegs, rect)
  let lines = [
    "PC " & formatAddress(PC) & " " & symtab.symbolize(PC),
    "SP " & formatAddress(SP),
    "R0 $" & toHex(R0, 2) & " " & $R0 & "   R1 $" & toHex(R1, 2) & " " & $R1,
    "ZF" & (if ZF: "*" else: ".") & "  IF" & (if IF: "*" else: ".") &
      "  HF" & (if HF: "*" else: ".") &
      (if waiting: "  WAI" else: "") &
      "  " & (if running: "RUNNING" else: "PAUSED"),
    "end " & formatAddress(imageEnd),
    "keys " & $keyFifo.len & (if keyPending(): "+guest" else: "")]
  for i in 0..<min(lines.len, max(0, rect.h-2)):
    putStr(rect.x+1, rect.y+1+i, lines[i], if i == 0: Green else: White)
    addAddressHits(lines[i], rect.x+1, rect.y+1+i, pRegs)

proc drawStack(rect: Rect; merged = false) =
  if not merged: drawPaneFrame(pStack, rect)
  let
    startY = if merged: rect.y + min(7, rect.h-2) else: rect.y+1
    rows = max(0, rect.y+rect.h-1-startY)
  for row in 0..<rows:
    let address = SP - row
    if address < 0: break
    var line = toHex(address, 4) & " " & toHex(mem[address and 0xffff], 2)
    if row mod 2 == 0 and address > 0:
      let returnAddress = ((mem[(address-1) and 0xffff] shl 8) or mem[address and 0xffff]) and 0xffff
      line.add("  ret " & formatAddress(returnAddress) & " " & symtab.symbolize(returnAddress))
      addHit(Rect(x: rect.x+12, y: startY+row, w: max(0, rect.w-13), h: 1),
             actAddress, pStack, returnAddress)
    putStr(rect.x+1, startY+row, line, White)

proc drawDisplay(rect: Rect) =
  drawPaneFrame(pDisplay, rect)
  if rect.w > 2 and rect.h > 2:
    if not kittyEnabled:
      renderHalfBlock(rect.x+1, rect.y+1, rect.w-2, rect.h-2)

proc drawMemory(rect: Rect) =
  drawPaneFrame(pMemory, rect)
  let rows = max(0, rect.h-2)
  memoryTop = memoryTop and 0xfff0
  for row in 0..<rows:
    let address = (memoryTop + row*16) and 0xffff
    var line = toHex(address, 4) & "  "
    for column in 0..<16:
      line.add(toHex(mem[(address+column) and 0xffff], 2) & " ")
    line.add(" |")
    for column in 0..<16:
      let value = mem[(address+column) and 0xffff] and 0xff
      line.add(if value >= 32 and value < 127: char(value) else: '.')
    line.add('|')
    putStr(rect.x+1, rect.y+1+row, line, White)
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: max(0, rect.w-2), h: 1),
           actCursor, pMemory, address)
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: 4, h: 1),
           actAddress, pMemory, address)
    if memoryCursor >= address and memoryCursor < address+16:
      let cx = rect.x + 7 + (memoryCursor-address)*3
      putStr(cx, rect.y+1+row, toHex(mem[memoryCursor], 2), Yellow,
             attrs = {caReverse})

proc drawLog(rect: Rect) =
  drawPaneFrame(pLog, rect)
  let rows = max(0, rect.h-2)
  let first = max(0, eventLog.len - rows - logScroll)
  for row in 0..<rows:
    let index = first + row
    if index >= eventLog.len or index >= eventLog.len-logScroll: break
    let line = eventLog[index]
    putStr(rect.x+1, rect.y+1+row, line, Gray)
    addAddressHits(line, rect.x+1, rect.y+1+row, pLog)

proc syncSourceToPc() =
  if symtab.lineFor.hasKey(PC and 0xffff):
    let location = symtab.lineFor[PC and 0xffff]
    sourceFile = location.file
    sourceCursor = location.line
    sourceTop = max(1, sourceCursor-5)

proc drawSource(rect: Rect) =
  drawPaneFrame(pSource, rect)
  if not symtab.loaded:
    putStr(rect.x+2, rect.y+2, "no map loaded", Gray)
    return
  if followPc: syncSourceToPc()
  if sourceFile.len == 0: syncSourceToPc()
  let lines = symtab.sourceLines(sourceFile)
  sourceRows.setLen(0)
  for row in 0..<max(0, rect.h-2):
    let lineNo = sourceTop + row
    if lineNo > lines.len: break
    let address = symtab.addrFor.getOrDefault((sourceFile, lineNo), -1)
    sourceRows.add((lineNo, address))
    let marker = (if lineNo == sourceCursor: ">" else: " ") &
                 (if address >= 0 and userBreaks[address]: "●" else: " ")
    let text = marker & align($lineNo, 4) & " " & lines[lineNo-1]
    putStr(rect.x+1, rect.y+1+row, text,
           if address == PC: Green else: White,
           attrs = if lineNo == sourceCursor: {caReverse} else: {})
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: max(0, rect.w-2), h: 1),
           actCursor, pSource, lineNo)
    if address >= 0:
      addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: 2, h: 1),
             actToggleBreak, pSource, address)

proc drawFuncs(rect: Rect) =
  drawPaneFrame(pFuncs, rect)
  if funcList.len == 0:
    putStr(rect.x+2, rect.y+2, "no functions", Gray)
    return
  if followPc: syncFuncsToPc()
  let
    rows = max(0, rect.h-2)
    current = funcIndexAt(PC)
  if funcCursor < 0 or funcCursor >= funcList.len:
    funcCursor = max(0, current)
  if funcCursor < funcTop: funcTop = funcCursor
  if funcCursor >= funcTop+rows: funcTop = max(0, funcCursor-rows+1)
  if current >= 0 and followPc:
    if current < funcTop: funcTop = current
    if current >= funcTop+rows: funcTop = max(0, current-rows+1)
  let nameW = max(4, rect.w-10)
  for row in 0..<rows:
    let index = funcTop + row
    if index >= funcList.len: break
    let
      fn = funcList[index]
      marker = (if index == funcCursor: ">" else: " ") &
               (if userBreaks[fn.address]: "*" else: " ")
      name = if fn.name.len > nameW: fn.name[0..<nameW] else: fn.name
      text = marker & name
    putStr(rect.x+1, rect.y+1+row, text,
           if index == current: Green else: White,
           attrs = if index == funcCursor: {caReverse} else: {})
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: max(0, rect.w-2), h: 1),
           actCursor, pFuncs, index)
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: 2, h: 1),
           actToggleBreak, pFuncs, fn.address)

proc drawBreaks(rect: Rect) =
  drawPaneFrame(pBreaks, rect)
  if breakList.len == 0:
    putStr(rect.x+2, rect.y+2, "no breakpoints", Gray)
    return
  let rows = max(0, rect.h-2)
  if breakCursor < 0 or breakCursor >= breakList.len:
    breakCursor = 0
  if breakCursor < breakTop: breakTop = breakCursor
  if breakCursor >= breakTop+rows: breakTop = max(0, breakCursor-rows+1)
  let nameW = max(4, rect.w-4)
  for row in 0..<rows:
    let index = breakTop + row
    if index >= breakList.len: break
    let
      address = breakList[index]
      marker = if index == breakCursor: ">" else: " "
      label = formatAddress(address) & " " & symtab.symbolize(address)
      text = marker & (if label.len > nameW: label[0..<nameW] else: label)
    putStr(rect.x+1, rect.y+1+row, text,
           if address == (PC and 0xffff): Green else: Yellow,
           attrs = if index == breakCursor: {caReverse} else: {})
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: max(0, rect.w-2), h: 1),
           actCursor, pBreaks, index)
    addHit(Rect(x: rect.x+1, y: rect.y+1+row, w: 2, h: 1),
           actToggleBreak, pBreaks, address)

proc drawToolbar(width: int) =
  fillRect(0, 0, width, 1, bg = BarBackground)
  let buttons = [
    ("[c Run]", actContinue), ("[s In]", actStepIn),
    ("[n Over]", actStepOver), ("[f Out]", actStepOut),
    ("[r Rst]", actReset), ("[?]", actHelp)]
  var x = 0
  for (label, action) in buttons:
    putStr(x, 0, label, Blue, BarBackground, {caBold})
    addHit(Rect(x: x, y: 0, w: label.len, h: 1), action)
    x += label.len
  let status = "  " & (if running: "RUNNING " else: "PAUSED ") & stopReason &
    "  " & imagePath.extractFilename & "  " & formatFloat(mhz, ffDecimal, 2) &
    "MHz  ins=" & $ins_retired
  putStr(x, 0, status, if running: Green else: Yellow, BarBackground)

proc drawBottomBar(width, height: int) =
  let y = height-1
  fillRect(0, y, width, 1, bg = BarBackground)
  var left = ""
  if confirm != confirmNone:
    left = if confirm == confirmReset: "Reset CPU? [y/N]" else: "Quit while running? [y/N]"
  elif editActive:
    left = "Edit " & formatAddress(memoryCursor) & " = " & editHex & "__"[0..<max(0, 2-editHex.len)]
  elif mode == mEx:
    left = ":" & exBuffer
  elif mode == mInput:
    left = "Guest keyboard active — Esc returns to debugger"
  else:
    left = stopReason
  putStr(0, y, left, White, BarBackground)
  let indicator = case mode
    of mNormal: "-- NORMAL --"
    of mInput: "-- INPUT --"
    of mEx: "-- COMMAND --"
  putStr(max(0, width-indicator.len), y, indicator, Yellow, BarBackground, {caBold})

proc drawHelp(width, height: int) =
  let
    w = min(78, width-4)
    h = min(24, height-4)
    x = (width-w) div 2
    y = (height-h) div 2
  fillRect(x, y, w, h, bg = OverlayBackground)
  drawBox(x, y, w, h, "CUPC/8 debugger help", true)
  let lines = [
    "s step in   n/F10 step over   f step out   c/F5 continue",
    "Space run/pause   p pause   u run to cursor   r reset",
    "b/F9 breakpoint   i guest input   : command   q quit",
    "Tab/Shift-Tab or 1..9 focus panes; arrows/PgUp/PgDn scroll",
    "Layout: funcs/breaks | disasm + source | regs/stack | display",
    "Memory and log share the bottom row. Drag any shared border to resize.",
    "8/9 open a function or breakpoint; b/F9 toggles. :b <sym>  :bc clears.",
    "g re-sync to PC; Enter follows targets; Backspace navigates back",
    "Memory: x/Enter edits a byte while paused. Display: +/- zoom.",
    "Mouse: click panes/addresses/gutters; wheel scrolls; drag borders to resize.",
    "",
    "Breakpoints stop before the marked instruction. Continuing after a hit",
    "bypasses that same breakpoint once, then rearms it automatically.",
    "Guest input is queued host-side and fed only when its 1-byte buffer is free.",
    "No Super, Ctrl+Shift shortcuts, or F11 are used.",
    "",
    "Commands: b, bc, w, wd, g, until, load, reset, log, gfx, display, theme, dump, q",
    "Press ? or Esc to close this help."]
  for i in 0..<min(lines.len, h-2):
    putStr(x+2, y+1+i, lines[i], White, OverlayBackground)

proc renderFrame() =
  let size = tuiSize()
  clear()
  hitRects.setLen(0)
  drawToolbar(size.w)
  let layout = layoutFor(size.w, size.h)
  if layout.tooSmall:
    let message = "terminal too small — need at least 80×24"
    putStr(max(0, (size.w-message.runeLen) div 2), size.h div 2, message, Yellow)
  else:
    for pane in PaneId:
      let rect = layout.panes[pane]
      if rect.w <= 0: continue
      case pane
      of pDisasm: drawDisassembly(rect)
      of pRegs:
        drawRegs(rect)
        if size.w < 100: drawStack(rect, merged = true)
      of pStack: drawStack(rect)
      of pDisplay: drawDisplay(rect)
      of pMemory: drawMemory(rect)
      of pLog: drawLog(rect)
      of pSource: drawSource(rect)
      of pFuncs: drawFuncs(rect)
      of pBreaks: drawBreaks(rect)
    addDividerHits(layout, size.w, size.h)
  drawBottomBar(size.w, size.h)
  if helpVisible: drawHelp(size.w, size.h)
  if kittyEnabled and not helpVisible and not layout.tooSmall and layout.panes[pDisplay].w > 2:
    let r = layout.panes[pDisplay]
    discard renderKitty(r.x+1, r.y+1, r.w-2, r.h-2)
  else:
    discard present()
    if kittyEnabled and (helpVisible or layout.tooSmall or layout.panes[pDisplay].w <= 2):
      deleteKittyImage()
  dirty = false

proc gotoAddress(address: int) =
  let a = address and 0xffff
  if a >= 0x1000 and a < imageEnd and disasm(mem, a, false).valid:
    if disCursor != a: navHistory.add(disCursor)
    disCursor = a
    disTop = a
    followPc = false
    focus = pDisasm
    displaySwap = false
    sourceSwap = false
  else:
    memoryCursor = a
    memoryTop = a and 0xfff0
    focus = pMemory
  dirty = true

proc cursorAddress(): int =
  case focus
  of pDisasm: disCursor
  of pSource: symtab.addrFor.getOrDefault((sourceFile, sourceCursor), -1)
  of pMemory: memoryCursor
  of pFuncs:
    if funcCursor >= 0 and funcCursor < funcList.len: funcList[funcCursor].address
    else: -1
  of pBreaks:
    if breakCursor >= 0 and breakCursor < breakList.len: breakList[breakCursor]
    else: -1
  else: -1

proc executeCommand(commandLine: string): bool =
  let fields = commandLine.splitWhitespace()
  if fields.len == 0: return true
  let command = fields[0].toLowerAscii
  case command
  of "b":
    if fields.len < 2: stopReason = "usage: :b <symbol|address>"
    else:
      let address = resolveToken(fields[1])
      if address < 0: stopReason = "unknown address " & fields[1]
      else: toggleBreakpoint(address)
  of "bc":
    for address in 0..userBreaks.high: userBreaks[address] = false
    clearAllBreaks()
    if tempBreak >= 0: setBreak(tempBreak)
    rebuildBreakList()
    stopReason = "breakpoints cleared"
  of "w":
    if fields.len < 2:
      stopReason = "usage: :w <addr> [r|w|rw] [len]"
    else:
      let address = resolveToken(fields[1])
      var mask = 3'u8
      if fields.len >= 3:
        case fields[2].toLowerAscii
        of "r": mask = 1
        of "w": mask = 2
        of "rw", "wr": mask = 3
        else: mask = 0
      var length = 1
      try:
        if fields.len >= 4: length = max(1, parseInt(fields[3]))
      except ValueError: length = 0
      if address < 0 or mask == 0 or length <= 0:
        stopReason = "invalid watchpoint"
      else:
        watches.add(Watch(address: address, length: length, mask: mask))
        rebuildWatchMask()
        stopReason = "watchpoint " & $watches.len & " at " & formatAddress(address)
  of "wd":
    if fields.len < 2: stopReason = "usage: :wd <n>"
    else:
      try:
        let index = parseInt(fields[1])-1
        if index < 0 or index >= watches.len: raise newException(ValueError, "range")
        watches.delete(index)
        rebuildWatchMask()
        stopReason = "watchpoint deleted"
      except ValueError: stopReason = "invalid watchpoint number"
  of "g":
    if fields.len < 2: stopReason = "usage: :g <address|symbol>"
    else:
      let address = resolveToken(fields[1])
      if address < 0: stopReason = "unknown address " & fields[1]
      else: gotoAddress(address)
  of "until":
    if fields.len < 2: stopReason = "usage: :until <address>"
    else:
      let address = resolveToken(fields[1])
      if address < 0: stopReason = "unknown address " & fields[1]
      else: runUntil(address)
  of "load":
    if fields.len < 2: stopReason = "usage: :load <image.o> [map]"
    else: loadImage(fields[1], if fields.len >= 3: fields[2] else: "")
  of "reset": resetCpu()
  of "log":
    if fields.len != 3 or fields[2].toLowerAscii notin ["on", "off"]:
      stopReason = "usage: :log <gpo|spi0|key|sd> on|off"
    else:
      let enabled = fields[2].toLowerAscii == "on"
      case fields[1].toLowerAscii
      of "gpo": logGpo = enabled
      of "spi0": logSpi0 = enabled
      of "key": logKey = enabled
      of "sd": logSd = enabled
      else:
        stopReason = "unknown log source"
        return true
      stopReason = "log " & fields[1] & " " & fields[2]
  of "gfx":
    if fields.len != 2: stopReason = "usage: :gfx kitty|half|auto"
    else:
      case fields[1].toLowerAscii
      of "kitty": kittyEnabled = true; gfxMode = gfxKitty
      of "half": deleteKittyImage(); kittyEnabled = false; gfxMode = gfxHalf
      of "auto": kittyEnabled = queryKittyGfx(); gfxMode = gfxAuto
      else: stopReason = "unknown graphics mode"
      resetKittyImage()
      forceRedraw()
  of "display":
    if fields.len != 2:
      stopReason = "usage: :display embedded|window"
    else:
      case fields[1].toLowerAscii
      of "embedded": setDisplayMode(displayEmbedded)
      of "window": setDisplayMode(displayWindow)
      else: stopReason = "unknown display mode"
  of "theme":
    if fields.len != 2:
      stopReason = "usage: :theme auto|dark|light"
    else:
      case fields[1].toLowerAscii
      of "auto": themeMode = themeAuto
      of "dark": themeMode = themeDark
      of "light": themeMode = themeLight
      else:
        stopReason = "unknown theme"
        return true
      applyTheme()
      stopReason = "theme " & fields[1].toLowerAscii
  of "dump":
    if fields.len != 2: stopReason = "usage: :dump <path.ppm>"
    else:
      display_dumpPpm(fields[1])
      stopReason = "wrote " & fields[1]
  of "q", "quit":
    if running: confirm = confirmQuit
    else: return false
  else: stopReason = "unknown command: " & command
  dirty = true
  true

proc scrollPane(pane: PaneId; amount: int) =
  case pane
  of pDisasm:
    followPc = false
    if amount < 0: disTop = symtab.prevInsAddr(disTop, -amount)
    else:
      for i in 0..<amount: disTop = (disTop + disasm(mem, disTop).len) and 0xffff
    disCursor = disTop
  of pMemory:
    memoryTop = (memoryTop + amount*16) and 0xffff
    memoryCursor = memoryTop
  of pLog: logScroll = max(0, min(eventLog.len, logScroll-amount))
  of pSource:
    sourceTop = max(1, sourceTop+amount)
    sourceCursor = max(1, sourceCursor+amount)
    followPc = false
  of pFuncs:
    followPc = false
    if funcList.len == 0: return
    funcCursor = max(0, min(funcList.len-1, funcCursor+amount))
    let rows = 12
    if funcCursor < funcTop: funcTop = funcCursor
    if funcCursor >= funcTop+rows: funcTop = max(0, funcCursor-rows+1)
  of pBreaks:
    if breakList.len == 0: return
    breakCursor = max(0, min(breakList.len-1, breakCursor+amount))
    if breakCursor < breakTop: breakTop = breakCursor
    if breakCursor >= breakTop+8: breakTop = max(0, breakCursor-7)
  of pStack: discard
  of pRegs: discard
  of pDisplay: setDisplayZoom(displayZoom + (if amount < 0: 1 else: -1))
  dirty = true

proc activate(action: HitRect) =
  case action.kind
  of actFocus:
    focus = action.pane
    if action.pane == pDisplay: mode = mInput
  of actContinue: continueRun()
  of actStepIn: stepInto()
  of actStepOver: stepOver()
  of actStepOut: stepOut()
  of actReset: confirm = confirmReset
  of actHelp: helpVisible = not helpVisible
  of actToggleBreak: toggleBreakpoint(action.value)
  of actAddress: gotoAddress(action.value)
  of actCursor:
    focus = action.pane
    case action.pane
    of pDisasm:
      disCursor = action.value
      followPc = false
    of pMemory:
      memoryCursor = action.value
    of pSource:
      sourceCursor = action.value
      followPc = false
    of pFuncs:
      if action.value >= 0 and action.value < funcList.len:
        funcCursor = action.value
        followPc = false
        gotoAddress(funcList[funcCursor].address)
        focus = pFuncs
    of pBreaks:
      if action.value >= 0 and action.value < breakList.len:
        breakCursor = action.value
        gotoAddress(breakList[breakCursor])
        focus = pBreaks
    else: discard
  of actDivider:
    dragDivider = DividerKind(action.value)
  of actNone: discard
  dirty = true

proc handleMouse(event: tui.Event) =
  if helpVisible: return
  if event.mouseAction == mouseMove and dragDivider != dividerNone:
    updateDivider(dragDivider, event.x, event.y)
    return
  if event.mouseAction == mouseRelease:
    dragDivider = dividerNone
    return
  if event.mouseAction == mouseWheel:
    let size = tuiSize()
    let layout = layoutFor(size.w, size.h)
    for pane in PaneId:
      if layout.panes[pane].contains(event.x, event.y):
        scrollPane(pane, if event.wheel > 0: -3 else: 3)
        return
  elif event.mouseAction == mousePress and event.mouseButton == mouseLeft:
    for i in countdown(hitRects.high, 0):
      if hitRects[i].rect.contains(event.x, event.y):
        activate(hitRects[i])
        return

proc focusOrder(): array[9, PaneId] =
  [pFuncs, pBreaks, pDisasm, pRegs, pDisplay, pStack, pMemory, pLog, pSource]

proc cycleFocus(backward: bool) =
  let
    size = tuiSize()
    layout = layoutFor(size.w, size.h)
    order = focusOrder()
  var visible: seq[PaneId]
  for pane in order:
    if layout.panes[pane].w > 0: visible.add(pane)
  if visible.len == 0: return
  var index = 0
  for i, pane in visible:
    if pane == focus: index = i
  index = (index + (if backward: visible.len-1 else: 1)) mod visible.len
  focus = visible[index]
  dirty = true

proc selectPane(pane: PaneId) =
  let
    size = tuiSize()
    preview = layoutFor(size.w, size.h)
  proc visible(id: PaneId): bool = preview.panes[id].w > 0
  case pane
  of pDisasm:
    focus = pDisasm
    displaySwap = false
    sourceSwap = false
    funcSwap = false
    breakSwap = false
  of pDisplay:
    if displayMode == displayEmbedded:
      focus = pDisplay
      if not visible(pDisplay):
        displaySwap = true
        sourceSwap = false
        funcSwap = false
        breakSwap = false
  of pSource:
    if symtab.loaded:
      focus = pSource
      if not visible(pSource):
        sourceSwap = true
        displaySwap = false
        funcSwap = false
        breakSwap = false
  of pFuncs:
    if funcList.len > 0 or symtab.loaded:
      focus = pFuncs
      if not visible(pFuncs):
        funcSwap = true
        breakSwap = false
        sourceSwap = false
        displaySwap = false
  of pBreaks:
    focus = pBreaks
    if not visible(pBreaks):
      breakSwap = true
      funcSwap = false
      sourceSwap = false
      displaySwap = false
  of pStack:
    focus = if visible(pStack): pStack else: pRegs
  of pMemory:
    focus = pMemory
    if size.h < 28: bottomLog = false
  of pLog:
    focus = pLog
    if size.h < 28: bottomLog = true
  of pRegs: focus = pRegs
  dirty = true

proc handleNormal(event: tui.Event): bool =
  if event.key == keyCtrlC:
    confirm = confirmQuit; dirty = true; return true
  if event.key == keyCtrlL:
    forceRedraw(); dirty = true; return true
  if helpVisible:
    if event.key == keyEscape or (event.key == keyChar and event.text == "?"):
      helpVisible = false; dirty = true
    return true
  if confirm != confirmNone:
    if event.key == keyChar and event.text.toLowerAscii == "y":
      let action = confirm
      confirm = confirmNone
      if action == confirmQuit: return false
      resetCpu()
    elif event.key in {keyEscape, keyEnter} or event.key == keyChar:
      confirm = confirmNone; dirty = true
    return true
  if editActive:
    if event.key == keyEscape:
      editActive = false; editHex.setLen(0)
    elif event.key == keyBackspace and editHex.len > 0:
      editHex.setLen(editHex.len-1)
    elif event.key == keyChar and event.text.len == 1 and event.text[0] in HexDigits:
      editHex.add(event.text)
      if editHex.len == 2:
        mem[memoryCursor] = parseHexInt(editHex)
        editActive = false
        editHex.setLen(0)
    dirty = true
    return true
  case event.key
  of keyTab: cycleFocus(false)
  of keyShiftTab: cycleFocus(true)
  of keyF5: continueRun()
  of keyF9:
    let address = cursorAddress()
    if address >= 0: toggleBreakpoint(address)
  of keyF10: stepOver()
  of keyUp: scrollPane(focus, -1)
  of keyDown: scrollPane(focus, 1)
  of keyPageUp: scrollPane(focus, -10)
  of keyPageDown: scrollPane(focus, 10)
  of keyHome:
    if focus == pMemory: memoryTop = 0; memoryCursor = 0
    elif focus == pDisasm: disTop = 0x1000; disCursor = disTop; followPc = false
    elif focus == pSource: sourceTop = 1; sourceCursor = 1; followPc = false
    elif focus == pFuncs and funcList.len > 0:
      funcCursor = 0; funcTop = 0; followPc = false
    elif focus == pBreaks and breakList.len > 0:
      breakCursor = 0; breakTop = 0
    dirty = true
  of keyEnd:
    if focus == pMemory: memoryTop = 0xfff0; memoryCursor = 0xffff
    elif focus == pDisasm: disTop = imageEnd and 0xffff; disCursor = disTop; followPc = false
    elif focus == pFuncs and funcList.len > 0:
      funcCursor = funcList.len-1; followPc = false
    elif focus == pBreaks and breakList.len > 0:
      breakCursor = breakList.len-1
    dirty = true
  of keyLeft:
    if focus == pMemory: memoryCursor = (memoryCursor-1) and 0xffff; dirty = true
  of keyRight:
    if focus == pMemory: memoryCursor = (memoryCursor+1) and 0xffff; dirty = true
  of keyEnter:
    if focus == pDisasm:
      let instruction = disasm(mem, disCursor)
      if instruction.target >= 0: gotoAddress(instruction.target)
    elif focus == pSource:
      let address = cursorAddress()
      if address >= 0: gotoAddress(address)
    elif focus == pFuncs:
      let address = cursorAddress()
      if address >= 0: gotoAddress(address)
    elif focus == pBreaks:
      let address = cursorAddress()
      if address >= 0: gotoAddress(address)
    elif focus == pMemory and not running:
      editActive = true; editHex.setLen(0); dirty = true
  of keyBackspace:
    if focus == pDisasm and navHistory.len > 0:
      disCursor = navHistory.pop(); disTop = disCursor; followPc = false; dirty = true
  of keyChar:
    let key = event.text
    case key
    of "s": stepInto()
    of "n": stepOver()
    of "f": stepOut()
    of "c": continueRun()
    of " ":
      if running: pause("paused") else: continueRun()
    of "p": pause("paused")
    of "u":
      let address = cursorAddress()
      if address >= 0: runUntil(address)
    of "r": confirm = confirmReset; dirty = true
    of "b":
      let address = cursorAddress()
      if address >= 0: toggleBreakpoint(address)
    of "i": mode = mInput; dirty = true
    of ":": mode = mEx; exBuffer.setLen(0); dirty = true
    of "?": helpVisible = true; dirty = true
    of "q":
      if running: confirm = confirmQuit; dirty = true
      else: return false
    of "g":
      if focus in {pDisasm, pSource, pFuncs}:
        followPc = true; disCursor = PC; dirty = true
      elif focus == pMemory:
        mode = mEx; exBuffer = "g "; dirty = true
    of "x":
      if focus == pMemory and not running:
        editActive = true; editHex.setLen(0); dirty = true
    of "+": setDisplayZoom(displayZoom+1); dirty = true
    of "-": setDisplayZoom(displayZoom-1); dirty = true
    of "1": selectPane(pDisasm)
    of "2": selectPane(pRegs)
    of "3": selectPane(pDisplay)
    of "4": selectPane(pStack)
    of "5": selectPane(pMemory)
    of "6": selectPane(pLog)
    of "7": selectPane(pSource)
    of "8": selectPane(pFuncs)
    of "9": selectPane(pBreaks)
    else: discard
  else: discard
  true

proc handleEvent(event: tui.Event): bool =
  if event.kind == evResize:
    resizeBuf(event.x, event.y)
    resetKittyImage()
    dirty = true
    return true
  if event.kind == evMouse:
    handleMouse(event)
    return true
  if event.kind != evKey: return true
  if mode == mInput:
    if event.key == keyEscape:
      mode = mNormal; dirty = true
    elif event.key == keyCtrlC:
      mode = mNormal; confirm = confirmQuit; dirty = true
    elif event.key == keyCtrlL:
      forceRedraw(); dirty = true
    elif event.key == keyChar:
      for ch in event.text: keyFifo.addLast(ord(ch))
    elif event.key == keyEnter: keyFifo.addLast(13)
    elif event.key == keyBackspace: keyFifo.addLast(8)
    return true
  if mode == mEx:
    case event.key
    of keyEscape: mode = mNormal; dirty = true
    of keyEnter:
      mode = mNormal
      return executeCommand(exBuffer)
    of keyBackspace:
      if exBuffer.len > 0: exBuffer.setLen(exBuffer.len-1)
      dirty = true
    of keyChar: exBuffer.add(event.text); dirty = true
    of keyCtrlC: mode = mNormal; confirm = confirmQuit; dirty = true
    of keyCtrlL: forceRedraw(); dirty = true
    else: discard
    return true
  handleNormal(event)

proc runTuiTest() =
  var last = "press keys or click; q exits"
  var active = true
  while active:
    let size = tuiSize()
    clear()
    for y in 0..<size.h:
      for x in 0..<size.w:
        let color = 0x01000000'u32 or uint32((x*255 div max(1,size.w-1)) shl 16) or
                    uint32((y*255 div max(1,size.h-1)) shl 8) or 0x40'u32
        putStr(x, y, " ", bg = color)
    putStr(2, 1, "simtui terminal test", White, 0x01000000'u32, {caBold})
    putStr(2, 3, last, White, 0x01000000'u32)
    discard present()
    let event = pollEvent(100)
    if event.kind == evResize:
      resizeBuf(event.x, event.y)
    elif event.kind == evMouse:
      last = "mouse $1 at $2,$3 button=$4 wheel=$5" % [
        $event.mouseAction, $event.x, $event.y, $event.mouseButton, $event.wheel]
    elif event.kind == evKey:
      last = "key " & $event.key & " text='" & event.text & "'"
      if event.key == keyEscape or (event.key == keyChar and event.text == "q"):
        active = false

proc runApplication() =
  installMemoryHook()
  sim.log_mask = 0
  loadImage(imagePath, mapPath)
  tuiInit()
  applyTheme()
  case gfxMode
  of gfxKitty: kittyEnabled = true
  of gfxHalf: kittyEnabled = false
  of gfxAuto: kittyEnabled = queryKittyGfx()
  if displayMode == displayWindow:
    setDisplayMode(displayWindow)
  var
    active = true
    lastRender = getMonoTime()
    lastRate = lastRender
    lastDisplay = lastRender
    lastRateIns = ins_retired
    batch = 100_000
  while active:
    pumpWindowEvents()
    let event = pollEvent(if running and not waiting: 0 else: 30)
    if event.kind != evNone: active = handleEvent(event)
    if not active: break
    if keyFifo.len > 0 and not keyPending(): pushKey(keyFifo.popFirst())
    if running:
      let sliceStart = getMonoTime()
      while running and (getMonoTime()-sliceStart).inMilliseconds < 10:
        let callStart = getMonoTime()
        let exit = cpuRun(batch)
        let elapsed = max(1'i64, (getMonoTime()-callStart).inMicroseconds)
        batch = max(1_000, min(1_000_000, int(int64(batch)*3000 div elapsed)))
        handleRunExit(exit)
        if keyFifo.len > 0 and not keyPending(): pushKey(keyFifo.popFirst())
        if exit != reCount: break
    let now = getMonoTime()
    if displayMode == displayWindow and display_dirty and
        (now-lastDisplay).inMilliseconds >= 16:
      display_render()
      lastDisplay = now
    if (now-lastRate).inMilliseconds >= 1000:
      let seconds = float((now-lastRate).inNanoseconds) / 1_000_000_000.0
      mhz = float(ins_retired-lastRateIns) / seconds / 1_000_000.0
      lastRate = now
      lastRateIns = ins_retired
      dirty = true
    if (running and (now-lastRender).inMilliseconds >= 16) or (not running and dirty):
      renderFrame()
      lastRender = now
  memHook = nil

proc usage() =
  echo "usage: simtui [--map:PATH] [--gfx:auto|kitty|half]"
  echo "               [--display:embedded|window] [--theme:auto|dark|light] <image.o>"
  echo "       simtui --tuitest"

when isMainModule:
  var tuiTest = false
  var parser = initOptParser()
  for kind, key, value in parser.getopt():
    case kind
    of cmdArgument: imagePath = key
    of cmdLongOption, cmdShortOption:
      case key
      of "map": mapPath = value
      of "gfx":
        case value.toLowerAscii
        of "auto": gfxMode = gfxAuto
        of "kitty": gfxMode = gfxKitty
        of "half": gfxMode = gfxHalf
        else:
          usage(); quit(1)
      of "display":
        case value.toLowerAscii
        of "embedded": displayMode = displayEmbedded
        of "window": displayMode = displayWindow
        else: usage(); quit(1)
      of "theme":
        case value.toLowerAscii
        of "auto": themeMode = themeAuto
        of "dark": themeMode = themeDark
        of "light": themeMode = themeLight
        else: usage(); quit(1)
      of "tuitest": tuiTest = true
      of "help", "h": usage(); quit(0)
      else:
        echo "unknown option: ", key
        usage(); quit(1)
    of cmdEnd: discard
  if not tuiTest and imagePath.len == 0:
    usage()
    quit(1)
  try:
    if tuiTest:
      tuiInit()
      applyTheme()
      runTuiTest()
    else:
      runApplication()
  finally:
    memHook = nil
    tuiShutdown()
