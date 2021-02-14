from app.bot import bot
from app.config import TEST, logger


def infinite_pooling():
    while True:
        try:
            bot.polling(none_stop=True)
        finally:
            logger.exception('Bot crashed')


if __name__ == '__main__':
    logger.info('RUN')
    if TEST:
        bot.polling()
    else:
        infinite_pooling()
