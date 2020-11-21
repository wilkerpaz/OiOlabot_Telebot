import logging
from datetime import timedelta

from multiprocessing.dummy import Pool as ThreadPool
from threading import Thread as RunningThread

import threading

from util.database import DatabaseHandler
from util.datehandler import DateHandler
from util.feedhandler import FeedHandler
from util.funcoes_telebot import envia_texto

logger = logging.getLogger(__name__)
logging.getLogger('util.processing').setLevel(logging.DEBUG)


class BatchProcess(threading.Thread):

    def __init__(self, db: DatabaseHandler, bot):
        RunningThread.__init__(self)

        self._finished = threading.Event()
        self.db = db
        self.bot = bot

    def run(self):
        # logger.info(f'Start processing')
        if self._finished.isSet():
            return False
        self.parse_parallel()
        return True

    def parse_parallel(self):
        time_started = DateHandler.datetime.now()
        urls = self.db.get_urls_activated()
        threads = 1
        pool = ThreadPool(threads)
        pool.map(self.update_feed, urls)
        pool.close()
        pool.join()

        time_ended = DateHandler.datetime.now()
        duration = time_ended - time_started
        info_bot = self.bot.get_me()
        bot = info_bot.first_name
        # logger.warning(f"Finished updating! Parsed {str(len(urls))} rss feeds in {str(duration)}! {bot}")
        return True

    def update_feed(self, url):
        if not self._finished.isSet():
            try:
                get_url_info = self.db.get_update_url(url)
                last_url = get_url_info['last_url']
                date_last_url = DateHandler.parse_datetime(get_url_info['last_update'])
                feed = FeedHandler.parse_feed(url, 4, date_last_url + timedelta(days=-1))
                for post in feed:
                    if not hasattr(post, "published") and not hasattr(post, "daily_liturgy"):
                        logger.warning('not published' + url)
                        continue
                    # for index, post in enumerate(feed):
                    date_published = DateHandler.parse_datetime(post.published)

                    if hasattr(post, "daily_liturgy"):
                        if date_published > date_last_url and post.link != last_url \
                                and post.daily_liturgy != '':
                            message = post.title + '\n' + post.daily_liturgy
                            result = self.send_newest_messages(message, url)
                            if post == feed[-1] and result:
                                self.update_url(url=url, last_update=date_published, last_url=post.link)
                    elif date_published > date_last_url and post.link != last_url:
                        message = post.title + '\n' + post.link
                        result = self.send_newest_messages(message, url)
                        if result:
                            self.update_url(url=url, last_update=date_published, last_url=post.link)
                    else:
                        pass
                return True, url
            except TypeError as e:
                logger.error(f"TypeError {url} {str(e)}")
                return False, url, 'update_feed'

    def update_url(self, url, last_update, last_url):
        if not self._finished.isSet():
            self.db.update_url(url=url, last_update=last_update, last_url=last_url)

    def send_newest_messages(self, message, url):
        if not self._finished.isSet():
            names_url = self.db.get_names_for_user_activated(url)
            for name in names_url:
                chat_id = int(self.db.get_value_name_key(name, 'chat_id'))
                if chat_id:
                    result = envia_texto(bot=self.bot, chat_id=chat_id, text=message, parse_mode='html')
                    if not result:
                        self.errors(chat_id=chat_id, url=url)
                    return result

    def errors(self, chat_id, url):
        """ Error handling """
        try:
            disable_url = self.db.disable_url_chat(chat_id)

            logger.error(f'disable url {url} for chat_id {chat_id} from chat list')
            # logger.error("An error occurred: %s" % error)

        except ValueError as e:
            logger.error(f"error ValueError {str(e)}")

    def stop(self):
        """Stop this thread"""
        self._finished.set()
