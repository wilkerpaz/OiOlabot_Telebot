import logging
import sys
import threading
from datetime import datetime, timedelta
from html import escape
from socket import gaierror
from time import sleep
from urllib.error import URLError

import schedule
import telebot
from decouple import config
from emoji import emojize
from flask import Flask, request, abort

from util.database import DatabaseHandler
from util.feedhandler import FeedHandler
from util.funcoes_telebot import envia_texto
from util.processing import BatchProcess

'''
-------------------------------------------------
======  Configurações                   =========
_________________________________________________

'''
# -------  Controle de log  -------

LOG = config('LOG')
logger = telebot.logger
telebot.logger.setLevel(logging.ERROR)

logging.basicConfig(format='%(asctime)s<%(threadName)s>%(name)s '
                           '(%(filename)s) %(levelname)s:%(lineno)d [%(funcName)] %(message)s')

log = logging.getLogger('OiOlabot')

log.setLevel(LOG)

# ===================================

# --------- DEV_MOD ---------------


if len(sys.argv) > 1:
    if sys.argv[1] == 'dev':
        DEV_MOD = True
        log.setLevel(LOG)
    else:
        if 'gunicorn' in sys.argv[0]:
            DEV_MOD = False
        else:
            print('argumento inválido! use "dev" ou "prod"')
            sys.exit()
else:
    if sys.argv[0] == 'uwsgi':
        DEV_MOD = False
    else:
        DEV_MOD = True
        log.setLevel(logging.DEBUG)

# =================================


'''
-------------------------------------------------
==============  Variáveis Globais  ==============
_________________________________________________

'''

ADMINS = ['26072030']  # Escreva a ID do seu Usuáro no telegram
USER_ADMINS = []

DB = config('DB_LD')
DEV_TOKEN = config('DEV_TOKEN_LD')  # Tokens do Bot de Desenvolvimento
PROD_TOKEN = config('PROD_TOKEN_LD')  # Tokens do Bot de Produção

if DEV_MOD:
    API_TOKEN = DEV_TOKEN
    log.debug("Bot Inicializado em modo DEV")
else:
    API_TOKEN = PROD_TOKEN

    WEBHOOK_HOST = 'ALGO.unasp.cf'  # no lugar de Algo, converse com o Neto para criar um subdomínio pro seu bot
    WEBHOOK_PORT = 443  # Precisa ser a porta correta, se não o webhook olha pro lugar errado

    WEBHOOK_URL_BASE = "https://%s:%s" % (WEBHOOK_HOST, WEBHOOK_PORT)
    WEBHOOK_URL_PATH = "/%s/" % (API_TOKEN)
    log.debug("Bot Inicializado em modo PROD")

help_text = 'Welcomes everyone that enters a group chat that this bot is a ' \
            'part of. By default, only the person who invited the bot into ' \
            'the group is able to change settings.\nCommands:\n\n' \
            '/welcome - Set welcome message\n' \
            '/goodbye - Set goodbye message\n' \
            '/disable\\_welcome - Disable the goodbye message\n' \
            '/disable\\_goodbye - Disable the goodbye message\n' \
            '/lock - Only the person who invited the bot can change messages\n' \
            '/unlock - Everyone can change messages\n' \
            '/quiet - Disable "Sorry, only the person who..." ' \
            '& help messages\n' \
            '/unquiet - Enable "Sorry, only the person who..." ' \
            '& help messages\n\n' \
            '/msg <msg> - To send message\n' \
            'You can use _$username_ and _$title_ as placeholders when setting' \
            ' messages. [HTML formatting]' \
            '(https://core.telegram.org/bots/api#formatting-options) ' \
            'is also supported.\n\n' \
            "Controls\n " \
            "/start - Activates the bot. If you have subscribed to RSS feeds, you will receive news from now on\n " \
            "/stop - Deactivates the bot. You won't receive any messages from the bot until you activate the bot again \
            using the start comand\n"
'''
-----------------------------------------------------------
======  Objetos Principais e Instâncias de Classes ========
___________________________________________________________
'''

# --------- Objeto do Bot ---------

bot = telebot.TeleBot(API_TOKEN, threaded=DEV_MOD)
db = DatabaseHandler(DB)
feed = BatchProcess(db=db, bot=bot)

# --------- Objeto do Flask -------

if not DEV_MOD:
    app = Flask(__name__)

