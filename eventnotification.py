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
from lxml.etree import tostring
import os
#strftime = string/strptime = obj
#remove expired data from nwp/nws
class EventNotification:
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\slowpoke.db' #?mode=rw
        self.month = [] #List of loaded events
        self.createtables() #Creates SQLite tables if they do not exist.
        self.load_events() #Loads events from database to self.month
        self.monitor_states = {
            'monitor_run': False,
            'reminders_sent': False,
            'rsvp_cutoff': False,
            'manual_stop': False
        }
        #self.monitor_run = False #Am I currently monitoring Discord voice channels?
        self.md_runtimes = [] #Populated by runmonitor. List of times to take voice channel snapshots.
        self.nw_num_members = 0 #Number of guildies that attended last NW
        self.server = ''
        self.id = '336274317962772483' #Bot's ID
        self.hex_colours = [0x1abc9c, 0x16a085, 0x2ecc71, 0x27ae60, 0x3498db, 0x2980b9, 0x9b59b6, 0x8e44ad, 0x34495e, 0x2c3e50, 0xf1c40f, 0xf39c12, 0xe67e22, 0xd35400, 0xe74c3c, 0xc0392b, 0xecf0f1, 0xbdc3c7, 0x95a5a6, 0x7f8c8d] #a e s t h e t i c 
        self.groups = [Group('Static test group', 'NotVoytek', '1', 'Ser4', self.hex_colours[randrange(0, 19)])]
        self.tasks = {#make manual commands too
            'refresh_cal': datetime.now()+timedelta(hours=4),
            'refresh_members': datetime.now()+timedelta(hours=5),
            'backup_db': datetime.now()+timedelta(days=1)
        }
        self.chans = {}
        self.clear = clear = lambda: os.system('cls')
        asyncio.ensure_future(self.tick())

