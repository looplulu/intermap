"""Page change detection - determines when a user has actually changed the screen."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class PageSnapshot:
    """A snapshot of a page state for change detection."""
    texts: list[str]
    image_hash: str
    node_id: str | None = None
    
    def text_signature(self) -> str:
        """Create a hash from the text set for quick comparison."""
        text_str = "|".join(sorted(self.texts))
        return hashlib.md5(text_str.encode()).hexdigest()[:12]


class PageChangeDetector:
    """Detects whether the page has actually changed between observations.
    
    Three layers:
    1. Image hash - fastest, detects visual change
    2. Text signature - reliable, detects content change  
    3. Node change - semantic, detects page type change
    
    Usage:
        detector = PageChangeDetector()
        
        # First frame - always considered a change
        snapshot = detector.snapshot(texts, image_bytes)
        detector.update(snapshot)
        
        # Subsequent frames
        snapshot = detector.snapshot(texts, image_bytes)
        if detector.has_changed(snapshot):
            # Page changed, proceed with navigation
            detector.update(snapshot)
    """

    def __init__(self, text_change_threshold: float = 0.3):
        """Args:
            text_change_threshold: fraction of texts that must differ to consider page changed.
                0.3 = if 30% of texts are different, page has changed.
        """
        self._current: PageSnapshot | None = None
        self._text_change_threshold = text_change_threshold

    @staticmethod
    def compute_image_hash(image_bytes: bytes) -> str:
        """Compute a quick perceptual hash from image bytes."""
        return hashlib.md5(image_bytes).hexdigest()[:12]

    def snapshot(
        self,
        texts: list[str],
        image_bytes: bytes | None = None,
        node_id: str | None = None,
    ) -> PageSnapshot:
        """Create a page snapshot."""
        image_hash = ""
        if image_bytes:
            image_hash = self.compute_image_hash(image_bytes)
        return PageSnapshot(
            texts=texts,
            image_hash=image_hash,
            node_id=node_id,
        )

    def has_changed(self, new_snapshot: PageSnapshot) -> bool:
        """Check if the page has changed from the current state.
        
        Returns True on first call (no previous state).
        
        Priority:
        1. If node_id changed -> definitely changed
        2. If image hash changed -> likely changed (visual)
        3. If text signature changed significantly -> content changed
        4. Otherwise -> not changed
        """
        if self._current is None:
            return True

        # Layer 1: Semantic change (node level)
        if (new_snapshot.node_id and self._current.node_id 
                and new_snapshot.node_id != self._current.node_id):
            return True

        # Layer 2: Visual change (image hash)
        if (new_snapshot.image_hash and self._current.image_hash
                and new_snapshot.image_hash != self._current.image_hash):
            # Visual changed, but verify with text too (could be animation)
            if self._texts_changed_significantly(new_snapshot):
                return True
            # Visual changed but text didn't -> might be minor animation, wait

        # Layer 3: Text change
        if self._texts_changed_significantly(new_snapshot):
            return True

        return False

    def _texts_changed_significantly(self, new_snapshot: PageSnapshot) -> bool:
        """Check if text content has changed significantly."""
        if self._current is None:
            return True

        current_set = set(self._current.texts)
        new_set = set(new_snapshot.texts)

        if not current_set or not new_set:
            return bool(current_set) != bool(new_set)

        # Jaccard-like: how different are the text sets?
        common = current_set & new_set
        total = current_set | new_set
        similarity = len(common) / len(total) if total else 0
        difference = 1.0 - similarity

        return difference >= self._text_change_threshold

    def update(self, snapshot: PageSnapshot) -> None:
        """Update current state to new snapshot."""
        self._current = snapshot

    @property
    def current(self) -> PageSnapshot | None:
        return self._current
