"""Prepare a child-only Gemini credential environment; never edit live config."""
import os
from pathlib import Path
from dotenv import dotenv_values

LIVE_KEY_NAMES = ('GEMINI_USER_A_KEY', 'GEMINI_USER_B_KEY', 'GEMINI_USER_C_KEY',
                  'GEMINI_USER_D_KEY', 'GEMINI_API_KEY')


def research_environment(path, repo_root, inherited=None):
    path = Path(path)
    if not path.is_file():
        raise ValueError('RESEARCH_CONFIG_MISSING: configure config/research.env locally')
    values = dotenv_values(path)
    key = (values.get('RESEARCH_GEMINI_API_KEY') or '').strip()
    project = (values.get('RESEARCH_PROJECT_ID') or '').strip()
    plan = (values.get('RESEARCH_PLAN') or '').strip().upper()
    if not key or not project:
        raise ValueError('RESEARCH_SETUP_REQUIRED: separate free project ID and API key are missing')
    if plan != 'FREE':
        raise ValueError('FREE_PLAN_REQUIRED: paid research use is not authorized')
    environment = dict(os.environ if inherited is None else inherited)
    live_keys = {environment.get(name) for name in LIVE_KEY_NAMES}
    for file in (Path(repo_root)/'.env', Path(repo_root)/'macro_engine/.env'):
        if file.is_file():
            live = dotenv_values(file)
            live_keys.update(live.get(name) for name in LIVE_KEY_NAMES)
    if key in live_keys:
        raise ValueError('LIVE_CREDENTIAL_REJECTED: research must not reuse a live API key')
    # dotenv uses override=False. Empty process variables prevent all local
    # live-key slots from being silently loaded into the research subprocess.
    for name in LIVE_KEY_NAMES:
        environment[name] = ''
    environment['GEMINI_API_KEY'] = key
    environment['BEGONYA_RESEARCH_DIAGNOSTICS'] = '1'
    environment['ENABLE_MACRO_TELEGRAM_NOTIFICATIONS'] = 'false'
    return environment, {
        'credential_profile': 'SEPARATE_RESEARCH_FREE_PLAN_DECLARED',
        'research_project_id': project,
        'provider_plan_verified_programmatically': False,
        'live_keys_excluded': True,
        'paid_use_authorized': False,
    }
