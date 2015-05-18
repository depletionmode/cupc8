import strutils
import sdl2, sdl2/gfx

discard sdl2.init(INIT_EVERYTHING)

var
    win: WindowPtr
    render: RendererPtr

win = createWindow("CUPCake Simulator", 100, 100, 256, 256, SDL_WINDOW_SHOWN)
when defined(emscripten):
  render = createRenderer(win, -1, Renderer_Software)
else:
  render = createRenderer(win, -1, Renderer_Accelerated)

render.setDrawColor 0,0,0,255 # black background
render.clear
render.present

render.setDrawColor 255,255,255,255 # always use white for now

var r : Rect
var state = "NOSTATE"
var rect_bitmask = 0
proc display_transact*(b) =
    var v : cint = (cint)b
    case state:
        of "CASET":
            if (rect_bitmask and 1) == 0:
                r.x = v
                rect_bitmask = rect_bitmask or 1
            elif (rect_bitmask and 2) == 0:
                r.w = (v - r.x) and 0xff
                rect_bitmask = rect_bitmask or 2
            if (rect_bitmask and 3) == 3:
                state = "NOSTATE"
        of "RASET":
            if (rect_bitmask and 4) == 0:
                r.y = v
                rect_bitmask = rect_bitmask or 4
            elif (rect_bitmask and 8) == 0:
                r.h = (v - r.y) and 0xff
                rect_bitmask = rect_bitmask or 8
            if (rect_bitmask and 12) == 12:
                state = "NOSTATE"
        of "COLOR_A":
            state = "COLOR_B"
        of "COLOR_B":
            state = "NOSTATE"
        else:
            case v:
                of 42:
                    state = "CASET"
                    rect_bitmask = rect_bitmask and 12
                    r.x = 0
                    r.w = 0
                of 43:
                    state = "RASET"
                    rect_bitmask = rect_bitmask and 3
                    r.y = 0
                    r.h = 0
                of 44:
                    state = "COLOR_A"
                    render.fillRect r
                    render.present
                else:
                    var a = 1 # pass?
