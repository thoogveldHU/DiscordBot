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
import pickle

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''


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

class UserInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='userinfo')
    async def _userinfo(self, ctx: commands.Context):
        try:
            user = ctx.message.mentions[0]
            member = ctx.guild.get_member(user.id)

            dutch_date_created = str(user.created_at.day) + "-"  + str(user.created_at.month) + "-" + str(
                user.created_at.year) + "  " + str(user.created_at.hour) + ":" + str(user.created_at.minute)

            dutch_date_joined = str(member.joined_at.day) + "-" + str(member.joined_at.month) + "-" + str(
                member.joined_at.year) + "  " + str(member.joined_at.hour) + ":" + str(member.joined_at.minute)

            roles = ""
            for role in member.roles:
                if str(role) != "@everyone":
                    roles += str(role) + ", "

            embed = discord.Embed(title='Genie : {.display_name}'.format(user), color=user.colour)
            embed.set_author(name="KWAADGENIE'S ONE AND ONLY...", url='https://www.youtube.com/watch?v=dQw4w9WgXcQ')
            embed.set_thumbnail(url=user.avatar_url)
            embed.add_field(name='name', value='{.name}'.format(user), inline=True)
            embed.add_field(name='joined at', value=dutch_date_joined, inline=True)
            embed.add_field(name='created account', value=dutch_date_created, inline=True)
            embed.add_field(name='roles', value=roles, inline=True)
            embed.add_field(name='id', value=user.id, inline=True)
            embed.set_footer(text='we love every single genie < 3')
            return await ctx.send(embed=embed)

        except IndexError:
            return
        
class Translater(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='clear')
    @has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
    async def _clear(self, ctx: commands.Context, number):
        number = int(number)
        counter = 0
        async for message in ctx.channel.history(limit=number):
            if counter < number:
                await message.delete()
                counter += 1

    @commands.command(name='warn')
    @has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
    async def _warn(self, ctx: commands.Context):

        try:
            member_to_warn = ctx.message.mentions[0]
        except IndexError:
            return
        
        try:
            splitLine = ctx.message.content.split(" ")
            reason = "-"
            for word in splitLine[2:]:
                reason += str(word) + " "
        except IndexError:
            return
        
        try:
            memberList = pickle.load(open("members.dat", "rb"))
            isSaved = 0
            amountOfWarns = 1
            for member in memberList: #0 id, 1 name, 2.... warns
                counter = 0
                if member[0] == member_to_warn.id:
                    member.append(reason)
                    amountOfWarns = len(member[2:])
                    pickle.dump(memberList, open("members.dat","wb"))
                    isSaved = 1
                counter += 1
            if isSaved == 0:
                memberList.append([member_to_warn.id, member_to_warn.name, reason])
                pickle.dump(memberList, open("members.dat", "wb"))
            await ctx.channel.send(member_to_warn.mention + " has been warned. \n Total warns for this genie: " + str(amountOfWarns) + ".")

        except FileNotFoundError:
            return

    @commands.command(name='clearwarn')
    @has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
    async def _clearwarn(self, ctx: commands.Context):
        member_to_warn = ctx.message.mentions[0]
        memberList = pickle.load(open("members.dat","rb"))
        counter = 0
        for member in memberList:
            if member[0] != member_to_warn.id:
                counter += 1
            else:
                memberList.pop(counter)
                return pickle.dump(memberList, open("members.dat", "wb"))

    @commands.command(name='warnlog')
    @has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
    async def _warnlog(self, ctx: commands.Context):
        try:
            embed=discord.Embed(title="Warns for user", url="https://www.youtube.com/watch?v=IbkziFdxHuA", color=0xff0000)
            embed.set_footer(text="Watch out..")
            member_to_warn = ctx.message.mentions[0]
            memberList = pickle.load(open("members.dat","rb"))
            for member in memberList:
                isWarned = 0
                if member[0] == member_to_warn.id:
                    counter = 1
                    print(member[2:])
                    for warn in member[2:]:
                        embed.add_field(name="Warn " + str(counter), value=warn, inline=False)
                        counter += 1
                        isWarned = 1
            if isWarned == 1:
                return await ctx.channel.send(embed=embed)
            else:
                embed = discord.Embed(title="Nothing found!", color=0x00ff00)
                return await ctx.channel.send(embed=embed)
        except:
            embed = discord.Embed(title="Nothing found!", color=0x00ff00)
            return await ctx.channel.send(embed=embed)

    @commands.command(name='ban')
    @has_any_role(627925171818332180, 512365666611757076, 652607412611710984)
    async def _ban(self, ctx: commands.Context):
        listOfWords = ctx.message.content.split(" ")
        member = listOfWords[1][3:-1]
        user = Client.get_user(int(member))
        await ctx.guild.ban(user)
        await ctx.channel.send(file=discord.File('ban.jpg'))

    @commands.command(name='invite')
    async def invite(self, ctx: commands.Context):
        link = await ctx.channel.create_invite(max_uses=1, reason=ctx.author.name + ' made this invite.')
        return await ctx.send(link)

class RoleCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='iam')
    @has_any_role(627925171818332180, 512365666611757076, 652607412611710984, 627893819979071509)
    async def _iam(self, ctx: commands.Context):
        listOfWords = str(ctx.message.content.lower()).split(" ")
        allowedList = ["streamer","tp20"]
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

    @commands.command(name='welkom')
    async def _welkom(self, ctx: commands.Context):
        member = ctx.message.author
        genie = get(member.guild.roles, id=627893819979071509)
        await member.add_roles(genie)
        emoji = '\U0001f44d'
        return await ctx.message.add_reaction(emoji)

    # welcome
    @commands.command(name='welcome')
    async def _welcome(self, ctx: commands.Context):
        member = ctx.message.author
        genie = get(member.guild.roles, id=627893819979071509)
        await member.add_roles(genie)
        emoji = '\U0001f44d'
        return await ctx.message.add_reaction(emoji)

class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def makeWelcomeBanner(self, name):
        astr = '''Welkom bij Kwaad Genie \n''' + str(name) + "!"
        para = textwrap.wrap(astr, width=30)
        im = Image.open('banner.png')
        MAX_W, MAX_H = im.size[0], im.size[1]

        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype('segoe-ui-bold.ttf', 28)

        # Front text
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

    @commands.Cog.listener()
    async def on_member_join(self, member):
        makeWelcomeBanner(member.name)
        guild = member.guild
        if guild.system_channel is not None:
            await guild.system_channel.send(file=discord.File('welcome_banner_ready.png'))
            to_send = 'Welkom {0.mention} bij {1.name}! Doe een !welkom om de rest van de kanalen te kunnen zien!'.format(
                member, guild)
            await guild.system_channel.send(to_send)
        channel = guild.get_channel(662355726043447296)
        embed = discord.Embed(title='Genie joined the server.')
        embed.add_field(name="User:", value=member.name, inline=False)
        return await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        try:
            if not message.content.startswith("!"):
                # Get the old message and give it a make over.
                embed = discord.Embed(
                    title="Deleted Message by: {0}".format(message.author))
                embed.add_field(name="Message content",
                                value=message.content, inline=False)
                embed.add_field(name="Channel:",
                                value=message.channel, inline=False)
                # get the streamer role from the guild, by id.
                guild = Client.get_guild(491609268567408641)
                # Logging channel.
                channel = guild.get_channel(661330775618224158)
                # Send it to the logging channel.
                await channel.send(embed=embed)
        except discord.errors.HTTPException:
            print()

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # Get the old message and give it a make over.
        if (before.content != after.content):
            try:
                embed = discord.Embed(
                    title="Edited Message by: {0}".format(before.author))
                embed.add_field(name="Old message content",
                                value=before.content, inline=False)
                embed.add_field(name="New Message content",
                                value=after.content, inline=False)
                embed.add_field(
                    name="Channel", value=before.channel, inline=False)
                # get the streamer role from the guild, by id.
                guild = Client.get_guild(491609268567408641)
                # Logging channel.
                channel = guild.get_channel(661330775618224158)
                # Send it to the logging channel.
                await channel.send(embed=embed)
            except discord.errors.HTTPException:
                print()

    @commands.Cog.listener()
    async def on_member_remove(self, user):
        guild = Client.get_guild(491609268567408641)
        # Logging channel.
        channel = guild.get_channel(662355726043447296)
        embed = discord.Embed(title='Genie left the server.')
        embed.add_field(name="User:", value=user, inline=False)
        return await channel.send(embed=embed)

class Streamer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.checkForStreaming.start()

    # Check for streamer & live roles.
    @loop(seconds=60)
    async def checkForStreaming():
        await Client.wait_until_ready()
        # get the streamer role from the guild, by id.
        guild = Client.get_guild(491609268567408641)
        streamerRole = guild.get_role(659062011082047499)
        liveRole = guild.get_role(660090844124282881)
        # all users with the streamer role
        for member in streamerRole.members:
            for activity in member.activities:
                if activity.name == "Twitch":
                    if liveRole not in member.roles:
                        await member.add_roles(liveRole)
        # Checking if still live.
        for member in liveRole.members:
            activList = []
            for activity in member.activities:
                activList.append(activity.name)
            if "Twitch" not in activList:
                await member.remove_roles(liveRole)

class Event(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

# prefix
Client = Bot('!')

#read token from file
def getToken(fileName, command):
    configFile = open(fileName, "r")
    lineList = configFile.readlines()
    for line in lineList:
        if not line.startswith('#'):
            split = line.split("=")
            if split[0] == command:
                return split[1]
    return "Command: " + command + " not found."

# run bot
token = getToken("config.txt", "TOKEN")

# checkForStreaming.start()
Client.add_cog(Streamer(Client))
Client.add_cog(Music(Client))
Client.add_cog(UserInfo(Client))
Client.add_cog(Translater(Client))
Client.add_cog(Moderation(Client))
Client.add_cog(RoleCommands(Client))
Client.add_cog(Listeners(Client))
Client.add_cog(Event(Client))

Client.run(token)

"""""""""
TO-DO:
    1.create events
    2.most played / is playing
    3.ttl next event
    4.meme return /r/memes or /r/dankmemes
"""""""""
