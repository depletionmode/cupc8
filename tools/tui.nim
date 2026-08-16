## Small dependency-free ANSI terminal UI core.

import atomics
import posix
import std/exitprocs
import std/termios
import strutils
import times
import unicode

type
  CellAttr* = enum caBold, caDim, caUnderline, caReverse
  Cell* = object
    grapheme*: string
    fg*, bg*: uint32
    attrs*: set[CellAttr]
  SinkProc* = proc(data: string)
  Key* = enum
    keyNone, keyChar, keyUp, keyDown, keyLeft, keyRight,
    keyPageUp, keyPageDown, keyHome, keyEnd, keyEnter, keyTab,
    keyShiftTab, keyBackspace, keyDelete, keyEscape,
    keyF1, keyF2, keyF3, keyF4, keyF5, keyF6, keyF7, keyF8,
    keyF9, keyF10, keyF12, keyCtrlC, keyCtrlL
  MouseAction* = enum mousePress, mouseRelease, mouseMove, mouseWheel
  MouseButton* = enum mouseLeft, mouseMiddle, mouseRight, mouseNone
  EventKind* = enum evNone, evKey, evMouse, evResize
  Event* = object
    kind*: EventKind
    key*: Key
    text*: string
    x*, y*: int
    mouseAction*: MouseAction
    mouseButton*: MouseButton
    wheel*: int

const
  Esc = '\e'
  DefaultWidth = 80
  DefaultHeight = 24

var SIGWINCH {.importc, header: "<signal.h>".}: cint

var
  cells, previous: seq[Cell]
  lastChanged: seq[bool]
  screenWidth = DefaultWidth
  screenHeight = DefaultHeight
  emitSink: SinkProc
  inputBuffer = ""
  initialized = false
  terminalActive = false
  termiosSaved = false
  originalTermios: Termios
  exitProcAdded = false
  signalHandlersAdded = false
  resizePending: Atomic[bool]
  defaultFg: uint32 = 0
  defaultBg: uint32 = 0

proc blankCell(): Cell = Cell(grapheme: " ", fg: defaultFg, bg: defaultBg)

proc forceRedraw*() =
  for i in 0..<previous.len:
    previous[i] = Cell(grapheme: "\x00")

proc setDefaultColors*(fg, bg: uint32) =
  defaultFg = fg
  defaultBg = bg
  forceRedraw()

proc emit(data: string) =
  if not emitSink.isNil and data.len > 0:
    emitSink(data)

proc fileSink(file: File): SinkProc =
  result = proc(data: string) =
    file.write(data)
    file.flushFile()

proc terminalDimensions(): tuple[w, h: int] =
  var size: IOctl_WinSize
  if ioctl(STDOUT_FILENO, TIOCGWINSZ, addr size) == 0 and
      size.ws_col > 0 and size.ws_row > 0:
    (int(size.ws_col), int(size.ws_row))
  else:
    (DefaultWidth, DefaultHeight)

proc tuiSize*(): tuple[w, h: int] = (screenWidth, screenHeight)

proc resizeBuf*(width, height: int) =
  screenWidth = max(1, width)
  screenHeight = max(1, height)
  cells = newSeq[Cell](screenWidth * screenHeight)
  previous = newSeq[Cell](screenWidth * screenHeight)
  lastChanged = newSeq[bool](screenWidth * screenHeight)
  for i in 0..<cells.len:
    cells[i] = blankCell()
    previous[i] = Cell(grapheme: "\x00")

proc clear*() =
  for i in 0..<cells.len:
    cells[i] = blankCell()

proc putCell(x, y: int; cell: Cell) =
  if x >= 0 and x < screenWidth and y >= 0 and y < screenHeight:
    cells[y * screenWidth + x] = cell

proc putStr*(x, y: int; value: string; fg: uint32 = 0; bg: uint32 = 0;
             attrs: set[CellAttr] = {}) =
  var column = x
  for rune in value.runes:
    if column >= screenWidth: break
    if column >= 0:
      putCell(column, y, Cell(grapheme: $rune,
        fg: (if fg == 0: defaultFg else: fg),
        bg: (if bg == 0: defaultBg else: bg), attrs: attrs))
    inc column

