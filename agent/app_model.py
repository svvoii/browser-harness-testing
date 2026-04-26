"""App knowledge base — stores learned patterns about the application under test."""
import json
from pathlib import Path
from datetime import datetime


class AppModel:
    """Global per-app model storing selector strategies, wait patterns, traps, and URL patterns.

    Stored as JSON in specs/<app_name>/app_model.json.
    """

    def __init__(self, app_name, app_url=None):
        self.app_name = app_name
        self.app_url = app_url
        self._data = {
            "app_name": app_name,
            "app_url": app_url,
            "selectors": {},
            "wait_patterns": [],
            "url_patterns": [],
            "known_traps": [],
            "component_states": {},
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    def load(self) -> dict:
        """Load model from specs/<app_name>/app_model.json"""
        path = self._model_path()
        if path.exists():
            self._data = json.loads(path.read_text())
        return self._data

    def save(self):
        """Save model to specs/<app_name>/app_model.json"""
        self._data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        path = self._model_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._data, indent=2))

    def _model_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "specs" / self.app_name / "app_model.json"

    def add_selector(self, key, selector):
        """Record a selector for a UI element."""
        self._data["selectors"][key] = selector

    def add_wait_pattern(self, selector, reason):
        """Record a wait pattern with explanation."""
        self._data["wait_patterns"].append({"selector": selector, "reason": reason})

    def add_url_pattern(self, pattern, description):
        """Record a URL pattern."""
        self._data["url_patterns"].append({"pattern": pattern, "description": description})

    def add_trap(self, selector, issue):
        """Record a known trap / selector that doesn't work."""
        self._data["known_traps"].append({"selector": selector, "issue": issue})

    def add_component_state(self, component_type, states):
        """Record component types and their typical states."""
        self._data["component_states"][component_type] = states

    def get_selector(self, key) -> str | None:
        """Look up a selector by key."""
        return self._data.get("selectors", {}).get(key)

    def query_selectors(self, component_type) -> list[str]:
        """Find all selectors for a component type (suffix matching)."""
        selectors = self._data.get("selectors", {})
        suffix = f"_{component_type}"
        return [s for k, s in selectors.items() if k.endswith(suffix)]

    def get_wait_pattern(self, selector) -> str | None:
        """Get wait pattern reason for a selector if known."""
        for wp in self._data.get("wait_patterns", []):
            if wp.get("selector") == selector:
                return wp.get("reason")
        return None

    def is_trap(self, selector) -> str | None:
        """Check if selector is a known trap. Returns issue description or None."""
        for trap in self._data.get("known_traps", []):
            if trap.get("selector") == selector:
                return trap.get("issue")
        return None

    def to_dict(self) -> dict:
        """Return the full model dict."""
        return self._data

    @staticmethod
    def from_json(data: dict) -> "AppModel":
        """Create model from JSON dict."""
        model = AppModel(data.get("app_name", "unknown"), data.get("app_url"))
        model._data = data
        return model