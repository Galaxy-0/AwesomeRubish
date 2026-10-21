"""Symmetric segment grouping for the independent offline model only.

CollisionMesh is two-sided and trims epsilon at both endpoints. A segment may
therefore be reversed; group by the endpoint with fewer distinct coordinates.
Native geometry/visibility code and historical BatchMesh remain unchanged.
"""
import numpy as np
def clear_pairs(mesh,starts,ends,epsilon=.015):
 starts=np.asarray(starts,float);ends=np.asarray(ends,float)
 if len(np.unique(ends,axis=0))<len(np.unique(starts,axis=0)):
  return mesh.clear_pairs(ends,starts,epsilon)
 return mesh.clear_pairs(starts,ends,epsilon)
