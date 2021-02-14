from app.base_scenario import MemberStateHandler, BaseScenario


def test_state_handler():
    assert MemberStateHandler('Echo') == {'scenario': 'Echo'}
    assert MemberStateHandler('Echo', 'hello') == {'scenario': 'Echo', 'appeal': 'hello'}
    assert MemberStateHandler('Echo', 'hello') == {'scenario': 'Echo', 'appeal': 'hello'}
    assert MemberStateHandler('Echo', 'hello', 1, 2, 3) == {'scenario': 'Echo', 'appeal': 'hello', 'args': (1, 2, 3)}
    assert MemberStateHandler({'scenario': 's1'}) == {'scenario': 's1'}

    def func():
        pass

    class FlexScenario(BaseScenario):
        pass

    assert MemberStateHandler({'scenario': FlexScenario, 'appeal': func}) == {'scenario': 'FlexScenario',
                                                                              'appeal': 'func'}
    assert MemberStateHandler(FlexScenario, func) == {'scenario': 'FlexScenario', 'appeal': 'func'}
    assert MemberStateHandler(FlexScenario) == {'scenario': 'FlexScenario'}
    assert MemberStateHandler(a=123, b=222) == {'a': 123, 'b': 222}
    assert MemberStateHandler(FlexScenario, foo='hello') == {'scenario': 'FlexScenario', 'foo': 'hello'}
    assert MemberStateHandler(appeal='aa', foo='hello') == {'appeal': 'aa', 'foo': 'hello'}
