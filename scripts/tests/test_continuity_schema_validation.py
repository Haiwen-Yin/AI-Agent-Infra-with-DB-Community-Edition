"""Migration validation must distinguish semantic CHECK drift from formatting."""
import pytest
from lib.continuity_schema_validation import check_expression,default_expression


def test_native_string_defaults_preserve_literal_identity():
    assert default_expression("'TASK'::character varying")=="'TASK'"
    assert default_expression(" ('TASK') ")=="'TASK'"
    assert default_expression("'Task'")!="'TASK'"
    assert default_expression("'a (b)'::text")=="'a (b)'"
    assert default_expression(' CURRENT_TIMESTAMP ')== 'CURRENT_TIMESTAMP'


def test_vendor_array_and_casts_preserve_check_semantics():
    expected="STATUS IN ('ACTIVE','RETIRED')"
    pg="((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'RETIRED'::character varying])::text[]))"
    assert check_expression(expected)==check_expression(pg)
    assert check_expression(expected)==check_expression('"STATUS" IN (\'RETIRED\',\'ACTIVE\')')


def test_changed_boolean_grouping_and_states_are_not_equivalent():
    assert check_expression("(A=1 OR B=2) AND C=3")!=check_expression("A=1 OR (B=2 AND C=3)")
    assert check_expression("STATUS IN ('ACTIVE','RETIRED')")!=check_expression("STATUS IN ('ACTIVE','DELETED')")
    assert check_expression('VERSION>0')!=check_expression('VERSION>=0')
    assert check_expression('X IS NULL')!=check_expression('X IS NOT NULL')


def test_postgresql_numeric_literal_bounds_preserve_confidence_checks():
    expected = 'CONFIDENCE IS NULL OR (CONFIDENCE>=0 AND CONFIDENCE<=1)'
    native = '((confidence IS NULL) OR ((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)))'
    assert check_expression(expected) == check_expression(native)
    assert check_expression(native) != check_expression('CONFIDENCE IS NULL OR (CONFIDENCE>=0 AND CONFIDENCE<=2)')
    with pytest.raises(ValueError):
        check_expression('CONFIDENCE::numeric>=0')


def test_cast_and_identifier_normalization_never_rewrite_string_values():
    for literal in ('0::numeric', 'A::text', 'a (b)', 'a "b"', "a''b", '__CX_CHECK_LITERAL_0__'):
        expression="STATUS='"+literal+"'"
        assert check_expression(expression)==check_expression(' ( '+expression+' ) ')
    assert check_expression("STATUS='0::numeric'")!=check_expression("STATUS='0'")
    assert check_expression("STATUS='A::text'")!=check_expression("STATUS='A'")
    assert check_expression("STATUS='a b'")!=check_expression("STATUS='ab'")


def test_context_budget_integer_sum_matches_native_parentheses_without_erasing_drift():
    expected='SOURCE_BUDGET+SYSTEM_TOKENS+TOOL_TOKENS+OUTPUT_RESERVE<=CONTEXT_WINDOW'
    native='((((source_budget + system_tokens) + tool_tokens) + output_reserve) <= context_window)'
    assert check_expression(expected)==check_expression(native)
    assert check_expression(expected)!=check_expression('SOURCE_BUDGET+SYSTEM_TOKENS+TOOL_TOKENS<=CONTEXT_WINDOW')
    assert check_expression(expected)!=check_expression(expected.replace('<=','<'))
    assert check_expression('A+1 BETWEEN 2 AND B+3')==check_expression('(A+1)>=2 AND (A+1)<=(B+3)')
    assert check_expression('A+1>2 AND B=3')==check_expression('(A+1)>2 AND (B=3)')


@pytest.mark.parametrize('value',['UNTRUSTED_FUNCTION(X)','VERSION*1>0','VERSION>0; DROP TABLE X','(X=1','X=1)',
    "A+'1'>0",'(A=1)+2>0','A+NULL>0','A+-1>0','A::numeric+1>0','A||B=1'])
def test_unsupported_or_malformed_checks_fail_closed(value):
    with pytest.raises((ValueError,IndexError)):
        check_expression(value)
