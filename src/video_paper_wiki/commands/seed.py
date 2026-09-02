"""Compatibility wrappers for functional seed commands."""
from video_paper_wiki.commands.domain import seed_validate, seed_status

def validate(args=None): return seed_validate(args)
def status(args=None): return seed_status(args)
