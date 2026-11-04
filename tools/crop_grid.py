import sys
from birdframe.config import load_config, build_renderer
from PIL import Image, ImageDraw
c=build_renderer(load_config()).catalog
out=sys.argv[1]; ids=sys.argv[2:]
allarts={a.artwork_id:a for l in c.by_wamei.values() for a in l}
ims=[]
for n in ids:
    a=allarts[n]; im=c.load(a).copy(); W,H=im.size
    im.thumbnail((470,640)); w,h=im.size; d=ImageDraw.Draw(im)
    for k in range(1,10):
        x=k*w/10; y=k*h/10
        d.line([x,0,x,h],fill=(0,160,255) if k!=5 else (0,80,255),width=1); d.line([0,y,w,y],fill=(0,160,255) if k!=5 else (0,80,255),width=1)
        d.text((x+1,1),str(k),fill=(255,0,255)); d.text((1,y+1),str(k),fill=(255,0,255))
    if a.box: d.rectangle([a.box[0]*w,a.box[1]*h,a.box[2]*w,a.box[3]*h],outline=(255,0,0),width=2)
    d.text((3,h-12),n[-24:],fill=(255,0,0)); ims.append(im)
sheet=Image.new("RGB",(sum(i.width+6 for i in ims),max(i.height for i in ims)),"gray"); x=0
for i in ims: sheet.paste(i,(x,0)); x+=i.width+6
sheet.save(out)
