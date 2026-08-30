"""Local Obsidian markdown rendering. No network, no apply."""

from video_paper_wiki.notes.frontmatter import render_paper_copy_markdown, year_from_arxiv_id
from video_paper_wiki.notes.list import scan_list
from video_paper_wiki.notes.show import load_paper
from video_paper_wiki.notes.section import read_paper_text, section_text
from video_paper_wiki.notes.grep import scan_matches
from video_paper_wiki.notes.stat import scan_stat
from video_paper_wiki.notes.index import upsert_index_entry
from video_paper_wiki.notes.links import paper_note_link_suffix, related_catalog_papers
from video_paper_wiki.notes.markdown import render_paper_markdown
from video_paper_wiki.notes.topics import load_topics, refresh_topic_pages

__all__ = [
    "load_topics",
    "paper_note_link_suffix",
    "refresh_topic_pages",
    "load_paper",
    "read_paper_text",
    "section_text",
    "scan_list",
    "scan_matches",
    "scan_stat",
    "related_catalog_papers",
    "render_paper_copy_markdown",
    "render_paper_markdown",
    "upsert_index_entry",
    "year_from_arxiv_id",
]
