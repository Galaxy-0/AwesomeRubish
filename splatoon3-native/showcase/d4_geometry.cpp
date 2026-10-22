// Browser-only own numerical geometry. No game runtime hooks or assets.
// Same predicates as tools/zipcaster_d4/geometry.cpp, supplied derived BVH.
namespace std {
 template<class T> T min(T a,T b){return a<b?a:b;} template<class T> T max(T a,T b){return a>b?a:b;}
 double abs(double a){return __builtin_fabs(a);} double sqrt(double a){return __builtin_sqrt(a);}
 bool isfinite(double a){return __builtin_isfinite(a);} template<class T> void swap(T&a,T&b){T c=a;a=b;b=c;}
}
extern "C" void*memcpy(void*d,const void*s,unsigned long n){char*a=(char*)d;const char*b=(const char*)s;for(unsigned long i=0;i<n;i++)a[i]=b[i];return d;}
struct V { double x,y,z; double operator[](int i)const{return i==0?x:i==1?y:z;} };
static V operator+(V a,V b){return{a.x+b.x,a.y+b.y,a.z+b.z};}
static V operator-(V a,V b){return{a.x-b.x,a.y-b.y,a.z-b.z};}
static V operator*(V a,double b){return{a.x*b,a.y*b,a.z*b};}
static double dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static V cross(V a,V b){return{a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static V low(V a,V b){return{std::min(a.x,b.x),std::min(a.y,b.y),std::min(a.z,b.z)};}
static V high(V a,V b){return{std::max(a.x,b.x),std::max(a.y,b.y),std::max(a.z,b.z)};}
struct Tri {V a,b,c,n,lo,hi;double area;};
struct Node {V lo,hi;int begin,end,left=-1,right=-1;};
struct Mesh {Tri*tri;int*order;Node*nodes;int node_count;};
static Mesh meshes[2];static double output[5];
static bool box(V lo,V hi,V o,V d,double maximum,double pad){
 double near=0,far=maximum;
 for(int i=0;i<3;i++){if(std::abs(d[i])<1e-15){if(o[i]<lo[i]-pad||o[i]>hi[i]+pad)return false;}
  else{double a=(lo[i]-pad-o[i])/d[i],b=(hi[i]+pad-o[i])/d[i];if(a>b)std::swap(a,b);near=std::max(near,a);far=std::min(far,b);if(near>far)return false;}}
 return far>=0;
}
struct Hit {int index=-1,priority=99;double t=1e300;V point{0,0,0};};
static void accept(Hit&h,double t,V p,int index,int priority,double maximum){
 if(!std::isfinite(t)||t<=1e-5||t>maximum+1e-6)return;
 if(t<h.t-1e-12||(std::abs(t-h.t)<=1e-12&&(priority<h.priority||(priority==h.priority&&index<h.index))))h={index,priority,t,p};
}
static void sphere_tri(const Tri&t,int index,V o,V d,double r,double maximum,Hit&h){
 V ab=t.b-t.a,ac=t.c-t.a;double nd=dot(t.n,d),sd=dot(o-t.a,t.n);
 double aa=dot(ab,ab),bb=dot(ab,ac),cc=dot(ac,ac),den=aa*cc-bb*bb;
 if(t.area>1e-12&&std::abs(nd)>1e-12&&std::abs(den)>1e-14){
  for(int s=0;s<2;s++){double sign=s?1:-1,along=(sign*r-sd)/nd;V p=o+d*along-t.n*(sign*r),q=p-t.a;double d20=dot(q,ab),d21=dot(q,ac),u=(cc*d20-bb*d21)/den,v=(aa*d21-bb*d20)/den;
   if(u>=-1e-7&&v>=-1e-7&&u+v<=1+1e-7)accept(h,along,p,index,s,maximum);}
 }
 V v[3]={t.a,t.b,t.c};
 for(int k=0;k<3;k++){
  V p0=v[k],ba=v[(k+1)%3]-p0,oa=o-p0;double baba=dot(ba,ba),bard=dot(ba,d),baoa=dot(ba,oa),rdoa=dot(d,oa),oaoa=dot(oa,oa),A=baba-bard*bard,B=baba*rdoa-baoa*bard,C=baba*oaoa-baoa*baoa-r*r*baba,disc=B*B-A*C;
  if(disc>=0&&baba>1e-12&&std::abs(A)>1e-12){double along=(-B-std::sqrt(disc))/A,y=baoa+along*bard;if(y>=0&&y<=baba)accept(h,along,p0+ba*(y/baba),index,2+k,maximum);}
 }
 for(int k=0;k<3;k++){V oc=o-v[k];double B=dot(oc,d),C=dot(oc,oc)-r*r,disc=B*B-C;if(disc>=0)accept(h,-B-std::sqrt(disc),v[k],index,5+k,maximum);}
}
static Hit sphere(const Mesh&m,V o,V d,double r,double maximum){
 Hit hit;if(!m.node_count)return hit;double len=std::sqrt(dot(d,d));if(len<1e-15)return hit;d=d*(1/len);int stack[128],size=0;stack[size++]=0;
 while(size){const auto&n=m.nodes[stack[--size]];if(!box(n.lo,n.hi,o,d,std::min(maximum,hit.t+1e-6),r+1e-6))continue;
  if(n.left>=0){stack[size++]=n.right;stack[size++]=n.left;}
  else for(int j=n.begin;j<n.end;j++)sphere_tri(m.tri[m.order[j]],m.order[j],o,d,r,maximum,hit);
 }return hit;
}
static bool clear(const Mesh&m,V a,V b,double epsilon){
 V d=b-a;double len=std::sqrt(dot(d,d));if(len<epsilon||!m.node_count)return true;double threshold=epsilon/std::max(len,1e-30);int stack[128],size=0;stack[size++]=0;
 while(size){const auto&n=m.nodes[stack[--size]];if(!box(n.lo,n.hi,a,d,1,epsilon))continue;
  if(n.left>=0){stack[size++]=n.right;stack[size++]=n.left;continue;}
  for(int j=n.begin;j<n.end;j++){const auto&t=m.tri[m.order[j]];V e1=t.b-t.a,e2=t.c-t.a,p=cross(d,e2);double det=dot(e1,p);if(std::abs(det)<=1e-10)continue;double inv=1/det;V q0=a-t.a;double u=dot(q0,p)*inv;if(u< -1e-8||u>1+1e-8)continue;V q=cross(q0,e1);double v=dot(d,q)*inv;if(v< -1e-8||u+v>1+1e-8)continue;double along=dot(e2,q)*inv;if(along>threshold&&along<1-threshold)return false;}
 }return true;
}
extern "C" {
int d4_tri_bytes(){return sizeof(Tri);} int d4_node_bytes(){return sizeof(Node);}
void d4_init(int which,double*points,int count,Tri*tri,Node*nodes,int node_count,int*order){
 for(int i=0;i<count;i++){V a{points[9*i],points[9*i+1],points[9*i+2]},b{points[9*i+3],points[9*i+4],points[9*i+5]},c{points[9*i+6],points[9*i+7],points[9*i+8]};V n=cross(b-a,c-a);double len=std::sqrt(dot(n,n));tri[i]={a,b,c,n*(1/std::max(len,1e-15)),low(a,low(b,c)),high(a,high(b,c)),len};}
 meshes[which]={tri,order,nodes,node_count};
}
double*d4_result(){return output;}
int d4_clear(int which,double ax,double ay,double az,double bx,double by,double bz,double epsilon){return clear(meshes[which],{ax,ay,az},{bx,by,bz},epsilon);}
int d4_sphere(int which,double ax,double ay,double az,double dx,double dy,double dz,double radius,double length){auto h=sphere(meshes[which],{ax,ay,az},{dx,dy,dz},radius,length);output[0]=h.t;output[1]=h.point.x;output[2]=h.point.y;output[3]=h.point.z;output[4]=h.index;return h.index;}
}
