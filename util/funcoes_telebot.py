import logging
import time

import telebot
from telebot import types

# -------  Controle de log  -------

logger = telebot.logger
telebot.logger.setLevel(logging.INFO)

logging.basicConfig(format='%(asctime)s<%(threadName)s>%(name)s '
                           '(%(filename)s) %(levelname)s:%(lineno)d [%(funcName)-15.15s] %(message)s')

log = logging.getLogger('OiOlabot')

log.setLevel(logging.INFO)

'''
-------------------------------------------------
==============  Funções de Menus  ===============
_________________________________________________

'''


def gera_menu(itens, colunas=3, tipo='padrao'):
    'Função Interna. Sem documentação'
    log.debug("uid:----- Inicio Gera menu")
    log.debug("uid:----- Menu tipo %s", tipo)
    if tipo is 'padrao':
        if len(itens) < colunas:
            colunas = len(itens)
        menu = types.ReplyKeyboardMarkup(row_width=colunas)
        botoes = [types.KeyboardButton(item) for item in itens]
        lista_botoes = ['botoes[%d]' % i for i in range(len(botoes))]
        comando = 'menu.add(' + ', '.join(lista_botoes) + ')'
        eval(comando)
        return menu

    elif tipo is 'inline':
        menu = types.InlineKeyboardMarkup(row_width=colunas)
        botoes = [types.InlineKeyboardButton(
            item, callback_data=item) for item in itens]
        lista_botoes = ['botoes[%d]' % i for i in range(len(botoes))]
        comando = 'menu.add(' + ', '.join(lista_botoes) + ')'
        eval(comando)
        return menu

    elif tipo is 'inline_id':
        menu = types.InlineKeyboardMarkup(row_width=colunas)
        botoes = [types.InlineKeyboardButton(item,
                                             callback_data=str(i)) for i, item in enumerate(itens)]
        lista_botoes = ['botoes[%d]' % i for i in range(len(botoes))]
        comando = 'menu.add(' + ', '.join(lista_botoes) + ')'
        eval(comando)
        return menu

    log.error("uid:----- tipo de menu não suportado")
    return []


def remove_menu(bot, chat_id, text):
    'Remove menu tipo "padrao" e envia mensagem\n\n\
    Use:\n\
    remove_menu(bot, chat_id, text, bot)\n\
    chat_id*    - int             -  id do chat (mesmo id do usuário)\n\
    texto*      - str             -  texto enviado após a remoção do menu\n\
    bot  - telebot Object  -  objeto do bot"\n\n\
                       *obrigatório'
    try:
        log.debug("uid:" + str(chat_id)[-5:] + " remove menu e envia texto")
        bot.send_message(
            chat_id, text, parse_mode='HTML', reply_markup=types.ReplyKeyboardRemove())
        return True

    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        return False


'''
-------------------------------------------------
==============  Funções Externas  ===============
_________________________________________________

'''


# def envia_texto(bot, chat_id, text, parse_mode=None, disable_web_page_preview=None, funcao_trata=''):

def envia_texto(bot, chat_id, text, funcao_trata='', **kwargs):
    'Envia mensagem de texto ou pergunta\n\n\
    Use:\n\
    envia_texto(bot, chat_id, text, funcao_trata, bot)\n\
    chat_id*      - int  -  id do chat (mesmo id do usuário)\n\
    texto*        - str  -  texto a ser enviado\n\
    funcao_trata  - str  -  Função que vai tratar a resposta caso seja uma pergunta"\n\
    bot    - obj  -  objeto do bot"\n\n\
                       *obrigatório'
    try:
        log.debug("uid:" + str(chat_id)[-5:] + " envia texto")
        # pergunta = bot.send_message(bot, chat_id, text, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview, )
        pergunta = bot.send_message(chat_id, text, **kwargs, )
        if funcao_trata:
            bot.register_next_step_handler(pergunta, funcao_trata)
        return True
    except Exception as e:
        if type(e).__name__ == 'ConnectionError':
            logging.info(f'Ocorrido o erro ao enviar text: {e}')
            time.sleep(3)
            envia_texto(chat_id, text, **kwargs)
        return False


def envia_acao(bot, chat_id, tipo='digitando'):
    try:
        log.debug("uid:" + str(chat_id)[-5:] + " envia texto")
        if tipo == 'digitando':
            bot.send_chat_action(chat_id, 'typing')

        return True

    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        return False


def envia_local(bot, chat_id, latitude, longitude, titulo='', endereco=''):
    try:
        if titulo:
            bot.send_venue(chat_id, latitude, longitude, titulo, endereco)
            return True
        else:
            bot.send_location(chat_id, latitude, longitude)
            return True
    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        return False


def envia_foto(bot, chat_id, arquivo, legenda=''):
    try:
        if legenda:
            dados_do_arquivo = open(arquivo, 'rb')
            bot.send_photo(chat_id, dados_do_arquivo, caption=str(legenda))
            dados_do_arquivo.close()
            return True
        else:
            dados_do_arquivo = open(arquivo, 'rb')
            bot.send_photo(chat_id, dados_do_arquivo)
            dados_do_arquivo.close()
            return True
    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        else:
            log.error(e)
        return False
    except FileNotFoundError:
        log.error('Foto Não encontrada')
        return False


