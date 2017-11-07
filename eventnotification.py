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
from lxml import html
#strftime = string/strptime = obj

class EventNotification:
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\slowpoke.db' #?mode=rw
        self.month = [] #List of loaded events
        self.createtables() #Creates SQLite tables if they do not exist.
        self.load_events() #Loads events from database to self.month
        self.monitor_run = False #Am I currently monitoring Discord voice channels?
        self.md_runtimes = [] #Populated by runmonitor. List of times to take voice channel snapshots.
        self.nw_num_members = 0 #Number of guildies that attended last NW
        self.server = ''
        self.id = '336274317962772483' #Bot's ID
        self.hex_colours = [0x1abc9c, 0x16a085, 0x2ecc71, 0x27ae60, 0x3498db, 0x2980b9, 0x9b59b6, 0x8e44ad, 0x34495e, 0x2c3e50, 0xf1c40f, 0xf39c12, 0xe67e22, 0xd35400, 0xe74c3c, 0xc0392b, 0xecf0f1, 0xbdc3c7, 0x95a5a6, 0x7f8c8d] #a e s t h e t i c 
        self.groups = [Group('Static test group', 'NotVoytek', '1', 'Ser4', self.hex_colours[randrange(0, 19)])]
        self.tasks = {
            'refresh_cal': datetime.now()+timedelta(hours=4),
            'refresh_members': datetime.now()+timedelta(seconds=2),
            'backup_db': datetime.now()+timedelta(days=1)
        }
        self.chans = {}
        asyncio.ensure_future(self.tick())

