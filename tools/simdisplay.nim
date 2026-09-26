# ili9340 display: persistent 320x240 framebuffer, integer-scaled window.

import strutils
import sdl2

const
  DispScaleDefault* = 3
  LedStrip = 28          # window pixels under the picture for the LEDs

var
  # the framebuffer size follows the card in the slot: 320x240 for the
  # legacy ILI9340 model, 640x480 for the GPU card
  DispWidth* = 320
  DispHeight* = 240
  win: WindowPtr
  ren: RendererPtr
  tex: TexturePtr
  display_inited*: bool = false
  display_init_error*: string = ""
  dispScale*: int = DispScaleDefault
  display_dirty*: bool = false
  # the main board's GPO LEDs D8..D1 ($f000), drawn in a strip under the
  # picture in the M1 machine; -1 = no strip (the legacy model)
  display_leds*: int = -1

  # RGB888 packed 0x00RRGGBB
  fb: seq[uint32] = newSeq[uint32](320 * 240)

  dc: bool = false
  state = "NOSTATE"
  casetPhase = 0
  pasetPhase = 0
  winX0, winX1, winY0, winY1: int
  curX, curY: int
  colorHi: int = -1

proc display_setScale*(s: int) =
  if s >= 1 and s <= 8:
    dispScale = s

proc display_pixel*(x, y: int): uint32 =
  if x < 0 or y < 0 or x >= DispWidth or y >= DispHeight:
    return 0
  result = fb[y * DispWidth + x]

proc display_setSize*(w, h: int) =
  ## Resize the framebuffer (and the window, if it is already open).
  if w == DispWidth and h == DispHeight:
    return
  DispWidth = w
  DispHeight = h
  fb = newSeq[uint32](w * h)
  display_dirty = true
  if display_inited:
    tex = createTexture(ren, SDL_PIXELFORMAT_ARGB8888.uint32,
                        SDL_TEXTUREACCESS_STREAMING.cint, w.cint, h.cint)
    win.setSize(cint(w * dispScale), cint(h * dispScale + (if display_leds >= 0: LedStrip else: 0)))

proc display_blit*(src: ptr uint32) =
  ## Copy a full frame of 0x00RRGGBB pixels into the framebuffer.
  let p = cast[ptr UncheckedArray[uint32]](src)
  for i in 0..fb.high:
    fb[i] = 0xFF000000'u32 or p[i]
  display_dirty = true

proc display_reset*() =
  for i in 0..fb.high:
    fb[i] = 0
  dc = false
  state = "NOSTATE"
  casetPhase = 0
  pasetPhase = 0
  winX0 = 0
  winX1 = DispWidth
  winY0 = 0
  winY1 = DispHeight
  curX = 0
  curY = 0
  colorHi = -1
  display_dirty = true

proc rgb565to32(c: int): uint32 =
  let
    r5 = (c shr 11) and 0x1f
    g6 = (c shr 5) and 0x3f
    b5 = c and 0x1f
    r = (r5 * 255) div 31
    g = (g6 * 255) div 63
    b = (b5 * 255) div 31
  # ARGB8888
  result = 0xFF000000'u32 or (uint32(r) shl 16) or (uint32(g) shl 8) or uint32(b)

proc putPixel(color: uint32) =
  if curX >= 0 and curY >= 0 and curX < DispWidth and curY < DispHeight:
    fb[curY * DispWidth + curX] = color
    display_dirty = true
  inc curX
  if curX >= winX1:
    curX = winX0
    inc curY

proc display_dumpPpm*(path: string) =
  var f = open(path, fmWrite)
  f.write("P6\n$# $#\n255\n" % [$DispWidth, $DispHeight])
  for y in 0..<DispHeight:
    for x in 0..<DispWidth:
      let p = fb[y * DispWidth + x]
      var pix: array[3, char]
      pix[0] = char((p shr 16) and 0xff)
      pix[1] = char((p shr 8) and 0xff)
      pix[2] = char(p and 0xff)
      discard f.writeBuffer(addr pix[0], 3)
  f.close()

