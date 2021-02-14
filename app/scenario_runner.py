from collections.abc import Callable
from dataclasses import dataclass
from typing import Set
import inspect

from app.base_scenario import MemberStateHandler, BotSignal, RoutePattern, StopSignalException
from app.config import logger
from app.handlers import Handler

# Ни в коем случае не удалять этот импорт. Иначе ничего работать не будет
from app.scenarios import *


@dataclass
class SignalHandler:
    scenario: type(BaseScenario) = None
    method: Callable = None
    args: tuple = ()


class RouteResolver:
    """
    Класс отвечает за выбор подходящего роута из словаря routes нужного сценария
    """

    def __init__(self, scenario, routes):
        self.scenario = scenario
        self.routes = routes
        self.signal_handler = SignalHandler(scenario=scenario,
                                            method=getattr(scenario, BaseScenario.default_response.__name__))

    def method_by_name(self, name):
        return getattr(self.scenario, name)

    def _iter_routes(self, appeal='', signal=None):
        if appeal in self.routes:
            self.signal_handler.method = self.routes[appeal]
            return
        for key, value in self.routes.items():
            if not isinstance(key, RoutePattern):
                key = RoutePattern.from_value(key)
            resolved = key.fit(text=appeal, signal=signal, value=value)
            if resolved:
                self.signal_handler.method = resolved.value
                self.signal_handler.args = resolved.args
                return

        if appeal and hasattr(self.scenario, appeal):
            self.signal_handler.method = getattr(self.scenario, appeal)

    def from_state(self, state: dict):
        appeal = state.get('appeal', '')
        args = state.get('args', ())
        self._iter_routes(appeal=appeal)
        self.signal_handler.args = args or self.signal_handler.args

    def from_signal(self, signal):
        call_data = signal.call and signal.call.data or ''
        print(call_data)
        self._iter_routes(signal=signal, appeal=call_data)


class ScenarioRunner:
    """
    Главный распределитель, решает, какой метод будет вызван для обработки сообщения или сигнала
    Сначала выбирается подходящий сценарий - класс наследник BaseScenario
        1. Если есть поле scenario в state то выбирается соответствующий класс
        2. Иначе берется сценарий по умолчанию (аттрибут default = True)
    Метод определяется следующим образом
        1. При первом вызове (то есть сразу от пользователя через бота) приоритет делается на текст сообщения
        или call.data, если в routes есть подходящая строка, следуем за ней
        2. Если это уже редирект, то в routes проверяется значение state['appeal']
        3. Если в 1-ом или 2-ом пункте в routes нет правила, но есть метод соответствующего названия, он вызывается
        4. Если метода нет, возвращается default_response
    """

    @classmethod
    def assert_valid(cls):
        assert len(cls._get_scenarios()) > 0
        cls._get_default_scenario()

    @staticmethod
    def _get_scenarios() -> Set[BaseScenario]:
        """
        Возвращает set всех классов сценариев. В том числе вложенных
        То есть всех наследников BaseScenario
        """
        klass = BaseScenario
        subclasses = set()
        work = [klass]
        while work:
            parent = work.pop()
            for child in parent.__subclasses__():
                if child not in subclasses:
                    subclasses.add(child)
                    work.append(child)
        return subclasses

    @classmethod
    def _get_scenario_dict(cls):
        """
        Словарь всех сценариев по названию {name: класс сценария}
        """
        scenarios = cls._get_scenarios()
        return {
            scenario.__name__: scenario
            for scenario in scenarios
        }

    @classmethod
    def _get_default_scenario(cls):
        classes = cls._get_scenarios()
        default_classes = [cl for cl in classes if getattr(cl, 'default', None)]
        assert len(default_classes) == 1, 'Should be exactly one default scenario. Set default = True in one class'
        return default_classes[0]

    @classmethod
    def _get_handler(cls, signal: BotSignal):
        return Handler(chat_id=signal.message.chat.id, user_id=signal.message.from_user.id,
                       chat_username=signal.message.chat.username)

    @classmethod
    def _get_scenario_routes(cls, scenario: type(BaseScenario)) -> dict:
        """
        :param scenario:
        :return: словарь редиректов по умолчанию, собирает его рекурсивно в корня дерева, то есть
        с самого класса BaseScenario и дальше по иерархии вниз
        """
        routes = {}
        for base in scenario.__bases__:
            if hasattr(base, 'routes'):
                routes.update(cls._get_scenario_routes(base))
        routes.update(scenario.routes)
        return routes

    @classmethod
    def _resolve_scenario_handler(cls, signal: BotSignal, state: dict, first_time: bool) -> SignalHandler:
        """
        Очень важная функция, она непосредственно определяет, кто будет вызван на основании
        входных данных
        :return:
        """
        scenario = cls._get_scenario_dict().get(state.get('scenario'), cls._get_default_scenario())
        routes = cls._get_scenario_routes(scenario)

        resolver = RouteResolver(scenario, routes)
        resolver.from_state(state)
        if first_time:
            resolver.from_signal(signal)

        if not inspect.isfunction(resolver.signal_handler.method):
            return cls._resolve_scenario_handler(signal, MemberStateHandler(resolver.signal_handler.method), first_time)
        return resolver.signal_handler

    @classmethod
    def run_scenario(cls, handler: Handler, signal: BotSignal, state: dict, first_time=True):
        """
        Выполняет грязную работу, запускает нужный метод на основе решения
        _resolve_scenario_handler, делает это итеративно, до тех пор пока выбрасывается исключение
        RedirectException
        """
        signal_handler = cls._resolve_scenario_handler(signal=signal, state=state, first_time=first_time)
        scenario_cls = signal_handler.scenario
        scenario_obj = scenario_cls(message=signal.message, call=signal.call, handler=handler, bot=signal.bot,
                                    first_time=first_time)
        try:
            scenario_obj.before()
            signal_handler.method(scenario_obj, *signal_handler.args)
            scenario_obj.after()
            if signal.call:
                # TODO Проверять переопределение метода в классе
                scenario_obj.default_callback_answer()
        except StopSignalException:
            """Nothing do more"""
        except RedirectException as continue_exception:
            state = continue_exception.state
            scenario_obj.set_state({**state, 'args': (), 'appeal': ''})
            cls.run_scenario(handler, signal, state, first_time=continue_exception.process_signal)

    @classmethod
    def process_signal(cls, signal: BotSignal):
        """
        Входящая функция, с нее начинается путешествие нашего сигнала
        На самом деле просто вызывается обработчик run_scenario
        состояние state читается из базы данных при наличие
        :param signal:
        :return:
        """
        try:
            if not signal.message and signal.call:
                signal.message = signal.call.message

            handler = cls._get_handler(signal)
            state = MemberStateHandler(handler.member and handler.member.state)
            if state.get('appeal'):
                handler.member.state = {**state, 'appeal': '', 'args': []}
            cls.run_scenario(handler=handler, signal=signal, state=state)
        except Exception:
            # with suppress(Exception):
            #     handler._save_models()
            # with suppress(Exception):
            #     handler._close_session()
            # with suppress(Exception):
            #     handler.session.rollback()
            # signal.bot.send_message(signal.message.chat.id, 'На сервере произошла ошибка')
            logger.exception('Signal handling exception')
            import os
            if os.environ.get('TEST'):
                raise


ScenarioRunner.assert_valid()