proc fillRect*(x, y, width, height: int; glyph = " "; fg: uint32 = 0;
               bg: uint32 = 0; attrs: set[CellAttr] = {}) =
  let cell = Cell(grapheme: glyph,
                  fg: (if fg == 0: defaultFg else: fg),
                  bg: (if bg == 0: defaultBg else: bg), attrs: attrs)
  for row in max(0, y)..<min(screenHeight, y + max(0, height)):
    for column in max(0, x)..<min(screenWidth, x + max(0, width)):
      putCell(column, row, cell)

proc drawBox*(x, y, width, height: int; title = ""; focused = false) =
  if width < 2 or height < 2: return
  let color = if focused: 0x015fcfff'u32 else: 0x01708090'u32
  putStr(x, y, "┌", color)
  putStr(x + width - 1, y, "┐", color)
  putStr(x, y + height - 1, "└", color)
  putStr(x + width - 1, y + height - 1, "┘", color)
  for column in (x + 1)..<(x + width - 1):
    putStr(column, y, "─", color)
    putStr(column, y + height - 1, "─", color)
  for row in (y + 1)..<(y + height - 1):
    putStr(x, row, "│", color)
    putStr(x + width - 1, row, "│", color)
  if title.len > 0 and width > 4:
    var shown = title
    if shown.runeLen > width - 4:
      shown.setLen(0)
      var count = 0
      for rune in title.runes:
        if count >= width - 4: break
        shown.add($rune)
        inc count
    putStr(x + 2, y, shown, color,
           attrs = if focused: {caBold} else: {})

proc sgr(cell: Cell): string =
  var codes = @["0"]
  if caBold in cell.attrs: codes.add("1")
  if caDim in cell.attrs: codes.add("2")
  if caUnderline in cell.attrs: codes.add("4")
  if caReverse in cell.attrs: codes.add("7")
  if cell.fg == 0:
    codes.add("39")
  else:
    codes.add("38;2;$1;$2;$3" % [
      $((cell.fg shr 16) and 0xff), $((cell.fg shr 8) and 0xff),
      $(cell.fg and 0xff)])
  if cell.bg == 0:
    codes.add("49")
  else:
    codes.add("48;2;$1;$2;$3" % [
      $((cell.bg shr 16) and 0xff), $((cell.bg shr 8) and 0xff),
      $(cell.bg and 0xff)])
  Esc & "[" & codes.join(";") & "m"

proc present*(): bool =
  if cells.len == 0: return false
  for i in 0..<lastChanged.len: lastChanged[i] = false
  var output = ""
  for row in 0..<screenHeight:
    var column = 0
    while column < screenWidth:
      let index = row * screenWidth + column
      if cells[index] == previous[index]:
        inc column
        continue
      let style = cells[index]
      output.add(Esc & "[" & $(row + 1) & ";" & $(column + 1) & "H")
      output.add(sgr(style))
      while column < screenWidth:
        let current = row * screenWidth + column
        if cells[current] == previous[current] or
            cells[current].fg != style.fg or cells[current].bg != style.bg or
            cells[current].attrs != style.attrs:
          break
        output.add(if cells[current].grapheme.len == 0: " " else: cells[current].grapheme)
        previous[current] = cells[current]
        lastChanged[current] = true
        inc column
  if output.len > 0:
    emit(output)
    return true

proc rectTouched*(x, y, width, height: int): bool =
  for row in max(0, y)..<min(screenHeight, y + max(0, height)):
    for column in max(0, x)..<min(screenWidth, x + max(0, width)):
      if lastChanged[row * screenWidth + column]: return true

proc rawEmit*(x, y: int; sequence: string) =
  emit(Esc & "[" & $(y + 1) & ";" & $(x + 1) & "H" & sequence)

proc tuiShutdown*() =
  if not initialized: return
  initialized = false
  if terminalActive:
    emit(Esc & "_Ga=d,d=A,q=2" & Esc & "\\")
    emit(Esc & "[?1006l" & Esc & "[?1002l" & Esc & "[?1000l")
    emit(Esc & "[0m" & Esc & "[?25h" & Esc & "[?1049l")
  if termiosSaved:
    discard tcSetAttr(STDIN_FILENO, TCSANOW, addr originalTermios)
  terminalActive = false
  termiosSaved = false

