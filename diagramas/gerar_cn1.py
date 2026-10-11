"""CN1 T3D: desenho de engenharia a partir do manual V2.3, PDF 6.
Numeração frontal macho; desenho esquemático, sem escala mecânica.
"""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 2200, 2520
im = Image.new('RGB', (W,H), 'white')
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="white"/>']
regular='/usr/share/fonts/google-noto/NotoSans-Regular.ttf'
bold='/usr/share/fonts/google-noto/NotoSans-Bold.ttf'

def text(x,y,s,size=28,color='#24364b',weight=False,anchor='start'):
    font=ImageFont.truetype(bold if weight else regular,size)
    width=d.textlength(s,font=font)
    px=x-width if anchor=='end' else x-width/2 if anchor=='middle' else x
    d.text((px,y),s,font=font,fill=color)
    svg.append(f'<text x="{x}" y="{y}" dominant-baseline="text-before-edge" text-anchor="{anchor}" font-family="Noto Sans,sans-serif" font-size="{size}" font-weight="{700 if weight else 400}" fill="{color}">{escape(s)}</text>')

def line(points,color='#74879b',width=3):
    d.line(points,fill=color,width=width)
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"/>')

def circle(x,y,r,color,stroke=None,width=2):
    d.ellipse((x-r,y-r,x+r,y+r),fill=color,outline=stroke,width=width)
    svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" stroke="{stroke or color}" stroke-width="{width}"/>')

def polygon(points,color,stroke,width=3):
    d.polygon(points,fill=color)
    d.line(points+[points[0]],fill=stroke,width=width)
    svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in points)}" fill="{color}" stroke="{stroke}" stroke-width="{width}"/>')

signals={
 1:'DI2 / ACLR — limpar alarme*',
 2:'DI4 / CWL — permissão de giro horário*',
 5:'DO2 / ALM — saída de estado de alarme*',
 6:'DO4 / BRK — liberação do freio*',
 8:'SIGN− — entrada de direção, negativo',
 9:'PULS− — entrada de pulsos, negativo',
 10:'AS− — entrada analógica, negativo',
 11:'GNDA — terra de referência analógica',
 12:'GND — terra dos sinais de encoder',
 13:'OA+ — saída de encoder A+',
 14:'OB+ — saída de encoder B+',
 15:'OZ+ — saída de encoder Z+ (índice)',
 16:'DI1 / SON — habilitação do servo*',
 17:'DI3 / CCWL — permissão de giro anti-horário*',
 20:'DO1 / RDY — servo pronto*',
 21:'DO3 / COIN — posição concluída*',
 23:'DO COM — comum das saídas digitais',
 24:'SIGN+ (5 V) — entrada de direção, positivo',
 25:'PULS+ (5 V) — entrada de pulsos, positivo',
 26:'AS+ — entrada analógica, positivo',
 27:'CZ — saída de índice Z',
 28:'OA− — saída de encoder A−',
 29:'OB− — saída de encoder B−',
 30:'OZ− — saída de encoder Z− (índice)',
 31:'COM+ — alimentação das entradas DI (24 V)',
 38:'SIGN+ (24 V) — entrada de direção, positivo',
 39:'PULS+ (24 V) — entrada de pulsos, positivo',
 40:'485_A — comunicação RS-485 A',
 41:'485_B — comunicação RS-485 B',
 42:'485_GND — terra de sinal RS-485',
}
analog={10,11,26}
text(65,40,'CN1 • T3D • conector de 44 pinos (DB44 / HD44)',48,weight=True)
text(65,110,'Vista frontal do plugue MACHO do cabo: pinos voltados para você.',32)
text(65,165,'Entrada analógica em destaque: 26 = AS+   •   10 = AS−   •   11 = GNDA',31,'#bd4f00',True)
text(65,235,'Como segurar para ler o desenho abaixo:',29,weight=True)
text(65,280,'Gire 90° no sentido horário; o lado mais largo fica à direita.',28)
text(65,322,'Pino 1 no alto à direita; pino 15 embaixo à direita.',28)

# Miniatura frontal na orientação horizontal habitual: macho, face de acoplamento.
polygon([(1510,230),(2090,230),(2050,355),(1550,355)],'#f3f6f9','#607185',2)
for row,(start,n,offset) in enumerate(((1,15,0),(16,15,-12),(31,14,-12))):
    for j in range(n):
        x=1540+j*35+offset;y=255+row*32
        circle(x,y,4,'#607185')
        if j in (0,n-1):text(x,y-16,str(start+j),13,weight=True,anchor='middle')
text(1800,372,'Antes de girar: lado largo em cima',20,anchor='middle')

# Mesmo conector girado 90° horário. Passos ampliados para os callouts.
polygon([(855,375),(1195,335),(1195,2155),(855,2115)],'#e9eef4','#526579',4)
circle(1030,355,15,'white','#526579',3)
circle(1030,2153,15,'white','#526579',3)
text(1045,2215,'Carcaça metálica — FG / blindagem',25,anchor='middle')
line([(1045,2212),(1045,2168)],'#526579',3)

# fileira superior → coluna direita; intermediária → central; inferior → esquerda
rows=((1,15,1115,480),(16,15,1025,435),(31,14,935,435))
seen=[]
for start,n,x,y0 in rows:
    for j in range(n):
        pin=start+j;y=y0+j*110
        known=pin in signals
        color='#bd4f00' if pin in analog else '#20517d' if known else '#76828d'
        label=f'{pin:02d} — {signals.get(pin,"Função não indicada no manual")}'
        if start==1:
            line([(x+19,y),(1270,y)],color,4 if pin in analog else 2)
            text(1290,y-19,label,27,color,pin in analog)
        else:
            # A coluna central sai entre os pinos da coluna esquerda.
            label_y = y + 45 if start == 16 else y
            points = [(x-19,y),(995,y),(970,label_y),(810,label_y)] if start == 16 else [(x-19,y),(810,y)]
            line(points,color,4 if pin in analog else 2)
            text(792,label_y-19,label,27,color,pin in analog,anchor='end')
        circle(x,y,20,'#fff1df' if pin in analog else 'white',color,3)
        text(x,y-15,str(pin),20,color,True,anchor='middle')
        seen.append(pin)
assert sorted(seen)==list(range(1,45))
text(65,2305,'* DI/DO são programáveis; os nomes indicam as funções do esquema do manual.',26)
text(65,2350,'“Não indicada” não significa pino livre: a fonte não atribui função a esse contato.',26)
text(65,2395,'Conferir os números moldados no plugue. A vista da fêmea e o lado de solda são espelhados.',26,weight=True)
text(65,2450,'Fonte: manual de comissionamento T3D V2.3, PDF 6 / página impressa 3. Esquemático, sem escala mecânica.',23)
svg.append('</svg>')
(ROOT/'CN1_T3D_frente_macho.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(ROOT/'CN1_T3D_frente_macho.png')
im.save(ROOT/'CN1_T3D_frente_macho.pdf',resolution=180)
print('Diagrama com 44 pinos gerado em PNG, SVG e PDF.')
