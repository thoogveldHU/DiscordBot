import discord
import asyncio
from discord.ext import commands
from discord.ext.commands import Bot, has_any_role
from discord.ext.tasks import loop
from discord.utils import get
import openpyxl
import os
from PIL import Image, ImageDraw, ImageFont
import textwrap
import youtube_dl


# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    # bind to ipv4 since ipv6 addresses cause issues sometimes
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command()
    async def play(self, ctx, *, url):
        """Plays from a url (almost anything youtube_dl supports)"""

        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=self.bot.loop)
            ctx.voice_client.play(player, after=lambda e: print(
                'Player error: %s' % e) if e else None)

        await ctx.send('Now playing: {}'.format(player.title))

    @commands.command()
    async def stream(self, ctx, *, url):
        """Streams from a url (same as yt, but doesn't predownload)"""

        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(
                'Player error: %s' % e) if e else None)

        await ctx.send('Now playing: {}'.format(player.title))

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("Changed volume to {}%".format(volume))

    @commands.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    @play.before_invoke
    @stream.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError(
                    "Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

#prefix
Client = Bot('!')

#Check for streamer & live roles.
@loop(seconds=60)
async def checkForStreaming():
    await Client.wait_until_ready()
    #get the streamer role from the guild, by id.
    guild = Client.get_guild(491609268567408641)
    streamerRole = guild.get_role(659062011082047499)
    liveRole = guild.get_role(660090844124282881)
    #Test channel to send notifcation of live, by id. Later this should add the Role "LIVE".
    channel = guild.get_channel(660083659801493505)
    #all users with the streamer role
    for member in streamerRole.members:
        for activity in member.activities:
            if activity.name == "Twitch":
                if liveRole not in member.roles:
                    await channel.send(member.name + "is live --- TEST")
                    await member.add_roles(liveRole)
    #Checking if still live.
    for member in liveRole.members:
        activList = []
        for activity in member.activities:
            activList.append(activity.name)
        if "Twitch" not in activList:
            await channel.send(member.name + "is no longer live --- TEST")
            await member.remove_roles(liveRole)

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

#command warn
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
async def clearwarn(ctx):

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
            for item in row[2:]:
                #Skip the ID and Name of the member, and just get the warnings.
                cell = (str(item)[-3:-1])
                ws[cell] = None
            wb.save('warnings.xlsx')
            return await ctx.send(user.name + " warns have been cleared.")

#command warnlog
@Client.command(pass_context=True)
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
async def warnlog(ctx):
    #Getting the user from the message
    listOfWords = ctx.message.content.split(" ")
    member = listOfWords[1][3:-1]
    user = Client.get_user(int(member))
    embed = discord.Embed(title="Warnlog for user {0.name}".format(user))
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
                if item.value != None:
                    warns.append(item.value)
                    size = len(warns)
                    embed.add_field(name="Warning {0}".format(size),value=item.value,inline=False)
                else:
                    embed.add_field(name="No warnings found for {0.name}".format(user),value="GOOD GENIE!")
    await ctx.channel.send(embed=embed)

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
    makeWelcomeBanner(member.name)
    guild = member.guild
    if guild.system_channel is not None:
        await guild.system_channel.send(file=discord.File('welcome_banner_ready.png'))
        to_send = 'Welkom {0.mention} bij {1.name}! Doe een !welkom om de rest van de kanalen te kunnen zien!'.format(member,guild)
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
@has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
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

@Client.event
async def on_message_delete(message):
    if not message.content.startswith("!"):
        #Get the old message and give it a make over.
        embed = discord.Embed(title="Deleted Message by: {0}".format(message.author))
        embed.add_field(name="Message content",value=message.content,inline=False)
        embed.add_field(name="Channel:",value=message.channel,inline=False)
        #get the streamer role from the guild, by id.
        guild = Client.get_guild(491609268567408641)
        #Logging channel.
        channel = guild.get_channel(661330775618224158)
        #Send it to the logging channel.
        await channel.send(embed=embed)

@Client.event
async def on_message_edit(before,after):
    #Get the old message and give it a make over.
    try:
        embed = discord.Embed(title="Edited Message by: {0}".format(before.author))
        embed.add_field(name="Old message content",value=before.content, inline=False)
        embed.add_field(name="New Message content",value=after.content, inline=False)
        embed.add_field(name="Channel",value=before.channel,inline=False)
        #get the streamer role from the guild, by id.
        guild = Client.get_guild(491609268567408641)
        #Logging channel.
        channel = guild.get_channel(661330775618224158)
        #Send it to the logging channel.
        await channel.send(embed=embed)
    except discord.errors.HTTPException:
        print()

#run bot
token = getToken("config.txt", "TOKEN")
checkForStreaming.start()
Client.add_cog(Music(Client))
Client.run(token)

"""""""""
TO-DO:
    1.create events
    2.most played / is playing
    3.ttl next event
    4.meme return /r/memes or /r/dankmemes
    5.music queue
"""""""""
