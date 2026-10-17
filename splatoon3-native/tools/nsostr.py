# nsostr.py <nso> <hexaddr>...: print the C string at module offsets
import sys
sys.argv = sys.argv[:2] + ['0'] + sys.argv[2:]; exec(open(__file__.replace('nsostr', 'nsodis')).read().split('a = int')[0])
for h in sys.argv[3:]:
    a = int(h, 16); print(h, bytes(img[a:img.index(0, a)]).decode('utf-8', 'replace'))
