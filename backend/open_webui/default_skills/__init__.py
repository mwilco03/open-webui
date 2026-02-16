"""
Default Skills Loader System

This module provides auto-installation of default skills on application startup.
Skills are loaded from Python files in this directory and automatically installed
for all users.
"""

import logging
import importlib
import os
from pathlib import Path

log = logging.getLogger(__name__)


def get_default_skills():
    """
    Discover all default skill files in this directory.
    Returns a list of (skill_name, file_path) tuples.
    """
    skills_dir = Path(__file__).parent
    skill_files = []

    for file_path in skills_dir.glob("*.py"):
        if file_path.name.startswith("_"):
            continue  # Skip __init__.py and other private files

        skill_name = file_path.stem
        skill_files.append((skill_name, str(file_path)))

    return skill_files


def read_skill_metadata(skill_path):
    """
    Extract metadata from skill file docstring.
    Returns dict with title, description, version, etc.
    """
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract metadata from module docstring
    metadata = {
        "title": "",
        "description": "",
        "author": "Open WebUI",
        "version": "1.0.0",
        "required_open_webui_version": "0.4.0"
    }

    # Parse triple-quoted docstring at top of file
    if content.startswith('"""') or content.startswith("'''"):
        quote_char = '"""' if content.startswith('"""') else "'''"
        end_idx = content.find(quote_char, 3)
        if end_idx != -1:
            docstring = content[3:end_idx]
            for line in docstring.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key in metadata:
                        metadata[key] = value

    return metadata


async def install_default_skills(app_state):
    """
    Install all default skills on application startup.
    Called from main.py during app initialization.

    Args:
        app_state: FastAPI app.state object with database access
    """
    try:
        from open_webui.models.tools import Tools
        from open_webui.env import GITLAB_TOKEN

        default_skills = get_default_skills()
        log.info(f"Found {len(default_skills)} default skills to install")

        for skill_name, skill_path in default_skills:
            try:
                # Check if we should install this skill
                # GitLab skill requires GITLAB_TOKEN to be configured
                if skill_name == "gitlab":
                    if not GITLAB_TOKEN:
                        log.info(f"Skipping GitLab skill installation (GITLAB_TOKEN not configured)")
                        continue

                # Read skill content
                with open(skill_path, "r", encoding="utf-8") as f:
                    skill_content = f.read()

                # Read metadata
                metadata = read_skill_metadata(skill_path)

                # Check if skill already exists
                existing_skill = Tools.get_tool_by_id(f"default_{skill_name}")

                if existing_skill:
                    # Update existing skill if version changed
                    if existing_skill.meta and existing_skill.meta.get("version") != metadata["version"]:
                        log.info(f"Updating default skill: {skill_name} to version {metadata['version']}")
                        Tools.update_tool_by_id(
                            f"default_{skill_name}",
                            {
                                "content": skill_content,
                                "meta": {
                                    **metadata,
                                    "is_default_skill": True
                                }
                            }
                        )
                    else:
                        log.debug(f"Default skill already installed: {skill_name}")
                else:
                    # Install new skill
                    log.info(f"Installing default skill: {skill_name}")

                    # Create tool form
                    from open_webui.models.tools import ToolForm, ToolMeta

                    tool_form = ToolForm(
                        id=f"default_{skill_name}",
                        name=metadata["title"] or skill_name.title(),
                        content=skill_content,
                        meta=ToolMeta(
                            description=metadata["description"],
                            manifest={
                                "version": metadata["version"],
                                "author": metadata["author"],
                                "required_open_webui_version": metadata["required_open_webui_version"]
                            },
                            **{
                                "is_default_skill": True,
                                "version": metadata["version"]
                            }
                        )
                    )

                    # Insert into database with system user ID (empty string for global)
                    Tools.insert_new_tool("", tool_form)
                    log.info(f"Successfully installed default skill: {skill_name}")

            except Exception as e:
                log.exception(f"Failed to install default skill {skill_name}: {e}")
                continue

        log.info("Default skills installation complete")

    except Exception as e:
        log.exception(f"Error during default skills installation: {e}")


async def uninstall_default_skill(skill_name):
    """
    Uninstall a default skill.

    Args:
        skill_name: Name of the skill to uninstall (e.g., "gitlab")
    """
    try:
        from open_webui.models.tools import Tools

        skill_id = f"default_{skill_name}"
        Tools.delete_tool_by_id(skill_id)
        log.info(f"Uninstalled default skill: {skill_name}")

    except Exception as e:
        log.exception(f"Failed to uninstall default skill {skill_name}: {e}")
