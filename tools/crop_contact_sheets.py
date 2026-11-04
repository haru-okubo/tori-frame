import sys, glob, os
from birdframe.config import load_config, build_renderer
from PIL import Image, ImageDraw
r=build_renderer(load_config()); c=r.catalog
arts=sorted({a.artwork_id:a for l in c.by_wamei.values() for a in l}.values(), key=lambda a:(a.wamei,a.artwork_id))
for f in glob.glob("/workspace/shots/rw_*.png"): os.remove(f)
per=5; CW=196
for si in range(0,len(arts),per):
    chunk=arts[si:si+per]
    sheet=Image.new("RGB",((CW+4)*per,300+327+162+120+60),"gray"); d=ImageDraw.Draw(sheet)
    for i,a in enumerate(chunk):
        img=c.load(a); W,H=img.size; x=i*(CW+4)
        d.text((x+2,1),f"{si+i} {a.wamei} {a.artwork_id[-24:]}",fill="white")
        o=img.copy(); dd=ImageDraw.Draw(o); lw=max(4,W//150)
        if a.box: dd.rectangle([a.box[0]*W,a.box[1]*H,a.box[2]*W,a.box[3]*H],outline=(255,0,0),width=lw)
        if a.clip: dd.rectangle([a.clip[0]*W,a.clip[1]*H,a.clip[2]*W,a.clip[3]*H],outline=(0,0,255),width=lw)
        o.thumbnail((CW,300)); sheet.paste(o,(x,14)); y=318
        for w,h in ((480,800),(480,397),(480,262)):
            t=r._cover_tile(img,a,w/h).resize((CW,int(CW*h/w))); sheet.paste(t,(x,y)); y+=t.height+4
    sheet.save(f"/workspace/shots/rw_{si//per:02d}.png")
print(len(arts))
for i,a in enumerate(arts): print(i,a.wamei,a.artwork_id)
