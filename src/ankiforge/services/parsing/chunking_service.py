import re
import hashlib
from typing import List, Dict, Any


class ChunkingService:
    """
    Service to convert raw Markdown text into semantic chunks while
    tracking the active page number and heading path.
    """

    # Matches either AnkiForge's HTML comment or Marker's default pagination format: {1}------------------------------------------------
    PAGE_MARKER_REGEX = re.compile(r"<!--\s*PAGE:\s*(\d+)\s*-->|\{(\d+)\}-{10,}", re.IGNORECASE)
    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)

    @classmethod
    def hash_content(cls, text: str) -> str:
        """Generates MD5 hash for content"""
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    @classmethod
    def extract_chunks(cls, content: str) -> List[Dict[str, Any]]:
        """
        Splits Markdown content into paragraphs and tracks page numbers and headings.

        Returns:
            List of dicts containing:
            - index: int
            - content: str
            - page_number: int | None
            - heading_path: str | None
            - content_hash: str
        """
        chunks = []

        # Split strictly by double newline for paragraph-level chunking
        raw_blocks = content.split("\n\n")

        current_page = None
        current_heading_stack: List[str] = []

        chunk_index = 0
        for block in raw_blocks:
            block = block.strip()
            if not block:
                continue

            # Check for page markers inside the block
            page_matches = list(cls.PAGE_MARKER_REGEX.finditer(block))
            if page_matches:
                # Update current page to the last page marker found in this block
                last_match = page_matches[-1]
                current_page = int(last_match.group(1) or last_match.group(2))

                # Remove the page markers from the block content so it's clean for hashing/display
                block = cls.PAGE_MARKER_REGEX.sub("", block).strip()
                if not block:
                    continue  # Block was only a page marker

            # Check for headings
            heading_matches = list(cls.HEADING_REGEX.finditer(block))
            if heading_matches:
                for h_match in heading_matches:
                    level = len(h_match.group(1))
                    title = h_match.group(2).strip()

                    # Truncate stack to the level above the current heading
                    current_heading_stack = current_heading_stack[: level - 1]
                    # Pad stack if there were jumps (e.g. H1 directly to H3)
                    while len(current_heading_stack) < level - 1:
                        current_heading_stack.append("Unknown")

                    current_heading_stack.append(title)

            # Skip chunks that are too small (e.g. less than 20 chars), unless they are headings
            if len(block) < 20 and not heading_matches:
                continue

            heading_path_str = " > ".join(current_heading_stack) if current_heading_stack else None

            chunks.append({"index": chunk_index, "content": block, "page_number": current_page, "heading_path": heading_path_str, "content_hash": cls.hash_content(block)})
            chunk_index += 1

        return chunks
