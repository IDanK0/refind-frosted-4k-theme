#!/usr/bin/env python3
"""Tell a photograph that is really 4K from one that merely has 4K pixels.

Some of the library had four thousand pixels across and about thirteen hundred
of picture, and the difference does not show in a thumbnail. Three numbers do
show it:

  noise      Immerkaer's estimator. The kernel's response is zero for anything
             smooth, so what survives it is noise and nothing else.
  chroma     the same, on the two colour-difference planes. Colour noise is far
             more objectionable than the grey kind and a luminance measure walks
             straight past it -- which it did, until a crop at 1:1 said otherwise.
  mottling   average to 8x8, subtract the large-scale trend, and measure what is
             left. A sky's gradient disappears; blotching does not. Without the
             subtraction this measures the picture rather than its faults, and
             says a clean gradient is the worst thing it has ever seen.
  sharpness  where the radially averaged power spectrum meets the noise floor,
             as a fraction of what 3840 pixels could carry. A real photograph
             lands near 75%; an upscale lands far below it.

Everything is measured on the picture as it will be used -- cropped to 16:9 and
resampled to 3840x2160 -- because that is where the noise ends up, not where it
started.

    ./check-photos.py 'library/*.jpg'
    ./check-photos.py '~/Pictures/*.jpg'
"""
import glob, os, sys, math, json
try:
    import numpy as np
except ModuleNotFoundError:
    raise SystemExit("this one needs numpy:\n"
                     "  Debian/Ubuntu  sudo apt install python3-numpy\n"
                     "  Fedora         sudo dnf install python3-numpy\n"
                     "  Arch           sudo pacman -S python-numpy\n"
                     "  or             pip install numpy")
from PIL import Image

W, H = 3840, 2160
def fit(path):
    im = Image.open(path).convert("RGB"); w,h = im.size
    if w/h > W/H:
        nw = int(h*W/H); im = im.crop(((w-nw)//2,0,(w-nw)//2+nw,h))
    else:
        nh = int(w*H/W); im = im.crop((0,(h-nh)//2,w,(h-nh)//2+nh))
    return im.resize((W,H), Image.LANCZOS)

def planes(im, crop=2048):
    w,h = im.size; c = min(crop,w,h)
    a = np.asarray(im.crop(((w-c)//2,(h-c)//2,(w-c)//2+c,(h-c)//2+c)), dtype=np.float64)
    r,g,b = a[...,0],a[...,1],a[...,2]
    return .299*r+.587*g+.114*b, r-g, b-g

def immerkaer(a):
    rr = (a[:-2,:-2] -2*a[:-2,1:-1] + a[:-2,2:]
        -2*a[1:-1,:-2] +4*a[1:-1,1:-1] -2*a[1:-1,2:]
        + a[2:,:-2]  -2*a[2:,1:-1]  + a[2:,2:])
    return math.sqrt(math.pi/2)*np.abs(rr).sum()/(6.0*rr.size)

def pool(a,k):
    n=(a.shape[0]//k)*k; m=(a.shape[1]//k)*k
    return a[:n,:m].reshape(n//k,k,m//k,k).mean(axis=(1,3))

def mottle(c):
    t = pool(c,8)
    tr = np.repeat(np.repeat(pool(t,4),4,axis=0),4,axis=1)
    n=min(t.shape[0],tr.shape[0]); m=min(t.shape[1],tr.shape[1])
    return (t[:n,:m]-tr[:n,:m]).std()

def sharpness(im):
    """Where the real detail stops, as a fraction of what 3840 could hold."""
    a = np.asarray(im.convert("L").crop((896,56,2944,2104)), dtype=np.float64)
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    F = np.fft.fftshift(np.abs(np.fft.fft2((a-a.mean())*win))**2)
    n=a.shape[0]; c=n//2
    y,x = np.ogrid[:n,:n]; r = np.hypot(x-c,y-c).astype(int)
    p = (np.bincount(r.ravel(), F.ravel())/np.maximum(np.bincount(r.ravel()),1))[:c]
    floor = np.median(p[int(c*.85):])
    above = np.where(p > floor*3)[0]
    return (above[-1]/c) if len(above) else 0.0

if len(sys.argv) < 2:
    sys.exit("usage: ./check-photos.py 'library/*.jpg' [out.json]\n"
             "The pattern is quoted so this program expands it, not the shell.")

rows=[]
# expanduser, because the pattern is quoted to keep the shell off it -- and a
# quoted ~ is a directory called "~", which matches nothing and measures nothing.
for f in sorted(glob.glob(os.path.expanduser(sys.argv[1]))):
    # a contact sheet of the library is not a member of it
    if os.path.basename(f) == "preview-sheet.jpg":
        continue
    im = fit(f)
    Y,c1,c2 = planes(im)
    rows.append(dict(file=f, lum=immerkaer(Y), chroma=(immerkaer(c1)+immerkaer(c2))/2,
                     mottle=(mottle(c1)+mottle(c2))/2, sharp=sharpness(im),
                     bright=Y.mean()))
rows.sort(key=lambda r: r["mottle"]*2 + r["lum"])
print(f"  {'file':38s} {'noise':>7s} {'chroma':>7s} {'mottling':>9s} {'sharpness':>10s} {'light':>6s}")
for r in rows:
    flag = "  <- noisy" if (r['lum'] > 3 or r['mottle'] > 5.5 or r['chroma'] > 1.2) else ""
    print(f"  {os.path.basename(r['file'])[:38]:38s} {r['lum']:7.2f} {r['chroma']:7.2f} "
          f"{r['mottle']:9.2f} {r['sharp']*100:9.0f}% {r['bright']:6.0f}{flag}")
json.dump(rows, open(sys.argv[2],"w")) if len(sys.argv)>2 else None
