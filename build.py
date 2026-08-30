from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import math, os, urllib.request

# La foto sorgente non e' ridistribuibile: viene scaricata al primo uso.
SORGENTE="dune-src.jpeg"
URL=("https://raw.githubusercontent.com/vinceliuice/Elegant-grub2-themes/"
     "main/backgrounds/background-mojave.jpeg")
if not os.path.exists(SORGENTE):
    print(f"  scarico {SORGENTE} ...")
    urllib.request.urlretrieve(URL, SORGENTE)
W,H=3840,2160; XSP,YSP=8,16; SS=4
# big_icon_size scelto come il MINIMO che porta la fila strumenti sotto le etichette
BIG=549;  TILE =(BIG*9)//8                # 617
SMALL=48; TILE1=(SMALL*4)//3              # 64
NTOOLS=5
R0X=(W+XSP-(TILE +XSP)*2)//2              # 1327
R0Y=(H//2)-TILE//2                        # 786
R1Y=R0Y+TILE+YSP                          # 1391
R1X=(W+XSP-(TILE1+XSP)*NTOOLS)//2         # 1744
TXTY=R1Y+TILE1+YSP                        # 1471
POS=[R0X,R0X+TILE+XSP]; CEN=[p+TILE//2 for p in POS]
OFF=(TILE-BIG)//2; OFF1=(TILE1-SMALL)//2
PLATE=340; LOGO_VIS=218; F_OS=66; LBL_Y=1290   # y di disegno: l'inchiostro parte a 1302
BOX=BIG*2; LOGO_BOX=LOGO_VIS*2            # disegno a 2x, rEFInd riduce
MAXV=W//(TILE+XSP)-1
print(f"  TILE={TILE}  MaxVisible={MAXV} (serve >=2)")
print(f"  centri lastre={CEN}  lastra y=910..1250  etichette y={LBL_Y}..{LBL_Y+70}")
print(f"  strumenti y={R1Y}..{R1Y+TILE1}  textPosY={TXTY}")
_f=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",F_OS)
_d=ImageDraw.Draw(Image.new("RGB",(10,10)))
_bb=[_d.textbbox((0,0),t,font=_f) for t in ("Windows","Ubuntu")]
INK_T=LBL_Y+min(b[1] for b in _bb); INK_B=LBL_Y+max(b[3] for b in _bb)
SOPRA=INK_T-(H//2+PLATE//2); SOTTO=R1Y-INK_B
print(f"  spazio lastra->scritta = {SOPRA}   scritta->strumenti = {SOTTO}")
assert SOTTO>0, "gli strumenti coprirebbero le scritte"
assert abs(SOPRA-SOTTO)<=2, f"spaziature diverse: {SOPRA} vs {SOTTO}"
print("  OK: spaziature uguali, strumenti sotto le scritte")

def aa(n,fn):
    im=Image.new("RGBA",(n*SS,n*SS),(0,0,0,0)); fn(ImageDraw.Draw(im),n*SS)
    return im.resize((n,n),Image.LANCZOS)
def win(d,S):
    h=S*0.94; g=S*0.046; s=(h-g)/2; r=s*0.11; C=S/2
    for gx in(0,1):
        for gy in(0,1):
            x=C-h/2+gx*(s+g); y=C-h/2+gy*(s+g)
            d.rounded_rectangle([x,y,x+s,y+s],radius=r,fill=(96,190,245,255))
def ubu(d,S):
    C=S/2; R=S*0.372; T=int(S*0.093); DOT=S*0.105
    for a in(-90,30,150): d.arc([C-R,C-R,C+R,C+R],a+26,a+94,fill=(245,130,80,255),width=T)
    for a in(-90,30,150):
        x,y=C+R*math.cos(math.radians(a)),C+R*math.sin(math.radians(a))
        d.ellipse([x-DOT,y-DOT,x+DOT,y+DOT],fill=(245,130,80,255))
for fn,n in ((win,"icon_windows.png"),(ubu,"icon_ubuntu.png")):
    t=Image.new("RGBA",(BOX,BOX),(0,0,0,0))
    t.alpha_composite(aa(LOGO_BOX,fn),((BOX-LOGO_BOX)//2,)*2); t.save(n)

GR=(232,238,250,255)
def i_about(d,S):
    m=S*0.09; d.ellipse([m,m,S-m,S-m],outline=GR,width=int(S*0.075))
    d.ellipse([S*0.44,S*0.24,S*0.56,S*0.36],fill=GR)
    d.rounded_rectangle([S*0.44,S*0.43,S*0.56,S*0.76],radius=S*0.06,fill=GR)
def i_tag(d,S):
    d.polygon([(S*0.14,S*0.50),(S*0.50,S*0.12),(S*0.88,S*0.12),(S*0.88,S*0.50),
               (S*0.52,S*0.88),(S*0.14,S*0.50)],outline=GR,width=int(S*0.075))
    d.ellipse([S*0.68,S*0.22,S*0.80,S*0.34],fill=GR)
def i_power(d,S):
    m=S*0.16; d.arc([m,m,S-m,S-m],-55,235,fill=GR,width=int(S*0.085))
    d.rounded_rectangle([S*0.455,S*0.10,S*0.545,S*0.46],radius=S*0.045,fill=GR)
def i_reset(d,S):
    m=S*0.16; d.arc([m,m,S-m,S-m],120,60,fill=GR,width=int(S*0.085))
    d.polygon([(S*0.80,S*0.10),(S*0.90,S*0.42),(S*0.58,S*0.34)],fill=GR)
def i_chip(d,S):
    a,b=S*0.26,S*0.74
    d.rounded_rectangle([a,a,b,b],radius=S*0.07,outline=GR,width=int(S*0.07))
    d.rounded_rectangle([S*0.42,S*0.42,S*0.58,S*0.58],radius=S*0.03,fill=GR)
    for t in (0.38,0.5,0.62):
        d.rectangle([S*t-S*0.022,S*0.10,S*t+S*0.022,a],fill=GR)
        d.rectangle([S*t-S*0.022,b,S*t+S*0.022,S*0.90],fill=GR)
        d.rectangle([S*0.10,S*t-S*0.022,a,S*t+S*0.022],fill=GR)
        d.rectangle([b,S*t-S*0.022,S*0.90,S*t+S*0.022],fill=GR)
TOOLS=[(i_about,"func_about.png"),(i_tag,"func_hidden.png"),(i_power,"func_shutdown.png"),
       (i_reset,"func_reset.png"),(i_chip,"func_firmware.png")]
for fn,n in TOOLS: aa(192,fn).save(n)

bg=Image.open("dune-src.jpeg").convert("RGB").resize((W,H),Image.LANCZOS)
bg=ImageEnhance.Brightness(bg).enhance(0.76)
def glass(img,cx,cy,s):
    x,y=cx-s//2,cy-s//2
    sh=Image.new("L",(W,H),0)
    ImageDraw.Draw(sh).rounded_rectangle([x+6,y+14,x+s+6,y+s+14],radius=int(s*0.19),fill=90)
    img.paste(Image.new("RGB",(W,H),(4,6,14)),(0,0),sh.filter(ImageFilter.GaussianBlur(26)))
    p=img.crop((x,y,x+s,y+s)).filter(ImageFilter.GaussianBlur(34))
    p=ImageEnhance.Brightness(p).enhance(1.34)
    p=Image.blend(p,Image.new("RGB",(s,s),(226,233,250)),0.19)
    gr=Image.new("L",(1,s)); gr.putdata([int(52*(1-i/s)) for i in range(s)])
    p=Image.composite(Image.new("RGB",(s,s),(255,)*3),p,gr.resize((s,s)))
    m=Image.new("L",(s*SS,s*SS),0)
    ImageDraw.Draw(m).rounded_rectangle([0,0,s*SS-1,s*SS-1],radius=int(s*SS*0.19),fill=255)
    img.paste(p,(x,y),m.resize((s,s),Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.6)))
    rm=Image.new("RGBA",(s*SS,s*SS),(0,0,0,0))
    ImageDraw.Draw(rm).rounded_rectangle([3,3,s*SS-4,s*SS-4],radius=int(s*SS*0.19),
                                         outline=(255,255,255,150),width=5*SS)
    rm=rm.resize((s,s),Image.LANCZOS)
    fade=Image.new("L",(1,s)); fade.putdata([int(255*(1-0.72*i/s)) for i in range(s)])
    img.paste(Image.new("RGB",(s,s),(255,)*3),(x,y),
              Image.composite(rm.split()[3],Image.new("L",(s,s),0),fade.resize((s,s))))
for c in CEN: glass(bg,c,H//2,PLATE)
d=ImageDraw.Draw(bg)
FB=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",F_OS)
for cx,t in zip(CEN,("Windows","Ubuntu")):
    bb=d.textbbox((0,0),t,font=FB); d.text((cx-(bb[2]-bb[0])//2,LBL_Y),t,font=FB,fill=(255,255,255))
bg.save("background.png","PNG",optimize=True)

INS=(TILE-PLATE)//2
sel=Image.new("RGBA",(TILE*SS,TILE*SS),(0,0,0,0)); sd=ImageDraw.Draw(sel)
sd.rounded_rectangle([INS*SS,INS*SS,(TILE-INS)*SS,(TILE-INS)*SS],radius=int(PLATE*SS*0.19),fill=(255,255,255,34))
sd.rounded_rectangle([INS*SS,INS*SS,(TILE-INS)*SS,(TILE-INS)*SS],radius=int(PLATE*SS*0.19),outline=(255,255,255,215),width=5*SS)
sel.resize((TILE,TILE),Image.LANCZOS).save("selection_big.png")
ss=Image.new("RGBA",(TILE1*SS,TILE1*SS),(0,0,0,0)); s2=ImageDraw.Draw(ss)
s2.rounded_rectangle([2,2,TILE1*SS-3,TILE1*SS-3],radius=int(TILE1*SS*0.24),fill=(255,255,255,40))
s2.rounded_rectangle([2,2,TILE1*SS-3,TILE1*SS-3],radius=int(TILE1*SS*0.24),outline=(255,255,255,190),width=3*SS)
ss.resize((TILE1,TILE1),Image.LANCZOS).save("selection_small.png")

c=bg.convert("RGBA")
c.alpha_composite(Image.open("selection_big.png").convert("RGBA"),(POS[0],R0Y))
for x,n in zip(POS,("icon_windows.png","icon_ubuntu.png")):
    c.alpha_composite(Image.open(n).convert("RGBA").resize((BIG,BIG),Image.LANCZOS),(x+OFF,R0Y+OFF))
for i,(_,n) in enumerate(TOOLS):
    c.alpha_composite(Image.open(n).convert("RGBA").resize((SMALL,SMALL),Image.LANCZOS),
                      (R1X+i*(TILE1+XSP)+OFF1,R1Y+OFF1))
c.convert("RGB").save("mockup.png")
c.resize((1280,720),Image.LANCZOS).convert("RGB").save("mock_small.png")
print("  mockup pronto")
