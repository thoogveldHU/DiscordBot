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
import functools
import itertools
import math
import random
from async_timeout import timeout



# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

class Userinfo:

    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True, aliases=['user', 'uinfo', 'info', 'ui'])
    async def userinfo(self, ctx, *, name=""):
        """Get user info. Ex: [p]info @user"""
        if ctx.invoked_subcommand is None:
            pre = cmd_prefix_len()
            if name:
                try:
                    user = ctx.message.mentions[0]
                except IndexError:
                    user = ctx.guild.get_member_named(name)
                if not user:
                    user = ctx.guild.get_member(int(name))
                if not user:
                    user = self.bot.get_user(int(name))
                if not user:
                    await ctx.send(self.bot.bot_prefix + 'Could not find user.')
                    return
            else:
                user = ctx.message.author

            if user.avatar_url_as(static_format='png')[54:].startswith('a_'):
                avi = user.avatar_url.rsplit("?", 1)[0]
            else:
                avi = user.avatar_url_as(static_format='png')
            if isinstance(user, discord.Member):
                role = user.top_role.name
                if role == "@everyone":
                    role = "N/A"
                voice_state = None if not user.voice else user.voice.channel
            if embed_perms(ctx.message):
                em = discord.Embed(timestamp=ctx.message.created_at, colour=0x708DD0)
                em.add_field(name='User ID', value=user.id, inline=True)
                if isinstance(user, discord.Member):
                    em.add_field(name='Nick', value=user.nick, inline=True)
                    em.add_field(name='Status', value=user.status, inline=True)
                    em.add_field(name='In Voice', value=voice_state, inline=True)
                    em.add_field(name='Game', value=user.activity, inline=True)
                    em.add_field(name='Highest Role', value=role, inline=True)
                em.add_field(name='Account Created', value=user.created_at.__format__('%A, %d. %B %Y @ %H:%M:%S'))
                if isinstance(user, discord.Member):
                    em.add_field(name='Join Date', value=user.joined_at.__format__('%A, %d. %B %Y @ %H:%M:%S'))
                em.set_thumbnail(url=avi)
                em.set_author(name=user, icon_url='https://i.imgur.com/RHagTDg.png')
                await ctx.send(embed=em)
            else:
                if isinstance(user, discord.Member):
                    msg = '**User Info:** ```User ID: %s\nNick: %s\nStatus: %s\nIn Voice: %s\nGame: %s\nHighest Role: %s\nAccount Created: %s\nJoin Date: %s\nAvatar url:%s```' % (user.id, user.nick, user.status, voice_state, user.activity, role, user.created_at.__format__('%A, %d. %B %Y @ %H:%M:%S'), user.joined_at.__format__('%A, %d. %B %Y @ %H:%M:%S'), avi)
                else:
                    msg = '**User Info:** ```User ID: %s\nAccount Created: %s\nAvatar url:%s```' % (user.id, user.created_at.__format__('%A, %d. %B %Y @ %H:%M:%S'), avi)
                await ctx.send(self.bot.bot_prefix + msg)

            await ctx.message.delete()

    @userinfo.command()
    async def avi(self, ctx, txt: str = None):
        """View bigger version of user's avatar. Ex: [p]info avi @user"""
        if txt:
            try:
                user = ctx.message.mentions[0]
            except IndexError:
                user = ctx.guild.get_member_named(txt)
            if not user:
                user = ctx.guild.get_member(int(txt))
            if not user:
                user = self.bot.get_user(int(txt))
            if not user:
                await ctx.send(self.bot.bot_prefix + 'Could not find user.')
                return
        else:
            user = ctx.message.author

        if user.avatar_url_as(static_format='png')[54:].startswith('a_'):
            avi = user.avatar_url.rsplit("?", 1)[0]
        else:
            avi = user.avatar_url_as(static_format='png')
        if embed_perms(ctx.message):
            em = discord.Embed(colour=0x708DD0)
            em.set_image(url=avi)
            await ctx.send(embed=em)
        else:
            await ctx.send(self.bot.bot_prefix + avi)
        await ctx.message.delete()

class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return '**{0.title}** by **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(
            cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError(
                'Couldn\'t find anything that matches `{}`'.format(search))

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError(
                    'Couldn\'t find anything that matches `{}`'.format(search))

        webpage_url = process_info['webpage_url']
        partial = functools.partial(
            cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(webpage_url))

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError(
                        'Couldn\'t retrieve any matches for `{}`'.format(webpage_url))

        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append('{} days'.format(days))
        if hours > 0:
            duration.append('{} hours'.format(hours))
        if minutes > 0:
            duration.append('{} minutes'.format(minutes))
        if seconds > 0:
            duration.append('{} seconds'.format(seconds))

        return ', '.join(duration)

