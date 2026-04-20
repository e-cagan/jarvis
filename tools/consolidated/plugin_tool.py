# tools/consolidated/plugin_tool.py
# Plugin yönetim tool'u — listele, yeniden yükle.

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("plugin_tool")

# Global plugin_loader reference — orchestrator tarafından set edilecek
_plugin_loader = None


def set_plugin_loader(loader):
    global _plugin_loader
    _plugin_loader = loader


@registry.register(
    name="plugins",
    description="Plugin yönetimi. Desteklenen action'lar: "
                "list (yüklü plugin'leri listele), "
                "reload (belirli bir plugin'i yeniden yükle).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "İşlem: list, reload"
            },
            "filename": {
                "type": "string",
                "description": "reload için: plugin dosya adı (örn: weather_plugin.py)"
            }
        },
        "required": ["action"]
    }
)
def plugins(action, filename=None):
    """Plugin yönetimi."""
    if _plugin_loader is None:
        return "Hata: Plugin loader başlatılmamış."

    action = action.lower().strip()

    if action == "list":
        return _plugin_loader.get_plugin_list()

    elif action == "reload":
        if not filename:
            return "Hata: 'filename' parametresi gerekli."
        return _plugin_loader.reload_plugin(filename)

    else:
        return f"Bilinmeyen action: {action}. Geçerli: list, reload"