##############################General##############################
    @asyncio.coroutine
    def tick(self):
        yield from self.getserver()
        while True:
            now = datetime.now()
            print('tick')
            #Monitors event reminders and sends notifications
            for event in self.month:
                #if event.event_type == '756874':
                #if event.e_instance_id == '14588437':
                #    yield from self.website_signups(event, True)
                #elif event.date_time-timedelta(minutes=30) <= now and event.event_type == '756874':
                #    yield from self.website_signups(event, True)
                for reminder in event.reminders:
                    if (reminder) and (datetime.strptime(reminder, '%Y-%m-%d %I:%M %p')) < now: #needs to supress multiple missed notifications on startup
                        em = yield from event.gen_embed()
                        if (len(event.reminders) > 2) and (event.event_type == '756874'):
                            yield from self.bot.purge_from(self.chans['botspam'], check=self.is_embed)
                            #yield from self.bot.send_message(self.chans['announcements'], discord.utils.get(self.server.roles, name='Guildies').mention, embed=em)#announcements
                            yield from self.bot.send_message(self.chans['botspam'], 'Role mentioned here', embed=em)#announcements
                        else:
                            #yield from self.bot.send_message(self.chans['slowpokeonly'], discord.utils.get(self.server.roles, name='Guildies').mention, embed=em)#slowpokeonly
                            yield from self.bot.send_message(self.chans['botspam'], 'Role mentioned here', embed=em)#slowpokeonly
                        event.rem_reminder(reminder)
            for task in self.tasks:
                if self.tasks[task] < now:
                    if task == 'refresh_cal':
                        self.tasks['refresh_cal'] = datetime.now()+timedelta(hours=4)
                        yield from self.refresh_calendar()
                        yield from self.logger('Calendar refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_cal'], '%Y-%m-%d %I:%M %p'), False)
                        print('Calendar refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_cal'], '%Y-%m-%d %I:%M %p'))
                    elif task == 'refresh_members':
                        self.tasks['refresh_members'] = datetime.now()+timedelta(hours=2)
                        yield from self.parsemembers()
                        yield from self.logger('Members refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_members'], '%Y-%m-%d %I:%M %p'), False)
                        print('Members refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_members'], '%Y-%m-%d %I:%M %p'))
                    elif task == 'backup_db':
                        self.tasks['backup_db'] = datetime.now()+timedelta(days=1)
                        yield from self.backup_db()
                        yield from self.logger('Database backed up. Next scheduled: ' + datetime.strftime(self.tasks['backup_db'], '%Y-%m-%d %I:%M %p'), False)
                        print('Database backed up. Next scheduled: ' + datetime.strftime(self.tasks['backup_db'], '%Y-%m-%d %I:%M %p'))
            if self.monitor_run:
                asyncio.ensure_future(self.monitordiscord())
            yield from asyncio.sleep(5)

    @asyncio.coroutine
    def getserver(self):
        while self.bot.is_logged_in == False:
            yield from asyncio.sleep(5)
        self.server = self.bot.get_server('216021345744584704')
        self.voice_chans = {
            'offense': discord.utils.get(self.server.channels, id='276513364228964353'),
            'cannon': discord.utils.get(self.server.channels, id='341105507844751360'),
            'defense': discord.utils.get(self.server.channels, id='276513403629994005'),
            'bdo_hangout': discord.utils.get(self.server.channels, id='216021883177533440'),
            'thunderdome': discord.utils.get(self.server.channels, id='216021962437165056'),
            'grinding': discord.utils.get(self.server.channels, id='216021992019722240'),
            'officer_office': discord.utils.get(self.server.channels, id='218425171365593088')
        }
        self.chans = {
            'announcements': discord.utils.get(self.server.channels, id='353921936889479168'),
            'slowpokeonly': discord.utils.get(self.server.channels, id='322916234402463746'),
            'guild_missions': discord.utils.get(self.server.channels, id='240943280903290880'),
            'lfg': discord.utils.get(self.server.channels, id='344663345892425741'),
            'botspam': discord.utils.get(self.server.channels, id='375873904075472897')
        }

    @commands.command(pass_context=True)
    async def clean(self, ctx):
        """Deletes Slowpoke Bot's messages for the last 14 days."""
        await self.logger(':wastebasket: I\'m cleaning up after myself!')
        await self.bot.purge_from(ctx.message.channel, limit=9999, check=self.is_me, after=datetime.now()-timedelta(days=13))

    async def logger(self, s, say=True):
        with open('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\log.txt', 'a', encoding='utf8') as logfile:
            logfile.write('['+datetime.strftime(datetime.now(), '%Y-%m-%d %I:%M %p')+'] '+str(s)+'\n')
        if say:
            #await self.bot.say(s)
            await self.bot.send_message(self.chans['botspam'], s)

    def is_me(self, m):
        """Only used for purge_from check."""
        return m.author.id == self.id
  
    def is_embed(self, m):
        """Only used for purge_from check."""
        return len(m.embeds) > 0

    async def chanroles(self, ctx, role='💠 Officer'):
        """Checks if command author has the correct permissions."""
        if role in [str(i) for i in ctx.message.author.roles]:
            return True
        await self.bot.say('```fix\nI\'m sorry '+ctx.message.author.display_name+', I\'m afraid I can\'t do that. (Insufficient channel permissions).\n```')
        await self.logger(ctx.message.author.display_name+' attempted unauthorized command.', False)
        return False