proc installHandlers() =
  if not exitProcAdded:
    addExitProc(tuiShutdown)
    exitProcAdded = true
  if not signalHandlersAdded:
    onSignal(SIGWINCH):
      resizePending.store(true, moRelaxed)
    onSignal(SIGINT, SIGTERM, SIGHUP):
      tuiShutdown()
      quit(128 + int(sig))
    signalHandlersAdded = true

proc tuiInit*(sink: File = stdout) =
  if initialized: tuiShutdown()
  emitSink = fileSink(sink)
  let size = terminalDimensions()
  resizeBuf(size.w, size.h)
  inputBuffer.setLen(0)
  discard tcGetAttr(STDIN_FILENO, addr originalTermios)
  var raw = originalTermios
  raw.c_iflag = raw.c_iflag and not Cflag(BRKINT or ICRNL or INPCK or ISTRIP or IXON)
  raw.c_oflag = raw.c_oflag and not Cflag(OPOST)
  raw.c_cflag = (raw.c_cflag and not Cflag(CSIZE or PARENB)) or CS8
  raw.c_lflag = raw.c_lflag and not Cflag(ECHO or ICANON or IEXTEN or ISIG)
  raw.c_cc[VMIN] = char(0)
  raw.c_cc[VTIME] = char(0)
  termiosSaved = tcSetAttr(STDIN_FILENO, TCSANOW, addr raw) == 0
  initialized = true
  terminalActive = true
  installHandlers()
  emit(Esc & "[?1049h" & Esc & "[?25l" & Esc & "[?1000h" &
       Esc & "[?1002h" & Esc & "[?1006h" & Esc & "[2J" & Esc & "[H")

proc tuiInit*(sink: SinkProc; width = DefaultWidth; height = DefaultHeight) =
  ## Buffer-only initializer for unit tests and embedders with their own tty.
  if initialized: tuiShutdown()
  emitSink = sink
  resizeBuf(width, height)
  inputBuffer.setLen(0)
  initialized = true
  terminalActive = false
  termiosSaved = false

proc readAvailable(timeoutMs: int): bool =
  var descriptor = TPollfd(fd: STDIN_FILENO, events: POLLIN)
  let ready = poll(addr descriptor, Tnfds(1), cint(max(0, timeoutMs)))
  if ready <= 0 or (descriptor.revents and POLLIN) == 0:
    return false
  var buffer: array[512, char]
  let count = posix.read(STDIN_FILENO, addr buffer[0], buffer.len)
  if count > 0:
    for i in 0..<int(count): inputBuffer.add(buffer[i])
    return true

proc keyEvent(key: Key; text = ""): Event =
  Event(kind: evKey, key: key, text: text)

proc utf8Bytes(first: uint8): int =
  if first < 0x80: 1
  elif first < 0xe0: 2
  elif first < 0xf0: 3
  else: 4

proc parseMouse(sequence: string): Event =
  let body = sequence[3..^2].split(';')
  if body.len != 3: return Event(kind: evNone)
  try:
    let
      code = parseInt(body[0])
      column = parseInt(body[1]) - 1
      row = parseInt(body[2]) - 1
      release = sequence[^1] == 'm'
    result = Event(kind: evMouse, x: column, y: row,
                   mouseAction: if release: mouseRelease else: mousePress,
                   mouseButton: mouseNone)
    if (code and 64) != 0:
      result.mouseAction = mouseWheel
      result.wheel = if (code and 1) == 0: 1 else: -1
    elif (code and 32) != 0:
      result.mouseAction = mouseMove
      result.mouseButton = if (code and 3) <= 2:
                             MouseButton(code and 3)
                           else:
                             mouseNone
    elif (code and 3) <= 2:
      result.mouseButton = MouseButton(code and 3)
  except ValueError:
    result = Event(kind: evNone)

