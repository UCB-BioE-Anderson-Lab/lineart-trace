"""Regenerate tests/fixtures/stress.png — a precision pattern of the cases
that break centreline tracing. Each specimen is deliberately isolated so a
failure can be attributed."""
import math, os
import cv2, numpy as np

W, H, S, B = 2200, 1500, 10, 0
img = np.full((H, W), 255, np.uint8)
ln = lambda p, q, s=S: cv2.line(img, tuple(map(int, p)), tuple(map(int, q)), B, s, cv2.LINE_AA)
poly = lambda pts, s=S, c=False: cv2.polylines(img, [np.array(pts, np.int32)], c, B, s, cv2.LINE_AA)
ell = lambda c, r, s=S, a0=0, a1=360: cv2.ellipse(img, tuple(map(int, c)), tuple(map(int, r)), 0, a0, a1, B, s, cv2.LINE_AA)

ln((80,120),(320,120));  ln((200,20),(200,220))                  # 1 perpendicular cross
ln((420,180),(700,180)); ln((420,215),(700,145))                 # 2 acute (~15 deg) cross
ln((800,40),(800,220));  ln((800,130),(1020,130))                # 3 T junction
poly([(1120,220),(1120,60),(1280,60)])                           # 4 right-angle corner
poly([(1340,220),(1400,60),(1460,220)])                          # 5 cusp
ell((1600,130),(80,80))                                          # 6 lone loop, no node
poly([(1760,210),(1830,60),(1930,210),(2030,60),(2120,150)])     # 7 zigzag
for i,g in enumerate((10,20,40)):                                # 8 parallels at 1x/2x/4x
    y = 340+i*90; ln((80,y),(420,y)); ln((80,y+g),(420,y+g))
for i,s in enumerate((4,10,20)): ln((520,340+i*90),(860,340+i*90), s)   # 9 mixed weights
cv2.fillPoly(img,[np.array([(960,340),(1120,420),(960,500)],np.int32)],B) # 10 FILLED
poly([(1200,340),(1360,420),(1200,500)],S,True)                  # 11 outlined triangle
for i in range(8): ln((1450+i*40,380),(1470+i*40,380))           # 12 dashes
for i in range(6): cv2.circle(img,(1460+i*45,470),5,B,-1)        # 13 dots
pts=[(1900+(8+t*7)*math.cos(t), 430+(8+t*7)*math.sin(t)) for t in np.linspace(0,6*math.pi,400)]
poly(pts)                                                        # 14 tight spiral
for i in range(10): ln((80+i*30,700),(80+i*30+120,880))          # 15 dense hatching
for i in range(10): ln((80+i*30,880),(80+i*30+120,700))
for i in range(60): ln((560+i*6,790),(566+i*6,790), max(2,int(2+i*0.3)))  # 16 taper
for r in (40,58,78): ell((1120,800),(r,r))                       # 17 concentric
ell((1420,760),(70,70)); ln((1280,830),(1560,830))               # 18 tangency
poly([(1680+i*8, 800+90*math.sin(i/9.0)*math.exp(-i/90.0)) for i in range(64)])  # 19 damped wave
for i in range(6): ell((300,1180),(40+i*22,55+i*26),S,-60,150)   # 20 nested ridges
poly([(700,1150),(730,1100),(760,1180),(790,1100),(820,1180),(850,1110)])       # 21 squiggle
ell((1500,1500),(700,420),S,190,350)                             # 22 long gentle arc

out = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "stress.png")
cv2.imwrite(os.path.normpath(out), img)
print("wrote", os.path.normpath(out))
