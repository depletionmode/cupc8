## CUPC/8

###### Documentation
https://github.com/depletionmode/cupc8/blob/master/doc/CUPC8%20Manual.md

###### Blog
http://depletionmode.com/

### Terminal debugger

Build the debugger from `tools/` with:

```sh
nim c -d:release simtui.nim
```

Then run `kernel/debug.sh`. The guest display is embedded by default; use
`kernel/debug.sh --display:window` for the standalone SDL window. Terminal
graphics and color treatment can be selected explicitly:

```sh
kernel/debug.sh --gfx:half --theme:light
kernel/debug.sh --gfx:auto --theme:dark
```

Inside the debugger, `:display embedded|window`, `:theme auto|dark|light`, and
`:gfx auto|kitty|half` switch these modes without restarting. Pane borders can
be dragged with the mouse to resize the layout. Press `?` for the complete
keymap and command reference.
