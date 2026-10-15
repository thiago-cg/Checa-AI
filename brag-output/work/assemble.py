import os
W=os.path.dirname(os.path.abspath(__file__))
parts=[open(os.path.join(W,p),encoding='utf-8').read() for p in ('p1.html','p2.html','p3.html')]
open(os.path.join(W,'index.html'),'w',encoding='utf-8').write(''.join(parts))
