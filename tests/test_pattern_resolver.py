import pytest

from app.base_scenario import RoutePattern


def test_route_pattern():
    value = 213123
    assert RoutePattern(text='123').fit_text('123', value).value == value
    assert RoutePattern(text='hello').fit_text('123', value).value is None
    assert RoutePattern(func=lambda x: x.startswith('x'))\
               .fit_text('x234', value).value == value
    assert RoutePattern.from_value('asfd').text == 'asfd'
    assert RoutePattern.from_value('foo').func is None
    assert RoutePattern.from_value(lambda: print()).func is not None
    assert RoutePattern.from_value('/echo').fit_text('/echo 123', value).value == value
    assert RoutePattern.from_value('/echo').fit_text('/echo 123', value).args == ('123',)
