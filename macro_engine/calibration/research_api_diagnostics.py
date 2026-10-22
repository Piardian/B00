"""Record provider outcomes without changing requests, routing or live code."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from unittest.mock import patch


@contextmanager
def record_provider_outcomes(root, router):
    from core import key_manager
    original = key_manager.genai.Client
    path = Path(root)/'research_provider_attempts.jsonl'
    secrets = [x for x in router.keys if x]

    def client_factory(*args, **kwargs):
        # Historical reconstruction needs completed inference rather than a
        # recreation of today's transient 25-second transport deadline.
        # Only research clients use this; generation parameters are untouched.
        options=kwargs.get('http_options')
        if options is not None:
            kwargs['http_options']=options.model_copy(update={'timeout':90000})
        client = original(*args, **kwargs)
        models = client.models
        generate = models.generate_content

        def monitored(*request_args, **request_kwargs):
            started = time.time()
            record = {'wall_epoch': started, 'model': request_kwargs.get('model'),
                      'research_http_timeout_ms':90000}
            try:
                response = generate(*request_args, **request_kwargs)
                record['status'] = 'SUCCESS'
                return response
            except Exception as error:
                record.update(status='ERROR', code=getattr(error, 'code', None),
                              error_type=type(error).__name__, message=str(error),
                              details=getattr(error, 'details', None))
                raise
            finally:
                record['elapsed_seconds'] = round(time.time()-started, 3)
                serialized = json.dumps(record, default=str, ensure_ascii=True)
                for secret in secrets:
                    serialized = serialized.replace(secret, '[REDACTED]')
                with path.open('a', encoding='utf-8') as handle:
                    handle.write(serialized+'\n')
        models.generate_content = monitored
        return client

    with patch.object(key_manager.genai, 'Client', client_factory):
        yield
