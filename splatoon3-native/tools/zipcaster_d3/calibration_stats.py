"""Small-sample rank and explicitly scoped controller calibration statistics."""
import math
import numpy as np

def ranks(x):
 x=np.asarray(x,float);out=np.empty(len(x));order=np.argsort(x,kind='stable');i=0
 while i<len(x):
  j=i+1
  while j<len(x)and x[order[j]]==x[order[i]]:j+=1
  out[order[i:j]]=(i+j-1)/2+1;i=j
 return out

def spearman(x,y):
 if len(x)<2:return None
 a,b=ranks(x),ranks(y)
 if np.ptp(a)==0 or np.ptp(b)==0:return None
 return float(np.corrcoef(a,b)[0,1])

def kendall(x,y):
 c=d=tx=ty=0
 for i in range(len(x)):
  for j in range(i+1,len(x)):
   a=np.sign(x[i]-x[j]);b=np.sign(y[i]-y[j])
   if a and b:c+=a==b;d+=a!=b
   elif not a and b:tx+=1
   elif a and not b:ty+=1
 den=math.sqrt((c+d+tx)*(c+d+ty));return float((c-d)/den)if den else None

def beta_interval(success,n):
 a,b=success+1,n-success+1;m=a+b-1
 def cdf(x):return sum(math.comb(m,j)*x**j*(1-x)**(m-j)for j in range(a,m+1))
 result=[]
 for p in [.025,.975]:
  lo,hi=0.,1.
  for _ in range(60):
   mid=(lo+hi)/2
   if cdf(mid)<p:lo=mid
   else:hi=mid
  result.append((lo+hi)/2)
 return result

def fit_reliability(predicted,observed):
 """MLE of Bernoulli(p_model*rho), a controller-surrogate parameter only."""
 p=np.asarray(predicted);y=np.asarray(observed);grid=np.linspace(.001,1.,1000)
 if not len(p)or not(p>.01).any():return 1.
 probability=np.clip(p[:,None]*grid[None,:],1e-8,1-1e-8);score=(y[:,None]*np.log(probability)+(1-y[:,None])*np.log1p(-probability)).sum(axis=0)
 return float(grid[np.argmax(score)])

def metrics(p,y):
 p=np.asarray(p,float);y=np.asarray(y,float)
 return dict(n=len(p),brier=float(np.mean((p-y)**2))if len(p)else None,mae=float(np.mean(np.abs(p-y)))if len(p)else None,mean_predicted=float(p.mean())if len(p)else None,observed=float(y.mean())if len(p)else None)