##############################Database##############################
    @commands.command(pass_context=True)
    async def testing(self, ctx):
        print(ctx.message.author.id)

    @commands.command()
    async def get_offline_members(self):
        await self.bot.request_offline_members(self.server)
        with open('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\members.txt', 'a', encoding='utf8') as memberfile:
            for member in self.server.members:
                if 'Guildies' in [str(i) for i in member.roles]:
                    memberfile.write(member.display_name+','+str(member)+'\n')
        print('done')

    @commands.command(pass_context=True)
    async def get_members_csv(self, ctx):
        if await self.chanroles(ctx):
            await self.gmp_parse()
            path = 'W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\slowpoke_members.csv'
            open(path, 'w', encoding='utf8').close()
            with open(path, 'a', encoding='utf8') as members_csv:
                members_csv.write('Family Name,Discord User ID,Node War Participation,Guild Mission Participation,Node War Signup Status\n')
                members = self.dbq('SELECT * FROM members')
                for member in members:
                    m_temp = ''
                    for x in range(0,5):
                        m_temp += member[x].replace(',','|')+',' if member[x] else ','
                    members_csv.write(m_temp+'\n')
            await self.bot.send_file(ctx.message.author, path)

    @commands.command(pass_context=True)
    async def linknames(self, ctx, family: str, *args):
        """Links a Family name to a Digcord Display Name and ID.

        !linknames Family / !linknames Family family#0000"""
        if await self.chanroles(ctx, 'Guildies'):
            du = ' '.join(args) if len(args)>1 else str(args[0])
            user_id = du if args else str(ctx.message.author.id)
            #dname = discord.utils.get(self.server.members, discriminator=user_id.split('#')[1]).display_name if args else ctx.message.author.display_name
            exists_user_id = self.dbq('SELECT count(*) FROM members WHERE user_id = (?)', (user_id,))[0]
            exists_family = self.dbq('SELECT count(*) FROM members WHERE family = (?)', (family,))[0]
            if exists_family == 1:
                self.dbq('UPDATE members SET user_id = (?) WHERE family = (?)', (user_id, family))
                await self.logger('```fix\n'+user_id+' has been linked to '+family+'```\n')
            elif exists_user_id == 1:
                self.dbq('UPDATE members SET family = (?) WHERE user_id = (?)', (family, user_id))
                await self.logger('```fix\n'+user_id+' and '+family+' have been linked to Discord ID: '+user_id+'```\n')
            else:
                self.dbq('INSERT INTO members (family, user_id) VALUES (?,?)', (family, user_id))
                await self.logger('```fix\n'+user_id+' was not found. Creating new entry to link with '+family+'.```\n')

    async def parsemembers(self):
        discord_guildies = list(map(lambda z: str(z.id), list(filter(lambda x: 'Guildies' in [str(i) for i in x.roles], self.server.members))))
        db_guildies = list(map(lambda x: str(x[1]), self.dbq('SELECT * FROM members')))
        #If user id exists in database but not in current list of @Guildies, remove them
        user = '{"user":{"email":"haggard05@gmail.com","password":"password"}}'
        h = {"Content-Type": "application/json"}
        login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
        members_url = 'http://slowpoke.shivtr.com/members.json'
        auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
        members = requests.get(members_url, data=auth).json()['members']
        for member in members:
            print('Parsing: '+member['display_name'])
            exists = self.dbq('SELECT count(*) FROM members WHERE family LIKE (?)', (member['display_name'],))
            characters = list(map(lambda x: x['name'], requests.get('http://slowpoke.shivtr.com/members/'+str(member['id'])+'/characters.json', data=auth).json()['characters']))
            if exists[0] == 0:
                await self.logger('Creating entry for family name: '+member['display_name'], False)
                self.dbq('INSERT INTO members (family,characters) VALUES (?,?)', (member['display_name'], ))
            else:
                await self.logger('Updating characters for '+member['display_name'], False)
                self.dbq('UPDATE members SET characters = ? WHERE family = ?', (json.dumps(characters), member['display_name']))
                #await self.logger(member['display_name']+' already exists.', False)
        #Links discord usernames with fam names
        await self.bot.request_offline_members(self.server)
        for guildie in discord_guildies:
            discord_family = re.split('\s+|\(+', guildie.display_name)[0]
            await self.logger('Updating entry for: '+str(guildie), False)
            if self.dbq('SELECT count(*) FROM members WHERE family LIKE ?', (discord_family,))[0] > 0:
                self.dbq('UPDATE members SET user_id = ? WHERE family LIKE ?', (guildie.id, discord_family))
            else:
                with open('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\lostmembers.txt', 'a', encoding='utf8') as memberfile:
                    memberfile.write(discord_family+'\n')
        for db_g in db_guildies:
            if db_g not in discord_guildies:
                self.dbq('DELETE FROM members WHERE user_id = ?', (db_g,))
                await self.logger(db_g+' no longer has @Guildie role. Deleting from database.', False)

    async def backup_db(self):
        """Makes a backup of slowpoke.db"""
        shutil.copy2(self.db_path, self.db_path + '.bak')
        await self.logger('Database backed up.', False)

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
                #ADD DESC TO CALENDAR
                cur.execute("CREATE TABLE IF NOT EXISTS calendar (eid text, e_instance_id text, event_type text, date_time text, title text, imagesuff text, location text, reminders text)")
                cur.execute("CREATE TABLE IF NOT EXISTS members (family text, user_id text, nwp text, gmp text, nws text, characters text)")
                cur.execute("CREATE TABLE IF NOT EXISTS nodewars (nw_date text, duration_minutes int, num_members int)")
                #cur.execute("CREATE TABLE IF NOT EXISTS guildquests (last_parsed text)")
                #cur.execute("CREATE TABLE IF NOT EXISTS groups (group_n text, group_m text, created_at text, last_updated text, active text, id integer primary key)")
        except Error as e:
            print(e)
            self.logger(e, False)