proc parseInput(): Event =
  if inputBuffer.len == 0: return Event(kind: evNone)
  if inputBuffer[0] != Esc:
    let value = ord(inputBuffer[0])
    case value
    of 3:
      inputBuffer.delete(0..0); return keyEvent(keyCtrlC)
    of 12:
      inputBuffer.delete(0..0); return keyEvent(keyCtrlL)
    of 9:
      inputBuffer.delete(0..0); return keyEvent(keyTab)
    of 10, 13:
      inputBuffer.delete(0..0); return keyEvent(keyEnter)
    of 8, 127:
      inputBuffer.delete(0..0); return keyEvent(keyBackspace)
    else:
      let count = utf8Bytes(uint8(value))
      if inputBuffer.len < count: return Event(kind: evNone)
      let value = inputBuffer[0..<count]
      inputBuffer.delete(0..<count)
      return keyEvent(keyChar, value)

  if inputBuffer.len == 1: return Event(kind: evNone)
  if inputBuffer.startsWith(Esc & "O") and inputBuffer.len >= 3:
    let key = case inputBuffer[2]
      of 'P': keyF1
      of 'Q': keyF2
      of 'R': keyF3
      of 'S': keyF4
      else: keyNone
    inputBuffer.delete(0..2)
    return keyEvent(key)
  if not inputBuffer.startsWith(Esc & "["):
    inputBuffer.delete(0..0)
    return keyEvent(keyEscape)
  if inputBuffer.startsWith(Esc & "[<"):
    var finish = -1
    for i in 3..<inputBuffer.len:
      if inputBuffer[i] == 'M' or inputBuffer[i] == 'm':
        finish = i; break
    if finish < 0: return Event(kind: evNone)
    let sequence = inputBuffer[0..finish]
    inputBuffer.delete(0..finish)
    return parseMouse(sequence)

  var finish = -1
  for i in 2..<inputBuffer.len:
    if inputBuffer[i] in {'A'..'Z', 'a'..'z', '~'}:
      finish = i; break
  if finish < 0: return Event(kind: evNone)
  let sequence = inputBuffer[0..finish]
  inputBuffer.delete(0..finish)
  let key = case sequence
    of Esc & "[A": keyUp
    of Esc & "[B": keyDown
    of Esc & "[C": keyRight
    of Esc & "[D": keyLeft
    of Esc & "[H", Esc & "[1~", Esc & "[7~": keyHome
    of Esc & "[F", Esc & "[4~", Esc & "[8~": keyEnd
    of Esc & "[5~": keyPageUp
    of Esc & "[6~": keyPageDown
    of Esc & "[3~": keyDelete
    of Esc & "[Z": keyShiftTab
    of Esc & "[11~": keyF1
    of Esc & "[12~": keyF2
    of Esc & "[13~": keyF3
    of Esc & "[14~": keyF4
    of Esc & "[15~": keyF5
    of Esc & "[17~": keyF6
    of Esc & "[18~": keyF7
    of Esc & "[19~": keyF8
    of Esc & "[20~": keyF9
    of Esc & "[21~": keyF10
    of Esc & "[24~": keyF12
    else: keyNone
  keyEvent(key)

proc pollEvent*(timeoutMs: int): Event =
  if resizePending.exchange(false, moRelaxed):
    let size = terminalDimensions()
    if size.w != screenWidth or size.h != screenHeight:
      return Event(kind: evResize, x: size.w, y: size.h)
  result = parseInput()
  if result.kind != evNone: return
  discard readAvailable(timeoutMs)
  result = parseInput()
  if result.kind != evNone: return
  if inputBuffer == $Esc:
    discard readAvailable(25)
    if inputBuffer == $Esc:
      inputBuffer.setLen(0)
      return keyEvent(keyEscape)
    result = parseInput()

proc queryKittyGfx*(): bool =
  let query = Esc & "_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA" & Esc & "\\"
  emit(query & Esc & "[c")
  let deadline = epochTime() + 0.100
  var response = ""
  while epochTime() < deadline:
    var descriptor = TPollfd(fd: STDIN_FILENO, events: POLLIN)
    if poll(addr descriptor, Tnfds(1), 10) > 0:
      var buffer: array[256, char]
      let count = posix.read(STDIN_FILENO, addr buffer[0], buffer.len)
      for i in 0..<max(0, int(count)): response.add(buffer[i])
      let kittyAt = response.find(Esc & "_Gi=31;")
      let fenceAt = response.find('c')
      if fenceAt >= 0:
        return kittyAt >= 0 and kittyAt < fenceAt
  false