##############################General##############################
    @asyncio.coroutine
    def tick(self):
        yield from self.getserver()
        while True:
            now = datetime.now()
            #print('tick')
            #Monitors event reminders and sends notifications
            for event in self.month:
                #if len(event.reminders) >= 1:
                if event.event_type == '756874':
                    #THESE ARE RESET ON BOT RESTART, WILL SEND DUPLICATE REMINDERS
                    if event.date_time-timedelta(minutes=90) <= now and self.monitor_states['reminders_sent'] == False:#90
                        self.monitor_states['reminders_sent'] = True
                        print('sent reminders')
                        #yield from self.website_signups(event, True)#send reminder dms 30 min before cutoff, update characters before this
                    elif event.date_time-timedelta(minutes=60) <= now and self.monitor_states['rsvp_cutoff'] == False:#60
                        self.monitor_states['rsvp_cutoff'] = True
                        print('recorded rsvp')
                        yield from self.website_signups(event)#record rsvp @ 1hr cutoff
                    elif event.date_time <= now and self.monitor_states['monitor_run'] == False:
                        if event.date_time <= now <= event.date_time+timedelta(minutes=2):
                        #if True:
                            self.monitor_states['monitor_run'] = True
                            start = datetime.now()
                            print('Running monitor...')
                            for x in range(13):
                                self.md_runtimes.append(start+timedelta(minutes=(x)))#every 10 min
                                #self.md_runtimes.append(start+timedelta(minutes=(x*10)))#every 10 min
                        else:
                            self.month.remove(event)
                            self.md_runtimes = []
                            self.dbq('DELETE FROM calendar WHERE e_instance_id = ?', (event.e_instance_id,))
                            self.monitor_states = {
                                'monitor_run': False,
                                'reminders_sent': False,
                                'rsvp_cutoff': False
                            }
                if event.reminders and event.reminders[0]:
                    for reminder in event.reminders:
                        reminder_datetime = datetime.strptime(reminder, '%Y-%m-%d %I:%M %p')
                        if reminder_datetime > reminder_datetime+timedelta(hours=1):
                            event.rem_reminder(reminder)
                        if reminder_datetime < reminder_datetime+timedelta(hours=1):
                            if reminder_datetime < now: #still sending 2 reminders
                                em = yield from event.gen_embed()
                                #if event.event_type == '756874':
                                    #yield from self.bot.send_message(self.chans['slowpokeonly'], discord.utils.get(self.server.roles, name='Guildies').mention, embed=em)#slowpokeonly
                                    #yield from self.bot.send_message(self.chans['botspam'], 'Role Mentioned Here', embed=em)#slowpokeonly
                                #else:
                                    #yield from self.bot.send_message(self.chans['slowpokeonly'], 'Event Reminder:', embed=em)#slowpokeonly
                                print('sent notification')
                                event.rem_reminder(reminder)
            for task in self.tasks:
                if self.tasks[task] < now and self.monitor_states['monitor_run'] == False:
                    if task == 'refresh_cal':
                        self.tasks['refresh_cal'] = datetime.now()+timedelta(hours=4)
                        yield from self.refresh_calendar()
                        yield from self.logger('Calendar refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_cal'], '%Y-%m-%d %I:%M %p'), False)
                        print('Calendar refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_cal'], '%Y-%m-%d %I:%M %p'))
                    elif task == 'refresh_members':
                        self.tasks['refresh_members'] = datetime.now()+timedelta(hours=5)
                        yield from self.parsemembers()
                        yield from self.logger('Members refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_members'], '%Y-%m-%d %I:%M %p'), False)
                        print('Members refreshed. Next scheduled: ' + datetime.strftime(self.tasks['refresh_members'], '%Y-%m-%d %I:%M %p'))
                    elif task == 'backup_db':
                        self.tasks['backup_db'] = datetime.now()+timedelta(days=1)
                        yield from self.backup_db()
                        yield from self.logger('Database backed up. Next scheduled: ' + datetime.strftime(self.tasks['backup_db'], '%Y-%m-%d %I:%M %p'), False)
                        print('Database backed up. Next scheduled: ' + datetime.strftime(self.tasks['backup_db'], '%Y-%m-%d %I:%M %p'))
            if len(self.md_runtimes)>0:#self.monitor_states['monitor_run']:
                asyncio.ensure_future(self.monitordiscord(event))
            #self.clear()
            print('['+now.strftime('%I:%M:%S%p %d-%m-%Y')+']: Running...')
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
            'botspam': discord.utils.get(self.server.channels, id='375873904075472897'),
            'slowpoke-bot-help': discord.utils.get(self.server.channels, id='379685284796825601')
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

    @commands.command()
    async def task(self, *args):
        if args:
            if args[0] == 'calendar':
                self.tasks['refresh_cal'] = datetime.now()
            elif args[0] == 'members':
                self.tasks['refresh_members'] = datetime.now()
            elif args[0] == 'database':
                self.tasks['backup_db'] = datetime.now()