##############################Monitoring##############################
    @commands.command(pass_context=True)
    async def runmonitor(self, ctx):
        """Begin monitoring Discord for NW participation.

        Use command again to end the monitoring."""
        print('runmonitor')
        if self.monitor_run == False:
            start = datetime.now()
            for x in range(12):#run every 10 minutes after 6pm - 12
                self.md_runtimes.append(start+timedelta(minutes=(x*10)))#every 10 min
                #self.md_runtimes.append(start+timedelta(seconds=(x)))#for testing
            self.monitor_run = True
        else:
            self.md_runtimes = [datetime.now()]
            return None

    async def website_signups(self, event, reminder=False):#fix
        user = '{"user":{"email":"haggard05@gmail.com","password":"password"}}'
        h = {"Content-Type": "application/json"}
        login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
        url = 'http://slowpoke.shivtr.com/events/'+event.eid+'?event_instance_id='+event.e_instance_id+'&view=status'
        #url = 'http://slowpoke.shivtr.com/events/835132?event_instance_id=14633723&view=status'#testing
        auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
        tree = html.fromstring(requests.get(url, data=auth).content)
        #date = tree.xpath('//*[@id="event_date"]')[0].text_content()
        if reminder:
            # m_links = tree.xpath('//*[@class="member_link"]//@href')
            # m = tree.xpath('//*[@class="member_link"]')
            to_remind = []
            rsvp = list(map(lambda x: x.text, tree.xpath('//*[@class="member_link"]')))
            m_all = []
            for m in rsvp[1:]:
                m_all.append(str(requests.get('http://slowpoke.shivtr.com'+link+'.json', data=auth).json()['members'][0]['display_name']))
            #for x in to_remind:
            #    print(str(x))
            #rsvp = list(map(lambda x: x.text, attending))+list(map(lambda x: x.text, maybe))+list(map(lambda x: x.text, declined))
            db_members = self.dbq('SELECT * FROM members')
            for member in db_members:
                if member[0] not in m_all:
                    to_remind.append(member[0])
                    print(member[0])
            return None
        else:#need to map to family name
            attending = tree.xpath('//*[@id="status_yes"]')[0].find_class('member_link')
            maybe = tree.xpath('//*[@id="status_maybe"]')[0].find_class('member_link')
            declined = tree.xpath('//*[@id="status_declined"]')[0].find_class('member_link')
            if len(attending)>0:#select specific nw date to modify dict
                for m in attending:
                    self.dbq('UPDATE members SET nws = ? WHERE family = ?', (json.dumps({event.date_time.strftime('%d-%m-%Y'): 'Attending'}), m.text))#event.date_time.strftime('%d-%m-%Y')
            if len(maybe)>0:
                for m in maybe:
                    self.dbq('UPDATE members SET nws = ? WHERE family = ?', (json.dumps({event.date_time.strftime('%d-%m-%Y'): 'Maybe'}), m.text))
            if len(declined)>0:
                for m in declined:
                    self.dbq('UPDATE members SET nws = ? WHERE family = ?', (json.dumps({event.date_time.strftime('%d-%m-%Y'): 'Declined'}), m.text))
            return None

    async def monitordiscord(self):
        print('tock')
        for t in self.md_runtimes:
            if t <= datetime.now():
                print('snapshot')
                self.md_runtimes.remove(t)
                now = datetime.now().strftime('%d-%m_%H:%M')
                cur_nw = datetime.now().strftime('%d-%m-%Y')
                #Retrieve list of members currently in applicable voice channels
                voice_connected_members = list(self.voice_chans['offense'].voice_members) + list(self.voice_chans['defense'].voice_members) + list(self.voice_chans['cannon'].voice_members)
                num_members = 0
                for usr in voice_connected_members:
                    if 'Guildies' in [str(i) for i in usr.roles]:# and str(usr.status) != 'idle'idle
                        num_members += 1
                        user_id = str(usr.id)
                        _nwp = self.dbq("SELECT nwp FROM members WHERE user_id = ?", (user_id,))
                        if _nwp and _nwp[0]:
                            _nwp = json.loads(_nwp[0])
                            if cur_nw in _nwp:
                                _nwp[cur_nw] += 10
                            else:
                                _nwp[cur_nw] = 10
                            __nwp = _nwp
                        elif _nwp:
                            __nwp = {cur_nw: 10}
                        else:
                            __nwp = {cur_nw: 10}
                            print('Cannot find '+user_id+' in database. Creating entry.')
                            self.dbq("INSERT INTO members (user_id) VALUES (?)", (user_id,))#verify guildie?
                        self.dbq("UPDATE members SET nwp = ? WHERE user_id = ?", (json.dumps(__nwp), user_id))
                        self.nw_num_members = num_members if (num_members > self.nw_num_members) else self.nw_num_members
                print('Parsed Members: '+str(self.nw_num_members))
                if len(self.md_runtimes) == 0:
                    print('last runtime')
                    duration_m = int(round((datetime.now()-datetime.now().replace(hour=17, minute=00)).total_seconds()/60))
                    self.dbq('INSERT INTO nodewars (nw_date, duration_minutes, num_members) VALUES (?,?,?)', (datetime.now().strftime('%d-%m-%Y'), duration_m, self.nw_num_members))
                    self.nw_num_members = 0
                    self.monitor_run = False
                    return None
        return None

    async def gmp_parse(self):
        """Updates members' guild mission participation."""
        lastgq = datetime.now()-timedelta(days=7)
        #self.dbq('INSERT INTO guildquests (last_parsed) VALUES (?)', (datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),))
        async for message in self.bot.logs_from(self.chans['guild_missions'], after=lastgq):
            for mention in message.mentions:
                _gmp = self.dbq('SELECT gmp FROM members WHERE user_id = ?', (str(mention.id),))
                if _gmp and _gmp[0] != None:#dont work
                    _gmp = json.loads(_gmp[0])
                    _gmp.append(datetime.strftime(message.timestamp, '%d-%m-%Y_%I:%M%p'))
                    __gmp = _gmp
                else:
                    __gmp = [datetime.strftime(message.timestamp, '%d-%m-%Y_%I:%M%p')]
                self.dbq('UPDATE members SET gmp = ? WHERE user_id = ?', (json.dumps(__gmp), str(mention.id)))
        await self.logger('Guild Mission participation parsed since: ' + datetime.strftime(lastgq, '%d-%m-%Y_%I:%M%p'), False)

