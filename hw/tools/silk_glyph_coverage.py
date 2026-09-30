"""Measure plotted text against independently decoded stroke-font coordinates.

Requires the source PCB to be parity-bound to these Gerbers by the caller.
The source supplies identity, orientation and search location. The fitted
vertical scale comes from delivered stroke coordinates, not source font size.
Font decoding follows the documented 21-unit newstroke format; it never calls
KiCad's glyph renderer or exports a reference text.
"""
import ctypes,ctypes.util,sys,re,math,collections,hashlib
from pathlib import Path
import pcbnew,gerberdrc as gd

def table():
 path=ctypes.util.find_library('kicommon')
 if not path:raise ValueError('independent glyph coverage needs installed kicommon font table')
 lib=ctypes.CDLL(path)
 if ctypes.c_int.in_dll(lib,'newstroke_font_bufsize').value<95:raise ValueError('incomplete font table')
 return (ctypes.c_char_p*95).in_dll(lib,'newstroke_font')
FONT=table()
def glyphs(text):
 result=[];cursor=0
 for char in text:
  if not 32<=ord(char)<127:raise ValueError('nonascii')
  raw=FONT[ord(char)-32].decode();start=ord(raw[0])-82;old=None
  for i in range(2,len(raw),2):
   if raw[i:i+2]==' R':old=None;continue
   p=((ord(raw[i])-82-start)/21+cursor,(ord(raw[i+1])-82-8)/21)
   if old is not None:result.append((old,p))
   old=p
  cursor+=(ord(raw[1])-ord(raw[0]))/21
 return result
def strokes(path):
 rows=[];ap={};current=None;pos=None;region=False
 for line in Path(path).read_text().splitlines():
  if m:=gd.APERTURE.fullmatch(line):ap[int(m[1])]=(m[2],tuple(float(x) for x in m[3].split('X')))
  elif m:=gd.SELECT.fullmatch(line):current=int(m[1])
  elif line=='G36*':region=True
  elif line=='G37*':region=False
  elif m:=gd.COORD.fullmatch(line):
   x=int(m[1])/1e6 if m[1] is not None else pos[0];y=-int(m[2])/1e6 if m[2] is not None else pos[1];p=(x,y)
   if m[3]=='01' and not region and ap[current][0]=='C':rows.append((pos,p,ap[current][1][0],len(rows)))
   pos=p
 return rows
def fit(expected,actual,angle,mirror):
 theta=math.radians(angle);c,s=math.cos(theta),math.sin(theta)
 points=[]
 for row in actual:
  for x,y in row[:2]:points.append(((x*c-y*s)*(-1 if mirror else 1),x*s+y*c))
 ep=[p for row in expected for p in row]
 scale=[];err=0
 for axis in (0,1):
  e=[p[axis] for p in ep];a=[p[axis] for p in points];ec=sum(e)/len(e);ac=sum(a)/len(a)
  variance=sum((v-ec)**2 for v in e)
  if variance<1e-10:return None
  k=sum((u-ec)*(v-ac) for u,v in zip(e,a))/variance
  err=max(err,max(abs(v-(ac+k*(u-ec))) for u,v in zip(e,a)));scale.append(k)
 return scale,err
def objects(board):
 result=[]
 draw=board.Drawings()
 for i in range(len(draw)):
  d=draw[i].Cast()
  if d.Type()==pcbnew.PCB_TEXT_T:result.append(d)
 for f in board.GetFootprints():
  result +=[f.Reference(),f.Value()]
  draw=f.GraphicalItems()
  for i in range(len(draw)):
   d=draw[i].Cast()
   if d.Type()==pcbnew.PCB_TEXT_T:result.append(d)
 return [d for d in result if d.IsVisible() and d.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS)]

def certify(board, silk):
 import silktextaudit
 minimum,inventory=silktextaudit.inventory(board)
 source={t.m_Uuid.AsString():t for t in objects(board)}
 if set(source)!={t['uuid'] for t in inventory}:raise ValueError('incomplete visible text identity coverage')
 paths={}
 for path in silk:
  content=Path(path).read_text()
  sides=[layer for side,layer in [('Top',pcbnew.F_SilkS),('Bot',pcbnew.B_SilkS)] if '%TF.FileFunction,Legend,'+side in content]
  if len(sides)!=1 or sides[0] in paths:raise ValueError('silk glyph coverage needs distinct front/back Legend layers')
  paths[sides[0]]=Path(path)
 if set(paths)!={pcbnew.F_SilkS,pcbnew.B_SilkS}:raise ValueError('silk glyph coverage needs both layers')
 rows={}
 for layer,path in paths.items():
  # Validate the entire supported Gerber grammar before extracting strokes.
  engine=gd.Geometry()
  try:gd.plotted_copper(path,engine,require_net=False,extra_function='Legend',allow_empty=True)
  finally:engine.close()
  rows[layer]=strokes(path)
 used=set();proofs=[]
 for identity in inventory:
  text=source[identity['uuid']];shown=identity['shown_text']
  if text.GetFont() is not None or text.IsBold() or text.IsItalic() or any(c in shown for c in ('\n','\t','~','{','}')):raise ValueError('unsupported glyph font/style/markup: '+identity['uuid'])
  expected=glyphs(shown)
  if not expected:raise ValueError('text has no measurable glyph strokes: '+identity['uuid'])
  bb=text.GetBoundingBox();x0,y0,x1,y1=[pcbnew.ToMM(v) for v in (bb.GetX(),bb.GetY(),bb.GetRight(),bb.GetBottom())]
  candidates=[r for r in rows[text.GetLayer()] if all(x0-.01<=p[0]<=x1+.01 and y0-.01<=p[1]<=y1+.01 for p in r[:2])]
  matches=[]
  for i in range(len(candidates)-len(expected)+1):
   actual=candidates[i:i+len(expected)]
   measured=fit(expected,actual,text.GetTextAngleDegrees(),text.IsMirrored())
   if measured and measured[1]<=.000003 and min(measured[0])>0:matches.append((measured,actual))
  if len(matches)!=1:raise ValueError('plotted glyph coverage ambiguous/missing/unmeasurable: '+identity['uuid']+' '+shown)
  (scale,error),actual=matches[0]
  # One-nanometre output quantization plus native integer rounding. This
  # tolerance is fixed independently of the minimum and of source fontsize.
  tolerance=.000003
  if scale[1]<minimum-tolerance:raise ValueError('plotted text height %.6f mm < %.6f mm: %s'%(scale[1],minimum,shown))
  if abs(scale[1]-identity['nominal_height_mm'])>tolerance or abs(scale[0]-identity['nominal_width_mm'])>tolerance:raise ValueError('plotted font scale differs from source identity: '+shown)
  if any(abs(r[2]-identity['stroke_mm'])>.000001 for r in actual):raise ValueError('plotted glyph stroke width differs from source: '+shown)
  indices={(text.GetLayer(),r[3]) for r in actual}
  if used&indices:raise ValueError('two text identities consume the same plotted glyph strokes')
  used.update(indices)
  proofs.append(dict(uuid=identity['uuid'],text=shown,height_mm=scale[1],width_mm=scale[0],residual_mm=error,stroke_count=len(actual)))
 return dict(complete=True,text_count=len(proofs),minimum_mm=minimum,coordinate_tolerance_mm=.000003,font_ascii_sha256=hashlib.sha256(b'\0'.join(FONT)).hexdigest(),texts=proofs)
