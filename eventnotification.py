from discord.ext import commands
import discord
import re
import asyncio
from datetime import datetime, timedelta, timezone
import sqlite3
from sqlite3 import Error
import shutil#used for db backups
import json
import requests
from random import randrange
from math import ceil
#strftime = string/strptime = obj
class EventNotification:

    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\slowpoke.db' #?mode=rw
        self.month = [] #List of loaded events
        self.createtables() #Creates SQLite tables if they do not exist.
        self.load_events() #Loads events from database to self.month
        self.event_run = False #Am I currently monitoring event notifications?
        self.monitor_run = False #Am I currently monitoring Discord voice channels?
        self.md_runtimes = [] #Populated by runmonitor. List of times to take voice channel snapshots.
        self.nw_num_members = 0 #Number of guildies that attended last NW
        self.id = '336274317962772483' #Bot's ID
        self.hex_colours = [0x1abc9c, 0x16a085, 0x2ecc71, 0x27ae60, 0x3498db, 0x2980b9, 0x9b59b6, 0x8e44ad, 0x34495e, 0x2c3e50, 0xf1c40f, 0xf39c12, 0xe67e22, 0xd35400, 0xe74c3c, 0xc0392b, 0xecf0f1, 0xbdc3c7, 0x95a5a6, 0x7f8c8d] #a e s t h e t i c 
        #self.groups = [Group('Static test group', 'NotVoytek', '1', 'Ser4', self.hex_colours[randrange(0, 19)])]
        self.channelids = {'announcements': '353921936889479168', 'offense': '276513364228964353', 'defense': '276513403629994005', 'guildmissions': '240943280903290880', 'temp': '304607221147500544', 'ann_temp': '366382361610551296', 'gq_temp': '366690805928427520', 'lfg': '344663345892425741', 'lfg_temp': '366382361610551296'}
        self.talking = False
        self.voice = ''

    ##############################General##############################
    @commands.command(pass_context=True)
    async def clean(self, ctx):
        """Deletes Slowpoke Bot's messages for the last 14 days."""
        await self.logger(':wastebasket: I\'m cleaning up after myself!')
        await self.bot.purge_from(ctx.message.channel, limit=9999, check=self.is_me, after=datetime.now()-timedelta(days=13))

    @commands.command(pass_context=True)
    async def linknames(self, ctx, family: str, *args):
        """Links a Family name to a Discord Display Name and ID.

        !linknames Family / !linknames Family family#0000"""
        if await self.chanroles(ctx, 'Guildies'):
            duser = str(args[0]) if args else str(ctx.message.author.name+'#'+ctx.message.author.discriminator)
            dname = discord.utils.get(ctx.message.server.members, name=duser.split('#')[0], discriminator=duser.split('#')[1]).display_name if args else ctx.message.author.display_name
            if self.dbq('SELECT count(*) FROM members WHERE duser = (?)', (duser,))[0] == 1:
                self.dbq('UPDATE members SET family = (?), dnick = (?) WHERE duser = (?)', (family, dname, duser))
                await self.logger('```fix\n'+family+' and '+dname+' have been linked to Discord ID: '+duser+'```\n')
            else:
                self.dbq('INSERT INTO members (family, dnick, duser) VALUES (?,?,?)', (family, dname, duser))
                await self.logger('```fix\n'+duser+' was not found. Creating new entry to link with '+dname+' and '+family+'.```\n')

    async def logger(self, s, say=True):
        with open('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\log.txt', 'a') as logfile:
            logfile.write('['+datetime.strftime(datetime.now(), '%Y-%m-%d %I:%M %p')+'] '+str(s)+'\n')
        if say:
            await self.bot.say(s)

    async def tick_event(self, future, ctx):
        while self.event_run:
            now = datetime.now()
            print('tick')
            for event in self.month:
                for reminder in event.reminders:
                    if (reminder) and (datetime.strptime(reminder, '%Y-%m-%d %I:%M %p')) < now:
                        #THIS CANNOT BE OVER 2000 CHARACTERS/NAME FIELD CANT BE BLANK
                        eventurl = 'http://slowpoke.shivtr.com/events/'+event.eid+'?event_instance_id='+event.e_instance_id
                        event_icon = {'756874': ':crossed_swords:', '757528': ':pushpin:', '756875': ':crossed_swords:'}
                        #make embed event method. async.
                        embed = discord.Embed(description=event_icon[event.event_type] + ' __***' + event.title + '***__', color=0xed859a, inline=True)
                        embed.add_field(name=':alarm_clock: Time:', value=datetime.strftime(event.date_time, '%I:%M %p') + ' PT / ' + datetime.strftime(event.date_time+timedelta(hours=3), '%I:%M %p') + ' ET', inline=True)
                        embed.add_field(name=':calendar_spiral: Date:', value=datetime.strftime(event.date_time, '%A, %B %d'), inline=True)
                        embed.add_field(name=':pencil: Event Page:', value='[Don\'t forget to sign up!]('+eventurl+')', inline=True)
                        embed.set_thumbnail(url='http://s3.mmoguildsites.com/s3/event_photos/'+event.eid+'/original.'+event.imagesuff)
                        if event.event_type == '756874':
                            embed.add_field(name=':globe_with_meridians: Location:', value=event.location+str(1) if event.location != 'TBD' else event.location, inline=True)
                            embed.add_field(name=':shopping_cart: Items to Bring:', value='[List of buffs](https://goo.gl/yhCPzi), Emergency Medical Kits, 3xPolished Stone: Repair Tower, 15xCopper Shards & 30xIron Ingots: Barricade Upgrades')
                            embed.add_field(name=':triangular_flag_on_post: Remember: ', value='Sign-ups must be done at least **3 hours in advance** to count for payout. If you are unable to attend, please let us know in the [comments on the event\'s page]('+eventurl+'#comments_new).', inline=False)
                        if (len(event.reminders) > 2) and (event.event_type == '756874'):
                            await self.bot.send_message(ctx.message.server.get_channel(self.channelids['ann_temp']),'@here', embed=embed)#announcements
                        else:
                            await self.bot.send_message(ctx.message.server.get_channel(self.channelids['temp']),'@here', embed=embed)#slowpokeonly
                        event.rem_reminder(reminder)
            await asyncio.sleep(5)

    def is_me(self, m):
        """Only used for purge_from check."""
        return m.author.id == self.id

    async def chanroles(self, ctx, role='Officer'):
        """Checks if command author has the correct permissions."""
        for r in ctx.message.author.roles:
            if r.name == role:
                return True
        await self.bot.say('```fix\nI\'m sorry '+ctx.message.author.display_name+', I\'m afraid I can\'t do that. (Insufficient channel permissions).\n```')
        await self.logger(ctx.message.author.display_name+' attempted unauthorized command.', False)
        return False

    ##############################Database##############################
    @commands.command(pass_context=True)#TODO NEXT
    async def populatemembers(self, ctx): #get from shivtr json instead of file
        if await self.chanroles(ctx):
            user = '{"user":{"email":"email","password":"password"}}'
            h = {"Content-Type": "application/json"}
            login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
            members_url = 'http://slowpoke.shivtr.com/members.json'
            auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
            members = requests.get(members_url, data=auth).json()['members']
            for member in members:
                print(member['display_name'])
                exists = self.dbq('SELECT count(*) FROM members WHERE family LIKE (?)', (member['display_name'],))
                print(exists)
                if exists[0] == 0:
                    await self.logger('Creating entry for family name: '+member['display_name'], False)
                    self.dbq('INSERT INTO members (family) VALUES (?)', (member['display_name'],))
                else:
                    await self.logger(member['display_name']+' already exists.', False)

    @commands.command(pass_context=True, name='parsediscordmembers')
    async def parsediscordmembers(self, ctx):
        """Compares discord users to the database and updates usernames."""
        #assumes members table is already populated with a list of family names
        if await self.chanroles(ctx):
            for x in list(ctx.message.server.members):
                for role in list(x.roles):
                    if str(role) == '@guildies': #CHANGE TO GUILDIE
                        username = x.name + '#' + str(x.discriminator)
                        foo = re.split('\s+|\(+', x.display_name)[0]
                        await self.logger('Updating entry for :'+username)
                        self.dbq('UPDATE members SET dnick = ?, duser = ? WHERE family LIKE ?', (x.display_name, username, foo))

    @commands.command()
    async def backupdb(self):
        """Makes a backup of slowpoke.db"""
        if await self.chanroles(ctx):
            shutil.copy2(self.db_path, self.db_path + '.bak')
            await self.logger('Database backed up.')

    def dbq(self, *args):
        if args:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    action = str(args[0]).split()
                    if action[0] == 'SELECT':
                        if len(args)>1:
                            cur.execute(args[0], args[1])
                        else:
                            cur.execute(args[0])
                        return cur.fetchall() if action[1] == '*' else cur.fetchone()
                    elif action[0] in ['INSERT', 'UPDATE', 'DELETE']:
                        if len(args)>1:
                            cur.execute(args[0], args[1])
                        else:
                            cur.execute(args[0])
                    else:
                        return None
            except Error as e:
                print(e)
        else:
            return None

    def createtables(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("CREATE TABLE IF NOT EXISTS calendar (eid text, e_instance_id text, event_type text, date_time text, title text, imagesuff text, location text, reminders text)")
                cur.execute("CREATE TABLE IF NOT EXISTS members (family text, dnick text, duser text, nwp text, gqp text)")
                cur.execute("CREATE TABLE IF NOT EXISTS nodewars (duration_minutes int, num_members int)")
                cur.execute("CREATE TABLE IF NOT EXISTS guildquests (last_parsed text)")
                cur.execute("CREATE TABLE IF NOT EXISTS groups (group_n text, group_m text, created_at text, last_updated text, active text, id integer primary key)")
        except Error as e:
            print(e)
            self.logger(e, False)

    ##############################Monitoring##############################
    @commands.command(pass_context=True)
    async def nwp_list(self, ctx):
        """Get a list of members' node war participation."""
        if await self.chanroles(ctx):
            members = self.dbq('SELECT * FROM members WHERE nwp IS NOT NULL')
            nw = ('SELECT * FROM nodewars')
            duration = int(ceil(nw[0]/10.0))*10
            msg = ''
            for member in members:
                attended_dur = int(len(json.loads(member[3])))*10
                attended_per = str(round((attended_dur/duration)*100))+'%'
                msg = msg+'`'+member[0]+'| Node War length: '+str(duration)+'| Attended Duration: '+str(attended_dur)+' | Percent Attended: '+attended_per+'`\n'
            await self.bot.send_message(ctx.message.author, msg)

    @commands.command(pass_context=True, name='gmp_parse')
    async def gmp_parse(self, ctx):
        """Updates members' guild mission participation.

        Run this before gmp_list."""
        if await self.chanroles(ctx):
            try:
                conn = self.create_connection()
                with conn:
                    cur = conn.cursor()
                    gq = self.sbq('SELECT * FROM guildquests')
                    lastgq = datetime.strptime(gq[0], '%Y-%m-%d %H:%M:%S.%f') if gq != None else ''
                    self.dbq('INSERT INTO guildquests (last_parsed) VALUES (?)', (datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),))
                    async for message in self.bot.logs_from(ctx.message.server.get_channel(self.channelids['gq_temp']), after=lastgq):
                        for mention in message.mentions:
                            _gqp = self.dbq('SELECT gqp FROM members WHERE duser = ?', (str(mention),))
                            if _gqp[0] != None:
                                _gqp = json.loads(_gqp[0])
                                _gqp.append(datetime.strftime(message.timestamp, '%Y-%m-%d'))
                                __gqp = _gqp
                            else:
                                __gqp = [datetime.strftime(message.timestamp, '%Y-%m-%d')]
                            self.dbq('UPDATE members SET gqp = ? WHERE duser LIKE ?', (json.dumps(__gqp), str(mention)))
            except Error as e:
                print(e)
                await self.logger(e, False)

    @commands.command(pass_context=True)
    async def gmp_list(self, ctx):
        """Get a list of members' guild mission participation."""
        if await self.chanroles(ctx):
            emb = discord.Embed(description=':clipboard: __***Guild Mission Participation***__', color=0xed859a, inline=False)
            members = self.dbq('SELECT * FROM members WHERE gqp IS NOT NULL')
            members = cur.fetchall()
            lastgq = self.dbq('SELECT * FROM guildquests')
            #lastgq = str(cur.fetchone()[0])
            for member in members:
                nq=len(json.loads(member[4]))
                s = 's' if nq > 1 else ''
                emb.add_field(name=member[0], value='`'+str(nq)+' mission'+s+' since '+lastgq+'`', inline=False)
                #msg = msg + '`' + member[0] + ' | ' + str(member[4]) + '`\n'
            await self.bot.send_message(ctx.message.author, embed=emb)

    ##############################Events##############################
    @commands.command(pass_context=True)
    async def runevent(self, ctx):
        """Begin event notifier."""
        if await self.chanroles(ctx):
            await self.bot.delete_message(ctx.message)
            if self.event_run == False:
                await self.logger('Running Event Notifier...')
                self.event_run = True
                self.future = asyncio.Future()
                asyncio.ensure_future(self.tick_event(self.future, ctx))
            else:
                self.event_run = False
                await self.logger('Shutting down Event Notifier...')

    @commands.command(pass_context=True, name='addchannel')
    async def addchannel(self, ctx, e_instance_id: str, channel: str):
        """Add a channel for an existing event."""
        if await self.chanroles(ctx):
                self.dbq('UPDATE calendar SET location = ? WHERE e_instance_id = ?', (channel, e_instance_id))
                await self.bot.say('Event ID ' + e_instance_id + ' has been updated with location: ' + channel)

    @commands.command(pass_context=True, name='processcalendar') #MAKE AUTOMATIC, ENSURE NO DUPES
    async def processcalendar(self, ctx):
        """Updates database with calendar events from shivtr."""
        if await self.chanroles(ctx):
            self.dbq('DELETE FROM calendar')
            self.month = []
            user = '{"user":{"email":"haggard05@gmail.com","password":"_W0jt3k!"}}'
            h = {"Content-Type": "application/json"}
            login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
            url = 'http://slowpoke.shivtr.com/events.json'
            auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
            e = requests.get(url, data=auth).json()
            eventsindex = e['events']
            n = datetime.now(timezone.utc)
            eid = {}
            for z in eventsindex:
                e_id = str(z['event_id'])
                e_date = z['date']
                if ":" == e_date[-3:-2]:
                    e_date = e_date[:-3]+e_date[-2:]
                d = datetime.strptime(e_date, '%Y-%m-%dT%H:%M:%S.%f%z')
                if (e_id in eid) and (d >= n):
                    eid[e_id]['events'].append({'id': str(z['id']), 'date': d})
                elif d >= n:
                    #{"832802": {"events":[], "name": "", "event_category_id": "", "eid" : ""}}
                    print('Processing event id: '+e_id)
                    if requests.get('http://s3.mmoguildsites.com/s3/event_photos/'+e_id+'/original.jpg').status_code == 200:
                        imgsuff = 'jpg'
                    elif requests.get('http://s3.mmoguildsites.com/s3/event_photos/'+e_id+'/original.png').status_code == 200:
                        imgsuff = 'png'
                    else:
                        imgsuff = 'gif'
                    event_details = requests.get('http://slowpoke.shivtr.com/events/'+e_id+'.json', data=auth).json()
                    eid[e_id] = {'events':[{'id': str(z['id']), 'date': d}], 'imgsuff': imgsuff, 'name': event_details['event']['name'], 'event_category_id': str(event_details['event']['event_category_id'])}
            for k in eid:
                for e in eid[k]['events']:
                    #eid text, e_instance_id text, event_type text, date_time text, title text, location text, reminders text
                    Event(k, e['id'], eid[k]['event_category_id'], datetime.strftime(e['date'], '%Y-%m-%d %I:%M %p'), eid[k]['name'], eid[k]['imgsuff'], None, None, 1)
            await self.logger('Calendar has been parsed!')

    @commands.command(pass_context=True, name='weeklyoverview')
    async def weeklyoverview(self, ctx, month: str, start: str, end: str):#add description?
        """Posts an event overview in the #announcements channel."""
        if await self.chanroles(ctx):
            await self.bot.purge_from(ctx.message.server.get_channel(self.channelids['ann_temp']), limit=100)#announcements
            week = []
            msg = ''
            event_icon = {'756874': ':crossed_swords:', '757528': ':pushpin:', '756875': ':crossed_swords:'}
            start = datetime.strptime(start+'-'+month+'-'+str(datetime.now().year), '%d-%m-%Y')
            end = datetime.strptime(end+'-'+month+'-'+str(datetime.now().year), '%d-%m-%Y')
            for e in self.month:
                if (e.date_time >= start) and (e.date_time <= end+timedelta(days=1)):
                    week.append(e)
            week.sort(key=lambda x: x.date_time)
            for event in week:
                msg += event_icon[event.event_type] + ' __***' + event.title + '***__ | ' + datetime.strftime(event.date_time, '%A, %B %d') + ' | ' +datetime.strftime(event.date_time, '%I:%M %p') + ' PT / ' + datetime.strftime(event.date_time+timedelta(hours=3), '%I:%M %p') + ' ET | http://slowpoke.shivtr.com/events/'+event.eid+'?event_instance_id='+event.e_instance_id+'\n'
            #await self.bot.delete_message(ctx.message)#deletes calling message
            await self.bot.send_message(ctx.message.server.get_channel(self.channelids['ann_temp']), msg)#announcements
            await self.bot.send_message(ctx.message.server.get_channel(self.channelids['temp']), '@Guildies #announcements has been updated with this weeks events! Get signed up for em!')
            await self.logger('Weekly Overview posted.', False)

    @commands.command(pass_context=True)
    async def listall(self, ctx):
        """Lists all events in database."""
        if await self.chanroles(ctx):
            self.month = []
            self.load_events()
            embed = discord.Embed(description=' __***Upcoming Events***__', color=0xed859a)
            for event in self.month:
                embed.add_field(name='Event ID: ' + event.e_instance_id, value='__' + event.title + '__: ' + event.date_time_str + ', Location: ' + event.location, inline=True)
            await self.bot.say('@here', embed=embed)

    @commands.command(pass_context=True)
    async def runmonitor(self, ctx):
        """Begin monitoring Discord for NW participation.

        Use command again to end the monitoring."""
        if await self.chanroles(ctx):
            start = datetime.now()
            if self.monitor_run == False:
                self.dbq('DELETE FROM nodewars')
                await self.logger('Monitoring Discord for Node War Participation...')
                for x in range(12):#run every 10 minutes after 6pm
                    #self.md_runtimes.append(start+timedelta(minutes=(x*10)))#every 10 min
                    self.md_runtimes.append(start+timedelta(minutes=(x)))#for testing
                self.monitor_run = True
                self.futuremd = asyncio.Future()
                asyncio.ensure_future(self.monitordiscord(self.futuremd, ctx))
            else:
                self.monitor_run = False
                duration_m = int(round((start-datetime.now().replace(hour=18, minute=00)).total_seconds()/60))
                self.dbq('INSERT INTO nodewars (duration_minutes, num_members) VALUES (?,?)', (duration_m, self.nw_num_members))
                self.nw_num_members = 0
                await self.logger('Ending Discord monitoring of Node War Participation...')
        else:
            print('FICL')

    async def monitordiscord(self, future, ctx):
        while self.monitor_run:
            print('tock')
            for t in self.md_runtimes:
                if t <= datetime.now():
                    await self.logger('Taking Discord Snapshot...')
                    self.md_runtimes.remove(t)
                    now = datetime.now().strftime('%d-%m_%H:%M')
                    #Retrieve list of members currently in applicable voice channels
                    duo = list(ctx.message.server.get_channel('300204089676136448').voice_members) + list(ctx.message.server.get_channel('256540097858502657').voice_members) #change id
                    num_members = 0
                    for usr in duo:
                        #Do not include idle users
                        if str(usr.status) != 'idle':#idle
                            num_members += 1
                            duser = str(usr.name+'#'+usr.discriminator)
                            _nwp = self.dbq("SELECT nwp FROM members WHERE duser = ?", (duser,))
                            if _nwp and _nwp[0]:
                                _nwp = json.loads(_nwp[0])
                                _nwp.append(now)
                                __nwp = _nwp
                            elif _nwp:
                                __nwp = [now]
                            else:
                                __nwp = [now]
                                print('Cannot find '+duser+' in database. Creating entry.')
                                self.dbq("INSERT INTO members (duser) VALUES (?)", (duser,))
                            self.dbq("UPDATE members SET nwp = ? WHERE duser = ?", (json.dumps(__nwp), duser))
                            self.nw_num_members = num_members if (num_members > self.nw_num_members) else self.nw_num_members
                    await self.logger('Processed ' + str(self.nw_num_members)+' members.')
            await asyncio.sleep(5)

    def load_events(self):
        print('Loading Events...')
        rows = self.dbq('SELECT * FROM calendar')
        for event in rows:
            self.month.append(Event(event[0], event[1], event[2], event[3], event[4], event[5], event[6], event[7], 0))

    ##############################Group##############################
    @commands.command(pass_context=True)
    async def group(self, ctx, *args):
        if await self.chanroles(ctx, 'Guildies'):
            author = ctx.message.author.display_name
            if args and args[0].isdigit() and args[1] == 'join':
                groupid = str(args[0])
                action = 'join'
            elif args and args[0] in ['create', 'leave', 'list']:
                args = list(args)
                action = args[0]
            else:
                await self.logger('Unrecognized argument. Please try again using the following formats:\n `!group list`\n `!group 1 join`\n `!group create (Serendia 4) This is a group!`\n `!group leave`')       
                return None

            if action == 'create':
                if args and len(args)>2 and re.search(r'\(\w+\)', args[1]):
                    channel = str(args[1]).strip('(').strip(')')
                    group_n = str(' '.join(args[2:])) if len(args) >= 1 else None
                    for cur_group in self.groups:
                        if author in cur_group.members:
                            await self.logger('You cannot create a group while you are in a group. Please leave your current group and try again.')
                            return None
                        elif group_n in self.groups:
                            await self.logger('A group with the name '+group_n+' already exists!')
                            return None
                    gid_temp = str(len(self.groups)+1)
                    self.groups.append(Group(group_n, author, gid_temp, channel, self.hex_colours[randrange(0, 19)]))
                    await self.logger(author+' has created group '+gid_temp+': '+group_n+' on '+channel)
                    return None
                else:
                    await self.logger('Please try again with the proper syntax: `!group create (channel) Group Name`')
                    return None

            elif action == 'join':
                for g in self.groups:
                    cur_group = g if g.group_id == groupid else None
                    if author in g.members:
                        await self.logger(author + ' is already in a group! Please leave that group to join a different one.')
                        return None
                if cur_group:
                    if author not in cur_group.members and len(cur_group.members) < 5:
                        cur_group.members.append(author)
                        cur_group.last_updated = datetime.now().strftime('%I:%M%p %d-%m')
                        cur_group.active = True
                        await self.logger(author+' has joined group '+cur_group.group_id+': '+cur_group.group_n)
                    elif author not in cur_group.members and len(cur_group.members) == 5:
                        await self.logger('Group ' + cur_group.group_n + ' is full!')
                        return None
                    elif author in cur_group.members:
                        await self.logger(author + ' is already in group ' + cur_group.group_n + '!')
                        return None
                else:
                    await self.logger('A group with the id '+groupid+' could not be found.')
                    return None

            elif action == 'leave':
                for g in self.groups:
                    cur_group = g if author in g.members else None
                if cur_group:
                    cur_group.members.remove(author)
                    #If last person in group leaves, delete group
                    if len(cur_group.members) > 0:
                        cur_group.last_updated = datetime.now().strftime('%I:%M%p %d-%m')
                        await self.logger(author+' left group '+cur_group.group_id)
                    else:
                        self.groups.remove(cur_group)
                        await self.logger('Group '+cur_group.group_id+': '+cur_group.group_n+' has disbanded!')
                    return None
                else:
                    await self.logger('You are not in a group!')
                    return None

            else:
                if len(self.groups) > 0:
                    for cur_group in self.groups:
                        await self.bot.send_message(ctx.message.channel, embed=cur_group.gen_embed())
                else:
                    await self.logger('There are no active groups to list!')
                    return None