##############################Database##############################
    # @commands.command(pass_context=True)
    # async def testing(self, ctx):
    #     print(ctx.message.author.id)

    # @commands.command()
    # async def get_offline_members(self):
    #     await self.bot.request_offline_members(self.server)
    #     with open('W:\\Development\\Red-DiscordBot\\data\\Slowpoke\\members.txt', 'a', encoding='utf8') as memberfile:
    #         for member in self.server.members:
    #             if 'Guildies' in [str(i) for i in member.roles]:
    #                 memberfile.write(member.display_name+','+str(member)+'\n')
    #     print('done')

    async def members_csv(self):
        await self.gmp_parse()
        cur_nw = datetime.now().strftime("%d-%m-%Y")
        print(cur_nw)
        cur_nw_length = self.dbq('SELECT duration_minutes FROM nodewars WHERE nw_date = ?', (cur_nw,))
        path = 'C:\\Users\\eigengrau\\Google Drive\\Slowpoke_Data\\'+cur_nw+'_participation.csv'
        open(path, 'w', encoding='utf8').close()
        with open(path, 'a', encoding='utf8') as members_csv:
            members_csv.write('Family Name,Node War Participation,Node War Signup Status,Guild Mission Participation\n')
            members = self.dbq('SELECT * FROM members')
            m = ''
            for member in members:
                if member[2] != None:
                    nwp = json.loads(member[2])
                    duration_attended = round(100*(int(nwp[cur_nw])*10)/int(cur_nw_length[0]))
                    print('duration_attended')
                    print(duration_attended)
                    m += member[0] if member[0] else ""+','+cur_nw+': '+str(duration_attended)+'%,'+json.loads(member[4]).replace(',','|') if member[4] else ""+','+json.loads(member[3]) if member[3] else ""+'\n'
            members_csv.write(m)
            print('Uploaded CSV...')
        #         for x in range(0,5):
        #             m_temp += member[x].replace(',','|')+',' if member[x] else ','
        #         members_csv.write(m_temp+'\n')
        # await self.bot.send_file(ctx.message.author, path)

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
        discord_guildies = list(filter(lambda x: 'Guildies' in [str(i) for i in x.roles], self.server.members))
        db_guildies = list(map(lambda x: str(x[1]), self.dbq('SELECT * FROM members')))
        #If user id exists in database but not in current list of @Guildies, remove them
        user = '{"user":{"email":"email","password":"password"}}'
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
            if db_g not in list(map(lambda z: str(z.id), discord_guildies)):
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
                cur.execute("CREATE TABLE IF NOT EXISTS calendar (eid text, e_instance_id text, event_type text, date_time text, title text, imagesuff text, reminders text)")
                cur.execute("CREATE TABLE IF NOT EXISTS members (family text, user_id text, nwp text, gmp text, nws text, characters text)")
                cur.execute("CREATE TABLE IF NOT EXISTS nodewars (nw_date text, duration_minutes int, num_members int)")
                #cur.execute("CREATE TABLE IF NOT EXISTS guildquests (last_parsed text)")
                #cur.execute("CREATE TABLE IF NOT EXISTS groups (group_n text, group_m text, created_at text, last_updated text, active text, id integer primary key)")
        except Error as e:
            print(e)
            self.logger(e, False)

    async def website_signups(self, event, reminder=False):#fix
        user = '{"user":{"email":"email","password":"password"}}'
        h = {"Content-Type": "application/json"}
        login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
        #url = 'http://slowpoke.shivtr.com/events/'+event.eid+'?event_instance_id='+event.e_instance_id+'&view=status'
        url = 'http://slowpoke.shivtr.com/events/835132?event_instance_id=14588437&view=status'
        auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
        tree = html.fromstring(requests.get(url, data=auth).content)
        rsvp = {
            'attending': list(map(lambda x: x.text, tree.xpath('//*[@id="status_yes"]')[0].find_class('member_link'))),
            'maybe': list(map(lambda x: x.text, tree.xpath('//*[@id="status_maybe"]')[0].find_class('member_link'))),
            'declined': list(map(lambda x: x.text, tree.xpath('//*[@id="status_declined"]')[0].find_class('member_link')))
        }
        rsvp_ids = []
        for rsvp_status in rsvp:
            for char in rsvp[rsvp_status]:
                if rsvp_status == 'declined':
                    _m = self.dbq('SELECT * FROM members WHERE family LIKE ?', ('%'+char+'%',))
                else:
                    _m = self.dbq('SELECT * FROM members WHERE characters LIKE ?', ('%'+char+'%',))
                m = _m[0] if _m else False
                if m:
                    print(rsvp_status+': '+char)
                    rsvp_ids.append(m[1])
                    if reminder == False:
                        if m[4] != None:
                            nws = json.loads(m[4])
                            nws[event.date_time.strftime('%d-%m-%Y')] = str(rsvp_status)
                        else:
                            nws = {event.date_time.strftime('%d-%m-%Y'): str(rsvp_status)}
                        self.dbq('UPDATE members SET nws = ? WHERE user_id = ?', (json.dumps(nws), m[1]))
                else:
                    print(char+' not found!!')
        if reminder:
            eventurl = 'http://slowpoke.shivtr.com/events/'+event.eid+'?event_instance_id='+event.e_instance_id
            em = discord.Embed(description='Node War Sign Up Cutoff in 30 Minutes!', color=0xed859a, inline=False)#0xed859a
            em.add_field(name=':clipboard: Sign Up Here: ', value='['+eventurl+']('+eventurl+')', inline=False)
            em.add_field(name=':triangular_flag_on_post: Remember: ', value='Sign-ups must be done at least **1 hour in advance** to count for payout. If you are unable to attend, please let us know in the [comments on the event\'s page]('+eventurl+'#comments_new).', inline=False)
            em.set_thumbnail(url='https://i.imgur.com/zd4QPv4.jpg')
            em.set_footer(text="Created at: "+datetime.now().strftime('%Y-%m-%d %I:%M %p'))
            print('Sending cutoff reminders...')
            db_members = self.dbq('SELECT * FROM members')
            for member in db_members:
                if member[1] not in rsvp_ids:
                    print(member[0])
                    #await self.bot.send_message(discord.utils.get(self.server.members, id=member[1]), embed=em)
        else:
            print('Recording RSVP status...')

