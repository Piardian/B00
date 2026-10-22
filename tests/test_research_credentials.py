import pytest

from scripts.research_credentials import research_environment, LIVE_KEY_NAMES


def setup_config(tmp_path, key='research_test_only', plan='FREE'):
    config=tmp_path/'research.env'
    config.write_text(f'RESEARCH_PROJECT_ID=test-project\nRESEARCH_GEMINI_API_KEY={key}\nRESEARCH_PLAN={plan}\n')
    return config


def test_research_child_excludes_all_live_slots_and_preserves_parent(tmp_path):
    parent={name:'live_test_only' for name in LIVE_KEY_NAMES}
    parent['UNRELATED_SETTING']='keep'
    result,metadata=research_environment(setup_config(tmp_path),tmp_path,parent)
    assert all(result[name]=='' for name in LIVE_KEY_NAMES if name!='GEMINI_API_KEY')
    assert result['GEMINI_API_KEY']=='research_test_only'
    assert parent['GEMINI_API_KEY']=='live_test_only'
    assert result['UNRELATED_SETTING']=='keep'
    assert metadata['paid_use_authorized'] is False
    assert 'research_test_only' not in str(metadata)


def test_local_live_key_cannot_be_reused_as_research(tmp_path):
    (tmp_path/'.env').write_text('GEMINI_USER_A_KEY=research_test_only\n')
    with pytest.raises(ValueError,match='LIVE_CREDENTIAL_REJECTED'):
        research_environment(setup_config(tmp_path),tmp_path,{})


def test_paid_profile_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='FREE_PLAN_REQUIRED'):
        research_environment(setup_config(tmp_path,plan='PAID'),tmp_path,{})


def test_blank_configuration_fails_before_any_request(tmp_path):
    with pytest.raises(ValueError,match='RESEARCH_SETUP_REQUIRED'):
        research_environment(setup_config(tmp_path,key=''),tmp_path,{})
