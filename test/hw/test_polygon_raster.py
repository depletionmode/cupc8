from pathlib import Path as FilePath
import sys,unittest,numpy as np,pcbnew as p
from matplotlib.path import Path
ROOT=FilePath(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/power'));from polygon_raster import path_grid_mask,grid_poly
import copper_mesh as cm

def legacy_poly(grid,mask,poly_set):
 pts=np.column_stack((grid.X.ravel(),grid.Y.ravel()))
 for outline,holes in cm._shape_paths(poly_set):
  lo,hi=outline.vertices.min(0),outline.vertices.max(0)
  selected=(pts[:,0]>=lo[0])&(pts[:,0]<=hi[0])&(pts[:,1]>=lo[1])&(pts[:,1]<=hi[1])
  inside=outline.contains_points(pts[selected])
  for hole in holes:inside &= ~hole.contains_points(pts[selected])
  mask.ravel()[np.flatnonzero(selected)[inside]]=True

class ExactRaster(unittest.TestCase):
 def compare(self,vertices,xs,ys):
  path=Path(np.asarray(vertices,float));X,Y=np.meshgrid(xs,ys)
  expected=path.contains_points(np.column_stack((X.ravel(),Y.ravel()))).reshape(X.shape)
  np.testing.assert_array_equal(path_grid_mask(path,xs,ys),expected)
 def test_horizontal_edges_vertices_and_float_neighbors(self):
  v=np.array([(0,0),(2,0),(2,2),(0,2)],float)
  axis=np.unique(np.concatenate((np.linspace(-.1,2.1,30),v[:,0],np.nextafter(v[:,0],np.inf),np.nextafter(v[:,0],-np.inf))))
  self.compare(v,axis,axis);self.compare(v[::-1],axis,axis)
 def test_self_crossings_collinear_and_repeated_closure(self):
  axis=np.linspace(-1,3,81)
  for v in [[(0,0),(2,2),(0,2),(2,0)],[(0,0),(1,1),(2,2)],[(0,0),(2,0),(2,2),(0,2),(0,0)]]:self.compare(v,axis,axis)
 def test_random_concave_polygons(self):
  rng=np.random.default_rng(123)
  for _ in range(40):
   vertices=rng.uniform(-1,1,(rng.integers(3,100),2));self.compare(vertices,np.linspace(-1.1,1.1,45),np.linspace(-1.1,1.1,43))
 def test_explicit_holes_and_multiple_outlines(self):
  q=p.SHAPE_POLY_SET();q.NewOutline()
  for x,y in [(0,0),(3000000,0),(3000000,3000000),(0,3000000)]:q.Append(x,y)
  h=q.NewHole()
  for x,y in [(1000000,1000000),(1000000,2000000),(2000000,2000000),(2000000,1000000)]:q.Append(x,y,-1,h)
  q.NewOutline()
  for x,y in [(4000000,0),(5000000,0),(5000000,1000000),(4000000,1000000)]:q.Append(x,y)
  for pitch in (.1,.07,.05,.035):
   grid=cm.Grid((-.1,-.1,5.1,3.1),pitch);expected=np.zeros(grid.X.shape,bool);actual=expected.copy()
   legacy_poly(grid,expected,q);cm.Grid.poly(grid,actual,q)
   np.testing.assert_array_equal(actual,expected)
 def test_native_rotated_pad_polygons(self):
  board=p.BOARD();footprint=p.FOOTPRINT(board);board.Add(footprint)
  count=0
  for shape in (p.PAD_SHAPE_CIRCLE,p.PAD_SHAPE_OVAL,p.PAD_SHAPE_RECT,p.PAD_SHAPE_ROUNDRECT):
   pad=p.PAD(footprint);pad.SetShape(shape);pad.SetSize(p.VECTOR2I(1300000,700000));pad.SetPosition(p.VECTOR2I(17405000,-15925000));pad.SetOrientationDegrees(17.35)
   if shape==p.PAD_SHAPE_ROUNDRECT:pad.SetRoundRectRadiusRatio(.25)
   footprint.Add(pad);q=pad.GetEffectivePolygon(p.F_Cu,p.ERROR_INSIDE);paths=list(cm._shape_paths(q));vertices=np.concatenate([outline.vertices for outline,_ in paths]);lo=vertices.min(0)-.1;hi=vertices.max(0)+.1
   for pitch in (.1,.07,.05,.035):
    grid=cm.Grid((*lo,*hi),pitch);expected=np.zeros(grid.X.shape,bool);actual=expected.copy();legacy_poly(grid,expected,q);cm.Grid.poly(grid,actual,q);np.testing.assert_array_equal(actual,expected)
   count+=1
  self.assertEqual(count,4)

if __name__=='__main__':unittest.main()