##############################Monitoring##############################
    @commands.command(pass_context=True)
    async def stop_monitor(self, ctx):
        print('Ending Discord monitor...')
        self.monitor_states['manual_stop'] = True
        self.md_runtimes = [datetime.now()]

    async def monitordiscord(self, event):#when !stop_monitor is called, an extra 10 minutes are added. fix this.
        #self.dbq('UPDATE members SET nwp = NULL')
        #self.dbq('UPDATE members SET nws = NULL')
        #self.dbq('UPDATE members SET gmp = NULL')
        temp_time = datetime.now().strftime('%I:%M%p %d-%m-%Y')
        print('['+temp_time+']: Monitoring Discord...')
        for t in self.md_runtimes:
            if t <= datetime.now():
                self.md_runtimes.remove(t)
                now = datetime.now().strftime('%d-%m_%H:%M')
                cur_nw = datetime.now().strftime('%d-%m-%Y')
                print('['+temp_time+']: Snapshot')
                #Retrieve list of members currently in applicable voice channels
                voice_connected_members = list(self.voice_chans['offense'].voice_members) + list(self.voice_chans['defense'].voice_members) + list(self.voice_chans['bdo_hangout'].voice_members)
                num_members = 0
                for usr in voice_connected_members:
                    if 'Guildies' in [str(i) for i in usr.roles]:# and str(usr.status) != 'idle'idle
                        num_members += 1
                        user_id = str(usr.id)
                        _nwp = self.dbq("SELECT nwp FROM members WHERE user_id = ?", (user_id,))
                        if _nwp[0] != None:
                            _nwp = json.loads(_nwp[0])
                            if cur_nw in _nwp:
                                _nwp[cur_nw] += 1 if self.monitor_states['manual_stop'] == False else 0
                            else:
                                _nwp[cur_nw] = 0
                            __nwp = _nwp
                        elif _nwp:
                            __nwp = {cur_nw: 0}
                        else:
                            __nwp = {cur_nw: 0}
                            print('Cannot find '+user_id+' in database. Creating entry.')
                            self.dbq("INSERT INTO members (user_id) VALUES (?)", (user_id,))#verify guildie?
                        self.dbq("UPDATE members SET nwp = ? WHERE user_id = ?", (json.dumps(__nwp), user_id))
                        self.nw_num_members = num_members if (num_members > self.nw_num_members) else self.nw_num_members
                print('Parsed Members: '+str(self.nw_num_members))
                if len(self.md_runtimes) == 0:
                    print('last runtime')
                    duration_m = int(round((datetime.now()-datetime.now().replace(hour=18, minute=00)).total_seconds()/60))
                    self.dbq('INSERT INTO nodewars (nw_date, duration_minutes, num_members) VALUES (?,?,?)', (datetime.now().strftime('%d-%m-%Y'), duration_m, self.nw_num_members))
                    self.nw_num_members = 0
                    self.monitor_states['monitor_run'] = False
                    self.month.remove(event)
                    self.dbq('DELETE FROM calendar WHERE e_instance_id = ?', (event.e_instance_id,))
                    self.monitor_states['manual_stop'] == False
                    await self.members_csv()
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
        self.dbq('INSERT INTO calendar (eid, e_instance_id, event_type, date_time, title, imagesuff, reminders) VALUES (?,?,?,?,?,?,?)', ('test', '14633725', '756874', '2018-10-25 06:00 PM', 'Test Node War', 'jpg', 'Serendia', ','.join(a)))
        self.load_events()

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
        user = '{"user":{"email":"email","password":"password"}}'
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
                if e['id'] not in temp_instance_id:
                    Event(k, e['id'], eid[k]['event_category_id'], datetime.strftime(e['date'], '%Y-%m-%d %I:%M %p'), eid[k]['name'], eid[k]['imgsuff'], None, 1)
        await self.logger('Calendar has been parsed!', False)

    @commands.command(pass_context=True)
    async def listall(self, ctx):
        """Lists all events in database."""
        if await self.chanroles(ctx):
            self.month = []
            self.load_events()
            embed = discord.Embed(description=' __***Upcoming Events***__', color=0xed859a)
            for event in self.month:
                embed.add_field(name='Event ID: ' + event.e_instance_id, value='__' + event.title + '__: ' + event.date_time_str, inline=True)
            await self.bot.say('@here', embed=embed)

    def load_events(self):
        self.month = []
        print('Loading Events...')
        rows = self.dbq('SELECT * FROM calendar')
        for event in rows:
            self.month.append(Event(event[0], event[1], event[2], event[3], event[4], event[5], event[6], 0))

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

    # @commands.command()
    # async def nw_groups(self):
    #     try:
    #         print('nw_groups')
    #         user = '{"user":{"email":"email","password":"password"}}'
    #         h = {"Content-Type": "application/json"}
    #         login_url = 'http://slowpoke.shivtr.com/users/sign_in.json'
    #         url = 'http://slowpoke.shivtr.com/events/837506?event_instance_id=14633775&view=groups'
    #         auth = {'auth_token': requests.post(login_url, data=user, headers=h).json()['user_session']['authentication_token']}
    #         tree = html.fromstring(requests.get(url, data=auth).content)
    #         #x = tree.xpath('//*[@id="signup_content"]/table')[0].find_class('mar_right').find_class('table_header')
    #         foo = tree.xpath('//*[@id="signup_content"]')
    #         print(tostring(foo))
    #         # for x in foo:
    #         #     print(x)
    #     except Error as e:
    #         print(e)

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
        self.embed.add_field(name='Created: ', value=self.created_at, inline=True)
        self.embed.add_field(name='Last Updated: ', value=self.last_updated, inline=True)
        self.embed.set_thumbnail(url='https://i.imgur.com/TtzKLel.png')
        self.embed.set_footer(text="Created at: "+datetime.now().strftime('%Y-%m-%d %I:%M %p'))
        return self.embed

