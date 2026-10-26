import logging
import os
import time

import boto3

from tracker import api, sources
from tracker.models import utcnow
from tracker.store import Store

logging.getLogger("botocore").setLevel(logging.WARNING)

TOKEN_CACHE_SECONDS = 300  # a rotated token takes effect within 5 minutes

_store = Store()
_ssm = boto3.client("ssm")
_token = {"value": None, "fetched_at": 0.0}


def expected_token() -> str | None:
    if _token["value"] is None or time.monotonic() - _token["fetched_at"] > TOKEN_CACHE_SECONDS:
        try:
            param = _ssm.get_parameter(Name=os.environ["API_TOKEN_PARAM"], WithDecryption=True)
        except _ssm.exceptions.ParameterNotFound:
            return None
        _token["value"], _token["fetched_at"] = param["Parameter"]["Value"], time.monotonic()
    return _token["value"]


def handler(event, context):
    return api.handle(
        event,
        expected_token=expected_token,
        store=_store,
        fetchers=sources.FETCHERS,
        searchers=sources.SEARCHERS,
        now=utcnow(),
    )