proc display_init*(resetFramebuffer = true): bool =
  if display_inited:
    return true
  if resetFramebuffer:
    display_reset()
  if sdl2.init(INIT_VIDEO) != SdlSuccess:
    display_init_error = "sdl2.init: " & $getError()
    return false
  discard setHint(HINT_RENDER_SCALE_QUALITY, "0")
  let ww = cint(DispWidth * dispScale)
  let hh = cint(DispHeight * dispScale + (if display_leds >= 0: LedStrip else: 0))
  win = createWindow("CUPC/8",
                     SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                     ww, hh,
                     SDL_WINDOW_SHOWN or SDL_WINDOW_RESIZABLE)
  if win.isNil:
    display_init_error = "createWindow: " & $getError()
    return false
  ren = createRenderer(win, -1, Renderer_Accelerated)
  if ren.isNil:
    display_init_error = "createRenderer: " & $getError()
    return false
  tex = createTexture(ren, SDL_PIXELFORMAT_ARGB8888.uint32,
                      SDL_TEXTUREACCESS_STREAMING.cint,
                      DispWidth.cint, DispHeight.cint)
  if tex.isNil:
    display_init_error = "createTexture: " & $getError()
    return false
  startTextInput()
  display_inited = true
  display_dirty = true
  return true

proc display_setVisible*(visible: bool) =
  if win.isNil: return
  if visible: win.show()
  else: win.hide()

proc display_render*() =
  if not display_inited:
    return
  discard updateTexture(tex, nil, addr fb[0], cint(DispWidth * 4))
  var ww, hh: cint
  win.getSize(ww, hh)
  let strip = (if display_leds >= 0: LedStrip.cint else: 0.cint)
  let s = max(1.cint, min(ww div DispWidth.cint, (hh - strip) div DispHeight.cint))
  var dst: Rect
  dst.w = DispWidth.cint * s
  dst.h = DispHeight.cint * s
  dst.x = (ww - dst.w) div 2
  dst.y = (hh - strip - dst.h) div 2
  ren.setDrawColor(0, 0, 0, 255)
  discard ren.clear()
  discard ren.copy(tex, nil, addr dst)
  if display_leds >= 0:
    # eight lights, D8 (bit 7) on the left, amber when lit
    const d = 14.cint
    const gap = 12.cint
    let total = 8 * d + 7 * gap
    var r: Rect
    r.w = d
    r.h = d
    r.y = hh - strip + (strip - d) div 2
    for i in 0..7:
      let bit = 7 - i
      r.x = (ww - total) div 2 + cint(i) * (d + gap)
      if ((display_leds shr bit) and 1) == 1:
        ren.setDrawColor(255, 176, 32, 255)
      else:
        ren.setDrawColor(48, 30, 12, 255)
      discard ren.fillRect(r)
  ren.present()
  display_dirty = false

proc display_set_dc*(b: int) =
  dc = (b == 1)

proc display_transact*(b: int) =
  let v = b and 0xff
  if not dc:
    case v:
      of 0x2a:
        state = "CASET"
        casetPhase = 0
      of 0x2b:
        state = "PASET"
        pasetPhase = 0
      of 0x2c:
        state = "RAMWR"
        curX = winX0
        curY = winY0
        colorHi = -1
      else:
        state = "NOSTATE"
    return

  case state:
    of "CASET":
      case casetPhase:
        of 0:
          winX0 = v shl 8
        of 1:
          winX0 = (winX0 and 0xff00) or v
        of 2:
          winX1 = v shl 8
        of 3:
          winX1 = (winX1 and 0xff00) or v
          # kernel sends exclusive end (x+w); keep that
          if winX1 <= winX0:
            winX1 = winX0 + 1
          state = "NOSTATE"
        else:
          discard
      inc casetPhase
    of "PASET":
      case pasetPhase:
        of 0:
          winY0 = v shl 8
        of 1:
          winY0 = (winY0 and 0xff00) or v
        of 2:
          winY1 = v shl 8
        of 3:
          winY1 = (winY1 and 0xff00) or v
          if winY1 <= winY0:
            winY1 = winY0 + 1
          state = "NOSTATE"
        else:
          discard
      inc pasetPhase
    of "RAMWR":
      if colorHi < 0:
        colorHi = v
      else:
        putPixel(rgb565to32((colorHi shl 8) or v))
        colorHi = -1
    else:
      discard

proc display_dumpWindow*(path: string) =
  ## What the window shows (picture and LED strip), as a PPM.
  if not display_inited: return
  display_render()
  var ww, hh: cint
  win.getSize(ww, hh)
  var px = newSeq[uint32](int(ww) * int(hh))
  discard ren.readPixels(nil, SDL_PIXELFORMAT_ARGB8888.cint, addr px[0], ww * 4)
  var f = open(path, fmWrite)
  f.write("P6\n$# $#\n255\n" % [$ww, $hh])
  for p in px:
    var pix: array[3, char]
    pix[0] = char((p shr 16) and 0xff)
    pix[1] = char((p shr 8) and 0xff)
    pix[2] = char(p and 0xff)
    discard f.writeBuffer(addr pix[0], 3)
  f.close()
