import discord
import asyncio
from discord.ext.commands import Bot
from discord.utils import get
import openpyxl

#prefix
Client = Bot('?')

#command clear
@Client.command(pass_context=True)
async def clear(ctx, number):
    number = int(number)
    counter = 0
    async for message in ctx.channel.history(limit=number):
        if counter < number:
            await message.delete()
            counter += 1

#command iam
@Client.command(pass_context=True)
async def iam(ctx):
    listOfWords = str(ctx.message.content.lower()).split(" ")
    allowedList = ["streamer"]
    if str(listOfWords[1]) in allowedList:
        member = ctx.message.author
        server = ctx.message.author.guild
        for role in server.roles:
            if role.name.lower() == listOfWords[1]:
                return await member.add_roles(role)

#command warn      
@Client.command(pass_context=True)          
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
                    return
            #there is no none, so we just add a cell after the items.
            cellStr = str(item)[-3:-1]
            cellOrd = chr(ord(cellStr[0]) + 1)
            newCellStr = str(cellOrd) + str(cellStr[1:])
            ws[newCellStr] = warnReason
            wb.save('warnings.xlsx')
            return
    username = user.name + "#" + user.discriminator
    ws.append([str(user.id),str(username),str(warnReason)])
    wb.save('warnings.xlsx')
    return

@Client.command(pass_context=True)
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

@Client.command(pass_context=True)
async def ban(ctx):
    listOfWords = ctx.message.content.split(" ")
    member = listOfWords[1][3:-1]
    user = Client.get_user(int(member))
    await ctx.guild.ban(user)
    await ctx.channel.send(file=discord.File('ban.jpg'))

def getToken(fileName,command):
    configFile = open(fileName,"r")
    lineList = configFile.readlines()
    for line in lineList:
        if not line.startswith('#'):
            split = line.split("=")
            if split[0] == command:
                return split[1]
    return "Command: " + command + " not found." 

token = getToken("config.txt", "TOKEN")
Client.run(token)

"""""""""
TO-DO:
    0.make sure only admin > can use the bot.
    1.make bot send message when role is assigned (iam)
    2.make bot send message on warn.
    3.make bot send warnlog
    4.streamer role -> live. https://discordpy.readthedocs.io/en/latest/api.html#discord.Streaming
    5.Welcome image

"""""""""