def envia_sticker(bot, chat_id, arquivo):
    log.debug("uid:" + str(chat_id)[-5:] + " envia Sticker")

    try:
        sti = open(arquivo, 'rb')
        bot.send_sticker(bot, chat_id, sti)

    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        else:
            log.error(e)
        return False


def envia_menu(bot, chat_id, text, colunas, itens, funcao_trata=''):
    'Envia menu "padrao"\n\n\
    Use:\n\
    envia_menu(bot, chat_id, text, colunas, itens, funcao_trata, bot)\n\
    chat_id*      - int  -  id do chat (mesmo id do usuário)\n\
    texto*        - str  -  texto a ser enviado\n\
    colunas*      - int  -  numero de colunas do menu\n\
    itens*        - lst  -  itens que comporão o menu\n\
    funcao_trata  - str  -  Função que vai tratar a resposta caso seja uma pergunta"\n\
    bot    - obj  -  objeto do bot\n\n\
                       *obrigatório'
    try:
        log.debug("uid:" + str(chat_id)[-5:] + " envia menu padrão")
        menu = gera_menu(itens, colunas, 'padrao')
        pergunta = bot.send_message(
            chat_id,
            text,
            parse_mode='HTML',
            reply_markup=menu
        )
        if funcao_trata:
            bot.register_next_step_handler(pergunta, funcao_trata)
        return True

    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        return False


def envia_alerta(bot, id_call, text='', tipo='aviso'):
    if tipo == 'aviso':
        try:
            bot.answer_callback_query(
                id_call, text)
        except Exception:
            log.warn("uid:----- Erro ao enviar alerta")
    if tipo == 'vazio':
        try:
            bot.answer_callback_query(
                id_call)
        except Exception:
            log.warn("uid:----- Erro ao enviar alerta vazio")
    if tipo == 'popup':
        try:
            bot.answer_callback_query(
                id_call, text, True)
        except Exception:
            log.warn("uid:----- Erro ao enviar alerta")


def envia_inline_menu(bot, chat_id, text, colunas, itens, ids=False):
    'Envia menu "inline"\n\n\
    Use:\n\
    envia_inline_menu(bot, chat_id, text, itens, bot)\n\
    chat_id*      - int  -  id do chat (mesmo id do usuário)\n\
    texto*        - str  -  texto a ser enviado\n\
    colunas*      - int  -  numero de colunas do menu\n\
    itens*        - lst  -  itens que comporão o menu\n\
    bot    - obj  -  objeto do bot\n\n\
                       *obrigatório'
    try:
        if not ids:
            log.debug("uid:" + str(chat_id)[-5:] + " envia menu inline")
            menu = gera_menu(itens, colunas, tipo='inline')
            bot.send_message(
                chat_id,
                text,
                parse_mode='HTML',
                disable_notification=True,
                reply_markup=menu
            )
            return True
        else:
            log.debug("uid:" + str(chat_id)[-5:] + " envia menu inline COM IDS")
            menu = gera_menu(itens, colunas, tipo='inline_id')
            bot.send_message(
                chat_id,
                text,
                parse_mode='HTML',
                disable_notification=True,
                reply_markup=menu
            )
            return True

    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        return False


def edita_inline_menu(bot, chat_id, id_mensagem, text='', colunas=3, itens=[], ids=False):
    'Edita menu "inline"\n\n\
    Use:\n\
    edita_inline_menu(bot, chat_id, id_mensagem, text, itens, bot)\n\
    chat_id*      - int  -  id do chat (mesmo id do usuário)\n\
    id_mensagem*   - int  -  id da mensagem que será editada\n\
    texto         - str  -  texto a ser enviado\n\
    colunas*      - int  -  numero de colunas do menu\n\
    itens         - lst  -  itens que comporão o menu\n\
    bot    - obj  -  objeto do bot\n\n\
                       *obrigatório\n\n\n\
    Obs: se não receber itens remove o inline_keyboard\n\
         se não receber texto envia apenas os itens do menu'

    try:
        log.debug("uid:" + str(chat_id)[-5:] + " edita menu Inline")
        if text and itens:
            if not ids:
                menu = gera_menu(itens, colunas, tipo='inline')
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=id_mensagem,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=menu
                )

                return True

            else:
                menu = gera_menu(itens, colunas, tipo='inline_id')
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=id_mensagem,
                    text=text,
                    parse_mode='HTML',
                    reply_markup=menu
                )

                return True

        elif text:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=id_mensagem,
                text=text,
                parse_mode='HTML'
            )

            return True

        else:
            if not ids:
                menu = gera_menu(itens, colunas, tipo='inline')
                bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=id_mensagem,
                    reply_markup=menu
                )

                return True

            else:
                menu = gera_menu(itens, colunas, tipo='inline_id')
                bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=id_mensagem,
                    reply_markup=menu
                )

                return True

    except telebot.apihelper.ApiException as e:

        if 'bot was blocked by the user' in str(e):
            log.error('Pessoa não está mais no bot')
        return False
