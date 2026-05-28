from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.runtime.tools import registered_tool_names

settings = get_settings()

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_name"] = settings.app_name
templates.env.globals["app_tagline"] = settings.app_tagline
templates.env.globals["registered_tool_names"] = registered_tool_names
