import logging

from tracker import checker

logging.getLogger("botocore").setLevel(logging.WARNING)


def handler(event, context):
    return checker.run()