class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(title='Now playing',
                               description='```css\n{0.source.title}\n```'.format(
                                   self),
                               color=discord.Color.blurple())
                 .add_field(name='Duration', value=self.source.duration)
                 .add_field(name='Requested by', value=self.requester.mention)
                 .add_field(name='Uploader', value='[{0.source.uploader}]({0.source.uploader_url})'.format(self))
                 .add_field(name='URL', value='[Click]({0.source.url})'.format(self))
                 .set_thumbnail(url=self.source.thumbnail))

        return embed

class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]

class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed())

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage(
                'This command can\'t be used in DM channels.')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('An error occurred: {}'.format(str(error)))

    @commands.command(name='join', invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel."""

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='summon')
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Summons the bot to a voice channel.

        If no channel was specified, it joins your channel.
        """

        if not channel and not ctx.author.voice:
            raise VoiceError(
                'You are neither connected to a voice channel nor specified a channel to join.')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        """Clears the queue and leaves the voice channel."""

        if not ctx.voice_state.voice:
            return await ctx.send('Not connected to any voice channel.')

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volume: int):
        """Sets the volume of the player."""

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        if 0 > volume > 100:
            return await ctx.send('Volume must be between 0 and 100')

        ctx.voice_state.volume = volume / 100
        await ctx.send('Volume of the player set to {}%'.format(volume))

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        """Displays the currently playing song."""

        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.command(name='pause')
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        """Pauses the currently playing song."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='resume')
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context):
        """Resumes a currently paused song."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='stop')
    @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):
        """Stops playing song and clears the queue."""

        ctx.voice_state.songs.clear()

        if not ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('⏹')

    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        """Vote to skip a song. The requester can automatically skip.
        3 skip votes are needed for the song to be skipped.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Not playing any music right now...')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send('Skip vote added, currently at **{}/3**'.format(total_votes))

        else:
            await ctx.send('You have already voted to skip this song.')

    @commands.command(name='queue')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        """Shows the player's queue.

        You can optionally specify the page to show. Each page contains 10 elements.
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(
                i + 1, song)

        embed = (discord.Embed(description='**{} tracks:**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                 .set_footer(text='Viewing page {}/{}'.format(page, pages)))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('✅')

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Removes a song from the queue at a given index."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('✅')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        """Loops the currently playing song.

        Invoke this command again to unloop the song.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction('✅')

    @commands.command(name='play')
    async def _play(self, ctx: commands.Context, *, search: str):
        """Plays a song.

        If there are songs in the queue, this will be queued until the
        other songs finished playing.

        This command automatically searches from various sites if no URL is provided.
        A list of these sites can be found here: https://rg3.github.io/youtube-dl/supportedsites.html
        """

        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send('An error occurred while processing this request: {}'.format(str(e)))
            else:
                song = Song(source)

                await ctx.voice_state.songs.put(song)
                await ctx.send('Enqueued {}'.format(str(source)))

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError(
                'You are not connected to any voice channel.')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError(
                    'Bot is already in a voice channel.')

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
    memberID = int(listOfWords[1][3:-1]) #userID

    #getting the user from their ID
    user = await Client.fetch_user(memberID)

    #Gettings Reason from the message
    warnReason = "No reason given."
    try:
        reasonString = ""
        for word in listOfWords[2:]:
            reasonString += word + " "
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
        await guild.system_channel.send(to_send)
    channel = guild.get_channel(662355726043447296)
    embed = discord.Embed(title='Genie joined the server.')
    embed.add_field(name="User:", value=member.name, inline=False)
    return await channel.send(embed=embed)

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
    astr = '''Welkom bij Kwaad Genie \n''' + str(name) + "!"
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
    try:
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
    except discord.errors.HTTPException:
        print()

@Client.event
async def on_message_edit(before,after):
    #Get the old message and give it a make over.
    if (before.content != after.content):
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

@Client.event
async def on_member_remove(user):
    guild = Client.get_guild(491609268567408641)
    #Logging channel.
    channel = guild.get_channel(662355726043447296)
    embed = discord.Embed(title='Genie left the server.')
    embed.add_field(name="User:",value=user,inline=False)
    return await channel.send(embed=embed)

@Client.command(pass_context=True)
async def invite(ctx):
    link = await ctx.channel.create_invite(max_uses = 1, reason = ctx.author.name + ' made this invite.')
    return await ctx.send(link)

# @Client.event
# async def on_member_ban(guild,user):
#     #Logging channel.
#     channel = guild.get_channel(661330775618224158)
#     embed = discord.Embed(title='Genie banned!')
#     embed.add_field(name="User:",value=user,inline=False)
#     return await channel.send(embed=embed)

#run bot
token = getToken("config.txt", "TOKEN")
checkForStreaming.start()

Client.add_cog(Music(Client))
#Client.add_cog(Userinfo(Client))

Client.run(token)

"""""""""
TO-DO:
    1.create events
    2.most played / is playing
    3.ttl next event
    4.meme return /r/memes or /r/dankmemes
    5.music queue
"""""""""