'''
-----------------------------------------------------------
======  Rotas do Flask                             ========
___________________________________________________________
'''
if not DEV_MOD:
    # Empty webserver index, return nothing, just http 200
    @app.route('/', methods=['GET', 'HEAD'])
    def index():
        return "<h1 style='color:blue'>Hello There!</h1>"


    # Process webhook calls
    @app.route(WEBHOOK_URL_PATH, methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            log.debug("WebHook: Uptade Recebido.")
            bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
            return "!", 200
        else:
            abort(403)

'''
-------------------------------------------------
==============  Funções Internas  ===============
_________________________________________________

'''
help_text_feed = "RSS Management\n" \
                 "/addurl <url> - Adds a util subscription to your list. or\n" \
                 "/addurl @chanel <url> - Add url in Your chanel to receve feed. or\n" \
                 "/addurl @group <url> - Add url in Your group to receve feed.\n" \
                 "/listurl - Shows all your subscriptions as a list.\n" \
                 "/remove <url> - Removes an exisiting subscription from your list.\n" \
                 "/remove @chanel <url> - Removes url in Your chanel.\n" \
                 "/remove @group <url> - Removes url in Your group.\n" \
                 "Other\n" \
                 "/help - Shows the help menu  :)"

help_text = help_text + help_text_feed


def _check(update, override_lock=None):
    """
    Perform some hecks on the update. If checks were successful, returns True,
    else sends an error message to the chat and returns False.
    """
    chat_id = update.chat.id
    user_id = update.from_user.id

    if chat_id > 0:
        text = 'Please add me to a group first!'
        envia_texto(bot=bot, chat_id=chat_id, text=text)
        return False

    locked = override_lock if override_lock is not None \
        else bool(db.get_value_name_key('group:' + str(chat_id), 'chat_lock'))

    if locked and int(db.get_value_name_key('group:' + str(chat_id), 'chat_adm')) != user_id:
        if not bool(db.get_value_name_key('group:' + str(chat_id), 'chat_quiet')):
            text = 'Sorry, only the person who invited me can do that.'
            envia_texto(bot=bot, chat_id=chat_id, text=text)
        return False

    return True


# Welcome a user to the chat
def _welcome(update, member=None):
    """ Welcomes a user to the chat """
    chat_id = update.chat.id
    chat_title = update.chat.title
    first_name = member.first_name
    logger.info(f'{escape(first_name)} joined to chat {chat_id} ({escape(chat_title)})')

    # Pull the custom message for this chat from the database
    text_group = db.get_value_name_key('group:' + str(chat_id), 'chat_welcome')
    if not text_group:
        return

    # Use default message if there's no custom one set
    welcome_text = f'Hello $username! Welcome to $title {emojize(":grinning_face:")}'
    if text_group:
        text = welcome_text + '\n' + text_group

    # Replace placeholders and send message
    else:
        text = welcome_text

    # Replace placeholders and send message
    text = text.replace('$username', first_name).replace('$title', chat_title)
    envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


# Introduce the context to a chat its been added to
def _introduce(update):
    """
    Introduces the bot to a chat its been added to and saves the user id of the
    user who invited us.
    """
    me = bot.get_me()
    if me.username == 'LiturgiaDiaria_bot':
        _set_daily_liturgy(update)
        return

    chat_title = update.chat.title
    chat_id = update.chat.id
    first_name = update.from_user.first_name
    chat_name = ''.join('@' if update.chat.username or update.from_user.username
                        else update.from_user.first_name)
    user_id = update.from_user.id

    logger.info(f'Invited by {user_id} to chat {chat_id} ({escape(chat_title)})')

    db.update_group(chat_id=chat_id, chat_name=chat_name, chat_title=chat_title, user_id=user_id)

    text = f'Hello {escape(first_name)}! I will now greet anyone who joins this chat ({chat_title}) with a' \
           f' nice message {emojize(":grinning_face:")} \n\ncheck the /help command for more info!'
    envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


def _set_daily_liturgy(update):
    chat_id = update.chat.id
    chat_name = '@' + update.chat.username or '@' + update.from_user.username \
                or update.from_user.first_name
    chat_title = update.chat.title
    user_id = update.from_user.id
    url = 'http://feeds.feedburner.com/evangelhoddia/dia'
    text = 'You will receive the daily liturgy every day.\nFor more commands click /help'

    db.set_url_to_chat(chat_id=chat_id, chat_name=chat_name, url=url, user_id=user_id)
    envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')

    logger.info(f'Invited by {user_id} to chat {chat_id} ({escape(chat_title)})')


'''
-------------------------------------------------
==============  Funções De Interação   ==========
_________________________________________________

'''

'''
-------------------------------------------------
================== Comandos =====================
_________________________________________________

'''


@bot.message_handler(content_types=['new_chat_member'])
def all_update(u):
    print(u)


@bot.message_handler(commands=['start', 'entrar', 'iniciar', 'help'])
# Print help text
def start(update):
    """ Prints help text """
    me = bot.get_me()
    if me.username == 'LiturgiaDiaria_bot':
        _set_daily_liturgy(update)
        return

    chat_id = update.chat.id
    from_user = update.from_user.id

    if not bool(db.get_value_name_key('group:' + str(chat_id), 'chat_quiet')) \
            or str(db.get_value_name_key('group:' + str(chat_id), 'chat_adm')) == str(from_user):
        envia_texto(bot=bot, chat_id=chat_id, text=help_text, parse_mode='MARKDOWN', disable_web_page_preview=True)


@bot.message_handler(content_types=['new_chat_members'])
def new_chat_members(update):
    me = bot.get_me()
    for member in update.new_chat_members:
        if member.id == me.id:
            return _introduce(update)
        else:
            return _welcome(update, member)


@bot.message_handler(content_types=['left_chat_member'])
def left_chat_member(update):
    me = bot.get_me()
    member = update.left_chat_member
    if member.id == me.id:
        print(f'O bot foi removido do chat {update.chat.title}')
        return
    else:
        return goodbye(update)


# Welcome a user to the chat
def goodbye(update):
    """ Sends goodbye message when a user left the chat """
    chat_id = update.chat.id
    chat_title = update.chat.title
    first_name = update.left_chat_member.first_name

    logger.info(f'{escape(first_name)} left chat {chat_id} ({escape(chat_title)})')

    # Pull the custom message for this chat from the database
    text = db.get_value_name_key('group:' + str(chat_id), 'chat_goodbye')

    # Goodbye was disabled
    if text == 'False':
        return

    # Use default message if there's no custom one set
    if text is None:
        text = 'Goodbye, $username!'

    # Replace placeholders and send message
    text = text.replace('$username', first_name).replace('$title', chat_title)
    envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


@bot.message_handler(commands=['welcome'])
# Set custom message
def set_welcome(u):
    """ Sets custom welcome message """
    args = u.text[u.entities[0].length + 1:] if u.entities else None
    chat_id = u.chat.id

    # _check admin privilege and group context
    if not _check(u):
        return

    # Split message into words and remove mentions of the bot
    # set_text = r' '.join(args)

    # Only continue if there's a message
    if not args:
        text = 'You need to send a message, too! For example:\n' \
               '<code>/welcome The objective of this group is to...</code>'
        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')
        return

    # Put message into database
    db.set_name_key('group:' + str(chat_id), {'chat_welcome': args})
    envia_texto(bot=bot, chat_id=chat_id, text='Got it!', parse_mode='HTML')


@bot.message_handler(commands=['goodbye'])
# Set custom message
def set_goodbye(update):
    """ Enables and sets custom goodbye message """
    args = update.text[update.entities[0].length + 1:] if update.entities else None
    chat_id = update.chat.id

    # _check admin privilege and group context
    if not _check(update):
        return

    # Split message into words and remove mentions of the bot
    # set_text = ' '.join(args)

    # Only continue if there's a message
    if not args:
        text = 'You need to send a message, too! For example:\n' \
               '<code>/goodbye Goodbye, $username!</code>'
        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')
        return

    # Put message into database
    db.set_name_key('group:' + str(chat_id), {'chat_goodbye': args})
    envia_texto(bot=bot, chat_id=chat_id, text='Got it!', parse_mode='HTML')


@bot.message_handler(commands=['disable_welcome'])
def disable_welcome(update):
    """ Disables the goodbye message """
    command_control(update, 'disable_welcome')


@bot.message_handler(commands=['disable_goodbye'])
def disable_goodbye(update):
    """ Disables the goodbye message """
    command_control(update, 'disable_goodbye')


@bot.message_handler(commands=['lock'])
def lock(update):
    """ Locks the chat, so only the invitee can change settings """
    command_control(update, 'lock')


@bot.message_handler(commands=['unlock'])
def unlock(update):
    """ Unlocks the chat, so everyone can change settings """
    command_control(update, 'unlock')


@bot.message_handler(commands=['quiet'])
def quiet(update):
    """ Quiets the chat, so no error messages will be sent """
    command_control(update, 'quiet')


@bot.message_handler(commands=['unquiet'])
def unquiet(update):
    """ Unquiets the chat """
    command_control(update, 'unquiet')


def command_control(update, command):
    """ Disables the goodbye message """
    chat_id = update.chat.id

    # _check admin privilege and group context
    if _check(update):
        if command == 'disable_welcome':
            commit = db.set_name_key('group:' + str(chat_id), {'chat_welcome': 'False'})
        elif command == 'disable_goodbye':
            commit = db.set_name_key('group:' + str(chat_id), {'chat_goodbye': 'False'})
        elif command == 'lock':
            commit = db.set_name_key('group:' + str(chat_id), {'chat_lock': 'True'})
        elif command == 'unlock':
            commit = db.set_name_key('group:' + str(chat_id), {'chat_lock': 'False'})
        elif command == 'quiet':
            commit = db.set_name_key('group:' + str(chat_id), {'chat_quiet': 'True'})
        elif command == 'unquiet':
            commit = db.set_name_key('group:' + str(chat_id), {'chat_quiet': 'False'})
        else:
            commit = False
        if commit:
            envia_texto(bot=bot, chat_id=chat_id, text='Got it!', parse_mode='HTML')


# Avaliar esta função
def get_chat_by_username(update, user_name=None):
    get_chat = None
    try:
        if user_name:
            user_name = user_name if user_name[0] == '@' else '@' + str(user_name)
        chat_id = update.chat.id if user_name == '@this' else user_name
        get_chat = bot.get_chat(chat_id=chat_id)
    except telebot.apihelper.ApiException as e:
        if user_name:
            update.reply_text(f'I cant resolved username {user_name}')
        logger.warning(f"{e}")

    user = {}
    if get_chat:
        user.update({'id': str(get_chat.id) or None})
        user.update({'title': get_chat.title}) if get_chat.title \
            else user.update({'first_name': get_chat.first_name})
        user.update({'description': get_chat.description}) if get_chat.description \
            else user.update({'last_name': get_chat.last_name})
        user.update({'username': '@' + get_chat.username if get_chat.username else None})

    return user if get_chat else None


def get_user_info(update):
    user_id = update.from_user.id
    chat_id = update.chat.id
    args = update.text[update.entities[0].length + 1:].split(' ') if update.entities else None
    command = update.text[1:update.entities[0].length] or None

    if args:
        user_input = args[0]
        get_chat = get_chat_by_username(update, user_name=user_input) if user_input else None

    else:
        get_chat = get_chat_by_username(update, user_name=user_id)

    if get_chat:
        text = '\n'.join(f'{k}: {v}' for k, v in get_chat.items())

        if text and command == 'me':
            envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


def get_id(update):
    args = update.text[update.entities[0].length + 1:] if update.entities else None
    from_user = update.from_user
    chat_id = update.chat.id

    if str(args[0])[:1] == '@':
        id_user = args

    elif not str(args[0]).find('/') < 0:
        id_user = '@' + str(args).split('/')[-1]
    else:
        id_user = '@' + str(args)
    try:
        get_id_user = bot.get_chat(chat_id=id_user)
    except telebot.apihelper.ApiException as e:
        error(e)
        return None

    if get_id_user:
        return {'user_id': get_id_user['id'], 'user_name': "@" + str(get_id_user['username'])}

    else:
        text = "Sorry, " + from_user.first_name + \
               "! I already have that group name " + id_user + " with stored in your subscriptions."
        envia_texto(bot=bot, chat_id=chat_id, text=text)
        return None


def feed_url(update, url, **chat_info):
    arg_url = FeedHandler.format_url_string(string=url)
    chat_id = update.chat.id

    # _check if argument matches url format
    if not FeedHandler.is_parsable(url=arg_url):
        text = "Sorry! It seems like '" + \
               str(arg_url) + "' doesn't provide an RSS news feed.. Have you tried another URL from that provider?"
        envia_texto(bot=bot, chat_id=chat_id, text=text)
        return
    chat_id = chat_info['chat_id']
    chat_name = chat_info.get('chat_name')
    user_id = update.from_user.id

    result = db.set_url_to_chat(
        chat_id=str(chat_id), chat_name=str(chat_name), url=url, user_id=str(user_id))

    if result:
        text = "I successfully added " + arg_url + " to your subscriptions!"
    else:
        text = "Sorry, " + update.from_user.first_name + \
               "! I already have that url with stored in your subscriptions."
    envia_texto(bot=bot, chat_id=chat_id, text=text)


@bot.message_handler(commands=['addurl'])
def add_url(update):
    """
    Adds a rss subscription to user
    """
    args = update.text[update.entities[0].length + 1:].split(' ') if update.entities else None
    chat_id = update.chat.id

    # _check admin privilege and group context
    if chat_id < 0:
        if not _check(update):
            return

    text = "Sorry! I could not add the entry! " \
           "Please use the the command passing the following arguments:\n\n " \
           "<code>/addurl url</code> or \n <code>/addurl username url</code> \n\n Here is a short example: \n\n " \
           "/addurl http://www.feedforall.com/sample.xml \n\n" \
           "/addurl @username http://www.feedforall.com/sample.xml "

    if len(args) > 2 or not args:
        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')
        return

    elif len(args) == 2:
        chat_name = args[0]
        url = args[1]
        chat_info = get_chat_by_username(update, chat_name)
        text = "I don't have access to chat " + chat_name + '\n' + text
        if chat_info is None:
            update.reply_text(text=text, quote=False)
        else:
            chat_info = {'chat_id': chat_info['id'], 'chat_name': chat_info['username']}
            feed_url(update, url, **chat_info)

    else:
        url = args[0]
        user_name = '@' + update.chat.username if update.chat.username else None
        first_name = update.from_user.first_name if update.from_user.first_name else None
        chat_title = update.chat.title if update.chat.title else None

        chat_name = user_name or chat_title or first_name
        user_id = update.from_user.id
        chat_info = {'chat_id': chat_id, 'chat_name': chat_name, 'user_id': user_id}

        feed_url(update, url, **chat_info)


@bot.message_handler(commands=['listurl'])
def list_url(update):
    """
    Displays a list of all user subscriptions
    """
    user_id = update.from_user.id
    chat_id = update.chat.id

    # _check admin privilege and group context
    if chat_id < 0:
        if not _check(update):
            return

    text = "Here is a list of all subscriptions I stored for you!"
    envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')

    urls = db.get_chat_urls(user_id=user_id)
    for url in urls:
        url = (str(url['chat_name']) + ' ' if url['chat_name'] and int(url['chat_id']) < 0 else '') + url['url']
        text = '<code>/removeurl ' + url + '</code>'
        # update.reply_text(message)
        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


@bot.message_handler(commands=['allurl'])
def all_url(update):
    """
    Displays a list of all user subscriptions
    """
    chat_id = update.chat.id

    # _check admin privilege and group context
    if chat_id < 0:
        if not _check(update):
            return

    text = "Here is a list of all subscriptions I stored for you!"
    envia_texto(bot=bot, chat_id=chat_id, text=text)

    urls = db.get_urls_activated()
    for url in urls:
        last_update = db.get_update_url(url)
        text = 'last_update: ' + last_update['last_update'] + '\n\n' \
               + 'last_url: <code>' + last_update['last_url'] + '</code>\n\n' \
               + 'url: <code>' + last_update['url'] + '</code>'

        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


@bot.message_handler(commands=['removeurl'])
def remove_url(update):
    """
    Removes an rss subscription from user
    """
    args = update.text[update.entities[0].length + 1:].split(' ') if update.entities else None
    chat_id = update.chat.id

    text = "Sorry! I could not remove the entry! " \
           "Please use the the command passing the following arguments:\n\n " \
           "<code>/removeurl url</code> or \n <code>/removeurl username url</code> \n\n " \
           "Here is a short example: \n\n " \
           "/removeurl http://www.feedforall.com/sample.xml \n\n" \
           "/removeurl @username http://www.feedforall.com/sample.xml "

    if len(args) > 2 or not args:
        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')
        return

    user_id = update.from_user.id
    chat_name = args[0] if len(args) == 2 else update.from_user.first_name
    logger.error(f'remove_url {str(user_id)} {chat_name}')
    chat_id = db.get_chat_id_for_chat_name(user_id, chat_name) if chat_name else update.chat.id
    url = args[1] if len(args) == 2 else args[0]

    if chat_id is None:
        text = "Don't exist chat " + chat_name + '\n' + text
        envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')
    else:
        exist_url = db.exist_url_to_chat(user_id, chat_id, url)
        if not exist_url:
            chat_name = chat_name or update.from_user.first_name
            text = "Don't exist " + url + " for chat " + chat_name + '\n' + text
            envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')
            result = None
        else:
            result = True if db.del_url_for_chat(chat_id, url) else None

        if result:
            text = "I removed " + url + " from your subscriptions!"
        else:
            text = "I can not find an entry with label " + \
                   url + " in your subscriptions! Please check your subscriptions using " \
                         "/listurl and use the delete command again!"
        envia_texto(bot=bot, chat_id=chat_id, text=text)

    names_url = db.find_names(url)
    print(names_url)
    if len(names_url) == 1:
        db.del_names(names_url)


@bot.message_handler(commands=['getkey'])
def get_key(update):
    args = update.text[update.entities[0].length + 1:].split(' ') if update.entities else None
    chat_id = update.chat.id
    if len(args) == 1:
        keys = db.find_names(args[0])
        for k in keys:
            text = str('<code>/removekey ' + str(k) + '</code>')
            envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


@bot.message_handler(commands=['removekey'])
def remove_key(update):
    args = update.text[update.entities[0].length + 1:].split(' ') if update.entities else None
    chat_id = update.chat.id
    text = 'I removed '
    if len(args) == 1:
        key = args[0]
        if db.redis.delete(args[0]) == 1:
            text = text + key
            envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


@bot.message_handler(commands=['stop'])
def stop(update):
    """
    Stops the bot from working
    """
    chat_id = update.chat.id

    # _check admin privilege and group context
    if chat_id < 0:
        if not _check(update):
            return

    text = "Oh.. Okay, I will not send you any more news updates! " \
           "If you change your mind and you want to receive messages " \
           "from me again use /start command again!"
    envia_texto(bot=bot, chat_id=chat_id, text=text, parse_mode='HTML')


def error(e):
    """ Error handling """
    logger.warning(f"def error {e}")


'''
-------------------------------------------------
================   Entradas   ===================
_________________________________________________

'''

'''
-----------------------------------------------------------
======  Funções Finais                             ========
___________________________________________________________
'''

# Remove webhook
bot.remove_webhook()

if not DEV_MOD and __name__ != "__main__":
    sleep(0.1)
    # Set webhook
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
    log.info(" bot Iniciado em modo Produção")
    for admin in ADMINS:
        bot.send_message(admin, 'Bot Iniciado no servidor', parse_mode='HTML')


def loop_parse():
    feed.run()
    at_loop_parse = str((datetime.now() + timedelta(seconds=15)).strftime('%H:%M:%S'))
    schedule.every().day.at(at_loop_parse).do(run_threaded, loop_parse)


def run_bot(restart=None):
    if restart:
        log.info("restart bot")
        sleep(3)
        if bot.get_me():
            loop_parse()
    log.info("start bot")
    schedule.clear('run_bot')
    bot.polling(none_stop=False)


def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()


# Start Bot
if __name__ == "__main__":
    if DEV_MOD:
        try:
            at = str((datetime.now() + timedelta(seconds=1)).strftime('%H:%M:%S'))
            schedule.every().days.at(at).do(run_threaded, run_bot).tag('run_bot')
            loop_parse()

            while 1:
                schedule.run_pending()
                sleep(0.01)
        except KeyboardInterrupt as e:
            feed.stop()
            bot.stop_bot()
        except URLError as e:
            print('####urllib.error.URLError', e)
            run_bot(restart=True)
        except gaierror as e:
            print('####GAIERROR', e)
            run_bot(restart=True)

    else:
        print('''
        \n O Bot está configurado para rodar com uWSGI ou Gunicorn\n 
        veja as configuraçoes de wsgi.py e rode:\n
        uwsgi --socket 0.0.0.0:8001 --protocol=http -w wsgi \n\n 
        Isso irá rodar o Flask, mas não funcionará o webhooks se não
        estiver configurado o uWSGI e o Nginx no servidor https
        ''')