##############################Events##############################
    @commands.command()
    async def create_test_event(self):
        self.dbq('DELETE FROM calendar WHERE eid = ?', ('test',))
        a = []
        for i in range(1,4):
            z = datetime.now()+timedelta(minutes=i)
            a.append(z.strftime('%Y-%m-%d %I:%M %p'))
        self.dbq('INSERT INTO calendar (eid, e_instance_id, event_type, date_time, title, imagesuff, location, reminders) VALUES (?,?,?,?,?,?,?,?)', ('test', '14549131', '756874', '2018-10-25 06:00 PM', 'Test Node War', 'jpg', 'Serendia', ','.join(a)))
        self.load_events()

    @commands.command()
    async def runevent(self):
        """Begin event notifier."""
        if self.event_run == False:
            await self.logger('Running Event Notifier...')
            self.event_run = True
            #self.future = asyncio.Future()
            asyncio.ensure_future(self.tick_event())
        else:
            self.event_run = False
            await self.logger('Shutting down Event Notifier...')

    @commands.command(pass_context=True, name='addchannel')
    async def addchannel(self, ctx, e_instance_id: str, channel: str):
        """Add a channel for an existing event."""
        if await self.chanroles(ctx):
                self.dbq('UPDATE calendar SET location = ? WHERE e_instance_id = ?', (channel, e_instance_id))
                await self.bot.say('Event ID ' + e_instance_id + ' has been updated with location: ' + channel)

    @commands.command(pass_context=True, name='calendar')
    async def calendar(self, ctx):
        if await self.chanroles(ctx):
            await self.refresh_calendar()

    async def refresh_calendar(self):
        """Updates database with calendar events from shivtr."""
        temp_instance_id = []
        n = datetime.now(timezone.utc)
        for event in self.month:
            if event.date_time < datetime.now():
                self.dbq('DELETE FROM calendar WHERE e_instance_id = ?', (event.e_instance_id,))
                self.month.remove(event)
            temp_instance_id.append(event.e_instance_id)
        user = '{"user":{"email":"haggard05@gmail.com","password":"password"}}'
        h = {"Content-Type": "application/json"}
        login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
        url = 'http://slowpoke.shivtr.com/events.json'
        auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
        e = requests.get(url, data=auth).json()
        eventsindex = e['events']
        eid = {}
        for z in eventsindex:
            e_id = str(z['event_id'])
            e_date = z['date']
            #Stupid datetime hack to account for extra colon
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
                if e['id'] not in temp_instance_id:
                    if eid[k]['event_category_id'] == '756874': #KAKAO CHANGE NW START TIME PLZ
                        e['date'] = e['date']-timedelta(hours=1)
                        print('nw')
                    print(e['date'].strftime('%Y-%m-%d %I:%M %p'))
                    Event(k, e['id'], eid[k]['event_category_id'], datetime.strftime(e['date'], '%Y-%m-%d %I:%M %p'), eid[k]['name'], eid[k]['imgsuff'], None, None, 1)
        await self.logger('Calendar has been parsed!', False)

    @commands.command(pass_context=True, name='weeklyoverview')#CANNOT SEND EMPTY MESSAGE
    async def weeklyoverview(self, ctx, month: str, start: str, end: str):
        """Posts an event overview in the #announcements channel."""
        if await self.chanroles(ctx):
            await self.bot.purge_from(self.chans['announcements'], limit=100)#announcements
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
            await self.bot.send_message(self.chans['announcements'], msg)#announcements
            await self.bot.send_message(self.chans['slowpokeonly'], '@Guildies #announcements has been updated with this weeks events! Get signed up for em!')
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

    def load_events(self):
        self.month = []
        print('Loading Events...')
        rows = self.dbq('SELECT * FROM calendar')
        for event in rows:
            self.month.append(Event(event[0], event[1], event[2], event[3], event[4], event[5], event[6], event[7], 0))