class Event:

    def __init__(self, eid, e_instance_id, event_type, date_time, title, imagesuff, reminders, processing):
        self.date_time = datetime.strptime(date_time, '%Y-%m-%d %I:%M %p')
        self.date_time_str = date_time
        self.title = title
        self.imagesuff = imagesuff
        self.event_type = event_type
        self.eid = eid
        self.e_instance_id = e_instance_id
        self.event_icon = ':crossed_swords:' if self.event_type == '756874' or self.event_type == '756875' else ':pushpin:'
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
                cur.execute("INSERT INTO calendar (eid, e_instance_id, event_type, date_time, title, imagesuff, reminders) VALUES (?,?,?,?,?,?,?)", (self.eid, self.e_instance_id, self.event_type, self.date_time_str, self.title, self.imagesuff, ','.join(self.reminders)))
        except Error as e:
            print(e)

    def create_reminders(self):
        if self.event_type == '756874':
            return [
                (self.date_time - timedelta(hours=22)).strftime('%Y-%m-%d %I:%M %p'),
                (self.date_time - timedelta(hours=5)).strftime('%Y-%m-%d %I:%M %p')
            ]
        else:
            return [(self.date_time - timedelta(hours=3)).strftime('%Y-%m-%d %I:%M %p')]

def setup(bot):
    bot.add_cog(EventNotification(bot))
