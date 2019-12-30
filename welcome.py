def getWelcomeImage(member):

    astr = '''Welkom bij Kwaad Genie! \n''' + member.name
    para = textwrap.wrap(astr, width=20)
    im = Image.open('test.jpeg')
    MAX_W, MAX_H = im.size[0], im.size[1]

    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype('segoe-ui-bold.ttf', 24)

    #Left
    current_h, pad = 50, 10
    for line in para:
        w, h = draw.textsize(line, font=font)
        if not line == para[-1]:
            draw.text(((MAX_W - w) / 2, current_h - 1), line, font=font,fill=(255,255,255,255))
        else:
            draw.text(((MAX_W - w) / 2, current_h - 1), line, font=font,fill=(0,0,0,255))
        current_h += h + pad

    #right
    current_h, pad = 50, 10
    for line in para:
        w, h = draw.textsize(line, font=font)
        if not line == para[-1]:
            draw.text(((MAX_W - w) / 2, current_h + 1), line, font=font,fill=(255,255,255,255))
        else:
            draw.text(((MAX_W - w) / 2, current_h + 1), line, font=font,fill=(0,0,0,255))
        current_h += h + pad

    #above
    current_h, pad = 50, 10
    for line in para:
        w, h = draw.textsize(line, font=font)
        if not line == para[-1]:
            draw.text(((MAX_W - w) / 2 -1 , current_h), line, font=font,fill=(255,255,255,255))
        else:
            draw.text(((MAX_W - w) / 2 -1, current_h), line, font=font,fill=(0,0,0,255))
        current_h += h + pad

    #under
    current_h, pad = 50, 10
    for line in para:
        w, h = draw.textsize(line, font=font)
        if not line == para[-1]:
            draw.text(((MAX_W - w) / 2 + 1, current_h), line, font=font,fill=(255,255,255,255))
        else:
            draw.text(((MAX_W - w) / 2 + 1, current_h), line, font=font,fill=(0,0,0,255))
        current_h += h + pad

    #Front text
    current_h, pad = 50, 10
    for line in para:
        w, h = draw.textsize(line, font=font)
        if not line == para[-1]:
            draw.text(((MAX_W - w) / 2, current_h), line, font=font,fill=(0,0,0,255))
        else:
            draw.text(((MAX_W - w) / 2, current_h), line, font=font,fill=(255,255,255,255))
        current_h += h + pad

    im.save('test.png')