##############################Group##############################
    async def list_groups(self):
        if len(self.groups) > 0:
            for cur_group in self.groups:
                await self.bot.send_message(self.chans['botspam'], embed=cur_group.gen_embed())

    @commands.command(pass_context=True)
    async def group(self, ctx, *args):
        await self.bot.delete_message(ctx.message)
        await self.bot.purge_from(self.chans['botspam'], check=self.is_me)
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
                if args and len(args)>2 and args[1].startswith('('):
                    #!group create (Ser4) Test Group
                    if args[1].endswith(')'):
                        channel = str(args[1]).strip('(').strip(')')
                        group_n = str(' '.join(args[2:])) if len(args) >= 1 else None
                    #!group create (Serendia 4) Test Group
                    elif args[2] and args[2].endswith(')'):
                        channel = str(args[1].strip('(')+args[2].strip(')'))
                        group_n = str(' '.join(args[3:])) if len(args) >= 1 else None
                    if len(channel) == 0:
                        await self.logger('Please try again with the proper syntax: `!group create (channel) Group Name`')
                        return None
                    for cur_group in self.groups:
                        if author in cur_group.members:
                            await self.logger('You cannot create a group while you are in a group. Please leave your current group and try again. `!group leave`')
                            return None
                        elif group_n in self.groups:
                            await self.logger('A group with the name '+group_n+' already exists!')
                            return None
                    gid_temp = str(len(self.groups)+1)
                    self.groups.append(Group(group_n, author, gid_temp, channel, self.hex_colours[randrange(0, 19)]))
                    await self.logger(author+' has created group '+gid_temp+': '+group_n+' on '+channel)
                    await self.list_groups()
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
                        await self.list_groups()
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
                    await self.list_groups()
                else:
                    await self.logger('You are not in a group!')
                    # return None

            else:
                if len(self.groups) > 0:
                    await self.list_groups()
                    #for cur_group in self.groups:
                    #    await self.bot.send_message(ctx.message.channel, embed=cur_group.gen_embed())
                else:
                    await self.logger('There are no active groups to list!')

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
        self.embed.set_footer(text="Created at: "+datetime.now().strftime('%Y-%m-%d %I:%M %p'))
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
        self.event_icon = ':crossed_swords:' if self.event_type == '756874' or self.event_type == '756875' else ':pushpin:'
        #self.embed = discord.Embed(description=self.event_icon + ' __***' + self.title + '***__', color=0xed859a, inline=True)
        if processing:
            self.reminders = self.create_reminders()
            self.add()
        else:
            self.reminders = reminders.split(',')

    async def gen_embed(self):
        eventurl = 'http://slowpoke.shivtr.com/events/'+self.eid+'?event_instance_id='+self.e_instance_id
        self.embed = discord.Embed(description=self.event_icon + ' __***' + self.title + '***__', color=0xed859a, inline=True)
        self.embed.add_field(name=':alarm_clock: Time:', value=datetime.strftime(self.date_time, '%I:%M %p') + ' PT / ' + datetime.strftime(self.date_time+timedelta(hours=3), '%I:%M %p') + ' ET', inline=True)
        self.embed.add_field(name=':calendar_spiral: Date:', value=datetime.strftime(self.date_time, '%A, %B %d'), inline=True)
        self.embed.add_field(name=':pencil: Event Page:', value='[Don\'t forget to sign up!]('+eventurl+')', inline=True)
        self.embed.set_thumbnail(url='http://s3.mmoguildsites.com/s3/event_photos/'+self.eid+'/original.'+self.imagesuff)
        self.embed.set_footer(text="Created at: "+datetime.now().strftime('%Y-%m-%d %I:%M %p'))
        if self.event_type == '756874':
            self.embed.add_field(name=':globe_with_meridians: Location:', value=self.location+str(1) if self.location != 'TBD' else self.location, inline=True)
            self.embed.add_field(name=':shopping_cart: Items to Bring:', value='[List of buffs](https://goo.gl/yhCPzi), Emergency Medical Kits, 3xPolished Stone: Repair Tower, 15xCopper Shards & 30xIron Ingots: Barricade Upgrades')
            self.embed.add_field(name=':triangular_flag_on_post: Remember: ', value='Sign-ups must be done at least **1 hour in advance** to count for payout. If you are unable to attend, please let us know in the [comments on the event\'s page]('+eventurl+'#comments_new).', inline=False)
        return self.embed

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
