import functools


def lazy_property(method):
    """Декоратор.
    Сохраняет ответ метода только если она был не None в аттрибуте класса
    с названием __ + имя метода"""
    attr_name = '__' + method.__name__

    @property
    @functools.wraps(method)
    def attr_saver(self):
        if not hasattr(self, attr_name):
            method_result = method(self)
            if method_result:
                setattr(self, attr_name, method_result)
        return getattr(self, attr_name, None)

    return attr_saver