class Group:
    def __init__(self, group_n, author, gid, channel, hexc):
        self.group_n = group_n
        self.author = author
        self.created_at = datetime.now().strftime('%I:%M%p %d-%m')
        self.last_updated = self.created_at
        self.active = True
        self.channel = channel
        self.members = [self.author]
        self.group_id = gid
        self.hexc = hexc

    def gen_embed(self):
        self.embed = discord.Embed(color=self.hexc, inline=False)#0xed859a
        self.embed.add_field(name=self.group_n, value='['+str(len(self.members))+'/5]: :crown:'+', '.join(self.members), inline=False)
        self.embed.add_field(name='Group ID: ', value=self.group_id, inline=True)
        self.embed.add_field(name='Channel: ', value=self.channel, inline=True)
        #self.embed.add_field(name='Active: ', value=str(self.active), inline=True)
        self.embed.add_field(name='Created: ', value=self.created_at, inline=True)
        self.embed.add_field(name='Last Updated: ', value=self.last_updated, inline=True)
        self.embed.set_thumbnail(url='https://i.imgur.com/TtzKLel.png')
        return self.embed

class Event:
    
    def __init__(self, eid, e_instance_id, event_type, date_time, title, imagesuff, location, reminders, processing):
        self.date_time = datetime.strptime(date_time, '%Y-%m-%d %I:%M %p')
        self.date_time_str = date_time
        self.title = title
        self.imagesuff = imagesuff
        self.event_type = event_type
        self.eid = eid
        self.e_instance_id = e_instance_id
        self.location = location if location else 'TBD'
        if processing:
            self.reminders = self.create_reminders()
            self.add()
        else:
            self.reminders = reminders.split(',')

    def rem_reminder(self, e):
        print(e)
        for x in self.reminders:
            if x == e:
                self.reminders.remove(x)
        try:
            with sqlite3.connect('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\slowpoke.db') as con:
                cur = con.cursor()
                cur.execute("UPDATE calendar SET reminders=? WHERE e_instance_id=?", (','.join(self.reminders), self.e_instance_id))
        except Error as e:
            print(e) 

    def add(self): 
        try:
            with sqlite3.connect('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\slowpoke.db') as con:
                cur = con.cursor()
                cur.execute("INSERT INTO calendar (eid, e_instance_id, event_type, date_time, title, imagesuff, location, reminders) VALUES (?,?,?,?,?,?,?,?)", (self.eid, self.e_instance_id, self.event_type, self.date_time_str, self.title, self.imagesuff, self.location, ','.join(self.reminders)))
        except Error as e:
            print(e)

    def create_reminders(self):
        #included in user-options
        r = 22 if self.event_type == 'Node Wars' else 12
        return [
            (self.date_time - timedelta(hours=r)).strftime('%Y-%m-%d %I:%M %p'),
            (self.date_time - timedelta(hours=5)).strftime('%Y-%m-%d %I:%M %p'),
            (self.date_time - timedelta(hours=1)).strftime('%Y-%m-%d %I:%M %p'), 
        ]

def setup(bot):
    bot.add_cog(EventNotification(bot))
