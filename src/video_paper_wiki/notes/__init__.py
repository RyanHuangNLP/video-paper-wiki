"""Local Obsidian markdown rendering. No network, no apply."""

from video_paper_wiki.notes.index import upsert_index_entry
from video_paper_wiki.notes.markdown import render_paper_markdown
from video_paper_wiki.notes.topics import load_topics, refresh_topic_pages

__all__ = [
    "load_topics",
    "refresh_topic_pages",
    "render_paper_markdown",
    "upsert_index_entry",
]
