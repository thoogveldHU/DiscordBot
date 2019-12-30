import discord
import asyncio
from discord.ext.commands import Bot, has_any_role
from discord.utils import get
import openpyxl
import os
from PIL import Image, ImageDraw, ImageFont
import textwrap

#prefix
Client = Bot('!')

#command clear
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
async def clear(ctx, number):
    number = int(number)
    counter = 0
    async for message in ctx.channel.history(limit=number):
        if counter < number:
            await message.delete()
            counter += 1

#command iam
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984, 627893819979071509)
async def iam(ctx):
    listOfWords = str(ctx.message.content.lower()).split(" ")
    allowedList = ["streamer"]
    if str(listOfWords[1]) in allowedList:
        member = ctx.message.author
        server = ctx.message.author.guild
        for role in server.roles:
            if role.name.lower() == listOfWords[1]:
                await member.add_roles(role)
                emoji = '\U0001f44d'
                return await ctx.message.add_reaction(emoji)
    emoji = '\U0001F44E'
    return await ctx.message.add_reaction(emoji)

#command warn      
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
async def warn(ctx):

    #Getting the user from the message
    listOfWords = ctx.message.content.split(" ")
    member = listOfWords[1][3:-1]
    user = Client.get_user(int(member))

    #Gettings Reason from the message
    warnReason = "No reason given."
    try:
        reasonString = ""
        for word in listOfWords[2:]:
            reasonString += word
            warnReason = reasonString
    except IndexError:
        warnReason = "No reason given."
    #opening the warning file
    wb = openpyxl.load_workbook('warnings.xlsx')
    ws = wb.active
    #Checking if user is already there.
    for row in ws:
        #Found the ID on A[x]
        if str(row[0].value) == str(user.id):
            #For items in user
            for item in row:
                if type(item.value) == type(None):
                    cell = (str(item)[-3:-1])
                    ws[cell] = warnReason
                    wb.save('warnings.xlsx')
                    return await ctx.send(user.name + " has been warned..")
            #there is no none, so we just add a cell after the items.
            cellStr = str(item)[-3:-1]
            cellOrd = chr(ord(cellStr[0]) + 1)
            newCellStr = str(cellOrd) + str(cellStr[1:])
            ws[newCellStr] = warnReason
            wb.save('warnings.xlsx')
            return await ctx.send(user.name + " has been warned..")
    username = user.name + "#" + user.discriminator
    ws.append([str(user.id),str(username),str(warnReason)])
    wb.save('warnings.xlsx')
    return await ctx.send(user.name + " has been warned..")

#command warnlog
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
async def warnlog(ctx):
    #Getting the user from the message
    listOfWords = ctx.message.content.split(" ")
    member = listOfWords[1][3:-1]
    user = Client.get_user(int(member))

    #opening the warning file
    wb = openpyxl.load_workbook('warnings.xlsx')
    ws = wb.active
    #Checking if user is already there.
    for row in ws:
        #Found the ID on A[x]
        if str(row[0].value) == str(user.id):
            #For items in user
            warns = []
            for item in row[2:]:
                warns.append(item.value)
            print(warns)

#command ban
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
async def ban(ctx):
    listOfWords = ctx.message.content.split(" ")
    member = listOfWords[1][3:-1]
    user = Client.get_user(int(member))
    await ctx.guild.ban(user)
    await ctx.channel.send(file=discord.File('ban.jpg'))

#on member join, putting in an image and a text line.
@Client.event
async def on_member_join(member):
    print('working')
    makeWelcomeBanner(member.name)
    print('made banner')
    guild = member.guild
    if guild.system_channel is not None:
        print('default channel is ready')
        await guild.system_channel.send(file=discord.File('welcome_banner_ready.png'))
        print('send image')
        to_send = 'Welkom {0.mention} bij {1.name}! Doe een !welkom om de rest van de kanalen te kunnen zien!'.format(member,guild)
        print(to_send)
        return await guild.system_channel.send(to_send)

#welkom
@Client.command(pass_context=True)
async def welkom(ctx):
    member = ctx.message.author
    genie = get(member.guild.roles, id=627893819979071509)
    await member.add_roles(genie)
    emoji = '\U0001f44d'
    return await ctx.message.add_reaction(emoji) 

#welcome
@Client.command(pass_context=True)
async def welcome(ctx):
    member = ctx.message.author
    genie = get(member.guild.roles, id=627893819979071509)
    await member.add_roles(genie)
    emoji = '\U0001f44d'
    return await ctx.message.add_reaction(emoji)

#read token from file
def getToken(fileName,command):
    configFile = open(fileName,"r")
    lineList = configFile.readlines()
    for line in lineList:
        if not line.startswith('#'):
            split = line.split("=")
            if split[0] == command:
                return split[1]
    return "Command: " + command + " not found." 

#test only.
@Client.command(pass_context=True)
async def welcomeMessageTest(ctx):
    makeWelcomeBanner(ctx)
    guild = ctx.author.guild
    await ctx.channel.send(file=discord.File('welcome_banner_ready.png'))
    to_send = " 'Welkom thuis {0.mention} - CaptainManCave'. Wat leuk dat je er bent, doe een !welkom in de chat om een Genie te worden en alle kanalen te bekijken!".format(ctx.author)
    return await ctx.channel.send(to_send)

#make welcome image
def makeWelcomeBanner(name):
    astr = '''Welkom bij Kwaad Genie \n''' + name + "!"
    para = textwrap.wrap(astr, width=30)
    im = Image.open('banner.png')
    MAX_W, MAX_H = im.size[0], im.size[1]

    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype('segoe-ui-bold.ttf', 28)

    #Front text
    current_h, pad = 75, 10
    for line in para:
        w, h = draw.textsize(line, font=font)
        if not line == para[-1]:
            draw.text(((MAX_W - w) / 4, current_h), line,
                      font=font, fill=(255, 255, 255, 255))
        else:
            draw.text(((MAX_W - w) / 3, current_h), line,
                      font=font, fill=(200, 200, 200, 255))
        current_h += h + pad

    im.save('welcome_banner_ready.png')

#run bot
token = getToken("config.txt", "TOKEN")
Client.run(token)

"""""""""
TO-DO:
    3.make bot send warnlog
    4.streamer role -> live. https://discordpy.readthedocs.io/en/latest/api.html#discord.Streaming

"""""""""
